"""Phase 4 PR1 — FastAPI host: session lifecycle, turns, live event stream.

The LLM is mocked (same _fake_stream pattern as test_graph); the greeting is
hardcoded in the engine so session creation needs no model at all. TestClient
runs the app's lifespan, so the event hub gets a real loop.

Run: pytest tests/test_api.py -v
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _fake_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _fake_stream(content=None):
    def _gen(**kwargs):
        if content:
            yield content
        return _fake_message(content=content)

    return _gen


@pytest.fixture()
def client(db_connection, monkeypatch, tmp_path):
    # Isolate the runtime-config overrides file: the app lifespan re-applies it
    # to os.environ GLOBALLY, so a real .api_config.json (written by a live
    # config-page session) leaked CLASSIFIER=on into the deterministic suite.
    monkeypatch.setenv("API_CONFIG_FILE", str(tmp_path / "api_config.json"))
    from app import main
    from app.main import app

    monkeypatch.setattr(main.settings, "checkpoint_path", tmp_path / "checkpoints.sqlite")

    with TestClient(app) as c:
        yield c


def _create(client, phone="+37060012353"):
    resp = client.post("/sessions", json={"caller_phone": phone})
    assert resp.status_code == 201
    return resp.json()


def _card_from_reading(customer_id: str) -> set[str]:
    """Which card the line's own reading leaves standing (wave 4: the tool returns signals and
    the cards decide, so a demo button is checked by what the FACTS then allow)."""
    import json as _json

    from agent.case import candidates
    from agent.facts import facts_from_signals
    from agent.tools import execute_tool

    payload = _json.loads(execute_tool("diagnose_connection", {"customer_id": customer_id}))
    facts = facts_from_signals(payload.get("signals"))
    return {c.fault for c in candidates(facts) if c.status == "matched"}


class TestLifecycle:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_create_returns_greeting(self, client):
        data = _create(client)
        assert data["session_id"]
        assert "Labas" in data["greeting"]

    def test_sessions_share_one_checkpointer_closed_on_shutdown(
        self, db_connection, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("API_CONFIG_FILE", str(tmp_path / "api_config.json"))
        from app import main

        monkeypatch.setattr(main.settings, "checkpoint_path", tmp_path / "checkpoints.sqlite")
        with TestClient(main.app) as c:
            first, second = _create(c)["session_id"], _create(c)["session_id"]
            saver = main.manager._checkpointer
            assert saver is not None
            for sid in (first, second):
                assert main.manager.get(sid).session._graph.checkpointer is saver
        assert main.manager._checkpointer is None  # closed and released on shutdown
        assert (tmp_path / "checkpoints.sqlite").exists()

    def test_unknown_session_404(self, client):
        assert client.post("/sessions/nope/turns", json={"text": "labas"}).status_code == 404
        assert client.delete("/sessions/nope").status_code == 404

    def test_delete_ends_session(self, client):
        sid = _create(client)["session_id"]
        assert client.delete(f"/sessions/{sid}").json() == {"ended": True}
        # Gone from the registry — a second delete is a 404.
        assert client.delete(f"/sessions/{sid}").status_code == 404


class TestTurns:
    def test_turn_returns_reply_and_summary(self, client):
        sid = _create(client)["session_id"]
        with (
            patch(
                "agent.speak.node.stream_tool_completion",
                side_effect=_fake_stream(content="Supratau, tikrinu."),
            ),
            patch(
                "agent.speak.node.get_last_call_stats",
                return_value={"model": "gpt-4o-mini", "input_tokens": 100, "output_tokens": 20},
            ),
        ):
            # An off-script question — falls through the scripted ladder to the LLM.
            resp = client.post(
                f"/sessions/{sid}/turns", json={"text": "O kas jūs tokie, kokia įmonė?"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"] == "Supratau, tikrinu."
        turn = data["turn"]
        assert turn["nodes"]  # which graph node ran
        assert turn["latency_ms"] >= 0
        assert turn["engine"] in ("scripted", "llm")

    def test_scripted_turn_marked_engine(self, client):
        # The anamnesis question is engine-composed — no LLM call at all.
        sid = _create(client)["session_id"]
        resp = client.post(f"/sessions/{sid}/turns", json={"text": "neveikia internetas"})
        assert resp.status_code == 200
        data = resp.json()
        assert "skambinate dėl" in data["reply"]  # etalonas #2: address, no anamnesis
        assert data["turn"]["engine"] == "scripted"
        assert data["turn"]["llm_calls"] == 0

    def test_sessions_are_isolated(self, client):
        a = _create(client, phone="+37060012353")["session_id"]
        b = _create(client, phone="+37060020101")["session_id"]
        assert a != b
        client.post(f"/sessions/{a}/turns", json={"text": "neveikia internetas"})
        from app.main import manager

        assert manager.get(a).session.state.intake.problem_type == "internet_down"
        assert manager.get(b).session.state.intake.problem_type is None


class TestEventStream:
    def test_ws_receives_turn_events(self, client):
        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            ws.send_json({"type": "turn", "text": "neveikia internetas"})
            seen = set()
            reply = None
            for _ in range(40):
                msg = ws.receive_json()
                seen.add(msg.get("type"))
                if msg.get("type") == "reply":
                    reply = msg
                # The summary may flush after the direct reply frame — read on
                # until both arrived.
                if reply is not None and "turn_summary" in seen:
                    break
            assert reply is not None and "skambinate dėl" in reply["reply"]
            # The brain-panel feed: engine events arrived live on the socket.
            assert "user_turn" in seen
            assert "turn_summary" in seen

    def test_ws_unknown_session_rejected(self, client):
        from starlette.websockets import WebSocketDisconnect as ClientDisconnect

        with pytest.raises(ClientDisconnect):
            with client.websocket_connect("/ws/call/nope") as ws:
                ws.receive_json()


class TestDisconnect:
    """F-3: a closed call socket ends the call after the grace — unless it reconnects."""

    def _wait_gone(self, sid, seconds=3.0):
        import time

        from app import main

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if main.manager.active_count == 0 or sid not in main.manager._sessions:
                return True
            time.sleep(0.05)
        return False

    def test_disconnect_ends_the_call_with_a_record(self, client, db_connection, monkeypatch):
        from app import main

        monkeypatch.setattr(main.settings, "ws_disconnect_grace_seconds", 0.1)
        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}"):
            pass

        assert self._wait_gone(sid)
        import time

        row = None
        deadline = time.monotonic() + 5.0
        while row is None and time.monotonic() < deadline:  # the record lands after the pop
            with db_connection.cursor() as cur:
                cur.execute(
                    "SELECT outcome, transport_end FROM conversations WHERE session_id = ?",
                    (sid,),
                )
                found = cur.fetchone()
            row = dict(found) if found else None
            if row is None:
                time.sleep(0.05)
        assert row is not None
        assert row["transport_end"] == "ws_disconnect"
        assert row["outcome"] != "ws_disconnect"  # F-4

    def test_a_reconnect_within_the_grace_keeps_the_call(self, client, monkeypatch):
        import time

        from app import main

        monkeypatch.setattr(main.settings, "ws_disconnect_grace_seconds", 0.5)
        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}"):
            pass
        with client.websocket_connect(f"/ws/call/{sid}"):
            time.sleep(0.8)
            assert client.delete(f"/sessions/{sid}").json() == {"ended": True}


class TestDashboard:
    """The dashboard page and its demo scenarios."""

    def test_dashboard_served(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Agento vidus" in resp.text
        assert "{{v}}" not in resp.text  # the cache buster is filled in
        assert client.get("/static/js/brain.js").status_code == 200

    def test_demo_scenarios_are_complete(self, client):
        scenarios = client.get("/demo/scenarios").json()["scenarios"]
        assert len(scenarios) >= 9
        for s in scenarios:
            assert s["phone"].startswith("+370") and s["say"] and "outcome" in s["expect"]
        assert len({s["id"] for s in scenarios}) == len(scenarios)


class TestArchive:
    """PR3 — past-call records: list, detail (trace + stats), audio, safety."""

    @pytest.fixture()
    def archived_call(self, client, monkeypatch, tmp_path):
        # A full lifecycle with the trace + recordings under tmp: create ->
        # scripted turn -> delete (writes the conversations row + jsonl).
        monkeypatch.setenv("TRACE_DIR", str(tmp_path))
        monkeypatch.setenv("API_RECORD_DIR", str(tmp_path))
        sid = _create(client)["session_id"]
        client.post(f"/sessions/{sid}/turns", json={"text": "neveikia internetas"})
        (tmp_path / sid).mkdir()
        (tmp_path / sid / "turn_01_user.wav").write_bytes(b"RIFFwav")
        client.delete(f"/sessions/{sid}")
        return sid

    def test_list_contains_archived_call(self, archived_call, client):
        calls = client.get("/calls").json()["calls"]
        assert any(c["session_id"] == archived_call for c in calls)
        row = next(c for c in calls if c["session_id"] == archived_call)
        assert row["purpose"] == "internet_down"

    def test_review_filter_lists_only_calls_for_review(self, archived_call, client):
        # The archived call hung up before identification: a record for review (D-14).
        row = next(
            c for c in client.get("/calls").json()["calls"] if c["session_id"] == archived_call
        )
        assert row["needs_review"] is True and row["transport_end"] == "client_closed"
        review = client.get("/calls?needs_review=1").json()["calls"]
        assert any(c["session_id"] == archived_call for c in review)
        assert all(c["needs_review"] for c in review)

    def test_detail_has_transcript_events_audio_stats(self, archived_call, client):
        resp = client.get(f"/calls/{archived_call}")
        assert resp.status_code == 200
        d = resp.json()
        assert any("skambinate dėl" in (m["text"] or "") for m in d["transcript"])
        # Caller lines from SCRIPTED turns come from the trace — the message
        # history misses them (engine appends user turns only on the LLM path).
        assert any(
            m["role"] == "user" and "neveikia internetas" in m["text"] for m in d["transcript"]
        )
        assert any(e.get("type") == "session_end" for e in d["events"])
        assert d["audio"] == ["turn_01_user.wav"]
        assert d["stats"]["llm_calls"] == 0  # scripted call — and cost 0
        assert d["stats"]["cost_usd"] == 0

    def test_audio_served_and_path_safe(self, archived_call, client):
        ok = client.get(f"/calls/{archived_call}/audio/turn_01_user.wav")
        assert ok.status_code == 200 and ok.content == b"RIFFwav"
        assert client.get(f"/calls/{archived_call}/audio/..%2Fsecret.wav").status_code == 404
        assert client.get(f"/calls/{archived_call}/audio/nope.wav").status_code == 404
        assert client.get("/calls/..%2F..%2Fetc/audio/x.wav").status_code == 404

    def test_unknown_call_404(self, client):
        assert client.get("/calls/nonexistent-session-id").status_code == 404


class TestConfigPage:
    """Config page (Phase 4): whitelist edits, live application, persistence.
    NOTE: admin auth required before public hosting (agreed 2026-08-06)."""

    @property
    def persist(self):
        # The client fixture isolates API_CONFIG_FILE per test — use ITS path.
        import os
        from pathlib import Path

        return Path(os.environ["API_CONFIG_FILE"])

    def test_get_lists_settings_with_values_and_scopes(self, client):
        items = client.get("/admin/config").json()["settings"]
        keys = {i["key"] for i in items}
        assert {"agent_model", "CLASSIFIER", "ASR_BACKEND", "TTS_VOICE"} <= keys
        for i in items:
            assert i["value"] in i["options"] or i["key"] == "agent_model"
            assert i["scope"] in ("immediate", "new_calls")

    def test_put_applies_env_and_persists(self, client, monkeypatch):
        import json as _json
        import os

        monkeypatch.setenv("CLASSIFIER", "on")
        resp = client.put("/admin/config", json={"CLASSIFIER": "off"})
        assert resp.status_code == 200
        assert os.environ["CLASSIFIER"] == "off"
        assert _json.loads(self.persist.read_text(encoding="utf-8"))["CLASSIFIER"] == "off"
        client.put("/admin/config", json={"CLASSIFIER": "on"})  # restore

    def test_put_model_reaches_agent_config(self, client):
        from agent.config import get_config

        before = get_config().model
        try:
            client.put("/admin/config", json={"agent_model": "gpt-4o"})
            assert get_config().model == "gpt-4o"
        finally:
            client.put("/admin/config", json={"agent_model": before})

    def test_put_voice_key_clears_adapter_caches(self, client, monkeypatch):
        from app import voice

        monkeypatch.setattr(voice, "_build_tts", voice._build_tts)  # real cached fn
        voice._build_tts.cache_clear()
        resp = client.put("/admin/config", json={"TTS_VOICE": "lt-LT-OnaNeural"})
        assert resp.status_code == 200
        assert voice._build_tts.cache_info().currsize == 0
        client.put("/admin/config", json={"TTS_VOICE": "lt-LT-LeonasNeural"})

    def test_put_rejects_unknown_key_and_bad_value(self, client):
        assert client.put("/admin/config", json={"OPENAI_API_KEY": "x"}).status_code == 400
        assert client.put("/admin/config", json={"TTS_ENGINE": "elevenlabs"}).status_code == 400

    def test_persisted_overrides_reapplied(self, client, monkeypatch):
        import os

        self.persist.write_text('{"SIMULATE_BRIDGE": "on"}', encoding="utf-8")
        monkeypatch.delenv("SIMULATE_BRIDGE", raising=False)
        from app import runtime_config

        runtime_config.load_persisted()
        assert os.environ["SIMULATE_BRIDGE"] == "on"


class TestSimulatePlug:
    """DEMO plug button (2026-08-12): the tester plays the caller's hands —
    POST makes an unbound device appear on the demo line; the agent only ever
    learns about it from its next telemetry read. Manual by design (no
    keyword auto-simulation)."""

    def test_plug_before_identification_is_409(self, client):
        sid = _create(client)["session_id"]
        assert client.post(f"/sessions/{sid}/simulate-plug").status_code == 409
        client.delete(f"/sessions/{sid}")

    def test_plug_makes_device_visible_then_unplug_clears(self, client):
        import json as _json

        sid = _create(client)["session_id"]
        from app.main import manager

        manager.get(sid).session.state.identity.customer_id = "CUST009"
        resp = client.post(f"/sessions/{sid}/simulate-plug")
        assert resp.status_code == 200 and resp.json()["ok"] is True
        assert "no_mac_observed" not in _card_from_reading("CUST009")
        resp = client.post(f"/sessions/{sid}/simulate-plug", params={"unplug": "true"})
        assert resp.status_code == 200
        assert _card_from_reading("CUST009") == {"no_mac_observed"}
        client.delete(f"/sessions/{sid}")

    def test_unknown_session_is_404(self, client):
        assert client.post("/sessions/nope/simulate-plug").status_code == 404


class TestSimulatePower:
    """DEMO power button (v3 stage 4): the caller plugs the dead router's power lead back
    in — the registered device shows on the line again, and the dead-router card falls."""

    def test_power_before_identification_is_409(self, client):
        sid = _create(client)["session_id"]
        assert client.post(f"/sessions/{sid}/simulate-power").status_code == 409
        client.delete(f"/sessions/{sid}")

    def test_power_brings_the_router_back(self, client):
        sid = _create(client)["session_id"]
        from agent.tools import get_db
        from app.main import manager

        manager.get(sid).session.state.identity.customer_id = "CUST009"
        try:
            assert _card_from_reading("CUST009") == {"no_mac_observed"}
            resp = client.post(f"/sessions/{sid}/simulate-power")
            assert resp.status_code == 200 and resp.json()["ok"] is True
            assert "no_mac_observed" not in _card_from_reading("CUST009")
        finally:
            with get_db().transaction() as cur:
                cur.execute(
                    "UPDATE ports SET observed_mac=NULL, dhcp_status=NULL "
                    "WHERE customer_id='CUST009'"
                )
            client.delete(f"/sessions/{sid}")

    def test_unknown_session_is_404(self, client):
        assert client.post("/sessions/nope/simulate-power").status_code == 404


class TestSimulateReboot:
    """DEMO reboot button (S6, 2026-08-31): the tester plays the caller's
    hands — POST is the moment the router's power lead is pulled: the port
    flaps and traffic returns. Not pressing it while claiming 'perkroviau'
    rehearses the wrong-device case."""

    def test_reboot_before_identification_is_409(self, client):
        sid = _create(client)["session_id"]
        assert client.post(f"/sessions/{sid}/simulate-reboot").status_code == 409
        client.delete(f"/sessions/{sid}")

    def test_reboot_flips_hung_to_healthy(self, client):
        import json as _json

        sid = _create(client)["session_id"]
        from app.main import manager

        manager.get(sid).session.state.identity.customer_id = "CUST112"
        from agent.tools import get_db

        try:
            assert _card_from_reading("CUST112") == {"router_hung"}
            resp = client.post(f"/sessions/{sid}/simulate-reboot")
            assert resp.status_code == 200 and resp.json()["ok"] is True
            # traffic is back and the flap was seen: the hung router is ruled out
            assert _card_from_reading("CUST112") == {"healthy_to_router"}
        finally:
            with get_db().transaction() as cur:
                cur.execute(
                    "UPDATE ports SET traffic_status='none', "
                    "last_status_change=datetime('now','-2 days') WHERE customer_id='CUST112'"
                )
            client.delete(f"/sessions/{sid}")

    def test_unknown_session_is_404(self, client):
        assert client.post("/sessions/nope/simulate-reboot").status_code == 404


class TestAdminReset:
    def test_reset_refused_during_call_then_reseeds(self, client):
        sid = _create(client)["session_id"]
        # Dropping tables under a live call would corrupt it — refused.
        assert client.post("/admin/db/reset").status_code == 409
        client.delete(f"/sessions/{sid}")
        resp = client.post("/admin/db/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reset"] is True
        assert data["customers"] >= 10  # seeded state is back


class TestTurnSummary:
    def test_cost_and_tokens_aggregated(self):
        from app.sessions import build_turn_summary

        events = [
            {"type": "node", "node": "diagnosis"},
            {"type": "tool_call", "name": "diagnose_connection"},
            {"type": "tool_result", "name": "diagnose_connection", "ok": True, "ms": 3},
            {"type": "llm", "model": "gpt-4o-mini", "input_tokens": 1000, "output_tokens": 100},
            {"type": "llm", "model": "gpt-4o-mini", "input_tokens": 2000, "output_tokens": 200},
        ]
        s = build_turn_summary(events, wall_ms=480)
        assert s["nodes"] == ["diagnosis"]
        assert s["tools"] == [{"name": "diagnose_connection", "ok": True, "ms": 3}]
        assert s["llm_calls"] == 2 and s["input_tokens"] == 3000 and s["output_tokens"] == 300
        # 3000*0.15/1M + 300*0.60/1M
        assert s["cost_usd"] == pytest.approx(0.00063, rel=1e-3)
        assert s["engine"] == "llm"

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
    from app.main import app

    with TestClient(app) as c:
        yield c


def _create(client, phone="+37060012353"):
    resp = client.post("/sessions", json={"caller_phone": phone})
    assert resp.status_code == 201
    return resp.json()


class TestLifecycle:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_create_returns_greeting(self, client):
        data = _create(client)
        assert data["session_id"]
        assert "Labas" in data["greeting"]

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
                "agent.react_agent.stream_tool_completion",
                side_effect=_fake_stream(content="Supratau, tikrinu."),
            ),
            patch(
                "agent.react_agent.get_last_call_stats",
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
        assert "kada dingo" in data["reply"]
        assert data["turn"]["engine"] == "scripted"
        assert data["turn"]["llm_calls"] == 0

    def test_sessions_are_isolated(self, client):
        a = _create(client, phone="+37060012353")["session_id"]
        b = _create(client, phone="+37060020101")["session_id"]
        assert a != b
        client.post(f"/sessions/{a}/turns", json={"text": "neveikia internetas"})
        from app.main import manager

        assert manager.get(a).session.state.problem_type == "internet_down"
        assert manager.get(b).session.state.problem_type is None


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
            assert reply is not None and "kada dingo" in reply["reply"]
            # The brain-panel feed: engine events arrived live on the socket.
            assert "user_turn" in seen
            assert "turn_summary" in seen

    def test_ws_unknown_session_rejected(self, client):
        from starlette.websockets import WebSocketDisconnect as ClientDisconnect

        with pytest.raises(ClientDisconnect):
            with client.websocket_connect("/ws/call/nope") as ws:
                ws.receive_json()


class _FakeASR:
    def transcribe(self, audio, *, language=None, sample_rate=16_000):
        return "neveikia internetas"


class _FakeTTS:
    def synthesize(self, text, *, language=None):
        return b"FAKEMP3"


class TestVoiceChannel:
    """PR2 — binary WS frames run a full voice turn (ASR/TTS faked)."""

    @pytest.fixture()
    def voice_fakes(self, monkeypatch, tmp_path):
        from app import voice

        monkeypatch.setattr(voice, "_build_asr", lambda: _FakeASR())
        monkeypatch.setattr(voice, "_build_tts", lambda: _FakeTTS())
        monkeypatch.setenv("API_RECORD_DIR", str(tmp_path))
        # Traces to tmp too: the interrupt test reads the session's jsonl, and
        # a cwd-relative "../logs" path broke on CI (pytest runs from the repo
        # root there, from chatbot_core/ locally).
        monkeypatch.setenv("TRACE_DIR", str(tmp_path))
        return tmp_path

    def test_binary_frame_runs_voice_turn(self, client, voice_fakes, monkeypatch):
        # The NON-streaming contract (VOICE_STREAM=off): one voice_turn JSON,
        # then the whole reply as one blob. The streaming default is covered by
        # test_streaming_voice_turn_chunks_then_done.
        monkeypatch.setenv("VOICE_STREAM", "off")
        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            ws.send_bytes(b"RIFF-fake-wav-utterance")
            payload = None
            audio = None
            for _ in range(60):
                msg = ws.receive()
                if msg.get("bytes"):
                    audio = msg["bytes"]
                    break  # reply audio is the last frame of the turn
                if msg.get("text"):
                    import json as _json

                    e = _json.loads(msg["text"])
                    if e.get("type") == "voice_turn":
                        payload = e
            assert payload is not None
            assert payload["transcript"] == "neveikia internetas"
            assert "kada dingo" in payload["reply"]  # scripted anamnesis
            assert payload["turn"]["engine"] == "scripted"
            assert payload["asr_ms"] >= 0 and payload["tts_ms"] >= 0
            assert audio == b"FAKEMP3"
        # The archive: caller WAV + agent reply audio landed next to the trace.
        rec = voice_fakes / sid
        assert (rec / "turn_01_user.wav").read_bytes() == b"RIFF-fake-wav-utterance"
        assert (rec / "turn_01_agent.mp3").read_bytes() == b"FAKEMP3"

    def test_partial_frame_is_a_noop_when_duplex_off(self, client, voice_fakes, monkeypatch):
        # E1 duplex: a b"PART"-prefixed frame is a rolling-transcript snapshot,
        # never a turn. With DUPLEX off (default) it is a complete no-op — the
        # socket still serves a normal text turn right after.
        monkeypatch.delenv("DUPLEX", raising=False)
        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            ws.send_bytes(b"PART" + b"RIFF-fake-wav")
            ws.send_json({"type": "turn", "text": "neveikia internetas"})
            reply = None
            for _ in range(40):
                msg = ws.receive_json()
                if msg.get("type") == "reply":
                    reply = msg
                    break
                assert msg.get("type") != "partial"  # off = nothing produced
            assert reply is not None and "kada dingo" in reply["reply"]

    def test_partial_frame_returns_rolling_transcript(self, client, voice_fakes, monkeypatch):
        monkeypatch.setenv("DUPLEX", "on")
        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            ws.send_bytes(b"PART" + b"RIFF-fake-wav")
            got = None
            for _ in range(40):
                msg = ws.receive_json()
                if msg.get("type") == "partial":
                    got = msg
                    break
            assert got is not None and got["text"] == "neveikia internetas"
            # the snapshot ran NO agent turn — the next real turn is turn #1
            from app.main import manager

            assert manager.get(sid).turn_count == 0
            assert manager.get(sid).last_partial == "neveikia internetas"

    def test_streaming_voice_turn_chunks_then_done(self, client, voice_fakes, monkeypatch):
        # Phase 5 PR1: the reply audio arrives sentence-by-sentence AS BINARY
        # FRAMES while the turn runs; the done JSON (TTFA + turn summary)
        # follows the last chunk. The scripted anamnesis reply is 2 sentences
        # -> 2 chunks with the fake TTS.
        monkeypatch.setenv("VOICE_STREAM", "on")
        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            ws.send_bytes(b"RIFF-fake-wav-utterance")
            chunks = []
            done = None
            for _ in range(80):
                msg = ws.receive()
                if msg.get("bytes"):
                    chunks.append(msg["bytes"])
                elif msg.get("text"):
                    import json as _json

                    e = _json.loads(msg["text"])
                    if e.get("type") == "voice_turn_done":
                        done = e
                        break
            assert len(chunks) >= 2  # sentence-by-sentence, not one blob
            assert all(c == b"FAKEMP3" for c in chunks)
            assert done is not None
            assert done["chunks"] == len(chunks)
            assert isinstance(done["ttfa_ms"], int)
            assert done["turn"]["engine"] == "scripted"
        # Recording: the full reply is the concatenated chunks.
        rec = voice_fakes / sid
        assert rec.joinpath("turn_01_user.wav").read_bytes() == b"RIFF-fake-wav-utterance"
        assert rec.joinpath("turn_01_agent.mp3").read_bytes() == b"FAKEMP3" * len(chunks)

    def test_interrupt_stops_remaining_chunks(self, client, voice_fakes, monkeypatch):
        # Phase 5 PR2 barge-in: an {"type":"interrupt"} arriving MID-STREAM stops
        # further chunks (the engine finishes quietly); the done payload says so.
        import time as _time

        from app import voice

        class _SlowTTS:
            def synthesize(self, text, *, language=None):
                _time.sleep(0.15)  # keep the stream alive long enough to interrupt
                return b"FAKEMP3"

        monkeypatch.setattr(voice, "_build_tts", lambda: _SlowTTS())
        monkeypatch.setenv("VOICE_STREAM", "on")
        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            ws.send_bytes(b"RIFF-fake-wav-utterance")
            chunks = 0
            done = None
            interrupted_sent = False
            for _ in range(120):
                msg = ws.receive()
                if msg.get("bytes"):
                    chunks += 1
                    if not interrupted_sent:
                        ws.send_text('{"type": "interrupt"}')  # spoke over the reply
                        interrupted_sent = True
                elif msg.get("text"):
                    import json as _json

                    e = _json.loads(msg["text"])
                    if e.get("type") == "voice_turn_done":
                        done = e
                        break
            assert done is not None
            assert done["interrupted"] is True
            assert done["chunks_sent"] < done["chunks"]  # the tail was swallowed
        # The barge-in landed on the trace (panel + archive see it). TRACE_DIR
        # points at tmp (voice_fakes) — no cwd-relative paths (broke on CI).
        import json as _json2

        trace = voice_fakes / f"{sid}.jsonl"
        events = [_json2.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
        assert any(e.get("type") == "barge_in" for e in events)

    def test_interrupt_truncates_history_to_heard_prefix(self, client, voice_fakes, monkeypatch):
        # D1 delivery ledger: the interrupt carries played=1 — only the first
        # sentence finished playing, so the engine's last assistant message
        # keeps just that prefix and the unheard tail waits for the narrator.
        import time as _time

        from app import voice

        class _SlowTTS:
            def synthesize(self, text, *, language=None):
                _time.sleep(0.15)
                return b"FAKEMP3"

        monkeypatch.setattr(voice, "_build_tts", lambda: _SlowTTS())
        monkeypatch.setenv("VOICE_STREAM", "on")
        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            ws.send_bytes(b"RIFF-fake-wav-utterance")
            done = None
            interrupted_sent = False
            for _ in range(120):
                msg = ws.receive()
                if msg.get("bytes"):
                    if not interrupted_sent:
                        ws.send_text('{"type": "interrupt", "played": 1}')
                        interrupted_sent = True
                elif msg.get("text"):
                    import json as _json

                    e = _json.loads(msg["text"])
                    if e.get("type") == "voice_turn_done":
                        done = e
                        break
            assert done is not None and done["interrupted"] is True
        from app.main import manager

        engine = manager.get(sid).session._agent
        # an unheard "?" upgrades the tail into the strong re-ask directive
        tail = engine._undelivered_tail or engine._unheard_question
        last_assistant = next(
            m for m in reversed(engine.state.messages) if m["role"] == "assistant"
        )
        # something was cut: the tail is pending and the history ends with the
        # heard-prefix marker instead of the full scripted reply
        assert tail
        assert last_assistant["content"].endswith("—")
        assert tail not in last_assistant["content"]

    def test_fram_stream_server_cuts_a_turn(self, client, voice_fakes, monkeypatch):
        # D2 duplex: the client streams FRAM frames; the SERVER's audio front
        # decides the utterance ended and runs the normal voice turn.
        import struct as _struct

        from app.audio_front import wav_bytes

        monkeypatch.setenv("DUPLEX", "on")
        monkeypatch.setenv("VOICE_STREAM", "on")

        def frame(loud):
            pcm = _struct.pack("<4096h", *([5000 if loud else 0] * 4096))
            return b"FRAM" + wav_bytes(pcm, 16_000)

        sid = _create(client)["session_id"]
        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            for _ in range(4):
                ws.send_bytes(frame(loud=True))
            for _ in range(5):  # > 900 ms of silence -> the server cuts
                ws.send_bytes(frame(loud=False))
            done = None
            saw_turn_start = False
            for _ in range(120):
                msg = ws.receive()
                if msg.get("text"):
                    import json as _json

                    e = _json.loads(msg["text"])
                    if e.get("type") == "turn_start":
                        saw_turn_start = True  # D1: the client's played reset
                    if e.get("type") == "voice_turn_done":
                        done = e
                        break
            assert done is not None
            assert saw_turn_start
            assert done["chunks"] >= 1  # the FakeASR turn produced a spoken reply
        # the assembled utterance landed in the archive like any voice turn
        rec = voice_fakes / sid
        assert rec.joinpath("turn_01_user.wav").exists()

    def test_completed_call_takes_no_more_turns(self, client, voice_fakes, monkeypatch):
        # Live 2026-08-27: after "Geros dienos!" the transport kept processing
        # garbled farewells and looped "Ar dar kuo padeti?" — a finished call
        # ignores further audio and tells the client once to hang up.
        monkeypatch.setenv("VOICE_STREAM", "on")
        sid = _create(client)["session_id"]
        from app.main import manager

        manager.get(sid).session._agent.state.is_complete = True
        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            ws.send_bytes(b"RIFF-fake-wav-utterance")
            ended = False
            got_turn = False
            for _ in range(20):
                msg = ws.receive()
                if msg.get("text"):
                    import json as _json

                    e = _json.loads(msg["text"])
                    if e.get("type") == "call_ended":
                        ended = True
                        break
                    if e.get("type") in ("voice_turn_done", "voice_turn"):
                        got_turn = True
            assert ended and not got_turn
        assert manager.get(sid).turn_count == 0  # no turn ever ran

    def test_over_frames_observe_only(self, client, voice_fakes, monkeypatch):
        # Duplex-hearing stage 1: speech spoken OVER the agent's voice becomes
        # an overlay OBSERVATION (transcript + echo verdict) — never a turn.
        import struct as _struct

        from app.audio_front import wav_bytes

        monkeypatch.setenv("DUPLEX", "on")
        sid = _create(client)["session_id"]

        def frame(loud):
            pcm = _struct.pack("<4096h", *([5000 if loud else 0] * 4096))
            return b"OVER" + wav_bytes(pcm, 16_000)

        with client.websocket_connect(f"/ws/call/{sid}") as ws:
            for _ in range(4):
                ws.send_bytes(frame(loud=True))
            for _ in range(5):
                ws.send_bytes(frame(loud=False))
            got = None
            for _ in range(60):
                msg = ws.receive()
                if msg.get("text"):
                    import json as _json

                    e = _json.loads(msg["text"])
                    if e.get("type") == "overlay":
                        got = e
                        break
            assert got is not None and got["text"] == "neveikia internetas"
            assert got["echo"] is False and "sim" in got
        from app.main import manager

        assert manager.get(sid).turn_count == 0  # observation, not a turn

    def test_greeting_audio_endpoint(self, client, voice_fakes):
        sid = _create(client)["session_id"]
        resp = client.get(f"/sessions/{sid}/greeting/audio")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/")
        assert resp.content == b"FAKEMP3"

    def test_dashboard_served(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Agento vidus" in resp.text


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

    def test_detail_has_transcript_events_audio_stats(self, archived_call, client):
        resp = client.get(f"/calls/{archived_call}")
        assert resp.status_code == 200
        d = resp.json()
        assert any("kada dingo" in (m["text"] or "") for m in d["transcript"])
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
        assert {"agent_model", "SOLVER_DRIVE", "ASR_BACKEND", "TTS_VOICE"} <= keys
        for i in items:
            assert i["value"] in i["options"] or i["key"] == "agent_model"
            assert i["scope"] in ("immediate", "new_calls")

    def test_put_applies_env_and_persists(self, client, monkeypatch):
        import json as _json
        import os

        monkeypatch.setenv("SOLVER_DRIVE", "on")
        resp = client.put("/admin/config", json={"SOLVER_DRIVE": "off"})
        assert resp.status_code == 200
        assert os.environ["SOLVER_DRIVE"] == "off"
        assert _json.loads(self.persist.read_text(encoding="utf-8"))["SOLVER_DRIVE"] == "off"
        client.put("/admin/config", json={"SOLVER_DRIVE": "on"})  # restore

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

        manager.get(sid).session.state.customer_id = "CUST009"
        resp = client.post(f"/sessions/{sid}/simulate-plug")
        assert resp.status_code == 200 and resp.json()["ok"] is True
        from agent.tools import execute_tool

        d = _json.loads(execute_tool("diagnose_connection", {"customer_id": "CUST009"}))
        assert ((d.get("verdict") or {}).get("reason")) != "no_mac_observed"
        resp = client.post(f"/sessions/{sid}/simulate-plug", params={"unplug": "true"})
        assert resp.status_code == 200
        d = _json.loads(execute_tool("diagnose_connection", {"customer_id": "CUST009"}))
        assert ((d.get("verdict") or {}).get("reason")) == "no_mac_observed"
        client.delete(f"/sessions/{sid}")

    def test_unknown_session_is_404(self, client):
        assert client.post("/sessions/nope/simulate-plug").status_code == 404


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

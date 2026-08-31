"""
Duplex-hearing 2 ŽINGSNIS: non-echo overlay words reach the engine at the
next turn — deterministic fact ingest through the importance gates + a
one-shot narrator note. Overlay may FILL facts, never steer routing.
"""

from types import SimpleNamespace


def _agent():
    from agent.react_agent import ReactAgent

    agent = ReactAgent(caller_phone="+37060012353")
    agent.state.customer_id = "CUST009"
    agent.state.problem_type = "internet_down"
    agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights"}
    return agent


class TestApplyOverlay:
    def test_pending_answer_lands_from_overlay(self, db_connection):
        agent = _agent()
        agent._evidence_last_ask_key = "lights"
        agent.apply_overlay(["ne, nedega nė viena"])
        assert agent.state.evidence.get("lights", {}).get("value") == "nedega"
        block = agent._state_facts_block() or ""
        assert "ĮSITERPĖ" in block and "nedega" in block
        assert "ĮSITERPĖ" not in (agent._state_facts_block() or "")  # one-shot

    def test_address_slots_prefill_from_overlay(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.problem_type = "internet_down"
        agent.apply_overlay(["dėl Vilniaus gatvės 29 Šiauliai"])
        p = agent.state.profile
        assert p.street.value and "Vilniaus" in p.street.value
        assert p.house.value == "29"

    def test_story_flip_still_gated(self, db_connection, monkeypatch):
        import agent.evidence as ev

        monkeypatch.setattr(
            ev, "extract_client_facts", lambda t: {"outlet_works": "neveikia"} if t else {}
        )
        agent = _agent()
        agent._evidence_last_ask_key = "lights"  # volunteered, not the asked key
        agent.apply_overlay(["rozetė neveikia"])
        assert agent.state.evidence.get("outlet_works") is None  # parked
        assert agent._fact_confirm == ("outlet_works", "neveikia")

    def test_empty_and_capped(self, db_connection):
        agent = _agent()
        agent.apply_overlay(["", "   "])
        assert agent._overlay_heard is None


class TestTransportHandOver:
    def test_turn_start_flushes_overlay_notes(self, monkeypatch):
        import threading

        from app import voice

        monkeypatch.setenv("API_RECORD_AUDIO", "0")
        monkeypatch.setenv("SPECULATION", "off")
        got: list = []

        class _P:
            prev_cancelled = False
            last_turn_aligned = True
            last_turn_sentences: list = []

            def stream_turn(self, audio, **kw):
                yield b"REAL"

        ms = SimpleNamespace(
            voice=_P(),
            cancel=threading.Event(),
            turn_count=0,
            overlay_notes=["aha, Vilniaus 29"],
            session=SimpleNamespace(
                session_id="t",
                is_complete=False,
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
                last_spoken_text=lambda: "",
                apply_overlay=lambda texts: got.append(texts),
            ),
        )
        chunks: list = []
        voice.run_voice_turn_stream(ms, b"RIFF", chunks.append)
        assert got == [["aha, Vilniaus 29"]]
        assert ms.overlay_notes == []  # flushed once

    def test_run_overlay_queues_non_echo_only(self, monkeypatch):
        from app import voice

        monkeypatch.setenv("DUPLEX", "on")

        def _ms(heard, spoken):
            return SimpleNamespace(
                voice=SimpleNamespace(transcribe_partial=lambda audio: heard),
                overlay_notes=[],
                session=SimpleNamespace(
                    tracer=SimpleNamespace(emit=lambda *a, **k: None),
                    last_spoken_text=lambda: spoken,
                ),
            )

        ms = _ms("dėl Vilniaus gatvės", "Ar dega lemputė kokia nors dabar")
        voice.run_overlay(ms, b"\x00" * 32_000)
        assert ms.overlay_notes == ["dėl Vilniaus gatvės"]
        ms2 = _ms("ar dega lemputė kokia nors", "Ar dega lemputė kokia nors dabar")
        voice.run_overlay(ms2, b"\x00" * 32_000)
        assert ms2.overlay_notes == []  # echo never queues

"""
graph_v2 — the conversation graph: entry routing, the diagnosis subgraph, the
per-stage tool scopes, and the checkpointed GraphState (SqliteSaver).
"""

from types import SimpleNamespace
from unittest.mock import patch

from agent.decide.procedure import StepOutcome
from agent.graph_v2.state import ClosingState, GraphState, IdentityState, TicketState


def _fake_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_names(schema):
    return {t["function"]["name"] for t in (schema or [])}


def _fake_stream(content=None, tool_calls=None, captured=None):
    def _gen(**kwargs):
        if captured is not None:
            captured["tools"] = kwargs.get("tools")
        if content:
            yield content
        return _fake_message(content=content, tool_calls=tool_calls)

    return _gen


def _v2_session(tmp_path, name="cp.sqlite", phone="unknown"):
    """AgentSession with an isolated sqlite checkpoint db."""
    from agent.graph_v2.checkpoint import make_checkpointer
    from agent.graph_v2.graph import build_graph
    from agent.session import AgentSession

    session = AgentSession(caller_phone=phone)
    session._graph = build_graph(make_checkpointer(tmp_path / name))
    return session


def _sync_checkpoint(session):
    """Mirror fields a test set on the engine into the checkpoint the entry router reads."""
    state = session.state
    updates = {name: getattr(state, name) for name in type(state).model_fields if name != "turn"}
    session._graph.update_state(session._graph_config, updates)


class FakeEngine:
    """Records the flow-call order so subgraph wiring is testable without LLM/DB:
    the flows the nodes call are replaced by recorders."""

    def __init__(self, monkeypatch, side_topic=False, driven=None):
        self.state = GraphState()
        self.state.identity.customer_id = "CUST-T"
        self.calls = []
        self.session_id = "fake-session"
        self.tracer = SimpleNamespace(emit=lambda *a, **k: None)
        self.runtime = _fake_runtime(self)
        recorders = {
            "agent.execute.diagnosis.ensure_diagnosed": ("diagnose", None),
            "agent.perceive.slots.prefill_slots_from_text": ("prefill", None),
            "agent.perceive.evidence.ingest_client_evidence": ("ingest", None),
            "agent.perceive.side_topic.classify_side_topic": ("classify", side_topic),
            "agent.decide.rules.diagnosis.solver_drive_turn": ("solver", driven),
            "agent.decide.procedure.advance": ("walker", StepOutcome("hold")),
            "agent.execute.diagnosis.ensure_action_done": ("action", None),
            "agent.narrator_flow.mark_step_presented": ("mark", None),
        }
        for target, (label, result) in recorders.items():
            monkeypatch.setattr(target, self._recorder(label, result))
        monkeypatch.setattr("agent.speak.node.begin_turn", lambda state, rt, user_input: None)
        monkeypatch.setattr("agent.speak.node.stream_reply", self._speak)
        monkeypatch.setattr("agent.execute.say.scripted_exit", lambda state, rt: None)

    def _recorder(self, label, result):
        def record(state, rt, *args):
            self.calls.append(label)
            return result

        return record

    def _speak(self, state, rt, owner):
        self.calls.append("narrate")
        yield "ok-"
        yield "reply"


def _fake_graph(engine):
    from agent.graph_v2.graph import build_graph
    from langgraph.checkpoint.memory import MemorySaver

    return build_graph(MemorySaver())


def _fake_runtime(engine):
    import threading

    from agent.config import AgentConfig
    from agent.runtime import AgentRuntime

    return AgentRuntime(
        session_id=engine.session_id,
        config=AgentConfig(),
        tracer=engine.tracer,
        tools=None,
        cancel=threading.Event(),
    )


def _diag_input():
    from agent.graph_v2.state import TurnScratch

    return {
        "identity": IdentityState(customer_id="CUST-T"),
        "turn": TurnScratch(user_input="neveikia internetas"),
    }


_CFG = {"configurable": {"thread_id": "t-subgraph"}}


class TestGraphCallOrder:
    """The legacy pipeline order survives perceive -> decide -> execute -> narrate."""

    def test_normal_path_keeps_legacy_call_order(self, monkeypatch):
        engine = FakeEngine(monkeypatch)
        out = _fake_graph(engine).invoke(_diag_input(), _CFG, context=_fake_runtime(engine))
        # The perceive node reads the turn first (slots, evidence, side-topic
        # signal); A-2 (2026-09-07): the guards run before the solver/walker can
        # consume a safety-question answer.
        assert engine.calls == [
            "prefill",
            "ingest",
            "classify",
            "diagnose",
            "solver",
            "walker",
            "action",
            "narrate",
            "mark",
        ]
        assert out["turn"].reply == "ok-reply"

    def test_side_topic_freezes_the_engine(self, monkeypatch):
        engine = FakeEngine(monkeypatch, side_topic=True)
        out = _fake_graph(engine).invoke(_diag_input(), _CFG, context=_fake_runtime(engine))
        # No close-inform/solver/walker/action on side chatter — only the frozen narration.
        assert engine.calls == ["prefill", "ingest", "classify", "diagnose", "narrate"]
        assert out["turn"].reply == "ok-reply"

    def test_solver_drive_skips_walker_and_narrator(self, monkeypatch):
        engine = FakeEngine(monkeypatch, driven="Atsakau pats.")
        out = _fake_graph(engine).invoke(_diag_input(), _CFG, context=_fake_runtime(engine))
        assert engine.calls == ["prefill", "ingest", "classify", "diagnose", "solver"]
        assert out["turn"].reply == "Atsakau pats."

    def test_tokens_stream_out_of_the_graph(self, monkeypatch):
        """The voice pipeline consumes stream_mode='custom' — narrator tokens must
        surface on the stream. Mirrors AgentSession.handle_turn_stream (subgraphs=True
        + unwrap)."""
        engine = FakeEngine(monkeypatch)
        chunks = [
            chunk
            for _ns, chunk in _fake_graph(engine).stream(
                _diag_input(),
                _CFG,
                context=_fake_runtime(engine),
                stream_mode="custom",
                subgraphs=True,
            )
        ]
        assert chunks == ["ok-", "reply"]


class TestSessionThroughGraph:
    def test_greeting_is_the_configured_opening(self, tmp_path):
        session = _v2_session(tmp_path)
        assert session.greeting() == session.config.greeting_message

    def test_handle_turn_returns_reply_and_syncs_engine_state(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()

        with (
            patch(
                "agent.speak.node.stream_tool_completion",
                side_effect=_fake_stream(content="Pasakykite adresą."),
            ),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            reply = session.handle_turn("neveikia internetas Vilniaus gatvėje 29")

        assert reply == "Pasakykite adresą."
        assert session.state.messages[-1]["content"] == "Pasakykite adresą."

    def test_unidentified_turn_has_no_tools(self, db_connection, tmp_path):
        """M5: the engine runs every identification lookup — the narrator only talks."""
        session = _v2_session(tmp_path)
        session.greeting()

        captured = {}
        with (
            patch(
                "agent.speak.node.stream_tool_completion",
                side_effect=_fake_stream(content="ok", captured=captured),
            ),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            session.handle_turn("neveikia internetas Vilniaus gatvėje 29")

        assert _tool_names(captured["tools"]) == set()


class TestRouting:
    """The deterministic router scopes the toolset per stage (structural gate)."""

    def _run_turn_capture_tools(self, session, text):
        _sync_checkpoint(session)
        captured = {}
        with (
            patch(
                "agent.speak.node.stream_tool_completion",
                side_effect=_fake_stream(content="ok", captured=captured),
            ),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            session.handle_turn(text)
        return _tool_names(captured["tools"])

    def test_no_tools_while_a_procedure_is_active(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()
        session.state.identity.customer_id = "CUST105"  # foreign_mac -> strategy activates

        # The engine owns diagnosis, the action and the closing, so the speaker just
        # talks. This is the fix for the observed catastrophe where a step left lookup
        # tools on the table and the model spammed check_outages to the call limit.
        assert self._run_turn_capture_tools(session, "taip") == set()

    def test_ticket_dialogue_routes_to_ticket_node_with_no_tools(self, db_connection, tmp_path):
        from agent.execute.ticket import begin_ticket_dialogue

        # Mid-dialogue turns run in the dedicated ticket_registration node: the
        # walker/solver stay frozen and the LLM (off-script question only) has NO
        # tools. A scripted turn would skip the LLM, so ask a question.
        session = _v2_session(tmp_path, phone="+37060012353")
        session.greeting()
        session.state.identity.customer_id = "CUST009"
        session.state.intake.problem_type = "internet_down"
        engine = SimpleNamespace(state=session.state, runtime=session._runtime)
        engine.state.diagnosis.hypothesis = {
            "cause": "no_mac_observed",
            "status": "testing",
            "because": ["linijoje nematomas įrenginys"],
        }
        engine.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "escalate",
            "asked": True,
        }
        begin_ticket_dialogue(engine.state, engine.runtime, None)

        names = self._run_turn_capture_tools(session, "O kokiu numeriu jūs skambinsite?")

        assert names == set()  # TICKET_TOOLS is empty — structurally no mutations
        assert engine.state.ticket.stage == "phone"  # the stage held; answer comes next turn

    def test_closed_session_routes_to_closing_with_no_tools(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()
        session.state.identity.customer_id = "CUST105"
        session.state.closing.case_closed = True  # END stage
        session.state.closing.closed_reason = "resolved"
        _sync_checkpoint(session)

        captured = {}
        with (
            patch(
                "agent.speak.node.stream_tool_completion",
                side_effect=_fake_stream(content="Geros dienos!", captured=captured),
            ),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            reply = session.handle_turn("O kiek tai kainuos?")  # a real question -> LLM

        assert reply == "Geros dienos!"
        assert captured["tools"] is None  # the speaker never gets tools


class TestCheckpointedState:
    def test_checkpoint_carries_full_graph_state(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()

        with (
            patch(
                "agent.speak.node.stream_tool_completion",
                side_effect=_fake_stream(content="Koks adresas?"),
            ),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            reply = session.handle_turn("neveikia internetas")

        values = session._graph.get_state(session._graph_config).values
        # The whole conversation state is in the checkpoint, not just the reply
        # (the reply may be engine-scripted, so compare against what was returned).
        assert values["turn"].reply == reply
        assert values["identity"].caller_phone == "unknown"
        assert values["messages"][-1]["content"] == reply
        assert values["dialog"].turn_count == session.state.dialog.turn_count

    def test_time_travel_history_across_turns(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()

        with (
            patch(
                "agent.speak.node.stream_tool_completion",
                side_effect=_fake_stream(content="Koks adresas?"),
            ),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            reply = session.handle_turn("neveikia internetas")

        history = list(session._graph.get_state_history(session._graph_config))
        # At least one checkpoint per turn (greeting + user turn), newest first.
        assert len(history) >= 2
        newest = history[0].values
        assert newest["turn"].reply == reply

    def test_state_survives_a_new_graph_over_same_db(self, tmp_path):
        """SqliteSaver persistence: a rebuilt graph (same thread_id, same db file)
        sees the previous state — the seam for state between calls."""
        from agent.graph_v2.checkpoint import make_checkpointer
        from agent.graph_v2.graph import build_graph

        session = _v2_session(tmp_path, "persist.sqlite")
        session.greeting()
        first = session._graph.get_state(session._graph_config).values
        assert first["turn"].reply

        rebuilt = build_graph(make_checkpointer(tmp_path / "persist.sqlite"))
        restored = rebuilt.get_state(session._graph_config).values
        assert restored["turn"].reply == first["turn"].reply
        assert restored["identity"].caller_phone == "unknown"


class TestBetweenTurnWrites:
    """Writes that happen between turns reach the checkpoint (no engine memory)."""

    def test_delivery_truncation_survives_into_the_next_turn(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()
        session.apply_delivery(["Labas!", "Kuo galiu padėti?"], 1)

        values = session._graph.get_state(session._graph_config).values
        assert values["messages"][-1]["content"] == "Labas! —"
        assert values["voice"].unheard_question == "Kuo galiu padėti?"  # the ask never landed

        seen = {}
        from agent.speak import node as speak_node

        original = speak_node.build_messages

        def spy(state, rt, *args, **kwargs):
            seen["history"] = [m.get("content") for m in state.messages]
            return original(state, rt, *args, **kwargs)

        with (
            patch.object(speak_node, "build_messages", side_effect=spy),
            patch(
                "agent.speak.node.stream_tool_completion",
                side_effect=_fake_stream(content="Suprantu."),
            ),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            session.handle_turn("O kas jūs tokie?")
        assert "Labas! —" in seen["history"]

    def test_background_results_ride_the_next_turn_input(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()
        with session._inbox_lock:
            session._inbox["analyst_signals"] = [{"type": "frustration", "quote": "kiek"}]
            session._inbox["bg_diagnosis"] = '{"success": true}'

        turn_input = session._graph_input("labas")
        assert turn_input["voice"].analyst_signals == [{"type": "frustration", "quote": "kiek"}]
        assert turn_input["turn"].bg_diagnosis == '{"success": true}'
        assert session._inbox == {}  # consumed once

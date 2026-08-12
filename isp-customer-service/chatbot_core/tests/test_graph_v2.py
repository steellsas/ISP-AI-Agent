"""
graph_v2 — R2 thin-wrapper parity + R1 checkpointer tests
(docs/ROADMAP_REFACTORING.md §3).

The v2 graph must behave exactly like the legacy graph (same replies, same
structural tool gates) while adding what v1 never had: a fully-synced typed
GraphState in every checkpoint and time-travel history via SqliteSaver.
"""

from types import SimpleNamespace
from unittest.mock import patch

from agent.graph_v2.router import route_entry
from agent.graph_v2.state import GraphState


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


def _v2_session(tmp_path, name="cp.sqlite"):
    """AgentSession on the v2 engine with an isolated sqlite checkpoint db."""
    from agent.graph_v2.checkpoint import make_checkpointer
    from agent.graph_v2.graph import build_graph
    from agent.session import AgentSession

    session = AgentSession(caller_phone="unknown", engine="legacy")
    session._engine_mode = "v2"
    session._use_graph = True
    session._graph = build_graph(session._agent, make_checkpointer(tmp_path / name))
    return session


class TestRouteEntryPure:
    def test_defaults_route_to_identification(self):
        assert route_entry(GraphState()) == "address_validation"

    def test_identified_routes_to_diagnosis(self):
        assert route_entry(GraphState(customer_id="CUST-1")) == "diagnosis"

    def test_ticket_stage_wins_over_identity(self):
        state = GraphState(customer_id="CUST-1", ticket_stage="phone")
        assert route_entry(state) == "ticket_registration"

    def test_case_closed_wins_over_everything(self):
        state = GraphState(customer_id="CUST-1", ticket_stage="phone", case_closed=True)
        assert route_entry(state) == "closing"


class TestRuntimeConfigSwitch:
    def test_agent_engine_knob_reaches_new_sessions(self, tmp_path, monkeypatch):
        """The dashboard knob (PUT /admin/config AGENT_ENGINE=v2) must flip the
        engine for the NEXT session."""
        from agent.session import AgentSession
        from app import runtime_config

        monkeypatch.setenv("API_CONFIG_FILE", str(tmp_path / "cfg.json"))
        monkeypatch.delenv("AGENT_ENGINE", raising=False)

        runtime_config.apply({"AGENT_ENGINE": "v2"})
        try:
            session = AgentSession(caller_phone="unknown")
            assert session._engine_mode == "v2"
            assert session.greeting()  # the v2 graph actually runs
        finally:
            monkeypatch.delenv("AGENT_ENGINE", raising=False)


class TestParityWithLegacy:
    def test_greeting_matches_legacy_and_graph(self, tmp_path):
        from agent.session import AgentSession

        v2 = _v2_session(tmp_path)
        assert v2.greeting() == AgentSession(caller_phone="unknown", engine="legacy").greeting()

    def test_handle_turn_returns_reply_and_syncs_engine_state(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()

        with (
            patch(
                "agent.react_agent.stream_tool_completion",
                side_effect=_fake_stream(content="Pasakykite adresą."),
            ),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            reply = session.handle_turn("neveikia internetas Vilniaus gatvėje 29")

        assert reply == "Pasakykite adresą."
        assert session.state.messages[-1]["content"] == "Pasakykite adresą."

    def test_unidentified_turn_is_lookup_only(self, db_connection, tmp_path):
        from agent.graph import LOOKUP_TOOLS

        session = _v2_session(tmp_path)
        session.greeting()

        captured = {}
        with (
            patch(
                "agent.react_agent.stream_tool_completion",
                side_effect=_fake_stream(content="ok", captured=captured),
            ),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            session.handle_turn("neveikia internetas Vilniaus gatvėje 29")

        names = _tool_names(captured["tools"])
        assert names <= set(LOOKUP_TOOLS)
        assert "diagnose_connection" not in names
        assert "create_ticket" not in names


class TestCheckpointedState:
    def test_checkpoint_carries_full_graph_state(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()

        with (
            patch(
                "agent.react_agent.stream_tool_completion",
                side_effect=_fake_stream(content="Koks adresas?"),
            ),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            reply = session.handle_turn("neveikia internetas")

        values = session._graph.get_state(session._graph_config).values
        # The whole conversation state is in the checkpoint, not just the reply
        # (the reply may be engine-scripted, so compare against what was returned).
        assert values["turn"].reply == reply
        assert values["caller_phone"] == "unknown"
        assert values["messages"][-1]["content"] == reply
        assert values["turn_count"] == session.state.turn_count

    def test_time_travel_history_across_turns(self, db_connection, tmp_path):
        session = _v2_session(tmp_path)
        session.greeting()

        with (
            patch(
                "agent.react_agent.stream_tool_completion",
                side_effect=_fake_stream(content="Koks adresas?"),
            ),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
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

        rebuilt = build_graph(session._agent, make_checkpointer(tmp_path / "persist.sqlite"))
        restored = rebuilt.get_state(session._graph_config).values
        assert restored["turn"].reply == first["turn"].reply
        assert restored["caller_phone"] == "unknown"

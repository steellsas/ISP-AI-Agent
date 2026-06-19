"""
Tests for the LangGraph orchestration plumbing (agent/graph.py, Phase 3.5 step 3.1).

3.1 is behaviour-preserving: the one-node graph must produce exactly what the
legacy ReactAgent loop produced. These prove the AgentSession seam works through
the graph (greeting + a mocked turn) and that the legacy switch still bypasses it.

Run: pytest tests/test_graph.py -v
"""

from types import SimpleNamespace
from unittest.mock import patch


def _fake_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_names(schema):
    return {t["function"]["name"] for t in (schema or [])}


class TestGreetingParity:
    def test_graph_greeting_matches_legacy(self):
        from agent.session import AgentSession

        graph = AgentSession(caller_phone="unknown", engine="graph")
        legacy = AgentSession(caller_phone="unknown", engine="legacy")

        assert graph.greeting() == legacy.greeting()
        assert graph._use_graph is True
        assert legacy._use_graph is False

    def test_default_engine_is_graph(self, monkeypatch):
        monkeypatch.delenv("AGENT_ENGINE", raising=False)
        from agent.session import AgentSession

        assert AgentSession(caller_phone="unknown")._use_graph is True

    def test_env_can_select_legacy(self, monkeypatch):
        monkeypatch.setenv("AGENT_ENGINE", "legacy")
        from agent.session import AgentSession

        assert AgentSession(caller_phone="unknown")._use_graph is False


class TestTurnThroughGraph:
    def test_handle_turn_returns_reply_via_graph(self, db_connection):
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown", engine="graph")
        session.greeting()  # establish the checkpoint / first turn

        msg = _fake_message(content="Pasakykite adresą.")
        with (
            patch("agent.react_agent.llm_tool_completion", return_value=msg),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            reply = session.handle_turn("neveikia internetas")

        assert reply == "Pasakykite adresą."
        # State still lives in (and is shared with) the underlying engine.
        assert session.state.messages[-1]["content"] == "Pasakykite adresą."

    def test_graph_and_legacy_same_turn_reply(self, db_connection):
        from agent.session import AgentSession

        msg = _fake_message(content="Tas pats atsakymas.")
        replies = {}
        for mode in ("graph", "legacy"):
            session = AgentSession(caller_phone="unknown", engine=mode)
            session.greeting()
            with (
                patch("agent.react_agent.llm_tool_completion", return_value=msg),
                patch("agent.react_agent.get_last_call_stats", return_value={}),
            ):
                replies[mode] = session.handle_turn("labas")

        assert replies["graph"] == replies["legacy"] == "Tas pats atsakymas."


class TestRouting:
    """The deterministic router scopes the toolset per stage (structural gate)."""

    def _run_turn_capture_tools(self, session, text):
        captured = {}

        def fake_llm(**kwargs):
            captured["tools"] = kwargs.get("tools")
            return _fake_message(content="ok")

        with (
            patch("agent.react_agent.llm_tool_completion", side_effect=fake_llm),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            session.handle_turn(text)
        return _tool_names(captured["tools"])

    def test_unidentified_turn_is_lookup_only(self, db_connection):
        from agent.graph import LOOKUP_TOOLS
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown", engine="graph")
        session.greeting()  # customer_id stays None

        names = self._run_turn_capture_tools(session, "neveikia internetas")

        assert names <= set(LOOKUP_TOOLS)
        # The structural gate: diagnostics simply aren't on the table here.
        assert "diagnose_connection" not in names
        assert "create_ticket" not in names

    def test_identified_turn_has_full_toolset(self, db_connection):
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown", engine="graph")
        session.greeting()
        session.state.customer_id = "CUST105"  # simulate an identified caller

        names = self._run_turn_capture_tools(session, "taip")

        assert "diagnose_connection" in names
        assert "resolve_address" in names  # diagnosis keeps lookup too (re-resolve)

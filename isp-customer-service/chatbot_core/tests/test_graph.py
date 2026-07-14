"""
Tests for the LangGraph orchestration plumbing (agent/graph.py, Phase 3.5 step 3.1).

3.1 is behaviour-preserving: the one-node graph must produce exactly what the
legacy ReactAgent loop produced. These prove the AgentSession seam works through
the graph (greeting + a mocked turn) and that the legacy switch still bypasses it.

Run: pytest tests/test_graph.py -v
"""

import json
from types import SimpleNamespace
from unittest.mock import patch


def _fake_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_names(schema):
    return {t["function"]["name"] for t in (schema or [])}


def _fake_stream(content=None, tool_calls=None, captured=None):
    """A fake stream_tool_completion: yields the content token, returns the message
    (so `yield from` both streams and captures the structured result)."""

    def _gen(**kwargs):
        if captured is not None:
            captured["tools"] = kwargs.get("tools")
        if content:
            yield content
        return _fake_message(content=content, tool_calls=tool_calls)

    return _gen


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

        with (
            patch(
                "agent.react_agent.stream_tool_completion",
                side_effect=_fake_stream(content="Pasakykite adresą."),
            ),
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
                patch("agent.react_agent.llm_tool_completion", return_value=msg),  # legacy
                patch(
                    "agent.react_agent.stream_tool_completion",
                    side_effect=_fake_stream(content="Tas pats atsakymas."),
                ),  # graph
                patch("agent.react_agent.get_last_call_stats", return_value={}),
            ):
                replies[mode] = session.handle_turn("labas")

        assert replies["graph"] == replies["legacy"] == "Tas pats atsakymas."


class TestRouting:
    """The deterministic router scopes the toolset per stage (structural gate)."""

    def _run_turn_capture_tools(self, session, text):
        captured = {}
        with (
            patch(
                "agent.react_agent.stream_tool_completion",
                side_effect=_fake_stream(content="ok", captured=captured),
            ),
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
        session.state.customer_id = "CUST001"  # identified, healthy -> no strategy

        names = self._run_turn_capture_tools(session, "taip")

        # Healthy line -> no resolution strategy -> the diagnosis node keeps the
        # full toolset (diagnose available; lookup kept for a re-resolve).
        assert "diagnose_connection" in names
        assert "resolve_address" in names

    def test_diagnose_withheld_while_strategy_active(self, db_connection):
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown", engine="graph")
        session.greeting()
        session.state.customer_id = "CUST105"  # foreign_mac -> strategy activates

        # ensure_diagnosed runs on entry -> strategy active at the CONFIRM step.
        # A CONFIRM step exposes NO tools at all: the engine owns diagnosis, the
        # action and closing, so the model just talks. This is the fix for the
        # observed catastrophe where an empty step still left lookup tools on the
        # table and the model spammed check_outages to the call limit.
        names = self._run_turn_capture_tools(session, "taip")
        assert names == set()
        assert "diagnose_connection" not in names
        assert "update_mac" not in names  # bind only exposed after confirm (bind_mac)
        assert "check_outages" not in names  # the looped tool in the failing trace

    def test_closed_session_routes_to_closing_with_no_tools(self, db_connection):
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown", engine="graph")
        session.greeting()
        session.state.customer_id = "CUST105"
        session.state.case_closed = True  # END stage
        session.state.closed_reason = "resolved"

        captured = {}
        with (
            patch(
                "agent.react_agent.stream_tool_completion",
                side_effect=_fake_stream(content="Geros dienos!", captured=captured),
            ),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            reply = session.handle_turn("ačiū")

        assert reply == "Geros dienos!"
        assert captured["tools"] == []  # closing stage is structurally tools-less


class TestEngineDrivenAction:
    """The ACTION step (bind_mac) is run by the engine, not the model — so there is
    no single-tool loop and the LLM only phrases a verified outcome. After binding we
    ASK the caller and re-read telemetry before deciding.

    These stub execute_tool + _fresh_diagnose_reason so they neither mutate the
    session-shared DB (which would leak into other tests) nor depend on test order.
    The real bind→telemetry flip is covered in test_port_actions / test_verdict."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="unknown")

    def _at_bind(self, agent):
        agent.state.customer_id = "CUST105"
        agent.state.resolution = {"verdict": "foreign_mac", "step": "bind_mac", "asked": False}

    def _at_restored(self, agent):
        agent.state.customer_id = "CUST105"
        agent.state.resolution = {
            "verdict": "foreign_mac",
            "step": "confirm_restored",
            "asked": True,
        }

    def _stub_tools(self, monkeypatch, telemetry):
        import agent.react_agent as ra

        monkeypatch.setattr(
            ra, "execute_tool", lambda name, args: json.dumps({"success": True, "new_mac": "X"})
        )
        monkeypatch.setattr(ra.ReactAgent, "_fresh_diagnose_reason", lambda self: telemetry)

    def test_bind_announces_then_walks_to_confirm(self, monkeypatch):
        agent = self._agent()
        self._at_bind(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        # The engine binds + re-reads telemetry, but does NOT close or jump ahead —
        # it STAYS on bind_mac to announce (model B). Telemetry is recorded.
        assert agent.ensure_action_done() is True
        assert agent.state.case_closed is False
        assert agent.state.resolution["step"] == "bind_mac"
        assert agent.state.resolution["telemetry_fixed"] is True
        assert agent.state.resolution["action_done"] is True
        # Once the announce is presented, the caller's next reply advances to verify.
        agent._mark_step_presented()
        agent._advance_resolution("laukiu")
        assert agent.state.resolution["step"] == "confirm_restored"

    def test_bind_runs_once(self, monkeypatch):
        agent = self._agent()
        self._at_bind(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        assert agent.ensure_action_done() is True
        assert agent.ensure_action_done() is False  # action_done guard — no re-bind

    def test_restored_yes_resolves(self, monkeypatch):
        agent = self._agent()
        self._at_restored(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        agent._advance_resolution("taip, veikia")
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "resolved"

    def test_restored_no_but_provider_ok_pivots_client_side(self, monkeypatch):
        agent = self._agent()
        self._at_restored(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")  # provider OK
        agent._advance_resolution("ne, vis dar neveikia")
        # Provider OK but caller has no internet -> in-home fault, not escalate.
        assert agent.state.case_closed is False
        assert agent.state.resolution["step"] == "client_side"

    def test_restored_no_and_line_still_down_waits_then_escalates(self, monkeypatch):
        agent = self._agent()
        self._at_restored(agent)
        self._stub_tools(monkeypatch, telemetry="foreign_mac")  # line not restored yet
        agent._advance_resolution("ne")  # 1st denial -> wait (may take a few minutes)
        assert agent.state.resolution["step"] == "confirm_restored"
        agent.state.resolution["asked"] = True
        agent._advance_resolution("vis dar ne")  # 2nd denial -> escalate
        assert agent.state.resolution["step"] == "escalate"

    def test_ensure_action_noop_on_confirm_step(self, monkeypatch):
        agent = self._agent()
        self._at_restored(agent)  # a CONFIRM step, not ACTION
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        assert agent.ensure_action_done() is False  # nothing to run
        assert agent.state.case_closed is False

    def test_instruct_steps_walk_one_per_turn(self):
        # "nieko nekeičiau" -> the cable INSTRUCT steps are walked ONE per reply:
        # each advances only after its instruction was presented last turn.
        agent = self._agent()
        agent.state.customer_id = "CUST105"
        agent.state.resolution = {"verdict": "foreign_mac", "step": "cable_check", "asked": False}

        # Instruction not presented yet -> a reply does NOT skip ahead.
        agent._advance_resolution("gerai")
        assert agent.state.resolution["step"] == "cable_check"
        # Present it, then the next reply advances to the reconnect instruction.
        agent._mark_step_presented()
        agent._advance_resolution("geltoname")
        assert agent.state.resolution["step"] == "cable_reconnect"
        # And one more reply (after presenting) reaches the bind action.
        agent._mark_step_presented()
        agent._advance_resolution("padariau")
        assert agent.state.resolution["step"] == "bind_mac"


class TestCaseStateTransitions:
    """_update_state_from_observation drives the END-state flags."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="unknown")

    def test_close_case_observation_sets_closed(self):
        import json

        agent = self._agent()
        agent._update_state_from_observation(
            "close_case",
            json.dumps({"success": True, "case_closed": True, "reason": "resolved"}),
        )
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "resolved"

    def test_active_outage_sets_reported_not_closed(self):
        import json

        agent = self._agent()
        agent._update_state_from_observation(
            "check_outages",
            json.dumps(
                {"success": True, "affected": True, "active_outages": [{"street": "Dainų g."}]}
            ),
        )
        assert agent.state.outage_reported is True
        assert agent.state.case_closed is False  # an outage does NOT close the case

    def test_no_outage_leaves_reported_false(self):
        import json

        agent = self._agent()
        agent._update_state_from_observation(
            "check_outages",
            json.dumps({"success": True, "affected": False, "active_outages": []}),
        )
        assert agent.state.outage_reported is False

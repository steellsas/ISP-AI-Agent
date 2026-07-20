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
        session.state.customer_id = "CUST104"  # link_down_local -> no strategy registered

        names = self._run_turn_capture_tools(session, "taip")

        # A verdict with no strategy -> the diagnosis node keeps the full toolset
        # (diagnose available; lookup kept for a re-resolve).
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

    def test_bind_tool_withheld_after_engine_ran(self, monkeypatch):
        # Once the engine has bound (action_done), update_mac must NOT be exposed to
        # the model, or the single-tool step gets re-called to the limit (observed:
        # update_mac x6 -> 'negaliu apdoroti'). The model only announces on this turn.
        agent = self._agent()
        self._at_bind(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        agent.ensure_action_done()  # engine binds; stays on bind_mac to announce
        names = {t["function"]["name"] for t in agent._scoped_tools_schema()}
        assert "update_mac" not in names

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


class TestIdentifyThenDiagnoseSameTurn:
    """resolve_address identifies -> the engine diagnoses in the SAME turn, so one
    reply confirms the address AND delivers the finding. Without this the
    identification turn has nothing to say and the model improvises ("nėra žinomų
    gedimų", "kokie įrenginiai prijungti?") — or the caller goes quiet and it stalls."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="unknown")

    def test_resolve_triggers_diagnosis_and_carries_the_finding(self, db_connection):
        from agent.tools import execute_tool

        agent = self._agent()
        obs = execute_tool(
            "resolve_address",
            {
                "city": "Šiauliai",
                "street": "Tilžės g.",
                "house_number": "60",
                "apartment_number": "3",
            },
        )
        agent.state.customer_id = "CUST101"  # committed by resolve_address
        out = json.loads(agent._augment_tool_result("resolve_address", obs))

        # The verdict is now in state AND spelled out for the model to voice.
        assert agent.state.diagnosis["network"]["reason"] == "billing_suspended"
        assert "DIAGNOZĖ" in out["message"]
        assert "gedimų nėra" in out["message"]  # explicit: do not invent the outage line

    def test_failed_resolve_does_not_diagnose(self, db_connection):
        from agent.tools import execute_tool

        agent = self._agent()
        obs = execute_tool("resolve_address", {"street": "Tilžės g."})  # no house -> no hit
        out = agent._augment_tool_result("resolve_address", obs)
        assert agent.state.diagnosis == {}
        assert "DIAGNOZĖ" not in out


class TestHypothesisObject:
    """The verdict tree decides; the hypothesis mirrors it so the agent can narrate the
    arc — including CONFIRMATION, which we could not say before (only rejection was
    tracked)."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="unknown")

    def _diagnose(self, agent, reason):
        agent._update_state_from_observation(
            "diagnose_connection",
            json.dumps({"success": True, "verdict": {"reason": reason, "side": "x", "group": "B"}}),
        )

    def test_verdict_opens_a_belief_with_its_reason(self):
        agent = self._agent()
        agent.state.customer_id = "CUST009"
        self._diagnose(agent, "no_mac_observed")

        h = agent.state.hypothesis
        assert h["cause"] == "no_mac_observed"
        assert h["status"] == "testing"
        assert h["because"]  # seeded with what the telemetry showed

    def test_a_working_fix_confirms_it(self):
        agent = self._agent()
        agent.state.customer_id = "CUST009"
        self._diagnose(agent, "no_mac_observed")
        agent._route_to(agent.state.resolution, "resolve")

        assert agent.state.hypothesis["status"] == "confirmed"
        assert "PASITVIRTINO" in (agent._state_facts_block() or "")

    def test_rejected_causes_are_remembered_and_not_re_offered(self, monkeypatch):
        import agent.react_agent as ra

        agent = self._agent()
        agent.state.customer_id = "CUST105"
        agent.state.hypothesis = {
            "cause": "foreign_mac",
            "because": ["linijoje kitas įrenginys"],
            "status": "testing",
            "settled_by": None,
        }
        agent.state.resolution = {
            "verdict": "foreign_mac",
            "step": "confirm_restored",
            "asked": True,
            "restored_denials": 1,
        }
        monkeypatch.setattr(ra.ReactAgent, "_fresh_diagnose_reason", lambda self: "foreign_mac")
        monkeypatch.setattr(
            ra,
            "execute_tool",
            lambda n, a: json.dumps(
                {
                    "success": True,
                    "verdict": {"reason": "healthy_to_router", "side": "x", "group": "B7"},
                }
            ),
        )
        agent._advance_resolution("vis dar neveikia")

        assert [x["cause"] for x in agent.state.rejected_hypotheses] == ["foreign_mac"]
        assert agent.state.hypothesis["cause"] == "healthy_to_router"  # a new belief
        assert "JAU ATMESTA" in (agent._state_facts_block() or "")


class TestTurnHolding:
    """Only a real answer or a completed action advances the walker. Everything else
    holds it — this is what stopped the agent running ahead of the caller."""

    def _at_step(self, monkeypatch, step_id, reason="no_mac_observed"):
        import agent.react_agent as ra

        agent = ra.ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {
            "verdict": "no_mac_observed",
            "step": step_id,
            "asked": True,
        }
        monkeypatch.setattr(ra.ReactAgent, "_fresh_diagnose_reason", lambda self: reason)
        return agent

    def test_in_progress_waits_instead_of_checking(self, monkeypatch):
        # Observed: "atsinešiu kompiuterį" advanced the step, so the engine read the
        # line before anything was plugged in and concluded the bridge had failed.
        agent = self._at_step(monkeypatch, "dr_plug_pc")
        agent._advance_resolution("Gerai, atsinešiu kompiuterį, pajungsiu.")
        assert agent.state.resolution["step"] == "dr_plug_pc"  # held
        assert agent.state.awaiting == "client_action"

    def test_done_advances(self, monkeypatch):
        agent = self._at_step(monkeypatch, "dr_plug_pc")
        agent._advance_resolution("įkišau")
        assert agent.state.resolution["step"] != "dr_plug_pc"
        assert agent.state.awaiting is None

    def test_question_and_confusion_hold(self, monkeypatch):
        for reply in ("o kiek tai kainuos?", "nesuprantu, kas tas kabelis"):
            agent = self._at_step(monkeypatch, "dr_offer_bridge")
            agent._advance_resolution(reply)
            assert agent.state.resolution["step"] == "dr_offer_bridge"

    def test_repeated_confusion_breaks_the_step_down(self, monkeypatch):
        agent = self._at_step(monkeypatch, "dr_lights")
        agent._advance_resolution("nesuprantu ko norit")
        assert agent.state.step_confusions == 1
        assert "NESUPRATO" in (agent._state_facts_block() or "")
        agent._advance_resolution("vis tiek nesuprantu")
        assert agent.state.step_confusions == 2
        assert "MAŽIAUSIĄ" in (agent._state_facts_block() or "")  # finest breakdown
        # a real answer clears it and moves on
        agent._advance_resolution("nedega")
        assert agent.state.step_confusions == 0

    def test_waiting_turns_accumulate_for_a_check_in(self, monkeypatch):
        agent = self._at_step(monkeypatch, "dr_plug_pc")
        for _ in range(3):
            agent._advance_resolution("tuoj, ieškau")
        assert agent.state.awaiting_turns == 3
        assert "ILGAI LAUKIAM" in (agent._state_facts_block() or "")


class TestBridgeSeesDevice:
    """The bridge binds only once telemetry SEES the device the caller plugged in —
    binding blindly when the cable is in the wrong socket fails confusingly."""

    def _at_plug(self, monkeypatch, reason):
        import agent.react_agent as ra

        agent = ra.ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {
            "verdict": "no_mac_observed",
            "step": "dr_plug_pc",
            "asked": True,
        }
        monkeypatch.setattr(ra.ReactAgent, "_fresh_diagnose_reason", lambda self: reason)
        return agent

    def test_device_seen_goes_to_bind(self, monkeypatch):
        agent = self._at_plug(monkeypatch, "foreign_mac")  # anything but no_mac_observed
        agent._advance_resolution("įkišiau")
        assert agent.state.resolution["step"] == "dr_bind"
        assert agent.state.resolution["device_seen"] is True

    def test_not_seen_walks_back_to_the_cable(self, monkeypatch):
        agent = self._at_plug(monkeypatch, "no_mac_observed")  # still nothing on the line
        agent._advance_resolution("įkišiau")
        assert agent.state.resolution["step"] == "dr_pick_cable"  # wrong cable — retry
        assert agent.state.resolution["device_seen"] is False

    def test_second_failure_escalates(self, monkeypatch):
        agent = self._at_plug(monkeypatch, "no_mac_observed")
        agent.state.resolution["plug_retries"] = 1  # already tried once
        agent._advance_resolution("įkišiau")
        assert agent.state.resolution["step"] == "escalate"


class TestHypothesisRejection:
    """A fix that does not restore the line rejects THAT hypothesis and looks for the
    next one — the agent has a Plan B instead of registering at the first failure."""

    def _at_restored(self, monkeypatch, telemetry_after):
        import agent.react_agent as ra

        agent = ra.ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST105"
        agent.state.resolution = {
            "verdict": "foreign_mac",
            "step": "confirm_restored",
            "asked": True,
            "restored_denials": 1,  # one denial already: the next one decides
        }
        monkeypatch.setattr(ra.ReactAgent, "_fresh_diagnose_reason", lambda self: "foreign_mac")
        monkeypatch.setattr(
            ra,
            "execute_tool",
            lambda n, args: json.dumps(
                {"success": True, "verdict": {"reason": telemetry_after, "side": "x", "group": "B"}}
            ),
        )
        return agent

    def test_new_verdict_switches_strategy_and_flags_the_rethink(self, monkeypatch):
        agent = self._at_restored(monkeypatch, telemetry_after="healthy_to_router")
        agent._advance_resolution("vis dar neveikia")

        assert agent.state.failed_hypotheses == ["foreign_mac"]
        assert agent.state.resolution["verdict"] == "healthy_to_router"  # Plan B
        assert agent.state.resolution["step"] == "cs_scope"
        assert agent.state.pivoted_from == "foreign_mac"  # narrate it once

    def test_same_verdict_has_no_plan_b_so_it_escalates(self, monkeypatch):
        agent = self._at_restored(monkeypatch, telemetry_after="foreign_mac")
        agent._advance_resolution("vis dar neveikia")

        assert agent.state.failed_hypotheses == ["foreign_mac"]
        assert agent.state.resolution["step"] == "escalate"
        assert agent.state.pivoted_from is None

    def test_rethink_is_voiced_once_then_cleared(self, monkeypatch):
        agent = self._at_restored(monkeypatch, telemetry_after="healthy_to_router")
        agent._advance_resolution("vis dar neveikia")

        facts = agent._state_facts_block() or ""
        assert "PERSIGALVOJIMAS" in facts
        agent._mark_step_presented()  # the reply carried it
        assert agent.state.pivoted_from is None
        assert "PERSIGALVOJIMAS" not in (agent._state_facts_block() or "")


class TestClosing:
    """The call ends (is_complete) on a farewell / 'no more', or a 2nd closing turn —
    so the agent does not loop goodbyes."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="unknown")

    def test_farewell_ends_the_call(self):
        agent = self._agent()
        agent.state.case_closed = True
        agent._maybe_finish("ne, ačiū")
        assert agent.state.is_complete is True

    def test_question_keeps_it_open_then_caps(self):
        agent = self._agent()
        agent.state.case_closed = True
        agent._maybe_finish("o kiek tai kainuos?")  # a real follow-up
        assert agent.state.is_complete is False
        agent._maybe_finish("gerai, supratau")  # 2nd closing turn -> cap
        assert agent.state.is_complete is True

    def test_noop_when_not_closed(self):
        agent = self._agent()
        agent._maybe_finish("viso gero")  # case not closed -> ignore
        assert agent.state.is_complete is False

    def test_goodbye_reply_ends_call_any_path(self):
        # Catch-all: the agent's own farewell ends the call even without case_closed
        # (e.g. the stuck backstop's "užregistruosiu… geros dienos" that used to loop).
        agent = self._agent()
        agent._maybe_end_on_goodbye(
            "Užregistruosiu problemą, specialistas susisieks. Geros dienos!"
        )
        assert agent.state.is_complete is True

    def test_midconversation_reply_does_not_end(self):
        agent = self._agent()
        agent._maybe_end_on_goodbye("Pasakykite adresą, kuriuo neveikia internetas.")
        assert agent.state.is_complete is False


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

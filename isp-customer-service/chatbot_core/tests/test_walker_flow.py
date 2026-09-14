"""
Tests for the resolution walker and its engine-driven steps (moved from the
deleted legacy-graph test module): engine-run actions, identify-then-diagnose in
one turn, the hypothesis object, turn holding, the bridge device check and
hypothesis rejection.

Run: pytest tests/test_walker_flow.py -v
"""

import json

import pytest

from tests.tool_fakes import install_fake_tools


@pytest.mark.usefixtures("walker_driven")
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
        agent.state.identity.customer_id = "CUST105"
        agent.state.resolution.procedure = {
            "verdict": "foreign_mac",
            "step": "bind_mac",
            "asked": False,
        }

    def _at_restored(self, agent):
        agent.state.identity.customer_id = "CUST105"
        agent.state.resolution.procedure = {
            "verdict": "foreign_mac",
            "step": "confirm_restored",
            "asked": True,
        }

    def _stub_tools(self, monkeypatch, telemetry):
        import agent.react_agent as ra

        install_fake_tools(
            monkeypatch, lambda name, args: json.dumps({"success": True, "new_mac": "X"})
        )
        monkeypatch.setattr("agent.walker_flow.fresh_diagnose_reason", lambda state, rt: telemetry)

    def test_bind_announces_then_walks_to_confirm(self, monkeypatch):
        from agent.narrator_flow import mark_step_presented
        from agent.walker_flow import advance_resolution, ensure_action_done

        agent = self._agent()
        self._at_bind(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        # The engine binds + re-reads telemetry, but does NOT close or jump ahead —
        # it STAYS on bind_mac to announce (model B). Telemetry is recorded.
        assert ensure_action_done(agent.state, agent.runtime) is True
        assert agent.state.closing.case_closed is False
        assert agent.state.resolution.procedure["step"] == "bind_mac"
        assert agent.state.resolution.procedure["telemetry_fixed"] is True
        assert agent.state.resolution.procedure["action_done"] is True
        # Once the announce is presented, the caller's next reply advances to verify.
        mark_step_presented(agent.state, agent.runtime)
        advance_resolution(agent.state, agent.runtime, "laukiu")
        assert agent.state.resolution.procedure["step"] == "confirm_restored"

    def test_bind_runs_once(self, monkeypatch):
        from agent.walker_flow import ensure_action_done

        agent = self._agent()
        self._at_bind(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        assert ensure_action_done(agent.state, agent.runtime) is True
        assert (
            ensure_action_done(agent.state, agent.runtime) is False
        )  # action_done guard — no re-bind

    def test_bind_tool_withheld_after_engine_ran(self, monkeypatch):
        from agent.narrator_flow import scoped_tools_schema
        from agent.walker_flow import ensure_action_done

        # Once the engine has bound (action_done), update_mac must NOT be exposed to
        # the model, or the single-tool step gets re-called to the limit (observed:
        # update_mac x6 -> 'negaliu apdoroti'). The model only announces on this turn.
        agent = self._agent()
        self._at_bind(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        ensure_action_done(
            agent.state, agent.runtime
        )  # engine binds; stays on bind_mac to announce
        names = {t["function"]["name"] for t in scoped_tools_schema(agent.state, agent.runtime)}
        assert "update_mac" not in names

    def test_restored_yes_resolves(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        agent = self._agent()
        self._at_restored(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        advance_resolution(agent.state, agent.runtime, "taip, veikia")
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "resolved"

    def test_restored_no_but_provider_ok_pivots_client_side(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        agent = self._agent()
        self._at_restored(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")  # provider OK
        advance_resolution(agent.state, agent.runtime, "ne, vis dar neveikia")
        # Provider OK but caller has no internet -> in-home fault, not escalate.
        assert agent.state.closing.case_closed is False
        assert agent.state.resolution.procedure["step"] == "client_side"

    def test_restored_no_and_line_still_down_waits_then_escalates(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        agent = self._agent()
        self._at_restored(agent)
        self._stub_tools(monkeypatch, telemetry="foreign_mac")  # line not restored yet
        advance_resolution(
            agent.state, agent.runtime, "ne"
        )  # 1st denial -> wait (may take a few minutes)
        assert agent.state.resolution.procedure["step"] == "confirm_restored"
        agent.state.resolution.procedure["asked"] = True
        advance_resolution(agent.state, agent.runtime, "vis dar ne")  # 2nd denial -> escalate
        assert agent.state.resolution.procedure["step"] == "escalate"

    def test_ensure_action_noop_on_confirm_step(self, monkeypatch):
        from agent.walker_flow import ensure_action_done

        agent = self._agent()
        self._at_restored(agent)  # a CONFIRM step, not ACTION
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        assert ensure_action_done(agent.state, agent.runtime) is False  # nothing to run
        assert agent.state.closing.case_closed is False

    def test_instruct_steps_walk_one_per_turn(self):
        from agent.narrator_flow import mark_step_presented
        from agent.walker_flow import advance_resolution

        # "nieko nekeičiau" -> the cable INSTRUCT steps are walked ONE per reply:
        # each advances only after its instruction was presented last turn.
        agent = self._agent()
        agent.state.identity.customer_id = "CUST105"
        agent.state.resolution.procedure = {
            "verdict": "foreign_mac",
            "step": "cable_check",
            "asked": False,
        }

        # Instruction not presented yet -> a reply does NOT skip ahead.
        advance_resolution(agent.state, agent.runtime, "gerai")
        assert agent.state.resolution.procedure["step"] == "cable_check"
        # Present it, then the next reply advances to the reconnect instruction.
        mark_step_presented(agent.state, agent.runtime)
        advance_resolution(agent.state, agent.runtime, "geltoname")
        assert agent.state.resolution.procedure["step"] == "cable_reconnect"
        # And one more reply (after presenting) reaches the bind action.
        mark_step_presented(agent.state, agent.runtime)
        advance_resolution(agent.state, agent.runtime, "padariau")
        assert agent.state.resolution.procedure["step"] == "bind_mac"


class TestIdentifyThenDiagnoseSameTurn:
    """resolve_address identifies -> the engine diagnoses in the SAME turn, so one
    reply confirms the address AND delivers the finding. Without this the
    identification turn has nothing to say and the model improvises ("nėra žinomų
    gedimų", "kokie įrenginiai prijungti?") — or the caller goes quiet and it stalls."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="unknown")

    def test_resolve_triggers_diagnosis_and_carries_the_finding(self, db_connection):
        from agent.narrator_flow import augment_tool_result, result_narration_tail
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
        agent.state.identity.customer_id = "CUST101"  # committed by resolve_address
        out = json.loads(augment_tool_result(agent.state, agent.runtime, "resolve_address", obs))

        # Arc v3 + identification ladder: the engine diagnosed SILENTLY (verdict in
        # state); the reply first finishes identification with the caller-intro
        # question ("su kuo kalbu?") — the result is deferred one turn behind it.
        assert agent.state.diagnosis.verdicts["network"]["reason"] == "billing_suspended"
        assert "su kuo kalbu" in out["message"].lower()
        assert agent.state.identity.result_pending is True
        # Once the caller introduces themselves, the tail delivers the real result.
        agent.state.identity.caller_name = "Jonas"
        tail = result_narration_tail(agent.state, agent.runtime)
        assert "Patikrinsiu būseną" in tail
        assert "ŽINIA" in tail
        assert (
            agent.state.diagnosis.news_delivered is True
        )  # inform news marked told — never repeated

    def test_resolve_activates_the_strategy_through_the_real_tool_loop(self, db_connection):
        """Regression: the tool loop augmented BEFORE committing customer_id, so
        _augment_resolve_result saw no id, skipped diagnosis, and the strategy never
        activated — the whole dead-router walk fell back to free-form LLM (step=None
        for the entire call). Drive the actual loop (no pre-set id) and require the
        strategy to be live afterwards."""
        from types import SimpleNamespace

        from agent.executor_flow import execute_tool_calls

        agent = self._agent()
        call = SimpleNamespace(
            id="c1",
            type="function",
            function=SimpleNamespace(
                name="resolve_address",
                arguments=json.dumps(
                    {"city": "Šiauliai", "street": "Vilniaus g.", "house_number": "29"}
                ),
            ),
        )
        execute_tool_calls(
            agent.state, agent.runtime, SimpleNamespace(content=None, tool_calls=[call])
        )

        assert agent.state.identity.customer_id == "CUST009"
        assert agent.state.resolution.procedure is not None  # strategy live, not None
        assert agent.state.resolution.procedure["verdict"] == "no_mac_observed"
        assert agent.state.diagnosis.hypothesis["cause"] == "no_mac_observed"

    def test_failed_resolve_does_not_diagnose(self, db_connection):
        from agent.narrator_flow import augment_tool_result
        from agent.tools import execute_tool

        agent = self._agent()
        obs = execute_tool("resolve_address", {"street": "Tilžės g."})  # no house -> no hit
        out = augment_tool_result(agent.state, agent.runtime, "resolve_address", obs)
        assert agent.state.diagnosis.verdicts == {}
        assert "DIAGNOZĖ" not in out


class TestHypothesisObject:
    """The verdict tree decides; the hypothesis mirrors it so the agent can narrate the
    arc — including CONFIRMATION, which we could not say before (only rejection was
    tracked)."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="unknown")

    def _diagnose(self, agent, reason):
        from agent.narrator_flow import update_state_from_observation

        update_state_from_observation(
            agent.state,
            agent.runtime,
            "diagnose_connection",
            json.dumps({"success": True, "verdict": {"reason": reason, "side": "x", "group": "B"}}),
        )

    def test_verdict_opens_a_belief_with_its_reason(self):
        agent = self._agent()
        agent.state.identity.customer_id = "CUST009"
        self._diagnose(agent, "no_mac_observed")

        h = agent.state.diagnosis.hypothesis
        assert h["cause"] == "no_mac_observed"
        assert h["status"] == "testing"
        assert h["because"]  # seeded with what the telemetry showed

    def test_a_working_fix_confirms_it(self):
        from agent.narrator_flow import state_facts_block
        from agent.walker_flow import route_to

        agent = self._agent()
        agent.state.identity.customer_id = "CUST009"
        self._diagnose(agent, "no_mac_observed")
        route_to(agent.state, agent.runtime, agent.state.resolution.procedure, "resolve")

        assert agent.state.diagnosis.hypothesis["status"] == "confirmed"
        assert "PASITVIRTINO" in (state_facts_block(agent.state, agent.runtime) or "")

    def test_rejected_causes_are_remembered_and_not_re_offered(self, monkeypatch):
        import agent.react_agent as ra
        from agent.narrator_flow import state_facts_block
        from agent.walker_flow import advance_resolution

        agent = self._agent()
        agent.state.identity.customer_id = "CUST105"
        agent.state.diagnosis.hypothesis = {
            "cause": "foreign_mac",
            "because": ["linijoje kitas įrenginys"],
            "status": "testing",
            "settled_by": None,
        }
        agent.state.resolution.procedure = {
            "verdict": "foreign_mac",
            "step": "confirm_restored",
            "asked": True,
            "restored_denials": 1,
        }
        monkeypatch.setattr(
            "agent.walker_flow.fresh_diagnose_reason", lambda state, rt: "foreign_mac"
        )
        install_fake_tools(
            monkeypatch,
            lambda n, a: json.dumps(
                {
                    "success": True,
                    "verdict": {"reason": "healthy_to_router", "side": "x", "group": "B7"},
                }
            ),
        )
        advance_resolution(agent.state, agent.runtime, "vis dar neveikia")

        assert [x["cause"] for x in agent.state.diagnosis.rejected_hypotheses] == ["foreign_mac"]
        assert agent.state.diagnosis.hypothesis["cause"] == "healthy_to_router"  # a new belief
        assert "JAU ATMESTA" in (state_facts_block(agent.state, agent.runtime) or "")


@pytest.mark.usefixtures("walker_driven")
class TestTurnHolding:
    """Only a real answer or a completed action advances the walker. Everything else
    holds it — this is what stopped the agent running ahead of the caller."""

    def _at_step(self, monkeypatch, step_id, reason="no_mac_observed"):
        import agent.react_agent as ra

        agent = ra.ReactAgent(caller_phone="unknown")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": step_id,
            "asked": True,
        }
        monkeypatch.setattr("agent.walker_flow.fresh_diagnose_reason", lambda state, rt: reason)
        return agent

    def test_in_progress_waits_instead_of_checking(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        # Observed: "atsinešiu kompiuterį" advanced the step, so the engine read the
        # line before anything was plugged in and concluded the bridge had failed.
        agent = self._at_step(monkeypatch, "dr_plug_pc")
        advance_resolution(agent.state, agent.runtime, "Gerai, atsinešiu kompiuterį, pajungsiu.")
        assert agent.state.resolution.procedure["step"] == "dr_plug_pc"  # held
        assert agent.state.dialog.awaiting == "client_action"

    def test_done_advances(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        agent = self._at_step(monkeypatch, "dr_plug_pc")
        advance_resolution(agent.state, agent.runtime, "įkišau")
        assert agent.state.resolution.procedure["step"] != "dr_plug_pc"
        assert agent.state.dialog.awaiting is None

    def test_question_and_confusion_hold(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        for reply in ("o kiek tai kainuos?", "nesuprantu, kas tas kabelis"):
            agent = self._at_step(monkeypatch, "dr_offer_bridge")
            advance_resolution(agent.state, agent.runtime, reply)
            assert agent.state.resolution.procedure["step"] == "dr_offer_bridge"

    def test_repeated_confusion_breaks_the_step_down(self, monkeypatch):
        from agent.narrator_flow import state_facts_block
        from agent.walker_flow import advance_resolution

        agent = self._at_step(monkeypatch, "dr_lights")
        advance_resolution(agent.state, agent.runtime, "nesuprantu ko norit")
        assert agent.state.dialog.step_confusions == 1
        assert "NESUPRATO" in (state_facts_block(agent.state, agent.runtime) or "")
        advance_resolution(agent.state, agent.runtime, "vis tiek nesuprantu")
        assert agent.state.dialog.step_confusions == 2
        assert "MAŽIAUSIĄ" in (
            state_facts_block(agent.state, agent.runtime) or ""
        )  # finest breakdown
        # a real answer clears it and moves on
        advance_resolution(agent.state, agent.runtime, "nedega")
        assert agent.state.dialog.step_confusions == 0

    def test_waiting_turns_accumulate_for_a_check_in(self, monkeypatch):
        from agent.narrator_flow import state_facts_block
        from agent.walker_flow import advance_resolution

        agent = self._at_step(monkeypatch, "dr_plug_pc")
        for _ in range(3):
            advance_resolution(agent.state, agent.runtime, "tuoj, ieškau")
        assert agent.state.dialog.awaiting_turns == 3
        assert "ILGAI LAUKIAM" in (state_facts_block(agent.state, agent.runtime) or "")


@pytest.mark.usefixtures("walker_driven")
class TestBridgeSeesDevice:
    """The bridge binds only once telemetry SEES the device the caller plugged in —
    binding blindly when the cable is in the wrong socket fails confusingly."""

    def _at_plug(self, monkeypatch, reason):
        import agent.react_agent as ra

        agent = ra.ReactAgent(caller_phone="unknown")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_plug_pc",
            "asked": True,
        }
        monkeypatch.setattr("agent.walker_flow.fresh_diagnose_reason", lambda state, rt: reason)
        return agent

    def test_device_seen_goes_to_bind(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        agent = self._at_plug(monkeypatch, "foreign_mac")  # anything but no_mac_observed
        advance_resolution(agent.state, agent.runtime, "įkišiau")
        assert agent.state.resolution.procedure["step"] == "dr_bind"
        assert agent.state.resolution.procedure["device_seen"] is True

    def test_not_seen_walks_back_to_the_cable(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        agent = self._at_plug(monkeypatch, "no_mac_observed")  # still nothing on the line
        advance_resolution(agent.state, agent.runtime, "įkišiau")
        assert agent.state.resolution.procedure["step"] == "dr_pick_cable"  # wrong cable — retry
        assert agent.state.resolution.procedure["device_seen"] is False

    def test_second_failure_escalates(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        agent = self._at_plug(monkeypatch, "no_mac_observed")
        agent.state.resolution.procedure["plug_retries"] = 1  # already tried once
        advance_resolution(agent.state, agent.runtime, "įkišiau")
        assert agent.state.resolution.procedure["step"] == "escalate"


class TestHypothesisRejection:
    """A fix that does not restore the line rejects THAT hypothesis and looks for the
    next one — the agent has a Plan B instead of registering at the first failure."""

    def _at_restored(self, monkeypatch, telemetry_after):
        import agent.react_agent as ra

        agent = ra.ReactAgent(caller_phone="unknown")
        agent.state.identity.customer_id = "CUST105"
        agent.state.resolution.procedure = {
            "verdict": "foreign_mac",
            "step": "confirm_restored",
            "asked": True,
            "restored_denials": 1,  # one denial already: the next one decides
        }
        monkeypatch.setattr(
            "agent.walker_flow.fresh_diagnose_reason", lambda state, rt: "foreign_mac"
        )
        install_fake_tools(
            monkeypatch,
            lambda n, args: json.dumps(
                {"success": True, "verdict": {"reason": telemetry_after, "side": "x", "group": "B"}}
            ),
        )
        return agent

    def test_new_verdict_switches_strategy_and_flags_the_rethink(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        agent = self._at_restored(monkeypatch, telemetry_after="healthy_to_router")
        advance_resolution(agent.state, agent.runtime, "vis dar neveikia")

        assert agent.state.diagnosis.failed_hypotheses == ["foreign_mac"]
        assert agent.state.resolution.procedure["verdict"] == "healthy_to_router"  # Plan B
        assert agent.state.resolution.procedure["step"] == "cs_scope"
        assert agent.state.diagnosis.pivoted_from == "foreign_mac"  # narrate it once

    def test_same_verdict_has_no_plan_b_so_it_escalates(self, monkeypatch):
        from agent.walker_flow import advance_resolution

        agent = self._at_restored(monkeypatch, telemetry_after="foreign_mac")
        advance_resolution(agent.state, agent.runtime, "vis dar neveikia")

        assert agent.state.diagnosis.failed_hypotheses == ["foreign_mac"]
        assert agent.state.resolution.procedure["step"] == "escalate"
        assert agent.state.diagnosis.pivoted_from is None

    def test_rethink_is_voiced_once_then_cleared(self, monkeypatch):
        from agent.narrator_flow import mark_step_presented, state_facts_block
        from agent.walker_flow import advance_resolution

        agent = self._at_restored(monkeypatch, telemetry_after="healthy_to_router")
        advance_resolution(agent.state, agent.runtime, "vis dar neveikia")

        facts = state_facts_block(agent.state, agent.runtime) or ""
        assert "PERSIGALVOJIMAS" in facts
        mark_step_presented(agent.state, agent.runtime)  # the reply carried it
        assert agent.state.diagnosis.pivoted_from is None
        assert "PERSIGALVOJIMAS" not in (state_facts_block(agent.state, agent.runtime) or "")

"""
Tests for the resolution walker and its engine-driven steps (moved from the
deleted legacy-graph test module): engine-run actions, identify-then-diagnose in
one turn, the hypothesis object, turn holding, the bridge device check and
hypothesis rejection.

Run: pytest tests/test_procedure.py -v
"""

import json

import pytest

from tests.calls import make_agent
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
        from tests.calls import make_agent

        return make_agent("unknown")

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

        install_fake_tools(
            monkeypatch, lambda name, args: json.dumps({"success": True, "new_mac": "X"})
        )
        monkeypatch.setattr(
            "agent.execute.diagnosis.fresh_diagnose_reason", lambda state, rt: telemetry
        )

    def test_bind_announces_then_walks_to_confirm(self, monkeypatch):
        from agent.decide.procedure import advance
        from agent.execute.diagnosis import ensure_action_done
        from agent.execute.step import mark_step_presented

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
        advance(agent.state, agent.runtime, "laukiu")
        assert agent.state.resolution.procedure["step"] == "confirm_restored"

    def test_bind_runs_once(self, monkeypatch):
        from agent.execute.diagnosis import ensure_action_done

        agent = self._agent()
        self._at_bind(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        assert ensure_action_done(agent.state, agent.runtime) is True
        assert (
            ensure_action_done(agent.state, agent.runtime) is False
        )  # action_done guard — no re-bind

    def test_bind_runs_once_and_the_step_stays_to_announce(self, monkeypatch):
        from agent.execute.diagnosis import ensure_action_done

        # The engine binds; the step stays on bind_mac so the speaker only announces it
        # (before M5 the model could re-call the exposed tool to the limit).
        agent = self._agent()
        self._at_bind(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        assert ensure_action_done(agent.state, agent.runtime) is True
        assert agent.state.resolution.procedure["action_done"] is True
        assert ensure_action_done(agent.state, agent.runtime) is False

    def test_restored_yes_resolves(self, monkeypatch):
        from agent.decide.procedure import advance

        agent = self._agent()
        self._at_restored(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        advance(agent.state, agent.runtime, "taip, veikia")
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "resolved"

    def test_restored_no_but_provider_ok_pivots_client_side(self, monkeypatch):
        from agent.decide.procedure import advance

        agent = self._agent()
        self._at_restored(agent)
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")  # provider OK
        advance(agent.state, agent.runtime, "ne, vis dar neveikia")
        # Provider OK but caller has no internet -> in-home fault, not escalate.
        assert agent.state.closing.case_closed is False
        assert agent.state.resolution.procedure["step"] == "client_side"

    def test_restored_no_and_line_still_down_waits_then_escalates(self, monkeypatch):
        from agent.decide.procedure import advance

        agent = self._agent()
        self._at_restored(agent)
        self._stub_tools(monkeypatch, telemetry="foreign_mac")  # line not restored yet
        advance(agent.state, agent.runtime, "ne")  # 1st denial -> wait (may take a few minutes)
        assert agent.state.resolution.procedure["step"] == "confirm_restored"
        agent.state.resolution.procedure["asked"] = True
        advance(agent.state, agent.runtime, "vis dar ne")  # 2nd denial -> escalate
        assert agent.state.resolution.procedure["step"] == "escalate"

    def test_ensure_action_noop_on_confirm_step(self, monkeypatch):
        from agent.execute.diagnosis import ensure_action_done

        agent = self._agent()
        self._at_restored(agent)  # a CONFIRM step, not ACTION
        self._stub_tools(monkeypatch, telemetry="healthy_to_router")
        assert ensure_action_done(agent.state, agent.runtime) is False  # nothing to run
        assert agent.state.closing.case_closed is False

    def test_instruct_steps_walk_one_per_turn(self):
        from agent.decide.procedure import advance
        from agent.execute.step import mark_step_presented

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
        advance(agent.state, agent.runtime, "gerai")
        assert agent.state.resolution.procedure["step"] == "cable_check"
        # Present it, then the next reply advances to the reconnect instruction.
        mark_step_presented(agent.state, agent.runtime)
        advance(agent.state, agent.runtime, "geltoname")
        assert agent.state.resolution.procedure["step"] == "cable_reconnect"
        # And one more reply (after presenting) reaches the bind action.
        mark_step_presented(agent.state, agent.runtime)
        advance(agent.state, agent.runtime, "padariau")
        assert agent.state.resolution.procedure["step"] == "bind_mac"


def _confirm_change(agent, answer):
    """D-05: the recheck's new cause is asked about, then the caller answers."""
    from agent.decide.rules import hypothesis_confirm
    from agent.decide.rules.reply import scripted_words

    question = scripted_words(agent.state, agent.runtime, None)
    agent.state.turn.user_input = answer
    hypothesis_confirm.plan(agent.state, agent.runtime)
    return question


class TestIdentifyThenDiagnoseSameTurn:
    """resolve_address identifies -> the engine diagnoses in the SAME turn, so one
    reply confirms the address AND delivers the finding. Without this the
    identification turn has nothing to say and the model improvises ("nėra žinomų
    gedimų", "kokie įrenginiai prijungti?") — or the caller goes quiet and it stalls."""

    def _agent(self):
        from tests.calls import make_agent

        return make_agent("unknown")

    def _slots(self, agent, street, house, apartment=None, city=None):
        from agent.slots import SlotStatus

        p = agent.state.identity.profile
        p.street.propose(street, 1.0, SlotStatus.RESOLVED)
        p.house.propose(house, 1.0, SlotStatus.RESOLVED)
        if apartment:
            p.apartment.propose(apartment, 1.0, SlotStatus.RESOLVED)
        if city:
            p.city.propose(city, 1.0, SlotStatus.RESOLVED)

    def test_the_commit_diagnoses_silently_and_defers_the_result(self, db_connection):
        """Wave 1b: the identification rule commits the address AND decides to diagnose
        (the chain used to hide inside the tool-observation handler)."""
        from agent.decide.rules.identification import engine_resolve_from_slots
        from agent.speak.context_card import result_narration_tail

        agent = self._agent()
        self._slots(agent, "Tilžės g.", "60", apartment="3", city="Šiauliai")

        assert engine_resolve_from_slots(agent.state, agent.runtime) is True

        assert agent.state.identity.customer_id == "CUST101"
        assert agent.state.diagnosis.verdicts["network"]["reason"] == "billing_suspended"
        # The reply finishes identification first ("su kuo kalbu?" — the caller-intro
        # head rule), so the news waits for its own turn and is then delivered whole.
        agent.state.identity.caller_name = "Jonas"
        tail = result_narration_tail(agent.state, agent.runtime)
        assert "Patikrinsiu būseną" in tail and "ŽINIA" in tail
        assert agent.state.diagnosis.news_delivered is True  # never repeated

    def test_the_commit_activates_the_strategy(self, db_connection):
        """Regression: the diagnosis ran before customer_id was committed, so the
        strategy never activated and the whole dead-router walk fell back to the LLM."""
        from agent.decide.rules.identification import engine_resolve_from_slots

        agent = self._agent()
        self._slots(agent, "Vilniaus g.", "29", city="Šiauliai")

        engine_resolve_from_slots(agent.state, agent.runtime)

        assert agent.state.identity.customer_id == "CUST009"
        assert agent.state.resolution.procedure["verdict"] == "no_mac_observed"
        assert agent.state.diagnosis.hypothesis["cause"] == "no_mac_observed"

    def test_a_failed_commit_does_not_diagnose(self, db_connection):
        from agent.decide.rules.identification import engine_resolve_from_slots

        agent = self._agent()
        self._slots(agent, "Tilžės g.", "999999")  # no such house -> no customer

        assert engine_resolve_from_slots(agent.state, agent.runtime) is False
        assert agent.state.identity.customer_id is None
        assert agent.state.diagnosis.verdicts == {}


class TestHypothesisObject:
    """The verdict tree decides; the hypothesis mirrors it so the agent can narrate the
    arc — including CONFIRMATION, which we could not say before (only rejection was
    tracked)."""

    def _agent(self):
        from tests.calls import make_agent

        return make_agent("unknown")

    def _diagnose(self, agent, reason):
        from agent.execute.observe import update_state_from_observation

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
        from agent.decide.procedure import route_to
        from agent.speak.context_card import context_card

        agent = self._agent()
        agent.state.identity.customer_id = "CUST009"
        self._diagnose(agent, "no_mac_observed")
        route_to(agent.state, agent.runtime, agent.state.resolution.procedure, "resolve")

        assert agent.state.diagnosis.hypothesis["status"] == "confirmed"
        assert "HYPOTHESIS CONFIRMED" in (context_card(agent.state, agent.runtime) or "")

    def test_rejected_causes_are_remembered_and_not_re_offered(self, monkeypatch):
        from agent.decide.procedure import advance
        from agent.speak.context_card import context_card

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
            "agent.execute.diagnosis.fresh_diagnose_reason", lambda state, rt: "foreign_mac"
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
        advance(agent.state, agent.runtime, "vis dar neveikia")
        assert agent.state.diagnosis.hypothesis["cause"] == "foreign_mac"  # only in doubt (D-05)
        _confirm_change(agent, "Taip")

        assert [x["cause"] for x in agent.state.diagnosis.rejected_hypotheses] == ["foreign_mac"]
        assert agent.state.diagnosis.hypothesis["cause"] == "healthy_to_router"  # a new belief
        assert "ALREADY RULED OUT" in (context_card(agent.state, agent.runtime) or "")


@pytest.mark.usefixtures("walker_driven")
class TestTurnHolding:
    """Only a real answer or a completed action advances the walker. Everything else
    holds it — this is what stopped the agent running ahead of the caller."""

    def _at_step(self, monkeypatch, step_id, reason="no_mac_observed"):

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": step_id,
            "asked": True,
        }
        monkeypatch.setattr(
            "agent.execute.diagnosis.fresh_diagnose_reason", lambda state, rt: reason
        )
        return agent

    def test_in_progress_waits_instead_of_checking(self, monkeypatch):
        from agent.decide.procedure import advance

        # Observed: "atsinešiu kompiuterį" advanced the step, so the engine read the
        # line before anything was plugged in and concluded the bridge had failed.
        agent = self._at_step(monkeypatch, "dr_plug_pc")
        advance(agent.state, agent.runtime, "Gerai, atsinešiu kompiuterį, pajungsiu.")
        assert agent.state.resolution.procedure["step"] == "dr_plug_pc"  # held
        assert agent.state.dialog.awaiting == "client_action"

    def test_done_advances(self, monkeypatch):
        from agent.decide.procedure import advance

        agent = self._at_step(monkeypatch, "dr_plug_pc")
        advance(agent.state, agent.runtime, "įkišau")
        assert agent.state.resolution.procedure["step"] != "dr_plug_pc"
        assert agent.state.dialog.awaiting is None

    def test_question_and_confusion_hold(self, monkeypatch):
        from agent.decide.procedure import advance

        for reply in ("o kiek tai kainuos?", "nesuprantu, kas tas kabelis"):
            agent = self._at_step(monkeypatch, "dr_offer_bridge")
            advance(agent.state, agent.runtime, reply)
            assert agent.state.resolution.procedure["step"] == "dr_offer_bridge"

    def test_repeated_confusion_breaks_the_step_down(self, monkeypatch):
        from agent.decide.procedure import advance
        from agent.speak.context_card import context_card

        agent = self._at_step(monkeypatch, "dr_lights")
        advance(agent.state, agent.runtime, "nesuprantu ko norit")
        assert agent.state.dialog.step_confusions == 1
        assert "DID NOT FOLLOW" in (context_card(agent.state, agent.runtime) or "")
        advance(agent.state, agent.runtime, "vis tiek nesuprantu")
        assert agent.state.dialog.step_confusions == 2
        assert "SMALLEST" in (context_card(agent.state, agent.runtime) or "")  # finest breakdown
        # a real answer clears it and moves on
        advance(agent.state, agent.runtime, "nedega")
        assert agent.state.dialog.step_confusions == 0

    def test_waiting_turns_accumulate_for_a_check_in(self, monkeypatch):
        from agent.decide.procedure import advance
        from agent.speak.context_card import context_card

        agent = self._at_step(monkeypatch, "dr_plug_pc")
        for _ in range(3):
            advance(agent.state, agent.runtime, "tuoj, ieškau")
        assert agent.state.dialog.awaiting_turns == 3
        assert "LONG WAIT" in (context_card(agent.state, agent.runtime) or "")


@pytest.mark.usefixtures("walker_driven")
class TestBridgeSeesDevice:
    """The bridge binds only once telemetry SEES the device the caller plugged in —
    binding blindly when the cable is in the wrong socket fails confusingly."""

    def _at_plug(self, monkeypatch, reason):

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_plug_pc",
            "asked": True,
        }
        monkeypatch.setattr(
            "agent.execute.diagnosis.fresh_diagnose_reason", lambda state, rt: reason
        )
        return agent

    def test_device_seen_goes_to_bind(self, monkeypatch):
        from agent.decide.procedure import advance

        agent = self._at_plug(monkeypatch, "foreign_mac")  # anything but no_mac_observed
        advance(agent.state, agent.runtime, "įkišiau")
        assert agent.state.resolution.procedure["step"] == "dr_bind"
        assert agent.state.resolution.procedure["device_seen"] is True

    def test_not_seen_walks_back_to_the_cable(self, monkeypatch):
        from agent.decide.procedure import advance

        agent = self._at_plug(monkeypatch, "no_mac_observed")  # still nothing on the line
        advance(agent.state, agent.runtime, "įkišiau")
        assert agent.state.resolution.procedure["step"] == "dr_pick_cable"  # wrong cable — retry
        assert agent.state.resolution.procedure["device_seen"] is False

    def test_second_failure_escalates(self, monkeypatch):
        from agent.decide.procedure import advance

        agent = self._at_plug(monkeypatch, "no_mac_observed")
        agent.state.resolution.procedure["plug_retries"] = 1  # already tried once
        advance(agent.state, agent.runtime, "įkišiau")
        assert agent.state.resolution.procedure["step"] == "escalate"


class TestHypothesisRejection:
    """A fix that does not restore the line rejects THAT hypothesis and looks for the
    next one — the agent has a Plan B instead of registering at the first failure."""

    def _at_restored(self, monkeypatch, telemetry_after):

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST105"
        agent.state.resolution.procedure = {
            "verdict": "foreign_mac",
            "step": "confirm_restored",
            "asked": True,
            "restored_denials": 1,  # one denial already: the next one decides
        }
        monkeypatch.setattr(
            "agent.execute.diagnosis.fresh_diagnose_reason", lambda state, rt: "foreign_mac"
        )
        install_fake_tools(
            monkeypatch,
            lambda n, args: json.dumps(
                {"success": True, "verdict": {"reason": telemetry_after, "side": "x", "group": "B"}}
            ),
        )
        return agent

    def test_new_verdict_switches_strategy_and_flags_the_rethink(self, monkeypatch):
        from agent.decide.procedure import advance

        agent = self._at_restored(monkeypatch, telemetry_after="healthy_to_router")
        advance(agent.state, agent.runtime, "vis dar neveikia")
        # D-05: the recheck only puts the belief in doubt — nothing switches yet.
        assert agent.state.resolution.procedure["verdict"] == "foreign_mac"
        c = agent.state.diagnosis.contradiction
        assert (c.kind, c.before_value, c.now_value) == (
            "verdict",
            "foreign_mac",
            "healthy_to_router",
        )
        question = _confirm_change(agent, "Taip, veikia telefone")
        assert "kitą vaizdą" in question  # the symptom question went out

        assert agent.state.diagnosis.failed_hypotheses == ["foreign_mac"]
        assert agent.state.resolution.procedure["verdict"] == "healthy_to_router"  # Plan B
        assert agent.state.resolution.procedure["step"] == "cs_scope"
        assert agent.state.diagnosis.pivoted_from == "foreign_mac"  # narrate it once

    def test_same_verdict_has_no_plan_b_so_it_escalates(self, monkeypatch):
        from agent.decide.procedure import advance

        agent = self._at_restored(monkeypatch, telemetry_after="foreign_mac")
        advance(agent.state, agent.runtime, "vis dar neveikia")

        assert agent.state.diagnosis.failed_hypotheses == ["foreign_mac"]
        assert agent.state.resolution.procedure["step"] == "escalate"
        assert agent.state.diagnosis.pivoted_from is None

    def test_rethink_is_voiced_once_then_cleared(self, monkeypatch):
        from agent.decide.procedure import advance
        from agent.execute.step import mark_step_presented
        from agent.speak.context_card import context_card

        agent = self._at_restored(monkeypatch, telemetry_after="healthy_to_router")
        advance(agent.state, agent.runtime, "vis dar neveikia")
        _confirm_change(agent, "Taip")

        facts = context_card(agent.state, agent.runtime) or ""
        assert "RETHINK" in facts
        mark_step_presented(agent.state, agent.runtime)  # the reply carried it
        assert agent.state.diagnosis.pivoted_from is None
        assert "RETHINK" not in (context_card(agent.state, agent.runtime) or "")


class TestStepOutcome:
    """procedure.advance reports what the answer did: advance / hold / exit."""

    def _state(self, make_state, step="rh_ability"):
        state = make_state("+37060020112")
        state.identity.customer_id = "CUST112"
        state.resolution.procedure = {"verdict": "router_hung", "step": step}
        return state

    def test_hold_names_the_awaited_role(self, make_state):
        from agent.decide.procedure import _outcome

        outcome = _outcome(self._state(make_state), "rh_ability")
        assert outcome.kind == "hold" and outcome.role == "ability_check"

    def test_advance_names_the_next_role(self, make_state):
        from agent.decide.procedure import _outcome

        outcome = _outcome(self._state(make_state, "rh_reboot"), "rh_ability")
        assert outcome.kind == "advance" and outcome.role == "reboot"

    def test_resolved_close_is_a_success_exit(self, make_state):
        from agent.decide.procedure import _outcome

        state = self._state(make_state, "rh_check")
        state.closing.case_closed = True
        state.closing.closed_reason = "resolved"
        assert _outcome(state, "rh_check").exit == "success"

    def test_a_started_registration_is_a_failure_exit(self, make_state):
        from agent.decide.procedure import _outcome

        state = self._state(make_state, "escalate")
        state.ticket.stage = "phone"
        assert _outcome(state, "rh_check").exit == "failure"


class TestHypothesisChangeDenied:
    """D-05: a denied (or twice unclear) symptom keeps the belief; the failed fix ends
    in the old procedure's registration."""

    def _doubted(self, monkeypatch):
        agent = TestHypothesisRejection()._at_restored(
            monkeypatch, telemetry_after="healthy_to_router"
        )
        from agent.decide.procedure import advance

        advance(agent.state, agent.runtime, "vis dar neveikia")
        return agent

    def test_no_keeps_the_belief_and_escalates(self, monkeypatch):
        agent = self._doubted(monkeypatch)
        _confirm_change(agent, "Ne")
        assert agent.state.resolution.procedure["verdict"] == "foreign_mac"
        assert agent.state.resolution.procedure["step"] == "escalate"
        assert agent.state.diagnosis.contradiction is None
        assert agent.state.dialog.resume_hold_due  # the "ne" is not the escalate consent

    def test_unclear_asks_again_then_keeps(self, monkeypatch):
        agent = self._doubted(monkeypatch)
        _confirm_change(agent, "hmm")
        assert agent.state.diagnosis.contradiction is not None  # asked again next
        _confirm_change(agent, "nežinau ką")
        assert agent.state.resolution.procedure["step"] == "escalate"

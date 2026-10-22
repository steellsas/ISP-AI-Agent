"""
Tests for call closing: the call ends on a farewell / 'no more' or a 2nd closing
turn, and observations drive the END-state flags (moved from the deleted
legacy-graph test module).

Run: pytest tests/closing/test_closing.py -v
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.call_record.finalizer import build_call_summary, finalize
from agent.graph_v2.state import (
    ClosingState,
    DiagnosisState,
    DialogState,
    GraphState,
    IdentityState,
    IntakeState,
    ResolutionState,
    TicketContext,
    TicketState,
    TurnScratch,
)

from tests.engine_fakes import as_call
from tests.tool_fakes import install_fake_tools

FUNCTION = "Uždarymas"


class TestClosing:
    """The call ends (is_complete) on a farewell / 'no more', or a 2nd closing turn —
    so the agent does not loop goodbyes."""

    def _agent(self):
        from tests.calls import make_agent

        return make_agent("unknown")

    def test_farewell_ends_the_call(self):
        from agent.decide.rules.closing import maybe_finish

        agent = self._agent()
        agent.state.closing.case_closed = True
        maybe_finish(agent.state, agent.runtime, "ne, ačiū")
        assert agent.state.closing.is_complete is True

    def test_question_keeps_it_open_then_caps(self):
        from agent.decide.rules.closing import maybe_finish

        agent = self._agent()
        agent.state.closing.case_closed = True
        maybe_finish(agent.state, agent.runtime, "o kiek tai kainuos?")  # a real follow-up
        assert agent.state.closing.is_complete is False
        maybe_finish(agent.state, agent.runtime, "gerai, supratau")  # 2nd closing turn -> cap
        assert agent.state.closing.is_complete is True

    def test_noop_when_not_closed(self):
        from agent.decide.rules.closing import maybe_finish

        agent = self._agent()
        maybe_finish(agent.state, agent.runtime, "viso gero")  # case not closed -> ignore
        assert agent.state.closing.is_complete is False

    def test_the_goodbye_plan_ends_the_call(self):
        """Wave 1: the farewell and the hang-up are ONE plan — a reply is never read
        back for goodbye words (the narrator's wording is not a decision)."""
        from agent.decide.rules import closing as closing_rules
        from agent.execute.actions import run_action

        agent = self._agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.closing.case_closed = True
        agent.state.ticket.ticket_id = "TKT1"
        agent.state.turn.user_input = "ačiū"

        agent.state.closing.closed_reason = "resolved"

        plan = closing_rules.plan(agent.state, agent.runtime)
        assert plan.rule == "closing.goodbye_after_ticket"
        assert plan.action.type == "close" and plan.action.args == {"complete": True}
        run_action(agent.state, agent.runtime, plan)

        assert agent.state.closing.is_complete is True
        # The farewell hangs up; WHY the call ended was decided before it.
        assert agent.state.closing.closed_reason == "resolved"

    def test_a_farewell_said_with_the_call_open_is_traced(self):
        """The net that used to hang up on goodbye words is gone; the gap is visible."""
        from agent.speak.postprocess import finalize

        agent = self._agent()
        events = []
        agent.runtime.tracer.emit = lambda event, **f: events.append((event, f))

        finalize(agent.state, agent.runtime, "Ačiū, kad paskambinote. Geros dienos!")

        assert agent.state.closing.is_complete is False
        assert any(e == "goodbye_unclosed" for e, _ in events)

    def test_a_midconversation_reply_is_not_a_farewell(self):
        from agent.speak.postprocess import finalize

        agent = self._agent()
        events = []
        agent.runtime.tracer.emit = lambda event, **f: events.append((event, f))

        finalize(agent.state, agent.runtime, "Pasakykite adresą, kuriuo neveikia internetas.")

        assert not any(e == "goodbye_unclosed" for e, _ in events)


class TestCaseStateTransitions:
    """_update_state_from_observation drives the END-state flags."""

    def _agent(self):
        from tests.calls import make_agent

        return make_agent("unknown")

    def test_active_outage_sets_reported_not_closed(self):
        import json

        from agent.execute.observe import update_state_from_observation

        agent = self._agent()
        update_state_from_observation(
            agent.state,
            agent.runtime,
            "check_outages",
            json.dumps(
                {"success": True, "affected": True, "active_outages": [{"street": "Dainų g."}]}
            ),
        )
        assert agent.state.diagnosis.outage_reported is True
        assert agent.state.closing.case_closed is False  # an outage does NOT close the case

    def test_no_outage_leaves_reported_false(self):
        import json

        from agent.execute.observe import update_state_from_observation

        agent = self._agent()
        update_state_from_observation(
            agent.state,
            agent.runtime,
            "check_outages",
            json.dumps({"success": True, "affected": False, "active_outages": []}),
        )
        assert agent.state.diagnosis.outage_reported is False


class TestClosingNode:
    """The node contract on a bare state + runtime: `run_turn_nodes(state, runtime)`
    returns the whole state as its update and reaches tools only via the gateway."""

    def test_number_correction_is_noted_through_the_gateway(self, make_state, make_runtime):
        from agent.graph_v2.state import ClosingState, TicketState, TurnScratch
        from langgraph.runtime import Runtime

        from tests.calls import run_turn_nodes

        rt = make_runtime(lambda name, args: {"success": True})
        state = make_state(
            "+37060012353",
            ticket=TicketState(ticket_id="TCK-1"),
            closing=ClosingState(case_closed=True),
            turn=TurnScratch(user_input="Skambinkite kitu numeriu 868321007"),
        )
        upd = run_turn_nodes(state, Runtime(context=rt))
        assert "Užsirašiau" in upd["turn"].reply
        assert [c[0] for c in rt.tools.provider.calls] == ["append_ticket_note"]
        assert "868321007" in rt.tools.provider.calls[0][1]["note"]
        assert state.turn.reply is None  # the node worked on its own copy


# --- from test_agent.py ---


class TestDeterministicInformClose:
    """INFORM mode (outage/billing/no-strategy) closes deterministically on a farewell —
    the engine, not the model, ends the call (fixes the goodbye loop observed live)."""

    def _informed_agent(self):
        from tests.calls import make_agent

        agent = make_agent("+37060020102")
        agent.state.identity.customer_id = "CUST102"
        agent.state.diagnosis.verdicts["network"] = {"group": "B2", "reason": "active_outage"}
        agent.state.diagnosis.outage_reported = True
        return agent

    def test_farewell_closes_outage_call(self, db_connection):
        from agent.decide.rules.closing import maybe_close_inform

        agent = self._informed_agent()
        maybe_close_inform(agent.state, agent.runtime, "Ačiū, viso gero, sudie")
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "outage"
        assert agent.state.closing.is_complete is True

    def test_no_farewell_keeps_call_open(self, db_connection):
        from agent.decide.rules.closing import maybe_close_inform

        agent = self._informed_agent()
        maybe_close_inform(agent.state, agent.runtime, "O kada tiksliai sutvarkysite?")
        assert agent.state.closing.case_closed is False

    def test_active_strategy_never_closed_here(self, db_connection):
        """A fault the Case is fixing is not news — even a goodbye must not end the call
        here (the Case owns it)."""
        from agent.decide.rules.closing import maybe_close_inform

        agent = self._informed_agent()
        agent.state.diagnosis.outage_reported = False
        agent.state.diagnosis.verdicts["network"] = {"group": "B6", "reason": "foreign_mac"}
        agent.state.case.fault, agent.state.case.solution = "foreign_mac", 0
        maybe_close_inform(agent.state, agent.runtime, "Ačiū, viso gero, sudie")
        assert agent.state.closing.case_closed is False


class TestScriptedWrapUp:
    """After the inform news, ANY non-question turn wraps up deterministically —
    a garbled goodbye ("Nusigaro") had looped 'nesupratau, pakartokite' forever."""

    def _informed(self, db_connection):
        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.identity.customer_id = "CUST101"
        agent.state.diagnosis.verdicts["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent.state.diagnosis.news_delivered = True
        return agent

    def test_garbled_goodbye_wraps_up(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        # Closing wave block 2 (2026-09-09): a content-bearing turn first gets
        # a REACTION (the caller may have said something real — "Vilma",
        # "sumokėjau"); the cap of 2 still guarantees a garbled goodbye
        # ("Nusigaro") cannot loop the wrap-up — the third turn closes.
        agent = self._informed(db_connection)
        assert scripted_words(agent.state, agent.runtime, "Nusigaro.") is None
        assert scripted_words(agent.state, agent.runtime, "Nusigaro.") is None
        reply = scripted_words(agent.state, agent.runtime, "Nusigaro.")
        assert reply and "Ačiū, kad paskambinote" in reply
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "inform"
        assert agent.state.closing.is_complete is True

    def test_question_after_news_goes_to_llm(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._informed(db_connection)
        assert scripted_words(agent.state, agent.runtime, "O kiek turiu sumokėti?") is None
        assert agent.state.closing.case_closed is False

    def test_wants_more_goes_to_llm(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._informed(db_connection)
        assert scripted_words(agent.state, agent.runtime, "Palaukite, dar turiu klausimą") is None
        assert agent.state.closing.case_closed is False


@pytest.fixture
def call(make_state, make_runtime):
    state, rt = make_state("+37060012353"), make_runtime()
    state.intake.problem_type = "internet_down"
    return state, rt


def _identified(state, fault=True):
    state.identity.customer_id = "CUST009"
    state.identity.caller_name = "Giedrius"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    if fault:
        state.case.fault, state.case.solution = "no_mac_observed", 0


# --- from test_v3_stage3a.py ---


class TestU3TheQuestionSaysWhatIsLeft:
    def test_unidentified(self, call):
        from agent.decide.rules.head import confirm_end_key

        state, _ = call
        assert confirm_end_key(state) == "identification.confirm_end_unidentified"

    def test_a_fault_being_fixed(self, call):
        from agent.decide.rules.head import confirm_end_key

        state, _ = call
        _identified(state)
        assert confirm_end_key(state) == "identification.confirm_end_fault"

    def test_news_not_yet_told(self, call):
        from agent.decide.rules.head import confirm_end_key

        state, _ = call
        _identified(state, fault=False)
        state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
        assert confirm_end_key(state) == "identification.confirm_end_news"

    def test_the_phrases_say_what_is_left(self):
        from agent.contract.locale import phrase

        assert "neradau jūsų sutarties" in phrase("identification.confirm_end_unidentified")
        assert "neišsprendėme" in phrase("identification.confirm_end_fault")


class TestU6RefusingAsksWhetherToEnd:
    @pytest.mark.parametrize(
        ("said", "asks"),
        [
            ("Nebenoriu, nutraukite", True),
            ("Nenoriu tęsti", True),
            ("Viso gero", True),
            ("Nesu namuose", False),  # U9: cannot now — the Case's later/callback path
            ("Neturiu laiko dabar", False),
            ("Nežinau, kur tas routeris", False),
        ],
    )
    def test_mid_fix(self, call, said, asks):
        from agent.decide.rules.head import farewell_mid_process

        state, rt = call
        _identified(state)
        assert farewell_mid_process(state, rt, said) is asks
        assert state.dialog.end_confirm_pending is asks


class TestU10TheConfirmedEndHasItsConclusion:
    @pytest.mark.parametrize(
        ("identified", "key"),
        [
            (False, "identification.declined_goodbye_unidentified"),
            (True, "identification.declined_goodbye_fault"),
        ],
    )
    def test_end_confirmed(self, call, identified, key):
        from agent.decide.rules.head import _end_declined

        state, rt = call
        if identified:
            _identified(state)
        _end_declined(state, rt)

        assert state.closing.declined_goodbye_due == key
        assert state.closing.case_closed and state.closing.is_complete

    def test_the_reply_is_the_scripted_goodbye(self, call):
        from agent.decide.rules.head import _end_declined
        from agent.decide.rules.reply import plan_reply

        state, rt = call
        _identified(state)
        _end_declined(state, rt)
        plan = plan_reply(state, rt, "Taip, baigiam")

        assert plan.rule == "dialog.declined_goodbye"
        assert "neišspręstas" in plan.say.text
        assert state.closing.declined_goodbye_due is None  # said once


class _Tracer:
    session_id = "wave9"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})

    def decisions(self):
        return [(e.get("intent"), e.get("action")) for e in self.events if e["type"] == "decision"]


@pytest.fixture
def dead_router(make_state, make_runtime):
    """The dead-router call of 2026-10-07 at the moment the Case has summed it up."""
    tracer = _Tracer()
    state, rt = make_state("+37060012353"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST009"
    state.identity.caller_name = "Andrius"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    state.case.fault, state.case.solution = "no_mac_observed", 0
    return state, rt, tracer


@pytest.fixture
def debt(make_state, make_runtime):
    """A caller who has just heard the debt news."""
    tracer = _Tracer()
    state, rt = make_state("+37060020101"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST101"
    state.identity.caller_name = "Rokas"
    state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
    state.diagnosis.news_delivered = True
    return state, rt, tracer


# --- from test_wave9_promises.py ---


class TestT1GoodbyeWithAnOpenRegistration:
    def test_the_inform_close_leaves_a_case_alone(self, dead_router):
        from agent.decide.rules.closing import maybe_close_inform

        state, rt, _ = dead_router
        state.diagnosis.news_delivered = True  # the summary turn marks the news as told
        state.case.summarised = True

        maybe_close_inform(state, rt, "Sutariam, viskas ačiū.")

        assert not state.closing.case_closed

    def test_the_inform_close_still_ends_a_debt_call(self, debt):
        from agent.decide.rules.closing import maybe_close_inform

        state, rt, _ = debt
        maybe_close_inform(state, rt, "Aišku, ačiū, viso gero")

        assert state.closing.case_closed

    def test_a_goodbye_after_the_summary_goes_to_the_registration(self, dead_router):
        from agent.decide.rules.head import farewell_mid_process

        state, rt, tracer = dead_router
        state.case.summarised = True

        assert farewell_mid_process(state, rt, "Sutariam, viskas ačiū.")
        assert not state.dialog.end_confirm_pending  # no „Ar tikrai norite baigti?"
        assert ("farewell_mid_process", "ticket_first") in tracer.decisions()

    def test_a_goodbye_mid_fix_is_confirmed_then_offered_a_technician(self, dead_router):
        from agent.decide.rules.head import end_confirm_answer, farewell_mid_process

        state, rt, _ = dead_router
        assert farewell_mid_process(state, rt, "Viso gero")
        assert state.dialog.end_confirm_pending

        end_confirm_answer(state, rt, "Taip, baigiam")
        assert state.dialog.end_ticket_offer  # not closed as „declined"
        assert not state.closing.case_closed

        end_confirm_answer(state, rt, "Taip, užregistruokite")
        assert state.ticket.stage == "phone"

    def test_a_declined_technician_closes(self, dead_router):
        from agent.decide.rules.head import end_confirm_answer, farewell_mid_process

        state, rt, _ = dead_router
        farewell_mid_process(state, rt, "Viso gero")
        end_confirm_answer(state, rt, "Taip, baigiam")
        end_confirm_answer(state, rt, "Ne, nereikia")

        assert state.closing.case_closed
        assert state.ticket.stage is None


class _Tracer_wave10_quick:
    session_id = "wave10"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def case_call(make_state, make_runtime):
    """A v2 Case call on a fault, the caller identified."""
    state, rt = make_state("+37060012353"), make_runtime(tracer=_Tracer_wave10_quick())
    state.identity.customer_id = "CUST009"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    state.case.fault, state.case.solution = "no_mac_observed", 0
    return state, rt


# --- from test_wave10_quick.py ---


def test_s5_a_hang_up_on_the_case_homework_is_a_callback(case_call, monkeypatch):
    """The homework was told and waits for „tinka?" — hanging up keeps the agreement."""
    from agent import executor_flow
    from agent.call_record import finalizer

    state, rt = case_call
    state.case.awaiting = "later_agreed"
    registered = []
    monkeypatch.setattr(
        executor_flow, "register_ticket_from_state", lambda *a, **k: registered.append(a)
    )
    finalizer.finalize(state, rt)

    assert state.closing.closed_reason == "callback"
    assert registered == []


# --- from test_fault_packs.py ---


class TestD5WaitAckAndClosing:
    """D5 (live 2026-08-25): scripted wait acknowledgements (the LLM cost up
    to 12 s for 'Gerai, palauksiu') and the closing fixes — the scripted
    goodbye must SPEAK, and a post-registration number correction must land
    on the ticket instead of vanishing."""

    def _agent(self):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        return agent

    def test_closing_goodbye_is_spoken_and_number_correction_lands(self, db_connection):
        from types import SimpleNamespace

        from agent.tools import create_ticket
        from langgraph.runtime import Runtime

        from tests.calls import run_turn_nodes

        agent = self._agent()
        res = create_ticket("CUST009", "network_issue", "routeris nedega")
        assert res.get("success")
        agent.state.ticket.ticket_id = res["ticket_id"]
        agent.state.closing.case_closed = True
        runtime = Runtime(context=agent.runtime)
        # 1) number correction: acknowledged aloud AND noted on the ticket
        upd = run_turn_nodes(
            agent.state.model_copy(
                update={"turn": TurnScratch(user_input="Skambinkite kitu numeriu 868321007")}
            ),
            runtime,
        )
        assert "Užsirašiau" in upd["turn"].reply
        assert upd["messages"][-1]["content"] == upd["turn"].reply
        agent.state = GraphState(**upd)  # the next turn starts from the committed state
        import sqlite3

        from agent.tools import get_db

        with get_db().cursor() as cur:
            cur.execute(
                "SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket.ticket_id,)
            )
            details = dict(cur.fetchone())["details"]
        assert "PATIKSLINTA" in details and "868321007" in details
        # 2) a plain 'gerai' now gets the SPOKEN scripted goodbye
        upd2 = run_turn_nodes(
            agent.state.model_copy(update={"turn": TurnScratch(user_input="Gerai, ačiū")}), runtime
        )
        assert upd2["turn"].reply and "Geros dienos" in upd2["turn"].reply
        assert upd2["messages"][-1]["content"] == upd2["turn"].reply

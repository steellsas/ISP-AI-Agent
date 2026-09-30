"""Wave 3f: the fault path as the Case drives it, turn by turn.

One driver, one question per turn. These tests walk the S6 call (a hung router) the way the
engine will, asserting the PLAN at each turn — not the wording, which belongs to the
narrator.
"""

import pytest
from agent.decide.rules import case_rule
from agent.ledger import record_client, record_telemetry

from tests.test_facts import BASE


@pytest.fixture
def call(make_state, make_runtime):
    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    return state, rt


def said(state, rt, fact, value):
    """A new caller turn: their words land, and the turn counter moves.

    The counter matters — one utterance may move the solution ONE step, because the redecide
    loop re-reads the same words on every hop (live: three steps in one turn, walking past an
    instruction that was never given).
    """
    state.dialog.turn_count += 1
    record_client(state, rt, fact, value)


class TestTheCaseWalksTheCall:
    def test_it_looks_before_it_asks(self, call):
        state, rt = call
        plan = case_rule.plan(state, rt)
        assert plan.rule == "case.probe"
        assert plan.action.type == "tool" and plan.action.name == "diagnose_connection"
        assert plan.redecide_after_action is True  # the same turn decides again
        assert plan.say.kind == "none"  # nothing is said for a check we run ourselves

    def test_with_the_line_read_it_starts_the_fix_without_a_question(self, call):
        """Wave 4a (Andrius 2026-09-23): the line sees the router and no traffic at all, so
        the reboot is the first move — asking "visuose ar tik viename?" first would change
        nothing about what we do next."""
        state, rt = call
        record_telemetry(state, rt, BASE)

        plan = case_rule.plan(state, rt)

        assert state.case.fault == "router_hung"
        assert plan.rule == "case.reach" and plan.awaiting == "reachable"

    def test_a_question_is_asked_where_it_decides_something(self, call):
        """Traffic reaches the router and the caller still has nothing: now WHICH devices
        fail is the thing only they can tell us."""
        state, rt = call
        record_telemetry(state, rt, {**BASE, "traffic": "flowing"})

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.ask" and plan.awaiting == "fail_scope"
        assert "visuose" in plan.say.text

    def test_a_caller_already_at_the_router_is_not_asked_to_go_there(self, call):
        """`done_when` on the step: "esu prie routerio" was said, so the engine moves on to
        the instruction instead of asking whether they can reach it."""
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "reachable", "yes")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.reboot" and "maitinimo" in plan.say.text

    def test_then_one_instruction_per_turn(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)  # reach
        said(state, rt, "reachable", "yes")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.reboot" and state.case.step == 1
        assert "maitinimo laidą" in plan.say.text  # the catalogue's words
        assert plan.action.type == "none"  # the caller does this, not the engine

    def test_after_the_reboot_the_engine_verifies_with_the_probe(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)
        said(state, rt, "reachable", "yes")
        case_rule.plan(state, rt)  # reboot
        state.dialog.turn_count += 1
        state.dialog.last_intent = "done"  # "padariau" — the one thing the line cannot say

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.verify"
        assert plan.action.name == "diagnose_connection" and plan.redecide_after_action

    def test_traffic_back_and_a_flap_seen_closes_the_call(self, call):
        state, rt = call
        state.case.facts.update({"fail_scope": "all", "reachable": "yes"})
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 2
        record_telemetry(state, rt, {**BASE, "traffic": "flowing", "port_flap_recent": True})

        plan = case_rule.plan(state, rt)

        assert state.case.step == 3  # past the verification: the fix worked
        assert plan.rule == "case.resolved"
        assert plan.action.type == "close" and plan.action.name == "resolved"

    def test_a_done_report_inside_a_question_still_moves_the_step(self, call):
        """Live 2026-09-28 (C1): „Tai padariau. Ką tik padariau? Kas toliau?" was read as a
        QUESTION (the mark wins in `detect_turn_intent`), so the step never moved and the same
        reboot instruction came back six times. A past-tense report of doing it counts even
        when a question rides along."""
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)  # reach
        said(state, rt, "reachable", "yes")
        case_rule.plan(state, rt)  # reboot instruction given
        state.dialog.turn_count += 1
        state.dialog.last_intent = "question"
        state.dialog.last_heard = "Tai padariau. Ką tik padariau? Kas toliau?"

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.verify", "the line is read instead of repeating the step"

    def test_a_question_without_a_done_word_does_not_move_the_step(self, call):
        """The other side of the same coin: asking about the step is not doing it."""
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)
        said(state, rt, "reachable", "yes")
        case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        state.dialog.last_intent = "question"
        state.dialog.last_heard = "O ar reikia ištraukti ir maitinimo laidą?"

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.reboot"


class TestWhenTheFixDoesNotWork:
    def test_a_reboot_nobody_saw_is_retried_once_with_the_card_s_wording(self, call):
        """Traffic came back but the line never saw the device drop: something else was
        power-cycled. The card says retry once — and only once."""
        state, rt = call
        state.case.facts.update({"fail_scope": "all", "reachable": "yes"})
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 2
        record_telemetry(state, rt, {**BASE, "traffic": "none", "port_flap_recent": False})

        plan = case_rule.plan(state, rt)

        assert state.case.step == 1 and plan.rule == "case.reboot"  # back to the reboot
        assert state.case.attempts  # counted, so it cannot loop

    def test_the_second_failure_ends_in_a_technician(self, call):
        state, rt = call
        state.case.facts.update({"reachable": "yes"})
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 2
        state.case.attempts = {"router_hung.1": 1}
        state.case.did = ["reach", "reboot"]  # the phone work really happened
        record_telemetry(state, rt, {**BASE, "traffic": "none"})

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.escalate" and state.ticket.stage == "phone"

    def test_a_technician_is_not_sent_before_the_card_s_own_fix(self, call):
        """`escalate.only_after` (Andrius 2026-09-23): a technician must not arrive to
        power-cycle a router the phone could have power-cycled. The reboot was never run
        here, so the escalation turns back into it."""
        state, rt = call
        state.case.facts.update({"reachable": "yes"})
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 2
        state.case.attempts = {"router_hung.1": 1}
        record_telemetry(state, rt, {**BASE, "traffic": "none"})

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.reboot" and state.ticket.stage != "phone"

    def test_a_caller_who_cannot_reach_the_device_is_not_held_to_it(self, call):
        """The same gate must never trap a call: if the work is impossible, the technician is
        the honest answer and the ticket records what was not done."""
        state, rt = call
        state.case.facts.update({"reachable": "no", "later_agreed": "no"})
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 2
        state.case.attempts = {"router_hung.1": 1}
        record_telemetry(state, rt, {**BASE, "traffic": "none"})

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.escalate" and state.ticket.stage == "phone"


class TestWhenNothingFits:
    def test_an_unreadable_case_ends_honestly(self, call):
        """The honest move is a technician, not the closest-looking procedure.

        Since waves 3–4b every reading the line can produce belongs to SOME card, so this is
        reached the other way: the card is settled but nothing it needs can be had (the caller
        cannot tell us, and there is nothing to assume)."""
        state, rt = call
        record_telemetry(state, rt, {**BASE, "traffic": "flowing"})
        state.case.facts["fail_scope"] = "one"
        state.case.unavailable.extend(["fail_device", "connection_type", "rebooted"])

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.escalate"
        assert state.ticket.stage == "phone"  # the contacts are collected first

    def test_an_outage_or_a_debt_is_not_ours_to_diagnose(self, call):
        """There is nothing to fix — only news to deliver. The Case yields the turn, and
        escalating here hijacked the inform path (full eval: four scenarios)."""
        state, rt = call
        record_telemetry(state, rt, {**BASE, "billing_suspended": True})

        assert case_rule.plan(state, rt) is None
        assert state.ticket.stage is None

    def test_a_step_the_catalogue_cannot_word_is_skipped_not_improvised(self, call):
        """A device nobody described has no button instruction: the engine moves on instead
        of telling the caller to press something that may not exist."""
        from agent.contract.schema import ModuleCall

        state, rt = call
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 1
        record_telemetry(state, rt, {**BASE, "device_model": "Huawei HG8245"})
        button = ModuleCall(module="reboot", args={"device": "router", "method": "button"})

        plan = case_rule._module_plan(state, rt, button, state.case.facts, rule="case.reboot")

        assert plan.rule != "case.reboot" or plan.say.text is None


class TestWhenTheCallerCannotDoItNow:
    """P-C: not being at home is a WHEN, not a fault. The caller gets the instruction for
    later and is asked if that suits them — a technician only if they want one."""

    def _at_the_reach_step(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)  # reach
        return state, rt

    def test_not_now_gives_the_instruction_for_later(self, call):
        state, rt = self._at_the_reach_step(call)
        said(state, rt, "reachable", "no")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.homework" and plan.awaiting == "later_agreed"
        assert "Kai būsite namuose" in plan.say.text
        assert "maitinimo laidą" in plan.say.text  # what they were about to be asked to do

    def test_agreeing_closes_the_call_as_a_callback(self, call):
        state, rt = self._at_the_reach_step(call)
        said(state, rt, "reachable", "no")
        case_rule.plan(state, rt)
        said(state, rt, "later_agreed", "yes")

        plan = case_rule.plan(state, rt)

        assert plan.action.type == "close" and plan.action.name == "callback"

    def test_declining_it_offers_a_technician(self, call):
        state, rt = self._at_the_reach_step(call)
        said(state, rt, "reachable", "no")
        case_rule.plan(state, rt)
        said(state, rt, "later_agreed", "no")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.escalate" and state.ticket.stage == "phone"


class TestWhenTheCallerDoesNotAnswerTheQuestion:
    """Wave 4a (eval X): the agent asked "visuose ar tik viename?" on four turns running
    while the caller kept telling it other things. The question lives on the client-side card
    now — the line carries traffic and the caller still has nothing — and the rules are: ask
    twice, the second time in other words, then carry on with what the card says to assume."""

    @pytest.fixture
    def client_side(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "traffic": "flowing"})
        return state, rt

    def test_the_same_question_is_not_asked_a_third_time(self, client_side):
        state, rt = client_side

        first = case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        second = case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        third = case_rule.plan(state, rt)

        assert first.awaiting == second.awaiting == "fail_scope"
        assert third.awaiting != "fail_scope"
        assert "fail_scope" in state.case.unavailable

    def test_the_second_ask_is_worded_differently(self, client_side):
        state, rt = client_side

        first = case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        second = case_rule.plan(state, rt)

        assert first.awaiting == second.awaiting == "fail_scope"
        assert second.say.text != first.say.text  # the card's `again` wording
        assert "Pažiūrėkite" in second.say.text

    def test_the_call_goes_on_with_what_the_card_assumes(self, client_side):
        """Andrius 2026-09-23: traffic reaches the router, so the internet is there — it is
        missing at the end device. That is the assumption, said out loud, not an answer."""
        state, rt = client_side
        state.case.asks["fail_scope"] = [1, 2]

        plan = case_rule.plan(state, rt)

        assert state.case.assumed == {"fail_scope": "one"}
        # The call carries on down the client-side road (which device fails), not to a ticket.
        assert plan.awaiting in ("fail_device", "connection_type", "rebooted")
        assert state.ticket.stage != "phone"

    def test_a_question_with_nothing_to_assume_is_a_dead_end(self, client_side):
        """`fail_device` has no assumption of its own: when the caller will not say, the call
        ends honestly instead of guessing which device they meant."""
        state, rt = client_side
        state.case.facts["fail_scope"] = "one"
        state.case.asks["fail_device"] = [1, 2]
        state.case.unavailable.append("connection_type")

        plan = case_rule.plan(state, rt)

        assert "fail_device" not in state.case.assumed
        assert plan.rule == "case.escalate" and state.ticket.stage == "phone"

    def test_an_answered_question_is_never_given_up_on(self, client_side):
        state, rt = client_side
        case_rule.plan(state, rt)  # asks fail_scope once
        said(state, rt, "fail_scope", "all")

        plan = case_rule.plan(state, rt)

        assert "fail_scope" not in state.case.unavailable
        assert plan.rule != "case.escalate"  # the answer opened a road, it did not end one


class TestACardWhoseFixIsWritten:
    """Wave 4b: the silent router is not a "nothing to do over the phone" card any more — its
    fix is a knowledge document, and the caller is walked through it one step per turn."""

    @pytest.fixture
    def silent_router(self, make_state, make_runtime):
        state, rt = make_state("+37060020106"), make_runtime()
        state.identity.customer_id = "CUST106"
        record_telemetry(state, rt, {**BASE, "dhcp_status": "no_requests", "traffic": "flowing"})
        # Wave 6: the walk is offered first and has its own tests below; these ones are about
        # what happens once the caller has agreed to it.
        record_client(state, rt, "guide_agreed", "yes")
        return state, rt

    @staticmethod
    def _guide_index(fault: str = "dhcp_silent") -> int:
        from agent.contract import cards

        steps = cards.card(fault).solution[0].steps
        return next(i for i, call in enumerate(steps) if call.module == "guide")

    def test_the_finding_is_told_before_anything_is_asked(self, silent_router):
        state, rt = silent_router

        case_rule.plan(state, rt)

        told = state.case.finding
        assert told and "adreso" in told["isvada"]
        assert "DHCP" not in told["isvada"] and "gamyklin" not in told["isvada"]

    def test_it_walks_the_document_before_a_technician(self, silent_router):
        state, rt = silent_router
        state.case.facts["reachable"] = "yes"  # they are at the router already

        plan = case_rule.plan(state, rt)

        assert state.case.fault == "dhcp_silent"
        assert plan.rule == "case.guide" and state.ticket.stage != "phone"
        assert "prijungti kompiuter" in plan.say.text.lower()  # the document's first ACTION

    def test_a_step_nobody_heard_cannot_be_finished(self, silent_router):
        """The mark is set where the reply is built, so a plan that never spoke leaves the
        step open — otherwise "taip, esu prie routerio" skipped the first step (2026-09-23)."""
        state, rt = silent_router
        state.case.facts["reachable"] = "yes"
        case_rule.plan(state, rt)  # plans step 1 — but nothing said it
        said(state, rt, "irrelevant", "yes")

        case_rule.plan(state, rt)

        assert state.case.guide_step == 0

    def test_once_said_the_next_answer_moves_one_action(self, silent_router):
        """One ACTION per turn, not one document step (wave 6).

        A written step holds several numbered points; live 2026-09-30 only the first of the
        three was ever spoken, so the caller never heard the address or the password.
        """
        state, rt = silent_router
        state.case.facts["reachable"] = "yes"
        case_rule.plan(state, rt)
        state.case.guide_said = 0  # the reply carried the first action
        state.dialog.turn_count += 1
        state.dialog.last_heard = "padariau"

        plan = case_rule.plan(state, rt)

        assert state.case.guide_step == 1
        assert plan.rule == "case.guide"
        assert "192.168.0.1" in plan.say.text, "the document's own address, not the model's"

    def test_the_document_ends_and_the_card_verifies(self, silent_router):
        state, rt = silent_router
        state.case.facts["reachable"] = "yes"
        from agent.contract import cards
        from agent.modules import guide_length

        at = self._guide_index()
        state.case.fault, state.case.solution, state.case.step = "dhcp_silent", 0, at
        last = guide_length(cards.card("dhcp_silent").solution[0].steps[at]) - 1
        state.case.guide_step, state.case.guide_said = last, last
        state.dialog.turn_count += 1
        state.dialog.last_heard = "padariau"

        plan = case_rule.plan(state, rt)

        assert state.case.step == at + 1  # past the guide
        assert plan.rule == "case.verify"


class TestWhatTheFindingSays:
    """Live 2026-09-23: two complaints about the finding moment — it invited an action the
    engine had not planned yet ("ar galėtumėte perkrauti?" and only THEN "ar galite
    prieiti?"), and the honest ending said nothing about what had been checked."""

    def test_the_honest_ending_still_says_what_was_checked(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "traffic": "flowing"})

        case_rule.announce(state, rt, "unclear_fault")

        told = state.case.finding
        assert told, "the finding must be held until something says it"
        # OUR side only: "srautas iki routerio" would drag the router into a TV call (eval T1).
        assert "linija" in told["faktai"] and "mazgas" in told["faktai"]
        assert "routerio" not in told["faktai"] and told["isvada"]

    def test_a_finding_without_an_offer_does_not_instruct(self, call):
        from agent.speak.context_card import _goal_recap_and_findings

        state, rt = call
        record_telemetry(state, rt, BASE)
        case_rule.plan(state, rt)  # settles router_hung and announces its finding

        lines = " ".join(_goal_recap_and_findings(state, rt))

        assert "FINDINGS MOMENT" in lines or "OPEN THE REPLY" in lines
        assert "Do NOT ask them to do anything yet" in lines or "before anything else" in lines


class TestWhenTheCallerWalksAhead:
    """Wave 6, from the live calls of 2026-09-29/30.

    Andrius: *„kartais padaryti veiksmai iš karto peršoka būseną… jei peršoko svarbius
    žingsnius, turėtų grįžti ir paprašyti padaryti tai pažingsniui, bet būtinai paaiškinti
    klientui, kodėl prašo kartoti."*
    """

    def test_a_reboot_reported_while_we_ask_about_reaching_is_not_asked_for_again(self, call):
        """Live: „Galiu perkrauti routerį. Tuoj perkrausiu… Perkraunu dabar routerį" — the
        engine closed only `reach` and then told them to pull the power lead."""
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)  # reach: can you get to the router
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Galiu prieiti, jau išjungiau iš elektros ir perkraunu."

        plan = case_rule.plan(state, rt)

        assert plan.rule != "case.reboot", "they said they are doing it"
        assert state.case.step >= 2, "the reboot step is behind us, not ahead"

    def test_the_lights_question_is_not_skipped_on_the_way(self, call):
        """The hypothesis stands on the lights: a jump may pass an instruction, never a
        question only the caller can answer (dead-router card, live 2026-09-30)."""
        state, rt = call
        dead = {**BASE, "device_seen": False}
        record_telemetry(state, rt, dead)
        record_client(state, rt, "has_computer", "yes")
        state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Jau įkišau laidą į kompiuterį."

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.check_lights", "the lights question comes first"
        assert state.case.step == 0

    def test_a_lights_answer_from_the_line_does_not_count_as_the_callers(self, call):
        """`check_lights` waits for `wan_link`, which telemetry also produces — and that is
        how the whole lights / power conversation was skipped on 2026-09-30."""
        from agent.decide.rules.case_rule import _client_said

        state, rt = call
        record_telemetry(state, rt, {**BASE, "device_seen": False, "wan_link": "down"})

        assert _client_said(state, "wan_link") is False, "the line said it, not the caller"

        # A fact the line cannot produce: once THEY say it, the question is answered.
        record_client(state, rt, "lights", "off")
        assert _client_said(state, "lights") is True


class TestTheDeadRouterAsksBeforeItConcludes:
    """Wave 6, from the live call of 2026-09-30.

    Andrius: *„jei nėra įrenginio, turėjo išsiaiškinti ar jis tikrai pajungtas, kaip lemputės
    dega, ir tuomet diagnozuoti routerio sugedimą… routerio gedimui nustatyti reikia lempučių
    ir ar elektra pasiekia įrenginį."*
    """

    def test_lights_off_leads_to_the_power_check_not_to_the_cable(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "device_seen": False})
        record_client(state, rt, "has_computer", "yes")
        state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
        case_rule.plan(state, rt)  # the lights question
        said(state, rt, "lights", "off")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.check_power", "power before concluding the box is dead"

    def test_the_bridge_is_offered_before_anything_is_unplugged(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "device_seen": False})
        record_client(state, rt, "has_computer", "yes")
        state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
        case_rule.plan(state, rt)
        said(state, rt, "lights", "off")
        case_rule.plan(state, rt)
        said(state, rt, "power_cable", "plugged")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.offer_bridge", "asked, not imposed"

    def test_a_refused_offer_goes_to_the_technician_without_the_cable(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "device_seen": False})
        record_client(state, rt, "has_computer", "yes")
        state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
        case_rule.plan(state, rt)
        said(state, rt, "lights", "off")
        case_rule.plan(state, rt)
        said(state, rt, "power_cable", "plugged")
        case_rule.plan(state, rt)
        said(state, rt, "bridge_agreed", "no")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.escalate", "no cable, no bind — straight to the ticket"

    def test_a_dead_router_is_a_replacement_ticket(self):
        """The technician has to know they are bringing a device, not a screwdriver."""
        from agent import ticket_types

        assert ticket_types.fault_type("no_mac_observed") == "equipment_replacement"
        assert ticket_types.fault_type("router_hung") == "fault_technician"


class TestTheWrittenFixIsOfferedNotImposed:
    """Wave 6, from the dhcp_silent call of 2026-09-30.

    Andrius: *„jei klientas sutinka, galime vesti — nes ne visi klientai supranta ir nori tai
    daryti, nereikia prievartauti"*, and *„dabar galite naršyklėje suvesti adresą… klientas
    suveda ir sako suvedžiau, agentas pasiklausia ką matote"*.
    """

    @pytest.fixture
    def silent(self, make_state, make_runtime):
        state, rt = make_state("+37060020106"), make_runtime()
        state.identity.customer_id = "CUST106"
        record_telemetry(state, rt, {**BASE, "dhcp_status": "no_requests", "traffic": "flowing"})
        state.case.facts["reachable"] = "yes"
        return state, rt

    def test_the_walk_is_offered_before_it_starts(self, silent):
        state, rt = silent

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.offer_guide"

    def test_a_refusal_goes_to_the_technician_instead_of_walking(self, silent):
        state, rt = silent
        case_rule.plan(state, rt)
        said(state, rt, "guide_agreed", "no")

        plan = case_rule.plan(state, rt)

        assert plan.rule != "case.guide", "not walked against their will"
        assert state.ticket.stage or plan.action is not None

    def test_one_action_per_turn_carries_the_documents_own_details(self, silent):
        """The address and the password are separate actions — live they were merged away and
        the model invented an address the document does not give."""
        state, rt = silent
        case_rule.plan(state, rt)
        said(state, rt, "guide_agreed", "yes")
        first = case_rule.plan(state, rt)
        state.case.guide_said = 0
        state.dialog.turn_count += 1
        state.dialog.last_heard = "padariau"
        second = case_rule.plan(state, rt)

        assert first.rule == "case.guide" and "prijungti kompiuter" in first.say.text.lower()
        assert second.rule == "case.guide" and "192.168.0.1" in second.say.text


class TestWhenTheFactsTurnTheCardWrong:
    """Wave 6 (G4), live 2026-09-28: the caller plugged a computer into the line mid-fix,
    `device_registered=foreign` landed — which `router_hung` lists in `rules_out` — and the
    engine kept rebooting a router that was no longer the device on the line."""

    def test_a_disqualifying_fact_reopens_the_case(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)  # router_hung is being worked on
        assert state.case.fault == "router_hung"

        # A different MAC on the line is what „the caller plugged their computer in" looks
        # like to telemetry (`device_registered` is derived, not reported).
        record_telemetry(state, rt, {**BASE, "observed_mac": "11:22:33:44:55:66"})
        case_rule.plan(state, rt)

        assert state.case.fault != "router_hung", "the card ruled itself out"

    def test_a_card_whose_conditions_still_hold_is_not_disturbed(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)

        case_rule.plan(state, rt)

        assert state.case.fault == "router_hung"


class TestThePowerQuestionIsAlwaysAsked:
    """Wave 6: „ar ateina elektra" is part of the diagnosis, not an optional extra.

    (The re-read of the line after a lead was found unplugged — G26 — was tried as a
    `verify` step and taken out again: a failed verification spends the whole card, so the
    caller lost the offer of a temporary line just because the router had not come back yet.
    It needs a read that does not close the card; it stays in FIX_PLAN §6.)
    """

    def _dead(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "device_seen": False})
        record_client(state, rt, "has_computer", "yes")
        state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
        case_rule.plan(state, rt)  # lights
        said(state, rt, "lights", "off")
        return state, rt

    def test_lights_off_is_followed_by_the_power_question(self, call):
        state, rt = self._dead(call)

        assert case_rule.plan(state, rt).rule == "case.check_power"

    def test_and_then_the_offer_whatever_the_power_answer_was(self, call):
        state, rt = self._dead(call)
        case_rule.plan(state, rt)
        said(state, rt, "power_cable", "unplugged")

        assert case_rule.plan(state, rt).rule == "case.offer_bridge"


class TestAStepThatKeepsBeingRepeated:
    """Wave 6 (G2): live 2026-09-28 the same reboot instruction went out six times, because
    nothing counted how often a step had been said."""

    def test_after_the_limit_the_card_gets_its_one_retry(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)
        said(state, rt, "reachable", "yes")

        rules = [case_rule.plan(state, rt).rule for _ in range(4)]

        assert rules[0] == "case.reboot"
        assert "case.retry" in rules, f"the card's own second attempt never came: {rules}"

    def test_with_nothing_left_to_try_it_ends_honestly(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "device_seen": False})
        record_client(state, rt, "has_computer", "no")
        state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0

        rules = [case_rule.plan(state, rt).rule for _ in range(5)]

        assert rules[0] == "case.check_lights"
        assert any(r.startswith("ticket.") or r == "case.escalate" for r in rules), rules


def test_a_step_given_up_on_does_not_send_the_call_back_into_itself(make_state, make_runtime):
    """Wave 6 (eval X_dhcp_silent, 2026-09-30): the repeat guard gave up on the guide, the
    escalation saw `only_after: [guide]` unfulfilled, re-entered the same branch — and the
    call spun there until the caller hung up. Giving up on a step is also a record that it
    was attempted."""
    state, rt = make_state("+37060020106"), make_runtime()
    state.identity.customer_id = "CUST106"
    record_telemetry(state, rt, {**BASE, "dhcp_status": "no_requests", "traffic": "flowing"})
    state.case.facts.update({"reachable": "yes", "guide_agreed": "yes"})

    rules = []
    for _ in range(8):
        plan = case_rule.plan(state, rt)
        rules.append(plan.rule if plan else None)
        state.dialog.turn_count += 1

    assert rules.count("case.guide") <= 4, f"the same step over and over: {rules}"
    assert any(r and (r.startswith("ticket.") or r == "case.escalate") for r in rules), rules

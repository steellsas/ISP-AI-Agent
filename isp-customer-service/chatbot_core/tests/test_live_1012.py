"""Andrius's live calls 2026-10-12 — A1..A6, with the caller's own words."""

import pytest


@pytest.mark.parametrize(
    ("said", "has"),
    [
        ("Routerį neturiu, bet kompiuterį turiu.", "yes"),  # A1: the call that lost its bridge
        ("Kompiuterį turiu, routerio neturiu", "yes"),
        ("Neturiu kito routerio, tik kompiuterį", "yes"),
        ("Ne, tik tiską telefoną. Neturiu kompiuterį.", "no"),
        ("Neturiu kompiuterio, tik telefoną", "no"),
        ("Neniauturiu kompiuterio", "no"),  # STT of „ne, neturiu"
    ],
)
def test_a1_the_computer_is_read_by_clause(said, has):
    from agent.evidence import extract_client_facts

    assert extract_client_facts(said).get("has_computer") == has


class TestA2PlugDoneWords:
    @pytest.fixture
    def plugging(self, make_state, make_runtime):
        from agent.decide.rules import case_rule
        from agent.ledger import record_client, record_telemetry

        from tests.test_case_rule import BASE, said

        state, rt = make_state("+37060020112"), make_runtime()
        state.identity.customer_id = "CUST112"
        record_telemetry(state, rt, {**BASE, "device_seen": False})
        record_client(state, rt, "reachable", "yes")
        state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
        case_rule.plan(state, rt)
        said(state, rt, "lights", "off")
        case_rule.plan(state, rt)
        said(state, rt, "power_cable", "unplugged")
        assert case_rule.plan(state, rt).rule == "case.plug_power"
        state.case.step_said = state.case.step
        return state, rt

    @pytest.mark.parametrize("heard", ["Ikišau.", "ikisau", "Įkišau"])
    def test_the_letters_asr_drops_do_not_hide_the_done(self, plugging, heard):
        from agent.decide.rules import case_rule

        state, rt = plugging
        state.dialog.turn_count += 1
        state.dialog.last_heard = heard
        plan = case_rule.plan(state, rt)

        assert plan.rule != "case.confirm"
        assert case_rule._current(state).module == "verify"

    def test_the_confirm_asks_about_the_action_only(self):
        from agent.contract.locale import phrase

        assert phrase("case.confirm.done_plug_power") == "Ar jau įkišote maitinimo laidą?"


@pytest.mark.parametrize(
    ("said", "name"),
    [
        ("Labą dieną, esu Paulius, mane veikia internetas. Vilniaus gatvė, 33", "Paulius"),
        ("Labas, čia Jonas, neveikia internetas", "Jonas"),
        ("Čia kalba Ona", "Ona"),
        ("Aš esu darbe", None),
        ("čia Vilniaus g. 29", None),
        ("Panavardos sėra gėdras.", None),
    ],
)
def test_a3_a_name_given_unasked(said, name):
    from agent.perceive.caller import introduced_name

    assert introduced_name(said) == name


def test_a3_the_name_question_is_skipped(make_state, make_runtime):
    from agent.decide.rules.reply import plan_reply

    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    state.identity.result_pending = True
    state.intake.heard_utterances = ["Labą dieną, esu Paulius, neveikia internetas"]
    plan = plan_reply(state, rt, "Taip")

    assert state.identity.caller_name == "Paulius"
    assert plan is None or plan.rule != "identification.caller_name"


def test_a4_a_garbled_name_is_asked_again_once(make_state, make_runtime):
    from agent.decide.rules.head import caller_intro
    from agent.decide.rules.reply import plan_reply

    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    state.identity.result_pending = True
    caller_intro(state, rt, "Panavardos sėra gėdras.")

    assert state.identity.caller_name is None
    plan = plan_reply(state, rt, "Panavardos sėra gėdras.")
    assert plan.rule == "identification.caller_name" and "pakartoti" in plan.say.text

    caller_intro(state, rt, "Ėėė, nu")  # still nothing readable — no third ask
    assert state.identity.caller_name == "nenurodyta"


@pytest.mark.parametrize(
    ("said", "when"),
    [
        ("Nuo 5 iki 6 vakare", "nuo 17 iki 18 val."),
        ("Rytoj, nuo 8 iki 10 valandų", "rytoj nuo 8 iki 10 val."),
        ("Bet kada galėtų skambinti darbalaikų", "darbo laiku"),
        ("po 5 vakare", "po 17 val."),
        ("nuo 12 iki 13", "nuo 12 iki 13 val."),
        ("Bet kada", "bet kada"),
    ],
)
def test_a5_the_day_and_the_evening_stay_on_the_ticket(said, when):
    from agent.decide.rules.ticket import hours_words

    assert hours_words(said) == when


def test_a5_no_double_full_stop(make_state, make_runtime):
    from agent.contract.locale import phrase

    hours = "nuo 17 iki 18 val.".rstrip(".")
    assert ".." not in phrase("identification.ticket_done", phone="+370 600 12353", hours=hours)


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("Skambinsime +370 600 12353, nuo 17 iki 18 val.", "plius 3 7 0, 6 0 0, 1 2 3 5 3"),
        ("paskambins 3455545741, bet kada.", "3 4 5, 5 5 4, 5 7 4 1"),
        ("Numeris +37060012353.", "plius 3 7 0, 6 0 0, 1 2 3 5 3"),
    ],
)
def test_a6_a_phone_number_is_dictated(text, spoken):
    from adapters.tts.sentences import speakable

    assert spoken in speakable(text)


@pytest.mark.parametrize("text", ["Skola 49 eurai 98 centai.", "Data 2026-10-12, 12:30"])
def test_a6_sums_and_dates_are_not_phones(text):
    from adapters.tts.sentences import speakable

    assert speakable(text) == text

"""STRUKTURA_V3 stage 3a — Andrius's ending rules (2026-10-09).

U3: „Ar tikrai baigti?" says what would be left undone. U6/U9: not WANTING to go on asks it;
not being ABLE to right now does not. U8: three prompts, each explaining, then an end with
the reason. U10: the confirmed end of an unfinished call is a scripted goodbye with what is
left and how to come back — and it hangs up.
"""

import pytest


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


class TestU8AccountCodeMisses:
    def test_a_code_not_found_is_capped(self, db_connection):
        from agent.contract import limits
        from agent.decide.rules.reply import scripted_words

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        agent.state.identity.account_code_mode = True
        replies = [
            scripted_words(agent.state, agent.runtime, "Mano kodas AB 99999")
            for _ in range(limits.get("account_code_miss_max") + 1)
        ]
        assert all("nerandu" in r for r in replies[:-1])
        assert "tik mūsų abonentams" in replies[-1]
        assert agent.state.closing.is_complete

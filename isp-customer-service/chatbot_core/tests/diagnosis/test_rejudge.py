"""Kortelės persvarstymas sprendimo viduryje (4 etapas, Andrius 2026-11-11): nepadėjęs veiksmas
tampa faktu (`tried_<priežastis>=failed`), o naujas svarbus faktas gali pakeisti šaką ir po
atliktų veiksmų — tai, kas jau padaryta, antrą kartą neprašoma; šaka keičiama ne daugiau 2 kartų."""

from __future__ import annotations

FUNCTION = "Kortelės persvarstymas"

# Phone branch, the Wi-Fi reconnect did not help.
RECONNECT_FAILED = [
    "Gerai",
    "Telefone neveikia",
    "Taip, galiu",
    "Įjungtas",
    "Taip, savo",
    "Padariau",
    "Ne, neveikia",
]
EVERYWHERE = "Ir kompiuteryje neveikia, visur neveikia"


def walk(c, turns):
    for text in turns:
        c.say(text)
    return c


def moves(c, name):
    return [e for e in c.of("case") if e.get("move") == name]


class TestWhatDidNotHelpIsAFact:
    def test_a_failed_fix_check_is_recorded(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), RECONNECT_FAILED)
        assert c.state.case.facts["tried_reconnect"] == "failed"
        assert c.rule == "case.device_restart"  # nothing new learned — the card goes on

    def test_the_card_may_reason_over_it(self):
        from agent.case import branch_of
        from agent.contract import cards

        card = cards.card("healthy_to_router")
        facts = {"fail_device": "phone", "fail_scope": "all", "tried_router_reboot": "failed"}
        index, fact, _ = branch_of(card, facts)
        assert fact is None and card.solution[index].steps[0].module == "escalate"
        # Without it, „visur neveikia" asks whether the router was rebooted.
        _, fact, _ = branch_of(card, {"fail_device": "phone", "fail_scope": "all"})
        assert fact == "rebooted"


class TestTheBranchIsChosenAgain:
    def test_everywhere_after_a_failed_step_goes_to_the_router(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), RECONNECT_FAILED)
        c.say(EVERYWHERE)
        assert moves(c, "rebranch") and c.state.case.facts["fail_scope"] == "all"
        assert c.rule == "case.ask" and "perkrauti router" in c.replies[-1]
        walk(c, ["Ne, neperkroviau", "Taip, galiu"])
        assert c.rule == "case.reboot"
        assert "device_restart" not in c.rules  # the phone's own ladder is left

    def test_what_was_done_is_not_asked_again(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), RECONNECT_FAILED)
        # „Visur" without an answer about the router: the phone's branch comes back, and the
        # reconnect that already failed is passed over, not asked a second time.
        walk(c, [EVERYWHERE, "Nežinau", "Nežinau"])
        done = [e.get("module") for e in moves(c, "done_before")]
        assert "wifi_reconnect" in done
        reconnects = [r for r in c.replies if "Pamiršti" in r]
        assert len(reconnects) == 1

    def test_a_card_is_rebranched_at_most_twice(self, diagnosing, monkeypatch):
        from agent.decide.rules import case_rule

        monkeypatch.setattr(case_rule, "MAX_REBRANCHES", 0)
        c = walk(diagnosing("healthy_to_router"), RECONNECT_FAILED)
        c.say(EVERYWHERE)
        assert not moves(c, "rebranch") and moves(c, "rebranch_limit")
        assert c.state.case.facts["fail_scope"] == "all"  # the fact is still recorded

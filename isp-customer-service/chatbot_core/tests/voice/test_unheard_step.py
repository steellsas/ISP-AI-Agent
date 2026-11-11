"""Balsas — žingsnis, kurio klientas neišgirdo, nėra pasakytas (klaida 2, 2026-11-11)."""

from __future__ import annotations

FUNCTION = "Neišgirstas žingsnis"


def _at_the_lights(diagnosing):
    c = diagnosing("no_mac_observed")
    # The first answer after the findings is asked twice (a known gap, diagnosis/test_phase).
    for text in ["Gerai", "Taip, galiu."]:
        c.say(text)
    reply = c.say("Taip, galiu.")
    assert c.rule == "case.check_lights"
    return c, reply


def _cut(c, reply: str, heard: int = 0) -> None:
    """The transport reports that only the first `heard` sentences finished playing."""
    from agent.delivery import _sentences

    c.session.apply_delivery(_sentences(reply), heard)


class TestTheUnheardStep:
    def test_a_cut_step_is_not_said(self, diagnosing):
        c, reply = _at_the_lights(diagnosing)
        assert c.state.case.step_said == c.state.case.step
        _cut(c, reply)
        assert c.state.case.step_said != c.state.case.step
        assert "step_unheard" in [e.get("move") for e in c.of("case")]

    def test_listening_after_an_unheard_step_is_not_an_unclear_answer(self, diagnosing):
        # Live 2026-11-10: „Klausu." → „Nesupratau, Giedri. Ar lemputė dega ar nedega?"
        c, reply = _at_the_lights(diagnosing)
        _cut(c, reply)
        again = c.say("Klausu.")
        assert "Nesupratau" not in again
        assert c.rule == "case.check_lights"
        assert c.state.case.step_said == c.state.case.step

    def test_a_heard_step_keeps_its_mark(self, diagnosing):
        c, _ = _at_the_lights(diagnosing)
        words = c.state.turn.plan["say"]["text"]
        c.session.apply_delivery([words, "Ir dar vienas sakinys."], 1)  # only the tail was cut
        assert c.state.case.step_said == c.state.case.step

    def test_an_unheard_question_is_not_counted_as_asked(self, diagnosing):
        c, reply = _at_the_lights(diagnosing)
        asks = {f: list(t) for f, t in c.state.case.asks.items()}
        _cut(c, reply)
        after = {f: list(t) for f, t in c.state.case.asks.items()}
        assert sum(map(len, after.values())) <= sum(map(len, asks.values()))

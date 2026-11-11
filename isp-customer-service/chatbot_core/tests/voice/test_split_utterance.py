"""Balsas — kliento frazė dviem dalimis: neišgirstas ėjimas atšaukiamas (2026-11-11)."""

from __future__ import annotations

FUNCTION = "Skelta frazė"


def _at_the_lights(diagnosing):
    c = diagnosing("no_mac_observed")
    for text in ["Gerai", "Taip, galiu."]:
        c.say(text)
    return c


class TestTheRewind:
    def test_a_cut_turn_is_undone_and_its_words_returned(self, diagnosing):
        c = _at_the_lights(diagnosing)
        before = c.state.model_dump(exclude={"turn"})
        c.say("Ne, palaukit")
        assert c.session.rewind_cut_turn() == "Ne, palaukit"
        assert c.state.model_dump(exclude={"turn"}) == before
        assert [e.get("done") for e in c.of("turn_rewind")] == [True]

    def test_both_pieces_are_read_as_one_turn(self, diagnosing):
        c = _at_the_lights(diagnosing)
        c.say("Taip,")
        first = c.session.rewind_cut_turn()
        c.say(f"{first} galiu.")
        assert c.rule == "case.check_lights"

    def test_only_the_last_turn_can_be_undone(self, diagnosing):
        c = _at_the_lights(diagnosing)
        c.say("Ne, palaukit")
        assert c.session.rewind_cut_turn()
        assert c.session.rewind_cut_turn() is None

    def test_a_turn_that_changed_something_is_not_undone(self, diagnosing, monkeypatch):
        c = _at_the_lights(diagnosing)
        c.say("Ne, palaukit")
        calls = c.session._current_state().tools.calls
        calls["reset_port"] = calls.get("reset_port", 0) + 1  # as if the port was reset

        monkeypatch.setattr(c.session, "_current_state", lambda: c.session._state)
        c.session._state.tools.calls.update(calls)
        assert c.session.rewind_cut_turn() is None
        assert [e.get("why") for e in c.of("turn_rewind")] == ["acted"]

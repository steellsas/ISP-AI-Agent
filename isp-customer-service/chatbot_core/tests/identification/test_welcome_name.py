"""The welcome by name (#58, #30): said with the result the name unlocked, or not at all —
left to a later reply, the model said „Malonu, Tomai!" after the debt news."""

from __future__ import annotations

import pytest

FUNCTION = "Pasisveikinimas vardu"


@pytest.mark.parametrize(
    "name, called",
    [
        ("Tomas", "Tomai"),
        ("Paulius", "Pauliau"),
        ("Giedrius", "Giedriau"),
        ("Kęstutis", "Kęstuti"),
        ("Agnė", "Agne"),
        ("Lina", "Lina"),
        ("Aldona", "Aldona"),
    ],
)
def test_the_vocative_of_a_first_name(name, called):
    from agent.locales.lt.lang import vocative

    assert vocative(name) == called


class TestTheResultOpensWithTheWelcome:
    def test_just_named_the_result_says_malonu(self, make_state):
        from agent.decide.rules.reply import _thanks

        state = make_state()
        state.identity.caller_name = "Tomas"
        state.identity.caller_name_heard = True
        state.identity.caller_name_heard_turn = state.dialog.turn_count
        assert _thanks(state) == "Malonu, Tomai!"
        # Said once, here: no later reply welcomes again.
        assert state.identity.caller_name_heard is False
        assert _thanks(state) == "Ačiū!"

    def test_no_name_no_welcome(self, make_state):
        from agent.decide.rules.reply import _thanks

        state = make_state()
        state.identity.caller_name = "nenurodyta"
        state.identity.caller_name_heard = True
        assert _thanks(state) == "Ačiū!"

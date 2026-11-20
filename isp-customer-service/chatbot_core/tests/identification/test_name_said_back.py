"""Vardas pakartojamas (#78 — live 2026-11-20): every heard name is said back — „Išgirdau —
Roma. Ar teisingai?" — and corrected there. The holder's name is never put in the caller's
mouth, a refusal is a refusal, and the welcome comes in the turn the name is settled.
"""

FUNCTION = "Vardas pakartojamas"

TOMAS = "+37060020101"  # CUST101 — the holder is Tomas
RASA = "+37060020102"  # CUST102 — the holder is Rasa


def _named(call, phone, name):
    c = call(phone)
    c.say("Neveikia internetas")
    c.say("Taip")
    return c, c.say(name)


def test_another_name_is_said_back_as_heard_not_as_the_holders(call):
    """Call 0005: „Roma" became „Tomas" and the caller heard „Malonu, Tomai!"."""
    c, said = _named(call, TOMAS, "Roma")
    assert c.identity.caller_name == "Roma"
    assert "Roma" in said and "Tom" not in said
    assert c.rule == "identification.name_confirm"


def test_a_garbled_name_is_not_snapped_to_the_holder(call):
    """Call 0006: „D. Darasa" became the holder's „Rasa" without a word."""
    c, said = _named(call, RASA, "D. Darasa")
    assert c.identity.caller_name != "Rasa"
    assert "Rasa" not in said.replace("Darasa", "")


def test_the_holders_name_garbled_takes_its_spelling(call):
    c, said = _named(call, TOMAS, "Tomus")
    assert c.identity.caller_name == "Tomas" and "Tomas" in said


def test_the_caller_corrects_the_heard_name(call):
    c, _ = _named(call, RASA, "D. Darasa")
    c.say("Ne, mano vardas Rasa")
    assert c.identity.caller_name == "Rasa"
    assert not c.identity.holder_clarify_open  # it is the holder's — nothing more to ask


def test_a_bare_no_asks_the_name_again(call):
    c, _ = _named(call, TOMAS, "Roma")
    c.say("Ne")
    assert c.identity.caller_name is None


def test_a_refusal_is_not_a_name(call):
    """Call 0008: „Nezakyso." („nesakysiu") became the name „Nezakysiu"."""
    c, said = _named(call, TOMAS, "Nezakyso.")
    assert c.identity.caller_name == "nenurodyta"
    c2, _ = _named(call, TOMAS, "Petras")
    c2.say("Ne, aš tiesiog nesakysiu, mano vardas ne toks.")
    assert c2.identity.caller_name == "nenurodyta"


def test_a_yes_with_a_stray_word_confirms(call):
    """Call 0010: „Taip. Visingai žiūrėtum." renamed Tomas to „Visingai"."""
    c, _ = _named(call, TOMAS, "Tomas")
    c.say("Taip. Visingai žiūrėtum.")
    assert c.identity.caller_name == "Tomas"


def test_the_welcome_belongs_to_its_turn(make_state):
    """A welcome left unsaid in its turn is not said later (call 0005: „Malonu, Tomai!" at the
    ticket, minutes after the name)."""
    from agent.decide.rules.head import mark_name_heard, name_welcome_due
    from agent.decide.rules.reply import _thanks

    state = make_state()
    state.identity.caller_name = "Tomas"
    mark_name_heard(state)
    assert name_welcome_due(state)
    state.dialog.turn_count += 1
    assert not name_welcome_due(state)
    assert _thanks(state) == "Ačiū!"

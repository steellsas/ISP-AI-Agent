"""„Ar galite prieiti?" (live 2026-11-24, Paulius — router_hung): „Lidu." became „cannot now"
(„Kada galėsite — šiandien ar vėliau?"), „Šiandien galiu dabar…" got the homework for later,
and „…jau prie routera" got „Ar jūs jau prie routerio?". „Galiu" about NOW is a yes, and the
instruction follows at once; a garble is asked again, not guessed.
"""

import pytest

FUNCTION = "Ar galite prieiti"

PAULIUS = "+37060020112"  # CUST112 — router_hung


@pytest.mark.parametrize(
    ("said", "reading"),
    [
        ("Galiu prieiti.", "yes"),
        ("Gerai, pabandu, galiu prieiti.", "yes"),
        ("Šiandien galiu dabar to priėjusiu.", "yes"),
        ("Pri jau prie routera, tu įsakot maitinimo laidą ištraukti.", "yes"),
        ("Galio.", "yes"),
        ("Galiu vėliau, vakare.", None),
        ("Negaliu dabar.", "not yes"),
        ("Ne prie routerio dabar.", "not yes"),
        ("Palaukit, einu prie routerio.", None),
    ],
)
def test_the_answer_is_read(said, reading):
    from agent.perceive.detectors import detect_reach

    if reading == "not yes":
        assert detect_reach(said) != "yes"  # „cannot now" is read by its own detector
    else:
        assert detect_reach(said) == reading


def _at_the_reach_question(call):
    c = call(PAULIUS)
    c.say("Neveikia internetas")
    c.say("Taip")
    c.say("Paulius")
    c.say("Taip")
    assert c.state.case.awaiting == "reachable"
    return c


@pytest.mark.parametrize("said", ["Galiu prieiti.", "Jau prie routera."])
def test_can_gets_the_instruction_at_once(call, said):
    c = _at_the_reach_question(call)
    c.say(said)
    assert c.rule != "case.confirm" and c.state.case.facts.get("reachable") == "yes"
    assert c.rule == "case.reboot", c.rule


def test_now_after_the_when_question_is_the_instruction(call):
    c = _at_the_reach_question(call)
    c.say("Negaliu dabar.")
    assert c.rule == "case.ask_when"
    c.say("Šiandien galiu dabar prieiti.")
    assert c.rule == "case.reboot", c.rule


def test_a_garble_is_not_read_as_cannot(call):
    """„Lidu." — the model's „not now" on two unknown words is not taken."""
    from agent.decide.rules.case_rule import _hear_cannot_now

    c = _at_the_reach_question(call)
    c.state.dialog.last_heard = "Lidu."
    c.state.turn.reply_status = "not_now"
    assert not _hear_cannot_now(c.state, c.session.rt if hasattr(c.session, "rt") else None)


def test_a_garble_the_model_reads_is_asked_again(call, monkeypatch):
    """„Lidu." read by the model as „yes" — not „Ar jūs jau prie routerio?", the question again."""
    from agent.decide.rules import case_rule

    c = _at_the_reach_question(call)
    monkeypatch.setattr(case_rule, "_model_read", lambda *a: ("reachable", "yes"))
    said = c.say("Lidu.")
    assert said == "Atsiprašau, ar galite dabar prieiti prie routerio?"
    assert "reachable" not in c.state.case.facts
    monkeypatch.undo()
    c.say("Taip, galiu.")
    assert c.rule == "case.reboot"

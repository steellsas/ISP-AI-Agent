"""Baigiamasis klausimas — „Ar dar kuo galiu padėti?" and what the caller's answer does (the
call-ending rule, PERZIURA §7): a farewell, a „ne" or silence ends the call with a goodbye;
anything that means "there is more" keeps it open. Mid-fix a goodbye is confirmed first.
"""

import pytest

FUNCTION = "Baigiamasis klausimas"

CLOSING_Q = "Puiku, internetas vėl veikia. Ar dar kuo galiu padėti?"
FIXED = ["Gerai", "Taip, galiu prieiti", "Taip, galiu prieiti", "Perkroviau"]


def _after_the_fix(diagnosing):
    c = diagnosing("router_hung")
    for text in FIXED:
        c.say(text)
    c.say("Taip, veikia", llm=CLOSING_Q)  # the conclusion ends with the closing question
    return c


AFTER_A_FIX = [
    pytest.param("Ne, ačiū", True, id="ne, ačiū → atsisveikina"),
    pytest.param("Ne", True, id="ne → atsisveikina"),
    pytest.param("Viso gero", True, id="viso gero → atsisveikina"),
    pytest.param("Ne, viskas gerai, ačiū", True, id="viskas gerai → atsisveikina"),
    pytest.param("O kiek kainuoja greitesnis planas?", False, id="klausimas → atsako"),
    pytest.param(
        "Taip, turiu dar klausimą",
        False,
        id="taip, dar klausimas → klauso",
        marks=pytest.mark.xfail(
            strict=True, reason="„taip, turiu dar klausimą“ po sutvarkymo baigia pokalbį"
        ),
    ),
]


@pytest.mark.parametrize(("said", "ends"), AFTER_A_FIX)
def test_the_answer_after_a_fix(diagnosing, said, ends):
    """Atsakymas į baigiamąjį klausimą po sutvarkymo"""
    c = _after_the_fix(diagnosing)
    reply = c.say(said)
    assert c.session.is_complete is ends
    if ends:
        assert "Geros dienos" in reply


AFTER_THE_NEWS = [
    pytest.param("Ne, ačiū", True, id="ne, ačiū → atsisveikina"),
    pytest.param("Viso gero", True, id="viso gero → atsisveikina"),
    pytest.param("Ačiū, viskas", True, id="ačiū, viskas → atsisveikina"),
    pytest.param("Taip, turiu dar klausimą", False, id="taip, dar klausimas → klauso"),
    pytest.param("O kiek kainuoja greitesnis planas?", False, id="klausimas → atsako"),
    pytest.param(
        "Ne",
        True,
        id="ne → atsisveikina",
        marks=pytest.mark.xfail(strict=True, reason="po žinios „ne“ pokalbio nebaigia"),
    ),
]


@pytest.mark.parametrize(("said", "ends"), AFTER_THE_NEWS)
def test_the_answer_after_the_news(diagnosing, said, ends):
    """Atsakymas į baigiamąjį klausimą po žinios (skola)"""
    c = diagnosing("billing_suspended")
    told = c.say("Gerai")
    assert "Ar dar kuo galiu padėti" in told or "kuo" in told.lower()
    c.say(said)
    assert c.session.is_complete is ends


def test_silence_after_the_closing_question_says_goodbye(diagnosing):
    """Tyla po baigiamojo klausimo — atsisveikina ir baigia"""
    c = diagnosing("billing_suspended")
    c.say("Gerai")
    words = c.session.close_on_silence()
    assert c.session.is_complete and "Geros dienos" in words


@pytest.mark.parametrize("said", ["Viso gero", "Ne, ačiū", "Ačiū, viskas"])
def test_a_goodbye_mid_fix_is_confirmed_first(diagnosing, said):
    """Atsisveikinimas vidury taisymo — pirma pasitikslina"""
    c = diagnosing("router_hung")
    for text in FIXED[:3]:
        c.say(text)
    reply = c.say(said)
    assert c.rule == "dialog.confirm_end" and "Ar tikrai norite baigti pokalbį" in reply
    assert not c.session.is_complete

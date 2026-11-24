"""Meistras iš karto (#86 — live 2026-11-23): „Negaliu, nenamos. Atvažiuokit, sutvarkykit" got
„Kada galėsite prieiti — šiandien ar vėliau?", then „nenoriu nieko spręsti" got „Ar tikrai
norite baigti pokalbį?". Away and asking — the technician is registered; after the one offer to
try together, a refusal answers that offer.
"""

import pytest

FUNCTION = "Meistras iš karto"

GIEDRIUS = "+37060012353"  # CUST009 — the dead router


@pytest.mark.parametrize(
    ("said", "reading"),
    [
        ("Negaliu, nenamos. Atvažiuokit, sutvarkykit man tą gedimą.", "demand"),
        ("Atvažiuokit, sutvarkykit.", "demand"),
        ("Atsiųskite meistrą.", "demand"),
        ("Nereikia registruoti", None),
        ("Nenoriu registruoti", None),
    ],
)
def test_the_request_is_read(said, reading):
    from agent.perceive.detectors import detect_refuse_or_ticket

    assert detect_refuse_or_ticket(said) == reading


def _at_the_reach_question(call):
    c = call(GIEDRIUS)
    c.say("Neveikia internetas")
    c.say("Taip")
    c.say("Giedrius")
    c.say("Taip")
    assert c.state.case.awaiting == "reachable"  # „Ar galite dabar prieiti prie routerio?"
    return c


def _away(call):
    c = _at_the_reach_question(call)
    said = c.say("Negaliu, nenamos. Atvažiuokit, sutvarkykit man tą gedimą. Ačiū.")
    # Andrius (2026-11-23): not registered at the first word — what it costs, and once the offer.
    assert c.rule == "case.away_offer" and "Ar vis tiek registruoti meistrą?" in said
    assert c.state.ticket.stage is None
    return c


def test_away_and_still_asking_registers(call):
    c = _away(call)
    c.say("Taip, registruokit.")
    assert c.rule == "case.summary"  # the conclusion, then the registration
    assert {"module": "check_lights", "how": "cant"} in c.state.case.declined  # „negalėjote"
    c.say("Gerai")
    assert c.state.ticket.stage == "phone"


def test_away_and_calling_back_is_the_callback(call):
    c = _away(call)
    c.say("Gerai, paskambinsiu, kai grįšiu.")
    assert c.rule == "case.later_agreed" and c.state.ticket.stage is None


def test_away_and_unclear_is_asked_once(call):
    c = _away(call)
    said = c.say("Hmm, nežinau.")
    assert "registruoti meistrą, ar paskambinsite" in said
    c.say("Na.")
    assert c.rule == "case.summary"


def test_after_the_offer_a_refusal_is_no_end_of_the_call(call):
    c = _at_the_reach_question(call)
    c.say("Atvažiuokit, sutvarkykit.")
    assert c.rule == "case.phone_work_offer"
    assert "jis dar paskambins" in c.state.messages[-1]["content"]
    c.say("Šiandien aš prie routerio, bet aš nenoriu nieko spręsti.")
    assert "dialog.confirm_end" not in c.rules
    assert c.state.case.summarised or c.state.ticket.stage


@pytest.mark.parametrize(
    "said",
    [
        "O jūs galite atvažiuoti ir sutvarkyti? Aš nesuprantu čia nieko.",
        "Gal atvažiuotumėt?",
        "Kada atvažiuosit?",
    ],
)
def test_asking_them_to_come_is_a_request(said):
    """Live 2026-11-24: the question form went to the LLM („registruoju tik jei nepavyks")."""
    from agent.perceive.detectors import detect_refuse_or_ticket

    assert detect_refuse_or_ticket(said) == "demand"


def test_asking_them_to_come_at_the_reach_question_is_the_engines_offer(call):
    c = _at_the_reach_question(call)
    c.say("O jūs galite atvažiuoti ir sutvarkyti? Aš nesuprantu čia nieko.")
    assert c.rule == "case.phone_work_offer"


def test_yes_with_can_reach_goes_past_the_reach_question(call):
    """„Gerai, pabandom, galiu prieiti" — both answers in one (replay 2026-11-24)."""
    c = _at_the_reach_question(call)
    c.say("O jūs galite atvažiuoti ir sutvarkyti?")
    assert c.rule == "case.phone_work_offer"
    c.say("Gerai, pabandom, galiu prieiti.")
    assert c.rule != "case.last_chance" and c.state.case.facts.get("reachable") == "yes"
    assert c.rule == "case.check_lights", c.rule

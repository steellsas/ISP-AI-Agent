"""Tiltas prieš meistrą (live 2026-11-24): the router was dead, the caller asked for a
technician after the power check, and heard „telefonu daugiau nieko nepadarysim" — the card's
temporary internet over a computer was never offered. The card's `escalate.offer_before` is
offered once; the technician is registered whatever the answer.
"""

FUNCTION = "Tiltas prieš meistrą"

GIEDRIUS = "+37060012353"  # CUST009 — the dead router


def _power_checked(call):
    c = call(GIEDRIUS)
    c.say("Neveikia internetas")
    c.say("Taip")
    c.say("Giedrius")
    c.say("Taip")
    c.say("Taip, galiu prieiti.")
    c.say("Nedega nė viena lemputė.")
    assert c.state.case.awaiting == "power_cable"
    return c


def _technician_wanted(call):
    c = _power_checked(call)
    c.say("Laidas tvirtai įkištas, rozetė veikia. Registruokit meistrą.")
    assert c.rule == "case.offer_bridge"  # „…Kol jis atvyks, galiu laikinai paleisti internetą"
    assert any(e.get("move") == "offer_before_technician" for e in c.of("case"))
    assert c.state.ticket.stage is None and not c.state.case.summarised
    return c


def test_the_bridge_is_offered_before_the_technician(call):
    _technician_wanted(call)


def test_no_computer_registers_for_the_callers_reason(call):
    c = _technician_wanted(call)
    c.say("Ne, kompiuterio neturiu.")
    assert c.state.case.summarised
    c.say("Gerai")
    assert c.state.ticket.stage == "phone" and c.state.ticket.reason == "klientas_praso"


def test_registering_again_is_not_offered_twice(call):
    c = _technician_wanted(call)
    c.say("Ne, tiesiog registruokit meistrą.")
    assert c.state.case.summarised and "case.offer_bridge" not in c.rules[-1:]


def test_yes_walks_the_bridge(call):
    c = _technician_wanted(call)
    c.say("Taip, turiu kompiuterį.")
    assert c.state.ticket.stage is None and not c.state.case.summarised
    assert c.rule in ("case.connect_direct", "case.step"), c.rule


def test_the_offer_answered_technician_gets_the_bridge_first(call):
    """The live path: „Ar norite meistro, ar dar pabandome?" came BEFORE the card's own bridge
    step — „Noriu meistro" must still hear the bridge offer."""
    c = _power_checked(call)
    c.state.case.technician_offer = "asked"
    c.say("Laidas įkištas. Noriu, kad užregistruotumėte meistrą.")
    assert c.rule == "case.offer_bridge", c.rules[-3:]

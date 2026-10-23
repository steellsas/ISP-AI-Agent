"""Atsakymai žingsniuose — at each step of a card, what the caller says and what the engine does
next, through the whole turn (all the readers, the Case, the step bookkeeping; the speaking
LLM faked, the model's read off).

A row: the step (reached by a short path from the findings), the caller's words, the rule of
the agent's next turn. The path gives the first answer after the findings twice (see the known
gap in test_phase.py).
"""

import pytest

FUNCTION = "Atsakymai žingsniuose"

FIRST = "Taip, galiu."
STEPS = {
    "reach": ("no_mac_observed", ["Gerai", FIRST]),
    "lights": ("no_mac_observed", ["Gerai", FIRST, FIRST]),
    "power": ("no_mac_observed", ["Gerai", FIRST, FIRST, "Nedega nė viena"]),
    "bridge": (
        "no_mac_observed",
        ["Gerai", FIRST, FIRST, "Nedega nė viena", "Maitinimo laidas įkištas tvirtai."],
    ),
    "reboot": ("router_hung", ["Gerai", "Taip, galiu prieiti", "Taip, galiu prieiti"]),
    "verify": (
        "router_hung",
        ["Gerai", "Taip, galiu prieiti", "Taip, galiu prieiti", "Perkroviau"],
    ),
    "when": ("router_hung", ["Gerai", "Taip, galiu prieiti", "Ne, nesu namie"]),
    "homework": ("router_hung", ["Gerai", "Taip, galiu prieiti", "Ne, nesu namie", "Vakare"]),
    "panel": ("dhcp_silent", ["Gerai", "Turiu telefoną."]),
    "guide_offer": ("dhcp_silent", ["Gerai", "Turiu telefoną.", "Turiu telefoną."]),
}
ASKED = {  # the rule of the turn that asked the step's question
    "reach": "case.reach",
    "lights": "case.check_lights",
    "power": "case.check_power",
    "bridge": "case.offer_bridge",
    "reboot": "case.reboot",
    "verify": "case.verify",
    "when": "case.ask_when",
    "homework": "case.homework",
    "panel": "case.panel_device",
    "guide_offer": "case.offer_guide",
}


def gap(step, said, then, label, why):
    return pytest.param(
        step, said, then, id=label, marks=pytest.mark.xfail(strict=True, reason=why)
    )


ANSWERS = [
    # Ar galite prieiti prie routerio?
    pytest.param("reach", "Taip, galiu.", "case.check_lights", id="prieiti: taip, galiu"),
    pytest.param(
        "reach", "Esu prie routerio", "case.check_lights", id="prieiti: esu prie routerio"
    ),
    pytest.param("reach", "Ne, nesu namie", "case.ask_when", id="prieiti: nesu namie → kada?"),
    pytest.param("reach", "Negaliu dabar", "case.ask_when", id="prieiti: negaliu dabar → kada?"),
    gap(
        "reach",
        "Galiu, tuoj nueisiu",
        "case.check_lights",
        "prieiti: galiu, tuoj nueisiu",
        "neperskaitoma — klausimas kartojamas",
    ),
    # Ar dega lemputės?
    pytest.param("lights", "Nedega nė viena", "case.check_power", id="lemputės: nedega nė viena"),
    pytest.param("lights", "Nedega", "case.check_power", id="lemputės: nedega"),
    pytest.param("lights", "Ne", "case.check_power", id="lemputės: ne"),
    # Ar maitinimo laidas įkištas?
    pytest.param("power", "Taip, įkištas", "case.offer_bridge", id="maitinimas: taip, įkištas"),
    pytest.param("power", "Įkištas", "case.offer_bridge", id="maitinimas: įkištas"),
    pytest.param("power", "Taip", "case.offer_bridge", id="maitinimas: taip"),
    pytest.param(
        "power", "Ištrauktas buvo", "case.plug_power", id="maitinimas: buvo ištrauktas → įkišti"
    ),
    pytest.param("power", "Ne", "case.plug_power", id="maitinimas: ne → įkišti"),
    gap(
        "power",
        "Įjungtas",
        "case.offer_bridge",
        "maitinimas: įjungtas",
        "„įjungtas“ neperskaitomas — klausimas kartojamas",
    ),
    gap(
        "power",
        "Įkišau dabar",
        "case.verify",
        "maitinimas: įkišau dabar",
        "„įkišau dabar“ neperskaitomas — klausimas kartojamas",
    ),
    # Ar turite kompiuterį (laikinas internetas)?
    pytest.param("bridge", "Neturiu.", "case.summary", id="tiltas: neturiu → išvada"),
    pytest.param(
        "bridge", "Tik telefoną turiu", "case.summary", id="tiltas: tik telefonas → išvada"
    ),
    pytest.param(
        "bridge", "Registruokit meistrą.", "case.summary", id="tiltas: registruokit → išvada"
    ),
    pytest.param(
        "bridge",
        "Taip, turiu kompiuterį.",
        "case.connect_direct",
        id="tiltas: turiu kompiuterį → jungti",
    ),
    pytest.param("bridge", "Gerai", "case.connect_direct", id="tiltas: gerai → jungti"),
    # Perkraukite routerį iš maitinimo.
    pytest.param("reboot", "Perkroviau", "case.verify", id="perkrovimas: perkroviau"),
    pytest.param(
        "reboot", "Išjungiau ir įjungiau", "case.verify", id="perkrovimas: išjungiau ir įjungiau"
    ),
    pytest.param(
        "reboot", "Ištraukiau ir įkišau", "case.verify", id="perkrovimas: ištraukiau ir įkišau"
    ),
    pytest.param("reboot", "Padariau", "case.verify", id="perkrovimas: padariau"),
    pytest.param("reboot", "Palaukite", "case.reboot", id="perkrovimas: palaukite → laukia"),
    pytest.param(
        "reboot", "Negaliu, nesu namie", "case.ask_when", id="perkrovimas: nesu namie → kada?"
    ),
    gap(
        "reboot",
        "Dar ne",
        "case.reboot",
        "perkrovimas: dar ne",
        "„dar ne“ laikomas atliktu — pereinama prie patikros",
    ),
    # Ar internetas veikia?
    pytest.param("verify", "Taip, veikia", "case.resolved", id="patikra: taip, veikia"),
    pytest.param("verify", "Veikia", "case.resolved", id="patikra: veikia"),
    pytest.param("verify", "Atsirado", "case.resolved", id="patikra: atsirado"),
    pytest.param("verify", "Taip", "case.resolved", id="patikra: taip"),
    pytest.param("verify", "Neveikia", "case.reboot", id="patikra: neveikia → dar kartą"),
    pytest.param("verify", "Vis dar ne", "case.reboot", id="patikra: vis dar ne → dar kartą"),
    pytest.param("verify", "Dar kraunasi", "case.verify", id="patikra: dar kraunasi → laukia"),
    # Kada galėsite prieiti?  /  Namų darbas: kai grįšite — perkraukite. Gerai?
    pytest.param("when", "Vakare", "case.homework", id="kada: vakare → namų darbas"),
    pytest.param("when", "Šiandien vakare grįšiu", "case.homework", id="kada: šiandien vakare"),
    pytest.param("homework", "Gerai", "case.later_agreed", id="namų darbas: gerai → perskambins"),
    # Ar turite telefoną ar kompiuterį nustatymams?  /  Pabandom kartu?
    pytest.param("panel", "Turiu telefoną.", "case.offer_guide", id="nustatymams: telefonas"),
    pytest.param("panel", "Kompiuterį turiu.", "case.offer_guide", id="nustatymams: kompiuteris"),
    pytest.param("panel", "Neturiu nieko.", "case.summary", id="nustatymams: nieko → išvada"),
    pytest.param("guide_offer", "Pabandykim kartu.", "case.guide", id="vedimas: pabandykim"),
    pytest.param("guide_offer", "Gerai", "case.guide", id="vedimas: gerai"),
    pytest.param(
        "guide_offer", "Ne, geriau meistrą", "case.summary", id="vedimas: geriau meistrą → išvada"
    ),
]


@pytest.mark.parametrize(("step", "said", "then"), ANSWERS)
def test_the_answer_moves_the_step(diagnosing, step, said, then):
    """Atsakymas → kitas žingsnis"""
    card, path = STEPS[step]
    c = diagnosing(card)
    for text in path:
        c.say(text)
    assert c.rule == ASKED[step], "the path no longer reaches the step"
    c.say(said)
    assert c.rule == then


@pytest.mark.parametrize(
    ("said", "value"),
    [
        pytest.param("Dega žalia", "on", id="dega"),
        pytest.param("Mirksi raudonai", "blinking", id="mirksi"),
        pytest.param("Nedega nė viena", "off", id="nedega"),
    ],
)
def test_the_lights_are_recorded(diagnosing, said, value):
    """Lemputės užrašomos kaip faktas"""
    card, path = STEPS["lights"]
    c = diagnosing(card)
    for text in path:
        c.say(text)
    c.say(said)
    assert {e["key"]: e["value"] for e in c.of("evidence")}.get("lights") == value


@pytest.mark.xfail(
    strict=True,
    reason="degančios lemputės kortelę turi atmesti, bet Case lieka prie „įrenginio nematyti“",
)
def test_lights_on_rule_out_a_dead_router(diagnosing):
    """Lemputės dega — tai ne miręs routeris"""
    card, path = STEPS["lights"]
    c = diagnosing(card)
    for text in path:
        c.say(text)
    c.say("Dega žalia")
    assert c.state.case.fault != "no_mac_observed"


@pytest.mark.xfail(
    strict=True, reason="„Nežinau kada“ laikomas klausimu modeliui, ne „nežino kada“"
)
def test_cannot_say_when_is_heard(diagnosing):
    """„Nežinau kada“ — nežino, kada galės"""
    card, path = STEPS["when"]
    c = diagnosing(card)
    for text in path:
        c.say(text)
    c.say("Nežinau kada")
    assert "cannot_say_when" in [e.get("move") for e in c.of("case")]


REBOOTED = ["Gerai", "Taip, galiu prieiti", "Taip, galiu prieiti", "Perkroviau"]


def test_a_reboot_the_line_did_not_see_is_asked_again(diagnosing, monkeypatch):
    """Telemetrija nematė perkrovimo — prašoma perkrauti dar kartą"""
    c = diagnosing("router_hung")
    monkeypatch.setenv("SIMULATE_REBOOT", "off")  # the line shows no flap
    for text in REBOOTED:
        c.say(text)
    assert c.rule == "case.reboot" and "retry" in [e.get("move") for e in c.of("case")]


def test_a_reboot_that_never_helped_goes_to_a_ticket(diagnosing, monkeypatch):
    """Perkrovimas nepadėjo — išvada ir tiketas"""
    c = diagnosing("router_hung")
    monkeypatch.setenv("SIMULATE_REBOOT", "off")
    for text in [*REBOOTED, "Neveikia", "Perkroviau"]:
        c.say(text)
    assert (
        c.rule == "ticket.phone_intro"
        and "routeris perkrautas, bet ryšys neatsistatė" in c.replies[-1]
    )


def test_a_fix_that_failed_twice_reopens_the_case(diagnosing):
    """Sprendimas nepadėjo du kartus — ieškoma kitos kortelės"""
    c = diagnosing("router_hung")
    for text in [*REBOOTED, "Neveikia", "Perkroviau", "Neveikia"]:
        c.say(text)
    assert "fix_failed" in [e.get("move") for e in c.of("case")]
    assert c.rule == "case.ask"  # the Case learns what may fit instead

"""Gyvai 2026-11-24 16:10 (Giedrius, sugedęs routeris):
- „Ne, dėkaurių vienalio lemputę." — the model read „dega", the engine „nedega"; every next
  turn mirrored the model's „dega" back over the engine's reading;
- „Gatvėje. Nežinau, galiu pabandyti." to „meistrą ar pabandome kartu?" was asked again.
"""

import pytest

FUNCTION = "Gyvi skambučiai 11-24 (2)"


def test_the_engines_reading_is_not_mirrored_back(make_state, make_runtime):
    from agent.evidence import CLIENT, set_fact
    from agent.ledger import mirror_evidence, record_client

    state, rt = make_state("+37060012353"), make_runtime()
    set_fact(state.diagnosis.evidence, "lights", "on", CLIENT, 1)  # the model's misreading
    mirror_evidence(state, rt)
    record_client(state, rt, "lights", "off")  # the engine's own reader, the same turn
    mirror_evidence(state, rt)  # the next turn
    assert state.case.facts["lights"] == "off"
    assert state.diagnosis.evidence["lights"]["value"] == "off"


@pytest.mark.parametrize(
    ("said", "choice"),
    [
        ("Gatvėje. Nežinau, galiu pabandyti.", "try"),
        ("Pabandysim kartu", "try"),
        ("Nenoriu bandyti, registruokit meistrą", "technician"),
    ],
)
def test_try_or_technician(said, choice):
    from agent.decide.rules.case_rule import technician_choice

    assert technician_choice(said) == choice


class _Tracer:
    session_id = "B"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


def test_an_inferred_wish_does_not_cut_off_the_bridge_offer(make_state, make_runtime):
    """Replay of the 16:10 call: the analyst's „atvažiuokit" from the opening came while the
    bridge offer was out, and „Ar norite meistro, ar pabandome kartu?" took its place."""
    from agent.analyst.node import _wants_technician
    from agent.analyst.signals import Signal
    from agent.contract import cards as catalog
    from agent.decide.rules import case_rule
    from agent.ledger import record_client, record_telemetry

    from tests.diagnosis.test_facts import BASE

    tracer = _Tracer()
    state, rt = make_state("+37060020112"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST112"
    record_telemetry(state, rt, {**BASE, "device_seen": False})
    for fact, value in (("reachable", "yes"), ("lights", "off"), ("power_cable", "plugged")):
        record_client(state, rt, fact, value)
    steps = catalog.card("no_mac_observed").solution[0].steps
    bridge = next(i for i, c in enumerate(steps) if c.module == "offer_bridge")
    state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, bridge
    state.case.did += ["reach", "check_lights", "check_power"]
    case_rule.plan(state, rt)  # the bridge offer
    state.case.step_said = state.case.step

    _wants_technician(state, rt, Signal(type="wants_technician", confidence=1.0, turn_index=9))
    state.dialog.turn_count += 1
    state.dialog.last_heard = "Gatvėje. Nežinau."
    plan = case_rule.plan(state, rt)

    assert plan is None or plan.rule != "case.technician_offer"
    assert any(e.get("move") == "technician_offer_moot" for e in tracer.events)

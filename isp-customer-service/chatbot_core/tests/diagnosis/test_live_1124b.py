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

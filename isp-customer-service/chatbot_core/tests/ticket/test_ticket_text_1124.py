"""Tiketo tekstas (live 2026-11-24, TKT03CEC34E): „Telefonu nespėta patikrinti: routerio
maitinimas, maitinimo laido įkišimas", though the caller had answered both; „Papildomai
patikrinti: None: „Antipinternatoriai kioto.""; „ar gali dabar prieiti prie įrenginio: turite".
"""

from types import SimpleNamespace

FUNCTION = "Tiketo tekstas"


def _state(**case):
    base = {
        "fault": "no_mac_observed",
        "solution": 0,
        "step": 2,
        "worked": [],
        "did": ["reach", "check_lights"],
        "facts": {},
        "said": [],
    }
    base.update(case)
    return SimpleNamespace(case=SimpleNamespace(**base))


def test_an_answered_check_is_not_unreached():
    from agent.executor_flow import _steps_not_reached

    s = _state(
        facts={"power_cable": "plugged", "outlet_works": "tried"},
        said=["power_cable", "outlet_works"],
    )
    assert not any("maitinim" in n for n in _steps_not_reached(s))


def test_an_unanswered_check_still_is():
    from agent.executor_flow import _steps_not_reached

    assert any("maitinim" in n for n in _steps_not_reached(_state()))


def test_a_garbled_side_complaint_stays_out():
    from agent.executor_flow import _extra_item

    assert _extra_item({"type": None, "text": "Antipinternatoriai kioto."}) is None
    said = _extra_item({"type": None, "text": "Dar ir televizorius nerodo"})
    assert said and "None" not in said
    assert "tv" in _extra_item({"type": "tv", "text": "TV nerodo"})


def test_reachable_reads_as_able():
    from agent.evidence import gloss_value

    assert gloss_value("yes", "reachable") == "gali prieiti"

"""Tiketo priežastis (live 2026-11-24, TKT3EFB3287): the ticket said „Gedimas: dingo internetas —
linijoje nematoma jokio įrenginio", then „routerio lemputės: dega" (the caller had said none
was on), „restored: turite", „wan_link: down", „laidas įkištas" next to „maitinimo laidas
įkištas". Andrius: the ticket says the main cause, why we think so, and what was done.
"""

from types import SimpleNamespace

FUNCTION = "Tiketo priežastis"

DEAD_ROUTER = {
    "node_reachable": "yes",
    "line_link": "up",
    "device_seen": "yes",  # the bridged computer
    "traffic": "flowing",
    "lights": "off",
    "power_cable": "plugged",
    "cable_seated": "yes",
    "outlet_works": "tried",
    "wan_link": "down",
    "has_computer": "yes",
    "bridge_agreed": "yes",
    "restored": "yes",
    "reachable": "yes",
}


def _state(facts=DEAD_ROUTER, evidence=None):
    said = [k for k in facts if k not in ("node_reachable", "line_link", "device_seen")]
    return SimpleNamespace(
        case=SimpleNamespace(fault="no_mac_observed", facts=dict(facts), said=said),
        diagnosis=SimpleNamespace(evidence=evidence or {}),
    )


def test_the_cause_and_why():
    from agent.executor_flow import _card_reading

    found, because, _ = _card_reading(_state())
    assert found.startswith("sugedęs routeris")
    assert because == [
        "linija iki buto veikia, bet routerio linijoje nematyti",
        "routerio lemputės nedega",
        "maitinimo laidas įkištas",
        "rozetė veikia",
        "kompiuteris, prijungtas tiesiai prie linijos, veikia — linija tvarkinga, gedimas routeryje",
    ]


def test_power_not_checked_is_said_so():
    from agent.executor_flow import _card_reading

    found, because, _ = _card_reading(_state({"line_link": "up", "lights": "off"}))
    assert "nepatikrintas" in found
    assert "maitinimo laidas įkištas" not in because


def test_lights_on_is_no_dead_router():
    from agent.executor_flow import _card_reading

    found, _, _ = _card_reading(_state({**DEAD_ROUTER, "lights": "on"}))
    assert found is None  # the line's own gloss stays


def test_the_checked_list_is_findings_only_and_once():
    from agent.executor_flow import _card_reading, _checked_with_client

    evidence = {  # what the model wrote first — „dega", and process facts
        "lights": {"value": "on", "source": "client"},
        "has_computer": {"value": "yes", "source": "client"},
        "restored": {"value": "yes", "source": "client"},
        "outlet_works": {"value": "tried", "source": "client"},
    }
    s = _state(evidence=evidence)
    _, _, covered = _card_reading(s)
    bits = _checked_with_client(s, covered)
    text = "; ".join(bits)
    for gone in ("dega", "restored", "turite", "wan_link", "prieiti", "tinka", "laidas: laidas"):
        assert gone not in text, text


def test_without_a_card_reading_the_engine_value_is_listed():
    from agent.executor_flow import _checked_with_client

    s = _state(evidence={"lights": {"value": "on", "source": "client"}})
    assert "routerio lemputės: nedega" in _checked_with_client(s, set())

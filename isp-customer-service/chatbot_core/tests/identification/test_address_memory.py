"""Adreso atmintis — the address slots across turns (agent/slots.py, agent/perceive/slots.py).

What was heard stays heard; what the registry resolved is not lost to a later mishearing; a
fresh full dictation wins over stale fragments; parts said over several turns add up.
"""

import pytest
from agent.slots import ClientProfileState, Slot, SlotStatus

from .helpers import _agent

FUNCTION = "Adreso atmintis"


# Parts said over several turns add up (T-3).
PARTS = [
    pytest.param(
        ["S. Dariaus ir Girėno gatvė", "25 namas", "butas 45"],
        ("S. Dariaus ir S. Girėno g.", "25", "45"),
        id="T-3 gatvė, namas, butas atskirai",
    ),
    pytest.param(
        ["Tilžės 60", "butas 7"], ("Tilžės g.", "60", "7"), id="gatvė su namu, tada butas"
    ),
    pytest.param(
        ["Tilžės 60 butas 7", "ne, butas 3"], ("Tilžės g.", "60", "3"), id="buto pataisymas"
    ),
    pytest.param(
        ["Skambinu jau trečią kartą"], (None, None, None), id="skaičius ne adreso sakinyje"
    ),
    pytest.param(
        ["Pas mane trys kompiuteriai ir neveikia"],
        (None, None, None),
        id="kiekis ne adreso sakinyje",
    ),
]


@pytest.mark.parametrize(("turns", "expect"), PARTS)
def test_the_parts_add_up(db_connection, turns, expect):
    """Adreso dalys kaupiamos"""
    from agent.perceive.slots import prefill_slots_from_text

    a = _agent()
    a.state.intake.problem_type = "internet_down"
    for text in turns:
        prefill_slots_from_text(a.state, a.runtime, text)
    p = a.state.identity.profile
    assert (p.street.value, p.house.value, p.apartment.value) == expect


# --- from test_slots.py ---


class TestSlotPropose:
    def test_fills_empty_slot(self):
        s = Slot()
        assert s.propose("Tilžės g.", 0.9, SlotStatus.RESOLVED) is True
        assert s.value == "Tilžės g." and s.status == SlotStatus.RESOLVED

    def test_ignores_empty_value(self):
        s = Slot()
        assert s.propose(None, 0.9, SlotStatus.RESOLVED) is False
        assert s.propose("", 0.9, SlotStatus.RESOLVED) is False
        assert s.status == SlotStatus.EMPTY

    def test_heard_does_not_overwrite_resolved_different_value(self):
        """The core guard: a mishearing can't clobber a DB-confirmed value."""
        s = Slot()
        s.propose("60", 0.9, SlotStatus.RESOLVED)
        assert s.propose("610", 0.5, SlotStatus.HEARD) is False
        assert s.value == "60" and s.status == SlotStatus.RESOLVED

    def test_resolved_overwrites_heard(self):
        s = Slot()
        s.propose("Tildžios", 0.5, SlotStatus.HEARD)
        assert s.propose("Tilžės g.", 0.9, SlotStatus.RESOLVED) is True
        assert s.value == "Tilžės g." and s.status == SlotStatus.RESOLVED

    def test_same_value_lower_status_still_applies(self):
        """Re-reading the same value never gets blocked (no spurious rejection)."""
        s = Slot()
        s.propose("60", 0.9, SlotStatus.RESOLVED)
        assert s.propose("60", 0.5, SlotStatus.HEARD) is True
        assert s.value == "60"

    def test_confirmed_is_top_of_the_order(self):
        s = Slot()
        s.propose("7", 1.0, SlotStatus.CONFIRMED)
        assert s.propose("8", 0.9, SlotStatus.RESOLVED) is False
        assert s.value == "7" and s.status == SlotStatus.CONFIRMED


class TestUpdateFromResolution:
    def test_ok_levels_become_resolved(self):
        profile = ClientProfileState()
        resolution = {
            "city": {"given": "Šiauliai", "status": "ok", "matched": "Šiauliai"},
            "street": {"given": "Tilžės", "status": "ok", "matched": "Tilžės g."},
            "house": {"given": "60", "status": "ok", "matched": "60"},
            "apartment": {"given": "7", "status": "ok"},
        }
        profile.update_from_resolution(resolution)
        assert profile.street.value == "Tilžės g." and profile.street.status == SlotStatus.RESOLVED
        assert profile.house.value == "60" and profile.house.status == SlotStatus.RESOLVED
        assert profile.apartment.value == "7" and profile.apartment.status == SlotStatus.RESOLVED

    def test_failed_level_becomes_heard(self):
        profile = ClientProfileState()
        resolution = {
            "city": {"given": "Šiauliai", "status": "ok", "matched": "Šiauliai"},
            "street": {"given": "Žeimių", "status": "not_in_city"},
            "house": {"given": None, "status": "skipped"},
            "apartment": {"given": None, "status": "skipped"},
        }
        profile.update_from_resolution(resolution)
        assert profile.street.value == "Žeimių" and profile.street.status == SlotStatus.HEARD
        assert profile.house.status == SlotStatus.EMPTY  # skipped -> untouched

    def test_skipped_levels_left_empty(self):
        profile = ClientProfileState()
        profile.update_from_resolution(
            {"city": {"given": "Šiauliai", "status": "ok", "matched": "Šiauliai"}}
        )
        assert profile.city.status == SlotStatus.RESOLVED
        assert profile.street.status == SlotStatus.EMPTY

    def test_recovered_city_is_resolved(self):
        profile = ClientProfileState()
        profile.update_from_resolution(
            {"city": {"given": "Vilnius", "status": "recovered", "matched": "Šiauliai"}}
        )
        assert profile.city.value == "Šiauliai" and profile.city.status == SlotStatus.RESOLVED

    def test_later_mishearing_does_not_drop_resolved(self):
        """Across two calls: the second, garbled house number must not win."""
        profile = ClientProfileState()
        profile.update_from_resolution({"house": {"given": "60", "status": "ok", "matched": "60"}})
        # next turn STT garbles it; resolve_address can't find 610 -> not_found
        profile.update_from_resolution({"house": {"given": "610", "status": "not_found"}})
        assert profile.house.value == "60" and profile.house.status == SlotStatus.RESOLVED


class TestIntegrationViaAgentTool:
    """resolve_address through the agent populates the slots over the seed DB."""

    def test_resolve_address_fills_slots(self, db_connection):
        import json

        from agent.execute.observe import update_state_from_observation
        from agent.tools import resolve_address

        from tests.calls import make_agent

        agent = make_agent("+37060020105")
        obs = json.dumps(
            resolve_address(
                city="Šiauliai", street="Tilžės", house_number="60", apartment_number="7"
            )
        )
        update_state_from_observation(agent.state, agent.runtime, "resolve_address", obs)

        p = agent.state.identity.profile
        assert p.street.status == SlotStatus.RESOLVED
        assert p.house.value == "60"
        assert agent.state.identity.customer_id == "CUST105"  # existing behaviour unchanged


# --- from test_nlu_wave.py ---


class TestCodeModeDictation:
    """Blokas 2: pilna diktacija kodo režime prabudina adresų skaitytuvą."""

    def test_full_dictation_wakes_reader(self, db_connection):
        from agent.perceive.slots import prefill_slots_from_text

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        prefill_slots_from_text(
            agent.state, agent.runtime, "Negaliu pasakyti kodo. Šiauliai, Tilžės gatvė 60, butas 3"
        )
        p = agent.state.identity.profile
        assert p.street.value and "Tilž" in p.street.value
        assert p.house.value == "60" and p.apartment.value == "3"

    def test_bare_digits_stay_silenced(self, db_connection):
        from agent.perceive.slots import prefill_slots_from_text

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        prefill_slots_from_text(agent.state, agent.runtime, "10104")
        assert agent.state.identity.profile.street.value is None


class TestFreshDictationWins:
    """Blokas 3: ŠIO turn'o pilna diktacija permuša senus fragmentus."""

    def test_full_dictation_overrides_stale_house(self, db_connection):
        from agent.perceive.slots import prefill_slots_from_text
        from agent.slots import SlotStatus

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.profile.street.propose("Tilžės g.", 0.92, SlotStatus.HEARD)
        agent.state.identity.profile.house.propose("6", 0.92, SlotStatus.HEARD)
        agent.state.identity.profile.apartment.propose("60", 0.92, SlotStatus.HEARD)
        prefill_slots_from_text(
            agent.state, agent.runtime, "Sakau — Šiauliai, Tilžės gatvė 60, butas 3"
        )
        p = agent.state.identity.profile
        assert p.house.value == "60" and p.apartment.value == "3"


def test_denied_street_dropped_and_not_reread(db_connection):
    """D1 (gyva 2026-09-10): „apie Žeimių gatvę nieko NESAKIAU" — slotas
    išmetamas ir iš paties neigimo sakinio gatvė NEgrįžta."""
    from agent.perceive.slots import prefill_slots_from_text
    from agent.slots import SlotStatus

    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    agent.state.identity.profile.street.propose("Žeimių g.", 1.0, SlotStatus.HEARD)
    agent.state.identity.profile.house.propose("60", 1.0, SlotStatus.HEARD)
    prefill_slots_from_text(agent.state, agent.runtime, "Aš apie Žeimių gatvę nieko nesakiau")
    assert agent.state.identity.profile.street.value is None
    assert agent.state.identity.address_resolve_failures >= 1  # žingsnis link paraidžiui


def test_denial_with_correction_keeps_new_street(db_connection):
    """D1: „nesakiau Žeimių — Tilžės gatvė 60" — pataisymas išgyvena."""
    from agent.perceive.slots import prefill_slots_from_text
    from agent.slots import SlotStatus

    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    agent.state.identity.profile.street.propose("Žeimių g.", 1.0, SlotStatus.HEARD)
    prefill_slots_from_text(agent.state, agent.runtime, "Nesakiau Žeimių — Tilžės gatvė 60")
    assert (
        agent.state.identity.profile.street.value
        and "Tilž" in agent.state.identity.profile.street.value
    )
    assert agent.state.identity.profile.house.value == "60"


# --- from test_nlu.py ---


def _stream_of(message):
    """A fake stream_tool_completion: streams the message content, returns the message."""

    def _gen(**kwargs):
        if message.content:
            yield message.content
        return message

    return _gen


def test_user_turn_prefills_slots(db_connection):
    """A caller turn populates the slots before the LLM, via the agent."""
    from unittest.mock import patch

    from agent.decide.rules.intake import apply_readings
    from agent.perceive import perceive
    from agent.slots import SlotStatus
    from agent.speak.node import turn as speak_turn

    from tests.calls import make_agent

    agent = make_agent("+37060012345")
    agent.state.dialog.turn_count = 1  # skip the greeting branch

    msg = type("M", (), {"content": "Gerai.", "tool_calls": None})()
    with (
        patch("agent.speak.node.stream_tool_completion", side_effect=_stream_of(msg)),
        patch("agent.speak.node.get_last_call_stats", return_value={}),
    ):
        text = "neveikia internetas Tilžės 60 butas 7"
        perceive(agent.state, agent.runtime, text)
        apply_readings(agent.state, agent.runtime)  # decide commits the problem (1c)
        list(speak_turn(agent.state, agent.runtime, text, "intake"))

    p = agent.state.identity.profile
    assert p.street.value == "Tilžės g." and p.street.status == SlotStatus.HEARD
    assert p.house.value == "60"
    assert p.apartment.value == "7"
    # R1: the stated problem is captured as a durable fact.
    assert agent.state.intake.problem_type == "internet_down"

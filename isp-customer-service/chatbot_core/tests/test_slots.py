"""
Tests for the structured dialog slots (agent/slots.py).

These lock down the durable-memory guarantees from pokalbio_variklis.md §3:
- a RESOLVED/CONFIRMED slot is NOT clobbered by a lower-confidence HEARD reading
  (the "TILŽĖ 610 overwrites Tilžės 60" trace bug);
- resolve_address per-level results map into the slots with the right status;
- the slots accumulate across calls.

Run: pytest tests/test_slots.py -v
"""

from agent.slots import ClientProfileState, Slot, SlotStatus


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

        from agent.react_agent import ReactAgent
        from agent.tools import resolve_address

        agent = ReactAgent(caller_phone="+37060020105")
        obs = json.dumps(
            resolve_address(
                city="Šiauliai", street="Tilžės", house_number="60", apartment_number="7"
            )
        )
        agent._update_state_from_observation("resolve_address", obs)

        p = agent.state.profile
        assert p.street.status == SlotStatus.RESOLVED
        assert p.house.value == "60"
        assert agent.state.customer_id == "CUST105"  # existing behaviour unchanged

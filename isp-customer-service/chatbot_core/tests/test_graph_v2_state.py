"""
GraphState (graph_v2) — R1 state-migration tests (docs/ROADMAP_REFACTORING.md §3).

What must hold before anything else is built on the new state:
1. Legacy <-> v2 round-trip is lossless for every AgentState field.
2. The whole state JSON-serializes and validates back (SqliteSaver readiness).
3. Snapshots are deep — mutating one side never leaks into the other.
4. Slot semantics (propose downgrade guard) survive the round-trip.
5. begin_turn resets scratch without touching conversation state.
"""

import dataclasses

from agent.graph_v2.state import _LEGACY_FIELDS, GraphState, TurnScratch
from agent.slots import SlotStatus
from agent.state import AgentState


def _populated_legacy() -> AgentState:
    """A legacy state with every mutable container non-empty."""
    s = AgentState(caller_phone="+37060012345")
    s.messages.append({"role": "user", "content": "neveikia internetas"})
    s.profile.street.propose("Tilžės g.", 0.9, SlotStatus.RESOLVED)
    s.profile.house.propose("60", 0.5, SlotStatus.HEARD)
    s.set_customer_info("CUST-7", name="Jonas", address="Tilžės g. 60, Šiauliai")
    s.address_confirmed = True
    s.problem_type = "internet"
    s.heard_utterances.extend(["šešias dešimt", "Tilžės"])
    s.symptoms["lights"] = "no_internet_led"
    s.observations.append("port down")
    s.diagnosis["network"] = {"group": "L2", "side": "isp", "action": "bind_mac"}
    s.hypothesis = {"cause": "foreign_mac", "because": ["mac mismatch"], "status": "testing"}
    s.evidence["router_lights"] = {"value": "dega", "source": "client", "turn": 3}
    s.failed_hypotheses.append("healthy_to_router")
    s.rejected_hypotheses.append({"cause": "healthy_to_router", "by": "telemetry"})
    s.resolution = {"verdict": "foreign_mac", "step": "bind_mac", "asked": True}
    s.last_question = "Ar mirksi lemputė?"
    s.stuck_count = 1
    s.last_heard = "mirksi"
    s.awaiting = "client_answer"
    s.awaiting_turns = 2
    s.turn_count = 5
    s.contact_phone = "+37061111111"
    return s


class TestFieldParity:
    def test_v2_covers_every_legacy_field(self):
        missing = [name for name in _LEGACY_FIELDS if name not in GraphState.model_fields]
        assert missing == [], f"GraphState is missing legacy fields: {missing}"

    def test_defaults_match_legacy_defaults(self):
        legacy = AgentState(caller_phone="+37060000000")
        v2 = GraphState(caller_phone="+37060000000")
        for name in _LEGACY_FIELDS:
            assert getattr(v2, name) == getattr(legacy, name), name


class TestRoundTrip:
    def test_legacy_to_v2_to_legacy_is_lossless(self):
        legacy = _populated_legacy()
        back = GraphState.from_legacy(legacy).to_legacy()
        for f in dataclasses.fields(AgentState):
            assert getattr(back, f.name) == getattr(legacy, f.name), f.name

    def test_snapshots_are_deep(self):
        legacy = _populated_legacy()
        v2 = GraphState.from_legacy(legacy)
        legacy.evidence["router_lights"]["value"] = "nedega"
        legacy.messages.append({"role": "user", "content": "papildoma"})
        assert v2.evidence["router_lights"]["value"] == "dega"
        assert len(v2.messages) == 1
        restored = v2.to_legacy()
        v2.diagnosis["network"]["action"] = "reset_port"
        assert restored.diagnosis["network"]["action"] == "bind_mac"

    def test_slot_guard_survives_round_trip(self):
        v2 = GraphState.from_legacy(_populated_legacy())
        street = v2.profile.street
        assert street.status is SlotStatus.RESOLVED
        # a weaker HEARD mishearing must still not clobber the RESOLVED value
        assert street.propose("TILŽĖ 610", 0.4, SlotStatus.HEARD) is False
        assert street.value == "Tilžės g."


class TestCheckpointerReadiness:
    def test_json_serialization_round_trip(self):
        v2 = GraphState.from_legacy(_populated_legacy())
        v2.turn.user_input = "mirksi raudonai"
        restored = GraphState.model_validate_json(v2.model_dump_json())
        assert restored.model_dump() == v2.model_dump()
        assert restored.profile.street.status is SlotStatus.RESOLVED
        assert restored.turn.user_input == "mirksi raudonai"

    def test_plain_dict_dump_has_no_live_objects(self):
        dumped = GraphState.from_legacy(_populated_legacy()).model_dump()

        def only_plain(value):
            if isinstance(value, dict):
                return all(only_plain(v) for v in value.values())
            if isinstance(value, list):
                return all(only_plain(v) for v in value)
            return isinstance(value, (str, int, float, bool, type(None)))

        assert only_plain(dumped)


class TestTurnLifecycle:
    def test_begin_turn_resets_scratch_only(self):
        v2 = GraphState.from_legacy(_populated_legacy())
        v2.turn.reply = "Sekundėlę, tikrinu."
        v2.turn.cancel_requested = True
        v2.begin_turn("dabar veikia")
        assert v2.turn == TurnScratch(user_input="dabar veikia")
        assert v2.stuck_count == 1
        assert v2.evidence["router_lights"]["value"] == "dega"

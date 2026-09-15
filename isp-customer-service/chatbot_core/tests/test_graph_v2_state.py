"""
GraphState (graph_v2) — the single call state.

What must hold for everything built on it:
1. The whole state JSON-serializes and validates back (checkpointer readiness).
2. Slot semantics (propose downgrade guard) survive serialization.
3. Every message shape the engine produces survives graph-entry coercion.
4. Every state model round-trips through the checkpoint serializer.
"""

from agent.graph_v2.state import GraphState
from agent.slots import SlotStatus


def _populated() -> GraphState:
    """A state with every group and mutable container non-empty."""
    s = GraphState()
    s.identity.caller_phone = "+37060012345"
    s.messages.append({"role": "user", "content": "neveikia internetas"})
    s.identity.profile.street.propose("Tilžės g.", 0.9, SlotStatus.RESOLVED)
    s.identity.profile.house.propose("60", 0.5, SlotStatus.HEARD)
    s.identity.set_customer("CUST-7", name="Jonas", address="Tilžės g. 60, Šiauliai")
    s.identity.address_confirmed = True
    s.intake.problem_type = "internet"
    s.intake.heard_utterances.extend(["šešias dešimt", "Tilžės"])
    s.intake.symptoms["lights"] = "no_internet_led"
    s.intake.observations.append("port down")
    s.diagnosis.verdicts["network"] = {"group": "L2", "side": "isp", "action": "bind_mac"}
    s.diagnosis.hypothesis = {
        "cause": "foreign_mac",
        "because": ["mac mismatch"],
        "status": "testing",
    }
    s.diagnosis.evidence["router_lights"] = {"value": "dega", "source": "client", "turn": 3}
    s.diagnosis.failed_hypotheses.append("healthy_to_router")
    s.diagnosis.rejected_hypotheses.append({"cause": "healthy_to_router", "by": "telemetry"})
    s.resolution.procedure = {"verdict": "foreign_mac", "step": "bind_mac", "asked": True}
    s.ticket.stage = "phone"
    s.ticket.contact_phone = "+37061111111"
    s.dialog.last_question = "Ar mirksi lemputė?"
    s.dialog.stuck_count = 1
    s.dialog.last_heard = "mirksi"
    s.dialog.awaiting = "client_answer"
    s.dialog.awaiting_turns = 2
    s.dialog.turn_count = 5
    s.closing.closing_turns = 1
    return s


class TestCheckpointerReadiness:
    def test_json_serialization_round_trip(self):
        state = _populated()
        state.turn.user_input = "mirksi raudonai"
        restored = GraphState.model_validate_json(state.model_dump_json())
        assert restored.model_dump() == state.model_dump()
        assert restored.identity.profile.street.status is SlotStatus.RESOLVED
        assert restored.turn.user_input == "mirksi raudonai"

    def test_plain_dict_dump_has_no_live_objects(self):
        dumped = _populated().model_dump()

        def only_plain(value):
            if isinstance(value, dict):
                return all(only_plain(v) for v in value.values())
            if isinstance(value, list):
                return all(only_plain(v) for v in value)
            return isinstance(value, (str, int, float, bool, type(None)))

        assert only_plain(dumped)

    def test_slot_guard_survives_serialization(self):
        restored = GraphState.model_validate_json(_populated().model_dump_json())
        street = restored.identity.profile.street
        assert street.status is SlotStatus.RESOLVED
        # a weaker HEARD mishearing must still not clobber the RESOLVED value
        assert street.propose("TILŽĖ 610", 0.4, SlotStatus.HEARD) is False
        assert street.value == "Tilžės g."


class TestRealMessageShapes:
    """The state must accept every message shape the engine ACTUALLY produces —
    not just happy-path {role, content} strings. Live 2026-08-13: an assistant
    tool-call message (tool_calls = LIST) passed the write, then EVERY following
    turn died at graph entry when pydantic coerced the stored state."""

    def test_tool_round_messages_survive_graph_entry_coercion(self):
        state = GraphState()
        state.messages.extend(
            [
                {"role": "user", "content": "Dėl Vilniaus gatvės 29."},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "resolve_address",
                                "arguments": '{"street":"Vilniaus","house_number":"29"}',
                            },
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": '{"success": true}'},
                {"role": "assistant", "content": "Radau adresą."},
            ]
        )
        # LangGraph re-coerces raw channel values via schema(**values) at EVERY
        # turn entry — the exact spot the live call kept failing at.
        coerced = GraphState(**state.model_dump())
        assert coerced.messages[1]["tool_calls"][0]["function"]["name"] == "resolve_address"
        restored = GraphState.model_validate_json(state.model_dump_json())
        assert restored.messages == state.messages


class TestCheckpointSerde:
    """Every model the engine keeps as call state comes back from the checkpoint
    serializer as the same model — not a plain dict, not a blocked type."""

    def test_state_models_round_trip_through_the_checkpoint_serializer(self, tmp_path):
        from agent.dialog_registry import ActiveQuestion
        from agent.evidence import EvidenceConflict, FactConfirm
        from agent.graph_v2.checkpoint import make_checkpointer

        serde = make_checkpointer(tmp_path / "cp.sqlite").serde
        state = _populated()
        values = [
            ActiveQuestion(owner="ticket", key="ticket_phone", asks=2, data={"retry": True}),
            EvidenceConflict(key="lights", old="on", new="off"),
            FactConfirm(key="outlet_works", value="not_working"),
            state,
            *(getattr(state, group) for group in type(state).model_fields),
        ]
        for value in values:
            # An unregistered type comes back as a plain dict (and logs "Blocked").
            restored = serde.loads_typed(serde.dumps_typed(value))
            assert type(restored) is type(value)
            assert restored == value

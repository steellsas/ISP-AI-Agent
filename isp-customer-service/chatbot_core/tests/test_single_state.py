"""
Single state (M1 proof): the checkpoint is the whole call.

A call runs a few turns, then continues on a NEW AgentSession object that shares
only the thread id and the checkpointer — identity, evidence, the procedure
position and the ticket dialogue must all carry over, and the engine object
must hold no call data of its own.

Run: pytest tests/test_single_state.py -v
"""

from types import SimpleNamespace
from unittest.mock import patch

from agent.graph_v2.checkpoint import make_checkpointer
from agent.session import AgentSession


def _fake_llm(**_kwargs):
    def _gen():
        yield "Gerai."
        return SimpleNamespace(content="Gerai.", tool_calls=None)

    return _gen()


def _turns(session, texts):
    replies = []
    with (
        patch("agent.react_agent.stream_tool_completion", side_effect=_fake_llm),
        patch("agent.react_agent.get_last_call_stats", return_value={}),
    ):
        for text in texts:
            replies.append(session.handle_turn(text))
    return replies


# Engine attributes that are runtime objects or config, never call data.
RUNTIME_ATTRIBUTES = {
    "config",
    "state",  # the working copy handed in by the running node
    "session_id",
    "tracer",
    "tools",
    "runtime",
    "llm_stats",
    "system_prompt",
    "tools_schema",
    "_session_ended",
    "_spec_cache",
    "_cancel_requested",
}


class TestCallContinuesOnAFreshSession:
    def test_state_survives_a_new_session_object(self, db_connection, tmp_path):
        saver = make_checkpointer(tmp_path / "calls.sqlite")
        first = AgentSession(caller_phone="+37060012353", checkpointer=saver)
        first.greeting()
        _turns(first, ["Neveikia internetas", "Taip", "Giedrius, mano sutartis"])
        before = first.state
        assert before.identity.customer_id == "CUST009"
        assert before.resolution.procedure and before.resolution.procedure.get("step")

        # The same call on a brand-new session object: only the thread id and
        # the checkpointer are shared.
        second = AgentSession(
            caller_phone="+37060012353", checkpointer=saver, thread_id=first.session_id
        )
        restored = second._current_state()
        assert restored.identity == before.identity
        assert restored.diagnosis.evidence == before.diagnosis.evidence
        assert restored.resolution.procedure == before.resolution.procedure
        assert restored.ticket == before.ticket
        assert restored.messages == before.messages

        # The call continues where it was: a ticket demand starts the contact dialogue.
        (reply,) = _turns(second, ["Nieko nedarysiu, užregistruokite gedimą"])
        after = second.state
        assert after.identity.customer_id == "CUST009"
        assert after.ticket.stage == "phone"
        assert "numer" in reply  # the dialogue's first question: the contact number
        assert after.messages[: len(before.messages)] == before.messages
        assert len(after.messages) > len(before.messages)

        # And back on the checkpoint: the first object sees the continued call too.
        assert first._current_state().ticket.stage == "phone"

    def test_engine_holds_no_call_data(self, db_connection):
        session = AgentSession(caller_phone="+37060012353")
        session.greeting()
        _turns(session, ["Neveikia internetas", "Taip"])
        leftovers = sorted(set(vars(session._agent)) - RUNTIME_ATTRIBUTES)
        assert leftovers == []

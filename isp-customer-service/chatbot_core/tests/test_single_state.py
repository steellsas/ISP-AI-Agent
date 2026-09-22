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
        patch("agent.speak.node.stream_tool_completion", side_effect=_fake_llm),
        patch("agent.speak.node.get_last_call_stats", return_value={}),
    ):
        for text in texts:
            replies.append(session.handle_turn(text))
    return replies

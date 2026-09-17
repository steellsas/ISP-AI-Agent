"""The dashboard's turn events (M7): a timed `graph_node` per graph node and one
`turn_plan` per turn, numbered."""

from types import SimpleNamespace
from unittest.mock import patch


class _CaptureTracer:
    session_id = "plan-trace-test"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


def _fake_llm(**_kwargs):
    def _gen():
        yield "Gerai."
        return SimpleNamespace(content="Gerai.", tool_calls=None)

    return _gen()


def test_every_turn_times_its_graph_nodes_and_numbers_its_plan(db_connection):
    from agent.session import AgentSession

    tracer = _CaptureTracer()
    session = AgentSession(caller_phone="+37060020112", tracer=tracer)
    session.greeting()
    with (
        patch("agent.speak.node.stream_tool_completion", side_effect=_fake_llm),
        patch("agent.speak.node.get_last_call_stats", return_value={}),
    ):
        session.handle_turn("Neveikia internetas")
        session.handle_turn("Taip")

    nodes = [e["node"] for e in tracer.events if e["type"] == "graph_node"]
    assert nodes[-4:] == ["perceive", "decide", "execute", "narrate"]
    assert all(isinstance(e["ms"], int) for e in tracer.events if e["type"] == "graph_node")
    plans = [e for e in tracer.events if e["type"] == "turn_plan"]
    assert [p["turn_index"] for p in plans][-2:] == [1, 2]
    assert {"owner", "rule", "say"} <= set(plans[-1])

"""Shadow TurnPlan (M4 step 2): every turn emits exactly one `turn_plan` event with a
rule id, and the plan names the path the engine took."""

from unittest.mock import patch

from agent.decide.plan import TurnPlan

from tests.test_graph_v2 import _fake_stream


class _Tracer:
    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


def _plans(tracer):
    return [e for e in tracer.events if e["type"] == "turn_plan"]


def test_every_turn_emits_one_plan(db_connection, tmp_path):
    from agent.graph_v2.checkpoint import make_checkpointer
    from agent.graph_v2.graph import build_graph
    from agent.session import AgentSession

    tracer = _Tracer()
    session = AgentSession(caller_phone="+37060012353", tracer=tracer)
    session._graph = build_graph(make_checkpointer(tmp_path / "cp.sqlite"))

    session.greeting()
    plans = _plans(tracer)
    assert len(plans) == 1
    assert plans[0]["rule"] == "dialog.greeting" and plans[0]["source"] == "policy"
    assert plans[0]["say"]["kind"] == "phrase"

    with patch("agent.react_agent.stream_tool_completion", _fake_stream("Kuo galiu padėti?")):
        session.handle_turn("O kas jūs tokie?")
    plans = _plans(tracer)
    assert len(plans) == 2
    TurnPlan.model_validate(
        {k: v for k, v in plans[1].items() if k not in ("type", "shadow", "source")}
    )
    assert plans[1]["rule"] and plans[1]["shadow"]["path"] in {"llm", "scripted"}

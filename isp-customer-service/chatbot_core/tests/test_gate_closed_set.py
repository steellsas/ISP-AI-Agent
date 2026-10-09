"""The plan gate (D-04, D-16, D-17): only declared actions run."""

from agent.decide.gate import check_plan
from agent.decide.plan import Action, Say, TurnPlan


class _Tracer:
    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


def _plan(action):
    return TurnPlan(owner="diagnosis", rule="test.rule", action=action, say=Say(kind="directive"))


def _call(make_state, make_runtime, verdict="router_hung"):
    state = make_state("+37060020112")
    state.resolution.procedure = {"verdict": verdict, "step": "rh_ability"}
    tracer = _Tracer()
    return state, make_runtime(tracer=tracer), tracer


def test_known_tool_and_ticket_pass(make_state, make_runtime):
    state, rt, _ = _call(make_state, make_runtime)
    for action in (
        Action(type="tool", name="update_mac"),
        Action(type="tool", name="preflight_phone"),
        Action(type="register_ticket"),
    ):
        assert check_plan(state, rt, _plan(action)).action == action


def test_unknown_tool_is_dropped_and_traced(make_state, make_runtime):
    state, rt, tracer = _call(make_state, make_runtime)
    plan = check_plan(state, rt, _plan(Action(type="tool", name="format_disk")))
    assert plan.action.type == "none" and plan.rule == "test.rule.gated"
    assert plan.say.kind == "directive"  # the words stay
    assert tracer.events[-1]["type"] == "gate"


def test_every_action_type_has_an_executor():
    """Wave 10, S4: `procedure_step` passed the gate but nothing executed it (execute raised
    „no executor"). Every action type a plan may carry must have its branch in execute."""
    import inspect
    import typing

    from agent.execute import actions

    source = inspect.getsource(actions.run_action)
    for kind in typing.get_args(Action.model_fields["type"].annotation):
        assert f'"{kind}"' in source, kind


def test_forbidden_action_is_dropped(make_state, make_runtime, monkeypatch):
    from agent.contract import policies

    state, rt, _ = _call(make_state, make_runtime)
    forbidden = policies.get().model_copy(update={"forbidden_actions": ["update_mac"]})
    monkeypatch.setattr(policies, "get", lambda: forbidden)
    assert (
        check_plan(state, rt, _plan(Action(type="tool", name="update_mac"))).action.type == "none"
    )

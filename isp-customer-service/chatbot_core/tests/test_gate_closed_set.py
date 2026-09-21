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


def test_known_tool_and_procedure_role_pass(make_state, make_runtime):
    state, rt, _ = _call(make_state, make_runtime)
    for action in (
        Action(type="tool", name="update_mac"),
        Action(type="tool", name="preflight_phone"),
        Action(type="procedure_step", name="reboot"),
        Action(type="procedure_step", name="run_due_action"),
        Action(type="register_ticket"),
    ):
        assert check_plan(state, rt, _plan(action)).action == action


def test_unknown_tool_is_dropped_and_traced(make_state, make_runtime):
    state, rt, tracer = _call(make_state, make_runtime)
    plan = check_plan(state, rt, _plan(Action(type="tool", name="format_disk")))
    assert plan.action.type == "none" and plan.rule == "test.rule.gated"
    assert plan.say.kind == "directive"  # the words stay
    assert tracer.events[-1]["type"] == "gate"


def test_role_outside_the_active_procedure_is_dropped(make_state, make_runtime):
    state, rt, _ = _call(make_state, make_runtime)
    plan = check_plan(state, rt, _plan(Action(type="procedure_step", name="bind_device")))
    assert plan.action.type == "none"


def test_consent_required_needs_the_recorded_consent(make_state, make_runtime):
    state, rt, _ = _call(make_state, make_runtime)
    action = Action(type="procedure_step", name="reboot", consent="required")
    assert check_plan(state, rt, _plan(action)).action.type == "none"
    state.dialog.consents["reboot"] = True
    assert check_plan(state, rt, _plan(action)).action == action


def test_forbidden_action_is_dropped(make_state, make_runtime, monkeypatch):
    from agent.contract import policies

    state, rt, _ = _call(make_state, make_runtime)
    forbidden = policies.get().model_copy(update={"forbidden_actions": ["update_mac"]})
    monkeypatch.setattr(policies, "get", lambda: forbidden)
    assert (
        check_plan(state, rt, _plan(Action(type="tool", name="update_mac"))).action.type == "none"
    )


def test_propose_fix_is_accepted_for_every_pack_verdict():
    from agent.decide.solver import SolverDecision
    from agent.decide.solver_guard import gate
    from agent.faults import pack_verdicts

    for verdict in pack_verdicts():
        decision = SolverDecision(
            current_hypothesis=verdict, next_action="propose_fix", narrator_instruction="x"
        )
        assert gate(decision, known_hypotheses=pack_verdicts()).accepted, verdict


def test_a_verdict_without_pack_or_news_starts_the_unclear_fault_ticket(make_state, make_runtime):
    from agent.execute.diagnosis import _unclear_fault_when_unknown

    state, rt, tracer = _call(make_state, make_runtime)
    state.resolution.procedure = None
    state.identity.customer_id = "CUST106"
    state.diagnosis.verdicts["network"] = {"reason": "dhcp_silent"}
    _unclear_fault_when_unknown(state, rt)
    assert state.resolution.procedure["verdict"] == "unclear_fault"
    assert state.ticket.stage == "phone"

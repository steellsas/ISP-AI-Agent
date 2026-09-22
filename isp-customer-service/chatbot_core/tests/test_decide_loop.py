"""Wave 1a: decide owns the turn.

- A plan whose action feeds the next decision sends the turn back to decide, bounded.
- The narrator only speaks: it plans nothing, closes nothing, registers nothing.
- The caller's words land on the history once, in perceive.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.contract import limits
from agent.decide.plan import Action, Say, TurnPlan
from agent.graph_v2.graph import redecide
from agent.graph_v2.state import GraphState, IdentityState, TurnScratch

# (redecide_after_action, hops already made, where the turn goes next)
HOPS = [
    (False, 0, "narrate"),
    (True, 0, "decide"),
    (True, 1, "decide"),
    (True, 2, "decide"),
    (True, 3, "narrate"),  # the budget (plan_redecide_max) is spent
    (True, 9, "narrate"),
]


@pytest.mark.parametrize("again, hops, goes_to", HOPS)
def test_the_turn_goes_back_to_decide_while_the_budget_lasts(again, hops, goes_to):
    # Wave 3 raised it to the longest honest chain: reflect the caller's action, read the
    # line, then say what it showed.
    assert limits.get("plan_redecide_max") == 3
    state = GraphState(
        turn=TurnScratch(
            plan=TurnPlan(
                owner="diagnosis",
                rule="t",
                say=Say(kind="none"),
                redecide_after_action=again,
            ).model_dump(mode="json"),
            plan_hops=hops,
        )
    )

    assert redecide(state) == goes_to


def _runtime():
    import threading

    from agent.config import AgentConfig
    from agent.runtime import AgentRuntime

    return AgentRuntime(
        session_id="t",
        config=AgentConfig(),
        tracer=SimpleNamespace(emit=lambda *a, **k: None),
        tools=None,
        cancel=threading.Event(),
    )


def _graph():
    from agent.graph_v2.graph import build_graph
    from langgraph.checkpoint.memory import MemorySaver

    return build_graph(MemorySaver())


def test_a_redeciding_plan_re_plans_the_turn_then_speaks(monkeypatch):
    """The loop runs decide again after the action — and the hop budget ends it."""
    passes = {"n": 0}

    def _plan_turn(state, rt):
        passes["n"] += 1
        return TurnPlan(
            owner="diagnosis",
            rule=f"test.pass{passes['n']}",
            say=Say(kind="phrase", text="Gerai.", stage="diagnosis"),
            redecide_after_action=True,
        )

    monkeypatch.setattr("agent.decide.policy.plan_turn", _plan_turn)
    monkeypatch.setattr("agent.perceive.node.perceive", lambda state, rt, text: None)
    monkeypatch.setattr("agent.perceive.node.read_turn_start", lambda state, rt, text: None)

    out = _graph().invoke(
        {"identity": IdentityState(customer_id="C1"), "turn": TurnScratch(user_input="labas")},
        {"configurable": {"thread_id": "loop"}},
        context=_runtime(),
    )

    budget = limits.get("plan_redecide_max")
    assert passes["n"] == budget + 1
    assert out["turn"].plan["rule"] == f"test.pass{budget + 1}"
    assert out["turn"].plan_hops == limits.get("plan_redecide_max")


class TestNarratorOnlySpeaks:
    def test_speaking_a_plan_changes_no_decision(self, make_state, make_runtime):
        """The narrator used to run the scripted layer: it planned, closed calls and
        registered tickets. Now it speaks the plan it is handed and nothing else."""
        from agent.execute.say import speak

        state, rt = make_state("+37060020112"), make_runtime()
        state.dialog.stuck_count = 4  # the backstop would have fired inside the narrator

        with (
            patch(
                "agent.speak.node.stream_tool_completion",
                side_effect=_stream("Patikrinkime dar kartą."),
            ),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            reply = speak(
                state,
                rt,
                TurnPlan(
                    owner="diagnosis",
                    rule="diagnosis.free_reply",
                    say=Say(kind="directive", stage="diagnosis"),
                ),
                None,
            )

        assert reply == "Patikrinkime dar kartą."
        assert state.closing.case_closed is False
        assert state.ticket.ticket_id is None
        assert state.turn.plan is None  # the narrator records no plan of its own

    def test_a_phrase_plan_runs_its_action_in_execute_not_in_the_narrator(
        self, make_state, make_runtime
    ):
        from agent.execute.actions import run_action

        state, rt = make_state("+37060020112"), make_runtime()
        plan = TurnPlan(
            owner="closing",
            rule="closing.goodbye",
            action=Action(type="close", name="resolved", args={"complete": True}),
            say=Say(kind="phrase", text="Geros dienos!", stage="closing"),
        )

        run_action(state, rt, plan)

        assert (state.closing.case_closed, state.closing.closed_reason) == (True, "resolved")
        assert state.closing.is_complete is True


class TestPerceiveReadsTheTurn:
    def test_the_caller_utterance_lands_on_the_history_once(self, make_state, make_runtime):
        from agent.perceive.node import read_turn_start

        state, rt = make_state("+37060020112"), make_runtime()

        read_turn_start(state, rt, "neveikia internetas")

        assert [m["content"] for m in state.messages if m["role"] == "user"] == [
            "neveikia internetas"
        ]
        assert state.dialog.last_heard == "neveikia internetas"
        assert state.dialog.last_intent  # the turn intent is read here too


def _stream(text):
    def _gen(**kwargs):
        yield text
        return SimpleNamespace(content=text, tool_calls=None)

    return _gen


class TestPerceiveOnlyReads:
    """Wave 1c: perceive takes the readings; what they MEAN for the call is decided."""

    def test_the_problem_is_read_in_perceive_and_committed_in_decide(
        self, make_state, make_runtime
    ):
        from agent.decide.rules.intake import apply_readings
        from agent.perceive.slots import prefill_slots_from_text

        state, rt = make_state("+37060020112"), make_runtime()

        prefill_slots_from_text(state, rt, "Labas, neveikia internetas")

        assert state.turn.problem_reading == "internet_down"
        assert state.intake.problem_type is None  # not decided yet

        apply_readings(state, rt)
        assert state.intake.problem_type == "internet_down"

    def test_perceive_changes_no_dialogue_state(self, make_state, make_runtime):
        """A read may fill facts and the turn scratch — never the call's decisions."""
        from agent.perceive import perceive

        state, rt = make_state("+37060020112"), make_runtime()
        state.identity.customer_id = "CUST009"
        before = {
            "closing": state.closing.model_dump(),
            "ticket": state.ticket.model_dump(),
            "resolution": state.resolution.model_dump(),
            "problem": state.intake.problem_type,
        }

        perceive(state, rt, "O dar televizorius neveikia")

        assert state.closing.model_dump() == before["closing"]
        assert state.ticket.model_dump() == before["ticket"]
        assert state.resolution.model_dump() == before["resolution"]
        assert state.intake.problem_type == before["problem"]


# (the reading, what the call already knows) -> what the reading becomes
PROBLEM_CASES = [
    ("internet_down", {}, "primary"),
    ("billing", {}, "primary"),  # a request IS a call reason
    ("not_ours", {}, "boundary"),  # outside the agent's competence
    ("tv", {"problem_type": "internet_down", "solving": True}, "secondary"),
    # a request mentioned mid-fault is not a secondary TECH problem (F-28)
    ("billing", {"problem_type": "internet_down", "solving": True}, "ignored"),
    ("tv", {"problem_type": "internet_down"}, "corrected"),  # nothing checked yet
]


@pytest.mark.parametrize("reading, known, becomes", PROBLEM_CASES)
def test_what_a_problem_reading_becomes(reading, known, becomes, make_state, make_runtime):
    from agent.decide.rules.intake import apply_readings

    state, rt = make_state("+37060020112"), make_runtime()
    state.dialog.last_heard = "o dar vienas dalykas nerodo"
    state.intake.problem_type = known.get("problem_type")
    if known.get("solving"):
        state.identity.customer_id = "CUST009"
        state.resolution.procedure = {"verdict": "router_hung", "step": "rh_check"}
    state.turn.problem_reading = reading

    apply_readings(state, rt)

    got = {
        "primary": state.intake.problem_type == reading,
        "boundary": state.intake.boundary_problem == reading,
        "secondary": [p["type"] for p in state.intake.secondary_problems] == [reading],
        "corrected": state.intake.problem_type == reading,
        "ignored": (
            state.intake.problem_type == known.get("problem_type")
            and not state.intake.secondary_problems
            and state.intake.boundary_problem is None
        ),
    }
    assert got[becomes], f"expected {becomes}, got {got}"

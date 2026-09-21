"""Wave 2b: one reply, one skill.

The narrator used to get every stage's rules and examples at once (~3500 tokens for a
reply of ~90). It now gets the core prompt plus the ONE skill the turn needs — and the
skill follows from the plan decide already made.
"""

import pytest
from agent.decide.plan import Say, TurnPlan
from agent.speak.node import speak_prompt
from agent.speak.skill import SKILLS, skill_for


def _plan(rule):
    return TurnPlan(owner=rule.split(".", 1)[0], rule=rule, say=Say(kind="directive")).model_dump(
        mode="json"
    )


# (the plan's rule, what the turn holds, the skill)
CASES = [
    ("identification.free_reply", {}, "ask_identity"),
    ("identification.problem_gate", {}, "ask_identity"),
    ("side_topic.answer", {}, "answer_side"),
    ("ticket.offscript_question", {}, "ticket_offscript"),
    ("inform.template", {}, "inform_news"),
    ("closing.free_reply", {}, "goodbye"),
    # the fault path: an instruction to carry out vs. a fact to learn
    ("procedure.hold", {"step": "rh_reboot"}, "instruct_step"),
    ("procedure.hold", {"step": "rh_scope"}, "ask_fact"),
    ("diagnosis.free_reply", {}, "ask_fact"),
    # the turn's own directives win over the stage
    ("procedure.hold", {"step": "rh_reboot", "findings": True}, "explain_finding"),
    ("procedure.hold", {"step": "rh_reboot", "evidence": True}, "ask_fact"),
    ("procedure.hold", {"step": "rh_reboot", "confused": True}, "reexplain_confused"),
]


@pytest.mark.parametrize("rule, turn, skill", CASES)
def test_the_skill_follows_the_plan(rule, turn, skill, make_state):
    state = make_state("+37060020112")
    state.turn.plan = _plan(rule)
    if turn.get("step"):
        state.resolution.procedure = {"verdict": "router_hung", "step": turn["step"]}
    if turn.get("findings"):
        state.turn.directives.findings = {"faktai": "x"}
    if turn.get("evidence"):
        state.turn.directives.evidence = {"key": "lights"}
    if turn.get("confused"):
        state.turn.understanding = {"type": "confusion", "confusion": "kas tas WAN"}

    assert skill_for(state, state.turn.plan["owner"]) == skill


def test_every_skill_has_a_prompt_and_examples():
    """A skill is a file pair: the instruction and its Lithuanian examples."""
    from agent.prompts import load_node_prompt

    for skill in SKILLS:
        text = load_node_prompt(f"skills/{skill}")
        assert text.startswith("SKILL:"), skill
        assert "GERAI" in text or "TONO" in text, f"{skill}: no examples reached the prompt"


def test_a_skill_prompt_is_far_smaller_than_the_old_owner_prompt():
    """The whole point: ~1.2-1.4k tokens instead of ~2.3-3.5k."""
    for skill in SKILLS:
        text = speak_prompt(skill, "+37060000000", "lt")
        assert len(text) < 7000, f"{skill}: {len(text)} chars"

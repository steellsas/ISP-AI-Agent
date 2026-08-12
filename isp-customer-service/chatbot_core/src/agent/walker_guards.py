"""
Walker guard chain — the ordered pre-checks that decide whether a caller's
turn may touch the active strategy step at all.

R3 extraction (docs/ROADMAP_REFACTORING.md §5): moved verbatim out of
ReactAgent._walk_resolution. Every guard is a hard-earned fix for an observed
live-call failure and the ORDER IS LOAD-BEARING — e.g. an explicit ticket
demand must outrank the evidence-question hold, which must outrank the
asked-step classifiers. Reorder only with a golden parity run.

Contract: a guard returns True when it CONSUMED the turn (the walker must
return without advancing), False to pass the turn to the next guard. Guards
may mutate engine state / route steps — they are behaviour, not pure routing;
the v2 graph will surface them as named edges once they are individually
addressable (this module is that step).

PRELUDE_GUARDS run before the strategy/step are resolved; STEP_GUARDS receive
the resolved (r, strat, step).
"""

from __future__ import annotations

import os
from typing import Any

# --- prelude (no step resolved yet) -----------------------------------------


def resume_hold(engine: Any, user_input: str | None) -> bool:
    """One-turn hold after the caller declined to end the call — their "ne,
    tęskime" answers the confirm-end question, not the current step."""
    if engine._resume_hold:
        engine._resume_hold = False
        return True
    return False


def end_confirm_pending(engine: Any, user_input: str | None) -> bool:
    """The confirm-end question is OUT and unanswered — in the graph's turn
    order the walker runs BEFORE the guard that reads its answer, so this
    reply belongs to that question, not the step (live 2026-08-11: "Ne,
    nenoriu" — i.e. don't END — advanced stale dr_intro -> escalate ->
    ticket). Hold; _pre_turn_guards resumes or closes this same turn."""
    if engine._end_confirm_pending:
        engine.tracer.emit("decision", intent="answer", action="hold", reason="end_confirm_pending")
        return True
    return False


PRELUDE_GUARDS = (resume_hold, end_confirm_pending)


# --- step guards (ordered — see module docstring) ----------------------------


def device_change_pre_answer(engine: Any, r, strat, step, user_input: str | None) -> bool:
    """A strong device-change signal advances confirm_change before it is even asked
    (the caller pre-answered, e.g. "neveikia, keičiau routerį"). ONLY for that step —
    elsewhere "kompiuteris" is a scope answer, not a device change. Runs before the
    intent gate: a clear pre-answer should move regardless of turn phrasing."""
    from .resolution import confirms_device_change, next_step_id

    if step.id == "confirm_change" and confirms_device_change(user_input):
        engine._route_to(r, next_step_id(strat, step.id, "yes"))
        return True
    return False


def backchannel_hold(engine: Any, r, strat, step, user_input: str | None) -> bool:
    """A bare "Mhm." / one-letter STT crumb is an acknowledgement, not an answer —
    HOLD asking steps instead of routing garbage (observed: "T." entered the bridge
    path as "yes, I have a computer"; "Mhm." climbed two INSTRUCT steps). ACTION
    steps still advance — their announce needs no answer."""
    from .resolution import StepKind, is_backchannel

    if step.kind in (StepKind.CONFIRM, StepKind.INSTRUCT) and is_backchannel(user_input):
        engine.tracer.emit(
            "decision", intent="backchannel", action="hold", from_step=step.id, to=step.id
        )
        return True
    return False


def restored_pre_answer(engine: Any, r, strat, step, user_input: str | None) -> bool:
    """A clear "atsirado / veikia" pre-answers a restored CONFIRM before it was even
    asked — often fused with the goodbye ("yra internetas, ačiū, viso gero"). Route
    the YES so the resolve is RECORDED instead of the call dying unclosed on the
    hangup (observed live: resolved Wi-Fi call left outcome=None). Only the clear
    affirmative pre-answers; a "no" still waits for the step's own question."""
    from .resolution import Outcome, detect_restored, next_step_id

    if step.detector == "restored" and not r.get("asked"):
        if detect_restored(user_input) is Outcome.YES:
            engine._route_to(r, next_step_id(strat, step.id, "yes"))
            return True
    return False


def refuse_or_ticket_redirect(engine: Any, r, strat, step, user_input: str | None) -> bool:
    """Refusal / explicit ticket demand ends troubleshooting in a REGISTRATION
    (policy 2026-07-30). A clear DEMAND ("įregistruokit gedimą") IS the consent —
    register now and close, with the reason on the ticket. A softer refusal
    ("nedarysiu", "nesu namuose") routes to the escalate step, whose consent
    question doubles as the polite clarification ("užregistruosiu — ar tinka?").
    Observed live: the caller demanded a ticket 3×, the narrator promised it 5×,
    and the walker held cable_check forever — no route existed."""
    from .resolution import StepKind, detect_refuse_or_ticket

    if step.kind is StepKind.ESCALATE:
        return False
    rt = detect_refuse_or_ticket(user_input)
    if rt is None or strat.step("escalate") is None:
        return False
    r["escalate_reason"] = (
        "Klientas paprašė registracijos."
        if rt == "demand"
        else "Neišspręsta — klientas atsisakė tęsti tikrinimą."
    )
    engine._goto_step(r, "escalate")
    engine.tracer.emit(
        "decision", intent="refuse_or_ticket", action=rt, from_step=step.id, to="escalate"
    )
    if rt == "demand":
        engine._begin_ticket_dialogue(strat.step("escalate"))
    return True


def evidence_question_open_hold(engine: Any, r, strat, step, user_input: str | None) -> bool:
    """Question OWNERSHIP (live 2026-08-11): while the evidence drive has an OPEN
    question, that is the question the caller is answering — the walker's own
    step question may be MANY turns stale. A barge-in-truncated "Ne." (meant:
    "ne, nedega…") was read by the stale dr_intro yes/no as "won't check
    together" → escalate → ticket → dead call. The asked-step routing below
    (classify + keyword) must not consume such a reply; explicit refusals and
    restored pre-answers were already handled above."""
    if engine._evidence_question_open():
        engine.tracer.emit(
            "decision",
            intent="answer",
            action="hold",
            from_step=step.id,
            to=step.id,
            reason="evidence_question_open",
        )
        return True
    return False


def classifier_confirm_route(engine: Any, r, strat, step, user_input: str | None) -> bool:
    """ASKED generic CONFIRM (yes/no, lights, scope, restored, …): the LLM classifier
    reads the answer AND whether it IS an answer in one call — so a confident answer
    advances even when the brittle keyword turn-intent would veto it (observed:
    "gerai, bandau… nė viena lemputė neužsidegė" was read as in_progress and froze
    dr_power). The keyword detector + intent gate stay as the fallback."""
    from .resolution import StepKind

    if (
        step.kind is StepKind.CONFIRM
        and r.get("asked")
        and engine._asked_recently(r)
        and step.on
        and step.id != "confirm_restored"
        and os.getenv("CLASSIFIER", "on").lower() != "off"
    ):
        return bool(engine._classify_confirm_and_route(step, strat, user_input))
    return False


def classifier_instruct_route(engine: Any, r, strat, step, user_input: str | None) -> bool:
    """ASKED INSTRUCT: the LLM classifier decides done-vs-still-doing, so a clear "I did
    it" phrased messily ("Gerai, jau įkišau") advances even when the keyword
    turn-intent reads it as in_progress and freezes the step (observed: dr_plug_pc
    froze, the bridge never bound). Keyword intent gate stays the fallback."""
    from .resolution import StepKind

    if (
        step.kind is StepKind.INSTRUCT
        and r.get("asked")
        and engine._asked_recently(r)
        and os.getenv("CLASSIFIER", "on").lower() != "off"
    ):
        return bool(engine._classify_instruct_and_advance(step, strat, user_input))
    return False


STEP_GUARDS = (
    device_change_pre_answer,
    backchannel_hold,
    restored_pre_answer,
    refuse_or_ticket_redirect,
    evidence_question_open_hold,
    classifier_confirm_route,
    classifier_instruct_route,
)

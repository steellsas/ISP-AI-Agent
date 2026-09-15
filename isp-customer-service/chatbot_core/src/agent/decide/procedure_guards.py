"""
Procedure step guards — the ordered pre-checks that decide whether a caller's
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

from ..contract.locale import vocab, vocab_set
from ..dialog_utils import asked_recently
from ..faults import CANNOT_NOW_ROLES

# --- prelude (no step resolved yet) -----------------------------------------


def question_priority_hold(state: Any, rt: Any, user_input: str | None) -> bool:
    """B-wave switch (Andrius 2026-09-08): the turn belongs to the
    HIGHEST-PRIORITY open question (safety > ident > ticket > walker). While
    a non-walker question is open, the walker must not read the turn as its
    step's answer — live P6: "Ne patogu" + an address question in one turn
    had the walker start a ticket over the safety ladder. The content is not
    lost: the evidence ingest still reads facts; the walker just holds."""
    from ..dialog_registry import OWNER_PRIORITY, active

    q = active(state, rt)
    if q is not None and OWNER_PRIORITY.get(q.owner, 99) < OWNER_PRIORITY["walker"]:
        rt.tracer.emit(
            "decision",
            intent="answer",
            action="hold",
            reason=f"question_registry:{q.owner}:{q.key}",
        )
        return True
    return False


def resume_hold(state: Any, rt: Any, user_input: str | None) -> bool:
    """One-turn hold after the caller declined to end the call — their "ne,
    tęskime" answers the confirm-end question, not the current step."""
    if state.dialog.resume_hold_due:
        state.dialog.resume_hold_due = False
        return True
    return False


def end_confirm_pending(state: Any, rt: Any, user_input: str | None) -> bool:
    """The confirm-end question is OUT and unanswered — in the graph's turn
    order the walker runs BEFORE the guard that reads its answer, so this
    reply belongs to that question, not the step (live 2026-08-11: "Ne,
    nenoriu" — i.e. don't END — advanced stale dr_intro -> escalate ->
    ticket). Hold; _pre_turn_guards resumes or closes this same turn."""
    if state.dialog.end_confirm_pending:
        rt.tracer.emit("decision", intent="answer", action="hold", reason="end_confirm_pending")
        return True
    return False


PRELUDE_GUARDS = (question_priority_hold, resume_hold, end_confirm_pending)


# --- step guards (ordered — see module docstring) ----------------------------


def device_change_pre_answer(state: Any, rt: Any, r, strat, step, user_input: str | None) -> bool:
    """A strong device-change signal advances confirm_device_change before it is even asked
    (the caller pre-answered, e.g. "neveikia, keičiau routerį"). ONLY for that step —
    elsewhere "kompiuteris" is a scope answer, not a device change. Runs before the
    intent gate: a clear pre-answer should move regardless of turn phrasing."""
    from ..perceive.detectors import confirms_device_change
    from ..resolution import next_step_id
    from .procedure import route_to

    if step.role == "confirm_device_change" and confirms_device_change(user_input):
        route_to(state, rt, r, next_step_id(strat, step.id, "yes"))
        return True
    return False


def homework_consent(state: Any, rt: Any, r, strat, step, user_input: str | None) -> bool:
    """P-C follow-up (live 2026-09-09, F1/F2): on the homework step a
    farewell ("Gerai, sutariam, viso gero"), a plain consent word or a
    first-person callback promise ("aš perskambinsiu") IS the yes — the
    caller agrees to do the homework and call back. Route to the callback
    terminal; an explicit ticket demand falls through to the refuse guard."""
    from ..perceive.detectors import detect_farewell
    from ..resolution import next_step_id
    from .procedure import route_to

    if step.role != "homework":
        return False
    low = (user_input or "").lower()
    tokens = {t.strip(".,!?") for t in low.split()}
    # A first-person callback promise wins outright — "nereikia susitikti,
    # aš perskambinsiu" refuses the MEETING, not the agreement.
    callback = any(m in low for m in vocab("will_call_back"))
    consent = detect_farewell(user_input) or bool(tokens & vocab_set("homework_agreed"))
    blocked = any(m in low for m in vocab("homework_blocked"))
    if callback or (consent and not blocked):
        route_to(state, rt, r, next_step_id(strat, step.id, "yes"))
        rt.tracer.emit("decision", intent="cannot_now", action="homework_agreed", from_step=step.id)
        return True
    return False


def backchannel_hold(state: Any, rt: Any, r, strat, step, user_input: str | None) -> bool:
    """A bare "Mhm." / one-letter STT crumb is an acknowledgement, not an answer —
    HOLD asking steps instead of routing garbage (observed: "T." entered the bridge
    path as "yes, I have a computer"; "Mhm." climbed two INSTRUCT steps). ACTION
    steps still advance — their announce needs no answer."""
    from ..perceive.detectors import is_backchannel
    from ..resolution import StepKind

    if step.kind in (StepKind.CONFIRM, StepKind.INSTRUCT) and is_backchannel(user_input):
        rt.tracer.emit(
            "decision", intent="backchannel", action="hold", from_step=step.id, to=step.id
        )
        return True
    return False


def restored_pre_answer(state: Any, rt: Any, r, strat, step, user_input: str | None) -> bool:
    """A clear "atsirado / veikia" pre-answers a restored CONFIRM before it was even
    asked — often fused with the goodbye ("yra internetas, ačiū, viso gero"). Route
    the YES so the resolve is RECORDED instead of the call dying unclosed on the
    hangup (observed live: resolved Wi-Fi call left outcome=None). Only the clear
    affirmative pre-answers; a "no" still waits for the step's own question."""
    from ..perceive.detectors import detect_restored
    from ..resolution import Outcome, next_step_id
    from .procedure import route_to

    if step.detector == "restored" and not r.get("asked"):
        if detect_restored(user_input) is Outcome.YES:
            route_to(state, rt, r, next_step_id(strat, step.id, "yes"))
            return True
    return False


def refuse_or_ticket_redirect(state: Any, rt: Any, r, strat, step, user_input: str | None) -> bool:
    """Refusal / explicit ticket demand ends troubleshooting in a REGISTRATION
    (policy 2026-07-30). A clear DEMAND ("įregistruokit gedimą") IS the consent —
    register now and close, with the reason on the ticket. A softer refusal
    ("nedarysiu", "nesu namuose") routes to the escalate step, whose consent
    question doubles as the polite clarification ("užregistruosiu — ar tinka?").
    Observed live: the caller demanded a ticket 3×, the narrator promised it 5×,
    and the walker held cable_check forever — no route existed."""
    from ..perceive.detectors import detect_refuse_or_ticket
    from ..resolution import StepKind
    from ..ticket_flow import begin_ticket_dialogue
    from .procedure import goto_step

    if step.kind is StepKind.ESCALATE:
        return False
    refusal = detect_refuse_or_ticket(user_input)
    escalate = strat.by_role("escalate")
    if refusal is None or escalate is None:
        return False
    # P-C (2026-09-08): an ability_check/locate_device/homework step's question IS
    # the pack's own cannot-now handling — a SOFT refusal ("nesu namuose")
    # is that question's answer and routes per the pack file (homework +
    # callback), never the generic escalate. An explicit ticket DEMAND
    # still wins — with the HONEST reason (nothing was done at the device).
    if step.role in CANNOT_NOW_ROLES:
        if refusal == "refuse":
            return False
        r["escalate_reason"] = "cannot_now_asks_ticket"
    else:
        r["escalate_reason"] = "caller_asked_ticket" if refusal == "demand" else "caller_refused"
    goto_step(state, rt, r, escalate.id)
    rt.tracer.emit(
        "decision", intent="refuse_or_ticket", action=refusal, from_step=step.id, to=escalate.id
    )
    if refusal == "demand":
        begin_ticket_dialogue(state, rt, escalate)
    return True


def evidence_question_open_hold(
    state: Any, rt: Any, r, strat, step, user_input: str | None
) -> bool:
    """Question OWNERSHIP (live 2026-08-11): while the evidence drive has an OPEN
    question, that is the question the caller is answering — the walker's own
    step question may be MANY turns stale. A barge-in-truncated "Ne." (meant:
    "ne, nedega…") was read by the stale dr_intro yes/no as "won't check
    together" → escalate → ticket → dead call. The asked-step routing below
    (classify + keyword) must not consume such a reply; explicit refusals and
    restored pre-answers were already handled above."""
    from ..evidence_drive import evidence_question_open

    if evidence_question_open(state, rt):
        rt.tracer.emit(
            "decision",
            intent="answer",
            action="hold",
            from_step=step.id,
            to=step.id,
            reason="evidence_question_open",
        )
        return True
    return False


def classifier_confirm_route(state: Any, rt: Any, r, strat, step, user_input: str | None) -> bool:
    """ASKED generic CONFIRM (yes/no, lights, scope, restored, …): the LLM classifier
    reads the answer AND whether it IS an answer in one call — so a confident answer
    advances even when the brittle keyword turn-intent would veto it (observed:
    "gerai, bandau… nė viena lemputė neužsidegė" was read as in_progress and froze
    dr_power). The keyword detector + intent gate stay as the fallback."""
    from ..resolution import StepKind
    from .procedure import classify_confirm_and_route

    if (
        step.kind is StepKind.CONFIRM
        and r.get("asked")
        and asked_recently(state, r)
        and step.on
        and step.role != "verify_restored"
        and os.getenv("CLASSIFIER", "on").lower() != "off"
    ):
        return bool(classify_confirm_and_route(state, rt, step, strat, user_input))
    return False


def classifier_instruct_route(state: Any, rt: Any, r, strat, step, user_input: str | None) -> bool:
    """ASKED INSTRUCT: the LLM classifier decides done-vs-still-doing, so a clear "I did
    it" phrased messily ("Gerai, jau įkišau") advances even when the keyword
    turn-intent reads it as in_progress and freezes the step (observed: dr_plug_pc
    froze, the bridge never bound). Keyword intent gate stays the fallback."""
    from ..resolution import StepKind
    from .procedure import classify_instruct_and_advance

    if (
        step.kind is StepKind.INSTRUCT
        and r.get("asked")
        and asked_recently(state, r)
        and os.getenv("CLASSIFIER", "on").lower() != "off"
    ):
        return bool(classify_instruct_and_advance(state, rt, step, strat, user_input))
    return False


STEP_GUARDS = (
    device_change_pre_answer,
    homework_consent,
    backchannel_hold,
    restored_pre_answer,
    refuse_or_ticket_redirect,
    evidence_question_open_hold,
    classifier_confirm_route,
    classifier_instruct_route,
)

# B2 (2026-08-21): the guards that READ the caller's answer into a route. In
# solver-driven packs they stay silent until the ledger hands over (see
# procedure.owns_answer); the policy guards above keep running.
ANSWER_GUARDS = (
    device_change_pre_answer,
    restored_pre_answer,
    classifier_confirm_route,
    classifier_instruct_route,
)

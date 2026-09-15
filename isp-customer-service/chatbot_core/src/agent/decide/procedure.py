"""The procedure runner — walks the active fault's steps from the caller's answer.

While a procedure is active, the caller's answer to its awaited step belongs to the
procedure (`owns_answer`); the diagnosis rules regain control when it exits, on a
contradiction, a refusal or ticket demand, or a new problem / side topic. `advance`
returns the StepOutcome: advance to a step role, exit (success / failure), or hold.
The step guards (decide/procedure_guards.py) run first, in their load-bearing order."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from ..contract import limits
from ..contract.locale import phrase
from ..dialog_utils import asked_recently, last_agent_question
from ..execute import diagnosis as _diagnosis
from ..faults import role_of, verdict_flag
from ..trace import emit_decision, trace_note
from . import hypothesis as _hypothesis


@dataclass(frozen=True)
class StepOutcome:
    """What the caller's answer did to the procedure this turn."""

    kind: Literal["advance", "hold", "exit"]
    role: str | None = None  # the step role now awaited (advance / hold)
    exit: Literal["success", "failure", "callback"] | None = None


def advance(state, rt, user_input: str | None) -> StepOutcome:
    """Walk the procedure from the caller's reply, trace WHY it moved (or did not) —
    the decision record is what makes a failed call debuggable — and return the
    outcome."""
    r = state.resolution.procedure
    before = r.get("step") if r else None
    # Ledger: a fresh evidence conflict holds the procedure THIS turn — the
    # contradicting utterance must not double as a step answer; the scripted
    # clarification goes out instead and the settling answer resumes.
    if state.diagnosis.evidence_conflict:
        rt.tracer.emit(
            "decision",
            intent="evidence_conflict",
            action="hold",
            key=state.diagnosis.evidence_conflict.key,
        )
    else:
        walk_resolution(state, rt, user_input)
        emit_decision(rt.tracer, state, before)
    return _outcome(state, before)


def _outcome(state, before: str | None) -> StepOutcome:
    r = state.resolution.procedure or {}
    if state.closing.case_closed:
        reason = state.closing.closed_reason
        return StepOutcome(
            "exit",
            exit="success"
            if reason == "resolved"
            else ("callback" if reason == "callback" else "failure"),
        )
    if state.ticket.stage:
        return StepOutcome("exit", exit="failure")  # the procedure escalated to a registration
    role = role_of(r.get("verdict"), r.get("step")) if r.get("step") else None
    return StepOutcome("advance" if r.get("step") != before else "hold", role=role)


def owns_answer(state, rt, r: dict, step) -> bool:
    """B2: may the walker READ this turn's answer? Packs without evidence: always.
    Evidence-led packs: only once the evidence layer handed over — the
    solution step was synced (`solution_synced`), the bridge is bound, or the
    step is a verify/escalate outcome step (telemetry + outcome, not a
    diagnostic fact the ledger collects)."""
    from ..faults import evidence_led
    from ..resolution import StepKind

    if not evidence_led(r.get("verdict")):
        return True
    if r.get("solution_synced") or state.resolution.bridge_bound:
        return True
    if step.kind in (StepKind.ESCALATE, StepKind.VERIFY):
        return True
    return step.role in ("verify_restored", "verify_device_visible")


def walk_resolution(state, rt, user_input: str | None) -> None:
    """Generic step-by-step walker over the active strategy, from the caller's
    reply. Uniform for all fault types:

    - INSTRUCT / ACTION: a guided step. Once its instruction (or the bind
      announce) has been presented, ANY caller reply — they did it / answered —
      advances to the next step. One instruction per turn, listen, move on.
    - CONFIRM: branches on yes/no (and a strong device-change pre-answer).
    - verify_restored: a VERIFY that blends the caller's word with a fresh
      telemetry read — routed separately (_advance_restored).

    This is what leads the caller one step at a time instead of dumping the
    whole playbook, and stops the model binding a device they never confirmed.

    The pre-checks live in procedure_guards.py (R3, roadmap §5) as an ordered,
    individually-named chain; this method keeps only the mechanics — intent
    derivation, the guard iteration and the advancement dispatch below."""
    from ..perceive.detectors import detect_turn_intent
    from ..resolution import StepKind, get_strategy, next_step_id
    from . import procedure_guards

    r = state.resolution.procedure
    if not r or state.closing.case_closed:
        return
    for guard in procedure_guards.PRELUDE_GUARDS:
        if guard(state, rt, user_input):
            return
    # Derive the intent from THIS call's input rather than trusting it was set
    # earlier — the walker must not depend on the caller's ordering.
    state.dialog.last_intent = detect_turn_intent(user_input)
    strat = get_strategy(r.get("verdict"))
    step = strat.step(r.get("step", "")) if strat else None
    if step is None:
        return
    # B2 (Andrius 2026-08-21): in SOLVER-driven packs the LEDGER owns the
    # evidence-collection phase — the walker reads NO answers until the
    # evidence layer hands over (solution synced / bridge bound / escalate /
    # verify steps). Two readers raced live: the stale dr_lights question ate
    # "taip, turiu kompiuterį" as "dega" and sent the call down the healthy-
    # router branch. One source of truth: the walker is a pointer, synced
    # FROM the ledger, until it legitimately owns the execution.
    owns = owns_answer(state, rt, r, step)
    for guard in procedure_guards.STEP_GUARDS:
        if not owns and guard in procedure_guards.ANSWER_GUARDS:
            continue  # policy guards still run; answer readers stay silent
        if guard(state, rt, r, strat, step, user_input):
            return
    if not owns:
        return
    # ESCALATE = deterministic OUTCOME (Phase 3.11 B). The step is a call-ending
    # consent question ("užregistruosiu gedimą — ar tinka?"): the ENGINE registers
    # the ticket from STATE on consent and closes; a decline closes without a
    # ticket. create_ticket is no longer an LLM-callable tool mid-strategy, so the
    # model can neither freelance a ticket nor loop the consent question (observed
    # live: 4× "ar tinka?" — the ticket only landed via the gate bailout).
    if step.kind is StepKind.ESCALATE:
        advance_escalate(state, rt, r, step, user_input)
        return
    # What KIND of turn was this? Only a real answer or a completed action may move
    # the conversation. "Einu prie routerio", a question, confusion or silence all
    # HOLD the step — the agent responds to them instead of running ahead.
    if not turn_may_advance(state, rt, step):
        return
    # verify_restored blends the caller's word with a fresh telemetry read.
    if step.role == "verify_restored":
        advance_restored(state, rt, r, user_input)
        return
    # verify_reboot (S6 hung router): caller's word + fresh telemetry + the reboot
    # witness (did the device actually drop off the line?) — routed separately.
    if step.role == "verify_reboot":
        advance_reboot_check(state, rt, r, user_input)
        return
    # NT line faults (2026-09-11): the cable-reseat check re-reads the port /
    # CRC level and blends it with the caller's word.
    if step.role == "verify_line":
        advance_line_check(state, rt, r, user_input)
        return
    # Bridge: did the device they just plugged in actually appear on the line?
    if step.role == "verify_device_visible":
        advance_see_device(state, rt, r)
        return
    # A guided instruction / the bind announce: advance on ANY reply, once it was
    # presented last turn — to an explicit goto if set, else the next step in order.
    if step.kind in (StepKind.INSTRUCT, StepKind.ACTION):
        if r.get("asked"):
            advance_instruct(state, rt, r, step, strat, user_input)
        return
    if step.kind != StepKind.CONFIRM:
        return
    # Otherwise route only once the question was asked — a bare "taip" on the
    # diagnose turn is the address confirmation, not an answer to this step.
    # A STALE question (walker benched for turns) does not read answers either.
    if not r.get("asked") or not asked_recently(state, r):
        return
    # Keyword fallback (classifier off / unsure): read the reply into a routing key.
    key = detect_confirm(state, rt, step, user_input)
    if key is None:
        return
    if block_uncorroborated_escalate(state, rt, step, strat, key, user_input):
        return  # clarify goes out instead; the step holds
    route_to(state, rt, r, next_step_id(strat, step.id, key))


def block_uncorroborated_escalate(state, rt, step, strat, label, user_input: str | None) -> bool:
    """A bare "Ne."-style reply about to route the walker into ESCALATE — a
    one-way door to the ticket dialogue — needs a second source agreeing it
    really is a refusal (the understanding pass reading a confident answer).
    Without it, ask the solve-or-ticket clarify ONCE instead and hold
    (Andrius 2026-08-11: clarify what the "ne" means, never rush the
    conclusion). A repeated no on the next turn escalates normally."""
    from ..perceive.detectors import is_bare_negation
    from ..resolution import StepKind, next_step_id

    target = next_step_id(strat, step.id, label)
    tstep = strat.step(target) if strat and target else None
    if tstep is None or tstep.kind is not StepKind.ESCALATE:
        return False
    if not is_bare_negation(user_input):
        return False
    if state.resolution.escalate_clarify_asked:
        return False  # clarified once already — a repeated no is a real no
    u = state.turn.understanding
    if (
        u is not None
        and u.get("type") == "answer"
        and (u.get("confidence") or 0) >= limits.get("understand_facts_min_confidence")
    ):
        return False  # two sources agree on the refusal — escalate may proceed
    state.resolution.escalate_clarify_asked = True
    state.resolution.escalate_clarify_due = True
    rt.tracer.emit(
        "decision",
        intent="answer",
        action="clarify",
        from_step=step.id,
        to=target,
        reason="bare negation, no corroboration",
    )
    return True


def _cached_perception(state, rt, step, user_input: str | None):
    """The merged perception call's step read for THIS step + THIS utterance,
    or None (walker then falls back to the standalone classifier)."""
    cached = state.turn.perception_step
    if not cached or cached.get("step_id") != step.id or cached.get("input") != user_input:
        return None
    from ..classifier import CandidateObservation

    try:
        return CandidateObservation(**cached["obs"])
    except Exception:  # pragma: no cover - defensive
        return None


def classify_confirm_and_route(state, rt, step, strat, user_input: str | None) -> bool:
    """Classifier-led routing for an asked CONFIRM step. One LLM call reads BOTH the
    answer (into a routing key) and whether it IS an answer. A confident answer
    advances the walker (overriding a brittle keyword turn-intent); anything unsure
    returns False → the keyword detector + intent gate handle it. Sensor only."""
    from ..classifier import classify_step
    from ..detectors import glosses as detector_glosses
    from ..faults import step_options
    from ..resolution import next_step_id

    # R4 perception merge: the understanding pass already classified this reply
    # against THIS step's keys in the same LLM call — consume the cached read
    # instead of a second round-trip. Fallback (cache miss / UNDERSTAND off):
    # the standalone classifier exactly as before.
    obs = _cached_perception(state, rt, step, user_input)
    if obs is None:
        detector_name = step.detector or "yes_no"
        # WHAT TO DETECT comes from the fault definition first (knowledge/faults.yaml —
        # per-step, so it can be worded precisely for THIS check), falling back to the
        # universal per-detector glosses (knowledge/detectors.yaml, code as last
        # resort). A reworded check is a file edit, not code.
        declared = step_options((state.resolution.procedure or {}).get("verdict"), step.id)
        glosses = detector_glosses(detector_name)
        options: dict[str, str] = {}
        for raw in step.on:
            # Some steps key `on` by the Outcome enum — str(Outcome.YES) is "Outcome.YES",
            # so take .value to get the real routing key ("yes") the classifier must return.
            key = str(getattr(raw, "value", raw))
            options[key] = (declared or {}).get(key) or glosses.get(key, key)
        question = last_agent_question(state) or step.hint or ""
        obs = classify_step(question, user_input or "", options, model=rt.config.model)
    if obs is None:
        trace_note(
            rt.tracer,
            state,
            "classifier",
            f"{step.detector or 'yes_no'}: no result → keyword",
        )
        return False
    answered = (
        obs.is_answer
        and obs.label in step.on
        and obs.confidence >= limits.get("classifier_accept_confidence")
    )
    rt.tracer.emit(
        "classify",
        detector=step.detector or "yes_no",
        step=step.id,
        label=obs.label,
        is_answer=obs.is_answer,
        confidence=obs.confidence,
        inconsistent=obs.internally_inconsistent,
        text=user_input,
        routed_by=("classifier" if answered else "keyword"),
    )
    if answered:
        if block_uncorroborated_escalate(state, rt, step, strat, obs.label, user_input):
            return True  # clarify goes out instead; the step holds
        state.dialog.awaiting = None
        state.dialog.awaiting_turns = 0
        state.dialog.step_confusions = 0
        state.dialog.last_intent = "answer"
        route_to(state, rt, state.resolution.procedure, next_step_id(strat, step.id, obs.label))
        return True
    return False


def advance_instruct(state, rt, r: dict, step, strat, user_input: str | None = None) -> None:
    """Advance a presented INSTRUCT/ACTION step to its goto (or the next step in order).
    Shared by the keyword path and the classifier gate. The verify_device_visible VERIFY is
    engine-owned, so resolve it in the SAME turn (reflect the plug-in in the demo, then
    read the line) instead of asking a dead question."""
    from ..executor_flow import simulate_bridge_connection, simulate_router_reboot_action
    from ..perceive.detectors import detect_restored
    from ..resolution import Outcome, StepKind, next_step_id
    from ..solver_flow import plug_report

    route_to(state, rt, r, step.goto or next_step_id(strat, step.id, None))
    # Skipped-ahead caller (live 2026-08-24): still on locate_cable, the caller
    # reported the cable ALREADY in the computer ("jau įkišau į kompiuterį").
    # One advance lands on the plug step and dictates an instruction they have
    # done. When the SAME utterance is a completed plug-into-computer report,
    # that instruct step is done too — fall through to its goto so the verify
    # runs this turn instead of a dead instruction.
    skipped = strat.step(r.get("step", "")) if strat else None
    if (
        skipped is not None
        and skipped.id != step.id
        and skipped.kind in (StepKind.INSTRUCT, StepKind.ACTION)
        and plug_report(state, rt, user_input)
    ):
        route_to(state, rt, r, skipped.goto or next_step_id(strat, skipped.id, None))
    current_role = role_of(r.get("verdict"), r.get("step"))
    if current_role == "verify_device_visible":
        simulate_bridge_connection(state, rt)
        advance_see_device(state, rt, r)
        return
    # verify_reboot (S6): an engine-owned BLEND step — never keyword-route it from
    # the completing utterance (a false "gerai" YES sent the flow into the
    # retry branch, eval S6). Reflect the claimed reboot in the demo world
    # (SIMULATE_REBOOT, eval only — live calls use the button), record
    # telemetry; the check question goes out this turn and the caller's
    # ANSWER decides on the next one.
    if current_role == "verify_reboot":
        simulate_router_reboot_action(state, rt)
        advance_reboot_check(state, rt, r, user_input)
        return
    # verify_line steps are engine-owned BLEND steps too — never let the
    # completing utterance keyword-route them (live 2026-09-11: "perkišau,
    # nepadėjo" matched the loose restored-YES vocabulary and closed a damaged
    # cable as resolved without the telemetry read).
    if current_role == "verify_line":
        advance_line_check(state, rt, r, user_input)
        return
    # Carry-through pre-answer: the utterance that completed the instruction often
    # already reports the outcome ("prisijungiau iš naujo — jau veikia"). If we just
    # landed on a restored CONFIRM and the SAME reply carries a clear YES, route it
    # now — otherwise that answer dies unheard and the caller's NEXT turn (often a
    # farewell, "Ne, ačiū") gets misread as the verify answer (observed live:
    # resolved call routed to escalate).
    new_step = strat.step(r.get("step", "")) if strat else None
    if (
        new_step is not None
        and new_step.detector == "restored"
        and detect_restored(user_input) is Outcome.YES
    ):
        route_to(state, rt, r, next_step_id(strat, new_step.id, "yes"))


def classify_instruct_and_advance(state, rt, step, strat, user_input: str | None) -> bool:
    """Classifier-led advancement for an asked INSTRUCT step: did the caller actually
    DO it, or are they still doing it / asking? A confident 'done' advances even when
    the keyword turn-intent misreads a messy done-signal as in_progress. Anything else
    returns False → the keyword intent gate decides. Sensor only."""
    from ..classifier import classify_step
    from ..detectors import glosses as detector_glosses

    # R4 perception merge first (cached same-call read), classifier fallback.
    obs = _cached_perception(state, rt, step, user_input)
    if obs is None:
        # Meanings come from knowledge/detectors.yaml (file-editable), code fallback.
        options = detector_glosses("instruct_done")
        question = last_agent_question(state) or step.hint or ""
        obs = classify_step(question, user_input or "", options, model=rt.config.model)
    if obs is None:
        return False
    done = obs.label == "done" and obs.confidence >= limits.get("classifier_accept_confidence")
    rt.tracer.emit(
        "classify",
        detector="instruct_done",
        step=step.id,
        label=obs.label,
        is_answer=obs.is_answer,
        confidence=obs.confidence,
        text=user_input,
        routed_by=("classifier" if done else "keyword"),
    )
    if done:
        state.dialog.awaiting = None
        state.dialog.awaiting_turns = 0
        state.dialog.step_confusions = 0
        state.dialog.last_intent = "done"
        advance_instruct(state, rt, state.resolution.procedure, step, strat, user_input)
        return True
    # Classifier VETO: the classifier RAN and did NOT say "done" (waiting OR
    # unclear) — HOLD the step unless the keyword intent is an explicit DONE
    # ("padariau", "patikrinau"), which outranks a soft classifier read (observed:
    # "Patikrinau, WiFi įjungtas" held as waiting slipped the resolve a turn).
    # Unclear included: the loose any-'answer' keyword path had advanced INSTRUCT
    # steps on garbage ("Įsitikimu, kad tai yra neturis" climbed dr_plug_pc live).
    from ..perceive.detectors import INTENT_DONE, detect_turn_intent

    return detect_turn_intent(user_input) != INTENT_DONE


def detect_confirm(state, rt, step, user_input: str | None):
    """Keyword FALLBACK detector for a CONFIRM reply — used when the classifier is off
    or unsure (the classifier-led path is _classify_confirm_and_route). Returns a
    routing key or None."""
    from ..perceive.detectors import DETECTORS

    keyword = DETECTORS.get(step.detector or "yes_no", DETECTORS["yes_no"])
    return keyword(user_input)


def turn_may_advance(state, rt, step) -> bool:
    """May the caller's turn move the walker forward?

    Only a real ANSWER or a completed action does. "Einu prie routerio" is work in
    progress, a question needs answering, confusion needs a finer explanation, and
    silence needs waiting — none of them mean the step is finished. Before this,
    every non-answer fell through to "repeat the question", which is how the agent
    ran ahead of the caller (it read a plugged-in-yet? check before they had
    plugged anything in) and repeated itself six turns running.

    Unknown is deliberately treated as an ANSWER only for CONFIRM steps, where a
    detector still has to agree — elsewhere it holds. Safe default: wait and ask."""
    from ..perceive.detectors import INTENT_ANSWER, INTENT_DONE, INTENT_IN_PROGRESS, INTENT_UNKNOWN
    from ..resolution import StepKind

    s = state
    from ..perceive.detectors import INTENT_CONFUSED

    intent = s.dialog.last_intent or INTENT_UNKNOWN
    if intent in (INTENT_ANSWER, INTENT_DONE):
        s.dialog.awaiting = None
        s.dialog.awaiting_turns = 0
        s.dialog.step_confusions = 0  # they got past this one
        return True
    if intent == INTENT_CONFUSED:
        # Each "I don't follow" on the SAME step earns a smaller piece of it.
        s.dialog.step_confusions += 1
    # Still waiting on the same thing — count the turns so the agent can check in
    # ("ar pavyksta?") instead of silently re-asking the same sentence.
    s.dialog.awaiting = (
        "client_action"
        if (intent == INTENT_IN_PROGRESS or step.kind is StepKind.INSTRUCT)
        else "client_answer"
    )
    s.dialog.awaiting_turns += 1
    return False


def advance_see_device(state, rt, r: dict) -> None:
    """Bridge check: after the caller plugs a computer into the wall cable, does the
    line actually SEE a device? Telemetry answers this, not the caller — binding
    blindly when the cable is in the wrong socket would fail confusingly. Seen ->
    bind; not seen after two tries -> the cable is wrong, walk it back."""
    reason = _diagnosis.fresh_diagnose_reason(state, rt)
    seen = verdict_flag(reason, "device_visible")  # any other verdict means a device is there
    r["device_seen"] = seen
    _hypothesis.note_evidence(
        state,
        rt,
        "the connected device is seen on the line" if seen else "still no device seen on the line",
    )
    if seen:
        goto_role(state, rt, r, "bind_device")
        return
    r["plug_retries"] = int(r.get("plug_retries", 0)) + 1
    if r["plug_retries"] >= limits.get("bridge_plug_retries_max"):
        goto_role(state, rt, r, "escalate")
    else:
        goto_role(state, rt, r, "locate_cable")  # wrong cable/socket — try again


def reject_and_rediagnose(state, rt, r: dict) -> bool:
    """The fix ran but the line is still down: reject THIS hypothesis and look for
    another one before giving up.

    Re-reads telemetry through the normal path so state.diagnosis and the strategy
    pivot both update (the pivot skips anything already in failed_hypotheses).
    Returns True when a genuinely NEW strategy took over — the agent has a Plan B
    and says so (see `pivoted_from`); False when nothing new is left, so the caller
    escalates. Without this the FIRST failed fix ended in a ticket even when the
    telemetry had started pointing at a different fault."""
    s = state
    verdict = r.get("verdict")
    if verdict and verdict not in s.diagnosis.failed_hypotheses:
        s.diagnosis.failed_hypotheses.append(verdict)
    _hypothesis.settle_hypothesis(
        state, rt, "rejected", "the connection did not recover after the action (telemetry)"
    )
    s.diagnosis.verdicts.pop("network", None)  # let ensure_diagnosed re-read the line
    _diagnosis.ensure_diagnosed(state, rt)
    new = (s.resolution.procedure or {}).get("verdict")
    if new and new != verdict and new not in s.diagnosis.failed_hypotheses:
        s.diagnosis.pivoted_from = verdict  # narrate the rethink once, then clear
        return True
    return False


def route_to(state, rt, r: dict, target: str) -> None:
    """Apply a routing target: the 'resolve'/'end'/'callback' terminals close
    the case; any other id is a real step to advance to. Centralises terminal
    handling so every branch (including client-side check -> resolve) actually
    closes."""
    if target == "resolve":
        state.closing.case_closed = True
        state.closing.closed_reason = "resolved"
        # The fix worked, so the cause we were testing was the right one — the
        # agent can now say so ("taigi dėl X ir nebuvo interneto").
        _hypothesis.settle_hypothesis(state, rt, "confirmed", "sutvarkius problema dingo")
    elif target == "callback":
        # P-C (Andrius 2026-09-08): the caller agreed to do the homework and
        # call back — a warm callback close, never pressure into a ticket.
        state.closing.case_closed = True
        state.closing.closed_reason = "callback"
        state.closing.callback_goodbye_due = True  # scripted speaks callback_goodbye
        rt.tracer.emit("decision", intent="cannot_now", action="callback_close")
    elif target == "end":
        state.closing.case_closed = True
        state.closing.closed_reason = state.closing.closed_reason or "declined"
    else:
        # P-E: escalating out of the homework step means nothing was done at
        # the device — the ticket intro must speak the honest state.
        if role_of(r.get("verdict"), target) == "escalate" and (
            role_of(r.get("verdict"), r.get("step")) == "homework"
        ):
            r.setdefault("escalate_reason", "cannot_now")
        goto_step(state, rt, r, target)


def advance_restored(state, rt, r: dict, user_input: str | None) -> None:
    """After binding, decide from BOTH the caller's word and a fresh telemetry
    read (re-read each turn — a bind can take a minute to come up):

    - caller says it works                 -> resolved
    - caller says NO, provider side OK      -> client-side fault (Wi-Fi/device)
    - caller says NO, provider not yet OK   -> wait (reassure); after a second
                                               denial with still-no-line, escalate
    An unclear answer stays and re-asks."""
    from ..perceive.detectors import detect_restored
    from ..resolution import Outcome

    reason_now = _diagnosis.fresh_diagnose_reason(state, rt)
    fixed = not verdict_flag(reason_now, "unresolved_after_fix")
    r["telemetry_fixed"] = fixed
    if not r.get("asked"):
        return  # question not asked yet (the bind turn) — just record telemetry
    outcome = detect_restored(user_input)
    if outcome == Outcome.YES:
        state.closing.case_closed = True
        state.closing.closed_reason = "resolved"
        _hypothesis.settle_hypothesis(state, rt, "confirmed", "klientas patvirtino, kad veikia")
        return
    if outcome == Outcome.NO:
        if fixed:
            # Provider side restored but the caller still has no internet — the
            # fault is inside the home. Pivot to the client-side step.
            goto_role(state, rt, r, "client_side_check")
        else:
            r["restored_denials"] = int(r.get("restored_denials", 0)) + 1
            if r["restored_denials"] >= limits.get("restored_denials_max"):
                # The bind has not taken after waiting. Don't register yet: reject
                # this hypothesis and see whether the telemetry now points at a
                # different fault. Only escalate when there is no Plan B.
                if not reject_and_rediagnose(state, rt, r):
                    goto_role(state, rt, r, "escalate")
            # else: stay, reassure it may take a couple of minutes (see hint)
        return


def _classify_reboot_check(state, rt, user_input: str | None) -> str | None:
    """Classifier fallback for the verify_reboot answer when the keyword detector
    is unsure — same order as CONFIRM steps. Meanings come from the pack's
    `answers:` (step_options), generic reboot_check glosses as fallback."""
    if os.getenv("CLASSIFIER", "on").lower() == "off":
        return None
    from ..classifier import classify_step
    from ..detectors import glosses as detector_glosses
    from ..faults import step_options

    r = state.resolution.procedure or {}
    options = step_options(r.get("verdict"), r.get("step")) or detector_glosses("reboot_check")
    obs = classify_step(
        last_agent_question(state) or phrase("solver.reboot_check_question"),
        user_input or "",
        options,
        model=rt.config.model,
    )
    if (
        obs is not None
        and obs.is_answer
        and obs.confidence >= limits.get("classifier_accept_confidence")
    ):
        return str(obs.label)
    return None


def advance_line_check(state, rt, r: dict, user_input: str | None) -> None:
    """verify_line (NT, Andrius 2026-09-11): after the cable
    reseat the ENGINE re-reads the line and blends it with the caller's word
    — the reboot-check pattern for the LINE faults.

    Routes:
    - fresh read still a line fault -> the honest escalate (the cable run is
      damaged; a technician must come out), whatever the caller said;
    - line recovered + caller YES -> resolved, no ticket;
    - line recovered but caller NO -> escalate (the technician sorts the
      rest; the note says the line itself came back);
    - unclear caller word with a recovered line -> hold, the step re-asks."""
    from ..perceive.detectors import detect_restored
    from ..resolution import Outcome

    if not r.get("asked"):
        return
    reason_now = _diagnosis.fresh_diagnose_reason(state, rt)
    if verdict_flag(reason_now, "line_fault"):
        r["escalate_reason"] = "line_not_restored"
        goto_role(state, rt, r, "escalate")
        rt.tracer.emit("decision", intent="line_check", action="still_down", reason=reason_now)
        return
    outcome = detect_restored(user_input)
    if outcome is Outcome.YES:
        route_to(state, rt, r, "resolve")
        rt.tracer.emit("decision", intent="line_check", action="resolved")
        return
    if outcome is Outcome.NO:
        r["escalate_reason"] = "caller_still_down"
        goto_role(state, rt, r, "escalate")
        rt.tracer.emit("decision", intent="line_check", action="line_ok_caller_no")
        return
    rt.tracer.emit("decision", intent="line_check", action="hold")


def advance_reboot_check(state, rt, r: dict, user_input: str | None) -> None:
    """S6 hung router: after the guided power-cycle, decide from the caller's
    word AND two telemetry facts read together (Andrius 2026-08-31):

      1. did TRAFFIC return (the hang cleared), and
      2. was the reboot actually WITNESSED — a real power-cycle drops the
         device off the line, so the port flaps (signals.port_flap_recent).

    Routes:
    - caller YES + telemetry agrees (traffic back OR the flap witnessed)
                                                  -> resolved, NO ticket
    - caller YES, telemetry disagrees (still hung, no flap) -> the words say
      "works" but the system saw neither traffic nor a reboot — treat like
      the wrong-device case: ONE retry with the clarification (VERIFICATION
      RULE, DIALOGO_ETALONAS.md #8: the caller's word alone is not enough)
    - caller NO + traffic returned                -> the router is alive;
                                                     the problem is on the path
                                                     to one device (device_path)
    - caller NO + no flap seen                    -> the wrong thing was
                                                     power-cycled (extension
                                                     cord / button / a second
                                                     router) — ONE retry with
                                                     the clarification, then
                                                     escalate
    - caller NO + flap seen, traffic still gone   -> rebooted but did not
                                                     recover — failing router,
                                                     escalate (ticket note says
                                                     "perkrauta, neatsistatė")
    An unclear answer holds the step (re-ask). The answer is read by the
    DEDICATED reboot_check detector (negation wins; "dega" alone is unclear
    — live 2026-08-31: the generic restored vocabulary read "jos nemirksi"
    as YES via the "jo" substring) with the classifier settling the rest
    through the pack's `answers:` glosses."""
    from ..perceive.detectors import detect_reboot_check
    from ..resolution import Outcome

    payload = _diagnosis.fresh_diagnose(state, rt)
    verdict = (payload or {}).get("verdict") or {}
    signals = (payload or {}).get("signals") or {}
    reason_now = verdict.get("reason")
    telem_ok = isinstance(payload, dict) and reason_now is not None
    flap = bool(signals.get("port_flap_recent"))
    r["telemetry_fixed"] = telem_ok and not verdict_flag(reason_now, "unresolved_after_fix")
    if not r.get("asked"):
        return  # the check question goes out this turn — just record telemetry
    outcome = detect_reboot_check(user_input)
    if outcome is None:
        label = _classify_reboot_check(state, rt, user_input)
        outcome = {"yes": Outcome.YES, "no": Outcome.NO}.get(label or "")
    if outcome == Outcome.YES:
        # The caller's word closes ONLY with the telemetry's agreement:
        # traffic back, the reboot witnessed, or telemetry unreachable
        # (then the word is all we have). Still hung with no flap = neither
        # source saw anything change -> the wrong-device retry path.
        if r.get("telemetry_fixed") or flap or not telem_ok:
            state.closing.case_closed = True
            state.closing.closed_reason = "resolved"
            _hypothesis.settle_hypothesis(
                state, rt, "confirmed", "the connection recovered after the reboot"
            )
            return
        outcome = Outcome.NO  # fall through to the no-flap retry below
    if outcome != Outcome.NO:
        return  # unclear -> stay on the reboot check, re-ask
    if r.get("telemetry_fixed"):
        _hypothesis.note_evidence(
            state,
            rt,
            "telemetry: traffic is back — the line works, the problem is on the device side",
        )
        goto_role(state, rt, r, "device_path")
        return
    if telem_ok and not flap:
        # The device never dropped off the line — no real power-cycle happened.
        _hypothesis.note_evidence(
            state,
            rt,
            "telemetry: the device NEVER dropped off the line — no full reboot was seen "
            "(an extension cord / a button / another device?)",
        )
        r["reboot_retries"] = int(r.get("reboot_retries", 0)) + 1
        if r["reboot_retries"] >= limits.get("reboot_retries_max"):
            goto_role(state, rt, r, "escalate")
        else:
            goto_role(state, rt, r, "reboot_retry")
        return
    # Rebooted (or telemetry unavailable) and still no traffic — give the other
    # hypotheses a chance before the ticket, exactly like a failed bind.
    if telem_ok:
        _hypothesis.note_evidence(
            state,
            rt,
            "telemetry: the reboot was seen, but traffic did not return — the router does not recover",
        )
    if not reject_and_rediagnose(state, rt, r):
        goto_role(state, rt, r, "escalate")


def advance_escalate(state, rt, r: dict, step, user_input: str | None) -> None:
    """Deterministic OUTCOME for an ESCALATE step (Phase 3.11 B). Once the consent
    question was posed (asked), the caller's reply decides:
      consent  -> the ENGINE registers the ticket from STATE and closes,
      decline  -> close WITHOUT a ticket (closed_reason='declined'),
      unclear  -> hold; the narrator re-asks (stuck-guard still backstops).
    The LLM only phrases — it can no longer call create_ticket itself."""
    from ..ticket_flow import begin_ticket_dialogue

    if not step.consent:
        return  # auto-register step — ensure_action_done handles it on arrival
    if not r.get("asked"):
        return  # consent question not posed yet — narrator asks it this turn
    from ..classifier import classify_step
    from ..detectors import glosses as detector_glosses
    from ..perceive.detectors import detect_ticket_consent

    label = detect_ticket_consent(user_input)
    routed_by = "keyword"
    # Keyword miss -> LLM classifier (same order as CONFIRM steps: the model reads
    # messy phrasing the wordlist can't — "na jo, tebūnie", garbled STT).
    if label is None and os.getenv("CLASSIFIER", "on").lower() != "off":
        obs = classify_step(
            last_agent_question(state) or str(step.hint or ""),
            user_input or "",
            # Meanings from knowledge/detectors.yaml (file-editable), code fallback.
            detector_glosses("ticket_consent"),
            model=rt.config.model,
        )
        if (
            obs is not None
            and obs.is_answer
            and obs.confidence >= limits.get("classifier_accept_confidence")
        ):
            label = obs.label
            routed_by = "classifier"
    rt.tracer.emit(
        "classify",
        detector="ticket_consent",
        step=step.id,
        label=label,
        is_answer=label is not None,
        confidence=1.0 if label else 0.0,
        text=user_input,
        routed_by=routed_by,
    )
    if label == "yes":
        begin_ticket_dialogue(state, rt, step)  # contacts first, then register+close
    elif label == "no":
        state.closing.case_closed = True
        state.closing.closed_reason = "declined"


def goto_role(state, rt, r: dict, role: str) -> bool:
    """Move the strategy to its step with `role` (False when the pack has none)."""
    from ..faults import step_by_role

    step = step_by_role(r.get("verdict"), role)
    if step is None:
        return False
    goto_step(state, rt, r, step.id)
    return True


def goto_step(state, rt, r: dict, next_id: str) -> None:
    """Move the strategy to `next_id`. When the step actually changes, clear the
    'asked' flag so the NEXT step (e.g. a second CONFIRM like check_cable) waits
    for its OWN question to be asked before a plain yes/no can advance it."""
    if next_id != r.get("step"):
        r["asked"] = False
        # Process journal (awareness №3): the walk's transitions — the
        # solver reads WHAT already happened instead of re-deriving it.
        journal = r.setdefault("journal", [])
        journal.append(f"{r.get('step') or '—'}→{next_id}")
        keep = limits.get("process_journal_max")
        if len(journal) > keep:
            del journal[:-keep]
    r["step"] = next_id

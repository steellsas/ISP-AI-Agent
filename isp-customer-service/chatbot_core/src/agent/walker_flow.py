"""
Walker flow — deterministic step walking: diagnose-once, the guard-chain
walker, per-kind advancement, hypothesis bookkeeping and the escalate outcome.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of
ReactAgent. The pure sequencer (next_step_id, detectors, strategies) stays in
agent/resolution.py; the guard chain lives in agent/walker_guards.py.
Functions take the engine explicitly; intra-family calls go through the
engine delegate seam (engine._x) so subclass overrides and test patches keep
working. execute_tool is resolved lazily from react_agent so the tests'
import-fallback stubs apply.
"""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import logging
import os  # noqa: F401
from typing import Any  # noqa: F401

from .glossary import DIAGNOSIS_LT as _DIAGNOSIS_LT  # noqa: F401

logger = logging.getLogger(__name__)


def execute_tool(name, args):
    """Lazy pass-through to react_agent's execute_tool (test stubs included)."""
    from . import react_agent

    return react_agent.execute_tool(name, args)


def fresh_diagnose_reason(engine) -> str | None:
    """Re-read telemetry now and return the verdict reason (or None on error).
    Read-only — used to VERIFY a fix actually took before closing/acting."""
    if not engine.state.customer_id:
        return None
    try:
        d = json.loads(
            execute_tool("diagnose_connection", {"customer_id": engine.state.customer_id})
        )
        return (d.get("verdict") or {}).get("reason")
    except Exception:  # pragma: no cover - best-effort
        return None


def ensure_diagnosed(engine) -> bool:
    """Deterministically run diagnose_connection the first time we enter the
    diagnosis stage (customer identified), so the verdict + strategy are set
    BEFORE the model narrates. The flow no longer depends on the model choosing
    to diagnose — which it did inconsistently (sometimes jumping straight to
    update_mac, sometimes re-diagnosing into another branch).

    Returns True if it ran diagnose on THIS call (first entry), so the caller
    skips a step advance that turn — the strategy's first question is only being
    asked now, not yet answered."""
    s = engine.state
    if not s.customer_id or s.case_closed:
        return False
    if s.diagnosis.get("network") or s.outage_reported:
        return False  # already diagnosed this stage (or an outage short-circuited it)
    try:
        obs = execute_tool("diagnose_connection", {"customer_id": s.customer_id})
    except Exception:  # pragma: no cover - best-effort
        return False
    engine.tracer.emit("tool_call", name="diagnose_connection", args={"customer_id": s.customer_id})
    engine._trace_tool_result("diagnose_connection", obs)
    engine._update_state_from_observation("diagnose_connection", obs)
    _seed_evidence_from_anamnesis(engine)
    return True


def _seed_evidence_from_anamnesis(engine) -> None:
    """Facts the caller stated EARLY must not die in anamnesis_raw (Andrius
    2026-08-13: 'pakeičiau routerį' answered at the ANAMNESIS question was
    re-asked later in the fault flow). Once the verdict activates a pack, the
    anamnesis answer is scanned against the pack's declared answer markers and
    matching facts land on the ledger — the drive then never asks them again.
    Only specific markers (>=5 chars) seed; generic affirmations never do."""
    s = engine.state
    raw = s.anamnesis_raw
    verdict = (s.resolution or {}).get("verdict")
    if not raw or not verdict:
        return
    from .evidence import CLIENT, _fold, _mark_hit, set_fact, spec_for

    spec = spec_for(verdict)
    if not spec:
        return
    low = _fold(raw)
    for key, item in (spec.get("client") or {}).items():
        if key in s.evidence:
            continue
        for value, marks in ((item or {}).get("atsakymai") or {}).items():
            hits = [m for m in marks or [] if len(str(m)) >= 5 and _mark_hit(low, _fold(str(m)))]
            if hits:
                set_fact(s.evidence, key, str(value), CLIENT, s.turn_count)
                engine.tracer.emit("evidence", action="anamnesis_seed", key=key, value=str(value))
                break


def ensure_action_done(engine) -> bool:
    """Run the current strategy's ACTION step deterministically (engine-driven,
    not model-invoked), the same way ensure_diagnosed runs the first diagnose.

    Model-invoked update_mac caused two bugs: a single-tool loop (the bind step
    exposes only update_mac, so the model re-called it to the limit) and a
    contradictory narration (the model ignored the verified result and re-told
    the problem — "nepririštas, dabar pririšiu" — right after binding). Binding
    is a pure engine action: the engine runs it + reset_port + re-diagnose (via
    _augment_tool_result, which also sets case_closed on success or advances to
    escalate on failure), so by the time the LLM narrates it only PHRASES the
    verified outcome. Returns True if it ran an action this call."""
    s = engine.state
    if not s.customer_id or s.case_closed:
        return False
    r = s.resolution
    if not r:
        return False
    from .resolution import StepKind, get_strategy

    strat = get_strategy(r.get("verdict"))
    step = strat.step(r.get("step", "")) if strat else None
    if step is None:
        return False
    # Auto-register ESCALATE (consent=False, e.g. dr_register_router after a working
    # bridge): the registration is a NECESSITY, not an offer — the engine registers
    # ON ARRIVAL and closes; the narrator only ANNOUNCES it ("užregistravau...,
    # kolegos susisieks ir detaliau paaiškins"). Asking permission here misread a
    # non-consent reply as a decline and the caller left WITHOUT the ticket they
    # were promised (observed live).
    # ESCALATE arrival (consented or not) begins the ticket dialogue THE SAME
    # TURN — deterministically. Leaving the arrival to the LLM narrator had it
    # claim "užregistravau…" before anything was registered and before the
    # contact questions (observed live 2026-08-04). The dialogue's intro
    # announces the registration; an explicit refusal during it still declines.
    if step.kind is StepKind.ESCALATE:
        engine._begin_ticket_dialogue(step)  # contacts first, then register+close
        return True
    if step.kind != StepKind.ACTION:
        return False
    if r.get("action_done"):
        return False  # already ran this action; the walker advances it next turn
    ran = False
    for action in step.tool_actions:
        try:
            obs = execute_tool(action, {"customer_id": s.customer_id})
        except Exception:  # pragma: no cover - best-effort
            continue
        engine.tracer.emit("tool_call", name=action, args={"customer_id": s.customer_id})
        obs = engine._augment_tool_result(action, obs)  # chains reset_port + re-diagnose
        engine._trace_tool_result(action, obs)
        ran = True
    if ran:
        r["action_done"] = True  # the announce is narrated this turn; advance next
        if "update_mac" in step.tool_actions:
            # Only a TEMPORARY bridge marks _bridge_bound (ticket-first close,
            # bridged intro) — foreign_mac's bind IS the fix, not a bridge.
            from .evidence import solution_for

            if solution_for(s.evidence, r.get("verdict")) == "bridge":
                engine._bridge_bound = True
    return ran


def advance_resolution(engine, user_input: str | None) -> None:
    """Walk the strategy from the caller's reply, then trace WHY it moved (or did
    not) — the decision record is what makes a failed call debuggable."""
    # Ledger: a fresh evidence conflict holds the walker THIS turn — the
    # contradicting utterance must not double as a step answer; the scripted
    # clarification goes out instead and the settling answer resumes.
    if engine._evidence_conflict:
        engine.tracer.emit(
            "decision",
            intent="evidence_conflict",
            action="hold",
            key=engine._evidence_conflict[0],
        )
        return
    r = engine.state.resolution
    before = r.get("step") if r else None
    engine._walk_resolution(user_input)
    engine._emit_decision(before)


def walker_owns_turn(engine, r: dict, step) -> bool:
    """B2: may the walker READ this turn's answer? Walker-driven packs: always.
    Solver-driven packs: only once the evidence layer handed over — the
    solution step was synced (`solution_synced`), the bridge is bound, or the
    step is a verify/escalate outcome step (telemetry + outcome, not a
    diagnostic fact the ledger collects)."""
    from .faults import driver
    from .resolution import StepKind

    if driver(r.get("verdict")) != "solveris":
        return True
    if r.get("solution_synced") or getattr(engine, "_bridge_bound", False):
        return True
    if step.kind in (StepKind.ESCALATE, StepKind.VERIFY):
        return True
    return step.id in ("confirm_restored", "dr_see_device")


def walk_resolution(engine, user_input: str | None) -> None:
    """Generic step-by-step walker over the active strategy, from the caller's
    reply. Uniform for all fault types:

    - INSTRUCT / ACTION: a guided step. Once its instruction (or the bind
      announce) has been presented, ANY caller reply — they did it / answered —
      advances to the next step. One instruction per turn, listen, move on.
    - CONFIRM: branches on yes/no (and a strong device-change pre-answer).
    - confirm_restored: a VERIFY that blends the caller's word with a fresh
      telemetry read — routed separately (_advance_restored).

    This is what leads the caller one step at a time instead of dumping the
    whole playbook, and stops the model binding a device they never confirmed.

    The pre-checks live in walker_guards.py (R3, roadmap §5) as an ordered,
    individually-named chain; this method keeps only the mechanics — intent
    derivation, the guard iteration and the advancement dispatch below."""
    from . import walker_guards
    from .resolution import (
        StepKind,
        detect_turn_intent,
        get_strategy,
        next_step_id,
    )

    r = engine.state.resolution
    if not r or engine.state.case_closed:
        return
    for guard in walker_guards.PRELUDE_GUARDS:
        if guard(engine, user_input):
            return
    # Derive the intent from THIS call's input rather than trusting it was set
    # earlier — the walker must not depend on the caller's ordering.
    engine.state.last_intent = detect_turn_intent(user_input)
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
    owns = walker_owns_turn(engine, r, step)
    for guard in walker_guards.STEP_GUARDS:
        if not owns and guard in walker_guards.ANSWER_GUARDS:
            continue  # policy guards still run; answer readers stay silent
        if guard(engine, r, strat, step, user_input):
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
        engine._advance_escalate(r, step, user_input)
        return
    # What KIND of turn was this? Only a real answer or a completed action may move
    # the conversation. "Einu prie routerio", a question, confusion or silence all
    # HOLD the step — the agent responds to them instead of running ahead.
    if not engine._turn_may_advance(step):
        return
    # confirm_restored blends the caller's word with a fresh telemetry read.
    if step.id == "confirm_restored":
        engine._advance_restored(r, user_input)
        return
    # Bridge: did the device they just plugged in actually appear on the line?
    if step.id == "dr_see_device":
        engine._advance_see_device(r)
        return
    # A guided instruction / the bind announce: advance on ANY reply, once it was
    # presented last turn — to an explicit goto if set, else the next step in order.
    if step.kind in (StepKind.INSTRUCT, StepKind.ACTION):
        if r.get("asked"):
            engine._advance_instruct(r, step, strat, user_input)
        return
    if step.kind != StepKind.CONFIRM:
        return
    # Otherwise route only once the question was asked — a bare "taip" on the
    # diagnose turn is the address confirmation, not an answer to this step.
    # A STALE question (walker benched for turns) does not read answers either.
    if not r.get("asked") or not engine._asked_recently(r):
        return
    # Keyword fallback (classifier off / unsure): read the reply into a routing key.
    key = engine._detect_confirm(step, user_input)
    if key is None:
        return
    if engine._block_uncorroborated_escalate(step, strat, key, user_input):
        return  # clarify goes out instead; the step holds
    engine._route_to(r, next_step_id(strat, step.id, key))


def block_uncorroborated_escalate(engine, step, strat, label, user_input: str | None) -> bool:
    """A bare "Ne."-style reply about to route the walker into ESCALATE — a
    one-way door to the ticket dialogue — needs a second source agreeing it
    really is a refusal (the understanding pass reading a confident answer).
    Without it, ask the solve-or-ticket clarify ONCE instead and hold
    (Andrius 2026-08-11: clarify what the "ne" means, never rush the
    conclusion). A repeated no on the next turn escalates normally."""
    from .resolution import StepKind, is_bare_negation, next_step_id

    target = next_step_id(strat, step.id, label)
    tstep = strat.step(target) if strat and target else None
    if tstep is None or tstep.kind is not StepKind.ESCALATE:
        return False
    if not is_bare_negation(user_input):
        return False
    if getattr(engine, "_escalate_clarify_asked", False):
        return False  # clarified once already — a repeated no is a real no
    u = getattr(engine, "_last_understanding", None)
    if u is not None and u.get("tipas") == "atsakymas" and (u.get("pasitikejimas") or 0) >= 0.6:
        return False  # two sources agree on the refusal — escalate may proceed
    engine._escalate_clarify_asked = True
    engine._escalate_clarify_pending = True
    engine.tracer.emit(
        "decision",
        intent="answer",
        action="clarify",
        from_step=step.id,
        to=target,
        reason="bare negation, no corroboration",
    )
    return True


def _cached_perception(engine, step, user_input: str | None):
    """The merged perception call's step read for THIS step + THIS utterance,
    or None (walker then falls back to the standalone classifier)."""
    cached = getattr(engine, "_perception_step", None)
    if not cached or cached.get("step_id") != step.id or cached.get("input") != user_input:
        return None
    from .classifier import CandidateObservation

    try:
        return CandidateObservation(**cached["obs"])
    except Exception:  # pragma: no cover - defensive
        return None


def classify_confirm_and_route(engine, step, strat, user_input: str | None) -> bool:
    """Classifier-led routing for an asked CONFIRM step. One LLM call reads BOTH the
    answer (into a routing key) and whether it IS an answer. A confident answer
    advances the walker (overriding a brittle keyword turn-intent); anything unsure
    returns False → the keyword detector + intent gate handle it. Sensor only."""
    from .classifier import classify_step
    from .detectors import glosses as detector_glosses
    from .faults import step_options
    from .resolution import next_step_id

    # R4 perception merge: the understanding pass already classified this reply
    # against THIS step's keys in the same LLM call — consume the cached read
    # instead of a second round-trip. Fallback (cache miss / UNDERSTAND off):
    # the standalone classifier exactly as before.
    obs = _cached_perception(engine, step, user_input)
    if obs is None:
        detector_name = step.detector or "yes_no"
        # WHAT TO DETECT comes from the fault definition first (knowledge/faults.yaml —
        # per-step, so it can be worded precisely for THIS check), falling back to the
        # universal per-detector glosses (knowledge/detectors.yaml, code as last
        # resort). A reworded check is a file edit, not code.
        declared = step_options((engine.state.resolution or {}).get("verdict"), step.id)
        glosses = detector_glosses(detector_name)
        options: dict[str, str] = {}
        for raw in step.on:
            # Some steps key `on` by the Outcome enum — str(Outcome.YES) is "Outcome.YES",
            # so take .value to get the real routing key ("yes") the classifier must return.
            key = str(getattr(raw, "value", raw))
            options[key] = (declared or {}).get(key) or glosses.get(key, key)
        question = engine._last_agent_question() or step.hint or ""
        obs = classify_step(question, user_input or "", options, model=engine.config.model)
    if obs is None:
        engine._trace_note("classifier", f"{step.detector or 'yes_no'}: no result → keyword")
        return False
    answered = obs.is_answer and obs.label in step.on and obs.confidence >= 0.5
    engine.tracer.emit(
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
        if engine._block_uncorroborated_escalate(step, strat, obs.label, user_input):
            return True  # clarify goes out instead; the step holds
        engine.state.awaiting = None
        engine.state.awaiting_turns = 0
        engine.state.step_confusions = 0
        engine.state.last_intent = "answer"
        engine._route_to(engine.state.resolution, next_step_id(strat, step.id, obs.label))
        return True
    return False


def advance_instruct(engine, r: dict, step, strat, user_input: str | None = None) -> None:
    """Advance a presented INSTRUCT/ACTION step to its goto (or the next step in order).
    Shared by the keyword path and the classifier gate. The dr_see_device VERIFY is
    engine-owned, so resolve it in the SAME turn (reflect the plug-in in the demo, then
    read the line) instead of asking a dead question."""
    from .resolution import Outcome, StepKind, detect_restored, next_step_id

    engine._route_to(r, step.goto or next_step_id(strat, step.id, None))
    # Skipped-ahead caller (live 2026-08-24): still on dr_pick_cable, the caller
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
        and engine._plug_report(user_input)
    ):
        engine._route_to(r, skipped.goto or next_step_id(strat, skipped.id, None))
    if r.get("step") == "dr_see_device":
        engine._simulate_bridge_connection()
        engine._advance_see_device(r)
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
        engine._route_to(r, next_step_id(strat, new_step.id, "yes"))


def classify_instruct_and_advance(engine, step, strat, user_input: str | None) -> bool:
    """Classifier-led advancement for an asked INSTRUCT step: did the caller actually
    DO it, or are they still doing it / asking? A confident 'done' advances even when
    the keyword turn-intent misreads a messy done-signal as in_progress. Anything else
    returns False → the keyword intent gate decides. Sensor only."""
    from .classifier import classify_step
    from .detectors import glosses as detector_glosses

    # R4 perception merge first (cached same-call read), classifier fallback.
    obs = _cached_perception(engine, step, user_input)
    if obs is None:
        # Meanings come from knowledge/detectors.yaml (file-editable), code fallback.
        options = detector_glosses("instruct_done")
        question = engine._last_agent_question() or step.hint or ""
        obs = classify_step(question, user_input or "", options, model=engine.config.model)
    if obs is None:
        return False
    done = obs.label == "done" and obs.confidence >= 0.5
    engine.tracer.emit(
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
        engine.state.awaiting = None
        engine.state.awaiting_turns = 0
        engine.state.step_confusions = 0
        engine.state.last_intent = "done"
        engine._advance_instruct(engine.state.resolution, step, strat, user_input)
        return True
    # Classifier VETO: the classifier RAN and did NOT say "done" (waiting OR
    # unclear) — HOLD the step unless the keyword intent is an explicit DONE
    # ("padariau", "patikrinau"), which outranks a soft classifier read (observed:
    # "Patikrinau, WiFi įjungtas" held as waiting slipped the resolve a turn).
    # Unclear included: the loose any-'answer' keyword path had advanced INSTRUCT
    # steps on garbage ("Įsitikimu, kad tai yra neturis" climbed dr_plug_pc live).
    from .resolution import INTENT_DONE, detect_turn_intent

    return detect_turn_intent(user_input) != INTENT_DONE


def detect_confirm(engine, step, user_input: str | None):
    """Keyword FALLBACK detector for a CONFIRM reply — used when the classifier is off
    or unsure (the classifier-led path is _classify_confirm_and_route). Returns a
    routing key or None."""
    from .resolution import DETECTORS

    keyword = DETECTORS.get(step.detector or "yes_no", DETECTORS["yes_no"])
    return keyword(user_input)


def open_hypothesis(engine, reason: str | None) -> None:
    """A fresh verdict = a new belief. Seeds it with what the telemetry showed."""
    if not reason:
        return
    h = engine.state.hypothesis
    if h and h.get("cause") == reason and h.get("status") == "testing":
        return  # same belief, still being tested — keep its evidence
    # The ANALYSIS fuses BOTH sides (Step 2): telemetry is the first evidence,
    # the caller's anamnesis (when it broke / after what) the second — so the
    # agent reasons and narrates from the full picture ("telemetrija rodo X, o
    # klientas sako dingo po audros").
    because = [_DIAGNOSIS_LT.get(reason, reason)]
    s = engine.state
    if s.anamnesis_when or s.anamnesis_trigger:
        bits = []
        if s.anamnesis_when:
            bits.append(f"dingo {s.anamnesis_when}")
        if s.anamnesis_trigger:
            bits.append(f"po: {s.anamnesis_trigger}")
        because.append("klientas sako " + ", ".join(bits))
    engine.state.hypothesis = {
        "cause": reason,
        "because": because,
        "status": "testing",
        "settled_by": None,
    }


def note_evidence(engine, text: str) -> None:
    """Add something the ENGINE learned (a telemetry read, a check outcome)."""
    h = engine.state.hypothesis
    if h and text and text not in h["because"]:
        h["because"].append(text)


def settle_hypothesis(engine, status: str, settled_by: str) -> None:
    """Close the belief: confirmed (the fix worked / the cause was proven) or
    rejected (it did not hold). Rejected ones are remembered so the engine never
    re-tries them and the agent can say what it already ruled out."""
    h = engine.state.hypothesis
    if not h or h.get("status") != "testing":
        return
    h["status"] = status
    h["settled_by"] = settled_by
    if status == "rejected":
        engine.state.rejected_hypotheses.append({"cause": h["cause"], "settled_by": settled_by})


def turn_may_advance(engine, step) -> bool:
    """May the caller's turn move the walker forward?

    Only a real ANSWER or a completed action does. "Einu prie routerio" is work in
    progress, a question needs answering, confusion needs a finer explanation, and
    silence needs waiting — none of them mean the step is finished. Before this,
    every non-answer fell through to "repeat the question", which is how the agent
    ran ahead of the caller (it read a plugged-in-yet? check before they had
    plugged anything in) and repeated itself six turns running.

    Unknown is deliberately treated as an ANSWER only for CONFIRM steps, where a
    detector still has to agree — elsewhere it holds. Safe default: wait and ask."""
    from .resolution import (
        INTENT_ANSWER,
        INTENT_DONE,
        INTENT_IN_PROGRESS,
        INTENT_UNKNOWN,
        StepKind,
    )

    s = engine.state
    from .resolution import INTENT_CONFUSED

    intent = s.last_intent or INTENT_UNKNOWN
    if intent in (INTENT_ANSWER, INTENT_DONE):
        s.awaiting = None
        s.awaiting_turns = 0
        s.step_confusions = 0  # they got past this one
        return True
    if intent == INTENT_CONFUSED:
        # Each "I don't follow" on the SAME step earns a smaller piece of it.
        s.step_confusions += 1
    # Still waiting on the same thing — count the turns so the agent can check in
    # ("ar pavyksta?") instead of silently re-asking the same sentence.
    s.awaiting = (
        "client_action"
        if (intent == INTENT_IN_PROGRESS or step.kind is StepKind.INSTRUCT)
        else "client_answer"
    )
    s.awaiting_turns += 1
    return False


def advance_see_device(engine, r: dict) -> None:
    """Bridge check: after the caller plugs a computer into the wall cable, does the
    line actually SEE a device? Telemetry answers this, not the caller — binding
    blindly when the cable is in the wrong socket would fail confusingly. Seen ->
    bind; not seen after two tries -> the cable is wrong, walk it back."""
    reason = engine._fresh_diagnose_reason()
    seen = reason != "no_mac_observed"  # any other verdict means a device is there
    r["device_seen"] = seen
    engine._note_evidence(
        "prijungtas įrenginys matomas linijoje" if seen else "įrenginio linijoje vis dar nematyti"
    )
    if seen:
        engine._goto_step(r, "dr_bind")
        return
    r["plug_retries"] = int(r.get("plug_retries", 0)) + 1
    if r["plug_retries"] >= 2:
        engine._goto_step(r, "escalate")
    else:
        engine._goto_step(r, "dr_pick_cable")  # wrong cable/socket — try again


def reject_and_rediagnose(engine, r: dict) -> bool:
    """The fix ran but the line is still down: reject THIS hypothesis and look for
    another one before giving up.

    Re-reads telemetry through the normal path so state.diagnosis and the strategy
    pivot both update (the pivot skips anything already in failed_hypotheses).
    Returns True when a genuinely NEW strategy took over — the agent has a Plan B
    and says so (see `pivoted_from`); False when nothing new is left, so the caller
    escalates. Without this the FIRST failed fix ended in a ticket even when the
    telemetry had started pointing at a different fault."""
    s = engine.state
    verdict = r.get("verdict")
    if verdict and verdict not in s.failed_hypotheses:
        s.failed_hypotheses.append(verdict)
    engine._settle_hypothesis("rejected", "po veiksmo ryšys neatsistatė (telemetrija)")
    s.diagnosis.pop("network", None)  # let ensure_diagnosed re-read the line
    engine.ensure_diagnosed()
    new = (s.resolution or {}).get("verdict")
    if new and new != verdict and new not in s.failed_hypotheses:
        s.pivoted_from = verdict  # narrate the rethink once, then clear
        return True
    return False


def route_to(engine, r: dict, target: str) -> None:
    """Apply a routing target: the 'resolve'/'end' terminals close the case; any
    other id is a real step to advance to. Centralises terminal handling so every
    branch (including client_side -> resolve) actually closes."""
    if target == "resolve":
        engine.state.case_closed = True
        engine.state.closed_reason = "resolved"
        # The fix worked, so the cause we were testing was the right one — the
        # agent can now say so ("taigi dėl X ir nebuvo interneto").
        engine._settle_hypothesis("confirmed", "sutvarkius problema dingo")
    elif target == "end":
        engine.state.case_closed = True
        engine.state.closed_reason = engine.state.closed_reason or "declined"
    else:
        engine._goto_step(r, target)


def advance_restored(engine, r: dict, user_input: str | None) -> None:
    """After binding, decide from BOTH the caller's word and a fresh telemetry
    read (re-read each turn — a bind can take a minute to come up):

    - caller says it works                 -> resolved
    - caller says NO, provider side OK      -> client-side fault (Wi-Fi/device)
    - caller says NO, provider not yet OK   -> wait (reassure); after a second
                                               denial with still-no-line, escalate
    An unclear answer stays and re-asks."""
    from .resolution import Outcome, detect_restored

    reason_now = engine._fresh_diagnose_reason()
    fixed = reason_now not in engine._UNRESOLVED_LINE_FAULTS
    r["telemetry_fixed"] = fixed
    if not r.get("asked"):
        return  # question not asked yet (the bind turn) — just record telemetry
    outcome = detect_restored(user_input)
    if outcome == Outcome.YES:
        engine.state.case_closed = True
        engine.state.closed_reason = "resolved"
        engine._settle_hypothesis("confirmed", "klientas patvirtino, kad veikia")
        return
    if outcome == Outcome.NO:
        if fixed:
            # Provider side restored but the caller still has no internet — the
            # fault is inside the home. Pivot to the client-side step.
            engine._goto_step(r, "client_side")
        else:
            r["restored_denials"] = int(r.get("restored_denials", 0)) + 1
            if r["restored_denials"] >= 2:
                # The bind has not taken after waiting. Don't register yet: reject
                # this hypothesis and see whether the telemetry now points at a
                # different fault. Only escalate when there is no Plan B.
                if not engine._reject_and_rediagnose(r):
                    engine._goto_step(r, "escalate")
            # else: stay, reassure it may take a couple of minutes (see hint)
        return
    # unclear -> stay on confirm_restored, re-ask


def advance_escalate(engine, r: dict, step, user_input: str | None) -> None:
    """Deterministic OUTCOME for an ESCALATE step (Phase 3.11 B). Once the consent
    question was posed (asked), the caller's reply decides:
      consent  -> the ENGINE registers the ticket from STATE and closes,
      decline  -> close WITHOUT a ticket (closed_reason='declined'),
      unclear  -> hold; the narrator re-asks (stuck-guard still backstops).
    The LLM only phrases — it can no longer call create_ticket itself."""
    if not step.consent:
        return  # auto-register step — ensure_action_done handles it on arrival
    if not r.get("asked"):
        return  # consent question not posed yet — narrator asks it this turn
    from .classifier import classify_step
    from .detectors import glosses as detector_glosses
    from .resolution import detect_ticket_consent

    label = detect_ticket_consent(user_input)
    routed_by = "keyword"
    # Keyword miss -> LLM classifier (same order as CONFIRM steps: the model reads
    # messy phrasing the wordlist can't — "na jo, tebūnie", garbled STT).
    if label is None and os.getenv("CLASSIFIER", "on").lower() != "off":
        obs = classify_step(
            engine._last_agent_question() or str(step.hint or ""),
            user_input or "",
            # Meanings from knowledge/detectors.yaml (file-editable), code fallback.
            detector_glosses("ticket_consent"),
            model=engine.config.model,
        )
        if obs is not None and obs.is_answer and obs.confidence >= 0.5:
            label = obs.label
            routed_by = "classifier"
    engine.tracer.emit(
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
        engine._begin_ticket_dialogue(step)  # contacts first, then register+close
    elif label == "no":
        engine.state.case_closed = True
        engine.state.closed_reason = "declined"
    # unclear -> stay; the step's question is re-asked


def goto_step(engine, r: dict, next_id: str) -> None:
    """Move the strategy to `next_id`. When the step actually changes, clear the
    'asked' flag so the NEXT step (e.g. a second CONFIRM like check_cable) waits
    for its OWN question to be asked before a plain yes/no can advance it."""
    if next_id != r.get("step"):
        r["asked"] = False
        # Process journal (sąmoningumas №3): the walk's transitions — the
        # solver reads WHAT already happened instead of re-deriving it.
        journal = r.setdefault("journal", [])
        journal.append(f"{r.get('step') or '—'}→{next_id}")
        if len(journal) > 12:
            del journal[:-12]
    r["step"] = next_id

"""Diagnosis execution — the telemetry reads (the first diagnosis, fresh rechecks) and the
procedure's due step action (bind, reset, verify), run by the engine, never the model."""

from __future__ import annotations

from ..contract.locale import vocab


def fresh_diagnose(state, rt) -> dict | None:
    """Re-read telemetry now and return the full diagnose payload
    ({verdict, signals}) or None on error. Read-only — used to VERIFY a fix
    actually took before closing/acting."""
    if not state.identity.customer_id:
        return None
    try:
        from ..tooling import telemetry

        return telemetry(state, rt, mode="recheck", reason="verify").data
    except Exception:  # pragma: no cover - best-effort
        return None


def fresh_diagnose_reason(state, rt) -> str | None:
    """The fresh verdict reason alone (or None on error)."""
    d = fresh_diagnose(state, rt)
    if not isinstance(d, dict):
        return None
    return (d.get("verdict") or {}).get("reason")


def ensure_diagnosed(state, rt) -> bool:
    """Deterministically run diagnose_connection the first time we enter the
    diagnosis stage (customer identified), so the verdict + strategy are set
    BEFORE the model narrates. The flow no longer depends on the model choosing
    to diagnose — which it did inconsistently (sometimes jumping straight to
    update_mac, sometimes re-diagnosing into another branch).

    Returns True if it ran diagnose on THIS call (first entry), so the caller
    skips a step advance that turn — the strategy's first question is only being
    asked now, not yet answered."""
    from ..ticket_flow import begin_ticket_dialogue

    s = state
    if not s.identity.customer_id or s.closing.case_closed:
        return False
    if s.diagnosis.verdicts.get("network") or s.diagnosis.outage_reported:
        return False  # already diagnosed this stage (or an outage short-circuited it)
    # NO-PATH rule (Andrius 2026-09-03): the reported problem is in-scope and
    # the caller is IDENTIFIED, but no fault pack declares a path for it
    # (e.g. TV today) — an honest "neaiškus gedimas" ticket instead of running
    # the INTERNET telemetry and walking a wrong-domain pack (live: a TV call
    # was led through Wi-Fi questions). The single-escalate strategy begins
    # the ticket dialogue deterministically on arrival.
    if s.intake.problem_type and s.resolution.procedure is None:
        from ..faults import problem_has_path, step_by_role

        if not problem_has_path(s.intake.problem_type):
            escalate = step_by_role("unclear_fault", "escalate")
            s.resolution.procedure = {"verdict": "unclear_fault", "step": escalate.id}
            s.diagnosis.verdicts["network"] = {"reason": "unclear_fault", "skipped": True}
            rt.tracer.emit(
                "decision",
                intent="no_path",
                action="unclear_fault_ticket",
                value=s.intake.problem_type,
            )
            begin_ticket_dialogue(state, rt, escalate)
            return True
    try:
        from ..tooling import telemetry

        telemetry(state, rt, mode="snapshot", reason="first_diagnosis")
    except Exception:  # pragma: no cover - best-effort
        return False
    _seed_evidence_from_anamnesis(state, rt)
    return True


def _seed_evidence_from_anamnesis(state, rt) -> None:
    """Facts the caller stated EARLY must not die in anamnesis_raw (Andrius
    2026-08-13: 'pakeičiau routerį' answered at the ANAMNESIS question was
    re-asked later in the fault flow). Once the verdict activates a pack, the
    anamnesis answer is scanned against the pack's declared answer markers and
    matching facts land on the ledger — the drive then never asks them again.
    Only specific markers (>=5 chars) seed; generic affirmations never do."""
    s = state
    raw = s.intake.anamnesis_raw
    verdict = (s.resolution.procedure or {}).get("verdict")
    if not raw or not verdict:
        return
    from ..evidence import CLIENT, _fold, _mark_hit, set_fact, spec_for

    spec = spec_for(verdict)
    if not spec:
        return
    low = _fold(raw)
    for key, item in (spec.get("client") or {}).items():
        if key in s.diagnosis.evidence:
            continue
        for value, name in ((item or {}).get("answers") or {}).items():
            marks = vocab(name)
            hits = [m for m in marks if len(str(m)) >= 5 and _mark_hit(low, _fold(str(m)))]
            if hits:
                set_fact(s.diagnosis.evidence, key, str(value), CLIENT, s.dialog.turn_count)
                rt.tracer.emit("evidence", action="anamnesis_seed", key=key, value=str(value))
                break


def ensure_action_done(state, rt) -> bool:
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
    from ..narrator_flow import augment_tool_result
    from ..ticket_flow import begin_ticket_dialogue

    s = state
    if not s.identity.customer_id or s.closing.case_closed:
        return False
    r = s.resolution.procedure
    if not r:
        return False
    from ..resolution import StepKind, get_strategy

    strat = get_strategy(r.get("verdict"))
    step = strat.step(r.get("step", "")) if strat else None
    if step is None:
        return False
    # Auto-register ESCALATE (consent=False, e.g. register_after_bridge after a working
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
        begin_ticket_dialogue(state, rt, step)  # contacts first, then register+close
        return True
    if step.kind != StepKind.ACTION:
        return False
    if r.get("action_done"):
        return False  # already ran this action; the walker advances it next turn
    ran = False
    for action in step.tool_actions:
        try:
            result = rt.tools.run(
                state,
                rt,
                action,
                {"customer_id": s.identity.customer_id},
                reason=f"step_action:{step.id}",
                apply=False,
            )
        except Exception:  # pragma: no cover - best-effort
            continue
        augment_tool_result(
            state, rt, action, result.observation
        )  # chains reset_port + re-diagnose
        ran = True
    if ran:
        r["action_done"] = True  # the announce is narrated this turn; advance next
        if "update_mac" in step.tool_actions:
            # Only a TEMPORARY bridge marks resolution.bridge_bound (ticket-first close,
            # bridged intro) — foreign_mac's bind IS the fix, not a bridge.
            from ..evidence import solution_for

            if solution_for(s.diagnosis.evidence, r.get("verdict")) == "bridge":
                state.resolution.bridge_bound = True
    return ran

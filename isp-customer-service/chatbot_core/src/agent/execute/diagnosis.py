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
    from .ticket import begin_ticket_dialogue

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
    from ..decide.rules import services

    service_route = services.route(state) if s.resolution.procedure is None else None
    if service_route == "not_subscribed":
        services.not_subscribed(state, rt)
        return True
    if s.intake.problem_type and s.resolution.procedure is None and service_route != "depends":
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
    if service_route == "depends":
        # IPTV over a broken internet: fix the internet, re-check the TV at the end.
        # Over a healthy internet the TV fault is its own — the no-path ticket.
        if services.depends_on_broken(state):
            services.recheck_after_fix(state, rt)
        else:
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
    _unclear_fault_when_unknown(state, rt)
    _seed_evidence_from_call(state, rt)
    return True


def _unclear_fault_when_unknown(state, rt) -> None:
    """D-04 / F-8: a verdict no pack solves and no inform template tells (dhcp_silent,
    no_port_data) never goes to a free LLM with all tools — the honest "unclear fault"
    ticket starts instead."""
    from ..faults import step_by_role, verdict_flag
    from ..resolution import get_strategy
    from .ticket import begin_ticket_dialogue

    s = state
    reason = (s.diagnosis.verdicts.get("network") or {}).get("reason")
    if not reason or s.resolution.procedure is not None or s.diagnosis.outage_reported:
        return
    if get_strategy(reason) is not None or verdict_flag(reason, "inform"):
        return
    escalate = step_by_role("unclear_fault", "escalate")
    s.resolution.procedure = {"verdict": "unclear_fault", "step": escalate.id}
    # No belief to voice and no telemetry jargon for the narrator (the raw reading stays
    # in verdicts["network"]["telemetry"] and on the ticket); the conversation hears
    # "unclear fault".
    from ..evidence import TELEMETRY, set_fact

    set_fact(s.diagnosis.evidence, "verdict", "unclear_fault", TELEMETRY, s.dialog.turn_count)
    s.diagnosis.hypothesis = {
        "cause": reason,
        "because": [],
        "status": "unsolved",
        "settled_by": None,
    }
    s.diagnosis.verdicts["network"] = {
        "reason": "unclear_fault",
        "telemetry": reason,
        "skipped": True,
    }
    rt.tracer.emit("decision", intent="no_pack", action="unclear_fault_ticket", value=reason)
    begin_ticket_dialogue(state, rt, escalate)


def _seed_evidence_from_call(state, rt) -> None:
    """Facts the caller stated BEFORE the pack existed must not die there (Andrius
    2026-08-13: 'pakeičiau routerį' answered at the ANAMNESIS question was re-asked
    later in the fault flow; F-11: 'neveikia visuose įrenginiuose' said in the very
    first sentence was re-asked as 'visuose ar tik viename?'). Once the verdict
    activates a pack, everything the caller has said so far is scanned against the
    pack's declared answer markers and matching facts land on the ledger — the drive
    then never asks them again. Only specific markers (>=5 chars) seed; generic
    affirmations never do."""
    s = state
    said = [x for x in [s.intake.anamnesis_raw, *s.intake.heard_utterances] if x]
    raw = " | ".join(said)
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
                # Volunteered, not asked: the step that would ask it checks it back
                # instead of making the caller repeat themselves (F-11).
                s.diagnosis.evidence[key]["seeded"] = True
                rt.tracer.emit("evidence", action="call_seed", key=key, value=str(value))
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
    from .observe import augment_tool_result
    from .ticket import begin_ticket_dialogue

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

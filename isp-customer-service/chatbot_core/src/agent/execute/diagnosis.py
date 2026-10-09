"""Diagnosis execution — the telemetry reads (the first diagnosis, fresh rechecks), run by
the engine, never the model."""

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
    from ..decide.rules import open_ticket, requests, services

    # A request outside the agent's knowledge is registered, a status question answered —
    # neither is diagnosed (D-11).
    from ..intents import problem_policy

    policy = problem_policy(s.intake.problem_type) if s.intake.problem_type else None
    if s.ticket.request_type:
        # Live 2026-09-17: a second pass took the billing question for an unclear fault
        # and the cancel-confirm spoke of a technician.
        return True
    if not state.ticket.stage and policy == "register":
        requests.start_request(state, rt)
        return True
    if policy == "answer":
        requests.answer_ticket_status(state, rt)
        return True
    # A repeat call about a problem that already has an open ticket: a note on it and its
    # status — no re-diagnosis, no duplicate ticket (D-12).
    if open_ticket.same_problem_ticket(state):
        open_ticket.repeat_call(state, rt)
        return True
    service_route = services.route(state)
    if service_route == "not_subscribed":
        services.not_subscribed(state, rt)
        return True
    if s.intake.problem_type and service_route != "depends":
        if not _has_cards(s.intake.problem_type):
            _no_path_ticket(state, rt)
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
            if not _has_cards(s.intake.problem_type):
                _no_path_ticket(state, rt)
                return True
    _seed_evidence_from_call(state, rt)
    return True


def _has_cards(problem: str | None) -> bool:
    """Does a v2 card work on this reported problem (its `symptom`)? A solve-policy problem
    without one — TV today — is an unclear fault (Andrius 2026-09-03)."""
    from ..contract import cards

    return bool(problem) and any(
        card.symptom == problem and not card.fallback for card in cards.cards().values()
    )


def _no_path_ticket(state, rt) -> None:
    """In scope, identified, but no card can work on it (e.g. TV today): an honest „unclear
    fault" ticket through the Case's unclear_fault card — never a wrong-domain walk (Andrius
    2026-09-03)."""
    s = state
    s.case.fault = "unclear_fault"
    s.diagnosis.verdicts["network"] = {"reason": "unclear_fault", "skipped": True}
    rt.tracer.emit(
        "decision", intent="no_path", action="unclear_fault_ticket", value=s.intake.problem_type
    )
    from ..decide.rules import case_rule
    from ..decide.rules.head import _begin_case_ticket

    case_rule.announce(state, rt, "unclear_fault")
    _begin_case_ticket(state, rt)


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
    # Wave 3: the facts in play are the Case's — what the caller mentioned in passing is read
    # against every open card, not against one walker verdict.
    verdict = s.case.fault
    if not raw:
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

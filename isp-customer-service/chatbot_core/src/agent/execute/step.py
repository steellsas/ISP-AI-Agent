"""The procedure step's presentation bookkeeping: which playbook chunk fed the
step (the trace would otherwise never show it), and the fact that the step's question
actually went out — the repeat guard and the "asked again" wording read it."""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import os  # noqa: F401
import re  # noqa: F401
from typing import Any  # noqa: F401


def emit_rag_injection(state, rt, doc: str | None, section: int, step_id: str, text: str) -> None:
    """Emit a `rag` trace event when a playbook section is injected for a step —
    deduped on (doc, section, step) so the multi-call turn (LLM + tool follow-up)
    logs it once, and a step change logs the new section."""
    key = [doc, section, step_id]
    if state.dialog.last_rag_injection_key == key:
        return
    state.dialog.last_rag_injection_key = key
    preview = " ".join((text or "").split())[:90]
    rt.tracer.emit("rag", doc=doc, section=section, step=step_id, preview=preview)


def mark_step_presented(state, rt) -> None:
    """After the agent replies while on a strategy step, record that the step's
    message (a CONFIRM question, an INSTRUCT instruction, or the ACTION announce)
    has now been presented — so the caller's NEXT reply advances the walker."""
    state.diagnosis.pivoted_from = None  # the rethink has now been said — say it once
    s = state
    # Identification ladder bookkeeping: while the caller-intro question is owed,
    # the strategy step's question was NOT asked this reply — do not mark it. Once
    # the caller introduced themselves and the RESULT was narrated, the deferral
    # closes (inform news counted as told).
    if s.identity.customer_id and state.identity.result_pending:
        if not s.identity.caller_name:
            return  # the reply asked WHO is calling — nothing else was presented
        state.identity.result_pending = False
        if s.resolution.procedure is None:
            state.diagnosis.news_delivered = True
    r = state.resolution.procedure
    if not r:
        return
    from ..resolution import StepKind, get_strategy

    strat = get_strategy(r.get("verdict"))
    step = strat.step(r.get("step", "")) if strat else None
    if step is not None and step.kind in (
        StepKind.CONFIRM,
        StepKind.INSTRUCT,
        StepKind.ACTION,
        StepKind.ESCALATE,  # the consent question ("ar tinka?") — Phase 3.11 B
    ):
        r["asked"] = True
        # Freshness stamp (2026-08-11): while the solver/evidence drive owns
        # the turns, the walker step's question ages — three live calls were
        # killed by a many-turns-stale dr_intro reading a reply as its own
        # answer. The asked-step routing only trusts a RECENT question.
        r["asked_at"] = len(state.messages)
        # B-wave registry (shadow): the step's question/instruction was just
        # presented — it is now the walker's active question. Live 2026-09-08:
        # the end-confirm and wrap-up replies are NOT the step's question, so
        # they must not re-register it (asks inflated to 5 on a solved call).
        from ..decide.question import active as _q_active
        from ..decide.question import clear_owner as _q_clear_owner
        from ..decide.question import register as _q_register

        _q = _q_active(state, rt)
        if state.dialog.end_confirm_pending:
            pass  # this reply asked the end-confirm question, not the step's
        elif _q is not None and _q.owner == "safety":
            # Live 2026-09-09 (N1): the reply just asked a SAFETY question
            # (cannot-now clarify) — clobbering it with the step let the
            # refuse guard consume the clarify ANSWER and start a ticket.
            pass
        elif state.closing.case_closed:
            _q_clear_owner(state, rt, "walker")  # the case is over — wrap-up owns the turns
        else:
            _q_register(state, rt, "walker", f"step:{step.id}")
        # Presentation counter (L2): a step presented the 2nd+ time gets the
        # ŽINGSNIS KARTOJAMAS directive — repeat WITH an explanation.
        counts = r.setdefault("presented", {})
        counts[step.id] = counts.get(step.id, 0) + 1

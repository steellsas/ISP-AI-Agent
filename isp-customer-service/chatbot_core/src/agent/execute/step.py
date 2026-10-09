"""The step's presentation bookkeeping: which playbook chunk fed the step (the trace
would otherwise never show it), and the fact that the step's question actually went
out — the repeat guard and the "asked again" wording read it."""

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


def mark_case_step_said(state, rt=None) -> None:
    """Kortelės žingsnis skaitomas NUSKAMBĖJUSIU tik tada, kai atsakymas jam tikrai statomas.

    Žymėti plano sudarymo metu neteisinga: ėjimą gali pasiimti identifikacija ar tiketas, planas
    niekada nenuskamba, o kliento kiti žodžiai tada palaikomi atsakymu į niekada neužduotą
    klausimą (2026-09-23 ir 09-30). Nuo 9 bangos tą pačią žymę naudoja ir parašytų žodžių kelias
    (L2), tad ji gyvena vienoje vietoje.
    """
    rule = str((state.turn.plan or {}).get("rule") or "")
    if not rule.startswith("case."):
        return
    state.case.step_said = state.case.step
    if rule == "case.guide":
        state.case.guide_said = state.case.guide_step
    if rt is not None:
        rt.tracer.emit("case", move="step_said", step=state.case.step, rule=rule)


def mark_step_presented(state, rt) -> None:
    """After the agent replies: the rethink has been said, and the identification
    ladder's deferred result is settled (news counted as told)."""
    state.diagnosis.pivoted_from = None  # the rethink has now been said — say it once
    s = state
    # Identification ladder bookkeeping: while the caller-intro question is owed,
    # nothing else was asked this reply. Once
    # the caller introduced themselves and the RESULT was narrated, the deferral
    # closes (inform news counted as told).
    if s.identity.customer_id and state.identity.result_pending:
        if not s.identity.caller_name:
            return  # the reply asked WHO is calling — nothing else was presented
        if s.identity.holder_clarify_open:
            # Live 2026-09-17: the reply asked whose name the contract is in — the
            # result (outage ETA, debt) still goes out next, through its template.
            return
        state.identity.result_pending = False
        from ..inform import is_news

        # Only NEWS (a debt, an outage, an open ticket) is told by this reply. A fault is not
        # news: this used to mark every fault call "told" once the caller gave a name — and
        # a goodbye mid-analysis then closed as „informed" without a technician (wave 10, S1).
        reason = (s.diagnosis.verdicts.get("network") or {}).get("reason")
        if is_news(reason):
            state.diagnosis.news_delivered = True

"""
W2 — TYLUSIS ANALITIKAS (Andrius 2026-08-25): a quiet observer that reads the
WHOLE conversation in the background and hands the narrator short advisory
notes — "the caller already said when it broke, do not re-ask", "that fact
contradicts what they keep saying, double-check it", "they are mixing up the
router and the computer, name the device".

Boundaries (agreed):
  - ADVISORY ONLY: notes shape the narrator's WORDING; they never write facts
    to the ledger and never change engine routing — the deterministic ledger
    and the packs stay the single source of truth.
  - Runs in the BACKGROUND thread after a voice turn (same seam as
    speculation) — it never adds latency to a reply.
  - Folded into the next turn's facts block once, then cleared; stale notes
    (case closed meanwhile) are dropped.
  - ANALYST=off reverts everything; the cheap PERCEPTION_MODEL does the read.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .contract.locale import vocab

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Tu — TYLUSIS ANALITIKAS, padedantis interneto tiekėjo balso agentui. "
    "Skaitai pokalbį ir žurnalą, bet pats NEkalbi su klientu. Tavo darbas — "
    "iki 2 TRUMPŲ patariamųjų pastabų agentui apie KITĄ repliką, lietuviškai, "
    "kiekviena naujoje eilutėje su „- “ pradžioje. Pastabos gali būti TIK "
    "šių tipų: (1) klientas JAU pasakė kažką, ko agentas gali nebeklausti; "
    "(2) žurnalo faktas įtartinas — prieštarauja tam, ką klientas kartoja "
    "(gali būti blogai išgirsta) — verta pasitikslinti; (3) klientas painioja "
    "sąvokas ar įrenginius — įvardinti aiškiau; (4) SVARBI ankstesnė detalė, "
    "kurios naujausioje pokalbio dalyje nebesimato — priminti agentui; "
    "(5) pokalbis NUKRYPO nuo aktyvaus klausimo — paskutiniai kliento "
    "atsakymai nesiejami su tuo, ko agentas KLAUSĖ (žr. AKTYVUS KLAUSIMAS), "
    "pažymėk nukrypimą (pvz. „klientas neatsako į aktyvų klausimą apie X — "
    "pokalbis nukrypo“). DRAUDŽIAMA: siūlyti diagnozę, "
    "kurti faktus, siūlyti veiksmus ar žingsnius, kartoti tai, kas akivaizdu. "
    "Jei vertingų pastabų nėra — parašyk tik OK."
)


def enabled() -> bool:
    return os.getenv("ANALYST", "on").lower() == "on"


def _allowed(note: str) -> bool:
    from .evidence import _fold

    low = _fold(note)
    if any(m in low for m in vocab("analyst_forbidden_marks")):
        return False
    return any(m in low for m in vocab("analyst_allowed_marks"))


def run_analyst(state: Any, rt: Any) -> list[str] | None:
    """One background read of the call -> advisory notes for the next narration
    (None when there is nothing to say). Reads engine.state, never writes it — the
    session hands the notes to the next turn. Best-effort: any hiccup returns None."""
    if not enabled():
        return None
    try:
        s = state
        if not s.intake.problem_type or s.closing.case_closed or s.closing.is_complete:
            return None
        from src.services.llm.client import llm_completion

        from .evidence import summary_lt
        from .understand import perception_model

        # Istorija v2: the analyst is the ONLY reader of the FULL transcript —
        # the narrator's window is short, so type-4 notes (an early detail no
        # longer visible) depend on this breadth. Capped to keep tokens sane.
        history = "\n".join(
            f"{'KLIENTAS' if m['role'] == 'user' else 'AGENTAS'}: {(m.get('content') or '')[:200]}"
            for m in s.messages[-60:]
            if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
        )
        ledger = summary_lt(s.diagnosis.evidence) if s.diagnosis.evidence else "(tuščias)"
        verdict = (s.resolution.procedure or {}).get("verdict") or "(nenustatyta)"
        # C wave (2026-09-08): the analyst sees the QUESTION REGISTRY's active
        # entry — the deterministic "what we are asking right now" — so the
        # type-5 deviation note compares reality against the plan.
        from .dialog_registry import active as _q_active

        q = _q_active(state, rt)
        # Damping (live 2026-09-08): a question asked THIS turn has no answer
        # yet — flagging "neatsako" then is noise. The deviation read only
        # makes sense once the same question needed a re-ask (asks >= 2).
        aktyvus = (
            f"{q.owner}/{q.key} (bandymas {q.asks})" if q is not None and q.asks >= 2 else "(nėra)"
        )
        user = (
            f"POKALBIS:\n{history}\n\nŽURNALAS (deterministiniai faktai): {ledger}\n"
            f"HIPOTEZĖ: {verdict}\nAKTYVUS KLAUSIMAS (registras): {aktyvus}\n\n"
            "Pastabos agentui (arba OK):"
        )
        content = llm_completion(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            model=perception_model(rt.config.model),
            temperature=0.2,
            # Reasoning models (gpt-oss) burn tokens on hidden thinking BEFORE
            # the answer — 180 returned an empty string (observed 2026-08-25).
            max_tokens=700,
        )
        notes = [
            line.strip().lstrip("-•* ").strip()
            for line in (content or "").splitlines()
            if line.strip().lstrip("-•* ").strip()
        ]
        notes = [n for n in notes if len(n) >= 12 and n.upper() != "OK"]
        # Boundary filter (live 2026-08-26: the model suggested ACTIONS —
        # "paprašykite patikrinti maitinimą" — which is the engine's job).
        # Deterministic whitelist: only the three agreed note types survive —
        # already-said, suspicious-fact, concept-confusion.
        notes = [n for n in notes if _allowed(n)][:2]
        if notes:
            rt.tracer.emit("analyst", notes=notes)
            # C wave: the deviation note is FLAG-ONLY — a separate trace event
            # so the deterministic layer (and the dashboards) can count it;
            # nothing routes on it yet.
            from .evidence import _fold as _f

            if any("nukryp" in _f(n) or "neatsako" in _f(n) for n in notes):
                rt.tracer.emit("analyst_flag", type="nukrypimas_nuo_plano")
        return notes or None
    except Exception:  # pragma: no cover - the analyst must never break a call
        logger.debug("analyst failed", exc_info=True)
        return None

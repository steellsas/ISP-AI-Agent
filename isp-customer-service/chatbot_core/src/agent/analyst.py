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

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Tu — TYLUSIS ANALITIKAS, padedantis interneto tiekėjo balso agentui. "
    "Skaitai pokalbį ir žurnalą, bet pats NEkalbi su klientu. Tavo darbas — "
    "iki 2 TRUMPŲ patariamųjų pastabų agentui apie KITĄ repliką, lietuviškai, "
    "kiekviena naujoje eilutėje su „- “ pradžioje. Pastabos gali būti TIK "
    "šių tipų: (1) klientas JAU pasakė kažką, ko agentas gali nebeklausti; "
    "(2) žurnalo faktas įtartinas — prieštarauja tam, ką klientas kartoja "
    "(gali būti blogai išgirsta) — verta pasitikslinti; (3) klientas painioja "
    "sąvokas ar įrenginius — įvardinti aiškiau. DRAUDŽIAMA: siūlyti diagnozę, "
    "kurti faktus, siūlyti veiksmus ar žingsnius, kartoti tai, kas akivaizdu. "
    "Jei vertingų pastabų nėra — parašyk tik OK."
)


def enabled() -> bool:
    return os.getenv("ANALYST", "on").lower() == "on"


def run_analyst(engine: Any) -> None:
    """One background read -> engine._analyst_notes (list[str] | None).
    Best-effort: any hiccup leaves the notes empty and the call untouched."""
    if not enabled():
        return
    try:
        s = engine.state
        if not s.problem_type or s.case_closed or s.is_complete:
            return
        from src.services.llm.client import llm_completion

        from .evidence import summary_lt
        from .understand import perception_model

        history = "\n".join(
            f"{'KLIENTAS' if m['role'] == 'user' else 'AGENTAS'}: {(m.get('content') or '')[:200]}"
            for m in s.messages[-14:]
            if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
        )
        ledger = summary_lt(s.evidence) if s.evidence else "(tuščias)"
        verdict = (s.resolution or {}).get("verdict") or "(nenustatyta)"
        user = (
            f"POKALBIS:\n{history}\n\nŽURNALAS (deterministiniai faktai): {ledger}\n"
            f"HIPOTEZĖ: {verdict}\n\nPastabos agentui (arba OK):"
        )
        content = llm_completion(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            model=perception_model(engine.config.model),
            temperature=0.2,
            max_tokens=180,
        )
        notes = [
            line.strip().lstrip("-•* ").strip()
            for line in (content or "").splitlines()
            if line.strip().lstrip("-•* ").strip()
        ]
        notes = [n for n in notes if len(n) >= 12 and n.upper() != "OK"][:2]
        engine._analyst_notes = notes or None
        if notes:
            engine.tracer.emit("analyst", notes=notes)
    except Exception:  # pragma: no cover - the analyst must never break a call
        logger.debug("analyst failed", exc_info=True)

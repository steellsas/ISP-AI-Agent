"""
LLM classifier — the PERCEIVE sensor (Phase 3.8 step 1, first slice).

The keyword detectors (agent/resolution.py) are the weak spot: they read a caller's
reply by substring match, so a clear human "yes" phrased outside the wordlist
("galėtume kartu patikrinti") returns None, the walker freezes, and the narration
drifts ahead — the dr_intro desync (docs/MASTANTIS_AGENTAS_SPEC.md, ARCHITEKTUROS_*).

This module replaces that reading with an LLM that understands MEANING. It is a SENSOR:
it returns a `CandidateObservation` and never touches state or the walker — the engine
still decides and routes (single decision-maker). It is deliberately narrow for this
slice (yes/no confirms only); other detectors migrate later.

Contract (docs/MASTANTIS_AGENTAS_SPEC.md §①):
- structured output validated against a schema (never free text),
- a strict label enum,
- `internally_inconsistent` for one-sentence self-contradiction ("nedega, ai ne, dega"),
- returns None on ANY failure so the caller can fall back to the keyword detector.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# yes / no / unclear — the confirm-step routing keys. Kept tiny and stable so the
# gate (and next_step_id's `on` map) can rely on it.
YES_NO_LABELS = ("yes", "no", "unclear")


class CandidateObservation(BaseModel):
    """What the classifier PERCEIVED — a candidate only; the solver/engine decides
    whether to trust it. Never written to state directly."""

    label: str = Field(description="one of: yes, no, unclear")
    internally_inconsistent: bool = Field(
        default=False, description="caller contradicted themselves in one sentence"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


_SYSTEM = (
    "You classify a caller's reply in a Lithuanian ISP phone support call. The agent "
    "asked a YES/NO question; decide what the caller's reply MEANS. Reply with JSON only:\n"
    '{"label": "yes"|"no"|"unclear", "internally_inconsistent": bool, "confidence": 0.0-1.0}\n'
    "- yes: they agree / confirm / consent / say it is done — including indirect Lithuanian "
    "phrasings ('galėtume', 'gerai, bandom', 'ką reikia daryti?', 'jau padariau', 'taip').\n"
    "- no: they decline / deny / say it did not work ('ne', 'nepavyko', 'vis tiek neveikia').\n"
    "- unclear: you genuinely cannot tell, or they only asked a question back.\n"
    "- internally_inconsistent: true if they contradict themselves in one sentence "
    "('nedega, ai ne, dega'). Judge MEANING, not keywords; tolerate speech-to-text noise."
)


def classify_yes_no(
    question: str, answer: str, model: str | None = None
) -> CandidateObservation | None:
    """Classify a reply to a yes/no question. Returns None on ANY failure (empty input,
    LLM/parse/validation error) so the caller falls back to the keyword detector — the
    conversation must never stall on a classifier hiccup."""
    if not answer or not answer.strip():
        return None
    try:
        from src.services.llm.client import llm_json_completion

        data = llm_json_completion(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": f"Agento klausimas: {question or '(patvirtinimas)'}\n"
                    f"Kliento atsakymas: {answer}",
                },
            ],
            model=model,
            temperature=0.0,
            max_tokens=120,
            validate_schema=CandidateObservation,
        )
        obs = CandidateObservation(**data)
        if obs.label not in YES_NO_LABELS:
            return None
        return obs
    except Exception as e:  # never let a classifier failure break the turn
        logger.warning(f"classify_yes_no fell back to keyword detector: {e}")
        return None

"""
LLM classifier — the PERCEIVE sensor (Phase 3.8 step 1).

The keyword detectors (agent/resolution.py) are the weak spot: they read a caller's
reply by substring match, so a clear human answer phrased outside the wordlist
("galėtume kartu patikrinti"; "gerai tada bandau… nė viena lemputė neužsidegė") returns
None or is mis-read, the walker freezes, and the narration drifts. Voice testing showed
this stalls the dead-router flow at the power step and mis-resolves the client-side flow.

This module replaces that reading with an LLM that understands MEANING, for ANY confirm
step (yes/no, lights, scope, restored, …), in ONE call that also decides whether the
caller actually ANSWERED (vs. still doing it / asking back / confused). It is a SENSOR:
it returns a CandidateObservation and never touches state or the walker — the engine
still decides and routes (single decision-maker; docs/MASTANTIS_AGENTAS_SPEC.md §①).

Returns None on ANY failure so the caller falls back to the keyword detector — the
conversation must never stall on a classifier hiccup.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CandidateObservation(BaseModel):
    """What the classifier PERCEIVED — a candidate only; the engine decides whether to
    trust it. `label` is one of the step's routing keys (or "unclear"); `is_answer` says
    whether the caller actually answered THIS step (so a brittle keyword turn-intent can
    no longer veto a turn that did answer)."""

    label: str = Field(description="one of the provided labels, or 'unclear'")
    is_answer: bool = Field(
        default=True, description="did the caller actually answer this step's question?"
    )
    internally_inconsistent: bool = Field(
        default=False, description="caller contradicted themselves in one sentence"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


def _system(options: dict[str, str]) -> str:
    opts = "\n".join(f'  - "{k}": {v}' for k, v in options.items())
    return (
        "You read a caller's reply in a Lithuanian ISP phone support call. The agent asked "
        "a question; pick which option MATCHES the caller's answer and whether they actually "
        "ANSWERED. The options (label: meaning):\n" + opts + "\n"
        "Reply with JSON only:\n"
        '{"label": one of the labels above or "unclear", "is_answer": bool, '
        '"internally_inconsistent": bool, "confidence": 0.0-1.0}\n'
        "- label: choose ONLY by MEANING (judge meaning, not keywords; tolerate speech-to-"
        "text noise). If the reply matches NONE of the meanings, label='unclear' — do NOT "
        "force a fit (e.g. 'susiradau routerį' is NOT a lights answer → unclear).\n"
        "- is_answer: true if the caller actually answered THIS question — even if they also "
        "said they were about to try ('gerai, bandau… nė viena lemputė neužsidegė' IS an "
        "answer). false if they are still doing it with no result, asked a question back, "
        "said they do not understand, or the reply does not address the question.\n"
        "- internally_inconsistent: true if they contradict themselves in one sentence.\n"
        "- 'unclear' + is_answer=false whenever you cannot confidently match a meaning."
    )


def classify_step(
    question: str, answer: str, options: dict[str, str], model: str | None = None
) -> CandidateObservation | None:
    """Classify a reply to a confirm step. `options` maps each routing key to its plain-
    language MEANING (the abstract keys yes/no/all/phone are meaningless to the model on
    their own). Returns None on ANY failure → caller falls back to the keyword detector."""
    if not answer or not answer.strip() or not options:
        return None
    allowed = set(options) | {"unclear"}
    try:
        from src.services.llm.client import llm_json_completion

        from .understand import perception_model as _perception_model

        data = llm_json_completion(
            messages=[
                {"role": "system", "content": _system(options)},
                {
                    "role": "user",
                    "content": f"Agento klausimas: {question or '(patvirtinimas)'}\n"
                    f"Kliento atsakymas: {answer}",
                },
            ],
            model=_perception_model(model),
            temperature=0.0,
            max_tokens=150,
            validate_schema=CandidateObservation,
        )
        obs = CandidateObservation(**data)
        if obs.label not in allowed:
            return None
        return obs
    except Exception as e:  # never let a classifier failure break the turn
        logger.warning(f"classify_step fell back to keyword detector: {e}")
        return None

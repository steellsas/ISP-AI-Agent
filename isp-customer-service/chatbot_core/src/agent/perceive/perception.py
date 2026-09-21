"""What one caller turn was — ONE reading, in one shape (wave 2a).

The same utterance used to be read by three or four paths (the LLM pass, the keyword
extractor, the pending-key reader, the step classifier), each with its own shape, and
~8 arbitration guards decided whose answer counted. This module gives the reading a
single shape and two cheap rules that replace most of that arbitration:

**The fast path.** A closed answer to a standing question ("taip", "ne", "dega",
"palaukit") is read deterministically — no LLM call, no latency. Most voice turns are
exactly that.

**Quote grounding.** A fact the LLM reports must come with the caller's own words, and
the code checks that those words are really in the utterance. A hallucinated fact has no
quote to show (live 2026-08-10: five facts the caller never said poisoned the ledger).

The engine still decides what a reading MEANS — this module only reads.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# How the reading was taken.
Source = Literal["fast_path", "llm", "keywords"]


class Fact(BaseModel):
    """One canonical fact value plus the caller's words that support it."""

    value: str
    quote: str | None = None
    grounded: bool = True  # False = the quote could not be found in the utterance


class Perception(BaseModel):
    """One turn, read once."""

    source: Source = "keywords"
    turn_type: str = "answer"  # answer | question | deviation | confusion | contradiction
    facts: dict[str, Fact] = Field(default_factory=dict)
    # The answer to the step whose question is out: {label, is_answer, confidence, …}.
    step: dict[str, Any] | None = None
    understood: str = ""  # half-sentence the narrator may reflect back
    confusion: str = ""
    confidence: float = 0.5

    def values(self) -> dict[str, str]:
        """The facts as the ledger takes them (key -> canonical value)."""
        return {key: fact.value for key, fact in self.facts.items()}

    def as_understanding(self) -> dict[str, Any]:
        """The shape the rest of the engine already reads (`turn.understanding`)."""
        return {
            "facts": self.values(),
            "type": self.turn_type,
            "understood": self.understood,
            "confusion": self.confusion,
            "confidence": self.confidence,
            "step": self.step,
        }


def fast_read(state: Any, utterance: str, options: dict[str, str] | None) -> Perception | None:
    """A closed answer to a standing question, read without the model. None = this turn
    needs the full reading.

    Only SHORT utterances qualify (`short_utterance_max_words`): the moment a caller adds
    anything of their own, the meaning is no longer a lookup.
    """
    from ..contract import limits
    from .detectors import detect_yes_no, is_backchannel, is_real_question

    text = (utterance or "").strip()
    if not text or is_real_question(text):
        return None
    if len(text.split()) > limits.get("short_utterance_max_words"):
        return None
    if is_backchannel(text):
        # "mhm", "gerai" — heard, nothing claimed.
        return Perception(source="fast_path", turn_type="answer", confidence=1.0)
    pending = _pending_fact(state, text)
    if pending is not None:
        key, value = pending
        step = _step_from(options, detect_yes_no(text)) if options else None
        return Perception(
            source="fast_path",
            turn_type="answer",
            facts={key: Fact(value=value, quote=text)},
            step=step,
            # The narrator reflects the answer back ("Gerai — lemputės nedega"): on this
            # path the half-sentence comes from the pack's own wording, not the model.
            understood=_said(key, value),
            confidence=1.0,
        )
    # A bare yes/no with NO evidence question pending is NOT enough: the step's answer
    # often implies a fact the pack declares, and only the model reads that from a
    # garbled utterance ("ne daganiai viena" = lights off). The full reading takes it.
    return None


def _said(key: str, value: str) -> str:
    """How this answer reads back, from the pack's own labels ("routerio lemputės
    nedega") — the narrator reflects it, so it must read like speech."""
    from ..evidence import gloss_label, gloss_value

    return f"{gloss_label(key)} {gloss_value(value, key)}".strip()


def _pending_fact(state: Any, text: str) -> tuple[str, str] | None:
    """The evidence question that is out, answered by this short utterance."""
    key = state.diagnosis.pending_evidence_key
    if not key:
        return None
    from ..evidence import read_pending_answer, spec_for

    spec = spec_for((state.resolution.procedure or {}).get("verdict")) or {}
    item = (spec.get("client") or {}).get(key)
    value = read_pending_answer(str(key), text, item)
    return (str(key), value) if value is not None else None


def _step_from(options: dict[str, str], outcome: Any) -> dict[str, Any] | None:
    """A yes/no the asked step branches on (only when the step offers that branch)."""
    if outcome is None:
        return None
    label = str(getattr(outcome, "value", outcome)).lower()
    if label not in options:
        return None
    return {"label": label, "is_answer": True, "internally_inconsistent": False, "confidence": 1.0}


def ground(perception: Perception, utterance: str) -> Perception:
    """Drop every fact whose quote is not in what the caller actually said.

    A fact WITHOUT a quote is left to the engine's own corroboration rules (an older
    model, or a fact read from context rather than quoted).
    """
    from ..evidence import _fold

    said = _fold(utterance or "")
    kept: dict[str, Fact] = {}
    for key, fact in perception.facts.items():
        quote = (fact.quote or "").strip()
        if not quote:
            kept[key] = fact
            continue
        if _fold(quote) in said:
            kept[key] = fact
        else:
            kept[key] = fact.model_copy(update={"grounded": False})
    return perception.model_copy(update={"facts": kept})

"""
Structured dialog slots — durable, typed memory for the identification phase.

Phase 3.5 (docs/pokalbio_variklis.md §3). The free ReAct loop kept the address
only in the LLM's context, so a single garbled turn could overwrite a resolved
address (observed: "Tilžės 60-7" -> "TILŽĖ 610"). These slots make the address
DURABLE memory with a confidence + status per level, so a low-confidence
mishearing never silently overwrites a DB-confirmed value.

Additive by design: it sits ALONGSIDE the existing AgentState fields and does not
change behaviour yet. The policy (1.3) and NLU (1.4) build on it; the eventual
LangGraph migration uses it as the typed graph state.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SlotStatus(StrEnum):
    EMPTY = "empty"  # not said yet
    HEARD = "heard"  # heard but not confirmed against the DB (low confidence)
    RESOLVED = "resolved"  # matched against the street/house registry (high)
    CONFIRMED = "confirmed"  # the caller confirmed it by voice


# Strength ordering — a weaker reading must not overwrite a stronger slot value.
_RANK = {
    SlotStatus.EMPTY: 0,
    SlotStatus.HEARD: 1,
    SlotStatus.RESOLVED: 2,
    SlotStatus.CONFIRMED: 3,
}


class Slot(BaseModel):
    value: str | None = None
    confidence: float = 0.0
    status: SlotStatus = SlotStatus.EMPTY

    def propose(self, value: str | None, confidence: float, status: SlotStatus) -> bool:
        """
        Offer a new reading for this slot.

        Applied only if it does not DOWNGRADE a stronger value: a HEARD
        mishearing cannot overwrite a RESOLVED/CONFIRMED value that DIFFERS (the
        policy asks the caller to confirm instead of silently switching). A reading
        of equal-or-higher strength, or a re-reading of the same value, always
        applies. Returns True if the slot changed.
        """
        if not value:
            return False
        if _RANK[status] < _RANK[self.status] and value != self.value:
            return False
        self.value = value
        self.confidence = confidence
        self.status = status
        return True


class ClientProfileState(BaseModel):
    """The address slots collected during identification (durable across turns)."""

    city: Slot = Field(default_factory=Slot)
    street: Slot = Field(default_factory=Slot)
    house: Slot = Field(default_factory=Slot)
    apartment: Slot = Field(default_factory=Slot)
    account_code: Slot = Field(default_factory=Slot)

    def update_from_resolution(self, resolution: dict) -> None:
        """
        Fold a resolve_address per-level `resolution` (§8.2 contract) into the slots.

        Runs on EVERY resolve_address call, success or not, so what the caller
        said accumulates as durable memory:
        - status ok / recovered  -> RESOLVED (DB-confirmed value, high confidence)
        - any other non-empty level with a `given` value -> HEARD (low confidence)
        - skipped / not_given     -> left untouched
        The per-slot `propose` guard prevents a HEARD reading from clobbering an
        already RESOLVED/CONFIRMED level.
        """
        levels = {
            "city": self.city,
            "street": self.street,
            "house": self.house,
            "apartment": self.apartment,
        }
        for level, slot in levels.items():
            info = resolution.get(level) or {}
            status = info.get("status")
            if status in ("ok", "recovered"):
                slot.propose(info.get("matched") or info.get("given"), 0.9, SlotStatus.RESOLVED)
            elif status not in (None, "skipped", "not_given") and info.get("given"):
                slot.propose(info.get("given"), 0.5, SlotStatus.HEARD)

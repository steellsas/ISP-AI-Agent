"""The Case — which faults the facts still allow (wave 3, review findings N, P).

Before this, one verdict was computed in code and the conversation had exactly one live
hypothesis; a fact that disagreed with it could only "doubt" it. A real call is not like
that: several faults explain the same complaint, and the questions are what separate them.

So the Case holds CANDIDATES. Every card says when it is a candidate and what rules it
out, and this module answers one question over those cards: given what we know, what is
still possible?

    matched    every condition the card names holds
    possible   nothing contradicts it, but something it names is still unknown
    ruled_out  a condition it names is false, or one of its `rules_out` holds

Nothing here decides what to say or do — that is the engine's job (the next step). This
is a pure function of the facts, so it is testable as a table and cannot drift with the
conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contract import cards as catalog
from .contract.schema import Condition, FaultCard


@dataclass(frozen=True)
class Candidate:
    """One fault as the facts currently leave it."""

    fault: str
    status: str  # matched | possible | ruled_out
    why: tuple[str, ...] = field(default_factory=tuple)  # conditions that hold
    unknown: tuple[str, ...] = field(default_factory=tuple)  # what is not known yet
    against: tuple[str, ...] = field(default_factory=tuple)  # what rules it out

    @property
    def open(self) -> bool:
        return self.status in ("matched", "possible")


def judge(card: FaultCard, facts: dict[str, str]) -> Candidate:
    """Where this one card stands. A condition whose fact is UNKNOWN keeps the card alive
    — "we have not asked" is not "it is not so" — and it is what the engine asks next."""
    against = tuple(str(c) for c in (Condition.parse(t) for t in card.rules_out) if c.holds(facts))
    if against:
        return Candidate(card.fault, "ruled_out", against=against)

    wanted, alternatives = card.when.parsed()
    holds = tuple(str(c) for c in wanted if c.holds(facts) is True)
    fails = tuple(str(c) for c in wanted if c.holds(facts) is False)
    unknown = tuple(str(c) for c in wanted if c.holds(facts) is None)
    if fails:
        return Candidate(card.fault, "ruled_out", why=holds, against=fails)

    if alternatives:
        any_holds = [c for c in alternatives if c.holds(facts) is True]
        any_unknown = [c for c in alternatives if c.holds(facts) is None]
        if not any_holds and not any_unknown:
            return Candidate(
                card.fault, "ruled_out", why=holds, against=tuple(str(c) for c in alternatives)
            )
        holds += tuple(str(c) for c in any_holds)
        unknown += tuple(str(c) for c in any_unknown if not any_holds)

    status = "possible" if unknown else "matched"
    return Candidate(card.fault, status, why=holds, unknown=unknown)


def candidates(facts: dict[str, str]) -> list[Candidate]:
    """Every card judged against the facts, the strongest first (matched, then possible,
    then ruled out). The fallback card is never a candidate — it is what the engine falls
    back TO when this list has nothing open."""
    order = {"matched": 0, "possible": 1, "ruled_out": 2}
    judged = [judge(card, facts) for card in catalog.cards().values() if not card.fallback]
    return sorted(judged, key=lambda c: (order[c.status], c.fault))


def open_candidates(facts: dict[str, str]) -> list[Candidate]:
    """The faults still in play."""
    return [c for c in candidates(facts) if c.open]


def fallback() -> FaultCard | None:
    """The honest "we cannot tell over the phone" card, when no fault fits."""
    return next((c for c in catalog.cards().values() if c.fallback), None)

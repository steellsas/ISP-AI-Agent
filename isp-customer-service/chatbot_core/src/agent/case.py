"""The Case — which faults the facts still allow, and what to do next (wave 3).

Before this, one verdict was computed in code and the conversation had exactly one live
hypothesis; a fact that disagreed with it could only "doubt" it. A real call is not like
that: several faults explain the same complaint, and the questions are what separate them.

So the Case holds CANDIDATES. Every card says when it is a candidate and what rules it
out, and this module answers one question over those cards: given what we know, what is
still possible?

    matched    every condition the card names holds
    possible   nothing contradicts it, but something it names is still unknown
    ruled_out  a condition it names is false, or one of its `rules_out` holds

`next_move` answers the only other question: what now? Learn the fact that separates the
open candidates, run the settled fault's solution, or admit honestly that this one is not
solvable over the phone.

HOW a fact is learned is not written in the cards — the engine indexes it (Andrius,
2026-09-22). Telemetry facts come from the probe declared in signals.yaml; anything a
module `produces` comes from that module; the rest is a question to the caller. The order
is deliberate: look first, act second, ask last, because the caller's patience is the
scarcest thing in the call. That indexing is also what makes a new fault cheap — declare
`when:` over facts and the engine already knows how to get each one.

Everything here is a pure function of the facts, so it is a table test and cannot drift
with the conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contract import cards as catalog
from .contract import signals as signal_catalog
from .contract.schema import Condition, FaultCard, ModuleCall


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
    judged = [
        judge(card, facts)
        for card in catalog.cards().values()
        # A fallback is what we reach FOR; a rule-named card (a service never ordered, a
        # ticket already open) is named by the engine, never by the line.
        if not card.fallback and card.set_by == "facts"
    ]
    return sorted(judged, key=lambda c: (order[c.status], c.fault))


def open_candidates(facts: dict[str, str]) -> list[Candidate]:
    """The faults still in play."""
    return [c for c in candidates(facts) if c.open]


def fallback() -> FaultCard | None:
    """The honest "we cannot tell over the phone" card, when no fault fits."""
    return next((c for c in catalog.cards().values() if c.fallback), None)


# --- how a fact is learned -----------------------------------------------------------

# Cheapest for the caller first: look at the line, then do something together, then ask.
SOURCE_ORDER = {"probe": 0, "module": 1, "ask": 2}


@dataclass(frozen=True)
class Source:
    """Where a fact can come from."""

    kind: str  # probe | module | ask
    fact: str
    tool: str | None = None
    module: str | None = None
    ask: str | None = None  # phrase key (kind: ask)

    @property
    def rank(self) -> int:
        return SOURCE_ORDER[self.kind]


def worth_asking(fact: str, card: FaultCard | None, facts: dict[str, str]) -> bool:
    """Is this fact worth asking YET? A need may name conditions that must hold first — the
    cable type means nothing until we know it is a computer."""
    need = card.needs.get(fact) if card else None
    if need is None or not need.when:
        return True
    return all(Condition.parse(text).holds(facts) is True for text in need.when)


def reason_for(fact: str, card: FaultCard | None) -> str | None:
    """Half a sentence on why we are asking, as the card words it."""
    from .contract.locale import maybe_phrase

    need = card.needs.get(fact) if card else None
    return maybe_phrase(need.why) if need else None


def sources_for(fact: str, card: FaultCard | None = None) -> list[Source]:
    """Every way this fact can be learned, cheapest first.

    The card adds only what an index cannot know: the wording of the question, and what a
    value means for THAT fault.
    """
    found: list[Source] = []
    if fact in signal_catalog.get():
        probe = signal_catalog.probe()
        if probe:
            found.append(Source("probe", fact, tool=probe))
    for name, spec in catalog.modules().items():
        if fact in spec.produces:
            found.append(Source("module", fact, module=name))
    need = card.needs.get(fact) if card else None
    if need is not None:
        if need.probe:
            found.append(Source("probe", fact, tool=need.probe))
        if need.ask:
            found.append(Source("ask", fact, ask=need.ask))
    return sorted(found, key=lambda s: (s.rank, s.module or s.tool or ""))


# --- what to do next ----------------------------------------------------------------


class _NoCard:
    news = False
    fallback = False


_NO_CARD = _NoCard()


@dataclass(frozen=True)
class Move:
    """The Case's answer to "what now". The engine turns it into a plan; the wording stays
    the narrator's."""

    kind: str  # learn | solve | inform | escalate
    fact: str | None = None
    source: Source | None = None
    fault: str | None = None
    steps: tuple[ModuleCall, ...] = field(default_factory=tuple)
    why: str = ""


def next_move(facts: dict[str, str], *, unavailable: frozenset[str] = frozenset()) -> Move:
    """One step of the case.

    `unavailable` names facts already tried and not obtained (a question the caller could
    not answer, a probe that is down), so the same dead end is never chosen twice.
    """
    open_ = open_candidates(facts)
    if not open_:
        return _honest_end("no fault card fits these facts")

    matched = [c for c in open_ if c.status == "matched"]
    possible = [c for c in open_ if c.status == "possible"]

    # News outranks a fault: there is nothing to diagnose, only something to tell (a debt, an
    # outage, a node down). It also means the caller is not asked to do anything at all.
    news = next((c for c in matched if (catalog.card(c.fault) or _NO_CARD).news), None)
    if news is not None:
        return Move("inform", fault=news.fault, why=f"{news.fault} is news, not a fault")

    # One fault fits and nothing else is still open: do what its card says.
    if len(matched) == 1 and not possible:
        return _solve(matched[0].fault, facts, unavailable)

    # Otherwise learn the fact that separates the most candidates.
    wanted = _discriminator(open_, facts, unavailable)
    if wanted is not None:
        fact, source = wanted
        return Move("learn", fact=fact, source=source, why=f"{len(open_)} faults still open")

    if matched:
        return _solve(matched[0].fault, facts, unavailable)
    return _honest_end("nothing left to check and no fault is settled")


def _honest_end(why: str) -> Move:
    card = fallback()
    return Move("escalate", fault=card.fault if card else None, why=why)


def _solve(fault: str, facts: dict[str, str], unavailable: frozenset[str]) -> Move:
    """The card's own solution for the facts we have — or the fact that chooses between
    its branches."""
    card = catalog.card(fault)
    if card is None:  # pragma: no cover - a fault id always comes from the catalogue
        return _honest_end(f"{fault}: no card")
    for solution in card.solution:
        conditions = [Condition.parse(text) for text in solution.when]
        if any(c.holds(facts) is False for c in conditions):
            continue
        pending = [c.fact for c in conditions if c.holds(facts) is None]
        if pending:
            for fact in pending:
                if fact in unavailable or not worth_asking(fact, card, facts):
                    continue
                found = sources_for(fact, card)
                if found:
                    return Move(
                        "learn",
                        fact=fact,
                        source=found[0],
                        fault=fault,
                        why=f"{fault}: which solution applies",
                    )
            continue
        if solution.hands_to:
            return _solve(solution.hands_to, facts, unavailable)
        return Move("solve", fault=fault, steps=tuple(solution.steps), why=f"{fault} confirmed")
    return Move("escalate", fault=fault, why=f"{fault}: no solution fits these facts")


def _discriminator(
    open_: list[Candidate], facts: dict[str, str], unavailable: frozenset[str]
) -> tuple[str, Source] | None:
    """The fact worth learning next: the one the most open candidates hang on. Ties go to
    the cheapest source, then alphabetically, so the same call always asks the same thing
    in the same order."""
    weight: dict[str, int] = {}
    where: dict[str, Source] = {}
    for candidate in open_:
        card = catalog.card(candidate.fault)
        for text in candidate.unknown:
            fact = Condition.parse(text).fact
            if fact in facts or fact in unavailable:
                continue
            if not worth_asking(fact, card, facts):
                continue  # its own conditions do not hold yet
            found = sources_for(fact, card)
            if not found:
                continue
            weight[fact] = weight.get(fact, 0) + 1
            best = where.get(fact)
            if best is None or found[0].rank < best.rank:
                where[fact] = found[0]
    if not weight:
        return None
    fact = sorted(weight.items(), key=lambda kv: (-kv[1], where[kv[0]].rank, kv[0]))[0][0]
    return fact, where[fact]


def clarify_for(fault: str | None, fact: str | None) -> str | None:
    """What to say when a bare "ne" answers this fact's question.

    "Ne" to "does it fail on ALL devices?" could mean either reading, so the engine names
    both instead of acting on a coin flip (the behaviour came from the evidence drive; the
    wording is the card's now).
    """
    from .contract.locale import maybe_phrase

    card = catalog.card(fault) if fault else None
    need = card.needs.get(fact) if card and fact else None
    return maybe_phrase(need.clarify) if need else None

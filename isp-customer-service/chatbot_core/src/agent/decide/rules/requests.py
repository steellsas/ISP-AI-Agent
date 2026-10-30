"""Request rules (D-11, owner 2026-09-16) — what the agent registers or answers, not solves.

A `register` intent (a bill, a contract, moving, a wish) is outside the agent's knowledge:
it is never answered or explained. After identification the caller's own words become a
ticket of the intent's type for the responsible person, through the same contact dialogue
a fault ticket uses. An `answer` intent (the status of a registration) is answered from
the customer's open tickets.
"""

from __future__ import annotations

from typing import Any


def start_request(state: Any, rt: Any, ticket_type: str | None = None) -> None:
    """Register the caller's question for the responsible person (contacts first)."""
    from ...execute.ticket import request_ticket
    from ...intents import problem_entry

    ticket_type = ticket_type or problem_entry(state.intake.problem_type).get("ticket_type")
    rt.tracer.emit("decision", intent="request", action="register", value=ticket_type)
    request_ticket(state, rt, "ne_musu_klausimas", request_type=ticket_type)


def answer_ticket_status(state: Any, rt: Any) -> None:
    """The status of the caller's registration — or that there is none open."""
    from . import open_ticket

    if state.identity.open_tickets:
        open_ticket.repeat_call(state, rt, state.identity.open_tickets[0])
        return
    state.diagnosis.verdicts["network"] = {"reason": "no_open_ticket", "skipped": True}
    rt.tracer.emit("verdict", reason="no_open_ticket", source="open_tickets")


def disputes_debt(text: str | None) -> bool:
    """The caller disagrees with the debt or does not understand it."""
    from ...contract.locale import vocab
    from ...perceive.payment_claim import read_payment_claim

    low = (text or "").lower()
    if not any(m in low for m in vocab("debt_dispute")):
        # „Liepos mėnesį 40 eur" after the debt news is a payment claim without the verb.
        claim = read_payment_claim(text)
        return bool(claim.get("amount") and claim.get("when"))
    # „O kiek nemokėjau?" asks for the amount we have just said — it is answered from the news,
    # not offered to the responsible person. Live 2026-10-07 the bare „mokėjau" inside
    # „ne mokėjau" read as „aš mokėjau", and the caller heard „sąskaitų detalių aš nematau"
    # right after being told 49,98 € (wave 9, T5). A real objection still wins.
    if any(m in low for m in vocab("debt_amount_question")):
        return any(m in low for m in vocab("debt_dispute_strong"))
    return True


def _debt_news_open(state: Any) -> bool:
    """The debt news was told and nothing is registered for it yet."""
    from ...faults import verdict_flag

    reason = (state.diagnosis.verdicts.get("network") or {}).get("reason")
    return bool(
        state.diagnosis.news_delivered
        and verdict_flag(reason, "inform") == "debt"
        and not state.ticket.request_type
        and not state.ticket.ticket_id
    )


def wants_handover(text: str | None) -> bool:
    """„Užregistruokit", „sujunkite su buhalterija" — the caller asks for a person."""
    from ...contract.locale import vocab
    from ...perceive.detectors import detect_ticket_consent

    low = (text or "").lower()
    if detect_ticket_consent(text) == "no":
        return False
    return any(m in low for m in vocab("debt_handover_request"))


def debt_dispute_due(state: Any, user_input: str | None) -> bool:
    """The caller disputes the debt news (or asks for a person) and no dispute is running."""
    return bool(
        state.closing.debt_offer in (None, "declined")
        and _debt_news_open(state)
        and (disputes_debt(user_input) or wants_handover(user_input))
    )


def debt_dialogue_running(state: Any) -> bool:
    """The engine collects the payment details or waits for the answer to its offer."""
    return state.closing.debt_offer in ("facts", "asked") and _debt_news_open(state)


def _clean(text: str | None) -> str:
    """The caller's words for a ticket: no fillers, no dots of a cut sentence."""
    import re

    out = re.sub(r"\b(m{2,}|e{2,}|hmm+|aaa+)\b[.,]*", "", text or "", flags=re.IGNORECASE)
    out = re.sub(r"\.{2,}|…", "", out)
    return re.sub(r"\s+", " ", out).strip(" ,")


def _note(state: Any, text: str | None) -> None:
    """What the caller said in the dispute: the payment details and their questions."""
    from ...perceive.payment_claim import read_payment_claim

    c = state.closing
    c.debt_claim = {**c.debt_claim, **read_payment_claim(text)}
    said = _clean(text)
    if said and _asks_a_question(text) and said not in c.debt_questions:
        c.debt_questions = [*c.debt_questions, said]


def _claims_payment(state: Any, text: str | None) -> bool:
    from ...contract.locale import vocab
    from ...perceive.payment_claim import read_payment_claim

    low = (text or "").lower()
    return bool(state.closing.debt_claim or read_payment_claim(text)) or any(
        m in low for m in vocab("payment_claim_words")
    )


def _debt_consent(text: str | None) -> str | None:
    """The answer to „Ar registruoti?" in a dispute — „pasižiūrėkit" asks us to check: a yes."""
    from ...contract.locale import vocab
    from ...perceive.detectors import detect_ticket_consent

    answer = detect_ticket_consent(text)
    if answer is None and any(m in (text or "").lower() for m in vocab("debt_consent_extra")):
        return "yes"
    return answer


def _asks_a_question(text: str | None) -> bool:
    """A question by its form — „nežinau, kaip čia" is not one, „kodėl nematot?" is."""
    from ...contract.locale import vocab
    from ...perceive.detectors import is_real_question

    t = (text or "").strip()
    opens = t.lower().split()[:2]
    return is_real_question(t) and (
        "?" in t or any(w in vocab("debt_question_openers") for w in opens)
    )


def debt_offer_turn(state: Any, rt: Any, user_input: str | None) -> str | None:
    """After the debt news (Andrius, 2026-10-30): the agent explains what it sees; what it
    cannot answer, and a disputed debt, go to the responsible person — with the caller's own
    payment details (when, how, how much: the payment is searched by them).

    Returns what the engine says this turn:
      "ask_facts" — the caller says they paid: ask for the missing details (twice at most);
      "offer"     — the details are in (or it is not about a payment): offer to register;
      "explain"   — a question while the offer stands: what the agent sees, then the offer;
      "clarify"   — an unclear answer to the offer: asked again, never taken as a no;
      "start"     — yes: the contact dialogue starts;
      "declined"  — a clear no;
      None        — not this rule's turn.
    """
    from ...contract import limits
    from ...perceive.payment_claim import missing_parts
    from ..question import clear, register

    c = state.closing
    if not _debt_news_open(state):
        return None
    if c.debt_offer == "facts":
        _note(state, user_input)
        if (
            missing_parts(c.debt_claim)
            and c.debt_claim_asks < limits.get("debt_claim_asks_max")
            and not wants_handover(user_input)
        ):
            c.debt_claim_asks += 1
            register(state, rt, "inform", "debt_claim")
            rt.tracer.emit("decision", intent="debt_offer", action="ask_facts")
            return "ask_facts"
        return _offer(state, rt)
    if c.debt_offer == "asked":
        answer = _debt_consent(user_input)
        if answer == "yes" or (answer is None and wants_handover(user_input)):
            c.debt_offer = "answered"
            clear(state, rt, "debt_offer")
            start_request(state, rt, "billing_request")
            return "start"
        if answer == "no":
            c.debt_offer = "declined"
            clear(state, rt, "debt_offer")
            rt.tracer.emit("decision", intent="debt_offer", action="declined")
            return "declined"
        _note(state, user_input)
        register(state, rt, "inform", "debt_offer")
        if _asks_a_question(user_input):
            rt.tracer.emit("decision", intent="debt_offer", action="explain")
            return "explain"
        c.debt_offer_unclear += 1
        rt.tracer.emit("decision", intent="debt_offer", action="clarify", n=c.debt_offer_unclear)
        return "clarify"
    if debt_dispute_due(state, user_input):
        if not state.ticket.request_note:
            state.ticket.request_note = _clean(user_input)[:200]
        if _claims_payment(state, user_input):
            c.debt_offer = "facts"
            return debt_offer_turn(state, rt, user_input)
        _note(state, user_input)
        return _offer(state, rt)
    return None


def _offer(state: Any, rt: Any) -> str:
    from ..question import register

    state.closing.debt_offer = "asked"
    register(state, rt, "inform", "debt_offer")
    rt.tracer.emit("decision", intent="debt_offer", action="ask")
    return "offer"


def debt_claim_text(state: Any) -> str:
    """„liepos mėn., banko pavedimu, 40 €" — the details as the caller gave them."""
    from ...perceive.payment_claim import PARTS

    claim = state.closing.debt_claim
    return ", ".join(claim[p] for p in PARTS if claim.get(p))

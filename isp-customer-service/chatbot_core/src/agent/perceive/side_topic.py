"""Side-topic signal — is this turn a deviation (a real question with no usable
facts) while the problem is being solved?"""

from __future__ import annotations

from ..contract.locale import vocab
from ..dialog_utils import last_agent_question


def classify_side_topic(state, rt, user_input: str | None) -> bool:
    """Is THIS turn a deviation (a real question with no usable facts)
    during analysis/solving? Sets the per-turn flag + the streak; a
    productive turn resets the streak. Mechanics turns (ticket dialogue,
    conflict clarify, end-confirm) are never deviations — their owners
    handle them."""
    from ..evidence import extract_client_facts
    from .detectors import is_real_question

    s = state
    state.turn.side_topic_active = False
    if not user_input or not s.identity.customer_id or s.closing.case_closed or state.ticket.stage:
        return False
    from ..decide.hypothesis import due

    if (
        due(state, "conflict") is not None
        or state.dialog.end_confirm_pending
        or state.dialog.resume_hold_due
        or state.closing.debt_offer == "asked"
    ):
        return False
    # A disputed debt answers our own news — the debt offer owns it (D-11).
    from ..decide.rules.requests import debt_dispute_due

    if debt_dispute_due(state, user_input):
        return False
    # Ticket demand is NEVER a side topic (live 2026-08-13: "Išregistruoti
    # meistrą ir paleisti internetą…" got type=deviation and the side_topic
    # LLM talked the caller OUT of the registration) — the demand machinery
    # in the solving path owns this turn.
    from .detectors import detect_refuse_or_ticket

    if detect_refuse_or_ticket(user_input) == "demand":
        state.dialog.side_topic_streak = 0
        rt.tracer.emit("decision", intent="side_topic", action="ticket_demand_passthrough")
        return False
    # How-to / help requests while an instruction or question stands are ON
    # TASK by definition (live 2026-08-21: "O kaip tai padaryti?" at the
    # bridge instruction got the FAQ "ne mano sritis") — the step explains.
    if is_howto(user_input) and (
        state.diagnosis.pending_evidence_key or (s.resolution.procedure or {}).get("asked")
    ):
        state.dialog.side_topic_streak = 0
        rt.tracer.emit("decision", intent="side_topic", action="on_task_howto")
        return False
    # The understanding pass judged this turn IN CONTEXT — but its type is
    # ONE model field, and side_topic FREEZES the engine, so a single sensor
    # may not decide alone (live 2026-08-10: "Galim dabar patikrinti" got
    # type=question and the answer was answered with a price non-sequitur).
    # CORROBORATION rule: enter only when a deterministic signal agrees —
    # a question word in the text or a FAQ keyword hit.
    u = state.turn.understanding
    if u is not None:
        if u["type"] in ("question", "deviation") and not u["facts"]:
            if extract_client_facts(user_input):
                # The keyword layer read facts the pass missed — an
                # informative interruption, not a deviation (they already
                # landed on the ledger via the always-on supplement).
                state.dialog.side_topic_streak = 0
                return False
            from ..faq import match as faq_match

            # A question ABOUT the current instruction is NOT a deviation
            # (live 2026-08-11: "Kur jungti tą kabelį į kompiuterį?" got
            # "tai nėra mano sritis"). FAQ topics stay side topics.
            if not faq_match(user_input) and on_task_question(state, rt, user_input):
                rt.tracer.emit("decision", intent="side_topic", action="on_task")
                state.dialog.side_topic_streak = 0
                return False
            corroborated = is_real_question(user_input) or bool(faq_match(user_input))
            if corroborated:
                state.turn.side_topic_active = True
                state.dialog.side_topic_streak += 1
                rt.tracer.emit(
                    "decision",
                    intent="side_topic",
                    action="enter",
                    streak=state.dialog.side_topic_streak,
                )
                return True
            # The model felt a deviation but the text carries no question —
            # treat as an on-topic turn (the evidence/solver flow continues).
            rt.tracer.emit("decision", intent="side_topic", action="uncorroborated")
            state.dialog.side_topic_streak = 0
            return False
        state.dialog.side_topic_streak = 0
        return False
    if not is_real_question(user_input):
        state.dialog.side_topic_streak = 0
        return False
    if extract_client_facts(user_input):
        # An informative interruption ANSWERS things — not a deviation.
        state.dialog.side_topic_streak = 0
        return False
    from ..faq import match as faq_match

    if not faq_match(user_input) and on_task_question(state, rt, user_input):
        rt.tracer.emit("decision", intent="side_topic", action="on_task")
        state.dialog.side_topic_streak = 0
        return False
    state.turn.side_topic_active = True
    state.dialog.side_topic_streak += 1
    rt.tracer.emit(
        "decision",
        intent="side_topic",
        action="enter",
        streak=state.dialog.side_topic_streak,
    )
    return True


def is_howto(text: str | None) -> bool:
    """A 'how do I do that / help me' request — about the standing task."""
    low = f" {(text or '').lower()} "
    return any(m in low for m in vocab("howto_marks"))


def on_task_question(state, rt, user_input: str | None) -> bool:
    """The 'deviation' shares content words with the agent's LAST reply —
    it is a question ABOUT the current instruction ("Kur jungti tą
    kabelį?"), not a side topic; the solver/narrator answers it in place.
    Folded prefix-overlap (≥5 chars) so inflections and dropped diacritics
    still match ("jungti" ~ "prijungsite", "kabelį" ~ "kabelio")."""
    last = last_agent_question(state) or ""
    if not last or not user_input:
        return False
    from ..evidence import _fold

    last_f = _fold(last)
    for tok in _fold(user_input).replace("?", " ").replace(",", " ").split():
        tok = tok.strip(".!?")
        if len(tok) >= 5 and tok[:5] in last_f:
            return True
    return False

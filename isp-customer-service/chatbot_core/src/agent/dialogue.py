"""The dialogue layer (STRUKTURA_V3 §4, stage 5) — HOW this reply talks, apart from WHAT it is for.

Andrius (2026-10-08): *„turi bendrauti, kad jaustųsi, kad klientas girdimas, ir jam
paaiškinam, jei kas neaišku; taip pat turi galimybę pasiklausti, jei kažko neišgirdo ar ne taip
suprato; taip pat ir klientą turi nuvesti į gedimo šalinimą, jei jis nukrypsta."*

Every reply has the same shape:

    [acknowledgement] + [ONE dialogue move] + [the phase goal]

The phase goal is decide's (the Case step, the identification rung, the ticket question). The
move is chosen HERE, once per turn, from the signals perceive and decide left on the state.
Before stage 5 those signals each wrote their own card section — up to five at once, some of
them contradicting each other („say you cannot advise" next to „NEVER say you cannot
advise"). Now exactly one move is chosen, in this order:

    RETURN    the caller went off the fault path — answer briefly, come back
    ANSWER    the caller asked something — answer first, then the goal
    WAIT      the caller is still doing it — say you will wait
    EXPLAIN   the caller did not follow — simpler words, a smaller piece
    CLARIFY   we did not get what we asked — say what we heard, ask the missing part
    CHECK_IN  silence or a long wait — are you there, how is it going

This module decides nothing about the call (no fact, no step, no ticket): it only reads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

RETURN, ANSWER, WAIT, EXPLAIN, CLARIFY, CHECK_IN, NONE = (
    "return",
    "answer",
    "wait",
    "explain",
    "clarify",
    "check_in",
    "none",
)
MOVES = (RETURN, ANSWER, WAIT, EXPLAIN, CLARIFY, CHECK_IN, NONE)

# The acknowledgement slot: a plain „Supratau…", or naming a reading we are not sure of so the
# caller can correct it.
ACK_PLAIN, ACK_CONFIRM, ACK_NONE = "plain", "confirm", "none"


@dataclass(frozen=True)
class DialogueMove:
    ack: str = ACK_NONE
    move: str = NONE
    why: str = ""  # the signal that chose it — the card's renderer and the trace key

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def choose(state: Any) -> DialogueMove:
    """This reply's acknowledgement and its ONE dialogue move."""
    if state.closing.case_closed:
        return DialogueMove()
    move, why = _move(state)
    return DialogueMove(ack=_ack(state, move), move=move, why=why)


def observe(state: Any, rt: Any) -> DialogueMove:
    """Choose and trace — the dashboard shows the move next to the plan."""
    chosen = choose(state)
    rt.tracer.emit("dialogue", **chosen.as_dict())
    return chosen


def _move(state: Any) -> tuple[str, str]:
    from .contract import limits
    from .perceive.detectors import INTENT_CONFUSED, INTENT_IN_PROGRESS, INTENT_QUESTION

    turn, dialog, case = state.turn, state.dialog, state.case
    rule = str((turn.plan or {}).get("rule") or "")
    waiting = bool(dialog.awaiting)
    understanding = turn.understanding or {}

    if turn.side_topic_active:
        return RETURN, "side_topic"
    if rule == "dialog.question_passthrough":
        return ANSWER, "question_mid_fix" if case.in_progress else "asked_how"
    if turn.also_asked:
        return ANSWER, "also_asked"
    if waiting and dialog.last_intent == INTENT_QUESTION:
        return ANSWER, "asked_while_waiting"
    if waiting and dialog.last_intent == INTENT_IN_PROGRESS:
        return WAIT, "in_progress"
    if understanding.get("type") == "confusion" and understanding.get("confusion"):
        return EXPLAIN, "caller_confused"
    if waiting and dialog.last_intent == INTENT_CONFUSED:
        return EXPLAIN, "did_not_follow"
    if case.unclear == case.step:
        return CLARIFY, "unclear_answer"
    if (turn.directives.recheck or {}).get("faktas"):
        return CLARIFY, "recheck"
    if dialog.stuck_count >= 2:
        return CLARIFY, "change_tactic"
    if dialog.stuck_count == 1 and dialog.last_heard:
        return CLARIFY, "not_understood"
    if case.in_progress and case.silence_asks:
        return CHECK_IN, "silence"
    if dialog.stuck_count == 1:
        return CHECK_IN, "quiet"
    if case.in_progress and case.waits >= limits.get("waits_before_help"):
        return EXPLAIN, "still_on_step"
    if waiting and dialog.awaiting_turns >= 3:
        return CHECK_IN, "long_wait"
    return NONE, ""


def _ack(state: Any, move: str) -> str:
    """Name what we understood — never over silence, never in a side-topic answer."""
    if move in (CHECK_IN, RETURN):
        return ACK_NONE
    if state.turn.confirm_reading:
        return ACK_CONFIRM
    understood = ((state.turn.understanding or {}).get("understood") or "").strip()
    return ACK_PLAIN if understood else ACK_NONE

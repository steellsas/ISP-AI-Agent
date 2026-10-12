"""STRUKTURA_V3 stage 5 — the dialogue layer: [acknowledgement] + ONE move + the phase goal.

Andrius (2026-10-08): the caller must feel heard, get an explanation when something is unclear,
be asked again when we did not get it, and be brought back when they drift. Before this stage
each of those signals wrote its own card section, and several landed in one reply.
"""

from pathlib import Path

import pytest
from agent import dialogue


class _Tracer:
    session_id = "5"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def fixing(make_state, make_runtime):
    """A dead-router fix under way, the caller identified, a question out."""
    tracer = _Tracer()
    state, rt = make_state("+37060012353"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST009"
    state.identity.caller_name = "Andrius"
    state.intake.problem_type = "internet_down"
    state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 1
    state.dialog.awaiting = "lights"
    state.dialog.last_heard = "Hmm"
    return state, rt, tracer


def _plan(state, rule):
    state.turn.plan = {"rule": rule, "owner": "diagnosis", "say": {"kind": "directive"}}


class TestTheMoveIsOne:
    @pytest.mark.parametrize(
        ("signals", "move", "why"),
        [
            ({}, dialogue.NONE, ""),
            ({"side_topic": True}, dialogue.RETURN, "side_topic"),
            ({"passthrough": True}, dialogue.ANSWER, "question_mid_fix"),
            ({"also_asked": True}, dialogue.ANSWER, "also_asked"),
            ({"intent": "question"}, dialogue.ANSWER, "asked_while_waiting"),
            ({"intent": "in_progress"}, dialogue.WAIT, "in_progress"),
            ({"confused": True}, dialogue.EXPLAIN, "caller_confused"),
            ({"intent": "confused"}, dialogue.EXPLAIN, "did_not_follow"),
            ({"unclear": True}, dialogue.CLARIFY, "unclear_answer"),
            ({"recheck": True}, dialogue.CLARIFY, "recheck"),
            ({"stuck": 1}, dialogue.CLARIFY, "not_understood"),
            ({"stuck": 2}, dialogue.CLARIFY, "change_tactic"),
            ({"silence": True}, dialogue.CHECK_IN, "silence"),
            ({"waits": 9}, dialogue.EXPLAIN, "still_on_step"),
            ({"long": True}, dialogue.CHECK_IN, "long_wait"),
            # several at once: the higher one wins, and only it
            ({"side_topic": True, "stuck": 2, "unclear": True}, dialogue.RETURN, "side_topic"),
            ({"also_asked": True, "unclear": True, "silence": True}, dialogue.ANSWER, "also_asked"),
            ({"confused": True, "unclear": True}, dialogue.EXPLAIN, "caller_confused"),
            ({"silence": True, "waits": 9, "long": True}, dialogue.CHECK_IN, "silence"),
        ],
    )
    def test_chosen_by_precedence(self, fixing, signals, move, why):
        from agent.perceive.detectors import INTENT_CONFUSED, INTENT_IN_PROGRESS, INTENT_QUESTION

        state, _, _ = fixing
        intents = {
            "question": INTENT_QUESTION,
            "in_progress": INTENT_IN_PROGRESS,
            "confused": INTENT_CONFUSED,
        }
        state.turn.side_topic_active = bool(signals.get("side_topic"))
        if signals.get("passthrough"):
            _plan(state, "dialog.question_passthrough")
        state.turn.also_asked = bool(signals.get("also_asked"))
        if "intent" in signals:
            state.dialog.last_intent = intents[signals["intent"]]
        if signals.get("confused"):
            state.turn.understanding = {"type": "confusion", "confusion": "kas yra WAN"}
        if signals.get("unclear"):
            state.case.unclear = state.case.step
        if signals.get("recheck"):
            state.turn.directives.recheck = {"faktas": "lemputės nedega"}
        state.dialog.stuck_count = signals.get("stuck", 0)
        state.case.silence_asks = 1 if signals.get("silence") else 0
        state.case.waits = signals.get("waits", 0)
        state.dialog.awaiting_turns = 5 if signals.get("long") else 0

        chosen = dialogue.choose(state)
        assert (chosen.move, chosen.why) == (move, why)

    def test_a_closed_call_has_no_move(self, fixing):
        from agent.closing import close_call

        state, rt, _ = fixing
        state.turn.also_asked = True
        close_call(state, rt, "resolved", complete=True)
        assert dialogue.choose(state).move == dialogue.NONE


class TestTheAcknowledgement:
    def test_plain_when_understood(self, fixing):
        state, _, _ = fixing
        state.turn.understanding = {"type": "answer", "understood": "lemputės nedega"}
        assert dialogue.choose(state).ack == dialogue.ACK_PLAIN

    def test_a_reading_we_are_not_sure_of_is_named_instead(self, fixing):
        from agent.speak.context_card import context_card

        state, rt, _ = fixing
        state.turn.understanding = {"type": "answer", "understood": "lemputės nedega"}
        state.turn.confirm_reading = "lemputės nedega"
        assert dialogue.choose(state).ack == dialogue.ACK_CONFIRM
        card = context_card(state, rt)
        assert "SAY WHAT YOU UNDERSTOOD FIRST" in card
        assert "ACKNOWLEDGE what you understood" not in card  # one acknowledgement, not two

    def test_none_over_silence(self, fixing):
        state, _, _ = fixing
        state.turn.understanding = {"type": "answer", "understood": "x"}
        state.case.silence_asks = 1
        assert dialogue.choose(state).ack == dialogue.ACK_NONE


class TestTheCardCarriesOneMove:
    def test_several_signals_one_section(self, fixing):
        from agent.speak.context_card import context_card

        state, rt, _ = fixing
        state.turn.also_asked = True
        state.case.unclear = state.case.step
        state.case.silence_asks = 1
        state.dialog.stuck_count = 1
        card = context_card(state, rt)

        assert card.count("THIS REPLY'S DIALOGUE MOVE") == 1
        assert "THE CALLER ALSO ASKED" in card
        assert "ANSWER WAS NOT CLEAR" not in card
        assert "SILENCE" not in card
        assert "DID NOT UNDERSTAND" not in card

    def test_no_move_no_frame(self, fixing):
        from agent.speak.context_card import context_card

        state, rt, _ = fixing
        assert "DIALOGUE MOVE" not in (context_card(state, rt) or "")

    def test_a_question_mid_fix_never_hears_we_cannot_advise(self, fixing, monkeypatch):
        """The contradiction stage 5 removes: with no written answer the old card said both
        „say honestly that you cannot advise" and „NEVER say you cannot advise"."""
        from agent.speak import context_card as card_module

        state, rt, _ = fixing
        _plan(state, "dialog.question_passthrough")
        monkeypatch.setattr(card_module, "_kb_answer", lambda state, rt: "")
        card = card_module.context_card(state, rt)

        assert "THEY ASKED SOMETHING WHILE THE FIX IS IN PROGRESS" in card
        assert "cannot advise on that" not in card


def test_the_move_is_traced(fixing):
    state, rt, tracer = fixing
    state.dialog.last_intent = "in_progress"
    from agent.perceive.detectors import INTENT_IN_PROGRESS

    state.dialog.last_intent = INTENT_IN_PROGRESS
    dialogue.observe(state, rt)
    assert {"type": "dialogue", "ack": "none", "move": "wait", "why": "in_progress"} in (
        tracer.events
    )


def test_every_why_has_its_words():
    from agent.speak.context_card import _MOVE_LABEL, _MOVE_WORDS

    source = (Path(dialogue.__file__)).read_text(encoding="utf-8")
    import re

    whys = set(re.findall(r'return [A-Z_]+, "([a-z_]+)"', source))
    whys |= {"question_mid_fix", "asked_how"}
    assert whys <= set(_MOVE_WORDS)
    assert set(_MOVE_LABEL) == set(dialogue.MOVES) - {dialogue.NONE}


def test_the_dashboard_shows_the_move():
    static = Path(__file__).resolve().parents[1] / "src" / "app" / "static" / "js" / "brain.js"
    js = static.read_text(encoding="utf-8")
    assert 'case "dialogue"' in js
    for move in set(dialogue.MOVES) - {dialogue.NONE}:
        assert f"{move}:" in js

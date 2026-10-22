"""The speaker (M5): the phrase path, the context card and the reply guards."""

from agent.call_record.finalizer import build_call_summary, finalize
from agent.contract import limits
from agent.decide.plan import Action, Say, TurnPlan
from agent.execute.say import speak
from agent.graph_v2.state import (
    ClosingState,
    DiagnosisState,
    DialogState,
    GraphState,
    IdentityState,
    IntakeState,
    ResolutionState,
    TicketContext,
    TicketState,
    TurnScratch,
)
from agent.speak.context_card import context_card
from agent.speak.postprocess import finish, track_stuck, trim_to_cap

from tests.diagnosis.test_facts import BASE
from tests.diagnosis.test_step_refusal import _hear, _Tracer, at_the_lights  # noqa: F401
from tests.engine_fakes import as_call

FUNCTION = "Kalbėtojas"


def _plan(**say):
    return TurnPlan(owner="diagnosis", rule="test.rule", action=Action(type="none"), say=Say(**say))


class TestPhrasePath:
    """A phrase is the locale's text, rendered by key — the LLM never sees it."""

    def test_phrase_key_renders_and_reaches_the_history(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        plan = _plan(kind="phrase", key="identification.ticket_phone", stage="ticket")

        reply = speak(state, rt, plan, None)

        assert reply and reply == state.messages[-1]["content"]
        assert "?" in reply  # the contact question, not an LLM paraphrase

    def test_phrase_vars_fill_the_template(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        plan = _plan(
            kind="phrase",
            key="identification.address_offer",
            vars={"address": "Tilžės g. 60"},
            stage="intake",
        )

        assert "Tilžės g. 60" in speak(state, rt, plan, None)

    def test_a_committed_phrase_is_only_streamed(self, make_state, make_runtime):
        """The solver already put its words on the history — speaking must not double them."""
        state, rt = make_state("+37060020112"), make_runtime()
        state.messages.append({"role": "assistant", "content": "Jau pasakyta."})
        plan = _plan(kind="phrase", text="Jau pasakyta.", committed=True, stage="diagnosis")

        assert speak(state, rt, plan, None) == "Jau pasakyta."
        assert len(state.messages) == 1


class TestReplyCap:
    """A phone caller cannot hold a paragraph, and a half-sentence is worse than a long one."""

    def test_a_long_reply_is_cut_at_the_last_full_sentence(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        cap = limits.get("reply_max_chars")
        text = ("Pirmas sakinys. " * 40) + "Paskutinis nebetelpa."

        trimmed = trim_to_cap(state, rt, text)

        assert len(trimmed) <= cap
        assert trimmed.endswith(".")
        assert text.startswith(trimmed)

    def test_one_long_sentence_goes_out_whole(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        text = "Labai ilgas sakinys be jokio taško viduryje " * 10

        assert trim_to_cap(state, rt, text) == text

    def test_a_short_reply_is_untouched(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()

        assert trim_to_cap(state, rt, "Trumpas atsakymas.") == "Trumpas atsakymas."


class TestFinish:
    def test_the_reply_lands_on_the_history_and_the_question_is_remembered(
        self, make_state, make_runtime
    ):
        state, rt = make_state("+37060020112"), make_runtime()

        reply, extra = finish(state, rt, "Koks jūsų adresas?")

        assert reply == "Koks jūsų adresas?" and extra == ""
        assert state.messages[-1] == {"role": "assistant", "content": reply}
        assert state.dialog.last_question == reply

    def test_a_repeated_question_raises_the_stuck_count(self, make_state, make_runtime):
        from agent.dialog_utils import progress_key

        state, rt = make_state("+37060020112"), make_runtime()
        state.turn.progress_key_at_start = progress_key(state)  # nothing moved this turn

        track_stuck(state, rt, "Kurioje gatvėje neveikia internetas?")
        assert state.dialog.stuck_count == 0  # the first ask is not a loop

        track_stuck(state, rt, "Kurioje gatvėje neveikia internetas?")
        assert state.dialog.stuck_count == 1 and state.dialog.last_reply_repeated is True


# --- from test_identify_first.py ---


def test_without_a_goal_the_open_question_is_the_engines(at_the_lights):
    from agent.speak.context_card import _next_step_words, _open_question

    state, _rt, _ = at_the_lights
    lines = _open_question(state, [])
    assert len(lines) == 1 and "OPEN QUESTION" in lines[0]
    assert _next_step_words(state) in lines[0]
    assert _open_question(state, ["PLAN GOAL — something"]) == []


# --- from test_fault_packs.py ---


class TestDirectiveTurnsAreSpeechOnly:
    """Live 2026-08-20: with tools exposed the model grabbed resolve_address on
    the anamnesis directive turn and skipped the ladder — directive turns get
    NO tools; the engine owns the mechanics."""

    def test_the_speaker_never_gets_tools(self, db_connection):
        """M5: the speaker has no tools at all — the engine ran every lookup and action."""
        from types import SimpleNamespace
        from unittest.mock import patch

        from agent.graph_v2.runtime import narrate

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.turn.directives.ident = {"kind": "anamnesis", "adresas": None, "fallback": "x"}
        captured = {}

        def _stream(**kwargs):
            captured.update(kwargs)
            yield "ok"
            return SimpleNamespace(content="ok", tool_calls=None)

        with (
            patch("agent.speak.node.stream_tool_completion", side_effect=_stream),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            narrate(agent.state, agent.runtime, "taip", "intake", "address_validation")
        assert captured["tools"] is None

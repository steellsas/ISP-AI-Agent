"""The speaker (M5): the phrase path, the context card and the reply guards."""

from agent.contract import limits
from agent.decide.plan import Action, Say, TurnPlan
from agent.execute.say import speak
from agent.speak.context_card import context_card
from agent.speak.postprocess import finish, track_stuck, trim_to_cap


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


class TestContextCard:
    """The card carries the engine's truth — and never a decision of its own."""

    def test_nothing_known_yet_gives_only_the_pre_problem_guard(self, make_state, make_runtime):
        card = context_card(make_state("unknown"), make_runtime())

        assert card and "THE PROBLEM IS NOT STATED YET" in card

    def test_identity_and_problem_land_on_the_card(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        state.identity.customer_id = "CUST009"
        state.identity.customer_name = "Jonas Jonaitis"
        state.intake.problem_type = "internet_down"

        card = context_card(state, rt)

        assert "Customer ID: CUST009" in card
        assert "Customer name: Jonas Jonaitis" in card
        assert "Problem type: internet_down" in card

    def test_the_plan_goal_is_the_one_instruction(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        state.turn.directives.ident = {
            "kind": "address_offer",
            "adresas": "Tilžės g. 60",
            "fallback": "Koks adresas?",
        }

        card = context_card(state, rt)

        assert "PLAN GOAL — IDENTIFICATION STEP" in card
        assert "Tilžės g. 60" in card

    def test_one_shot_lines_are_consumed(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        state.voice.undelivered_tail = "…patikrinkite lemputes."

        assert "NOT HEARD" in context_card(state, rt)
        assert state.voice.undelivered_tail is None
        assert "NOT HEARD" not in (context_card(state, rt) or "")

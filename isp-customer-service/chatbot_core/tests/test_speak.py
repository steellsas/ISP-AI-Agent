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


class TestHeardCheckBack:
    """F-11 (owner 2026-09-16): what the caller volunteered is checked back, not re-asked."""

    def _at_scope_step(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        state.identity.customer_id = "CUST112"
        state.resolution.procedure = {"verdict": "router_hung", "step": "rh_scope"}
        state.diagnosis.evidence["fail_scope"] = {
            "value": "all",
            "source": "client",
            "turn": 1,
            "seeded": True,
        }
        return state, rt

    def test_a_volunteered_fact_is_checked_back(self, make_state, make_runtime):
        from agent.decide.rules.evidence import seeded_step_confirm

        state, rt = self._at_scope_step(make_state, make_runtime)

        reply = seeded_step_confirm(state, rt, None)

        assert reply and "Supratau" in reply
        assert state.resolution.procedure["heard_confirm"]["key"] == "fail_scope"

    def test_a_yes_takes_the_step_branch(self, make_state, make_runtime):
        from agent.decide.rules.evidence import seeded_step_confirm

        state, rt = self._at_scope_step(make_state, make_runtime)
        seeded_step_confirm(state, rt, None)

        assert seeded_step_confirm(state, rt, "taip") is None
        assert state.resolution.procedure["step"] == "rh_ability"  # the 'all' branch
        assert "heard_confirm" not in state.resolution.procedure

    def test_a_no_drops_the_fact_so_the_question_is_asked(self, make_state, make_runtime):
        from agent.decide.rules.evidence import seeded_step_confirm

        state, rt = self._at_scope_step(make_state, make_runtime)
        seeded_step_confirm(state, rt, None)

        assert seeded_step_confirm(state, rt, "ne, tik telefone") is None
        assert "fail_scope" not in state.diagnosis.evidence
        assert state.resolution.procedure["step"] == "rh_scope"  # the step asks now

    def test_a_fact_the_step_itself_collected_is_not_checked_back(self, make_state, make_runtime):
        from agent.decide.rules.evidence import seeded_step_confirm

        state, rt = self._at_scope_step(make_state, make_runtime)
        state.diagnosis.evidence["fail_scope"].pop("seeded")

        assert seeded_step_confirm(state, rt, None) is None

    def test_the_card_hides_the_step_question_during_a_check_back(self, make_state, make_runtime):
        from agent.speak.context_card import context_card

        state, rt = self._at_scope_step(make_state, make_runtime)
        state.resolution.procedure["heard_confirm"] = {"key": "fail_scope", "value": "all"}

        card = context_card(state, rt) or ""

        assert "THIS STEP:" not in card and "STEP GOAL:" not in card

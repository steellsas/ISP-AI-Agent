"""The reply guard (review finding AB): the phone rules are kept WHILE the reply
streams — what is cut is never generated, spoken or recorded."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.speak.guard import ReplyGuard

FUNCTION = "Atsakymo sargai"

# (tokens as the LLM streams them, stop_chars, what goes out, why it stopped)
CASES = [
    # one question per reply — the reply ends with the first question
    (
        ["Supratau. ", "Ar dega ", "lemputė? ", "Ar mirksi?"],
        200,
        "Supratau. Ar dega lemputė?",
        "one_question",
    ),
    (["Ar dega? Jei", " taip — gerai."], 200, "Ar dega?", "one_question"),
    (["Ar dega?“ ", "Ir dar?"], 200, "Ar dega?“", "one_question"),
    # a reply without a question streams whole
    (["Gerai, ", "palauksiu."], 200, "Gerai, palauksiu.", None),
    # past the length cap the reply ends at the next sentence end
    (["Vienas. ", "Du. ", "Trys. ", "Keturi."], 10, "Vienas. Du.", "length"),
    # one long sentence goes out whole — never cut mid-sentence
    (
        ["Labai ilgas sakinys be jokio ", "taško iki pat galo."],
        10,
        "Labai ilgas sakinys be jokio taško iki pat galo.",
        "length",
    ),
    # decimals and in-word dots are not sentence ends
    (["Greitis 1.5 ", "Mbps. ", "Kitas."], 12, "Greitis 1.5 Mbps.", "length"),
]


@pytest.mark.parametrize("tokens, stop_chars, spoken, reason", CASES)
def test_the_guard_keeps_the_phone_rules(tokens, stop_chars, spoken, reason):
    guard = ReplyGuard(stop_chars=stop_chars)
    out = "".join(guard.feed(t) for t in tokens)

    assert out == spoken
    assert guard.stopped == reason


class TestStreamedReply:
    def test_the_generation_stops_after_the_first_question(self, make_state, make_runtime):
        """The LLM stream is closed at the cut: the caller hears, and the history keeps,
        exactly the guarded reply."""
        from agent.speak.node import stream_reply

        state, rt = make_state("+37060020112"), make_runtime()
        closed = {}

        def _stream(**kwargs):
            try:
                yield from ("Supratau. ", "Ar dega lemputė? ", "O ar ", "mirksi?")
            except GeneratorExit:
                closed["yes"] = True
                raise
            return SimpleNamespace(content="Supratau. Ar dega lemputė? O ar mirksi?")

        with (
            patch("agent.speak.node.stream_tool_completion", side_effect=_stream),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            spoken = "".join(stream_reply(state, rt, "diagnosis"))

        assert spoken == "Supratau. Ar dega lemputė?"
        assert state.messages[-1]["content"] == "Supratau. Ar dega lemputė?"
        assert closed.get("yes")

    def test_the_reply_generation_is_capped(self, make_state, make_runtime):
        from agent.contract import limits
        from agent.speak.node import stream_reply

        state, rt = make_state("+37060020112"), make_runtime()
        seen = {}

        def _stream(**kwargs):
            seen["max_tokens"] = kwargs["max_tokens"]
            yield "Gerai."
            return SimpleNamespace(content="Gerai.")

        with (
            patch("agent.speak.node.stream_tool_completion", side_effect=_stream),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            list(stream_reply(state, rt, "diagnosis"))

        assert seen["max_tokens"] == min(rt.config.max_tokens, limits.get("speak_max_tokens"))
        assert seen["max_tokens"] <= 150


class TestEveryScriptedQuestionSurvivesTheGuard:
    """Banga 7, gyvai 2026-10-01: tilto pasiūlymas buvo 233 simbolių, o sargas baigia atsakymą
    tuo sakiniu, kuris perlipa `reply_stop_chars` — nukrito paskutinis sakinys „Ar norite
    pabandyti?", klientas išgirdo pranešimą be klausimo ir atsakė „Neturiu." į nieką.

    Tad kiekviena kortelės klausimo frazė turi praeiti sargą su savo klaustuku.
    """

    def test_a_module_question_still_ends_in_a_question(self):
        from agent.contract import limits
        from agent.contract.locale import load_locale
        from agent.speak.guard import ReplyGuard

        locale = load_locale("lt")
        keys = [k for k in locale.phrases if k.startswith("modules.") and k.endswith(".question")]
        assert keys, "modules.*.question frazių turi būti"
        for key in keys:
            guard = ReplyGuard(stop_chars=limits.get("reply_stop_chars"))
            guard.feed(locale.template(key))
            assert guard.text.rstrip().endswith("?"), f"{key}: klausimas nukerpamas"


class _Tracer:
    session_id = "wave10"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def case_call(make_state, make_runtime):
    """A v2 Case call on a fault, the caller identified."""
    state, rt = make_state("+37060012353"), make_runtime(tracer=_Tracer())
    state.identity.customer_id = "CUST009"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    state.case.fault, state.case.solution = "no_mac_observed", 0
    return state, rt


# --- from test_wave10_quick.py ---


class TestAPromiseNothingBacksIsNotSpoken:
    """A: „užregistruosiu" the ENGINE has not decided is withheld before TTS (eval K1). Since
    2026-10-13 a fault being worked on or debt news told is not a decision — only a running or
    done registration, or the Case having summed up for a technician, is (Andrius: the engine
    decides, the model only says it)."""

    PROMISE = "Šiuo klausimu geriausiai atsakys atsakingas žmogus — užregistruosiu jūsų klausimą."

    def test_no_reason_no_promise(self, case_call):
        from agent.execute.ticket import unbacked_promise

        state, _ = case_call
        state.case.fault, state.case.solution = None, None  # still identifying the fault
        assert unbacked_promise(state, self.PROMISE)

    @pytest.mark.parametrize("backing", ["fault_in_progress", "debt_told"])
    def test_a_promise_the_engine_has_not_decided_is_withheld(self, case_call, backing):
        from agent.execute.ticket import unbacked_promise

        state, _ = case_call
        if backing == "debt_told":
            state.case.fault = None
            state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
            state.diagnosis.news_delivered = True
        assert unbacked_promise(state, self.PROMISE)

    @pytest.mark.parametrize("decided", ["summed_up", "ticket_running"])
    def test_a_decided_registration_may_be_said(self, case_call, decided):
        from agent.execute.ticket import unbacked_promise

        state, _ = case_call
        if decided == "summed_up":
            state.case.summarised = True
        else:
            state.ticket.stage = "phone"
        assert not unbacked_promise(state, self.PROMISE)

    def test_a_misformed_past_promise_after_the_debt_offer_is_withheld(self, case_call):
        """Live 2026-10-19 (G17): Gemma's „užregistruojau jūsų kreipimąsi" with no ticket."""
        from agent.execute.ticket import unbacked_promise

        state, _ = case_call
        state.case.fault = None
        state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
        state.diagnosis.news_delivered = True
        assert unbacked_promise(state, "Gerai, Tomas, užregistruojau jūsų kreipimąsi.")

    def test_other_sentences_pass(self, case_call):
        from agent.execute.ticket import unbacked_promise

        state, _ = case_call
        state.case.fault = None
        assert not unbacked_promise(state, "Naršyklėje įveskite 192.168.0.1.")

    def test_the_streamed_reply_and_history_lose_the_promise(self, case_call):
        from types import SimpleNamespace
        from unittest.mock import patch

        from agent.speak.node import stream_reply

        state, rt = case_call
        state.case.fault, state.case.solution = None, None

        def _stream(**kwargs):
            yield "Naršyklėje įveskite 192.168.0.1. "
            yield self.PROMISE
            return SimpleNamespace(content="…")

        with (
            patch("agent.speak.node.stream_tool_completion", side_effect=_stream),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            spoken = "".join(stream_reply(state, rt, "diagnosis"))

        assert spoken.strip() == "Naršyklėje įveskite 192.168.0.1."
        assert state.messages[-1]["content"] == "Naršyklėje įveskite 192.168.0.1."
        assert any(e.get("reason") == "unbacked_promise" for e in rt.tracer.events)

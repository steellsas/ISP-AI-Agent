"""The reply guard (review finding AB): the phone rules are kept WHILE the reply
streams — what is cut is never generated, spoken or recorded."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.speak.guard import ReplyGuard

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

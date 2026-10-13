"""v3 6d — the model's language mistakes live in ONE file (`locales/lt/kalba.yaml`)."""

import pytest


@pytest.mark.parametrize(
    ("said", "spoken"),
    [
        ("Džiaugiuosi, kad viskas sutvarkėsi.", "Džiaugiuosi, kad viskas susitvarkė."),
        ("Pasižiūrėjome lemputžių.", "Pasižiūrėjome lemputes."),
        ("Sutvarkėsi!", "Susitvarkė!"),  # the capital stays
        ("bet 39 numerio nerodu.", "bet 39 numerio nerandu."),
        ("nerodus", "nerodus"),  # whole words only
    ],
)
def test_a_known_mistake_is_corrected(said, spoken):
    from agent.contract.language import fix_words

    assert fix_words(said)[0] == spoken


def test_the_prompt_carries_only_the_chosen_few():
    from agent.contract.language import fixes, prompt_lines

    lines = prompt_lines()
    assert "sutvarkėsi" in lines and "susitvarkė" in lines
    assert "tiešiai" in fixes() and "tiešiai" not in lines  # fixed, but not in the prompt


def test_the_speaking_prompt_has_the_line():
    from agent.speak.node import speak_prompt

    assert "never the left one: „sutvarkėsi“ → „susitvarkė“" in speak_prompt(
        "ask_fact", "+370", "lt", "investigate"
    )


def test_a_correction_is_traced(make_state, make_runtime):
    """The caller hears it right, and measuring still counts the model's mistake."""

    class _Tracer:
        session_id = "6d"

        def __init__(self):
            self.events = []

        def emit(self, event_type, **fields):
            self.events.append({"type": event_type, **fields})

    from agent.speak import node

    tracer = _Tracer()
    state, rt = make_state("+37060020112"), make_runtime(tracer=tracer)

    def fake_stream(**_):
        yield "Džiaugiuosi, kad viskas sutvarkėsi. "

    import agent.speak.node as module

    original = module.stream_tool_completion
    module.stream_tool_completion = fake_stream
    try:
        gen = node._stream_tokens(state, rt, [])
        out = "".join(list(gen))
    finally:
        module.stream_tool_completion = original
    assert "susitvarkė" in out and "sutvarkėsi" not in out
    assert {"type": "language_fix", "wrong": "sutvarkėsi", "right": "susitvarkė"} in tracer.events

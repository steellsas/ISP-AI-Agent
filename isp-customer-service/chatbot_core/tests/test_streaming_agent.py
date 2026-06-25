"""
Tests for the streaming LLM completion (Pillar C3, services/llm/client.py).

stream_tool_completion is a generator that yields content tokens and returns the
final assistant message (with .content / .tool_calls) — litellm is mocked so no
network/key is needed.

Run: pytest tests/test_streaming_agent.py -v
"""

from types import SimpleNamespace
from unittest.mock import patch


def _content_chunk(text):
    delta = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


def _tool_chunk(index, id=None, name=None, args=None):
    fn = SimpleNamespace(name=name, arguments=args)
    tc = SimpleNamespace(index=index, id=id, function=fn)
    delta = SimpleNamespace(content=None, tool_calls=[tc])
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


def _usage_chunk(prompt, completion):
    return SimpleNamespace(
        choices=[], usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    )


def _drain(gen):
    """Run a generator to exhaustion -> (yielded_items, return_value)."""
    out = []
    while True:
        try:
            out.append(next(gen))
        except StopIteration as e:
            return out, e.value


class TestStreamToolCompletion:
    def _run(self, chunks):
        from services.llm import client

        with (
            patch.object(client, "_configure_provider", return_value="openai"),
            patch.object(client.litellm, "completion", return_value=iter(chunks)),
        ):
            return _drain(client.stream_tool_completion(messages=[], tools=[], model="gpt-4o-mini"))

    def test_streams_content_tokens_and_returns_message(self):
        tokens, message = self._run(
            [_content_chunk("Lab"), _content_chunk("as."), _usage_chunk(10, 2)]
        )
        assert tokens == ["Lab", "as."]
        assert message.content == "Labas."
        assert message.tool_calls is None

    def test_accumulates_tool_call_across_deltas(self):
        tokens, message = self._run(
            [
                _tool_chunk(0, id="call_1", name="resolve_address", args='{"str'),
                _tool_chunk(0, args='eet": "Tilžės"}'),
                _usage_chunk(5, 3),
            ]
        )
        assert tokens == []  # a tool round produces no speech
        assert message.content is None
        assert len(message.tool_calls) == 1
        tc = message.tool_calls[0]
        assert tc.id == "call_1"
        assert tc.function.name == "resolve_address"
        assert tc.function.arguments == '{"street": "Tilžės"}'

    def test_updates_last_call_stats(self):
        from services.llm import client

        self._run([_content_chunk("ok"), _usage_chunk(7, 1)])
        s = client.get_last_call_stats()
        assert s["input_tokens"] == 7
        assert s["output_tokens"] == 1
        assert s["model"] == "gpt-4o-mini"

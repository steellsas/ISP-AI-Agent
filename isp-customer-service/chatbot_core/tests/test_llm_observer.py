"""Every LLM call of a conversation is visible (review finding B): the client reports
each completed call to the conversation's observer, with the call's role."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def provider_key(monkeypatch):
    """The client exports the provider's key before every call; CI has none (locally it
    comes from .env), and these tests patch the transport, not the credentials."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def _fake_response(text="{}", prompt_tokens=120, completion_tokens=8):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


class _Recorder:
    def __init__(self):
        self.events = []

    def emit(self, event, **fields):
        self.events.append((event, fields))

    def of(self, event):
        return [f for e, f in self.events if e == event]


class TestClientObserver:
    def test_a_completed_call_is_reported_with_its_role(self):
        from src.services.llm.client import llm_completion, observe_llm_calls

        seen = []
        with (
            patch("litellm.completion", return_value=_fake_response()),
            observe_llm_calls(lambda role, stats: seen.append((role, stats))),
        ):
            llm_completion([{"role": "user", "content": "x"}], model="gpt-4o-mini", role="solver")

        assert [role for role, _ in seen] == ["solver"]
        assert seen[0][1]["input_tokens"] == 120
        assert seen[0][1]["success"] is True

    def test_a_failed_call_is_reported_too(self, monkeypatch):
        from src.services.llm import client

        monkeypatch.setattr(
            client,
            "get_settings",
            lambda: SimpleNamespace(
                max_retries=1,
                retry_delay=0,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=100,
                top_p=1.0,
            ),
        )
        seen = []
        with (
            patch("litellm.completion", side_effect=RuntimeError("down")),
            client.observe_llm_calls(lambda role, stats: seen.append((role, stats))),
            pytest.raises(Exception),
        ):
            client.llm_completion([{"role": "user", "content": "x"}], role="analyst")

        assert [role for role, _ in seen] == ["analyst"]
        assert seen[0][1]["success"] is False

    def test_no_observer_no_report(self):
        from src.services.llm.client import llm_completion

        with patch("litellm.completion", return_value=_fake_response()):
            assert llm_completion([{"role": "user", "content": "x"}], model="gpt-4o-mini") == "{}"


class TestSessionSeesSensorCalls:
    def test_a_sensor_call_inside_the_graph_reaches_the_trace_and_totals(
        self, db_connection, monkeypatch
    ):
        """The observer set by the session must reach the graph's nodes (a perception
        call inside perceive) — the trace gets an `llm` event with the role and the
        call counts toward the call's totals."""
        from agent.session import AgentSession
        from src.services.llm.client import llm_completion

        def perceive_with_llm(state, rt, user_input):
            if user_input:
                llm_completion(
                    [{"role": "user", "content": user_input}],
                    model="gpt-4o-mini",
                    role="perception",
                )

        monkeypatch.setattr("agent.perceive.node.perceive", perceive_with_llm)
        tracer = _Recorder()
        session = AgentSession(caller_phone="+37060000000", tracer=tracer)
        session.greeting()
        with (
            patch("litellm.completion", return_value=_fake_response()),
            patch("agent.speak.node.stream_tool_completion", side_effect=_no_speak),
        ):
            session.handle_turn("neveikia internetas")
            list(session.handle_turn_stream("vis dar neveikia"))  # the voice path

        sensor = [f for f in tracer.of("llm") if f.get("role") == "perception"]
        assert len(sensor) == 2
        assert sensor[0]["input_tokens"] == 120
        assert session.stats["total_calls"] >= 1


def _no_speak(**kwargs):
    yield "Gerai."
    return SimpleNamespace(content="Gerai.", tool_calls=None)


class _ProviderStream:
    """What litellm returns for stream=True: iterable chunks over a closable provider
    stream (the openai Stream holding the HTTP response)."""

    def __init__(self, texts):
        self.completion_stream = SimpleNamespace(closed=False)
        self.completion_stream.close = lambda: setattr(self.completion_stream, "closed", True)
        self._chunks = [
            SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(delta=SimpleNamespace(content=t, tool_calls=None))],
            )
            for t in texts
        ]

    def __iter__(self):
        return iter(self._chunks)


class TestStreamLifetime:
    """Wave-0 eval hang (2026-09-18): a stream the reply guard stopped reading was left
    to the garbage collector, which finalized it inside the next request while httpx
    held its pool lock — a deadlock. The stream must close the moment reading stops."""

    def test_a_stream_stopped_early_is_closed_at_once(self):
        from src.services.llm.client import stream_tool_completion

        provider = _ProviderStream(["Ar dega? ", "O ar ", "mirksi?"])
        with patch("litellm.completion", return_value=provider):
            gen = stream_tool_completion(
                [{"role": "user", "content": "x"}], tools=None, model="gpt-4o-mini"
            )
            assert next(gen) == "Ar dega? "
            gen.close()  # the reply guard / a barge-in stops reading here

        assert provider.completion_stream.closed is True

    def test_a_fully_read_stream_is_closed_too(self):
        from src.services.llm.client import stream_tool_completion

        provider = _ProviderStream(["Gerai."])
        with patch("litellm.completion", return_value=provider):
            assert list(
                stream_tool_completion(
                    [{"role": "user", "content": "x"}], tools=None, model="gpt-4o-mini"
                )
            ) == ["Gerai."]

        assert provider.completion_stream.closed is True

    def test_every_request_carries_a_timeout(self, monkeypatch):
        from src.services.llm.client import llm_completion, stream_tool_completion

        monkeypatch.setenv("LLM_TIMEOUT_S", "12")
        seen = []

        def _completion(**kwargs):
            seen.append(kwargs.get("timeout"))
            return _ProviderStream(["x"]) if kwargs.get("stream") else _fake_response()

        with patch("litellm.completion", side_effect=_completion):
            llm_completion([{"role": "user", "content": "x"}], model="gpt-4o-mini")
            list(
                stream_tool_completion(
                    [{"role": "user", "content": "x"}], tools=None, model="gpt-4o-mini"
                )
            )

        assert seen == [12.0, 12.0]

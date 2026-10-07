"""Open-model routing and the fallback model (2026-10-07: Gemma 4 on Scaleway as the
main model, gpt-4o-mini taking over when it fails). Transport is patched — no network."""

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

GEMMA = "scaleway/gemma-4-26b-a4b-it"


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("SCW_SECRET_KEY", "test-scw")
    monkeypatch.delenv("SCW_API_BASE", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "gpt-4o-mini")
    from src.services.llm import client

    monkeypatch.setattr(
        client,
        "get_settings",
        lambda: SimpleNamespace(
            max_retries=3,
            retry_delay=0,
            model=GEMMA,
            temperature=0.3,
            max_tokens=100,
            top_p=1.0,
            request_timeout=30.0,
        ),
    )


def _response(text="Gerai."):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2),
    )


class _Stream:
    def __init__(self, texts, fail_after=None):
        self.texts, self.fail_after = texts, fail_after
        self.completion_stream = SimpleNamespace(close=lambda: None)

    def __iter__(self):
        for i, t in enumerate(self.texts):
            if self.fail_after is not None and i == self.fail_after:
                raise RuntimeError("provider broke")
            yield SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(delta=SimpleNamespace(content=t, tool_calls=None))],
            )


def _routed_to(kwargs):
    return "scaleway" if kwargs.get("api_base") else kwargs["model"]


class TestEndpoints:
    def test_scaleway_name_becomes_an_openai_compatible_call(self):
        from src.services.llm.endpoints import litellm_kwargs

        kw = litellm_kwargs(GEMMA)
        assert kw["model"] == "openai/gemma-4-26b-a4b-it"
        assert kw["api_base"] == "https://api.scaleway.ai/v1"
        assert kw["api_key"] == "test-scw"
        # an open model must not "think" on a phone call
        assert kw["extra_body"] == {"reasoning_effort": "none"}

    def test_local_server_is_the_same_call_with_another_address(self, monkeypatch):
        from src.services.llm.endpoints import litellm_kwargs

        monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://gpu-box:8000/v1")
        kw = litellm_kwargs("local/gemma4:26b")
        assert kw["model"] == "openai/gemma4:26b"
        assert kw["api_base"] == "http://gpu-box:8000/v1"

    def test_reasoning_effort_can_be_switched_off(self, monkeypatch):
        from src.services.llm.endpoints import litellm_kwargs

        monkeypatch.setenv("LLM_REASONING_EFFORT", "")
        assert "extra_body" not in litellm_kwargs(GEMMA)

    def test_other_models_are_left_to_litellm(self):
        from src.services.llm.endpoints import litellm_kwargs

        assert litellm_kwargs("gpt-4o-mini") == {}
        assert litellm_kwargs("groq/openai/gpt-oss-20b") == {}

    def test_open_models_get_json_mode_and_local_costs_nothing(self):
        from src.services.llm.client import get_model_info
        from src.services.llm.models import calculate_cost

        assert get_model_info(GEMMA)["supports_json_mode"] is True
        assert calculate_cost("local/gemma4:26b", 1000, 1000) == 0.0
        assert calculate_cost(GEMMA, 1_000_000, 0) == pytest.approx(0.25)


class TestCompletionFallback:
    def test_main_model_answers(self):
        from src.services.llm.client import llm_completion

        seen = []
        with patch("litellm.completion", side_effect=lambda **kw: seen.append(kw) or _response()):
            assert llm_completion([{"role": "user", "content": "x"}]) == "Gerai."
        assert [_routed_to(k) for k in seen] == ["scaleway"]

    def test_a_failed_main_model_hands_over_once_and_says_so(self, caplog):
        from src.services.llm.client import llm_completion

        seen = []

        def _completion(**kw):
            seen.append(kw)
            if kw.get("api_base"):
                raise RuntimeError("503 Service Unavailable")
            return _response("Atsarginis.")

        with (
            caplog.at_level(logging.INFO, logger="ops"),
            patch("litellm.completion", side_effect=_completion),
        ):
            assert (
                llm_completion([{"role": "user", "content": "x"}], role="perception")
                == "Atsarginis."
            )

        # ONE try on the main model (no retries before the hand-over), then the fallback
        assert [_routed_to(k) for k in seen] == ["scaleway", "gpt-4o-mini"]
        ops = [r.getMessage() for r in caplog.records if r.name == "ops"]
        assert any("[llm] fallback" in m and GEMMA in m and "503" in m for m in ops)

    def test_main_model_has_the_short_timeout(self, monkeypatch):
        from src.services.llm.client import llm_completion

        monkeypatch.setenv("LLM_PRIMARY_TIMEOUT_S", "5")
        seen = []
        with patch("litellm.completion", side_effect=lambda **kw: seen.append(kw) or _response()):
            llm_completion([{"role": "user", "content": "x"}])
        assert seen[0]["timeout"] == 5.0

    def test_without_a_fallback_the_error_surfaces(self, monkeypatch, caplog):
        from src.services.llm.client import llm_completion

        monkeypatch.setenv("LLM_FALLBACK_MODEL", "")
        with (
            caplog.at_level(logging.INFO, logger="ops"),
            patch("litellm.completion", side_effect=RuntimeError("down")),
            pytest.raises(Exception),
        ):
            llm_completion([{"role": "user", "content": "x"}])
        assert any("[llm] call failed" in r.getMessage() for r in caplog.records if r.name == "ops")

    def test_our_own_rate_limit_is_not_a_reason_to_fall_back(self):
        from src.services.llm import client
        from src.services.llm.rate_limiter import RateLimitError

        limiter = SimpleNamespace(
            check_or_raise=lambda: (_ for _ in ()).throw(RateLimitError("loop"))
        )
        with (
            patch.object(client, "get_rate_limiter", return_value=limiter),
            patch("litellm.completion") as transport,
            pytest.raises(RateLimitError),
        ):
            client.llm_completion([{"role": "user", "content": "x"}])
        transport.assert_not_called()

    def test_missing_scaleway_key_falls_back(self, monkeypatch):
        from src.services.llm.client import llm_completion

        monkeypatch.delenv("SCW_SECRET_KEY")
        with patch("litellm.completion", return_value=_response("Atsarginis.")) as transport:
            assert llm_completion([{"role": "user", "content": "x"}]) == "Atsarginis."
        assert transport.call_args.kwargs["model"] == "gpt-4o-mini"


class TestJsonFallback:
    def test_a_model_that_cannot_keep_json_hands_over(self):
        from src.services.llm.client import llm_json_completion

        def _completion(**kw):
            return _response("ne json" if kw.get("api_base") else '{"lights": "on"}')

        with patch("litellm.completion", side_effect=_completion) as transport:
            assert llm_json_completion([{"role": "user", "content": "x"}]) == {"lights": "on"}
        # the main model's own retry first (2 calls), then the fallback
        assert [_routed_to(c.kwargs) for c in transport.call_args_list] == [
            "scaleway",
            "scaleway",
            "gpt-4o-mini",
        ]


class TestStreamFallback:
    def _drain(self, gen):
        out = []
        while True:
            try:
                out.append(next(gen))
            except StopIteration as stop:
                return out, stop.value

    def test_a_stream_that_never_starts_is_answered_by_the_fallback(self):
        from src.services.llm.client import get_last_call_stats, stream_tool_completion

        def _completion(**kw):
            if kw.get("api_base"):
                raise RuntimeError("connect timeout")
            return _Stream(["Laba ", "diena."])

        with patch("litellm.completion", side_effect=_completion):
            tokens, message = self._drain(
                stream_tool_completion([{"role": "user", "content": "x"}], tools=None)
            )
        assert "".join(tokens) == "Laba diena."
        assert message.content == "Laba diena."
        assert get_last_call_stats()["model"] == "gpt-4o-mini"  # cost follows who answered

    def test_a_stream_failing_before_its_first_token_still_falls_back(self):
        from src.services.llm.client import stream_tool_completion

        def _completion(**kw):
            return _Stream(["x"], fail_after=0) if kw.get("api_base") else _Stream(["Gerai."])

        with patch("litellm.completion", side_effect=_completion):
            tokens, _ = self._drain(
                stream_tool_completion([{"role": "user", "content": "x"}], tools=None)
            )
        assert tokens == ["Gerai."]

    def test_a_reply_cut_by_the_guard_books_its_own_stats(self):
        """Live 2026-10-07: the reply guard closed the stream before the usage chunk, and
        the speak call was booked with the PREVIOUS (perception) call's numbers."""
        from src.services.llm import client

        client._last_call_stats = {"model": "x", "input_tokens": 2305, "output_tokens": 64}
        with patch("litellm.completion", return_value=_Stream(["Ar dega? ", "O ar mirksi?"])):
            gen = client.stream_tool_completion(
                [{"role": "user", "content": "Laba diena, neveikia internetas"}], tools=None
            )
            assert next(gen) == "Ar dega? "
            gen.close()  # the reply guard stops reading here

        stats = client.get_last_call_stats()
        assert stats["model"] == GEMMA
        assert stats["estimated"] is True and stats["complete"] is False
        assert 0 < stats["input_tokens"] < 100  # counted for THIS prompt, not 2305
        assert stats["output_tokens"] > 0

    def test_warm_up_reports_a_dead_provider_at_startup(self, caplog):
        from src.services.llm.client import warm_up

        with (
            caplog.at_level(logging.INFO, logger="ops"),
            patch("litellm.completion", side_effect=RuntimeError("403 FORBIDDEN")),
        ):
            assert warm_up(GEMMA) is None
        assert any("warm-up failed" in r.getMessage() for r in caplog.records if r.name == "ops")

        with patch("litellm.completion", return_value=_response()) as transport:
            assert warm_up(GEMMA) is not None
        assert transport.call_args.kwargs["max_tokens"] == 1

    def test_once_words_are_out_a_broken_stream_is_not_replayed(self):
        from src.services.llm.client import stream_tool_completion

        calls = []

        def _completion(**kw):
            calls.append(kw)
            return _Stream(["Laba ", "diena."], fail_after=1)

        gen = stream_tool_completion([{"role": "user", "content": "x"}], tools=None)
        with patch("litellm.completion", side_effect=_completion), pytest.raises(RuntimeError):
            self._drain(gen)
        assert len(calls) == 1  # the caller already heard "Laba" — no second voice

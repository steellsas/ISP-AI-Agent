"""The turn "why" view's trace (ROADMAP 3.1): every call says what it ran on, every decide
pass says which rule families it asked, and in development every LLM call keeps what the
model saw and answered."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest


class _CaptureTracer:
    session_id = "why-view-test"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})

    def of(self, event_type):
        return [e for e in self.events if e["type"] == event_type]


def _fake_response(text='{"facts": {}}'):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2),
    )


class TestVersions:
    def test_a_call_starts_with_what_it_runs_on(self, db_connection):
        from agent.session import AgentSession

        tracer = _CaptureTracer()
        session = AgentSession(caller_phone="+37060020112", tracer=tracer)
        (start,) = tracer.of("session_start")
        v = start["versions"]
        assert {"code", "knowledge", "locale", "prompts", "documents", "models"} <= set(v)
        assert v["models"]["speak"] == session.config.model
        assert session.versions == v

    def test_an_edited_knowledge_file_changes_the_tag(self, tmp_path, monkeypatch):
        from agent import versions

        (tmp_path / "card.yaml").write_text("a: 1", encoding="utf-8")
        monkeypatch.setitem(versions.CONTENT, "knowledge", [tmp_path])
        before = versions.content_hashes()["knowledge"]
        (tmp_path / "card.yaml").write_text("a: 2 # edited", encoding="utf-8")
        assert versions.content_hashes()["knowledge"] != before

    def test_hashes_survive_the_phone_scrubber(self, tmp_path):
        from adapters.tracing.jsonl_tracer import JsonlFileTracer

        tracer = JsonlFileTracer("scrub-test", trace_dir=tmp_path, redact=True)
        tracer.emit("note", text="skambino +37061234567")
        tracer.emit("session_start", versions={"knowledge": "6123456789"})
        written = (tmp_path / "scrub-test.jsonl").read_text("utf-8")
        assert "37061234567" not in written  # the scrubber is on
        assert '"knowledge": "6123456789"' in written


class TestPolicyChain:
    def test_every_decide_pass_names_the_families_it_asked(self, db_connection):
        from agent.session import AgentSession

        tracer = _CaptureTracer()
        session = AgentSession(caller_phone="+37060020112", tracer=tracer)
        session.greeting()
        session.handle_turn("Neveikia internetas")

        passes = tracer.of("policy")
        assert passes, "no decide pass traced"
        first = passes[0]
        assert first["family"] == "dialog.greeting" and first["declined"] == []
        later = passes[-1]
        assert "dialog.greeting" in later["declined"]
        assert later["family"] is None or later["rule"]


class TestLLMCapture:
    @pytest.fixture(autouse=True)
    def provider_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _call(self):
        from src.services.llm.client import llm_completion, observe_llm_calls

        seen = []
        with (
            patch("litellm.completion", return_value=_fake_response()),
            observe_llm_calls(lambda role, stats: seen.append(stats)),
        ):
            llm_completion(
                [{"role": "user", "content": "Labas"}], model="gpt-4o-mini", role="perception"
            )
        return seen[0]

    def test_development_keeps_what_the_model_saw_and_answered(self, monkeypatch):
        monkeypatch.delenv("DEBUG_LLM", raising=False)  # the default is full
        stats = self._call()
        assert stats["messages"] == [{"role": "user", "content": "Labas"}]
        assert stats["output"] == '{"facts": {}}'

    @pytest.mark.parametrize("level", ["off", "card", "0", "1"])
    def test_lower_levels_keep_numbers_only(self, monkeypatch, level):
        monkeypatch.setenv("DEBUG_LLM", level)
        stats = self._call()
        assert "messages" not in stats and "output" not in stats
        assert stats["input_tokens"] == 10

    def test_the_session_writes_it_into_the_llm_event(self, db_connection):
        from agent.session import AgentSession

        tracer = _CaptureTracer()
        session = AgentSession(caller_phone="+37060020112", tracer=tracer)
        session._observe_llm(
            "perception",
            {"model": "m", "messages": [{"role": "user", "content": "x"}], "output": "{}"},
        )
        (e,) = tracer.of("llm")
        assert e["messages"] == [{"role": "user", "content": "x"}] and e["output"] == "{}"

    def test_the_switch_is_on_the_config_page(self):
        from app import runtime_config

        item = next(i for i in runtime_config.current() if i["key"] == "DEBUG_LLM")
        assert item["options"][0] == "full"


def test_the_dashboard_loads_the_why_view():
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "src" / "app" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    assert html.index("js/why.js") < html.index("js/brain.js")
    assert html.count('class="b-why"') == 2  # the live call and the archive
    assert "WhyView.render" in (static / "js" / "brain.js").read_text(encoding="utf-8")

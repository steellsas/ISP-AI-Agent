"""
Tests for the conversation trace (observability).

Covers the JSONL sink contract from stebejimo_dizainas.md: per-session file,
one event per line, every event stamped with v/ts/session_id/type, verdict as
its own event type, PII redaction, and the NullTracer / factory behaviour.

The end-to-end "the agent actually emits" path is validated by the manual CLI
run (it needs live LLM calls); here we test the sink + factory directly and the
ReactAgent helper that turns observations into events.

Run: pytest tests/test_tracing.py -v
"""

import json

import pytest


def _read_events(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestJsonlFileTracer:
    def test_writes_one_line_per_event_with_stamps(self, tmp_path):
        from adapters.tracing import JsonlFileTracer

        tracer = JsonlFileTracer("sess-1", trace_dir=tmp_path, redact=False)
        tracer.emit("session_start", caller_phone="+37060020105", model="gpt-4o-mini")
        tracer.emit("user_turn", text="neveikia internetas")
        tracer.emit("agent_reply", text="Pasakykite adresą...")

        events = _read_events(tracer.path)
        assert len(events) == 3
        for e in events:
            assert e["v"] == 1
            assert e["session_id"] == "sess-1"
            assert "ts" in e
            assert "type" in e
        assert [e["type"] for e in events] == ["session_start", "user_turn", "agent_reply"]

    def test_file_named_by_session_id(self, tmp_path):
        from adapters.tracing import JsonlFileTracer

        tracer = JsonlFileTracer("abc-123", trace_dir=tmp_path)
        assert tracer.path.name == "abc-123.jsonl"

    def test_redacts_phone_numbers(self, tmp_path):
        from adapters.tracing import JsonlFileTracer

        tracer = JsonlFileTracer("sess-2", trace_dir=tmp_path, redact=True)
        tracer.emit("session_start", caller_phone="+37060020105")
        tracer.emit("tool_call", name="find_customer", args={"phone": "+37060020105"})

        raw = tracer.path.read_text(encoding="utf-8")
        assert "+37060020105" not in raw  # masked everywhere, incl. nested args
        assert "***0105" in raw

    def test_session_id_not_corrupted_by_redaction(self, tmp_path):
        # A numeric session id can coincidentally match the phone regex; it must
        # survive redaction intact (structural field), unlike text/args values.
        from adapters.tracing import JsonlFileTracer

        sid = "20260617-135857-245253-0001"
        tracer = JsonlFileTracer(sid, trace_dir=tmp_path, redact=True)
        tracer.emit("user_turn", text="+37060020105")

        events = _read_events(tracer.path)
        assert events[0]["session_id"] == sid  # untouched
        assert events[0]["text"] == "***0105"  # value still redacted

    def test_redact_off_keeps_full_number(self, tmp_path):
        from adapters.tracing import JsonlFileTracer

        tracer = JsonlFileTracer("sess-3", trace_dir=tmp_path, redact=False)
        tracer.emit("session_start", caller_phone="+37060020105")
        assert "+37060020105" in tracer.path.read_text(encoding="utf-8")

    def test_export_txt_writes_readable_transcript(self, tmp_path):
        from adapters.tracing import JsonlFileTracer

        tracer = JsonlFileTracer("sess-txt", trace_dir=tmp_path, redact=False)
        tracer.emit("session_start", caller_phone="+37060020105", model="gpt-4o-mini")
        tracer.emit("user_turn", text="neveikia internetas")
        tracer.emit("tool_call", name="resolve_address", args={"city": "Šiauliai"})
        tracer.emit(
            "tool_result",
            name="resolve_address",
            ok=True,
            ms=12,
            summary={"customer_id": "CUST105"},
        )
        tracer.emit("verdict", side="customer", group="B6", action="instruct", reason="foreign_mac")
        tracer.emit("agent_reply", text="Ar pakeitėte routerį?")
        tracer.emit("session_end", outcome="done", customer_id="CUST105", ticket_id=None)

        txt = tracer.export_txt()
        assert txt is not None and txt.exists()
        content = txt.read_text(encoding="utf-8")
        assert "USER : neveikia internetas" in content
        assert "AGENT: Ar pakeitėte routerį?" in content
        assert "VERDICT B6 instruct foreign_mac" in content
        assert "12ms" in content

    def test_emit_never_raises_on_bad_dir(self, tmp_path):
        from adapters.tracing import JsonlFileTracer

        # Point at a path that cannot be a directory (a file) -> sink disabled,
        # but emit must stay silent (best-effort, never breaks the call).
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        tracer = JsonlFileTracer("sess-4", trace_dir=blocker)
        tracer.emit("user_turn", text="hi")  # must not raise


class TestFactory:
    def test_disabled_returns_null_tracer(self):
        from adapters.tracing import NullTracer, get_tracer

        tracer = get_tracer("sess", enabled=False)
        assert isinstance(tracer, NullTracer)
        assert tracer.emit("anything", x=1) is None  # no-op, no file

    def test_enabled_returns_file_tracer(self, tmp_path):
        from adapters.tracing import JsonlFileTracer, get_tracer

        tracer = get_tracer("sess", enabled=True, trace_dir=tmp_path)
        assert isinstance(tracer, JsonlFileTracer)

    def test_new_session_id_unique_and_sortable(self):
        from adapters.tracing import new_session_id

        a = new_session_id()
        b = new_session_id()
        assert a != b
        assert b >= a  # microsecond timestamp -> monotonic-ish, sortable


class _CaptureTracer:
    """In-memory tracer to assert what ReactAgent emits."""

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


class TestReactAgentEmits:
    """ReactAgent translates tool observations into trace events (no LLM)."""

    def _agent(self, tracer):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="+37060020105", language="lt", tracer=tracer)

    def test_session_start_on_init(self, db_connection):
        cap = _CaptureTracer()
        self._agent(cap)
        assert cap.events[0]["type"] == "session_start"
        assert cap.events[0]["model"]

    def test_tool_result_and_verdict_events(self, db_connection):
        cap = _CaptureTracer()
        agent = self._agent(cap)
        cap.events.clear()

        # Feed a real diagnose_connection observation through the helper.
        from agent.tools import diagnose_connection

        obs = json.dumps(diagnose_connection("CUST105"))
        agent._trace_tool_result("diagnose_connection", obs)

        types = [e["type"] for e in cap.events]
        assert types == ["tool_result", "verdict"]
        verdict = cap.events[1]
        assert verdict["group"] == "B6"
        assert verdict["reason"] == "foreign_mac"
        assert verdict["side"] == "customer"

    def test_resolve_address_hint_in_summary(self, db_connection):
        cap = _CaptureTracer()
        agent = self._agent(cap)
        cap.events.clear()

        from agent.tools import resolve_address

        obs = json.dumps(resolve_address(city="Šiauliai", street="Žeimių"))
        agent._trace_tool_result("resolve_address", obs)

        result = cap.events[0]
        assert result["type"] == "tool_result"
        assert "Ginkūnai" in result["summary"]["hint"]

    def test_end_session_idempotent(self, db_connection):
        cap = _CaptureTracer()
        agent = self._agent(cap)
        cap.events.clear()

        agent.end_session(outcome="complete")
        agent.end_session(outcome="complete")  # second call is a no-op

        ends = [e for e in cap.events if e["type"] == "session_end"]
        assert len(ends) == 1
        assert ends[0]["outcome"] == "complete"

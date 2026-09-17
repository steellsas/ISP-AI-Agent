"""Contact record (M6, D-14): every call ends with one record whose outcome is derived from
the final state; the transport end never overwrites it (F-4)."""

import json

import pytest
from agent.call_record.outcome import derive, outage_id


def _identified(make_state):
    state = make_state("+37060020101")
    state.identity.customer_id = "CUST101"
    return state


class TestUnidentified:
    def test_technical_error(self, make_state):
        record = derive(make_state("+37000000000"), technical_error=True)

        assert (record.outcome, record.unidentified_reason, record.needs_review) == (
            "error",
            "technical_error",
            True,
        )

    def test_stuck(self, make_state):
        state = make_state("+37000000000")
        state.closing.unidentified_reason = "stuck"

        assert derive(state).unidentified_reason == "stuck"
        assert derive(state).needs_review

    def test_not_a_customer(self, make_state):
        state = make_state("+37000000000")
        state.closing.unidentified_reason = "not_a_customer"

        assert derive(state).outcome == "unidentified"
        assert derive(state).unidentified_reason == "not_a_customer"

    def test_caller_refused_needs_no_review(self, make_state):
        state = make_state("+37000000000")
        state.closing.case_closed = True
        state.closing.closed_reason = "declined"

        record = derive(state)
        assert (record.unidentified_reason, record.needs_review) == ("caller_refused", False)

    def test_address_not_found(self, make_state):
        from agent.slots import SlotStatus

        state = make_state("+37000000000")
        state.identity.profile.street.propose("Vilniaus g.", 1.0, SlotStatus.HEARD)

        assert derive(state).unidentified_reason == "address_not_found"

    def test_hung_up(self, make_state):
        record = derive(make_state("+37000000000"))

        assert (record.outcome, record.unidentified_reason, record.needs_review) == (
            "abandoned",
            "hung_up",
            True,
        )


class TestIdentified:
    def test_informed_outage(self, make_state):
        state = _identified(make_state)
        state.diagnosis.outage_reported = True

        assert derive(state).outcome == "informed_outage"

    def test_informed_debt(self, make_state):
        state = _identified(make_state)
        state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
        state.diagnosis.news_delivered = True

        assert derive(state).outcome == "informed_debt"

    def test_a_disputed_debt_ticket_is_a_ticket(self, make_state):
        state = _identified(make_state)
        state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
        state.diagnosis.news_delivered = True
        state.ticket.ticket_id = "TKT1"

        assert derive(state).outcome == "ticket"

    def test_ticket_appended(self, make_state):
        state = _identified(make_state)
        state.closing.appended_ticket_id = "TKTDEMO307"

        assert derive(state).outcome == "ticket_appended"

    def test_resolved(self, make_state):
        state = _identified(make_state)
        state.closing.case_closed = True
        state.closing.closed_reason = "resolved"

        record = derive(state)
        assert (record.outcome, record.needs_review) == ("resolved", False)

    def test_hang_up_before_close_needs_review(self, make_state):
        state = _identified(make_state)
        state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_lights"}

        record = derive(state)
        assert (record.outcome, record.needs_review) == ("abandoned", True)
        assert record.unidentified_reason is None


def test_outage_id_from_the_verdict_or_the_held_outage(make_state):
    state = _identified(make_state)
    state.identity.held_outage = {"outage_id": "OUT7"}
    assert outage_id(state) == "OUT7"

    state.diagnosis.verdicts["network"] = {"signals": {"incident": {"outage_id": "OUT9"}}}
    assert outage_id(state) == "OUT9"


class TestFinalizer:
    @pytest.fixture
    def agent(self, db_connection, tmp_path):
        from adapters.tracing.jsonl_tracer import JsonlFileTracer

        from tests.calls import make_agent

        tracer = JsonlFileTracer("record-test", trace_dir=tmp_path)
        return make_agent("+37000000000", language="lt", tracer=tracer)

    def _rows(self, db_connection):
        with db_connection.cursor() as cur:
            cur.execute("SELECT * FROM conversations WHERE session_id = ?", ("record-test",))
            return [dict(r) for r in cur.fetchall()]

    def test_one_record_with_the_derived_outcome(self, agent, db_connection):
        from agent.call_record.finalizer import finalize

        agent.state.intake.problem_type = "internet_down"
        finalize(agent.state, agent.runtime, transport_end="client_closed")
        finalize(agent.state, agent.runtime, transport_end="expired")  # idempotent

        rows = self._rows(db_connection)
        assert len(rows) == 1
        row = rows[0]
        assert row["outcome"] == "abandoned"  # not "client_closed" (F-4)
        assert row["transport_end"] == "client_closed"
        assert (row["unidentified_reason"], row["needs_review"]) == ("hung_up", 1)
        assert row["intent"] == "internet_down"
        assert row["audio_retention_until"]  # an unidentified caller's audio expires
        assert json.loads(row["summary"])["review_reason"] == "hung_up"

    def test_a_technical_error_in_the_trace_is_the_outcome(self, agent, db_connection):
        from agent.call_record.finalizer import finalize

        agent.tracer.emit("error", where="voice_turn", detail="boom")
        finalize(agent.state, agent.runtime, transport_end="ws_disconnect")

        assert self._rows(db_connection)[0]["outcome"] == "error"

    def test_a_warning_note_is_not_a_technical_error(self, agent, db_connection):
        from agent.call_record.finalizer import finalize

        agent.tracer.emit("error", level="warn", where="classifier", detail="fallback")
        finalize(agent.state, agent.runtime, transport_end="client_closed")

        assert self._rows(db_connection)[0]["outcome"] == "abandoned"

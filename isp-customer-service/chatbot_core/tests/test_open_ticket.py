"""Open tickets (M6, D-12): a repeat call is a note on the ticket, never a duplicate."""

from agent.decide.rules import open_ticket

OPEN = {
    "ticket_id": "TKT1",
    "ticket_type": "fault_technician",
    "problem_type": "internet_down",
    "status": "open",
    "created_at": "2026-09-15T10:00:00",
}


def _caller(make_state, said):
    state = make_state("+37060030307")
    state.identity.customer_id = "CUST307"
    state.identity.open_tickets = [dict(OPEN)]
    state.intake.problem_type = "internet_down"
    state.intake.heard_utterances = [said]
    return state


class TestSameProblem:
    def test_the_same_problem_finds_the_open_ticket(self, make_state):
        assert (
            open_ticket.same_problem_ticket(_caller(make_state, "neveikia"))["ticket_id"] == "TKT1"
        )

    def test_a_different_problem_takes_the_normal_path(self, make_state):
        state = _caller(make_state, "televizija nerodo")
        state.intake.problem_type = "tv"

        assert open_ticket.same_problem_ticket(state) is None


class TestNoteKind:
    def test_nobody_came(self, make_state):
        assert (
            open_ticket.note_kind(_caller(make_state, "vis dar neveikia, niekas neatvažiavo"))
            == "nobody_came"
        )

    def test_just_checking(self, make_state):
        assert (
            open_ticket.note_kind(_caller(make_state, "norėjau pasiteirauti, kada sutvarkys"))
            == "just_checking"
        )


class TestRepeatCall:
    def test_the_note_goes_on_the_ticket_and_the_status_is_told(self, make_state, make_runtime):
        from agent.inform import inform_text

        calls = []

        def fake_tools(name, args):
            calls.append((name, args))
            return {"success": True}

        state = _caller(make_state, "niekas neatvažiavo")
        rt = make_runtime(fake_tools=fake_tools)

        open_ticket.repeat_call(state, rt)

        assert calls == [
            (
                "append_ticket_note",
                {"ticket_id": "TKT1", "note": "niekas neatvažiavo", "kind": "nobody_came"},
            )
        ]
        assert state.closing.appended_ticket_id == "TKT1"
        assert state.resolution.procedure is None  # nothing re-diagnosed, nothing registered
        text = inform_text(state, rt, "open_ticket_exists")
        assert "jau užregistruotas" in text and "laukia meistro" in text

"""Problema — Pagrindinė problema."""

from agent.call_record.finalizer import build_call_summary, finalize
from agent.graph_v2.state import (
    ClosingState,
    DiagnosisState,
    DialogState,
    GraphState,
    IdentityState,
    IntakeState,
    ResolutionState,
    TicketContext,
    TicketState,
    TurnScratch,
)

from tests.engine_fakes import as_call

FUNCTION = "Pagrindinė problema"

# --- from test_fault_packs.py ---


class TestPrimaryGoalFrozen:
    """A (2026-08-21): the primary goal never flips mid-call; other mentions
    become secondary problems (asked at the end, listed on the ticket)."""

    def test_mid_call_mention_becomes_secondary(self, db_connection):
        from tests.calls import hear, make_agent

        agent = make_agent("unknown")
        s = agent.state
        hear(agent, "Neveikia internetas")
        assert s.intake.problem_type == "internet_down"
        s.identity.customer_id = "CUST009"
        hear(agent, "O dar televizorius man blogai rodo")
        assert s.intake.problem_type == "internet_down"  # frozen
        assert s.intake.secondary_problems and s.intake.secondary_problems[0]["type"] == "tv"
        # dedupe: the same type mentioned again does not duplicate
        hear(agent, "Tas televizorius vis dar blogai")
        assert len(s.intake.secondary_problems) == 1
        # A request type (billing, D-11) never becomes a secondary TECH problem —
        # it is not a fault to list on the fault ticket.
        hear(agent, "O dar sąskaitos klausimas turiu")
        assert all(x["type"] != "billing" for x in s.intake.secondary_problems)

    def test_secondary_lands_on_ticket_and_closing_facts(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        s = agent.state
        s.identity.customer_id = "CUST009"
        s.intake.problem_type = "internet_down"
        s.intake.secondary_problems.append({"type": "tv", "text": "TV blogai rodo", "turn": 5})
        s.closing.case_closed = True
        block = context_card(agent.state, agent.runtime)
        assert "SECONDARY PROBLEMS" in block and "TV blogai rodo" in block

    def test_bridge_bound_phrase_states_visibility(self):
        from agent.contract.locale import phrase

        text = phrase("identification.bridge_bound")
        assert "matau" in text.lower() and "pririšau" in text.lower()


class TestOpenerAndClosingHygiene:
    """Live 2026-08-21: a garbled opener triggered the address offer before
    any problem; a garble in the ticket dialogue became a 'secondary problem';
    the closing LLM re-asked the hours after registration."""

    def test_garbled_opener_asks_for_the_problem(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        from tests.calls import make_agent

        agent = make_agent("unknown")
        r1 = scripted_words(agent.state, agent.runtime, "Atsikai, daro.")
        assert r1 and "problema" in r1
        r2 = scripted_words(agent.state, agent.runtime, "Mmm kažkas.")
        assert r2 and "neveikia" in r2  # U8: the second prompt says WHY
        # U8 (Andrius 2026-10-09): the third prompt says what happens without an answer, the
        # fourth fruitless turn ends the call with the reason — and hangs up.
        r3 = scripted_words(agent.state, agent.runtime, "Nu...")
        assert r3 and "turėsiu baigti pokalbį" in r3
        bye = scripted_words(agent.state, agent.runtime, "Eee...")
        assert bye and "nepasakėte, kas neveikia" in bye and "skambinkite" in bye
        assert agent.state.closing.is_complete

    def test_phone_account_block_waits_for_the_problem(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.identity.phone_candidate = {
            "customer_id": "CUST009",
            "name": "T",
            "address": "Šiauliai, Vilniaus g. 29",
            "street": "Vilniaus g.",
            "house": "29",
            "apartment": None,
            "city": "Šiauliai",
        }
        assert "PHONE ACCOUNT" not in (context_card(agent.state, agent.runtime) or "")
        agent.state.intake.problem_type = "internet_down"
        assert "PHONE ACCOUNT" in (context_card(agent.state, agent.runtime) or "")

    def test_no_secondary_problems_from_ticket_stage_garbles(self, db_connection):
        from tests.calls import hear, make_agent

        agent = make_agent("unknown")
        s = agent.state
        s.intake.problem_type = "internet_down"
        s.identity.customer_id = "CUST009"
        agent.state.ticket.stage = "hours"
        hear(agent, "Sąskaitos žemės gatvės klausimas")
        assert s.intake.secondary_problems == []
        agent.state.ticket.stage = None
        hear(agent, "Žemės gatvės")  # 2 words: a garble
        assert s.intake.secondary_problems == []
        hear(agent, "O dar televizorius man blogai rodo")
        assert s.intake.secondary_problems and s.intake.secondary_problems[0]["type"] == "tv"

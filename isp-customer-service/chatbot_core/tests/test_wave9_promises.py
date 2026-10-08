"""Wave 9 — words may not outrun the engine (live calls 2026-10-07).

T1 a goodbye cannot end a call that still owes a registration; T2 an answer and a question
in one breath keep the Case's move; T3 a promised registration becomes the contact
dialogue; T4 our own sentence heard back is echo; T5 „kiek nemokėjau?" is a question about
the amount, not a dispute.
"""

import pytest


class _Tracer:
    session_id = "wave9"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})

    def decisions(self):
        return [(e.get("intent"), e.get("action")) for e in self.events if e["type"] == "decision"]


@pytest.fixture
def dead_router(make_state, make_runtime):
    """The dead-router call of 2026-10-07 at the moment the Case has summed it up."""
    tracer = _Tracer()
    state, rt = make_state("+37060012353"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST009"
    state.identity.caller_name = "Andrius"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    state.case.fault, state.case.solution = "no_mac_observed", 0
    return state, rt, tracer


@pytest.fixture
def debt(make_state, make_runtime):
    """A caller who has just heard the debt news."""
    tracer = _Tracer()
    state, rt = make_state("+37060020101"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST101"
    state.identity.caller_name = "Rokas"
    state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
    state.diagnosis.news_delivered = True
    return state, rt, tracer


class TestT1GoodbyeWithAnOpenRegistration:
    def test_the_inform_close_leaves_a_case_alone(self, dead_router):
        from agent.decide.rules.closing import maybe_close_inform

        state, rt, _ = dead_router
        state.diagnosis.news_delivered = True  # the summary turn marks the news as told
        state.case.summarised = True

        maybe_close_inform(state, rt, "Sutariam, viskas ačiū.")

        assert not state.closing.case_closed

    def test_the_inform_close_still_ends_a_debt_call(self, debt):
        from agent.decide.rules.closing import maybe_close_inform

        state, rt, _ = debt
        maybe_close_inform(state, rt, "Aišku, ačiū, viso gero")

        assert state.closing.case_closed

    def test_a_goodbye_after_the_summary_goes_to_the_registration(self, dead_router):
        from agent.decide.rules.head import farewell_mid_process

        state, rt, tracer = dead_router
        state.case.summarised = True

        assert farewell_mid_process(state, rt, "Sutariam, viskas ačiū.")
        assert not state.dialog.end_confirm_pending  # no „Ar tikrai norite baigti?"
        assert ("farewell_mid_process", "ticket_first") in tracer.decisions()

    def test_a_goodbye_mid_fix_is_confirmed_then_offered_a_technician(self, dead_router):
        from agent.decide.rules.head import end_confirm_answer, farewell_mid_process

        state, rt, _ = dead_router
        assert farewell_mid_process(state, rt, "Viso gero")
        assert state.dialog.end_confirm_pending

        end_confirm_answer(state, rt, "Taip, baigiam")
        assert state.dialog.end_ticket_offer  # not closed as „declined"
        assert not state.closing.case_closed

        end_confirm_answer(state, rt, "Taip, užregistruokite")
        assert state.ticket.stage == "phone"

    def test_a_declined_technician_closes(self, dead_router):
        from agent.decide.rules.head import end_confirm_answer, farewell_mid_process

        state, rt, _ = dead_router
        farewell_mid_process(state, rt, "Viso gero")
        end_confirm_answer(state, rt, "Taip, baigiam")
        end_confirm_answer(state, rt, "Ne, nereikia")

        assert state.closing.case_closed
        assert state.ticket.stage is None


class TestT2AnswerAndQuestionInOneBreath:
    def test_the_case_keeps_the_turn_and_the_question_is_flagged(self, dead_router, monkeypatch):
        from agent.decide.plan import Say, TurnPlan
        from agent.decide.rules import reply, stage

        state, rt, tracer = dead_router
        case_plan = TurnPlan(
            owner="procedure", rule="case.summary", say=Say(kind="directive", stage="diagnosis")
        )
        passthrough = TurnPlan(
            owner="diagnosis",
            rule="dialog.question_passthrough",
            say=Say(kind="directive", stage="diagnosis"),
        )
        monkeypatch.setattr(stage, "_stage_plan", lambda s, r: case_plan)
        monkeypatch.setattr(reply, "scripted_layer", lambda s, r: passthrough)

        assert stage.plan(state, rt) is case_plan
        assert state.turn.also_asked
        assert ("question_mid_case", "answer_then_step") in tracer.decisions()

    def test_the_card_tells_the_speaker_to_answer_first(self, dead_router, monkeypatch):
        from agent.speak import context_card
        from agent.speak.context_card import _also_asked

        state, rt, _ = dead_router
        monkeypatch.setattr(context_card, "_kb_answer", lambda s, r: "")
        state.dialog.last_heard = "Gerai, veikia. Kada dėl routerio paskambinsit?"
        assert _also_asked(state, rt) == []

        state.turn.also_asked = True
        line = _also_asked(state, rt)[0]
        assert "Kada dėl routerio" in line and "promise no registration" in line

    def test_a_how_question_gets_the_written_knowledge(self, dead_router, monkeypatch):
        """Eval K1: „kaip pakeisti wifi slaptažodį?" mid-Case is answered from the knowledge
        base, not with „užregistruosiu jūsų klausimą"."""
        from agent.speak import context_card

        state, rt, _ = dead_router
        state.turn.also_asked = True
        state.dialog.last_heard = "O sakykite, kaip pakeisti wifi slaptažodį?"
        monkeypatch.setattr(
            context_card, "_kb_answer", lambda s, r: "Naršyklėje įveskite 192.168.0.1 …"
        )

        line = context_card._also_asked(state, rt)[0]
        assert "192.168.0.1" in line and "written knowledge" in line


class TestT3APromiseBecomesTheProcess:
    CLAIM = "Dėl routerio geriausiai atsakys atsakingas žmogus — užregistruosiu jūsų klausimą."

    def test_a_case_promise_starts_the_contact_dialogue(self, dead_router):
        from agent.execute.ticket import registration_claim_guard

        state, rt, _ = dead_router
        state.case.summarised = True

        extra = registration_claim_guard(state, rt, self.CLAIM)

        assert extra and state.ticket.stage == "phone"
        assert state.ticket.request_type is None  # a technician, not a billing question

    def test_a_promise_after_the_debt_news_is_a_billing_request(self, debt):
        from agent.execute.ticket import registration_claim_guard

        state, rt, _ = debt
        extra = registration_claim_guard(
            state, rt, "Galiu užregistruoti — užregistruosiu jūsų klausimą dėl skolos."
        )

        assert extra and state.ticket.request_type == "billing_request"
        assert state.ticket.stage == "phone"

    @pytest.mark.parametrize(
        "text",
        [
            "Patikrinome lemputes ir prijungėme kompiuterį.",  # no promise
            "Užregistravau jūsų routerį prie linijos.",  # a device bind, not a ticket
        ],
    )
    def test_no_promise_no_dialogue(self, dead_router, text):
        from agent.execute.ticket import registration_claim_guard

        state, rt, _ = dead_router
        state.case.summarised = True

        assert registration_claim_guard(state, rt, text) is None
        assert state.ticket.stage is None

    def test_a_running_registration_is_left_alone(self, dead_router):
        from agent.execute.ticket import registration_claim_guard

        state, rt, _ = dead_router
        state.case.summarised = True
        state.ticket.stage = "hours"

        assert registration_claim_guard(state, rt, self.CLAIM) is None
        assert state.ticket.stage == "hours"


class TestT4OurOwnSentenceIsEcho:
    AGENT = (
        "Suprantu. Sąskaitų detalių aš nematau, bet galiu užregistruoti jūsų klausimą — "
        "atsakingas žmogus su jumis susisieks ir aptars skolą. Ar registruoti?"
    )

    @pytest.mark.parametrize(
        ("heard", "echo"),
        [
            ("Atsakingas žmogus su jumis susisieks ir aptars skolą.", True),  # live 2026-10-07
            ("Taip, registruokite.", False),  # a real short answer is never swallowed
            ("Taip.", False),
            ("Ne, aš noriu sužinoti, kiek tiksliai skolingas.", False),
        ],
    )
    def test_echo_needs_a_sentence_of_our_own_words(self, heard, echo):
        from agent.barge_in import is_echo

        assert is_echo(heard, self.AGENT) is echo

    def test_no_reference_no_echo(self):
        from agent.barge_in import is_echo

        assert not is_echo("Atsakingas žmogus su jumis susisieks", "")


class TestT5HowMuchIsNotADispute:
    @pytest.mark.parametrize(
        ("said", "dispute"),
        [
            ("O ho, kiek ne mokėjau?", False),  # live 2026-10-07
            ("Kiek aš skolingas?", False),
            ("Kaip tai skola, aš sumokėjau", True),
            ("Kiek? Aš juk sumokėjau!", True),  # a real objection still wins
            ("Nesutinku su ta skola", True),
            ("Aišku, ačiū, sumokėsiu", False),
        ],
    )
    def test_dispute_reading(self, said, dispute):
        from agent.decide.rules.requests import disputes_debt

        assert disputes_debt(said) is dispute

    def test_the_amount_question_is_answered_from_the_news(self, debt):
        from agent.decide.rules.requests import debt_offer_turn
        from agent.faq import match

        state, rt, _ = debt

        assert debt_offer_turn(state, rt, "O ho, kiek ne mokėjau?") is None
        assert "debt_amount" in [e["topic"] for e in match("O ho, kiek ne mokėjau?")]


def test_scenario_reset_is_wired_in_the_dashboard():
    """T6: a picked scenario's call starts from the seeded DB."""
    from pathlib import Path

    js = Path(__file__).resolve().parents[1] / "src" / "app" / "static" / "js"
    app = (js / "app.js").read_text(encoding="utf-8")
    assert "Scenarios.current()" in app and "/admin/db/reset" in app
    assert "current: () => current" in (js / "scenarios.js").read_text(encoding="utf-8")


def test_a_normal_voice_turn_checks_for_our_own_echo(monkeypatch):
    """T4 wiring: without a barge-in the pipeline still gets an echo check — and only that
    (a plain „taip" is never read as consent-to-swallow)."""
    import threading
    from types import SimpleNamespace

    from app import voice

    seen = {}

    class _Pipeline:
        prev_cancelled = False
        last_turn_aligned = True
        last_turn_sentences: list = []

        def stream_turn(self, audio, **kwargs):
            check = kwargs["interruption"]
            seen["echo"] = check("Atsakingas žmogus su jumis susisieks ir aptars skolą.")
            seen["yes"] = check("Taip.")
            yield b"REAL"

    ms = SimpleNamespace(
        voice=_Pipeline(),
        cancel=threading.Event(),
        turn_count=0,
        session=SimpleNamespace(
            session_id="t",
            is_complete=False,
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
            last_spoken_text=lambda: TestT4OurOwnSentenceIsEcho.AGENT,
        ),
    )
    monkeypatch.setenv("API_RECORD_AUDIO", "0")
    voice.run_voice_turn_stream(ms, b"RIFF-fake", lambda chunk: None)

    assert seen == {"echo": "echo", "yes": None}

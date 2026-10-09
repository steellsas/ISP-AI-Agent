"""Wave 10 (stage 0) — guards that still read v1's `resolution.procedure`, and four live
misreadings from 2026-10-07. Each test names the finding it pins (S1..S7, V1..V7)."""

import pytest


class _Tracer:
    session_id = "wave10"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def case_call(make_state, make_runtime):
    """A v2 Case call on a fault, the caller identified."""
    state, rt = make_state("+37060012353"), make_runtime(tracer=_Tracer())
    state.identity.customer_id = "CUST009"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    state.case.fault, state.case.solution = "no_mac_observed", 0
    return state, rt


class TestS1AFaultIsNotNews:
    def _after_the_name(self, state, rt):
        from agent.execute.step import mark_step_presented

        state.identity.result_pending = True
        state.identity.caller_name = "Andrius"
        mark_step_presented(state, rt)

    def test_a_case_fault_is_not_marked_told(self, case_call):
        state, rt = case_call
        self._after_the_name(state, rt)
        assert not state.diagnosis.news_delivered

    def test_a_debt_is_marked_told(self, case_call):
        state, rt = case_call
        state.case.fault = None
        state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
        self._after_the_name(state, rt)
        assert state.diagnosis.news_delivered


def test_s2_the_resume_hold_lasts_one_turn(case_call):
    from agent.perceive.node import read_turn_start

    state, rt = case_call
    state.dialog.resume_hold_due = True
    read_turn_start(state, rt, "O kiek kainuoja naujas routeris?")
    assert not state.dialog.resume_hold_due


def test_s5_a_hang_up_on_the_case_homework_is_a_callback(case_call, monkeypatch):
    """The homework was told and waits for „tinka?" — hanging up keeps the agreement."""
    from agent import executor_flow
    from agent.call_record import finalizer

    state, rt = case_call
    state.case.awaiting = "later_agreed"
    registered = []
    monkeypatch.setattr(
        executor_flow, "register_ticket_from_state", lambda *a, **k: registered.append(a)
    )
    finalizer.finalize(state, rt)

    assert state.closing.closed_reason == "callback"
    assert registered == []


def test_s6_a_second_fault_mid_case_is_recorded(case_call):
    from agent.decide.rules.intake import _apply_problem

    state, rt = case_call
    state.intake.problem_type = "internet_down"
    state.dialog.last_heard = "Ir televizorius irgi nerodo jokių kanalų"
    state.turn.problem_reading = "tv_down"
    _apply_problem(state, rt)

    assert [p["type"] for p in state.intake.secondary_problems] == ["tv_down"]


def test_s7_solved_shows_after_a_case_resolution(case_call):
    from agent.speak.context_card import _case_facts

    state, rt = case_call
    state.closing.case_closed = True
    state.closing.closed_reason = "resolved"

    assert any(line.startswith("SOLVED") for line in _case_facts(state, rt))


class TestV1YesToOurOffer:
    @pytest.mark.parametrize(
        ("said", "more"),
        [
            ("Taip.", True),  # live 2026-10-07: closed the call
            ("Taip, turiu", True),
            ("Ne, ačiū", False),
            ("Taip, viso gero", False),  # the goodbye
        ],
    )
    def test_yes_means_they_have_more(self, case_call, said, more):
        from agent.decide.rules.reply import _yes_to_more

        state, _ = case_call
        state.dialog.last_question = "Ar turite kitų klausimų dėl savo interneto ryšio?"
        assert _yes_to_more(state, said) is more

    def test_yes_to_another_question_is_not_more(self, case_call):
        from agent.decide.rules.reply import _yes_to_more

        state, _ = case_call
        state.dialog.last_question = "Ar lemputė dega?"
        assert not _yes_to_more(state, "Taip.")


@pytest.mark.parametrize(
    ("said", "lights"),
    [
        ("Jokios net dega.", "no"),  # live 2026-10-07: ASR lost the „ne", read as lit
        ("Nė viena net šviečia", "no"),
        ("Jokia lemputė nedega", "no"),
        ("Visos dega", "yes"),
        ("Taip, dega", "yes"),
        ("Dega žalia", "green"),
    ],
)
def test_v4_a_negative_pronoun_means_off(said, lights):
    from agent.perceive.detectors import detect_lights

    assert detect_lights(said) == lights


class TestV5OnlyTheCallersOwnNameCorrects:
    def _answer(self, case_call, heard):
        from agent.decide.rules.intake import _apply_caller_relation

        state, rt = case_call
        state.identity.caller_name = "Andrius"
        state.dialog.last_heard = heard
        state.turn.caller_relation_reading = "family"
        _apply_caller_relation(state, rt)
        return state.identity.caller_name

    def test_the_holders_name_is_not_the_caller(self, case_call):
        # live 2026-10-07: the caller became „Gedrius"
        assert self._answer(case_call, "Taip, mano tėtis Gedrius yra vardu.") == "Andrius"

    def test_a_garbled_word_is_not_a_name(self, case_call):
        assert self._answer(case_call, "Aršku ačių lauksu.") == "Andrius"

    def test_their_own_name_corrects(self, case_call):
        assert self._answer(case_call, "Ne, mano vardas Giedrius.") == "Giedrius"


class TestV7AddressReading:
    STREETS = ["Aušros g.", "Tilžės g.", "Vilniaus g."]

    @pytest.mark.parametrize(
        ("said", "street"),
        [
            ("Vakar vakare, po audros", None),  # eval I1: became „Aušros gatvė"
            ("Ausros 5", "Aušros g."),  # a number makes the near match an address
            ("Aušros gatvė", "Aušros g."),  # an exact name
            ("Tilžės 60 butas 3", "Tilžės g."),
        ],
    )
    def test_a_near_street_needs_address_evidence(self, said, street):
        from agent.perceive.nlu import extract_address

        assert extract_address(said, self.STREETS, ["Šiauliai"]).street == street


def test_piper_session_is_bounded(monkeypatch):
    """TTS: the ONNX session uses a bounded pool without spinning (live: 0.3–2.4 s/sentence)."""
    from adapters.tts import piper_tts

    seen = {}

    class _Session:
        def __init__(self, path, sess_options=None, providers=None):
            seen["threads"] = sess_options.intra_op_num_threads

    import onnxruntime

    monkeypatch.setattr(onnxruntime, "InferenceSession", _Session)
    monkeypatch.setenv("TTS_PIPER_THREADS", "4")
    piper_tts._cpu_session("model.onnx")
    assert seen["threads"] == 4


class TestAPromiseNothingBacksIsNotSpoken:
    """A: „užregistruosiu" with no reason to register is withheld before TTS (eval K1); with a
    reason it stays — the claim guard then turns it into the contact dialogue (wave 9, T3)."""

    PROMISE = "Šiuo klausimu geriausiai atsakys atsakingas žmogus — užregistruosiu jūsų klausimą."

    def test_no_reason_no_promise(self, case_call):
        from agent.execute.ticket import unbacked_promise

        state, _ = case_call
        state.case.fault, state.case.solution = None, None  # still identifying the fault
        assert unbacked_promise(state, self.PROMISE)

    @pytest.mark.parametrize("backing", ["case", "debt", "ticket"])
    def test_a_backed_promise_stays(self, case_call, backing):
        from agent.execute.ticket import unbacked_promise

        state, _ = case_call
        if backing == "debt":
            state.case.fault = None
            state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
            state.diagnosis.news_delivered = True
        if backing == "ticket":
            state.case.fault = None
            state.ticket.stage = "phone"
        assert not unbacked_promise(state, self.PROMISE)

    def test_other_sentences_pass(self, case_call):
        from agent.execute.ticket import unbacked_promise

        state, _ = case_call
        state.case.fault = None
        assert not unbacked_promise(state, "Naršyklėje įveskite 192.168.0.1.")

    def test_the_streamed_reply_and_history_lose_the_promise(self, case_call):
        from types import SimpleNamespace
        from unittest.mock import patch

        from agent.speak.node import stream_reply

        state, rt = case_call
        state.case.fault, state.case.solution = None, None

        def _stream(**kwargs):
            yield "Naršyklėje įveskite 192.168.0.1. "
            yield self.PROMISE
            return SimpleNamespace(content="…")

        with (
            patch("agent.speak.node.stream_tool_completion", side_effect=_stream),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            spoken = "".join(stream_reply(state, rt, "diagnosis"))

        assert spoken.strip() == "Naršyklėje įveskite 192.168.0.1."
        assert state.messages[-1]["content"] == "Naršyklėje įveskite 192.168.0.1."
        assert any(e.get("reason") == "unbacked_promise" for e in rt.tracer.events)


def test_cyrillic_slips_are_written_in_latin():
    from agent.speak.guard import latin_lookalikes

    assert latin_lookalikes("skурti į Wireless Security") == "skurti į Wireless Security"
    assert latin_lookalikes("Laba diena") == "Laba diena"


@pytest.mark.parametrize(
    ("turn_type", "searched"),
    [
        ("answer", True),  # eval K1: Gemma labelled a „kaip…?" an answer
        ("question", True),
        ("confusion", False),  # still a job for re-explaining, not new knowledge
        ("deviation", False),
    ],
)
def test_a_how_question_reaches_the_knowledge_base(turn_type, searched):
    from agent.knowledge_need import Refusal, from_caller

    need = from_caller("O sakykite, kaip pakeisti wifi slaptažodį?", turn_type=turn_type)
    assert (not isinstance(need, Refusal)) is searched


def test_a_bare_question_mid_case_keeps_the_old_path(case_call, monkeypatch):
    """T2 narrowed (eval K1): only an answer + question keeps the Case's move; a turn that is
    ONLY a question gets the knowledge answer and the standing question."""
    from agent.decide.plan import Say, TurnPlan
    from agent.decide.rules import reply, stage

    state, rt = case_call
    ask = TurnPlan(owner="procedure", rule="case.ask", say=Say(kind="directive"))
    passthrough = TurnPlan(
        owner="diagnosis", rule="dialog.question_passthrough", say=Say(kind="directive")
    )
    monkeypatch.setattr(stage, "_stage_plan", lambda s, r: ask)
    monkeypatch.setattr(reply, "scripted_layer", lambda s, r: passthrough)

    assert stage.plan(state, rt) is passthrough
    assert not state.turn.also_asked

    state.case.moved_on_turn = state.dialog.turn_count  # the Case read an answer too
    assert stage.plan(state, rt) is ask

"""Kaip suprantamas atsakymas į klausimą, kurį agentas ką tik uždavė (7 banga).

Trys sluoksniai, ir šie testai gina kiekvieną:

    0. žodynas  — `detect_*` + `vocabulary.yaml`, nemokamas ir tikslus;
    1. modelis  — TO PATIES ėjimo supratimo kvietimas, kuriam paduodami ŠIO žingsnio variantai
                  (`perceive/evidence.py::_case_step_options`); jis grąžina etiketę iš uždaro
                  sąrašo, `is_answer` ir pasitikėjimą;
    2. matomumas — kai nė vienas nesuprato, trace'e lieka `reader_silent`, ir iš to sąrašo auga
                  žodynai bei parafrazės čia apačioje.

Andrius (2026-10-01): *„kad neatsitiktų taip, kad įvedant naujus gedimus atsiranda naujų
taisymų ar nesupratimo… gavęs tą pačią problemą kitais žodžiais nežinotų, kaip spręsti."*
"""

from __future__ import annotations

import pytest
from agent.call_record.finalizer import build_call_summary, finalize
from agent.contract import cards as catalog
from agent.decide.rules import case_rule
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
from agent.ledger import record_client, record_telemetry
from agent.modules import read_answer

from tests.diagnosis.test_facts import BASE
from tests.diagnosis.test_step_refusal import _hear, _Tracer, at_the_lights  # noqa: F401
from tests.engine_fakes import as_call

FUNCTION = "Atsakymų skaitymas"


class Collecting:
    """Trace'as, kurį galima perskaityti teste."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event_type: str, **fields) -> None:
        self.events.append((event_type, fields))

    def of(self, event_type: str) -> list[dict]:
        return [f for name, f in self.events if name == event_type]


@pytest.fixture
def call(make_state, make_runtime):
    state, rt = make_state("+37060020112"), make_runtime(tracer=Collecting())
    state.identity.customer_id = "CUST112"
    return state, rt


def _step(call: str, **args):
    from agent.contract.schema import ModuleCall

    return ModuleCall(module=call, args=args)


# --- 0 sluoksnis: parafrazės, kurias privalo suprasti ŽODYNAS ------------------------------
#
# Kiekviena eilutė — tikra formuluotė (iš gyvų skambučių arba jų artimas variantas) ir faktas,
# kurį ji turi nustatyti. Naujas gedimas prideda eilučių čia, ne naują `if` kode.
DICTIONARY: list[tuple[str, dict, str, tuple[str, str]]] = [
    # Tiltas: „neturiu" ir „tik telefonas" yra ATSAKYMAS, o prašymas registruoti — irgi.
    ("offer_bridge", {"to": "computer"}, "Neturiu.", ("bridge_agreed", "no")),
    ("offer_bridge", {"to": "computer"}, "Neturiu kompiuterio.", ("bridge_agreed", "no")),
    (
        "offer_bridge",
        {"to": "computer"},
        "Kompiuterio neturiu, tik telefoną.",
        ("bridge_agreed", "no"),
    ),
    ("offer_bridge", {"to": "computer"}, "Aš noriu registruoti gedimą.", ("bridge_agreed", "no")),
    ("offer_bridge", {"to": "computer"}, "Registruokit meistrą.", ("bridge_agreed", "no")),
    ("offer_bridge", {"to": "computer"}, "Nenoriu.", ("bridge_agreed", "no")),
    # Trumpi šnekamieji žymekliai: „jo" yra sutikimas sakinio pradžioje, bet ne įvardis viduryje
    # („jo šiandien nėra" — žr. MODEL_TIER žemiau), ir ne „jokia" viduje.
    ("offer_bridge", {"to": "computer"}, "Jo, gerai.", ("bridge_agreed", "yes")),
    ("offer_bridge", {"to": "computer"}, "Gerai, pabandom.", ("bridge_agreed", "yes")),
    # Eval S4: „neturiu" sakinyje, kuris iš tikrųjų yra TAIP — kompiuteris ir yra tai, ko tiltui
    # reikia. Nuogas „netur-" kamienas 7b bangoje buvo tai suplojęs į atsisakymą.
    (
        "offer_bridge",
        {"to": "computer"},
        "Neturiu kito routerio, tik kompiuterį",
        ("bridge_agreed", "yes"),
    ),
    ("offer_bridge", {"to": "computer"}, "Taip, turiu kompiuterį.", ("bridge_agreed", "yes")),
    # Vedimo sutikimas.
    ("offer_guide", {}, "Pabandykim kartu.", ("guide_agreed", "yes")),
    ("offer_guide", {}, "Gerai, einam.", ("guide_agreed", "yes")),
    ("offer_guide", {}, "Esu pasiruošęs.", ("guide_agreed", "yes")),
    ("offer_guide", {}, "Ne, geriau iš karto specialistą.", ("guide_agreed", "no")),
    # Ar yra kuo atidaryti nustatymus (telefonas TINKA).
    ("panel_device", {"device": "router"}, "Turiu telefoną.", ("panel_device", "yes")),
    ("panel_device", {"device": "router"}, "Kompiuterį turiu.", ("panel_device", "yes")),
    ("panel_device", {"device": "router"}, "Neturiu nieko.", ("panel_device", "no")),
    ("panel_device", {"device": "router"}, "Nu yra toks senas planšetas.", ("panel_device", "yes")),
    # Ar gali prieiti.
    ("reach", {"device": "router"}, "Taip, galiu.", ("reachable", "yes")),
    ("reach", {"device": "router"}, "Ne, aš ne namie.", ("reachable", "no")),
]


# Tos pačios parafrazės, bet faktą nustato RAKTINIŲ ŽODŽIŲ sluoksnis (`evidence.py`), ne modulio
# skaitytuvas: „įkištas" nėra „taip", o faktas vis tiek turi atsirasti.
KEYWORDS: list[tuple[str, str, str]] = [
    ("Maitinimo laidas įkištas tvirtai.", "power_cable", "plugged"),
    ("Laidas buvo ištrauktas iš rozetės.", "power_cable", "unplugged"),
    ("Nedega nė viena lemputė.", "lights", "off"),
    ("Lemputė mirksi.", "lights", "blinking"),
    ("Kompiuterio neturiu.", "has_computer", "no"),
    ("Turiu kompiuterį.", "has_computer", "yes"),
]


@pytest.mark.parametrize("heard,fact,value", KEYWORDS)
def test_the_keyword_layer_reads_this_phrasing(heard, fact, value):
    from agent.evidence import extract_client_facts

    assert extract_client_facts(heard).get(fact) == value


@pytest.mark.parametrize("module,args,heard,expected", DICTIONARY)
def test_the_dictionary_reads_this_phrasing(module, args, heard, expected):
    assert read_answer(_step(module, **args), heard) == expected


# Formuluotės, kurių žodynas sąmoningai NEGAUDO — jas skaito modelis (1 sluoksnis). Sąrašas
# egzistuoja todėl, kad būtų matoma, kas kuo laikosi: jei kuri nors čia pradeda veikti per
# žodyną, ji keliauja aukščiau, o ne tyliai dubliuojasi.
MODEL_TIER: list[tuple[str, dict, str]] = [
    ("offer_bridge", {"to": "computer"}, "Mmm, o kiek tai kainuos?"),
    ("offer_bridge", {"to": "computer"}, "Mano anūkas tuo užsiima, jo šiandien nėra."),
    ("offer_guide", {}, "Aš su technika nelabai draugauju."),
]


@pytest.mark.parametrize("module,args,heard", MODEL_TIER)
def test_this_phrasing_is_left_to_the_model(module, args, heard):
    assert read_answer(_step(module, **args), heard) is None


# --- 1 sluoksnis: modelis gauna ŠIO žingsnio variantus -------------------------------------


class TestTheModelIsToldWhatWeAsked:
    """Iki 7 bangos `step_perception_options` klausė v1 `resolution.procedure`, kurio v2 Case
    nebepildo — tad kortelės žingsniui variantai buvo `None` ir modelis niekada nežinojo, ko
    paklausėme. Vienintelis skaitytuvas buvo žodynas."""

    def _at_the_offer(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "device_seen": False})
        record_client(state, rt, "reachable", "yes")
        record_client(state, rt, "lights", "off")
        record_client(state, rt, "power_cable", "plugged")
        state.case.fault, state.case.solution = "no_mac_observed", 0
        steps = catalog.card("no_mac_observed").solution[0].steps
        state.case.step = next(i for i, s in enumerate(steps) if s.module == "offer_bridge")
        return state, rt

    def test_the_steps_own_labels_are_the_options(self, call, monkeypatch):
        from agent.perceive.evidence import step_perception_options

        monkeypatch.setenv("CLASSIFIER", "on")  # testuose jis išjungtas (conftest)
        state, rt = self._at_the_offer(call)
        state.case.step_said = state.case.step  # klausimas nuskambėjo

        options, step = step_perception_options(state, rt)

        assert set(options) == {"yes", "no"}
        assert "neturiu" in options["no"].lower()  # reikšmė, ne tik etiketė
        assert step.module == "offer_bridge"

    def test_a_question_that_never_went_out_gets_no_options(self, call, monkeypatch):
        """Tas pats 6 bangos reikalavimas kaip ir žodynui: planą galėjo paimti identifikacija."""
        from agent.perceive.evidence import step_perception_options

        monkeypatch.setenv("CLASSIFIER", "on")
        state, rt = self._at_the_offer(call)
        state.case.step_said = -1

        assert step_perception_options(state, rt) == (None, None)

    def _read_by_the_model(self, call, heard, confidence):
        state, rt = self._at_the_offer(call)
        state.case.step_said = state.case.step
        case_rule.plan(state, rt)  # pastato `awaiting`
        state.dialog.turn_count += 1
        state.dialog.last_heard = heard
        state.turn.perception = {
            "step": {"label": "no", "is_answer": True, "confidence": confidence},
        }
        return state, rt, case_rule.plan(state, rt)

    def test_a_confident_reading_is_confirmed_before_it_is_taken(self, call):
        """Andrius (2026-10-12): patikslinti visada geriau nei spėti. Žodynas to neskaito, tad
        tai tik modelio skaitymas — agentas pasako, ką suprato, ir klausia, ar teisingai."""
        state, rt, plan = self._read_by_the_model(call, "Nelabai, nebūtina man to.", 0.9)

        assert plan.rule == "case.confirm" and "ar teisingai" in plan.say.text
        assert state.case.facts.get("bridge_agreed") is None
        assert any(e.get("move") == "read_by_model" for e in rt.tracer.of("case"))

        state.dialog.turn_count += 1
        state.dialog.last_heard = "Taip"
        state.turn.perception = None
        case_rule.plan(state, rt)

        assert state.case.facts.get("bridge_agreed") == "no"
        assert state.case.confirming is None

    def test_a_denied_reading_is_dropped_and_the_question_asked_simply(self, call):
        state, rt, _ = self._read_by_the_model(
            call, "Mano anūkas tuo užsiima, jo šiandien nėra.", 0.6
        )
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Ne, ne taip"
        state.turn.perception = None
        case_rule.plan(state, rt)

        assert state.case.facts.get("bridge_agreed") is None
        assert state.case.unclear == state.case.step  # perklausiama dviem pasirinkimais

    def test_a_model_no_needs_the_callers_own_negation(self, call):
        """7e / eval D8: į „Visuose" (atsakymą apie įrenginius) modelis pasakė, kad klientas prie
        routerio prieiti NEGALI — pasitikėjimas 1,0 — ir skambutis nuėjo į namų darbus. Modelis
        gali atverti duris, bet ne užverti jų be kliento žodžio: lietuviškas „ne" nešasi neiginį."""
        state, rt = self._at_the_offer(call)
        state.case.step_said = state.case.step
        case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Visuose"  # jokio neiginio
        state.turn.perception = {"step": {"label": "no", "is_answer": True, "confidence": 1.0}}

        case_rule.plan(state, rt)

        assert state.case.facts.get("bridge_agreed") is None

    def test_a_weak_reading_changes_nothing(self, call):
        state, rt = self._at_the_offer(call)
        state.case.step_said = state.case.step
        case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Mmm, o kiek čia bus?"
        state.turn.perception = {"step": {"label": "no", "is_answer": True, "confidence": 0.2}}

        case_rule.plan(state, rt)

        assert state.case.facts.get("bridge_agreed") is None

    def test_still_doing_it_is_not_an_answer(self, call):
        """`is_answer=false` nėra „nesupratau": klientas dar daro arba klausia atgal."""
        state, rt = self._at_the_offer(call)
        state.case.step_said = state.case.step
        case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Einu pasižiūrėti, ar tas kompiuteris veikia."
        state.turn.perception = {"step": {"label": "yes", "is_answer": False, "confidence": 0.9}}

        case_rule.plan(state, rt)

        assert state.case.facts.get("bridge_agreed") is None

    def test_an_unclear_label_is_never_forced(self, call):
        state, rt = self._at_the_offer(call)
        state.case.step_said = state.case.step
        case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "O kada meistras galėtų atvykti?"
        state.turn.perception = {
            "step": {"label": "unclear", "is_answer": False, "confidence": 0.9}
        }

        case_rule.plan(state, rt)

        assert state.case.facts.get("bridge_agreed") is None


# --- 2 sluoksnis: kai niekas nesuprato, tai MATOMA -----------------------------------------


class TestWhatNobodyUnderstoodIsVisible:
    def test_reader_silent_names_the_module_the_detector_and_the_words(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "device_seen": False})
        record_client(state, rt, "reachable", "yes")
        record_client(state, rt, "lights", "off")
        record_client(state, rt, "power_cable", "plugged")
        state.case.fault, state.case.solution = "no_mac_observed", 0
        steps = catalog.card("no_mac_observed").solution[0].steps
        state.case.step = next(i for i, s in enumerate(steps) if s.module == "offer_bridge")
        state.case.step_said = state.case.step
        case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Mmm, o kiek tai kainuos?"

        case_rule.plan(state, rt)

        silent = rt.tracer.of("reader_silent")
        assert silent, "neperskaitytas atsakymas turi likti trace'e"
        assert silent[-1]["module"] == "offer_bridge"
        assert silent[-1]["detector"] == "bridge_consent"
        assert silent[-1]["fact"] == "bridge_agreed"
        assert "kainuos" in silent[-1]["heard"]


# --- from test_live_1012.py ---


@pytest.mark.parametrize(
    ("said", "has"),
    [
        ("Routerį neturiu, bet kompiuterį turiu.", "yes"),  # A1: the call that lost its bridge
        ("Kompiuterį turiu, routerio neturiu", "yes"),
        ("Neturiu kito routerio, tik kompiuterį", "yes"),
        ("Ne, tik tiską telefoną. Neturiu kompiuterį.", "no"),
        ("Neturiu kompiuterio, tik telefoną", "no"),
        ("Neniauturiu kompiuterio", "no"),  # STT of „ne, neturiu"
    ],
)
def test_a1_the_computer_is_read_by_clause(said, has):
    from agent.evidence import extract_client_facts

    assert extract_client_facts(said).get("has_computer") == has


class TestA2PlugDoneWords:
    @pytest.fixture
    def plugging(self, make_state, make_runtime):
        from agent.decide.rules import case_rule
        from agent.ledger import record_client, record_telemetry

        from tests.diagnosis.test_case_rule import said
        from tests.diagnosis.test_facts import BASE

        state, rt = make_state("+37060020112"), make_runtime()
        state.identity.customer_id = "CUST112"
        record_telemetry(state, rt, {**BASE, "device_seen": False})
        record_client(state, rt, "reachable", "yes")
        state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
        case_rule.plan(state, rt)
        said(state, rt, "lights", "off")
        case_rule.plan(state, rt)
        said(state, rt, "power_cable", "unplugged")
        assert case_rule.plan(state, rt).rule == "case.plug_power"
        state.case.step_said = state.case.step
        return state, rt

    @pytest.mark.parametrize("heard", ["Ikišau.", "ikisau", "Įkišau"])
    def test_the_letters_asr_drops_do_not_hide_the_done(self, plugging, heard):
        from agent.decide.rules import case_rule

        state, rt = plugging
        state.dialog.turn_count += 1
        state.dialog.last_heard = heard
        plan = case_rule.plan(state, rt)

        assert plan.rule != "case.confirm"
        assert case_rule._current(state).module == "verify"

    def test_the_confirm_asks_about_the_action_only(self):
        from agent.contract.locale import phrase

        assert phrase("case.confirm.done_plug_power") == "Ar jau įkišote maitinimo laidą?"


@pytest.fixture
def dead_router(make_state, make_runtime):
    from agent.decide.rules import case_rule
    from agent.ledger import record_client, record_telemetry

    tracer = _Tracer()
    state, rt = make_state("+37060020112"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST112"
    record_telemetry(state, rt, {**BASE, "device_seen": False})
    record_client(state, rt, "reachable", "yes")
    state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
    assert case_rule.plan(state, rt).rule == "case.check_lights"
    state.case.step_said = state.case.step
    _hear(state, "Nedega nė viena")
    record_client(state, rt, "lights", "off")
    plan = case_rule.plan(state, rt)
    assert plan.rule == "case.check_power"
    state.case.step_said = state.case.step
    return state, rt, tracer


# --- from test_live_call_1014b.py ---


def test_an_answer_with_palaukite_is_an_answer(dead_router):
    """„Tuoje palaukite, tvirtai įkištas" — the offer is said, not swallowed by the wait."""
    from agent.decide.rules import case_rule
    from agent.ledger import record_client
    from agent.perceive.detectors import INTENT_ANSWER, INTENT_IN_PROGRESS
    from agent.perceive.node import _answer_beats_wait

    state, rt, _ = dead_router
    _hear(state, "Tuoje palaukite, tvirtai įkištas.")
    state.dialog.last_intent = INTENT_IN_PROGRESS
    awaited = state.case.awaiting
    record_client(state, rt, "power_cable", "plugged")
    _answer_beats_wait(state, rt, awaited, False)
    assert state.dialog.last_intent == INTENT_ANSWER

    plan = case_rule.plan(state, rt)
    assert plan.rule == "case.offer_bridge"
    assert "perduosime meistrui" in plan.say.text and "kompiuter" in plan.say.text


def test_a_new_step_is_never_swallowed_by_the_wait(dead_router):
    from agent.decide.rules import case_rule
    from agent.ledger import record_client
    from agent.perceive.detectors import INTENT_IN_PROGRESS
    from agent.speak.context_card import _case_step

    state, rt, _ = dead_router
    record_client(state, rt, "power_cable", "plugged")
    plan = case_rule.plan(state, rt)
    state.turn.plan = plan.model_dump() if hasattr(plan, "model_dump") else plan.__dict__
    state.dialog.last_intent = INTENT_IN_PROGRESS
    state.dialog.awaiting = "power_cable"
    lines = _case_step(state, rt)
    assert not any("THE STEP WAITS" in line for line in lines)


@pytest.mark.parametrize("said", ["Mhm.", "Aha", "mhm"])
def test_a_backchannel_is_not_consent(said):
    from agent.perceive.detectors import detect_bridge_consent

    assert detect_bridge_consent(said) is None


def test_no_computer_mid_step_skips_the_bridge(dead_router):
    from agent.decide.rules import case_rule
    from agent.ledger import record_client

    state, rt, tracer = dead_router
    record_client(state, rt, "power_cable", "plugged")
    case_rule.plan(state, rt)  # the offer
    state.case.step_said = state.case.step
    record_client(state, rt, "bridge_agreed", "yes")
    plan = case_rule.plan(state, rt)
    assert plan.rule == "case.connect_direct"
    state.case.step_said = state.case.step
    _hear(state, "Aš neturiu kompiuterio, tik telefoną naudoju.")
    record_client(state, rt, "has_computer", "no")
    plan = case_rule.plan(state, rt)

    assert plan.rule != "case.connect_direct" and plan.rule != "case.confirm"
    assert "no_longer_applies" in tracer.moves()
    assert "connect_direct" not in state.case.worked  # the summary must not say it was done


def test_a_no_is_never_a_done_report():
    from agent.perceive.detectors import detect_yes_no
    from agent.resolution import Outcome

    assert detect_yes_no("Ne, ne įkišau, nes neturiu kompiuterį.") is Outcome.NO


class _Tracer_wave10_quick:
    session_id = "wave10"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def case_call(make_state, make_runtime):
    """A v2 Case call on a fault, the caller identified."""
    state, rt = make_state("+37060012353"), make_runtime(tracer=_Tracer_wave10_quick())
    state.identity.customer_id = "CUST009"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    state.case.fault, state.case.solution = "no_mac_observed", 0
    return state, rt


# --- from test_wave10_quick.py ---


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


# --- from test_identify_first.py ---


def test_garbled_speech_is_not_a_no():
    from agent.evidence import polarity, read_pending_answer

    assert read_pending_answer("lights", "Gekine matone") is None
    assert polarity("Gekine matone") is None
    assert read_pending_answer("lights", "Ne, nedega") == "off"
    assert read_pending_answer("lights", "ne dega") == "off"


# --- from test_fault_packs.py ---


class TestVoiceTestFixes:
    """2026-08-13 live-call fixes: polarity, early facts, phase gating, glosses."""

    def test_negated_demand_is_not_a_demand(self):
        from agent.perceive.detectors import detect_refuse_or_ticket

        assert detect_refuse_or_ticket("Neregistruokite, pajunkim kompiuterį") != "demand"
        assert detect_refuse_or_ticket("užregistruokit gedimą") == "demand"

    def test_demand_with_stop_words_keeps_the_dialogue(self):
        from types import SimpleNamespace

        from agent.decide.rules.ticket import wants_to_keep_solving

        # live phrase: negated solving verbs + explicit demand -> NOT keep-solving
        assert (
            wants_to_keep_solving(
                None,
                None,
                "Nebe noriu tikrinti toliau, užregistruokit gedimą ir nebesprendžiam",
            )
            is False
        )
        assert wants_to_keep_solving(None, None, "Ne, pajunkim tą kompiuterį") is True

    def test_aciu_nereikia_is_a_farewell(self):
        from agent.perceive.detectors import detect_farewell

        assert detect_farewell("Ačiū, nereikia") is True
        assert detect_farewell("Nebereikia.") is True
        assert detect_farewell("Ačiū") is False

    def test_the_call_so_far_seeds_the_ledger_on_activation(self, monkeypatch):
        from types import SimpleNamespace

        from agent.execute.diagnosis import _seed_evidence_from_call

        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    intake=IntakeState(anamnesis_raw="Ką kečiau, routere?"),
                    diagnosis=DiagnosisState(evidence={}),
                    dialog=DialogState(turn_count=1),
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        _seed_evidence_from_call(engine.state, engine.runtime)
        assert engine.state.diagnosis.evidence.get("changed_device", {}).get("value") == "yes"

    def test_the_opening_sentence_seeds_too(self, monkeypatch):
        """F-11: a fact stated in the very first sentence must not be re-asked once the
        pack activates ("neveikia visuose įrenginiuose" -> "visuose ar tik viename?")."""
        from types import SimpleNamespace

        from agent.execute.diagnosis import _seed_evidence_from_call

        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    intake=IntakeState(
                        heard_utterances=["Neveikia internetas visuose įrenginiuose"]
                    ),
                    diagnosis=DiagnosisState(evidence={}),
                    dialog=DialogState(turn_count=1),
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        _seed_evidence_from_call(engine.state, engine.runtime)
        assert engine.state.diagnosis.evidence.get("fail_scope", {}).get("value") == "all"

    def test_pack_glosses_replace_raw_keys(self):
        from agent.evidence import gloss_label, gloss_value

        assert gloss_label("changed_device") == "routerio keitimas"
        assert gloss_value("yes", "changed_device") == "keitė arba prijungė naują įrenginį"
        assert gloss_label("lights") == "routerio lemputės"  # built-ins keep working


class TestDetourResilience:
    """Live 2026-08-20: a bare 'Ne.' read as farewell derailed the recap ->
    findings chain and the agent re-ran diagnostics it already had."""

    def test_bare_ne_is_never_a_farewell(self):
        from agent.perceive.detectors import detect_farewell

        assert detect_farewell("Ne.") is False
        assert detect_farewell("Ne") is False
        assert detect_farewell("Ne, ačiū") is True  # real closer kept
        assert detect_farewell("Viso gero") is True

    def test_split_ne_symptom_polarity(self):
        from agent.perceive.nlu import extract_symptoms

        assert extract_symptoms("Ne 1 lemputė ne dega.").get("lights") == "off"
        assert extract_symptoms("lemputės nedega").get("lights") == "off"

    def test_resync_note_renders_once(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST009"
        from agent.evidence import CLIENT, set_fact

        set_fact(agent.state.diagnosis.evidence, "lights", "off", CLIENT, 1)
        agent.state.dialog.resync_note = True
        block = context_card(agent.state, agent.runtime)
        assert "BACK TO SOLVING" in block and "established" in block
        assert "GRĮŽTAME" not in (context_card(agent.state, agent.runtime) or "")  # consumed

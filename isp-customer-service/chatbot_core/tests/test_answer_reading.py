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
from agent.contract import cards as catalog
from agent.decide.rules import case_rule
from agent.ledger import record_client, record_telemetry
from agent.modules import read_answer

from tests.test_facts import BASE


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

    def test_a_confident_reading_settles_the_step(self, call):
        state, rt = self._at_the_offer(call)
        state.case.step_said = state.case.step
        case_rule.plan(state, rt)  # pastato `awaiting`
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Mmm, o kiek tai kainuos?"  # žodynas to neskaito
        state.turn.perception = {
            "step": {"label": "no", "is_answer": True, "confidence": 0.9},
        }

        case_rule.plan(state, rt)

        assert state.case.facts.get("bridge_agreed") == "no"
        assert state.turn.confirm_reading is None  # tikras — nereikia tikslintis
        assert any(e.get("move") == "read_by_model" for e in rt.tracer.of("case"))

    def test_a_middling_reading_is_taken_but_said_out_loud(self, call):
        state, rt = self._at_the_offer(call)
        state.case.step_said = state.case.step
        case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Mano anūkas tuo užsiima, jo šiandien nėra."
        state.turn.perception = {"step": {"label": "no", "is_answer": True, "confidence": 0.6}}

        case_rule.plan(state, rt)

        assert state.case.facts.get("bridge_agreed") == "no"
        assert state.turn.confirm_reading, "vidutinį supratimą pasakom pakeliui"

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

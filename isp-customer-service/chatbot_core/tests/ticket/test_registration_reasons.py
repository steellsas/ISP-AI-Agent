"""Registration only for a written-down reason, decided by the engine (Andrius, 2026-10-13).

`knowledge/registracija.yaml` is the one list of WHEN a ticket is registered. The engine starts
a registration through `request_ticket(state, rt, <reason>)` (or `registration.mark` for one that
skips the contact dialogue) and nothing else — a model's word never does.
"""

import re
from pathlib import Path

import pytest

FUNCTION = "Registracijos priežastys"


F = "Taip, galiu."
# The path through the call → the reason written on the ticket (knowledge/registracija.yaml).
PATHS = [
    pytest.param(
        "no_mac_observed",
        [
            "Gerai",
            F,
            F,
            "Nedega nė viena",
            "Maitinimo laidas įkištas tvirtai.",
            "Neturiu kompiuterio.",
            "Taip",  # the conclusion is said; the next turn registers
        ],
        "telefonu_nepataisoma",
        id="miręs routeris → telefonu nepataisoma",
    ),
    pytest.param(
        "link_down_local",
        ["Gerai", F, F, "Dega žalia", "Perkišau laidą", "Neveikia"],
        "sprendimas_baigtas",
        id="linija neaktyvi, perkišta → sprendimas baigtas",
    ),
    pytest.param(
        "crc_errors",
        ["Gerai", F, F, "Patikrinau, laidas sveikas, tvirtai įkištas", "Neveikia"],
        "sprendimas_baigtas",
        id="klaidos linijoje → sprendimas baigtas",
    ),
    pytest.param(
        "switch_unreachable",
        ["Gerai"],
        "musu_tinklo_gedimas",
        id="mazgas nepasiekiamas → mūsų tinklo gedimas",
    ),
    pytest.param(
        "no_mac_observed",
        ["Gerai", F, F, "Registruokite meistrą"],
        "klientas_praso",
        id="registruokite meistrą → klientas prašo",
    ),
    pytest.param(
        "router_hung",
        ["Gerai", F, "Ne, nesu namie", "Nežinau, gal negalėsiu"],
        "klientas_negali",
        id="nesu namie, nežinau kada → klientas negali",
    ),
    pytest.param(
        "router_hung",
        [
            "Gerai",
            "Taip, galiu prieiti",
            "Taip, galiu prieiti",
            "Perkroviau",
            "Taip, veikia",
            "Ne, palaukite, vis tiek neveikia",
        ],
        "vel_neveikia",
        id="po „veikia“ vėl neveikia",
    ),
    pytest.param(
        "dhcp_silent",
        ["Gerai", "Turiu telefoną.", "Turiu telefoną.", "Ne, geriau meistrą", "Taip"],
        "klientas_nenori",
        id="atsisako vedimo → klientas nenori",
        marks=pytest.mark.xfail(
            strict=True, reason="įrašoma „sprendimas_baigtas“, nors klientas atsisakė tęsti"
        ),
    ),
]


@pytest.mark.parametrize(("card", "turns", "reason"), PATHS)
def test_the_reason_follows_the_call(diagnosing, card, turns, reason):
    """Registracijos priežastis atitinka skambučio eigą"""
    c = diagnosing(card)
    for text in turns:
        c.say(text)
    assert c.state.ticket.reason == reason


def _phoned(*turns):
    """A whole call from +37060020112 (this module's own `call` fixture is another one)."""
    from tests.phases import CallDriver

    c = CallDriver("+37060020112")
    try:
        for text in turns:
            c.say(text)
    finally:
        c.close()
    return c


def test_a_request_from_the_start_is_not_ours_to_answer(db_connection):
    """Sąskaitos klausimas → atsakingam žmogui"""
    c = _phoned("Skambinu dėl sąskaitos", "Taip", "Paulius")
    assert (
        c.state.ticket.reason == "ne_musu_klausimas"
        and c.state.ticket.request_type == "billing_request"
    )


def test_a_slow_line_without_a_card_is_an_unclear_fault(db_connection):
    """Lėtas internetas be kortelės → neaiškus gedimas"""
    c = _phoned("Internetas labai lėtas", "Taip", "Paulius")
    assert c.state.ticket.reason == "neaiskus_gedimas"


def test_a_hang_up_after_the_decision_registers_anyway(diagnosing):
    """Padėjo ragelį po sprendimo → tiketas vis tiek registruojamas"""
    c = diagnosing("no_mac_observed")
    for text in [
        "Gerai",
        F,
        F,
        "Nedega nė viena",
        "Maitinimo laidas įkištas tvirtai.",
        "Neturiu kompiuterio.",
    ]:
        c.say(text)
    c.session.end_session()
    assert c.state.ticket.reason == "padejo_rageli" and c.state.ticket.ticket_id
    assert c.state.closing.closed_reason == "registered"


@pytest.mark.xfail(
    strict=True, reason="„nenoriu…, atsiųskite meistrą“ skaitoma kaip noras baigti pokalbį"
)
def test_asking_for_a_technician_is_not_a_goodbye(diagnosing):
    """„Atsiųskite meistrą“ — prašymas, ne atsisveikinimas"""
    c = diagnosing("no_mac_observed")
    for text in ["Gerai", F, F, "Nenoriu nieko daryti, atsiųskite meistrą"]:
        c.say(text)
    assert c.rule != "dialog.confirm_end"


SRC = Path(__file__).resolve().parents[2] / "src" / "agent"


_CALL = re.compile(r"""(?:request_ticket\([^)]*?|mark\(\s*\w+\s*,)\s*["']([a-z_]+)["']""")


def _reasons_in_code() -> set[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        found |= set(_CALL.findall(path.read_text(encoding="utf-8")))
    for path in SRC.rglob("case_rule.py"):
        text = path.read_text(encoding="utf-8")
        found |= set(re.findall(r'_escalate\([^)]*?why="([a-z_]+)"', text, re.S))
    return found


def test_every_reason_in_the_code_is_written_down():
    from agent.contract.registration import reasons

    used = _reasons_in_code()
    assert used, "the scan found no registration at all"
    assert used <= set(reasons()), f"not in registracija.yaml: {used - set(reasons())}"


def test_every_reason_says_when_and_why():
    from agent.contract.registration import reasons

    for key, spec in reasons().items():
        assert spec.get("kada") and spec.get("tiketui"), key
        assert spec.get("sutikimas") in ("taip", "ne"), key


def test_an_unknown_reason_is_refused(make_state, make_runtime):
    from agent.contract.schema import KnowledgeError
    from agent.execute.ticket import request_ticket

    state, rt = make_state("+37060012353"), make_runtime()
    with pytest.raises(KnowledgeError):
        request_ticket(state, rt, "promise")  # the model's word is not a reason


def test_the_reason_goes_onto_the_ticket(make_state, make_runtime):
    from agent.executor_flow import register_ticket_from_state

    from tests.calls import make_runtime as runtime_with

    created = []

    def tools(name, args):
        if name == "create_ticket":
            created.append(args)
            return {"success": True, "ticket_id": "T"}
        return {}

    state = make_state("+37060012353")
    rt = runtime_with(fake_tools=tools)
    state.identity.customer_id = "CUST009"
    state.case.fault = "no_mac_observed"
    state.ticket.reason = "telefonu_nepataisoma"
    register_ticket_from_state(state, rt)

    assert (
        "Registruota, nes: gedimo telefonu pašalinti negalima."
        in (created[0]["problem_description"])
    )


def test_the_card_offers_no_registration():
    """The dialogue lines used to tell the model to „offer to register the fault" — a decision
    the engine had not made."""
    card = (SRC / "speak" / "context_card.py").read_text(encoding="utf-8")
    for offer in (
        "or offer to register the fault",
        "register the problem for a call-back",
        "you will register a technician",
    ):
        assert offer not in card, offer
    assert card.count("Promise no registration") >= 2  # what the lines say instead


def _sources():
    for path in SRC.rglob("*.py"):
        yield path, path.read_text(encoding="utf-8")


class _Tracer:
    session_id = "3b"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def call(make_state, make_runtime):
    tracer = _Tracer()
    state, rt = make_state("+37060012353"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST009"
    return state, rt, tracer


# --- from test_v3_stage3b.py ---


def test_the_contact_dialogue_starts_only_through_request_ticket():
    callers = [
        f"{path.relative_to(SRC)}:{n}"
        for path, text in _sources()
        for n, line in enumerate(text.splitlines(), 1)
        if "_begin_ticket_dialogue(" in line
        and "def _begin_ticket_dialogue" not in line
        and path.relative_to(SRC).as_posix() != "execute/ticket.py"
    ]
    assert callers == []


def test_a_fault_ticket_carries_its_card_note_and_its_reason(call):
    from agent.execute.ticket import request_ticket

    state, rt, tracer = call
    state.case.fault, state.case.solution = "no_mac_observed", 0
    request_ticket(state, rt, "sprendimas_baigtas")

    assert state.ticket.stage == "phone"
    assert state.case.facts.get("_ticket_note")  # the card's note for the technician
    asked = [e for e in tracer.events if e.get("intent") == "ticket_requested"]
    assert asked and asked[0]["action"] == "sprendimas_baigtas"


def test_a_request_is_typed_and_a_running_one_is_not_restarted(call):
    from agent.execute.ticket import request_ticket

    state, rt, tracer = call
    request_ticket(state, rt, "ne_musu_klausimas", request_type="billing_request")
    request_ticket(state, rt, "klientas_praso")  # already collecting — nothing changes

    assert state.ticket.request_type == "billing_request"
    assert len([e for e in tracer.events if e.get("intent") == "ticket_requested"]) == 1


class _Tracer_wave9_promises:
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
    tracer = _Tracer_wave9_promises()
    state, rt = make_state("+37060012353"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST009"
    state.identity.caller_name = "Andrius"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    state.case.fault, state.case.solution = "no_mac_observed", 0
    return state, rt, tracer


# --- from test_wave9_promises.py ---


class TestT3AWordNeverStartsARegistration:
    """Wave 9 T3 turned a model's „užregistruosiu" INTO the contact dialogue. Since 2026-10-13
    (Andrius: the engine decides, the model only says it) no word starts a registration: a
    promise the engine has not decided is not spoken, a decided one is, and the registration is
    started by the engine's own rule (the Case's summary is followed by the contact dialogue)."""

    CLAIM = "Dėl routerio geriausiai atsakys atsakingas žmogus — užregistruosiu jūsų klausimą."

    def test_the_claim_guard_is_gone(self):
        from agent.execute import ticket

        assert not hasattr(ticket, "registration_claim_guard")

    def test_a_summed_up_case_registers_through_the_engine(self, dead_router):
        from agent.decide.rules import case_rule

        state, rt, _ = dead_router
        state.case.summarised = True
        state.case.step = len(case_rule._solution_steps(state))  # nothing left but the ticket

        case_rule.plan(state, rt)

        assert state.ticket.stage == "phone"
        assert state.ticket.reason in ("sprendimas_baigtas", "telefonu_nepataisoma")

    def test_the_finished_reply_adds_nothing(self, dead_router):
        from agent.speak.postprocess import finish

        state, rt, _ = dead_router
        reply, extra = finish(state, rt, self.CLAIM)

        assert extra == "" and state.ticket.stage is None

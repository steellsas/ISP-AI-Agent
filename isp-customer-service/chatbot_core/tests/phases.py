"""A whole call for tests, and calls that START in a given phase (ROADMAP 3.2).

`CallDriver` runs the real graph (perceive → decide → execute → narrate) over the seeded test
DB. Only the speaking LLM is replaced: where the engine hands the words to the model the reply
is `LLM_REPLY`, so a test checks what the ENGINE decided (rules, state, tools) and the engine's
own scripted phrases word for word. Wording by the model is the eval's job (real LLM).

Phase fixtures build the state a phase starts from WITHOUT running the phases before it: a
diagnosis test begins with `identified_call(...)`, so a broken identification fails only the
identification tests, not every test after it. The commit uses the engine's own routine
(`engine_resolve_from_slots`), the same one a "taip" to the address runs.

    def test_x(call):                      # tests/conftest.py fixture
        c = call("+37060020112")
        c.say("Laba diena, neveikia internetas")
        assert c.rule == "identification.address_move"

    def test_y(identified):                # starts identified
        c = identified("CUST105")
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

LLM_REPLY = "‹LLM›"

# The seeded customers a phase fixture can start from: the address a caller would say.
CUSTOMERS: dict[str, dict[str, str]] = {
    "CUST105": {"street": "Tilžės g.", "house": "60", "apartment": "7", "phone": "+37060020105"},
    "CUST101": {"street": "Tilžės g.", "house": "60", "apartment": "3", "phone": "+37060020101"},
    "CUST112": {"street": "Vilniaus g.", "house": "33", "apartment": "2", "phone": "+37060020112"},
    "CUST009": {"street": "Vilniaus g.", "house": "29", "phone": "+37060012353"},
    "CUST104": {
        "street": "S. Dariaus ir S. Girėno g.",
        "house": "25",
        "apartment": "45",
        "phone": "+37060020104",
    },
    "CUST109": {
        "street": "Žeimių g.",
        "house": "12",
        "apartment": "6",
        "city": "Ginkūnai",
        "phone": "+37060020109",
    },
    "CUST110": {"street": "Aušros g.", "house": "8", "city": "Bubiai", "phone": "+37060020110"},
    # one per diagnosis card (tests/diagnosis): the line each one's telemetry shows
    "CUST001": {"street": "Tilžės g.", "house": "12", "apartment": "5", "phone": "+37060012345"},
    "CUST007": {"street": "Dainų g.", "house": "9", "phone": "+37060012351"},
    "CUST102": {"street": "Dainų g.", "house": "5", "apartment": "5", "phone": "+37060020102"},
    "CUST103": {"street": "Žemaitės g.", "house": "14", "apartment": "2", "phone": "+37060020103"},
    "CUST106": {"street": "Vilniaus g.", "house": "31", "apartment": "2", "phone": "+37060020106"},
    "CUST305": {"street": "Tilžės g.", "house": "62", "phone": "+37060030305"},
    "CUST306": {"street": "Vilties g.", "house": "17", "apartment": "2", "phone": "+37060030306"},
}

# The demo customer whose line shows each card (the seeded network data).
CARD_CUSTOMER = {
    "router_hung": "CUST112",
    "no_mac_observed": "CUST001",
    "foreign_mac": "CUST105",
    "link_down_local": "CUST104",
    "dhcp_silent": "CUST106",
    "crc_errors": "CUST305",
    "healthy_to_router": "CUST109",
    "billing_suspended": "CUST101",
    "active_outage": "CUST102",
    "switch_unreachable": "CUST103",
    "node_fault_unregistered": "CUST306",
}


class CaptureTracer:
    """Keeps every trace event in memory (no file)."""

    def __init__(self, session_id: str = "test-call"):
        self.session_id = session_id
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, **fields: Any) -> None:
        self.events.append({"type": event_type, **fields})


class CallDriver:
    """One call through the real graph; the speaking LLM answers `LLM_REPLY`."""

    def __init__(self, phone: str = "unknown", greet: bool = True):
        from agent.session import AgentSession

        self._next_llm: str | None = None
        self._patches = [
            patch("agent.speak.node.stream_tool_completion", side_effect=self._speaker),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ]
        for p in self._patches:
            p.start()
        self.tracer = CaptureTracer()
        self.session = AgentSession(caller_phone=phone, tracer=self.tracer)
        self.replies: list[str] = []
        if greet:
            self.replies.append(self.session.greeting())

    def _speaker(self, **_kwargs):
        text = self._next_llm or LLM_REPLY

        def _gen():
            yield text
            return SimpleNamespace(content=text, tool_calls=None)

        return _gen()

    def say(self, text: str, llm: str | None = None) -> str:
        """One caller turn; the agent's reply (`LLM_REPLY` where the model would word it).
        `llm` = what the model says this turn, when the next step depends on the question
        it asked (the engine reads its own last question back)."""
        self._next_llm = llm
        reply = self.session.handle_turn(text)
        self._next_llm = None
        self.replies.append(reply)
        return reply

    def close(self) -> None:
        for p in self._patches:
            p.stop()

    # --- what a test reads -------------------------------------------------
    @property
    def state(self):
        return self.session.state

    @property
    def identity(self):
        return self.session.state.identity

    def of(self, event_type: str) -> list[dict[str, Any]]:
        return [e for e in self.tracer.events if e["type"] == event_type]

    @property
    def rules(self) -> list[str]:
        """Every turn's planning rule, in order (the greeting is the first)."""
        return [e["rule"] for e in self.of("turn_plan")]

    @property
    def rule(self) -> str | None:
        return (self.rules or [None])[-1]

    @property
    def tools(self) -> list[str]:
        return [e["name"] for e in self.of("tool_call")]

    @property
    def llm_cards(self) -> list[str]:
        """The context cards the speaking LLM was given (DEBUG_LLM=full in tests)."""
        return [e.get("card") or "" for e in self.of("llm_input")]

    def heard_everything(self) -> str:
        """All the agent said and all the model was told — for "never said X" checks."""
        return "\n".join(self.replies + self.llm_cards)

    # --- phase starts -------------------------------------------------------
    def identify(
        self, customer_id: str, caller_name: str | None = "Tomas", problem: str = "internet_down"
    ):
        """Commit the customer the way the engine does after a „taip" to the address —
        without the identification dialogue."""
        from agent.decide.rules.identification import engine_resolve_from_slots
        from agent.slots import SlotStatus

        addr = CUSTOMERS[customer_id]

        def write(state, rt):
            state.intake.problem_type = state.intake.problem_type or problem
            p = state.identity.profile
            p.street.propose(addr["street"], 1.0, SlotStatus.HEARD)
            p.house.propose(addr["house"], 1.0, SlotStatus.HEARD)
            if addr.get("apartment"):
                p.apartment.propose(addr["apartment"], 1.0, SlotStatus.HEARD)
            if addr.get("city"):
                p.city.propose(addr["city"], 1.0, SlotStatus.HEARD)
            assert engine_resolve_from_slots(state, rt), f"{customer_id} did not resolve"
            state.identity.address_confirmed = True
            if caller_name:
                state.identity.caller_name = caller_name
                state.identity.caller_relation = "holder"
                # The findings go out on the next turn, as after a real name answer.
                state.identity.result_pending = True

        self.session._write_between_turns(write)
        assert self.identity.customer_id == customer_id
        return self


def identified_call(
    customer_id: str,
    caller_name: str | None = "Tomas",
    phone: str | None = None,
    problem: str = "internet_down",
) -> CallDriver:
    """A call that starts AFTER identification: the customer committed and confirmed, the
    caller named, the problem known. Called from its own phone number by default."""
    driver = CallDriver(phone or CUSTOMERS[customer_id]["phone"])
    return driver.identify(customer_id, caller_name=caller_name, problem=problem)

"""
Agent State Management.

Contains the state dataclass that tracks conversation progress.
"""

from dataclasses import dataclass, field
from typing import Any

from .slots import ClientProfileState


@dataclass
class AgentState:
    """
    Agent conversation state.

    Tracks all information gathered during a customer support call.
    """

    # Call identification
    caller_phone: str

    # Conversation history (for LLM context). NOT dict[str, str]: assistant
    # tool-call messages carry a `tool_calls` LIST and tool results ride along
    # too — the too-narrow annotation, mirrored into GraphState, made pydantic
    # reject the whole state at the next graph turn after any LLM tool round
    # (live 2026-08-13: every turn after an address tool round died silently).
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Structured address slots (Phase 3.5) — durable, typed identification memory
    # populated from resolve_address. Additive: the existing customer_* /
    # address_confirmed fields below still drive current behaviour; the slots are
    # the foundation the policy/NLU steps build on.
    profile: ClientProfileState = field(default_factory=ClientProfileState)

    # Customer information (populated after find_customer)
    customer_id: str | None = None
    customer_name: str | None = None  # Name from CRM (the ACCOUNT holder)
    customer_address: str | None = None

    # Who is actually ON THE PHONE — captured only for the call record / history, NEVER
    # compared to the account name (we serve the holder AND family / tenants / a helper, so
    # a mismatch is expected). The address is the identity anchor, not this. Set when the
    # `name` extra question is enabled (identification.yaml); consumed by the call record
    # (Phase 3.10).
    caller_name: str | None = None
    # Relation to the contract, keyword-read from the caller's intro ("holder" /
    # "family" / "tenant" / "helper" / "unknown"). Record + confidence signal only —
    # NEVER a gate (5d rule: a mismatch is expected and fine).
    caller_relation: str | None = None

    # Pre-flight phone lookup result (the caller's number, resolved at the start
    # of the call). UNCONFIRMED — a candidate the agent offers for the caller to
    # confirm, NOT a confirmed identity. {customer_id, name, address} or None.
    phone_candidate: dict[str, Any] | None = None
    # Whether the pre-flight phone lookup has run (so "no candidate" can be told
    # apart from "lookup not done yet" — the agent only states "no account on
    # file" once we have actually checked).
    preflight_done: bool = False
    # Proactive mass-outage awareness: if the caller's number is on a street with
    # an active outage, the pre-flight stores {street, eta, description} here so
    # the agent can inform immediately ("Ar dėl <street>? Ten avarija…") instead
    # of running full identification. Only the STREET is revealed (PII-safe), and
    # as a question, not an identity claim. None = no known outage for the caller.
    preflight_outage: dict[str, Any] | None = None

    # Caller information (populated after customer confirms)
    address_confirmed: bool = False

    # Active resolution strategy (agent/resolution.py): {"verdict", "step"} once a
    # diagnose verdict maps to a strategy, so the engine can walk its steps
    # deterministically (the model cannot skip). None = generic inform/instruct.
    resolution: dict[str, Any] | None = None

    # Tool observations
    observations: list[str] = field(default_factory=list)

    # Raw utterance buffer — everything the caller said, verbatim (noise already
    # filtered upstream). VAD/STT can split one spoken address into short garbled
    # fragments ("šešiasdešimt" -> "šešias dešimt"); no single fragment parses,
    # but the WHOLE buffer lets the LLM reconcile the address (esp. numbers) when
    # the deterministic slots stall. Also the seam for later async silent
    # re-processing. Keeps ALL info (address + problem + symptoms), never dropped.
    heard_utterances: list[str] = field(default_factory=list)

    # Problem tracking
    problem_type: str | None = None  # internet, tv, phone, billing
    # A (2026-08-21): the PRIMARY goal never flips mid-call; later mentions of
    # OTHER problems land here — asked about at the end, listed on the ticket.
    secondary_problems: list = field(default_factory=list)
    problem_description: str | None = None
    # Intake anamnesis (identification block, 2026-07-31): the ONE history question
    # ("kada pastebėjote, po ko dingo?") is asked once, engine-scripted; the caller's
    # raw answer is kept for the ANALYSIS (Step 2) and the call record.
    anamnesis_asked: bool = False
    anamnesis_raw: str | None = None
    # Keyword-read from the raw answer (nlu.extract_anamnesis): when it broke and an
    # optional trigger event — the caller's half of the ANALYSIS (Step 2).
    anamnesis_when: str | None = None
    anamnesis_trigger: str | None = None

    # Ticket-confirmation dialogue (2026-08-04): collected right before EVERY
    # registration — the contact number is ALWAYS asked (never assumed from
    # caller-ID/DB), plus when it is convenient to call. Ride on the ticket.
    contact_phone: str | None = None
    contact_hours: str | None = None

    # Diagnostic findings (case state), namespaced BY DOMAIN so new fault families
    # (iptv, voip…) attach additively without touching the base flow:
    #   {"network": {group, side, action, reason, signals}}
    # Kept so the agent reconciles findings with what the customer says and never
    # loses / re-runs them. The container is extensible; we only populate domains
    # that actually exist (today: "network").
    diagnosis: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Symptoms the customer reported (case state) — deterministically extracted
    # categoricals: {lights, connection, devices, frequency, services}. Revisable;
    # feeds the agent's questioning + the eventual diagnosis. Free-form symptoms
    # (exact "when did it start") are left to the LLM / a future SLM (§12.7).
    symptoms: dict[str, str] = field(default_factory=dict)

    # Case closing (END state, Phase 3.5). case_closed flips the router to the
    # tools-less `closing` node — set ONLY by the close_case tool (model-driven, so
    # the model owns the "is the caller actually done?" judgement; never auto-set,
    # see the outage discussion). closed_reason tailors the goodbye.
    case_closed: bool = False
    closed_reason: str | None = None  # "resolved" | "outage" | "declined"
    # What we currently believe is wrong, and why. The verdict tree stays the SOURCE
    # (it decides); this mirrors it so the agent can narrate the whole arc — "manau X,
    # nes Y" -> "pasitvirtino / nepasitvirtino, nes Z". Evidence comes from telemetry,
    # not from parsing the caller.
    #   {"cause": str, "because": [str], "status": testing|confirmed|rejected,
    #    "settled_by": str | None}
    hypothesis: dict[str, Any] | None = None
    # Evidence ledger (Phase 4.5 Ledger v1): {key: {value, source, turn, history,
    # conflict}} — telemetry facts are ground truth, client facts fill what
    # telemetry cannot see; a contradicting client answer flags a conflict the
    # engine clarifies. See agent/evidence.py.
    evidence: dict[str, Any] = field(default_factory=dict)
    # Causes the telemetry has already disproved (a fix ran and did NOT restore the
    # line). The engine never re-tries these, so a failed fix leads to the NEXT likely
    # cause instead of straight to a ticket.
    failed_hypotheses: list[str] = field(default_factory=list)
    rejected_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    # Carries the just-rejected cause for ONE reply, so the agent says the rethink out
    # loud instead of silently restarting.
    pivoted_from: str | None = None
    # An active outage was reported for the caller's street. This does NOT close the
    # case (the caller still asks "when fixed? / compensation?") — it switches the
    # agent into a restricted mode: answer outage follow-ups, no more diagnosis.
    outage_reported: bool = False

    # Repeat-guard (Phase 3.5): stop the agent re-asking the same thing 2–4×.
    # stuck_count = consecutive question-turns that made NO progress (a slot/
    # customer_id/node change resets it); last_question is the previous question
    # asked, for verbatim-repeat detection. Drives a scaled nudge → deterministic
    # backstop (offer account code → register + close).
    last_question: str | None = None
    stuck_count: int = 0
    # What the caller actually said THIS turn ("" = silence / nothing usable). Lets
    # the agent say "nesupratau: girdžiu <...>" instead of a blanket "neišgirdau",
    # and never reflect words from an earlier turn as if they were just said.
    last_heard: str = ""
    # "standard" | "basic". Raised (and kept) for the rest of the call once the caller
    # signals they do not follow the technical wording — the agent then explains in
    # plain, visual words instead of repeating the same jargon at them.
    clarity_level: str = "standard"
    # What the engine is blocked on this turn, and for how many turns. Same shape for
    # a human wait and (later) a slow telemetry read, so Phase 5's async polling plugs
    # into `system_check` without reworking the walker.
    #   None | "client_answer" | "client_action" | "system_check"
    awaiting: str | None = None
    awaiting_turns: int = 0
    # How many times the caller has said they do not follow THIS step. Each time the
    # agent breaks the same instruction into a smaller piece instead of repeating it.
    # (clarity_level changes the WORDS; this changes the SIZE of the step.)
    step_confusions: int = 0
    # How the caller's last turn was classified (see resolution.detect_turn_intent).
    # Only "answer"/"done" may advance a step — everything else holds the walker.
    last_intent: str = ""

    # Conversation control
    is_complete: bool = False  # transport hangs up once True (final goodbye spoken)
    closing_turns: int = 0  # turns spent in the closing stage (cap to avoid loops)
    turn_count: int = 0
    max_turns: int = 20

    # Ticket info (if created)
    ticket_id: str | None = None
    # Ticket-confirmation dialogue stage (R3 promotion of engine._ticket_stage,
    # docs/ROADMAP_REFACTORING.md §6): None | "phone" | "hours" | "done" |
    # "cancelled". The engine's scripted ladder owns transitions; routers read it
    # (legacy route() via the engine property, v2 route_entry via GraphState) to
    # send mid-dialogue turns to the ticket node.
    ticket_stage: str | None = None

    def add_observation(self, observation: str):
        """Add tool observation to history."""
        self.observations.append(observation)

    def set_customer_info(self, customer_id: str, name: str = None, address: str = None):
        """Set customer information from CRM lookup."""
        self.customer_id = customer_id
        self.customer_name = name
        self.customer_address = address

    def confirm_address(self, caller_name: str = None):
        """Mark address as confirmed by caller."""
        self.address_confirmed = True
        if caller_name:
            self.caller_name = caller_name

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for serialization."""
        return {
            "caller_phone": self.caller_phone,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "customer_address": self.customer_address,
            "caller_name": self.caller_name,
            "address_confirmed": self.address_confirmed,
            "problem_type": self.problem_type,
            "secondary_problems": self.secondary_problems,
            "problem_description": self.problem_description,
            "is_complete": self.is_complete,
            "turn_count": self.turn_count,
            "ticket_id": self.ticket_id,
        }

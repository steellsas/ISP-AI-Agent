"""
Knowledge schema — pydantic models for every file in `agent/knowledge/` plus the
cross-reference checks a model alone cannot express (routing targets exist,
modules exist, answers match routing keys, playbook sections exist).

`validate_knowledge()` reads the files, validates them and raises one
KnowledgeError listing every problem as `file: path: message`. It changes no
behaviour: the runtime loaders still read the files themselves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictFloat,
    StrictInt,
    ValidationError,
    model_validator,
)

AGENT_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = AGENT_DIR / "knowledge"
PLAYBOOK_DIR = AGENT_DIR.parent / "rag" / "knowledge_base"

# Routing targets handled by the walker itself, not by a pack step.
TERMINAL_TARGETS = frozenset({"resolve", "callback", "end"})
# Condition tokens that are not `evidence_key=value`.
CONDITION_TOKENS = frozenset({"confirmed", "bridge_phase"})
# Detectors implemented in code (resolution.DETECTORS); detectors.yaml may add
# LLM-only ones.
CODE_DETECTORS = frozenset(
    {"yes_no", "restored", "reboot_check", "scope", "conn", "port", "lights", "have_device"}
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Fault packs and modules ------------------------------------------------------


# Evidence item fields whose value is a phrase key.
EVIDENCE_PHRASE_FIELDS = (
    "label_key",
    "question_key",
    "why_key",
    "simpler_key",
    "clarify_key",
    "ask_result_key",
)


class EvidenceItem(_Model):
    label_key: str | None = None
    value_label_keys: dict[str, str] = {}
    goal: str | None = None  # what must be established (for the LLM)
    question_key: str | None = None
    why_key: str | None = None
    simpler_key: str | None = None
    clarify_key: str | None = None
    ask_result_key: str | None = None
    meaning: dict[str, str] = {}  # value -> what it means (for the LLM)
    answers: dict[str, str] = {}  # value -> vocabulary list of reply markers
    step_role: str | None = None
    when: list[str] = []
    confirm_values: list[str] = []
    wording: Literal["scripted"] | None = None


class Evidence(_Model):
    client: dict[str, EvidenceItem] = {}
    # Absent = still collecting; [] = confirmed by telemetry from the start.
    confirmed_when: list[str] | None = None
    refuted_when: list[str] = []
    on_refuted: str | None = None  # a step role


class Solution(_Model):
    when: list[str]
    action: Literal["procedure", "bridge", "ticket"]
    step_role: str | None = None
    description_key: str | None = None


class BridgeFailed(_Model):
    notice_key: str
    ticket_note_key: str


class Step(_Model):
    """A procedure step (`id` + `kind` + `role`) or a module call (`use` + `as`)."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str | None = None
    use: str | None = None
    as_: str | None = Field(default=None, alias="as")
    kind: Literal["confirm", "action", "instruct", "verify", "escalate"] | None = None
    detector: str | None = None
    rag_section: int | None = None
    on: dict[str, str] = {}
    goto: str | None = None
    hint: str | None = None
    goal: str | None = None
    answers: dict[str, str] = {}
    tools: list[str] = []
    tool_actions: list[str] = []
    # required: the caller agrees before the step's action runs (the default);
    # not_required: it runs without asking (e.g. the post-bridge registration).
    consent: Literal["required", "not_required"] | None = None
    # What the step does (D-18); a module call inherits the module step's role.
    role: str | None = None

    @model_validator(mode="after")
    def _step_or_module_call(self) -> Step:
        if self.use:
            if self.id or self.kind:
                raise ValueError("a module call (use) takes no id/kind")
        elif not (self.id and self.kind and self.role):
            raise ValueError("a step needs id, kind and role (or use for a module call)")
        return self

    @property
    def name(self) -> str:
        return str(self.id or self.as_ or self.use)


class PackMeta(_Model):
    title: str
    domain: str


class FaultPack(_Model):
    verdict: str
    meta: PackMeta
    problem: str | None = None  # None: never a solving path (unclear_fault)
    playbook: str | None = None
    evidence: Evidence | None = None
    ticket_need_key: str | None = None
    conclusion_key: str | None = None
    confirm_key: str | None = None  # the symptom question when a recheck points here
    offer_goal: str | None = None  # the findings-moment directive (for the LLM)
    bridge_failed: BridgeFailed | None = None
    solutions: list[Solution] = []
    steps: list[Step]


class ModuleMeta(_Model):
    description: str


class Module(_Model):
    module: str
    meta: ModuleMeta
    exits: list[str] = []
    steps: list[Step]

    @model_validator(mode="after")
    def _plain_steps(self) -> Module:
        if any(s.use for s in self.steps):
            raise ValueError("a module cannot call another module")
        return self


# --- Catalog and other knowledge files ------------------------------------------


class Intent(_Model):
    # The service the complaint is about (knowledge/services.yaml); None for non-service
    # intents (billing, chat…).
    service: str | None = None
    description: str | None = None  # for the LLM classifier
    examples_key: str | None = None  # locale examples file/section, one phrasing per line
    policy: Literal["solve", "register", "answer", "not_ours", "chat"] = "solve"
    # register: the ticket type the request becomes (knowledge/ticket_types.yaml, M6 step 4)
    ticket_type: str | None = None
    confirm_question_key: str | None = None
    boundary_reply_key: str | None = None
    triggers_vocab: str | None = None  # a vocabulary list name


class IntentsCatalog(_Model):
    intents: dict[str, Intent]


class TicketType(_Model):
    department: str
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    append_only: bool = False


class TicketTypes(_Model):
    ticket_types: dict[str, TicketType]


class ServiceSpec(_Model):
    technologies: list[str]


class Dependency(_Model):
    service: str
    technology: str
    depends_on: str


class Services(_Model):
    services: dict[str, ServiceSpec]
    dependencies: list[Dependency] = []


class Detectors(_Model):
    detectors: dict[str, dict[str, str]]


class FaqEntry(_Model):
    topic: str
    keywords_vocab: str
    answer_key: str
    # The news whose own facts answer this question once it has been delivered. Without it
    # the agent denied a debt figure it had just read out (live 2026-09-23).
    answer_from_news: str | None = None


class Faq(_Model):
    faq: list[FaqEntry]


class InformEntry(_Model):
    template_key: str
    fallback_key: str | None = None
    # What to say when the caller asks about this news AFTER hearing it — rendered from the
    # same facts, so the answer can never contradict what was just delivered.
    asked_again_key: str | None = None
    clarity_requirements: list[
        Literal[
            "what_is_wrong", "what_to_do", "what_is_being_done", "when_restored", "how_notified"
        ]
    ] = []


class Inform(RootModel[dict[str, InformEntry]]):
    pass


class IdentificationPolicy(_Model):
    offer_phone_address: bool = True
    require_apartment: bool = True
    ask_caller: bool = True
    # Names of `identification.questions.<name>` phrases.
    extra_questions: list[str] = []


class Identification(_Model):
    identification: IdentificationPolicy


class VerdictFlags(_Model):
    unresolved_after_fix: bool = False
    line_fault: bool = False
    device_visible: bool = True
    healthy_up_to_router: bool = False
    inform: Literal["debt", "outage", "network", "service", "ticket"] | None = None
    auto_ticket: bool = False


class Verdicts(RootModel[dict[str, VerdictFlags]]):
    pass


class Limit(_Model):
    value: StrictInt | StrictFloat
    env: str | None = None  # an environment variable that wins when set


class Limits(RootModel[dict[str, StrictInt | StrictFloat | Limit]]):
    def entries(self) -> dict[str, Limit]:
        return {k: v if isinstance(v, Limit) else Limit(value=v) for k, v in self.root.items()}


# --- Signals -> facts (wave 3) ----------------------------------------------------


class Threshold(_Model):
    """A numeric signal read against a limit from limits.yaml."""

    limit: str
    then: str
    otherwise: str = Field(alias="else")


class SignalMap(_Model):
    """How ONE telemetry signal becomes a fact. Exactly one reading is declared:
    `map` (value -> value, with `*` and `null`), `present` (did we see anything at all),
    `above` (a numeric limit) or `derive` (a named reader in agent/facts.py, for the two
    readings that compare signals with each other)."""

    signal: str | None = None
    map: dict[str, str] | None = None
    present: bool = False
    above: Threshold | None = None
    derive: str | None = None
    values: list[str] = []  # required for `derive`: what the reader can return

    def value_set(self) -> frozenset[str]:
        """Every value this fact can take — what a card condition is checked against."""
        if self.values:
            return frozenset(self.values)
        if self.map:
            return frozenset(self.map.values())
        if self.present:
            return frozenset({"yes", "no"})
        if self.above:
            return frozenset({self.above.then, self.above.otherwise, "unknown"})
        return frozenset()

    @model_validator(mode="after")
    def _one_reading(self) -> SignalMap:
        if self.derive and not self.values:
            raise ValueError("a derived fact must declare its `values`")
        readings = [bool(self.map), self.present, bool(self.above), bool(self.derive)]
        if sum(readings) != 1:
            raise ValueError("declare exactly one of: map, present, above, derive")
        if not self.derive and not self.signal:
            raise ValueError("a signal name is required unless the fact is derived")
        return self


class Signals(_Model):
    # The tool whose observation carries these signals: how the engine knows it can LOOK
    # instead of asking the caller.
    probe: str | None = None
    facts: dict[str, SignalMap]


# --- Fault cards v2 and modules (wave 3) ------------------------------------------


# A condition on ONE fact: `traffic=none` / `device_registered!=foreign`.
CONDITION_RE = re.compile(r"^(?P<fact>[a-z][a-z0-9_]*)(?P<op>!?=)(?P<value>[a-z0-9_]+)$")


class Condition(_Model):
    """A card's claim about one fact, parsed from `fact=value` / `fact!=value`."""

    fact: str
    value: str
    negated: bool = False

    @classmethod
    def parse(cls, text: str) -> Condition:
        match = CONDITION_RE.match(str(text).strip())
        if not match:
            raise ValueError(f"condition {text!r} is not fact=value or fact!=value")
        return cls(fact=match["fact"], value=match["value"], negated=match["op"] == "!=")

    def holds(self, facts: dict[str, str]) -> bool | None:
        """True / False, or None when the fact is not known yet — "we have not asked"
        must never read as "it is not so"."""
        known = facts.get(self.fact)
        if known is None:
            return None
        return (known != self.value) if self.negated else (known == self.value)

    def __str__(self) -> str:
        return f"{self.fact}{'!=' if self.negated else '='}{self.value}"


def _conditions(values: Any) -> list[Condition]:
    return [Condition.parse(v) for v in (values or [])]


class Candidacy(_Model):
    """When a card is a candidate: every `all` condition and at least one `any`."""

    all: list[str] = []
    any: list[str] = []

    def parsed(self) -> tuple[list[Condition], list[Condition]]:
        return _conditions(self.all), _conditions(self.any)


class Need(_Model):
    """A fact the card still needs, and HOW to get it (P-2): a probe if one exists, a
    question otherwise — the engine chooses, the card only declares what is possible."""

    probe: str | None = None  # tool name
    ask: str | None = None  # phrase key for the question
    values: dict[str, str] = {}  # value -> "confirms" | "rules_out" | "hands_to=<fault>"
    # value -> the locale vocabulary list that recognises it in the caller's words. This is
    # what reads "tik viename" as `fail_scope=one` with no model call at all.
    answers: dict[str, str] = {}
    # What to say when the caller answers a bare "ne": it could mean either reading, so the
    # engine clarifies instead of acting (it used to live in the evidence drive).
    clarify: str | None = None
    # Values that FLIP the story when the caller volunteers them out of turn ("rozetė
    # neveikia" while we asked about the lights): parked for one confirm question rather than
    # accepted silently.
    confirm_values: list[str] = []
    # Conditions on other facts that must hold before this one is worth asking. Asking about
    # the cable type before we know it is a computer makes the agent sound like a form.
    when: list[str] = []
    # Half a sentence on why we are asking. A caller who knows why answers better — and
    # follows the instruction that comes next.
    why: str | None = None
    # The SECOND wording, for a caller whose answer was about something else. Asking the
    # identical question again is what made the agent sound like a machine (live 2026-09-23:
    # the same question four turns running), so the card says it differently — usually with
    # an example of how to check.
    again: str | None = None
    # What to carry on with when the caller cannot or will not tell us. A hung router is
    # rebooted anyway (that is its primary fix); a line that carries traffic is assumed to be
    # failing at one device. The engine says the assumption out loud and writes it on the
    # ticket — it never pretends the caller answered (Andrius, 2026-09-23).
    assume: str | None = None
    # Never asked — used only when the caller says it themselves. "Esu prie routerio, lemputės
    # dega" confirms a hung router on the spot, but nobody would ask about the lights before
    # the reboot: for this fault the reboot is the first move.
    volunteered: bool = False
    # There is no going on without it: instead of a third wording or a silent assumption, the
    # caller is told WHY it is needed and what happens if we do not know.
    critical: bool = False

    @model_validator(mode="after")
    def _reachable(self) -> Need:
        if not self.probe and not self.ask and not self.volunteered:
            raise ValueError(
                "a need must be reachable: declare `probe`, `ask`, or `volunteered: true`"
            )
        if self.critical and self.assume:
            raise ValueError("critical and assume contradict: either we can go on, or we cannot")
        if self.volunteered and (self.ask or self.again or self.assume):
            raise ValueError("a volunteered need is never asked, so it has no wording to assume")
        for value, meaning in self.values.items():
            if meaning not in ("confirms", "rules_out") and not meaning.startswith("hands_to="):
                raise ValueError(
                    f"values.{value}: expected confirms / rules_out / hands_to=<fault>"
                )
        if self.assume is not None and self.assume not in self.values:
            raise ValueError(f"assume: {self.assume!r} is not one of {sorted(self.values)}")
        return self


class ModuleCall(_Model):
    """One step of a solution: a module with its arguments, and what to do when the
    verification it produces says it did not work."""

    module: str
    args: dict[str, Any] = {}
    on_fail: ModuleCall | None = None
    # Facts that mean this step is ALREADY achieved, so it is skipped rather than asked for
    # ("esu prie routerio" answers "ar galite prieiti?"). The order of a fix is not loosened by
    # this — a procedure has an order (Andrius, 2026-09-23: "sprendimui reikia tikslaus
    # algoritmo, analizei — ne") — only what is already true is passed over.
    done_when: list[str] = []


class Solution(_Model):
    """What to DO once the card is confirmed — or which card takes over instead."""

    when: list[str] = []
    steps: list[ModuleCall] = []
    hands_to: str | None = None

    @model_validator(mode="after")
    def _does_something(self) -> Solution:
        if bool(self.steps) == bool(self.hands_to):
            raise ValueError("a solution either runs steps or hands over, not both/neither")
        return self


class Escalation(_Model):
    # Why the technician is needed. Optional: some faults escalate with the generic
    # reason, exactly as their v1 packs did.
    need: str | None = None
    note: str | None = None  # what the ticket must say
    # Modules that must have been RUN (or proved impossible) before a technician is sent: a
    # technician must not arrive to power-cycle a router the phone could have power-cycled
    # (Andrius, 2026-09-23). When one is missing and still possible, the engine does it first;
    # when it cannot be done, the ticket says so.
    only_after: list[str] = []


class ParamSpec(_Model):
    """One module parameter: required, a closed set of values, or a default."""

    required: bool = False
    values: list[str] = []
    default: Any = None


class ModuleSpec(_Model):
    """A reusable instruction (P-8 §3): what it does, what it needs to know, and which
    facts it can establish. The words come from the equipment catalogue, so the same
    module speaks differently for a TP-Link router and a TV box."""

    module: str
    kind: Literal["ask", "instruct", "action", "verify", "escalate"]
    params: dict[str, ParamSpec] = {}
    goal: str
    text: str | None = None  # equipment:… / device:… / procedure:… reference
    tool: str | None = None  # an engine action's tool (kind: action)
    probe: str | None = None  # the tool that verifies (kind: verify)
    produces: list[str] = []  # facts this module can establish
    # A module that asks carries its own question and its own reader, so the generic
    # policies (can you reach it, is it back) work for any device and any fault.
    ask: str | None = None  # phrase key for a question
    announce: str | None = None  # phrase key for what the agent SAYS while the engine acts
    detector: str | None = None  # a reader in perceive/detectors.py
    answers: dict[str, str] = {}  # the detector's label -> "fact=value"
    # The SAME news under another key. The reading layer has its own vocabulary from v1
    # ("esu prie routerio" lands as `device_present=found`), and without this the engine asked
    # "ar galite prieiti?" right after the caller said they were standing at it (live
    # 2026-09-23). Shape: {other_key: {other_value: this_module's_fact_value}}.
    also: dict[str, dict[str, str]] = {}
    # DEMO ONLY: the tool that makes the seeded database reflect what the caller just did
    # physically, and the environment flag that allows it. Off in production, where the
    # line changes by itself.
    simulate: str | None = None
    simulate_env: str | None = None


class FaultCard(_Model):
    """One fault, as a technician can edit it (wave 3): when it is a candidate, what
    would settle it, how it is fixed, and what happens when it is not."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fault: str
    service: str
    symptom: str | None = None
    explain: dict[str, str] = {}
    # Facts to TELL when this card's finding is announced, beyond the conditions it matched
    # on. The honest-ending card matches on nothing, so without this it said only "gedimo
    # tipas neaiškus" — the caller never heard that the line up to their flat is fine (live
    # 2026-09-23).
    explain_facts: list[str] = []
    # A fallback card is taken ONLY when no other card fits, so an honest "we cannot tell
    # over the phone" can never compete with a real diagnosis.
    fallback: bool = False
    # NEWS, not a fault: there is nothing to diagnose, only something to tell (a debt, an
    # outage, a node fault). The inform path speaks it from inform.yaml.
    news: bool = False
    # The engine names this one instead of the facts (a service never ordered, a ticket
    # already open — both come from the CRM profile, not from the line), so it is never a
    # candidate from facts.
    set_by: Literal["facts", "rule"] = "facts"
    # This card means the network up to the caller's own equipment is fine. A service that
    # RIDES on another one (IPTV over the internet) reads it to tell "fix the internet
    # first" from "the TV is its own fault" — wave 4: it used to read the verdict tree.
    line_ok: bool = False
    when: Candidacy = Candidacy()
    rules_out: list[str] = []
    needs: dict[str, Need] = {}
    solution: list[Solution] = []
    escalate: Escalation | None = None
    knowledge: str | None = None


# --- Equipment catalogue (wave 3, P-8) --------------------------------------------


class LightSpec(_Model):
    """One indicator: how to ask about it, and what each answer MEANS as a fact. This is
    what keeps model knowledge out of the fault cards."""

    ask_key: str | None = None
    means: dict[str, str] = {}


class EquipmentSpec(_Model):
    """One level of the catalogue: a model, a manufacturer family, or the basic device.

    `extends` names the level below; what is written here overrides it, and everything
    else is inherited — so the basic file carries what is true of every router and a
    family file only what is not.
    """

    equipment: str
    type: str  # router | modem | ont | tv_box | computer …
    extends: str | None = None
    matches: list[str] = []  # what the CRM model string / the caller's words may contain
    name_key: str | None = None
    locate_key: str | None = None
    actions: dict[str, str] = {}  # "reboot.power" -> phrase key
    lights: dict[str, LightSpec] = {}


# --- Tools (P-7 manifests) --------------------------------------------------------


# What a tool DOES, which is what the engine reasons about — never the implementation.
TOOL_CAPABILITIES = ("probe", "action", "crm", "outages", "ticketing", "knowledge", "simulate")
# demo_db and fake run in-process; mcp:<server> / http:<service> arrive with the real
# systems (stage 12), and switching one tool over is this one line.
ADAPTER_RE = re.compile(r"^(demo_db|rag_local|fake|mcp:[a-z0-9_]+|http:[a-z0-9_]+)$")
# "08-22" — the hours the tool may run at all (equipment reboots are not a night job).
HOURS_RE = re.compile(r"^([01]\d|2[0-3])-([01]\d|2[0-3])$")


class ToolGuards(_Model):
    """Per-tool limits the gateway enforces before the adapter is ever reached."""

    max_per_call: StrictInt | None = None
    cooldown_s: StrictInt | None = None
    allowed_hours: str | None = None

    @model_validator(mode="after")
    def _hours(self) -> ToolGuards:
        if self.allowed_hours and not HOURS_RE.match(self.allowed_hours):
            raise ValueError(f"allowed_hours '{self.allowed_hours}' is not HH-HH (e.g. 08-22)")
        return self


class ToolRateLimit(_Model):
    per_minute: StrictInt


class ToolFailure(_Model):
    """What happens when the tool does not answer: what the caller hears, and which way
    the call goes on. `fallback` is a PLAN, not an excuse — the engine keeps the call
    moving instead of stalling on a system that is down."""

    say_key: str | None = None  # required unless the call simply goes on (fallback: skip)
    fallback: Literal["ask_client", "ticket", "skip", "end_call"]
    alert: Literal["ops"] | None = None

    @model_validator(mode="after")
    def _say(self) -> ToolFailure:
        if self.fallback != "skip" and not self.say_key:
            raise ValueError(f"on_failure.fallback '{self.fallback}' needs a say_key")
        return self


class ToolManifest(_Model):
    """One tool's contract (P-7): what it can do, who may call it, how long it may take,
    and what happens when it fails. A new tool is this file plus an adapter."""

    tool: str
    capability: Literal[TOOL_CAPABILITIES]  # type: ignore[valid-type]
    adapter: str
    args: dict[str, str] = {}
    returns: list[str] = []  # evidence keys / facts the observation may bring
    requires: list[Literal["identified", "consent"]] = []
    guards: ToolGuards = ToolGuards()
    timeout_s: StrictInt | StrictFloat
    retries: StrictInt = 0
    rate_limit: ToolRateLimit | None = None
    filler_key: str | None = None  # what to say while the caller waits
    on_failure: ToolFailure
    audit: bool = False

    @model_validator(mode="after")
    def _adapter(self) -> ToolManifest:
        if not ADAPTER_RE.match(self.adapter):
            raise ValueError(
                f"adapter '{self.adapter}' is not demo_db, fake, mcp:<server> or http:<service>"
            )
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        return self


class Policies(_Model):
    # Who may call a tool is declared per tool (knowledge/tools/*.yaml -> requires).
    forbidden_actions: list[str] = []
    forbidden_topics: list[str] = []


# --- Validation -------------------------------------------------------------------


class KnowledgeError(Exception):
    """Every problem found in the knowledge files, one `file: path: message` per line."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("knowledge files are invalid:\n  " + "\n  ".join(errors))


@dataclass
class Knowledge:
    intents: IntentsCatalog | None = None
    services: Services | None = None
    ticket_types: TicketTypes | None = None
    packs: dict[str, FaultPack] = field(default_factory=dict)
    modules: dict[str, Module] = field(default_factory=dict)
    detectors: Detectors | None = None
    faq: Faq | None = None
    inform: Inform | None = None
    identification: Identification | None = None
    verdicts: Verdicts | None = None
    limits: Limits | None = None
    policies: Policies | None = None
    signals: Signals | None = None
    tools: dict[str, ToolManifest] = field(default_factory=dict)


def _non_string_keys(data: Any, loc: str = "") -> list[str]:
    """YAML 1.1 reads unquoted on/yes/no keys as booleans — name each one."""
    out = []
    if isinstance(data, dict):
        for key, value in data.items():
            here = f"{loc}.{key}" if loc else str(key)
            if not isinstance(key, str):
                out.append(
                    f"{loc or '<root>'}: key {key!r} is not a string (quote it: 'on', 'yes', 'no')"
                )
            out += _non_string_keys(value, here)
    elif isinstance(data, list):
        for i, value in enumerate(data):
            out += _non_string_keys(value, f"{loc}.{i}" if loc else str(i))
    return out


def _read(path: Path, model: type[BaseModel], errors: list[str], root: Path) -> Any:
    rel = path.relative_to(root).as_posix()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        errors.append(f"{rel}: cannot read ({e})")
        return None
    bad_keys = _non_string_keys(data)
    if bad_keys:
        errors += [f"{rel}: {e}" for e in bad_keys]
        return None
    try:
        return model.model_validate(data if data is not None else {})
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            errors.append(f"{rel}: {loc}: {err['msg']}")
        return None


def _playbook_sections(kb_dir: Path, doc: str) -> int | None:
    from ..playbook import parse_steps

    path = kb_dir / (doc if doc.endswith(".md") else f"{doc}.md")
    if not path.is_file():
        return None
    return len(parse_steps(path.read_text(encoding="utf-8")))


def _condition_errors(conds: list[str], keys: set[str], where: str) -> list[str]:
    out = []
    for cond in conds:
        cond = cond.strip()
        if cond in CONDITION_TOKENS:
            continue
        key, sep, value = cond.partition("=")
        if not sep or not value.strip():
            out.append(f"{where}: condition '{cond}' is not key=value")
        elif key.strip() not in keys:
            out.append(f"{where}: condition '{cond}' names an undeclared evidence key")
    return out


def _check_module(rel: str, module: Module, detectors: set[str]) -> list[str]:
    errors = []
    ids = [s.name for s in module.steps]
    targets = set(ids) | set(module.exits)
    for i, step in enumerate(module.steps):
        where = f"{rel}: steps.{i} ({step.name})"
        for key, target in step.on.items():
            if target not in targets:
                errors.append(f"{where}: on.{key} -> unknown target '{target}'")
        if step.goto and step.goto not in targets:
            errors.append(f"{where}: goto -> unknown target '{step.goto}'")
        if step.detector and step.detector not in detectors:
            errors.append(f"{where}: unknown detector '{step.detector}'")
    return errors


def _check_pack(
    rel: str,
    pack: FaultPack,
    modules: dict[str, Module],
    detectors: set[str],
    problems: set[str] | None,
    kb_dir: Path,
) -> list[str]:
    errors: list[str] = []
    names = [s.name for s in pack.steps]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        errors.append(f"{rel}: duplicate step names {dupes}")
    targets = set(names) | TERMINAL_TARGETS
    sections = _playbook_sections(kb_dir, pack.playbook) if pack.playbook else None
    if pack.playbook and sections is None:
        errors.append(f"{rel}: playbook '{pack.playbook}' not found")
    if problems is not None and pack.problem and pack.problem not in problems:
        errors.append(f"{rel}: problem '{pack.problem}' is not in intents.yaml intents")

    from ..faults import ENGINE_ROLES

    roles = [
        step.role
        or (
            modules[step.use].steps[0].role
            if step.use in modules and modules[step.use].steps
            else None
        )
        for step in pack.steps
    ]
    repeated = sorted({r for r in roles if r in ENGINE_ROLES and roles.count(r) > 1})
    if repeated:
        errors.append(f"{rel}: engine roles {repeated} appear on more than one step")
    for i, step in enumerate(pack.steps):
        where = f"{rel}: steps.{i} ({step.name})"
        for key, target in step.on.items():
            if target not in targets:
                errors.append(f"{where}: on.{key} -> unknown step '{target}'")
        if step.goto and step.goto not in targets:
            errors.append(f"{where}: goto -> unknown step '{step.goto}'")
        if step.detector and step.detector not in detectors:
            errors.append(f"{where}: unknown detector '{step.detector}'")
        if sections is not None and step.rag_section is not None:
            if not 0 <= step.rag_section < sections:
                errors.append(
                    f"{where}: rag_section {step.rag_section} but the playbook has {sections} sections"
                )
        routing = set(step.on)
        if step.use:
            module = modules.get(step.use)
            if module is None:
                errors.append(f"{where}: unknown module '{step.use}'")
                continue
            if not step.as_:
                errors.append(f"{where}: a module call needs `as` (the instance name)")
            unknown_exits = set(step.on) - set(module.exits)
            if unknown_exits:
                errors.append(f"{where}: on keys {sorted(unknown_exits)} are not module exits")
            missing_exits = set(module.exits) - set(step.on)
            if missing_exits:
                errors.append(f"{where}: module exits {sorted(missing_exits)} are not routed")
            routing = set(module.steps[0].on) if module.steps else set()
        if step.answers and routing and not set(step.answers) <= routing:
            extra = sorted(set(step.answers) - routing)
            errors.append(f"{where}: answers keys {extra} are not routing keys")

    ev = pack.evidence
    keys = set(ev.client) if ev else set()
    declared_roles = {r for r in roles if r}

    def role_errors(where: str, role: str | None) -> list[str]:
        if not role:
            return []
        if role not in declared_roles:
            return [f"{where}: step_role '{role}' is not a role of this pack"]
        if roles.count(role) > 1:
            return [f"{where}: step_role '{role}' names more than one step"]
        return []

    if ev:
        for key, item in ev.client.items():
            where = f"{rel}: evidence.client.{key}"
            errors += role_errors(f"{where}.step_role", item.step_role)
            errors += _condition_errors(item.when, keys, f"{where}.when")
        for name in ("confirmed_when", "refuted_when"):
            errors += _condition_errors(getattr(ev, name) or [], keys, f"{rel}: evidence.{name}")
        errors += role_errors(f"{rel}: evidence.on_refuted", ev.on_refuted)
    for i, rule in enumerate(pack.solutions):
        where = f"{rel}: solutions.{i}"
        errors += role_errors(f"{where}.step_role", rule.step_role)
        errors += _condition_errors(rule.when, keys, f"{where}.when")
    return errors


def llm_texts(k: Knowledge) -> list[tuple[str, str]]:
    """(where, text) for the LLM-facing texts that may quote <<examples:…>>."""
    out: list[tuple[str, str]] = []
    for verdict, pack in k.packs.items():
        if pack.offer_goal:
            out.append((f"pack {verdict}: offer_goal", pack.offer_goal))
        for step in pack.steps:
            for name in ("hint", "goal"):
                if getattr(step, name):
                    out.append((f"pack {verdict}: steps.{step.name}.{name}", getattr(step, name)))
    for name, module in k.modules.items():
        for step in module.steps:
            if step.hint:
                out.append((f"module {name}: steps.{step.name}.hint", step.hint))
    return out


def phrase_refs(k: Knowledge) -> list[tuple[str, str]]:
    """(where, phrase key) for every locale sentence the knowledge files name."""
    refs: list[tuple[str, str]] = []

    def add(where: str, key: str | None) -> None:
        if key:
            refs.append((where, key))

    for verdict, pack in k.packs.items():
        where = f"pack {verdict}"
        for key, item in (pack.evidence.client if pack.evidence else {}).items():
            for name in EVIDENCE_PHRASE_FIELDS:
                add(f"{where}: evidence.client.{key}.{name}", getattr(item, name))
            for value, phrase_key in item.value_label_keys.items():
                add(f"{where}: evidence.client.{key}.value_label_keys.{value}", phrase_key)
        add(f"{where}: ticket_need_key", pack.ticket_need_key)
        add(f"{where}: conclusion_key", pack.conclusion_key)
        add(f"{where}: confirm_key", pack.confirm_key)
        if pack.bridge_failed:
            add(f"{where}: bridge_failed.notice_key", pack.bridge_failed.notice_key)
            add(f"{where}: bridge_failed.ticket_note_key", pack.bridge_failed.ticket_note_key)
        for i, rule in enumerate(pack.solutions):
            add(f"{where}: solutions.{i}.description_key", rule.description_key)
        for step in pack.steps:
            for answer, phrase_key in step.answers.items():
                add(f"{where}: steps.{step.name}.answers.{answer}", phrase_key)
    for name, module in k.modules.items():
        for step in module.steps:
            for answer, phrase_key in step.answers.items():
                add(f"module {name}: steps.{step.name}.answers.{answer}", phrase_key)
    if k.intents:
        for name, intent in k.intents.intents.items():
            add(f"intents.yaml: intents.{name}.confirm_question_key", intent.confirm_question_key)
            add(f"intents.yaml: intents.{name}.boundary_reply_key", intent.boundary_reply_key)
    if k.faq:
        for i, entry in enumerate(k.faq.faq):
            add(f"faq.yaml: faq.{i}.answer_key", entry.answer_key)
    if k.inform:
        for verdict, entry in k.inform.root.items():
            add(f"inform.yaml: {verdict}.template_key", entry.template_key)
            add(f"inform.yaml: {verdict}.fallback_key", entry.fallback_key)
    if k.detectors:
        for name, options in k.detectors.detectors.items():
            for key, phrase_key in options.items():
                add(f"detectors.yaml: {name}.{key}", phrase_key)
    if k.identification:
        for name in k.identification.identification.extra_questions:
            add("identification.yaml: extra_questions", f"identification.questions.{name}")
    for name, tool in k.tools.items():
        add(f"tools/{name}.yaml: on_failure.say_key", tool.on_failure.say_key)
        add(f"tools/{name}.yaml: filler_key", tool.filler_key)
    return refs


def validate_knowledge(
    knowledge_dir: Path = KNOWLEDGE_DIR,
    playbook_dir: Path = PLAYBOOK_DIR,
    language: str = "lt",
    locales_dir: Path | None = None,
) -> Knowledge:
    """Validate every knowledge file against the schema and the `language`
    locale; raise KnowledgeError listing all problems."""
    from .locale import LOCALES_DIR, LocaleError, load_locale

    errors: list[str] = []
    root = knowledge_dir
    k = Knowledge()

    single_files: dict[str, tuple[str, type[BaseModel]]] = {
        "intents": ("intents.yaml", IntentsCatalog),
        "services": ("services.yaml", Services),
        "ticket_types": ("ticket_types.yaml", TicketTypes),
        "detectors": ("detectors.yaml", Detectors),
        "faq": ("faq.yaml", Faq),
        "inform": ("inform.yaml", Inform),
        "identification": ("identification.yaml", Identification),
        "verdicts": ("verdicts.yaml", Verdicts),
        "limits": ("limits.yaml", Limits),
        "policies": ("policies.yaml", Policies),
        "signals": ("signals.yaml", Signals),
    }
    for attr, (name, model) in single_files.items():
        setattr(k, attr, _read(root / name, model, errors, root))

    module_files: dict[str, str] = {}
    for path in sorted((root / "modules").glob("*.yaml")):
        module = _read(path, Module, errors, root)
        if module is None:
            continue
        rel = path.relative_to(root).as_posix()
        if module.module in k.modules:
            errors.append(f"{rel}: module '{module.module}' also in {module_files[module.module]}")
        k.modules[module.module] = module
        module_files[module.module] = rel

    tool_files: dict[str, str] = {}
    for path in sorted((root / "tools").glob("*.yaml")):
        tool = _read(path, ToolManifest, errors, root)
        if tool is None:
            continue
        rel = path.relative_to(root).as_posix()
        if tool.tool in k.tools:
            errors.append(f"{rel}: tool '{tool.tool}' also in {tool_files[tool.tool]}")
        k.tools[tool.tool] = tool
        tool_files[tool.tool] = rel

    pack_files: dict[str, str] = {}
    for path in sorted((root / "faults").glob("*.yaml")):
        pack = _read(path, FaultPack, errors, root)
        if pack is None:
            continue
        rel = path.relative_to(root).as_posix()
        if pack.verdict in k.packs:
            errors.append(f"{rel}: verdict '{pack.verdict}' also in {pack_files[pack.verdict]}")
        k.packs[pack.verdict] = pack
        pack_files[pack.verdict] = rel

    declared = set(k.detectors.detectors) if k.detectors else set()
    for name in sorted(CODE_DETECTORS - declared):
        errors.append(f"detectors.yaml: detector '{name}' has no answer meanings")
    detectors = set(CODE_DETECTORS) | declared
    problems = set(k.intents.intents) if k.intents else None
    if k.services:
        known = set(k.services.services)
        for i, dep in enumerate(k.services.dependencies):
            for field in ("service", "depends_on"):
                if getattr(dep, field) not in known:
                    errors.append(
                        f"services.yaml: dependencies.{i}.{field} '{getattr(dep, field)}' is not a service"
                    )
            if (
                dep.service in known
                and dep.technology not in k.services.services[dep.service].technologies
            ):
                errors.append(
                    f"services.yaml: dependencies.{i}.technology '{dep.technology}' is not a technology of {dep.service}"
                )
        for name, intent in (k.intents.intents if k.intents else {}).items():
            if (
                intent.ticket_type
                and k.ticket_types
                and intent.ticket_type not in k.ticket_types.ticket_types
            ):
                errors.append(
                    f"intents.yaml: intents.{name}.ticket_type '{intent.ticket_type}' is not a ticket type"
                )
            if intent.service and intent.service not in known:
                errors.append(
                    f"intents.yaml: intents.{name}.service '{intent.service}' is not a service"
                )
    for name, module in k.modules.items():
        errors += _check_module(module_files[name], module, detectors)
    for verdict, pack in k.packs.items():
        errors += _check_pack(
            pack_files[verdict], pack, k.modules, detectors, problems, playbook_dir
        )

    try:
        locale = load_locale(language, locales_dir or LOCALES_DIR)
    except LocaleError as e:
        errors.append(str(e))
    else:
        for where, key in phrase_refs(k):
            if not locale.has(key):
                errors.append(f"{where}: phrase '{key}' is missing in locale '{language}'")
        from .locale import _examples, example_refs

        for verdict, pack in k.packs.items():
            for key, item in (pack.evidence.client if pack.evidence else {}).items():
                for value, name in item.answers.items():
                    if not isinstance(locale.vocabulary.get(name), tuple):
                        errors.append(
                            f"pack {verdict}: evidence.client.{key}.answers.{value} '{name}' is not a vocabulary list"
                        )
        for i, entry in enumerate(k.faq.faq if k.faq else []):
            if not isinstance(locale.vocabulary.get(entry.keywords_vocab), tuple):
                errors.append(
                    f"faq.yaml: faq.{i}.keywords_vocab '{entry.keywords_vocab}' is not a vocabulary list"
                )
        for name, intent in (k.intents.intents if k.intents else {}).items():
            if intent.triggers_vocab and not isinstance(
                locale.vocabulary.get(intent.triggers_vocab), tuple
            ):
                errors.append(
                    f"intents.yaml: intents.{name}.triggers_vocab '{intent.triggers_vocab}' is not a vocabulary list"
                )
            if intent.examples_key:
                try:
                    _examples(language, intent.examples_key)
                except LocaleError as e:
                    errors.append(f"intents.yaml: intents.{name}.examples_key: {e}")
        for where, text in llm_texts(k):
            for ref in example_refs(text):
                try:
                    _examples(language, ref)
                except LocaleError as e:
                    errors.append(f"{where}: {e}")

    if errors:
        raise KnowledgeError(errors)
    return k

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


class Faq(_Model):
    faq: list[FaqEntry]


class InformEntry(_Model):
    template_key: str
    fallback_key: str | None = None
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
    identified_customer_required: list[str] = []  # tools refused before identification
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

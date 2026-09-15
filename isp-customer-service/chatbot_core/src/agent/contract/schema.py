"""
Knowledge schema — pydantic models for every file in `agent/knowledge/` plus the
cross-reference checks a model alone cannot express (routing targets exist,
modules exist, answers match routing keys, playbook sections exist).

`validate_knowledge()` reads the files, validates them and raises one
KnowledgeError listing every problem as `file: path: message`. It changes no
behaviour: the runtime loaders still read the files themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, RootModel, ValidationError, model_validator

AGENT_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = AGENT_DIR / "knowledge"
PLAYBOOK_DIR = AGENT_DIR.parent / "rag" / "knowledge_base"

# Routing targets handled by the walker itself, not by a pack step.
TERMINAL_TARGETS = frozenset({"resolve", "callback", "end"})
# Condition tokens that are not `evidence_key=value`.
CONDITION_TOKENS = frozenset({"patvirtinta", "tilto_fazeje"})
# Detectors implemented in code (resolution.DETECTORS); detectors.yaml may add
# LLM-only ones.
CODE_DETECTORS = frozenset(
    {"yes_no", "restored", "reboot_check", "scope", "conn", "port", "lights", "have_device"}
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Fault packs and modules ------------------------------------------------------


# Evidence item fields whose value is a phrase key.
EVIDENCE_PHRASE_FIELDS = ("label", "klausimas", "kodel", "paprasciau", "patikslinimas", "ka_radote")


class EvidenceItem(_Model):
    label: str | None = None
    reiksmes: dict[str, str] = {}
    reikia: str | None = None
    klausimas: str | None = None
    kodel: str | None = None
    paprasciau: str | None = None
    patikslinimas: str | None = None
    ka_radote: str | None = None
    reiskia: dict[str, str] = {}
    atsakymai: dict[str, list[str]] = {}
    zingsnis: str | None = None
    kada: list[str] = []
    patikslinti: list[str] = []
    formuluote: Literal["skriptas"] | None = None


class Evidence(_Model):
    client: dict[str, EvidenceItem] = {}
    # Absent = still collecting; [] = confirmed by telemetry from the start.
    patvirtinta_kai: list[str] | None = None
    paneigta_kai: list[str] = []
    paneigta_veda: str | None = None


class Solution(_Model):
    jei: list[str]
    tada: Literal["walker", "bridge", "ticket"]
    zingsnis: str | None = None
    aprasymas: str | None = None


class BridgeFailed(_Model):
    pastaba: str
    prierasas: str


class Step(_Model):
    """A procedure step (`id` + `kind`) or a module call (`use` + `kaip`)."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str | None = None
    use: str | None = None
    kaip: str | None = None
    kind: Literal["confirm", "action", "instruct", "verify", "escalate"] | None = None
    detector: str | None = None
    rag_section: int | None = None
    on: dict[str, str] = {}
    goto: str | None = None
    hint: str | None = None
    tikslas: str | None = None
    answers: dict[str, str] = {}
    tools: list[str] = []
    tool_actions: list[str] = []
    consent: bool | None = None
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
        return str(self.id or self.kaip or self.use)


class PackMeta(_Model):
    pavadinimas: str
    domenas: str
    priklauso_nuo: list[str] = []
    tags: list[str] = []
    vairuotojas: Literal["solveris", "walker"] | None = None


class FaultPack(_Model):
    verdict: str
    meta: PackMeta
    problem: str
    playbook: str
    evidence: Evidence | None = None
    reikalinga: str | None = None
    isvada: str | None = None
    pasiulymas: str | None = None
    tiltas_nepavyko: BridgeFailed | None = None
    sprendimai: list[Solution] = []
    steps: list[Step]


class ModuleMeta(_Model):
    aprasymas: str
    tags: list[str] = []


class Module(_Model):
    modulis: str
    meta: ModuleMeta
    isejimai: list[str] = []
    steps: list[Step]

    @model_validator(mode="after")
    def _plain_steps(self) -> Module:
        if any(s.use for s in self.steps):
            raise ValueError("a module cannot call another module")
        return self


# --- Catalog and other knowledge files ------------------------------------------


class Problem(_Model):
    aprasymas: str | None = None
    pavyzdziai: list[str] = []
    politika: Literal["sprendzia", "registruoja", "nelieciam", "pokalbis"] = "sprendzia"
    patvirtinimas: str | None = None
    atsakymas: str | None = None
    triggers: list[str] = []


class FaultsManifest(_Model):
    problems: dict[str, Problem]
    faults: dict[str, FaultPack] = {}


class Detectors(_Model):
    detectors: dict[str, dict[str, str]]


class FaqEntry(_Model):
    tema: str
    raktazodziai: list[str]
    atsakymas: str


class Faq(_Model):
    faq: list[FaqEntry]


class InformEntry(_Model):
    sakoma: str
    fallback: str | None = None
    aiskumo_salyga: list[
        Literal["kas_negerai", "ka_daryti", "kas_daroma", "kada_atsistatys", "kaip_suzinos"]
    ] = []


class Informavimas(RootModel[dict[str, InformEntry]]):
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
    inform: Literal["debt", "outage", "network"] | None = None
    auto_ticket: bool = False


class Verdicts(RootModel[dict[str, VerdictFlags]]):
    pass


# --- Validation -------------------------------------------------------------------


class KnowledgeError(Exception):
    """Every problem found in the knowledge files, one `file: path: message` per line."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("knowledge files are invalid:\n  " + "\n  ".join(errors))


@dataclass
class Knowledge:
    manifest: FaultsManifest | None = None
    packs: dict[str, FaultPack] = field(default_factory=dict)
    modules: dict[str, Module] = field(default_factory=dict)
    detectors: Detectors | None = None
    faq: Faq | None = None
    informavimas: Informavimas | None = None
    identification: Identification | None = None
    verdicts: Verdicts | None = None


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
    targets = set(ids) | set(module.isejimai)
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
    sections = _playbook_sections(kb_dir, pack.playbook)
    if sections is None:
        errors.append(f"{rel}: playbook '{pack.playbook}' not found")
    if problems is not None and pack.problem not in problems:
        errors.append(f"{rel}: problem '{pack.problem}' is not in faults.yaml problems")

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
            if not step.kaip:
                errors.append(f"{where}: a module call needs kaip (the instance name)")
            unknown_exits = set(step.on) - set(module.isejimai)
            if unknown_exits:
                errors.append(f"{where}: on keys {sorted(unknown_exits)} are not module exits")
            missing_exits = set(module.isejimai) - set(step.on)
            if missing_exits:
                errors.append(f"{where}: module exits {sorted(missing_exits)} are not routed")
            routing = set(module.steps[0].on) if module.steps else set()
        if step.answers and routing and not set(step.answers) <= routing:
            extra = sorted(set(step.answers) - routing)
            errors.append(f"{where}: answers keys {extra} are not routing keys")

    ev = pack.evidence
    keys = set(ev.client) if ev else set()
    step_names = set(names)
    if ev:
        for key, item in ev.client.items():
            where = f"{rel}: evidence.client.{key}"
            if item.zingsnis and item.zingsnis not in step_names:
                errors.append(f"{where}: zingsnis -> unknown step '{item.zingsnis}'")
            errors += _condition_errors(item.kada, keys, f"{where}.kada")
        for name in ("patvirtinta_kai", "paneigta_kai"):
            errors += _condition_errors(getattr(ev, name) or [], keys, f"{rel}: evidence.{name}")
        if ev.paneigta_veda and ev.paneigta_veda not in step_names:
            errors.append(f"{rel}: evidence.paneigta_veda -> unknown step '{ev.paneigta_veda}'")
    for i, rule in enumerate(pack.sprendimai):
        where = f"{rel}: sprendimai.{i}"
        if rule.zingsnis and rule.zingsnis not in step_names:
            errors.append(f"{where}: zingsnis -> unknown step '{rule.zingsnis}'")
        errors += _condition_errors(rule.jei, keys, f"{where}.jei")
    return errors


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
            for value, phrase_key in item.reiksmes.items():
                add(f"{where}: evidence.client.{key}.reiksmes.{value}", phrase_key)
        add(f"{where}: reikalinga", pack.reikalinga)
        add(f"{where}: isvada", pack.isvada)
        if pack.tiltas_nepavyko:
            add(f"{where}: tiltas_nepavyko.pastaba", pack.tiltas_nepavyko.pastaba)
            add(f"{where}: tiltas_nepavyko.prierasas", pack.tiltas_nepavyko.prierasas)
        for i, rule in enumerate(pack.sprendimai):
            add(f"{where}: sprendimai.{i}.aprasymas", rule.aprasymas)
    if k.manifest:
        for name, problem in k.manifest.problems.items():
            add(f"faults.yaml: problems.{name}.patvirtinimas", problem.patvirtinimas)
            add(f"faults.yaml: problems.{name}.atsakymas", problem.atsakymas)
    if k.faq:
        for i, entry in enumerate(k.faq.faq):
            add(f"faq.yaml: faq.{i}.atsakymas", entry.atsakymas)
    if k.informavimas:
        for verdict, entry in k.informavimas.root.items():
            add(f"informavimas.yaml: {verdict}.sakoma", entry.sakoma)
            add(f"informavimas.yaml: {verdict}.fallback", entry.fallback)
    if k.identification:
        for name in k.identification.identification.extra_questions:
            add("identification.yaml: extra_questions", f"identification.questions.{name}")
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
        "manifest": ("faults.yaml", FaultsManifest),
        "detectors": ("detectors.yaml", Detectors),
        "faq": ("faq.yaml", Faq),
        "informavimas": ("informavimas.yaml", Informavimas),
        "identification": ("identification.yaml", Identification),
        "verdicts": ("verdicts.yaml", Verdicts),
    }
    for attr, (name, model) in single_files.items():
        setattr(k, attr, _read(root / name, model, errors, root))

    module_files: dict[str, str] = {}
    for path in sorted((root / "modules").glob("*.yaml")):
        module = _read(path, Module, errors, root)
        if module is None:
            continue
        rel = path.relative_to(root).as_posix()
        if module.modulis in k.modules:
            errors.append(
                f"{rel}: module '{module.modulis}' also in {module_files[module.modulis]}"
            )
        k.modules[module.modulis] = module
        module_files[module.modulis] = rel

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
    problems = set(k.manifest.problems) if k.manifest else None
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

    if errors:
        raise KnowledgeError(errors)
    return k

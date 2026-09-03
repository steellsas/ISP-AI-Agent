"""
Fault knowledge loader — the declarative layer (Phase 3.8 step 5b/5c).

Reads `agent/knowledge/faults.yaml`, which holds:
  * `problems` — the call's PURPOSE and the phrases that signal it (what the CALLER
    reports), and
  * `faults`   — each CAUSE the telemetry can reach: its playbook, and the full
    procedure (steps: kind, detector, routing, rag section, hint, and what each
    routing key MEANS).

Why: the procedure and the answer meanings used to live in Python (`STRATEGIES`,
`DETECTOR_GLOSSES`, `_PROBLEM_KEYWORDS`). Moving them here makes a new fault — or a
reworded check — a FILE edit rather than a code change, which is the whole point of the
migration. Code keeps the mechanism and the safety enforcement.

Fail-soft by design: anything missing or malformed yields None/{} and the engine falls
back to its in-code defaults, so a bad edit can never take the agent down.
"""

from __future__ import annotations

import logging
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_KNOWLEDGE = Path(__file__).resolve().parent / "knowledge"
_FAULTS_PATH = _KNOWLEDGE / "faults.yaml"
_FAULTS_DIR = _KNOWLEDGE / "faults"
_MODULES_DIR = _KNOWLEDGE / "modules"


@lru_cache(maxsize=1)
def _doc() -> dict[str, Any]:
    """Parse the manifest once. Any failure -> empty (engine uses its code defaults)."""
    try:
        import yaml

        data = yaml.safe_load(_FAULTS_PATH.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:  # pragma: no cover - defensive; never break a call
        logger.warning(f"faults.yaml not loaded ({e}); using in-code defaults")
        return {}


def _load_yaml_dir(path: Path, key_field: str) -> dict[str, Any]:
    """Every *.yaml in `path` -> {spec[key_field]: spec}. Fail-soft per file: one
    broken pack must not take the others (or the call) down."""
    out: dict[str, Any] = {}
    if not path.is_dir():
        return out
    try:
        import yaml
    except Exception:  # pragma: no cover - defensive
        return out
    for f in sorted(path.glob("*.yaml")):
        try:
            spec = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            name = spec.get(key_field)
            if isinstance(spec, dict) and name:
                out[str(name)] = spec
            else:
                logger.warning(f"{f.name}: missing '{key_field}' — skipped")
        except Exception as e:
            logger.warning(f"{f.name} not loaded ({e}) — skipped")
    return out


@lru_cache(maxsize=1)
def _dir_faults() -> dict[str, Any]:
    """Fault PACKS — one file per fault in knowledge/faults/ (R5: 'įkelti naują
    gedimą' = drop a file in). A pack overrides a same-named monolith entry."""
    return _load_yaml_dir(_FAULTS_DIR, "verdict")


@lru_cache(maxsize=1)
def _modules() -> dict[str, Any]:
    """Reusable instruction MODULES (knowledge/modules/): named step sequences
    with declared exits (isejimai) that packs compose via `use:` — the same
    procedure (bind a MAC, verify restored) is written ONCE."""
    return _load_yaml_dir(_MODULES_DIR, "modulis")


def _faults() -> dict[str, Any]:
    merged = dict(_doc().get("faults") or {})
    merged.update(_dir_faults())
    return merged


def reload() -> None:
    """Drop the caches so edited knowledge files take effect without a restart."""
    _doc.cache_clear()
    _dir_faults.cache_clear()
    _modules.cache_clear()
    _expanded_steps.cache_clear()
    build_strategy.cache_clear()


# --- Module expansion (compile-time composition) ---------------------------------


@lru_cache(maxsize=32)
def _expanded_steps(verdict: str) -> tuple[dict[str, Any], ...]:
    """The fault's steps with every `use:` module call EXPANDED inline.

    Rules (docs/FAULT_PACKS.md): a single-step module's step id becomes the
    instance name (`kaip:`); a multi-step module's ids become `<kaip>_<id>`.
    Module-declared exits (isejimai) route through the instance's `on:` map;
    internal targets are renamed by the same id rule. Instance-level `hint`,
    `rag_section` override the module's FIRST step. Fail-soft: an unknown
    module logs and is skipped."""
    spec = _faults().get(verdict) or {}
    out: list[dict[str, Any]] = []
    for raw in spec.get("steps") or []:
        if not isinstance(raw, dict):
            continue
        if "use" not in raw:
            out.append(raw)
            continue
        mod = _modules().get(str(raw["use"]))
        instance = str(raw.get("kaip") or raw["use"])
        if not isinstance(mod, dict) or not mod.get("steps"):
            logger.warning(f"{verdict}: unknown module '{raw.get('use')}' — skipped")
            continue
        msteps = [dict(m) for m in mod["steps"] if isinstance(m, dict)]
        exits = {str(x) for x in (mod.get("isejimai") or [])}
        exit_map = {str(k): str(v) for k, v in (raw.get("on") or {}).items()}
        single = len(msteps) == 1

        def _rename(step_id: str, _inst: str = instance, _single: bool = single) -> str:
            return _inst if _single else f"{_inst}_{step_id}"

        for i, m in enumerate(msteps):
            m["id"] = _rename(str(m.get("id", i)))
            m["on"] = {
                str(k): (exit_map.get(str(v), str(v)) if str(v) in exits else _rename(str(v)))
                for k, v in (m.get("on") or {}).items()
            }
            if m.get("goto"):
                g = str(m["goto"])
                m["goto"] = exit_map.get(g, g) if g in exits else _rename(g)
            if not m.get("playbook") and mod.get("playbook"):
                m["playbook"] = mod["playbook"]
            if i == 0:
                # Instance-level overrides: the module is generic, the CALL SITE
                # supplies the contextual wording ("prijungtame kompiuteryje…"
                # vs "po perkrovimo…") and the RAG section for this fault.
                for key in ("hint", "rag_section", "answers", "detector", "tikslas"):
                    if raw.get(key) is not None:
                        m[key] = raw[key]
            out.append(m)
    return tuple(out)


# --- Meta / discovery -------------------------------------------------------------


def fault_meta(verdict: str | None) -> dict[str, Any]:
    """The pack's meta block (pavadinimas, domenas, priklauso_nuo, tags, …)."""
    if not verdict:
        return {}
    meta = (_faults().get(verdict) or {}).get("meta")
    return meta if isinstance(meta, dict) else {}


def find_by_tag(tag: str) -> list[str]:
    """Verdicts whose meta.tags contain `tag` — the knowledge-discovery index."""
    low = tag.lower()
    return [
        v
        for v, spec in _faults().items()
        if isinstance(spec, dict)
        and low in [str(t).lower() for t in (spec.get("meta") or {}).get("tags") or []]
    ]


def driver(verdict: str | None) -> str | None:
    """meta.vairuotojas — who drives this fault's turns: "solveris" (the
    evidence-drive + solver own the flow) or "walker" (the step tree; default).
    R4b rollout is PER PACK: flipping a fault to the solver is a file edit."""
    v = fault_meta(verdict).get("vairuotojas")
    return str(v) if v in ("solveris", "walker") else None


def depends_on(verdict: str | None) -> list[str]:
    """meta.priklauso_nuo — upstream domains to check FIRST (mixed faults:
    'neveikia TV' whose real cause is the internet being down)."""
    dep = fault_meta(verdict).get("priklauso_nuo")
    return [str(x) for x in dep] if isinstance(dep, list) else []


# --- Purpose: what the CALLER reports -------------------------------------------


def classify_purpose(text: str | None) -> str | None:
    """The reported problem type from the utterance, using the manifest's triggers.
    Order matters (a specific problem before a broader one), which YAML preserves.
    Returns None when nothing matches, so the caller can fall back to its own table."""
    if not text:
        return None
    low = f" {text.lower()} "
    problems = _doc().get("problems")
    if not isinstance(problems, dict):
        return None
    for problem, spec in problems.items():
        for trig in (spec or {}).get("triggers") or []:
            if str(trig).lower() in low:
                return str(problem)
    return None


# --- Detection: what each routing key MEANS -------------------------------------


def step_options(verdict: str | None, step_id: str | None) -> dict[str, str] | None:
    """{routing key -> plain-language MEANING} for one step, or None when undeclared
    (caller falls back to the generic per-detector glosses in code)."""
    if not verdict or not step_id:
        return None
    for step in _expanded_steps(verdict):
        if isinstance(step, dict) and step.get("id") == step_id:
            answers = step.get("answers")
            if isinstance(answers, dict) and answers:
                return {str(k): str(v) for k, v in answers.items()}
            return None
    return None


def problem_has_path(problem: str | None) -> bool:
    """Does ANY fault pack declare a solving path for this reported problem
    (`problem:` field)? A sprendzia-classified problem WITHOUT one is an
    UNCLEAR fault (Andrius 2026-09-03): an identified customer gets an honest
    'neaiškus gedimas' ticket instead of a wrong-domain improvisation (live:
    a TV call was walked down the internet client-side pack)."""
    if not problem:
        return False
    return any(
        isinstance(spec, dict) and spec.get("problem") == problem for spec in _faults().values()
    )


def problem_entry(problem: str | None) -> dict[str, Any]:
    """The classification-catalog entry for a PROBLEM type (problems: section)."""
    if not problem:
        return {}
    entry = (_doc().get("problems") or {}).get(problem)
    return entry if isinstance(entry, dict) else {}


def problem_politika(problem: str | None) -> str:
    """The competence policy for a problem type: sprendzia (default) |
    registruoja | nelieciam | pokalbis. Files declare WHAT the agent solves
    (onboarding C blokas); code only enforces the behaviour per policy."""
    v = problem_entry(problem).get("politika")
    return str(v) if v in ("sprendzia", "registruoja", "nelieciam", "pokalbis") else "sprendzia"


def problem_atsakymas(problem: str | None) -> str | None:
    """The scripted boundary reply for a nelieciam/pokalbis type."""
    v = problem_entry(problem).get("atsakymas")
    return str(v) if v else None


def problem_patvirtinimas(problem: str | None) -> str | None:
    """The explicit-confirmation question for a medium-confidence LLM guess."""
    v = problem_entry(problem).get("patvirtinimas")
    return str(v) if v else None


def problem_catalog_options() -> dict[str, str]:
    """{type: human meaning} for the L2 LLM classifier — built from each
    entry's `aprasymas` (+ a couple of `pavyzdziai`). Only entries WITH an
    aprasymas participate (a triggers-only legacy entry stays L1-only)."""
    out: dict[str, str] = {}
    for name, entry in (_doc().get("problems") or {}).items():
        if not isinstance(entry, dict):
            continue
        desc = entry.get("aprasymas")
        if not desc:
            continue
        pvz = [str(x) for x in (entry.get("pavyzdziai") or [])[:2]]
        out[str(name)] = str(desc) + (f" (pvz.: {'; '.join(pvz)})" if pvz else "")
    return out


def playbook(verdict: str | None) -> str | None:
    """The RAG doc holding this fault's step wording."""
    if not verdict:
        return None
    return (_faults().get(verdict) or {}).get("playbook")


# --- Procedure: the steps themselves --------------------------------------------


@cache
def build_strategy(verdict: str):
    """Build a Strategy from the manifest, or None if this fault is not declared there
    (the caller then uses the in-code registry). Built objects are the SAME dataclasses
    the walker already consumes, so nothing downstream changes."""
    spec = _faults().get(verdict)
    if not isinstance(spec, dict) or not spec.get("steps"):
        return None
    try:
        from .resolution import Step, StepKind, Strategy

        steps = []
        for raw in _expanded_steps(verdict):
            steps.append(
                Step(
                    id=str(raw["id"]),
                    kind=StepKind(str(raw["kind"])),
                    hint=str(raw.get("hint", "")),
                    tikslas=str(raw.get("tikslas", "")),
                    tools=frozenset(raw.get("tools") or ()),
                    tool_actions=tuple(raw.get("tool_actions") or ()),
                    rag_section=raw.get("rag_section"),
                    detector=str(raw.get("detector", "")),
                    on={str(k): str(v) for k, v in (raw.get("on") or {}).items()},
                    goto=str(raw.get("goto", "")),
                    consent=bool(raw.get("consent", True)),
                )
            )
        return Strategy(
            verdict=verdict,
            rag_doc=str(spec.get("playbook", "")),
            steps=tuple(steps),
        )
    except Exception as e:  # a malformed entry must not break the call
        logger.warning(f"faults.yaml: cannot build strategy for {verdict} ({e})")
        return None

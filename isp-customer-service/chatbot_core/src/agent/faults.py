"""
Fault knowledge loader — the declarative layer (Phase 3.8 step 5b/5c).

Reads `agent/knowledge/faults.yaml` — the call's PURPOSE catalog (what the CALLER
reports) — and the fault packs in `agent/knowledge/faults/`: each CAUSE the telemetry
can reach, its playbook and its procedure (steps: kind, role, detector, routing,
rag section, hint, and what each routing key MEANS).

Why: the procedure and the answer meanings used to live in Python. Moving them here makes a new fault — or a
reworded check — a FILE edit rather than a code change, which is the whole point of the
migration. Code keeps the mechanism and the safety enforcement.

Files are read through contract.loader, which validates them all at startup: a bad
edit stops the app with a readable error instead of misbehaving in a call.
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
    """The problem catalog (faults.yaml)."""
    from .contract.loader import read_yaml

    data = read_yaml(_FAULTS_PATH) or {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _dir_faults() -> dict[str, Any]:
    """Fault PACKS — one file per fault in knowledge/faults/ (R5: 'įkelti naują
    gedimą' = drop a file in). A pack overrides a same-named monolith entry."""
    from .contract.loader import read_yaml_dir

    return read_yaml_dir(_FAULTS_DIR, "verdict")


@lru_cache(maxsize=1)
def _modules() -> dict[str, Any]:
    """Reusable instruction MODULES (knowledge/modules/): named step sequences
    with declared exits that packs compose via `use:` — the same
    procedure (bind a MAC, verify restored) is written ONCE."""
    from .contract.loader import read_yaml_dir

    return read_yaml_dir(_MODULES_DIR, "module")


def _faults() -> dict[str, Any]:
    return _dir_faults()


# Step roles the engine acts on (D-18). Each is unique within a pack; every other
# role only names the step for people and the dashboard.
ENGINE_ROLES = frozenset(
    {
        "escalate",
        "verify_restored",
        "client_side_check",
        "verify_reboot",
        "reboot_retry",
        "device_path",
        "verify_line",
        "verify_device_visible",
        "bind_device",
        "locate_cable",
        "register_after_bridge",
        "confirm_device_change",
        "ability_check",
        "locate_device",
        "homework",
    }
)
# The pack's own cannot-now handling ("can you get to the router now?").
CANNOT_NOW_ROLES = frozenset({"ability_check", "locate_device", "homework"})

_VERDICTS_PATH = _KNOWLEDGE / "verdicts.yaml"
_FLAG_DEFAULTS: dict[str, Any] = {
    "unresolved_after_fix": False,
    "line_fault": False,
    "device_visible": True,
    "healthy_up_to_router": False,
    "inform": None,
    "auto_ticket": False,
}


@lru_cache(maxsize=1)
def _verdict_flags() -> dict[str, dict[str, Any]]:
    from .contract.loader import read_yaml

    return read_yaml(_VERDICTS_PATH) or {}


def verdict_flag(verdict: str | None, name: str) -> Any:
    """A verdict's flag from knowledge/verdicts.yaml (the default when unset)."""
    if name not in _FLAG_DEFAULTS:
        raise KeyError(f"unknown verdict flag '{name}'")
    return (_verdict_flags().get(verdict or "") or {}).get(name, _FLAG_DEFAULTS[name])


def step_by_role(verdict: str | None, role: str):
    """The verdict's procedure step with `role`, or None."""
    from .resolution import get_strategy

    strat = get_strategy(verdict)
    return strat.by_role(role) if strat else None


def role_of(verdict: str | None, step_id: str | None) -> str | None:
    """The role of a step id in the verdict's procedure (None when unknown)."""
    from .resolution import get_strategy

    strat = get_strategy(verdict)
    step = strat.step(step_id or "") if strat else None
    return step.role if step else None


def reload() -> None:
    """Drop the derived caches (contract.loader.reload calls this)."""
    _doc.cache_clear()
    _verdict_flags.cache_clear()
    _dir_faults.cache_clear()
    _modules.cache_clear()
    _expanded_steps.cache_clear()
    build_strategy.cache_clear()


# --- Module expansion (compile-time composition) ---------------------------------


@lru_cache(maxsize=32)
def _expanded_steps(verdict: str) -> tuple[dict[str, Any], ...]:
    """The fault's steps with every `use:` module call EXPANDED inline.

    Rules (docs/FAULT_PACKS.md): a single-step module's step id becomes the
    instance name (`as:`); a multi-step module's ids become `<as>_<id>`.
    Module-declared exits route through the instance's `on:` map;
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
        instance = str(raw.get("as") or raw["use"])
        if not isinstance(mod, dict) or not mod.get("steps"):
            logger.warning(f"{verdict}: unknown module '{raw.get('use')}' — skipped")
            continue
        msteps = [dict(m) for m in mod["steps"] if isinstance(m, dict)]
        exits = {str(x) for x in (mod.get("exits") or [])}
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
                for key in ("hint", "rag_section", "answers", "detector", "goal", "role"):
                    if raw.get(key) is not None:
                        m[key] = raw[key]
            out.append(m)
    return tuple(out)


# --- Meta / discovery -------------------------------------------------------------


def fault_meta(verdict: str | None) -> dict[str, Any]:
    """The pack's meta block (title, domain, driver)."""
    if not verdict:
        return {}
    meta = (_faults().get(verdict) or {}).get("meta")
    return meta if isinstance(meta, dict) else {}


def driver(verdict: str | None) -> str | None:
    """meta.driver — who drives this fault's turns: "solver" (the evidence-drive +
    solver own the flow) or "walker" (the step tree; default). Temporary: M4
    makes the solver the only driver (D-03)."""
    v = fault_meta(verdict).get("driver")
    return str(v) if v in ("solver", "walker") else None


# --- Purpose: what the CALLER reports -------------------------------------------


def classify_purpose(text: str | None) -> str | None:
    """The reported problem type from the utterance, using the manifest's triggers.
    Order matters (a specific problem before a broader one), which YAML preserves.
    Returns None when nothing matches, so the caller can fall back to its own table."""
    if not text:
        return None
    from .contract.locale import vocab

    low = f" {text.lower()} "
    problems = _doc().get("problems")
    if not isinstance(problems, dict):
        return None
    for problem, spec in problems.items():
        name = (spec or {}).get("triggers_vocab")
        for trig in vocab(name) if name else ():
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
                from .contract.locale import phrase

                return {str(k): phrase(str(v)) for k, v in answers.items()}
            return None
    return None


def problem_has_path(problem: str | None) -> bool:
    """Does ANY fault pack declare a solving path for this reported problem
    (`problem:` field)? A solve-policy problem WITHOUT one is an
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


BOUNDARY_POLICIES = frozenset({"not_ours", "chat"})


def problem_policy(problem: str | None) -> str:
    """The competence policy for a problem type: solve (default) | register |
    not_ours | chat. Files declare WHAT the agent solves; code only enforces the
    behaviour per policy."""
    v = problem_entry(problem).get("policy")
    return str(v) if v in ("solve", "register", "not_ours", "chat") else "solve"


def problem_boundary_reply(problem: str | None) -> str | None:
    """The scripted boundary reply for a not_ours / chat type."""
    from .contract.locale import maybe_phrase

    return maybe_phrase(problem_entry(problem).get("boundary_reply_key"))


def problem_confirm_question(problem: str | None) -> str | None:
    """The explicit-confirmation question for a medium-confidence LLM guess."""
    from .contract.locale import maybe_phrase

    return maybe_phrase(problem_entry(problem).get("confirm_question_key"))


def problem_catalog_options() -> dict[str, str]:
    """{type: meaning} for the L2 LLM classifier — each entry's `description`
    plus a couple of the locale's example phrasings. Only entries WITH a
    description participate (a triggers-only entry stays L1-only)."""
    from .contract.locale import examples

    out: dict[str, str] = {}
    for name, entry in (_doc().get("problems") or {}).items():
        if not isinstance(entry, dict):
            continue
        desc = entry.get("description")
        if not desc:
            continue
        key = entry.get("examples_key")
        samples = [ln for ln in examples(key).splitlines() if ln.strip()][:2] if key else []
        out[str(name)] = str(desc) + (f" (e.g.: {'; '.join(samples)})" if samples else "")
    return out


def pack_verdicts() -> frozenset[str]:
    """Every verdict a loaded fault pack declares (the solver's known hypotheses)."""
    return frozenset(_faults())


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
        from .contract.locale import expand_examples
        from .resolution import Step, StepKind, Strategy

        steps = []
        for raw in _expanded_steps(verdict):
            steps.append(
                Step(
                    id=str(raw["id"]),
                    kind=StepKind(str(raw["kind"])),
                    role=str(raw.get("role", "")),
                    hint=expand_examples(str(raw.get("hint", ""))),
                    goal=expand_examples(str(raw.get("goal", ""))),
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
            rag_doc=spec.get("playbook") or None,
            steps=tuple(steps),
        )
    except Exception as e:  # a malformed entry must not break the call
        logger.warning(f"faults.yaml: cannot build strategy for {verdict} ({e})")
        return None

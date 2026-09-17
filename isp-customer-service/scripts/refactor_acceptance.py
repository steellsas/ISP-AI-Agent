"""Acceptance checks of the single-engine refactor (docs/refactoring/M0…M7), in one run.

Each milestone's Definition of Done had "this grep returns nothing" / "these files are
gone" checks. They are kept here so a later change that brings something back is caught.
A match the owner accepted is a DEVIATION (reported, not a failure).

    uv run python scripts/refactor_acceptance.py          # exit 1 on any FAIL
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "chatbot_core"
SRC = CORE / "src"
AGENT = SRC / "agent"
SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".pytest_cache", "logs"}
LT_LETTERS = re.compile(r"[ąčęėįšųūžĄČĘĖĮŠŲŪŽ]")


@dataclass
class Check:
    milestone: str
    name: str
    pattern: str
    roots: list[Path]
    exts: tuple[str, ...] = (".py",)
    # Paths (relative to the repo root, prefix match) where a match is expected.
    allowed: tuple[str, ...] = ()
    # Paths where a match is an owner-accepted deviation, with the reason.
    deviations: dict[str, str] = field(default_factory=dict)


def _files(roots: list[Path], exts: tuple[str, ...]):
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.suffix in exts and not (SKIP_DIRS & set(path.parts)) and path.is_file():
                yield path


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


CHECKS = [
    Check(
        "M1",
        "legacy engines and state are gone",
        r"AGENT_ENGINE|AgentState|_LEGACY_FIELDS|sync_updates|to_legacy|from_legacy|run_until_response|agent\.graph\b",
        [SRC, CORE / "tests"],
    ),
    Check(
        "M2",
        "tool calls go through the one gateway",
        r"execute_tool\(|from crm_mcp|from network_diagnostic_mcp",
        [SRC],
        allowed=("chatbot_core/src/agent/tooling/", "chatbot_core/src/agent/tools.py"),
    ),
    Check(
        "M3",
        "no hardcoded step ids outside knowledge",
        # step ids / suffixes; a role name such as `client_side_check` is not a step id
        r"\b(rh_check|rh_device|rh_reboot_retry|ll_recheck|crc_recheck|dr_see_device|dr_bind|dr_pick_cable|dr_register_router|confirm_restored|confirm_change|client_side)\b|\w+_(ability|locate|homework)\b",
        [SRC],
    ),
    Check(
        "M3",
        "no Lithuanian schema keys in code",
        r"\b(vairuotojas|patvirtinta_kai|paneigta_kai|paneigta_veda|sprendimai|reikalinga|pasiulymas|tiltas_nepavyko|isejimai|modulis|politika|aprasymas|sakoma|raktazodziai|tesiniai)\b",
        [SRC],
    ),
    Check(
        "M3",
        "in-code strategy and phrase tables are gone",
        r"STRATEGIES =|DETECTOR_GLOSSES|_PHRASES_DEFAULTS|_PROBLEM_KEYWORDS",
        [SRC],
    ),
    Check(
        "M4",
        "old drivers and registries are gone",
        r"\bdriver\b|vairuotojas|SOLVER_DRIVE|SOLVER_SHADOW|walker_owns_turn|open_hypothesis|_refute_state|dialog_registry",
        [SRC],
    ),
    Check(
        "M5",
        "ReactAgent and the narrator flow are gone",
        r"ReactAgent|react_agent|narrator_flow|state_facts_block|LOOKUP_TOOLS|NARRATOR_QUESTIONS",
        [SRC, CORE / "tests"],
        deviations={
            "chatbot_core/": "NARRATOR_QUESTIONS stays until the prompt/wording pass (owner 2026-09-16)",
        },
    ),
    Check(
        "M6",
        "proactive outage and the fixed technician ticket are gone",
        r"PROACTIVE OUTAGE|preflight_outage|amend_ticket_note|\"technician_visit\",\s*\"high\"",
        [SRC],
    ),
]

M0_DELETED = [
    "chatbot_core/src/agent/graph_v2/nodes/perception.py",
    "chatbot_core/src/agent/graph_v2/nodes/diagnosis/evidence_drive.py",
    "chatbot_core/src/services/mcp_service.py",
    "chatbot_core/src/services/custom_mcp_client.py",
    "chatbot_core/src/services/crm.py",
    "chatbot_core/src/services/network.py",
    "chatbot_core/src/services/llm/cache.py",
    "chatbot_core/src/services/llm/utils.py",
    "chatbot_core/test_mcp_simple.py",
    "chatbot_core/voice_demo.py",
    "chatbot_core/src/adapters/transport/fastrtc_stream.py",
    "chatbot_core/src/ports/transport.py",
    "chatbot_core/src/streamlit_ui",
    "chatbot_core/src/config/__init__.py",
    "chatbot_core/src/agent/prompts/greeting.txt",
    "chatbot_core/src/agent/prompts/partials/consultation.md",
    "chatbot_core/src/agent/prompts/partials/understanding.md",
    # later milestones
    "chatbot_core/src/agent/session_record.py",
    "chatbot_core/src/agent/knowledge/faults.yaml",
]

M7_FILES = [
    "chatbot_core/src/app/static/index.html",
    "chatbot_core/src/app/static/app.css",
    "chatbot_core/src/app/static/js/layout.js",
    "chatbot_core/src/app/static/js/brain.js",
    "chatbot_core/src/app/static/js/voiceviz.js",
    "chatbot_core/src/app/static/js/scenarios.js",
    "chatbot_core/src/app/static/js/archive.js",
    "chatbot_core/src/app/scenarios.yaml",
    "chatbot_core/src/agent/call_record/finalizer.py",
    "chatbot_core/src/agent/call_record/outcome.py",
    "chatbot_core/src/agent/knowledge/intents.yaml",
    "chatbot_core/src/agent/knowledge/ticket_types.yaml",
    "chatbot_core/src/agent/knowledge/services.yaml",
]


def run_grep(check: Check) -> tuple[str, list[str]]:
    rx = re.compile(check.pattern)
    hits, deviations = [], []
    for path in _files(check.roots, check.exts):
        rel = _rel(path)
        if any(rel.startswith(a) for a in check.allowed):
            continue
        for n, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if rx.search(line):
                entry = f"{rel}:{n}: {line.strip()[:110]}"
                reason = next((r for p, r in check.deviations.items() if rel.startswith(p)), None)
                (deviations if reason else hits).append(entry)
    if hits:
        return "FAIL", hits
    if deviations:
        reason = next(iter(check.deviations.values()))
        return "DEVIATION", [f"{len(deviations)} match(es) — {reason}"]
    return "PASS", []


def lithuanian_strings_in_code() -> tuple[str, list[str]]:
    """M3: caller-facing words live in locales/, not in Python string literals (docstrings and
    comments may quote callers). Still OPEN after M7 — the remaining Lithuanian directive
    strings are listed in docs/refactoring/ROADMAP.md; this check reports them without
    failing the run until that item is done."""
    hits = []
    for path in _files([AGENT], (".py",)):
        rel = _rel(path)
        if "/locales/" in rel:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                ):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and LT_LETTERS.search(node.value)
            ):
                hits.append(f"{rel}:{node.lineno}: {node.value.strip()[:80]!r}")
    return (
        ("PASS", [])
        if not hits
        else ("OPEN", [f"{len(hits)} string literal(s) — ROADMAP R-3"] + hits)
    )


def main() -> int:
    rows: list[tuple[str, str, str, list[str]]] = []
    gone = [p for p in M0_DELETED if (ROOT / p).exists()]
    rows.append(("M0", "deleted dead code stays deleted", "FAIL" if gone else "PASS", gone))
    for check in CHECKS:
        status, details = run_grep(check)
        rows.append((check.milestone, check.name, status, details))
    status, details = lithuanian_strings_in_code()
    rows.append(("M3", "no Lithuanian string literals in agent code", status, details))
    missing = [p for p in M7_FILES if not (ROOT / p).exists()]
    rows.append(
        ("M6-M7", "new modules and dashboard files exist", "FAIL" if missing else "PASS", missing)
    )

    failed = 0
    for milestone, name, status, details in rows:
        print(f"[{status:9}] {milestone:6} {name}")
        for d in details[:12]:
            print(f"             {d}")
        if len(details) > 12:
            print(f"             … {len(details) - 12} more")
        failed += status == "FAIL"
    print(f"\n{len(rows) - failed}/{len(rows)} checks without failures")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

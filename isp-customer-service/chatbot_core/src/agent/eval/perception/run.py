"""Perception eval — is the READING right? (wave 2a, review finding AR)

The conversation eval scores whole calls; this one scores the one thing every call
depends on: what the agent understood from a single utterance. It replays cases through
`perceive.perception.read_turn` with the REAL model and compares the reading with the
case's expectation — the turn type and the canonical facts.

This is the measurement that makes the model, the prompt and the prompt LANGUAGE
comparable (P-5): run it, change one thing, run it again.

Two case files:
  cases.json           BASELINE — what the system read on recorded calls. Unreviewed:
                       it locks today's behaviour, gaps included, so a DROP here is a
                       regression, while a difference may be an improvement.
  cases_reviewed.json  CURATED — expectations a human confirmed. These must pass.

Usage (needs LLM keys in .env):
    cd chatbot_core
    uv run python src/agent/eval/perception/run.py                  # both files
    uv run python src/agent/eval/perception/run.py --only reviewed  # curated only
    uv run python src/agent/eval/perception/run.py --limit 20 --json report.json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_SRC = _DIR.parents[2]  # chatbot_core/src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

FILES = {"baseline": _DIR / "cases.json", "reviewed": _DIR / "cases_reviewed.json"}


def _load(which: str) -> list[dict]:
    path = FILES[which]
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [dict(case, _set=which) for case in data.get("cases", [])]


def _state_for(case: dict):
    """A call in the position the case describes: a verdict (so the fault's evidence
    spec is live) and an identified caller."""
    from agent.resolution import get_strategy
    from agent.runtime import new_call

    state, rt = new_call(case.get("phone", "+37060012353"), "lt")
    state.identity.customer_id = case.get("customer_id", "CUST009")
    state.intake.problem_type = (case.get("context") or {}).get("problem") or "internet_down"
    verdict = (case.get("context") or {}).get("verdict")
    if verdict:
        strategy = get_strategy(verdict)
        if strategy is not None:
            state.resolution.procedure = {"verdict": verdict, "step": strategy.steps[0].id}
        state.diagnosis.verdicts["network"] = {"reason": verdict}
    pending = (case.get("context") or {}).get("pending")
    if pending:
        state.diagnosis.pending_evidence_key = pending
    state.dialog.last_question = (case.get("context") or {}).get("question") or ""
    state.dialog.last_heard = case["utterance"]
    return state, rt


def _score(case: dict, read) -> dict:
    """What the reading got right: the turn type and the facts (exact values)."""
    want = case.get("expect") or {}
    want_facts = {k: str(v) for k, v in (want.get("facts") or {}).items()}
    got_facts = read.values() if read is not None else {}
    missing = {k: v for k, v in want_facts.items() if got_facts.get(k) != v}
    extra = {k: v for k, v in got_facts.items() if k not in want_facts}
    type_ok = (not want.get("turn_type")) or (
        read is not None and read.turn_type == want["turn_type"]
    )
    return {
        "utterance": case["utterance"],
        "set": case["_set"],
        "source": getattr(read, "source", None),
        "type_ok": type_ok,
        "facts_ok": not missing,
        "missing": missing,
        "extra": extra,
        "ok": type_ok and not missing,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Perception eval — the reading, scored")
    ap.add_argument("--only", choices=sorted(FILES), help="one case file")
    ap.add_argument("--limit", type=int, help="first N cases")
    ap.add_argument("--json", help="write the raw report here")
    args = ap.parse_args()
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")

    from agent.eval.run_eval import _bump_rate_limits, _load_env

    _load_env()
    from agent.contract import loader

    loader.startup()
    from agent.perceive.perception import read_turn

    cases = _load(args.only) if args.only else _load("reviewed") + _load("baseline")
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No cases.")
        return 2

    results = []
    for case in cases:
        _bump_rate_limits()
        state, rt = _state_for(case)
        try:
            read = read_turn(state, rt, case["utterance"])
        except Exception as e:  # a crash IS a finding
            results.append({"utterance": case["utterance"], "set": case["_set"], "error": str(e)})
            continue
        results.append(_score(case, read))

    return _report(results, args.json)


def _report(results: list[dict], json_path: str | None) -> int:
    by_set: dict[str, list[dict]] = {}
    for r in results:
        by_set.setdefault(r["set"], []).append(r)
    print(f"\n{'=' * 78}\nPERCEPTION EVAL — the reading, scored\n{'=' * 78}")
    reviewed_failed = 0
    for name, rows in by_set.items():
        ok = sum(1 for r in rows if r.get("ok"))
        fast = sum(1 for r in rows if r.get("source") == "fast_path")
        print(f"\n[{name}] {ok}/{len(rows)} readings match · fast path: {fast}")
        for r in rows:
            if r.get("ok"):
                continue
            if name == "reviewed":
                reviewed_failed += 1
            detail = r.get("error") or f"missing={r.get('missing')} extra={r.get('extra')}"
            print(f"    XXX {r['utterance'][:60]!r}: {detail}")
    print(f"\n{'-' * 78}\n  curated failures: {reviewed_failed}\n{'-' * 78}\n")
    if json_path:
        Path(json_path).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Report written to {json_path}")
    return 1 if reviewed_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""What an eval run COST and how STABLE it was — the yardstick for prompt changes (v3 stage 6).

Pass/fail alone does not say whether a prompt change helped: a shorter prompt may pass the same
scenarios and still be slower, longer-winded or less stable. This reads the report that
`run_eval.py --json` writes (and the trace of every scenario in it) and prints:

  * per LLM role (perception, speak, analyst …): calls, input / output tokens, latency median / p90
  * replies: how many the engine wrote and how many the LLM spoke, their length (mean / max)
  * scenarios: passed, failed, and UNSTABLE (passed in one run, failed in another)
  * perception stability: the same caller sentence, read in every run — how often the readings
    disagree (needs `--runs 2` or more)

    uv run python src/agent/eval/metrics.py ../logs/eval_base.json
    uv run python src/agent/eval/metrics.py ../logs/eval_base.json --compare ../logs/eval_6c.json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def _events(trace: str | None) -> list[dict]:
    if not trace or not Path(trace).exists():
        return []
    out = []
    for line in Path(trace).read_text(encoding="utf-8").splitlines():
        with contextlib.suppress(ValueError):
            out.append(json.loads(line))
    return out


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


def measure(report_path: str) -> dict:
    """The numbers of one eval report."""
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    roles: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    replies: list[int] = []
    kinds: dict[str, int] = defaultdict(int)
    outcomes: dict[str, list[bool]] = defaultdict(list)
    readings: dict[tuple[str, int], list[str]] = defaultdict(list)
    for row in report:
        outcomes[row["id"]].append(all(c["pass"] for c in row["checks"]))
        turn = 0
        for e in _events(row.get("trace")):
            kind = e.get("type")
            if kind == "llm":
                role = roles[str(e.get("role") or "?")]
                role["in"].append(e.get("input_tokens") or 0)
                role["out"].append(e.get("output_tokens") or 0)
                role["ms"].append(e.get("latency_ms") or 0)
            elif kind == "agent_reply" and e.get("text"):
                replies.append(len(e["text"]))
            elif kind == "turn_plan":
                kinds[str((e.get("say") or {}).get("kind") or "?")] += 1
            elif kind == "user_turn":
                turn += 1
            elif kind == "perception" and e.get("source") == "llm":
                step = e.get("step") or {}
                facts = e.get("facts") or {}
                readings[(row["id"], turn)].append(
                    json.dumps([step.get("label"), facts], sort_keys=True, ensure_ascii=False)
                )
    runs = max((r.get("run", 1) for r in report), default=1)
    compared = {k: v for k, v in readings.items() if len(v) >= 2}
    unstable_readings = sum(1 for v in compared.values() if len(set(v)) > 1)
    return {
        "report": report_path,
        "runs": runs,
        "roles": {
            name: {
                "calls": len(v["in"]),
                "in": statistics.mean(v["in"]) if v["in"] else 0,
                "out": statistics.mean(v["out"]) if v["out"] else 0,
                "ms_med": statistics.median(v["ms"]) if v["ms"] else 0,
                "ms_p90": _pct(v["ms"], 0.9),
            }
            for name, v in sorted(roles.items())
        },
        "replies": {
            "count": len(replies),
            "mean": statistics.mean(replies) if replies else 0,
            "max": max(replies, default=0),
            "engine": kinds.get("phrase", 0),
            "llm": kinds.get("directive", 0),
        },
        "scenarios": {
            "total": len(outcomes),
            "passed_every_run": sum(1 for v in outcomes.values() if all(v)),
            "failed_every_run": sorted(k for k, v in outcomes.items() if not any(v)),
            "unstable": sorted(k for k, v in outcomes.items() if any(v) and not all(v)),
        },
        "perception": {
            "sentences_compared": len(compared),
            "read_differently": unstable_readings,
        },
    }


def _print(m: dict) -> None:
    print(f"\n== {m['report']}  (runs: {m['runs']})")
    print(f"{'role':<12}{'calls':>7}{'in tok':>9}{'out tok':>9}{'ms med':>9}{'ms p90':>9}")
    for name, r in m["roles"].items():
        print(
            f"{name:<12}{r['calls']:>7}{r['in']:>9.0f}{r['out']:>9.0f}{r['ms_med']:>9.0f}"
            f"{r['ms_p90']:>9.0f}"
        )
    rp = m["replies"]
    print(
        f"replies: {rp['count']}  engine {rp['engine']} / llm {rp['llm']}  "
        f"length mean {rp['mean']:.0f}  max {rp['max']}"
    )
    sc = m["scenarios"]
    print(
        f"scenarios: {sc['passed_every_run']}/{sc['total']} passed every run; "
        f"unstable {len(sc['unstable'])} {sc['unstable']}; failed {sc['failed_every_run']}"
    )
    pc = m["perception"]
    if pc["sentences_compared"]:
        print(
            f"perception: {pc['read_differently']}/{pc['sentences_compared']} sentences read "
            "differently across runs"
        )


def _print_compare(a: dict, b: dict) -> None:
    print(f"\n== {a['report']}  ->  {b['report']}")
    print(f"{'role':<12}{'in tok':>16}{'out tok':>14}{'ms med':>16}{'ms p90':>16}")
    for name in sorted(set(a["roles"]) | set(b["roles"])):
        ra, rb = a["roles"].get(name), b["roles"].get(name)
        if not ra or not rb:
            continue
        print(
            f"{name:<12}"
            f"{ra['in']:>7.0f}->{rb['in']:<7.0f}"
            f"{ra['out']:>6.0f}->{rb['out']:<6.0f}"
            f"{ra['ms_med']:>7.0f}->{rb['ms_med']:<7.0f}"
            f"{ra['ms_p90']:>7.0f}->{rb['ms_p90']:<7.0f}"
        )
    pa, pb = a["replies"], b["replies"]
    print(f"reply length mean {pa['mean']:.0f} -> {pb['mean']:.0f}, max {pa['max']} -> {pb['max']}")
    sa, sb = a["scenarios"], b["scenarios"]
    print(
        f"passed every run {sa['passed_every_run']}/{sa['total']} -> "
        f"{sb['passed_every_run']}/{sb['total']}; unstable {len(sa['unstable'])} -> "
        f"{len(sb['unstable'])}"
    )
    newly = sorted(
        set(sb["unstable"] + sb["failed_every_run"]) - set(sa["unstable"] + sa["failed_every_run"])
    )
    if newly:
        print(f"NEW trouble: {newly}")
    ca, cb = a["perception"], b["perception"]
    if ca["sentences_compared"] and cb["sentences_compared"]:
        print(
            f"perception read differently {ca['read_differently']}/{ca['sentences_compared']} -> "
            f"{cb['read_differently']}/{cb['sentences_compared']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Cost and stability of an eval run")
    ap.add_argument("report", help="the --json report of run_eval.py")
    ap.add_argument("--compare", help="a second report to compare against the first")
    args = ap.parse_args()
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")
    first = measure(args.report)
    _print(first)
    if args.compare:
        second = measure(args.compare)
        _print(second)
        _print_compare(first, second)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

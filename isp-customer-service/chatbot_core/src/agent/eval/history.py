"""
Eval run history — one JSONL line per `run_eval.py` run, tagged with what it ran on.

`run_eval.py` appends a line after every run (see `record_from_results`); this module reads
the file back so a flaky scenario can be told apart from a regression:

    python chatbot_core/src/agent/eval/history.py list [-n 10]
    python chatbot_core/src/agent/eval/history.py flaky [--last N] [--all]
    python chatbot_core/src/agent/eval/history.py diff [A] [B]        # default: -2 -1
    python chatbot_core/src/agent/eval/history.py import logs/eval_*.json

Run numbers are the `#` column of `list` (1 = oldest); negative numbers count from the end.
Every command takes `--file PATH` (default: `logs/eval/history.jsonl`). Standard library only,
no LLM, no agent imports — safe to run anywhere.

Line format (`schema` 1):
    {"schema": 1, "ts": ISO-8601, "source": "run" | "import:<file name>",
     "versions": call_versions() | {"code": "unknown"},
     "args": {"only", "runs", "voice", "no_db"},
     "summary": {"scenarios", "runs", "results", "passed", "checks_pass", "checks_total",
                 "hard_fails", "exit_code"},
     "results": [{"id", "run", "known_bug", "pass", "checks": {name: bool}}]}
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = 1
HISTORY_PATH = Path(__file__).resolve().parents[4] / "logs" / "eval" / "history.jsonl"


# --- Writing -------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def summarize(results: list[dict], exit_code: int | None = None) -> dict[str, Any]:
    """Totals over normalized results (`{id, run, known_bug, pass, checks}`).

    A scenario is a hard failure when any of its runs failed and it is not a known bug —
    the same gate `run_eval.py` applies to its exit code."""
    ids = list(dict.fromkeys(r["id"] for r in results))
    hard = {r["id"] for r in results if not r["pass"] and not r.get("known_bug", False)}
    return {
        "scenarios": len(ids),
        "runs": max((r["run"] for r in results), default=0),
        "results": len(results),
        "passed": sum(1 for r in results if r["pass"]),
        "checks_pass": sum(sum(1 for ok in r["checks"].values() if ok) for r in results),
        "checks_total": sum(len(r["checks"]) for r in results),
        "hard_fails": len(hard),
        "exit_code": exit_code,
    }


def make_record(
    results: list[dict],
    *,
    source: str,
    versions: dict[str, Any],
    args: dict[str, Any],
    exit_code: int | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ts": ts or now_iso(),
        "source": source,
        "versions": versions,
        "args": args,
        "summary": summarize(results, exit_code),
        "results": results,
    }


def record_from_results(
    results: list[dict],
    *,
    args: dict[str, Any],
    versions: dict[str, Any],
    exit_code: int,
    ts: str | None = None,
) -> dict[str, Any]:
    """One history line from `run_eval.py`'s in-memory results (`{scn, checks, run}`).

    Check details stay out of the history (they are in `--json` and the trace)."""
    rows = [
        {
            "id": r["scn"]["id"],
            "run": r["run"],
            "known_bug": bool(r["scn"].get("known_bug", False)),
            "pass": all(ok for _, ok, _ in r["checks"]),
            "checks": {name: bool(ok) for name, ok, _ in r["checks"]},
        }
        for r in results
    ]
    return make_record(rows, source="run", versions=versions, args=args, exit_code=exit_code, ts=ts)


def record_from_report(path: Path) -> dict[str, Any]:
    """One history line from an old `run_eval.py --json` report. The version is unknown;
    the time is the file's modification time (the names do not carry a date)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [
        {
            "id": e["id"],
            "run": int(e.get("run", 1)),
            "known_bug": bool(e.get("known_bug", False)),
            "pass": all(c["pass"] for c in e["checks"]),
            "checks": {c["name"]: bool(c["pass"]) for c in e["checks"]},
        }
        for e in data
    ]
    ts = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    ids = {r["id"] for r in rows}
    return make_record(
        rows,
        source=f"import:{path.name}",
        versions={"code": "unknown"},
        args={
            "only": next(iter(ids)) if len(ids) == 1 else None,
            "runs": max((r["run"] for r in rows), default=1),
            "voice": any(e.get("voice", False) for e in data),
            "no_db": None,
        },
        ts=ts,
    )


def append(record: dict[str, Any], path: Path = HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# --- Reading -------------------------------------------------------------------------
def _when(rec: dict) -> datetime:
    try:
        return datetime.fromisoformat(rec["ts"])
    except (KeyError, TypeError, ValueError):
        return datetime.min.astimezone()


def load(path: Path = HISTORY_PATH) -> list[dict]:
    """All records, oldest first. A line that does not parse is skipped with a warning."""
    if not path.exists():
        return []
    records = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            print(f"warning: {path.name}:{n} is not valid JSON — skipped", file=sys.stderr)
            continue
        if isinstance(rec, dict) and isinstance(rec.get("results"), list):
            records.append(rec)
    return sorted(records, key=_when)


def _pick(records: list[dict], number: int) -> tuple[int, dict]:
    """Run `number` as `list` shows it (1 = oldest; negative counts from the end)."""
    idx = number - 1 if number > 0 else len(records) + number
    if not 0 <= idx < len(records) or number == 0:
        raise SystemExit(f"no run #{number} (history has {len(records)})")
    return idx + 1, records[idx]


def _label(rec: dict) -> str:
    return rec.get("source", "run")


def _short(value: Any) -> str:
    return "-" if value in (None, "") else str(value)


# --- Commands ------------------------------------------------------------------------
def cmd_list(records: list[dict], n: int) -> None:
    shown = list(enumerate(records, 1))[-n:] if n > 0 else list(enumerate(records, 1))
    print(
        f"{'#':>3}  {'when':<16}  {'source':<30} {'code':<14} {'knowledge':<10} "
        f"{'prompts':<10} {'args':<22} {'passed':>9}  hard"
    )
    for i, rec in shown:
        v, a, s = rec.get("versions", {}), rec.get("args", {}), rec.get("summary", {})
        args = f"runs={a.get('runs', 1)}" + (" voice" if a.get("voice") else "")
        if a.get("only"):
            args += f" only={a['only']}"
        passed = f"{s.get('passed', 0)}/{s.get('results', 0)}"
        print(
            f"{i:>3}  {rec.get('ts', '')[:16].replace('T', ' '):<16}  {_label(rec)[:30]:<30} "
            f"{_short(v.get('code')):<14} {_short(v.get('knowledge')):<10} "
            f"{_short(v.get('prompts')):<10} {args[:22]:<22} {passed:>9}  {s.get('hard_fails', 0)}"
        )
    if not records:
        print("(no runs recorded)")


def scenario_stats(records: list[dict]) -> dict[str, dict]:
    """Per scenario over the given runs: runs, passed, known_bug (latest) and how often
    each check failed."""
    stats: dict[str, dict] = {}
    for rec in records:
        for r in rec["results"]:
            st = stats.setdefault(
                r["id"], {"runs": 0, "passed": 0, "known_bug": False, "failed": {}}
            )
            st["runs"] += 1
            st["passed"] += 1 if r["pass"] else 0
            st["known_bug"] = bool(r.get("known_bug", False))
            for name, ok in r.get("checks", {}).items():
                if not ok:
                    st["failed"][name] = st["failed"].get(name, 0) + 1
    return stats


def cmd_flaky(records: list[dict], show_all: bool) -> None:
    stats = scenario_stats(records)
    rows = [(sid, st) for sid, st in stats.items() if show_all or st["passed"] < st["runs"]]
    rows.sort(key=lambda x: (x[1]["passed"] / x[1]["runs"], x[0]))
    print(f"scenario stability over {len(records)} runs")
    print(f"{'status':<7} {'scenario':<50} {'passed':>8}  {'rate':>5}  failing checks")
    for sid, st in rows:
        p, n = st["passed"], st["runs"]
        status = "STABLE" if p == n else ("FAIL" if p == 0 else "FLAKY")
        top = sorted(st["failed"].items(), key=lambda x: (-x[1], x[0]))[:3]
        checks = ", ".join(f"{name} {k}" for name, k in top)
        tag = " [KNOWN BUG]" if st["known_bug"] else ""
        print(f"{status:<7} {sid:<50} {p:>3}/{n:<4}  {p / n:>5.0%}  {checks}{tag}")
    if not rows:
        print("(every scenario passed every run)")


def _flatten(versions: dict, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in versions.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def cmd_diff(records: list[dict], a: int, b: int) -> None:
    ia, ra = _pick(records, a)
    ib, rb = _pick(records, b)
    print(f"A = #{ia} {ra.get('ts', '')[:16]} {_label(ra)}")
    print(f"B = #{ib} {rb.get('ts', '')[:16]} {_label(rb)}")

    va, vb = _flatten(ra.get("versions", {})), _flatten(rb.get("versions", {}))
    changed = [k for k in sorted(set(va) | set(vb)) if va.get(k) != vb.get(k)]
    print("\nversions:" + ("" if changed else " same"))
    for k in changed:
        print(f"  {k:<20} {_short(va.get(k))} -> {_short(vb.get(k))}")

    sa, sb = scenario_stats([ra]), scenario_stats([rb])
    green = {sid for sid, st in sa.items() if st["passed"] == st["runs"]}
    green_b = {sid for sid, st in sb.items() if st["passed"] == st["runs"]}
    both = sorted(set(sa) & set(sb))

    def rate(st: dict) -> str:
        return f"{st['passed']}/{st['runs']}"

    sections = {
        "broke": [sid for sid in both if sid in green and sid not in green_b],
        "fixed": [sid for sid in both if sid not in green and sid in green_b],
        "still failing": [sid for sid in both if sid not in green and sid not in green_b],
    }
    for title, ids in sections.items():
        print(f"\n{title}: {len(ids)}")
        for sid in ids:
            fa, fb = set(sa[sid]["failed"]), set(sb[sid]["failed"])
            notes = []
            if fb - fa:
                notes.append("now failing: " + ", ".join(sorted(fb - fa)))
            if fa - fb:
                notes.append("recovered: " + ", ".join(sorted(fa - fb)))
            if not notes and fb:
                notes.append("failing: " + ", ".join(sorted(fb)))
            tag = " [KNOWN BUG]" if sb[sid]["known_bug"] else ""
            print(f"  {sid:<50} {rate(sa[sid]):>5} -> {rate(sb[sid]):<5} {'; '.join(notes)}{tag}")

    only_a, only_b = sorted(set(sa) - set(sb)), sorted(set(sb) - set(sa))
    if only_b:
        print(f"\nnew in B: {', '.join(only_b)}")
    if only_a:
        print(f"\nmissing in B: {', '.join(only_a)}")


def cmd_import(paths: list[Path], history: Path) -> None:
    done = {rec.get("source") for rec in load(history)}
    added = 0
    for p in sorted(paths, key=lambda x: x.stat().st_mtime):
        rec = record_from_report(p)
        if rec["source"] in done:
            print(f"skip {p.name} (already imported)")
            continue
        append(rec, history)
        done.add(rec["source"])
        added += 1
        s = rec["summary"]
        print(f"imported {p.name}: {s['passed']}/{s['results']} passed, {rec['ts'][:16]}")
    print(f"{added} imported into {history}")


def main(argv: list[str] | None = None) -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description="Eval run history")
    ap.add_argument("--file", type=Path, default=HISTORY_PATH, help="history JSONL path")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="the last N runs")
    p_list.add_argument("-n", type=int, default=10, help="how many (0 = all)")
    p_flaky = sub.add_parser("flaky", help="per-scenario pass rate over the runs")
    p_flaky.add_argument("--last", type=int, default=0, help="only the last N runs (0 = all)")
    p_flaky.add_argument("--all", action="store_true", help="also list stable scenarios")
    p_diff = sub.add_parser("diff", help="what broke / got fixed between two runs")
    p_diff.add_argument("a", type=int, nargs="?", default=-2)
    p_diff.add_argument("b", type=int, nargs="?", default=-1)
    p_import = sub.add_parser("import", help="add old run_eval.py --json reports")
    p_import.add_argument("reports", type=Path, nargs="+")
    args = ap.parse_args(argv)

    if args.cmd == "import":
        cmd_import(args.reports, args.file)
        return 0
    records = load(args.file)
    if args.cmd == "list":
        cmd_list(records, args.n)
    elif args.cmd == "flaky":
        cmd_flaky(records[-args.last :] if args.last > 0 else records, args.all)
    elif args.cmd == "diff":
        if len(records) < 2:
            print("need at least two runs to compare")
            return 2
        cmd_diff(records, args.a, args.b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

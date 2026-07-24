"""
Conversation eval harness — Golden Dataset (Phase 3.8 step 0).

Drives AgentSession TEXT-TO-TEXT through scripted CLIENT turns and HARD-SCORES the
resulting conversation STATE + replies. The LLM only phrases; the verdict tree and
step walker are deterministic given the scripted turns, so the state trajectory
(verdict reached, disposition, steps) is stable enough to assert on — unlike the
free-form reply text, which we only check for required/forbidden substrings.

This is the safety net REQUIRED before any Phase 3.8 reasoning change lands (see
docs/MASTANTIS_AGENTAS_SPEC.md). Scenarios flagged `known_bug` encode a bug we found
in voice testing and are EXPECTED to fail now — they turn green once the fix lands,
so a regression can never silently return.

Checks per scenario (all optional, only those present are scored):
  - verdict_in    : the expected verdict reason appears at some point
                    (state.hypothesis.cause / resolution.verdict across turns)
  - disposition   : resolved | ticket | outage | inform | open | any
  - reply_any     : at least one agent reply contains EACH listed substring
  - reply_none    : NO agent reply contains ANY listed substring (regression guard)

Usage (needs LLM API keys in .env — like the voice demo):
    cd chatbot_core
    uv run python src/agent/eval/run_eval.py                 # all scenarios
    uv run python src/agent/eval/run_eval.py --only S1_foreign_mac_changed_router
    uv run python src/agent/eval/run_eval.py --no-db          # skip DB rebuild (faster reruns)
    uv run python src/agent/eval/run_eval.py --json report.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Make `agent` / `isp_shared` importable when run as a script from chatbot_core.
_EVAL_DIR = Path(__file__).resolve().parent
_SRC_DIR = _EVAL_DIR.parent.parent  # chatbot_core/src
_PROJECT_ROOT = _SRC_DIR.parents[1]  # isp-customer-service
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

SCENARIOS_PATH = _EVAL_DIR / "scenarios.json"


# --- .env (LLM keys) — the harness drives the REAL model, like voice_demo ---------
def _load_env() -> None:
    # The eval drives simulated calls end-to-end: enable the dead-router bridge device
    # simulation so the bridge can VERIFY + bind (like the update_mac/reset_port stubs).
    os.environ.setdefault("SIMULATE_BRIDGE", "on")
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for env in (_PROJECT_ROOT / ".env", _SRC_DIR.parent / ".env"):
        if env.exists():
            load_dotenv(env, override=False)


# --- DB rebuild — deterministic seed world, fresh per scenario --------------------
# The bind/reset stubs MUTATE the DB, so scenarios must not leak state into each
# other. Rebuilding per scenario is sub-second (pure sqlite3) and mirrors the manual
# "perkrauk DB prieš MAC/tiltą" rule in docs/TESTAVIMO_SCENARIJUS.md.
def _rebuild_db(attempts: int = 3) -> None:
    for script in ("scripts/setup_db.py", "scripts/seed_data.py"):
        last = None
        for _ in range(attempts):
            last = subprocess.run(
                [sys.executable, script],
                cwd=_PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if last.returncode == 0:
                break
            # Windows can transiently fail to delete/recreate the SQLite file if a
            # handle (AV / indexer / a just-exited process) is still open — retry.
            time.sleep(0.5)
        else:
            raise RuntimeError(
                f"{script} failed after {attempts} attempts (exit {last.returncode}):\n"
                f"{(last.stderr or last.stdout or '').strip()}"
            )


def _close_db() -> None:
    """Release the process-held SQLite connection so the NEXT scenario's rebuild can
    delete the file. Without this, the AgentSession from scenario N keeps the DB open
    and scenario N+1's `db_path.unlink()` hits WinError 32 (file in use)."""
    try:
        from database import connection as dbconn

        if dbconn._db_connection is not None:
            dbconn._db_connection.close()
    except Exception:
        pass


def _load_scenarios() -> list[dict]:
    data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    return [s for s in data["scenarios"] if isinstance(s, dict) and "id" in s]


# --- Run one scenario -------------------------------------------------------------
def _run_scenario(scn: dict) -> dict:
    """Drive the scripted turns; snapshot state each turn; return the raw evidence."""
    from agent.session import AgentSession

    session = AgentSession(caller_phone=scn["phone"], language="lt")
    replies: list[str] = []
    verdicts_seen: set[str] = set()

    def _snapshot() -> None:
        st = session.state
        if st.hypothesis and st.hypothesis.get("cause"):
            verdicts_seen.add(st.hypothesis["cause"])
        if st.resolution and st.resolution.get("verdict"):
            verdicts_seen.add(st.resolution["verdict"])

    replies.append(session.greeting())
    _snapshot()
    for turn in scn["turns"]:
        try:
            replies.append(session.handle_turn(turn) or "")
        except Exception as e:  # a crash IS a finding — record, don't abort the suite
            replies.append(f"<<EXCEPTION: {e}>>")
        _snapshot()

    st = session.state
    trace_path = session.tracer.path if hasattr(session.tracer, "path") else None
    session.end_session(outcome="eval")
    _close_db()  # free the file handle before the next scenario's DB rebuild

    tools = _tools_in_trace(trace_path)
    return {
        "replies": replies,
        "verdicts_seen": verdicts_seen,
        "case_closed": st.case_closed,
        "closed_reason": st.closed_reason,
        "customer_id": st.customer_id,
        "outage_reported": getattr(st, "outage_reported", False),
        "ticket_created": "create_ticket" in tools,
        "tools_used": tools,
        "trace": str(trace_path) if trace_path else None,
    }


def _tools_in_trace(trace_path: Path | None) -> set[str]:
    """The set of tool_call names in the session's JSONL trace (create_ticket, update_mac,
    …) — lets a scenario assert an action actually ran, not just that the reply sounded right."""
    tools: set[str] = set()
    if not trace_path or not Path(trace_path).exists():
        return tools
    for line in Path(trace_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "tool_call" and e.get("name"):
            tools.add(e["name"])
    return tools


def _disposition(ev: dict) -> str:
    if ev["ticket_created"]:
        return "ticket"
    if ev["closed_reason"] == "resolved":
        return "resolved"
    if ev["closed_reason"] == "outage" or ev["outage_reported"]:
        return "outage"
    if ev["closed_reason"] == "declined":
        return "declined"
    return "open"


# --- Score one scenario against its expectations ----------------------------------
def _score(scn: dict, ev: dict) -> list[tuple[str, bool, str]]:
    """Return [(check_name, passed, detail)]. Only checks present in expect are run."""
    exp = scn.get("expect", {})
    checks: list[tuple[str, bool, str]] = []
    blob = "\n".join(ev["replies"]).casefold()

    if "verdict_in" in exp:
        want = exp["verdict_in"]
        ok = want in ev["verdicts_seen"]
        checks.append(("verdict", ok, f"want={want} seen={sorted(ev['verdicts_seen']) or '-'}"))

    if "disposition" in exp and exp["disposition"] != "any":
        want = exp["disposition"]
        got = _disposition(ev)
        # 'inform' has no crisp close signal (no ticket, no resolve) — accept open/outage
        ok = got == want or (want == "inform" and got in ("open", "outage"))
        checks.append(("disposition", ok, f"want={want} got={got}"))

    # reply_any = at least ONE of the listed substrings appears (an OR-group / synonyms).
    any_list = exp.get("reply_any", [])
    if any_list:
        hits = [s for s in any_list if s.casefold() in blob]
        ok = bool(hits)
        detail = f"found={hits}" if ok else f"NONE of {any_list}"
        checks.append(("reply_any", ok, detail))

    # reply_none = NONE of the listed substrings may appear (regression guard for a bug).
    none_list = exp.get("reply_none", [])
    if none_list:
        leaked = [s for s in none_list if s.casefold() in blob]
        ok = not leaked
        detail = "clean" if ok else f"LEAKED (bug): {leaked}"
        checks.append(("reply_none", ok, detail))

    # tool_used = each listed tool_call must have actually run (an ACTION, not just words —
    # e.g. the bridge must really bind the MAC, not merely say it will).
    for tool in exp.get("tool_used", []):
        ok = tool in ev["tools_used"]
        checks.append((f"tool_used:{tool}", ok, "ran" if ok else "NOT CALLED"))

    return checks


def _print_report(results: list[dict]) -> int:
    print(f"\n{'=' * 78}\nCONVERSATION EVAL — Golden Dataset\n{'=' * 78}")
    total_pass = total = 0
    hard_fails = 0  # failures NOT expected (i.e. excluding known_bug scenarios)

    for r in results:
        scn, checks, ev = r["scn"], r["checks"], r["ev"]
        n_ok = sum(1 for _, ok, _ in checks if ok)
        n = len(checks)
        total_pass += n_ok
        total += n
        known = scn.get("known_bug", False)
        scn_pass = n_ok == n
        if not scn_pass and not known:
            hard_fails += 1
        tag = " [KNOWN BUG]" if known else ""
        head = "PASS" if scn_pass else ("xfail" if known else "FAIL")
        print(f"\n[{head}] {scn['id']}  ({n_ok}/{n}){tag}")
        print(f"       {scn['desc']}")
        for name, ok, detail in checks:
            print(f"         {'ok ' if ok else 'XXX'} {name:<28} {detail}")
        if ev.get("trace"):
            print(f"       trace: {ev['trace']}")

    print(f"\n{'-' * 78}")
    print(f"  checks: {total_pass}/{total} passed · unexpected scenario failures: {hard_fails}")
    print(f"{'-' * 78}\n")
    # Exit non-zero only on UNEXPECTED failures — known_bug scenarios may fail.
    return 1 if hard_fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Conversation eval — Golden Dataset")
    ap.add_argument("--only", help="run a single scenario by id")
    ap.add_argument("--no-db", action="store_true", help="skip DB rebuild between scenarios")
    ap.add_argument("--json", help="write the raw report to this path")
    args = ap.parse_args()

    _load_env()
    scenarios = _load_scenarios()
    if args.only:
        scenarios = [s for s in scenarios if s["id"] == args.only]
        if not scenarios:
            print(f"No scenario with id '{args.only}'")
            return 2

    results = []
    for scn in scenarios:
        if not args.no_db:
            _rebuild_db()
        print(f"... running {scn['id']} (phone={scn['phone']})", flush=True)
        ev = _run_scenario(scn)
        checks = _score(scn, ev)
        results.append({"scn": scn, "ev": ev, "checks": checks})

    code = _print_report(results)

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                [
                    {
                        "id": r["scn"]["id"],
                        "known_bug": r["scn"].get("known_bug", False),
                        "checks": [
                            {"name": n, "pass": ok, "detail": d} for n, ok, d in r["checks"]
                        ],
                        "verdicts_seen": sorted(r["ev"]["verdicts_seen"]),
                        "disposition": _disposition(r["ev"]),
                        "trace": r["ev"]["trace"],
                    }
                    for r in results
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Report written to {args.json}")

    return code


if __name__ == "__main__":
    raise SystemExit(main())

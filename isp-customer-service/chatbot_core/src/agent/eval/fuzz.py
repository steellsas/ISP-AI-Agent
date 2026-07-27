"""
Adversarial fuzzing eval — an LLM plays the caller (Phase 3.9 A).

The Golden Dataset uses fixed, clean turns; every bug found in live testing was something
those clean turns did not exercise. Here an LLM plays each caller from `fuzz_personas.json`
— messy, colloquial, sometimes unsure — driven by a `ground_truth` so it stays CONSISTENT
with a real situation, over one no-internet direction. The agent drives; we score the
OUTCOME (verdict reached, action actually ran, sensible close) and surface any errors.
This is the measurement that DEFINES the fix list for making the fault flawless.

Non-deterministic by nature (two LLMs in a loop), so it is a FINDING generator, not a
pass/fail gate — read the transcripts. Needs LLM keys (like the voice demo / run_eval).

Usage:
    cd chatbot_core
    uv run python src/agent/eval/fuzz.py                       # all personas, 1 run each
    uv run python src/agent/eval/fuzz.py --only dead_router_messy --runs 3
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
_SRC_DIR = _EVAL_DIR.parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Reuse the Golden harness plumbing (env, DB rebuild, trace scan).
from agent.eval.run_eval import (  # noqa: E402
    _close_db,
    _disposition,
    _load_env,
    _rebuild_db,
    _tools_in_trace,
)

_PERSONAS_PATH = _EVAL_DIR / "fuzz_personas.json"
_MAX_TURNS = 16
_END = "BAIGTA"


def _load_personas() -> list[dict]:
    data = json.loads(_PERSONAS_PATH.read_text(encoding="utf-8"))
    return [p for p in data["personas"] if isinstance(p, dict) and "id" in p]


def _actor_reply(persona: str, ground_truth: str, transcript: list[tuple[str, str]]) -> str:
    """The LLM-caller's next line, in character and consistent with the ground truth."""
    from src.services.llm.client import llm_completion

    convo = "\n".join(f"{'Agentas' if who == 'a' else 'Tu'}: {txt}" for who, txt in transcript)
    system = (
        "Tu esi žmogus, skambinantis interneto tiekėjui (lietuviškai). VAIDINK personą, "
        "neatsakinėk kaip tobulas scenarijus — kalbėk trumpai, šnekamąja kalba, kartais "
        "nerišliai ar neužtikrintai, kaip tikras žmogus telefonu.\n"
        f"PERSONA: {persona}\n"
        f"TAVO TIKROJI SITUACIJA (laikykis jos nuosekliai): {ground_truth}\n"
        "Atsakyk TIK viena trumpa replika į paskutinį agento sakinį. Neaiškink savęs kaip "
        f"instrukcijos. Kai agentas aiškiai IŠSPRENDĖ arba UŽBAIGĖ pokalbį (atsisveikino), "
        f"atsakyk tik vienu žodžiu: {_END}"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Pokalbis iki šiol:\n{convo}\n\nTavo replika:"},
    ]
    # The actor shares the provider's rate limit with the agent's own calls; on a
    # rate-limit error wait the suggested time and retry, so a run does not die at turn 0.
    for _ in range(3):
        try:
            out = llm_completion(messages=messages, temperature=0.7, max_tokens=60)
            return (out or "").strip().strip('"')
        except Exception as e:
            msg = str(e)
            if "rate limit" in msg.lower():
                m = re.search(r"(\d+(?:\.\d+)?)\s*s", msg)
                time.sleep(min(float(m.group(1)) + 1, 30) if m else 5)
                continue
            return f"<<ACTOR ERROR: {e}>>"
    return f"<<ACTOR ERROR: rate limited: {msg}>>"


def _run(persona: dict) -> dict:
    from agent.session import AgentSession

    session = AgentSession(caller_phone=persona["phone"], language="lt")
    transcript: list[tuple[str, str]] = []
    verdicts: set[str] = set()

    def snap():
        st = session.state
        if st.hypothesis and st.hypothesis.get("cause"):
            verdicts.add(st.hypothesis["cause"])
        if st.resolution and st.resolution.get("verdict"):
            verdicts.add(st.resolution["verdict"])

    greeting = session.greeting()
    transcript.append(("a", greeting))
    snap()

    turns = 0
    while turns < _MAX_TURNS and not session.is_complete:
        caller = _actor_reply(persona["persona"], persona["ground_truth"], transcript)
        transcript.append(("u", caller))
        if _END in caller or caller.startswith("<<ACTOR ERROR"):
            break
        try:
            reply = session.handle_turn(caller) or ""
        except Exception as e:
            reply = f"<<EXCEPTION: {e}>>"
        transcript.append(("a", reply))
        snap()
        turns += 1

    st = session.state
    trace = session.tracer.path if hasattr(session.tracer, "path") else None
    session.end_session(outcome="fuzz")
    _close_db()
    tools = _tools_in_trace(trace)
    ev = {
        "verdicts_seen": verdicts,
        "tools_used": tools,
        "case_closed": st.case_closed,
        "closed_reason": st.closed_reason,
        "outage_reported": getattr(st, "outage_reported", False),
        "ticket_created": "create_ticket" in tools,
        "turns": turns,
        "transcript": transcript,
        "trace": str(trace) if trace else None,
    }
    ev["disposition"] = _disposition(ev)
    return ev


def _findings(persona: dict, ev: dict) -> list[str]:
    """Heuristic red flags — a fuzz run is a finding generator, not a hard gate."""
    exp = persona.get("expect", {})
    out: list[str] = []
    if exp.get("verdict_in") and exp["verdict_in"] not in ev["verdicts_seen"]:
        out.append(
            f"verdict {exp['verdict_in']} never reached (seen {sorted(ev['verdicts_seen'])})"
        )
    for tool in exp.get("tool_used", []):
        if tool not in ev["tools_used"]:
            out.append(f"action {tool} never ran")
    if exp.get("disposition") and ev["disposition"] != exp["disposition"]:
        out.append(f"disposition {ev['disposition']} != {exp['disposition']}")
    if ev["turns"] >= _MAX_TURNS and not ev["case_closed"]:
        out.append(f"did not close within {_MAX_TURNS} turns (possible loop/stall)")
    if any("<<EXCEPTION" in t for _, t in ev["transcript"]):
        out.append("agent raised an exception mid-call")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Adversarial fuzzing eval (LLM caller)")
    ap.add_argument("--only", help="run a single persona by id")
    ap.add_argument("--runs", type=int, default=1, help="runs per persona (variance)")
    ap.add_argument("--no-db", action="store_true", help="skip DB rebuild between runs")
    ap.add_argument("--transcripts", action="store_true", help="print full transcripts")
    args = ap.parse_args()

    _load_env()
    personas = _load_personas()
    if args.only:
        personas = [p for p in personas if p["id"] == args.only]
        if not personas:
            print(f"No persona '{args.only}'")
            return 2

    print(
        f"\n{'=' * 78}\nFUZZING EVAL — LLM caller ({len(personas)} persona(s) x {args.runs})\n{'=' * 78}"
    )
    total_findings = 0
    for persona in personas:
        for run in range(args.runs):
            if not args.no_db:
                _rebuild_db()
            print(f"\n... {persona['id']} run {run + 1}", flush=True)
            ev = _run(persona)
            finds = _findings(persona, ev)
            total_findings += len(finds)
            head = "OK  " if not finds else "FLAG"
            print(
                f"[{head}] {persona['id']}  turns={ev['turns']} "
                f"verdict={sorted(ev['verdicts_seen']) or '-'} disp={ev['disposition']} "
                f"tools={sorted(ev['tools_used']) or '-'}"
            )
            for f in finds:
                print(f"        ! {f}")
            if args.transcripts:
                for who, txt in ev["transcript"]:
                    print(f"        {'A' if who == 'a' else 'U'}: {txt[:80]}")
            if ev.get("trace"):
                print(f"        trace: {ev['trace']}")

    print(f"\n{'-' * 78}\n  total findings: {total_findings}\n{'-' * 78}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

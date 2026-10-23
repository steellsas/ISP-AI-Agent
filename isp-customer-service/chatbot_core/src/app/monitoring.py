"""Stebėsena (ROADMAP 3.3) — what the calls of a period say about the agent.

Two levels, both read from the call traces (logs/sessions, or logs/eval for eval runs):

- `call_card(events)` — ONE call in a few fields: outcome, phases, the cards it ran, what no
  reader understood, guards, interruptions, latency, cost, errors, the versions it ran on,
  and the reasons a person should look at it (`flags`). The archive shows it above a call.
- `overview(days, source, version)` — the period: outcomes, where calls end, identification,
  cards, what was not understood, latency and cost by day, the versions side by side, and
  the review queue.

Pure reading: nothing here changes a call. A card is cached by the trace file's size and
time, so a page reload re-reads only new or growing calls.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
SOURCES = {"live": _ROOT / "logs" / "sessions", "eval": _ROOT / "logs" / "eval"}

PHASES = ("greeting", "intake", "identify", "investigate", "ticket", "closing")
# „be žmogaus": the agent solved it or told the caller what is going on; a ticket hands it on.
SOLVED = {"resolved", "informed", "informed_debt", "informed_outage", "callback"}
# An unfinished call is handed on too: a person reviews it and phones back (2026-10-22).
HANDED_ON = {"ticket", "ticket_appended", "unfinished"}
SLOW_MS = 3000  # a p90 above this puts the call in the review queue

FLAG_LT = {
    "technical_error": "techninė klaida",
    "hung_up_before_close": "padėjo ragelį prieš pabaigą",
    "hung_up": "padėjo ragelį",
    "unfinished": "nebaigtas — perskambinti",
    "stuck": "užstrigo",
    "not_a_customer": "ne klientas",
    "address_not_found": "adreso nerado",
    "unidentified": "neidentifikuotas",
}


def _ms_median(values: list[int]) -> int | None:
    return int(statistics.median(values)) if values else None


def _p90(values: list[int]) -> int | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]


def call_card(events: list[dict[str, Any]], session_id: str | None = None) -> dict[str, Any]:
    """One call in a few fields — from its trace events only."""
    from .config import cost_usd

    of = lambda t: [e for e in events if e.get("type") == t]  # noqa: E731
    start = next(iter(of("session_start")), {})
    summary = next(iter(of("call_summary")), {})
    end = next(iter(of("session_end")), {})
    plans = of("turn_plan")
    ts = [e["ts"] for e in events if e.get("ts")]
    try:
        duration = round(
            (datetime.fromisoformat(ts[-1]) - datetime.fromisoformat(ts[0])).total_seconds()
        )
    except (IndexError, ValueError):
        duration = None

    phases: list[str] = []
    bad_phase = False
    for e in of("phase"):
        if not phases or phases[-1] != e.get("phase"):
            phases.append(e.get("phase"))
        bad_phase = bad_phase or e.get("ok") is False
    ident_turn = next(
        (
            p.get("turn_index")
            for p in plans
            if p.get("rule", "").startswith(("identification.caller_name", "identification.result"))
        ),
        None,
    )
    cards = list(dict.fromkeys(e["fault"] for e in of("case") if e.get("move") and e.get("fault")))
    silent = [
        {"module": e.get("module"), "fact": e.get("fact"), "heard": e.get("heard")}
        for e in of("reader_silent")
    ]
    guards = Counter(e.get("reason") for e in of("reply_guard"))
    promises = [e.get("dropped") for e in of("reply_guard") if e.get("dropped")]
    barge = Counter(e.get("verdict") for e in of("barge_in"))
    latency = [
        int(e["total_ms"])
        for e in of("pipecat_latency")
        if not e.get("suspect") and e.get("total_ms")
    ]
    llm = of("llm")
    cost = sum(
        cost_usd(e.get("model"), int(e.get("input_tokens") or 0), int(e.get("output_tokens") or 0))
        for e in llm
    )
    errors = (
        [f"{e.get('where')}: {e.get('detail')}" for e in of("error") if e.get("level") != "warn"]
        + [f"sistema {e.get('tool')}: {e.get('error')}" for e in of("ops_alert")]
        + [f"įrankis {e.get('name')} nepavyko" for e in of("tool_result") if e.get("ok") is False]
        + [f"LLM ({e.get('role')}) nepavyko" for e in llm if e.get("success") is False]
    )
    stuck = any(e.get("count") or e.get("repeated") for e in of("stuck"))
    outcome = summary.get("outcome") or end.get("outcome")
    ended_in = phases[-1] if phases else None

    flags: list[str] = []
    if summary.get("needs_review") or end.get("needs_review"):
        reason = summary.get("review_reason")
        flags.append(FLAG_LT.get(reason, reason or "pažymėta peržiūrai"))
    if errors:
        flags.append(f"klaidos: {len(errors)}")
    if len(silent) >= 2:
        flags.append(f"nesuprato {len(silent)} k.")
    if stuck and "užstrigo" not in flags:
        flags.append("užstrigo")
    if promises:
        flags.append("sargas sustabdė pažadą")
    if (_p90(latency) or 0) > SLOW_MS:
        flags.append("lėtas atsakymas")
    if bad_phase:
        flags.append("neleistinas fazės perėjimas")
    if outcome is None:
        flags.append("be pabaigos įrašo")

    versions = start.get("versions") or {}
    return {
        "session_id": session_id
        or start.get("session_id")
        or (events[0].get("session_id") if events else None),
        "started": ts[0] if ts else None,
        "duration_s": duration,
        "transport": "balsas" if of("pipecat_latency") or of("asr") else "tekstas",
        "turns": max(0, len(plans) - 1),
        "purpose": summary.get("purpose"),
        "customer_id": summary.get("customer_id") or end.get("customer_id"),
        "outcome": outcome,
        "ticket_id": summary.get("ticket_id") or end.get("ticket_id"),
        "unidentified_reason": summary.get("unidentified_reason"),
        "phases": phases,
        "ended_in": ended_in,
        "ident_turn": ident_turn,
        "cards": cards,
        "not_understood": silent,
        "guards": dict(guards),
        "promises_stopped": promises,
        "interruptions": dict(barge),
        "latency_median_ms": _ms_median(latency),
        "latency_p90_ms": _p90(latency),
        "latency_ms": latency,
        "llm_calls": len(llm),
        "tokens_in": sum(int(e.get("input_tokens") or 0) for e in llm),
        "tokens_out": sum(int(e.get("output_tokens") or 0) for e in llm),
        "cost_usd": round(cost, 5),
        "errors": errors,
        "version": {
            "code": versions.get("code"),
            "knowledge": versions.get("knowledge"),
            "prompts": versions.get("prompts"),
            "model": (versions.get("models") or {}).get("speak") or start.get("model"),
        },
        "flags": flags,
    }


_CACHE: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}


def _card_of(path: Path) -> dict[str, Any] | None:
    stat = path.stat()
    key = (stat.st_size, stat.st_mtime_ns)
    hit = _CACHE.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    events = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:  # a line being written right now
                        continue
    except OSError:
        return None
    if not any(e.get("type") == "session_start" for e in events):
        return None
    card = call_card(events, path.stem)
    # A call still being written is not "without an ending" — it is going on.
    if card["outcome"] is None and datetime.now().timestamp() - stat.st_mtime < 120:
        card["ongoing"] = True
        card["flags"] = [f for f in card["flags"] if f != "be pabaigos įrašo"]
    _CACHE[str(path)] = (key, card)
    return card


def _day(session_id: str) -> str | None:
    try:
        return datetime.strptime(session_id[:8], "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def version_key(card: dict[str, Any]) -> str:
    v = card["version"]
    if not v.get("code"):
        return "nežinoma (iki 3.1)"
    return f"{v['code']} · žinios {v.get('knowledge')} · promptai {v.get('prompts')}"


def cards(days: int | None = 7, source: str = "live") -> list[dict[str, Any]]:
    """Every call of the period, newest first."""
    folder = SOURCES.get(source, SOURCES["live"])
    if not folder.is_dir():
        return []
    since = (datetime.now() - timedelta(days=days - 1)).date().isoformat() if days else None
    out = []
    for path in folder.glob("*.jsonl"):
        day = _day(path.stem)
        if day is None or (since and day < since):
            continue
        card = _card_of(path)
        if card:
            out.append(card)
    out.sort(key=lambda c: c["session_id"] or "", reverse=True)
    return out


def overview(
    days: int | None = 7, source: str = "live", version: str | None = None
) -> dict[str, Any]:
    """The period in numbers, for the monitoring page."""
    every = cards(days, source)
    versions_all = Counter(version_key(c) for c in every)
    calls = [c for c in every if not version or version_key(c) == version]
    n = len(calls)
    outcomes = Counter(c["outcome"] or "be įrašo" for c in calls)
    pct = lambda k: round(100 * k / n) if n else 0  # noqa: E731

    # Where calls end: the last phase of each call that did not reach the closing.
    phased = [c for c in calls if c["phases"]]  # older traces carry no phase events
    reached = Counter(p for c in phased for p in set(c["phases"]))
    ended = Counter(
        c["ended_in"]
        for c in phased
        if c["ended_in"] and c["ended_in"] != "closing" and c["outcome"] not in SOLVED | HANDED_ON
    )
    identified = [c for c in calls if c["customer_id"]]
    ident_turns = [c["ident_turn"] for c in identified if c["ident_turn"] is not None]

    card_stats: dict[str, Counter] = defaultdict(Counter)
    for c in calls:
        for f in c["cards"]:
            card_stats[f]["calls"] += 1
            card_stats[f][
                "solved"
                if c["outcome"] in SOLVED
                else "ticket"
                if c["outcome"] in HANDED_ON
                else "other"
            ] += 1

    silent: dict[tuple, dict[str, Any]] = {}
    for c in calls:
        for s in c["not_understood"]:
            k = (s["module"], s["fact"])
            row = silent.setdefault(
                k, {"module": s["module"], "fact": s["fact"], "count": 0, "heard": []}
            )
            row["count"] += 1
            if s["heard"] and len(row["heard"]) < 4 and s["heard"] not in row["heard"]:
                row["heard"].append(s["heard"])

    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in calls:
        by_day[_day(c["session_id"]) or "?"].append(c)
    days_rows = []
    for d in sorted(by_day):
        lat = [ms for c in by_day[d] for ms in c["latency_ms"]]
        days_rows.append(
            {
                "day": d,
                "calls": len(by_day[d]),
                "solved": sum(c["outcome"] in SOLVED for c in by_day[d]),
                "latency_median_ms": _ms_median(lat),
                "latency_p90_ms": _p90(lat),
                "cost_usd": round(sum(c["cost_usd"] for c in by_day[d]), 4),
            }
        )

    per_version = []
    for key in versions_all:
        vc = [c for c in every if version_key(c) == key]
        lat = [ms for c in vc for ms in c["latency_ms"]]
        per_version.append(
            {
                "version": key,
                "calls": len(vc),
                "solved_pct": round(100 * sum(c["outcome"] in SOLVED for c in vc) / len(vc)),
                "ticket_pct": round(100 * sum(c["outcome"] in HANDED_ON for c in vc) / len(vc)),
                "not_understood": sum(len(c["not_understood"]) for c in vc),
                "latency_median_ms": _ms_median(lat),
                "first": min(c["session_id"] for c in vc),
                "last": max(c["session_id"] for c in vc),
            }
        )
    per_version.sort(key=lambda r: r["last"], reverse=True)

    latency = [ms for c in calls for ms in c["latency_ms"]]
    guards = Counter()
    barge = Counter()
    for c in calls:
        guards.update(c["guards"])
        barge.update(c["interruptions"])
    return {
        "source": source,
        "days": days,
        "version": version,
        "totals": {
            "calls": n,
            "solved_pct": pct(sum(c["outcome"] in SOLVED for c in calls)),
            "handed_on_pct": pct(sum(c["outcome"] in HANDED_ON for c in calls)),
            "identified_pct": pct(len(identified)),
            "review": sum(bool(c["flags"]) for c in calls),
            "latency_median_ms": _ms_median(latency),
            "latency_p90_ms": _p90(latency),
            "cost_usd": round(sum(c["cost_usd"] for c in calls), 4),
            "cost_per_call_usd": round(sum(c["cost_usd"] for c in calls) / n, 4) if n else 0,
            "voice_calls": sum(c["transport"] == "balsas" for c in calls),
        },
        "outcomes": dict(outcomes.most_common()),
        "phases": {
            "calls": len(phased),
            "reached": {p: reached.get(p, 0) for p in PHASES},
            "ended": {p: ended.get(p, 0) for p in PHASES},
        },
        "identification": {
            "identified": len(identified),
            "of": sum(bool(c["purpose"]) for c in calls),  # calls that said what is wrong
            "median_turn": _ms_median(ident_turns),
        },
        "cards": sorted(
            ({"card": k, **v} for k, v in card_stats.items()), key=lambda r: -r["calls"]
        ),
        "not_understood": sorted(silent.values(), key=lambda r: -r["count"]),
        "guards": dict(guards.most_common()),
        "promises_stopped": [p for c in calls for p in c["promises_stopped"]][:20],
        "interruptions": dict(barge),
        "errors": [{"session_id": c["session_id"], "error": e} for c in calls for e in c["errors"]][
            :50
        ],
        "by_day": days_rows,
        "versions": per_version,
        "review": [
            {
                k: c[k]
                for k in (
                    "session_id",
                    "started",
                    "outcome",
                    "ended_in",
                    "turns",
                    "flags",
                    "transport",
                )
            }
            for c in calls
            if c["flags"]
        ][:100],
    }

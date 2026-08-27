"""
S1 speculation (VOICE_PLAN, sutarta 2026-08-24) — the agent thinks WHILE the
caller is answering.

After a question goes out, the pack already names the possible answers
(`atsakymai`: dega/nedega, radau/neradau, yes/no). A background thread applies
each candidate to a COPY of the ledger (pure functions — no state touched),
computes what the next directive would be (ask the next fact / recap /
findings), words it with a standalone narrator call (persona+style prompt, no
tools) and synthesizes the audio. When the real answer arrives and matches a
branch — the reply is served from the cache (~0 s instead of LLM+TTS).

Safety (sutarta): the branch is used ONLY when the deterministic reader maps
the utterance to exactly that canonical value AND the utterance carries
nothing else (no extra facts, not a question/demand/farewell). Any doubt →
the normal path, byte-for-byte today's behaviour. The background work never
mutates engine state and never calls mutating tools.
"""

from __future__ import annotations

import copy
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.getenv("SPECULATION", "on").lower() == "on"


# --- planning (pure) ---------------------------------------------------------


def _directive_line(kind: str, payload: dict[str, Any]) -> str:
    """The SAME goal-directive wording the live facts block would carry —
    the speculative narrator answers to the same instruction."""
    if kind == "evidence":
        kodel = f" Kodėl tikriname: {payload['kodel']}." if payload.get("kodel") else ""
        return (
            f"- KLAUSK DABAR: išsiaiškink — {payload['reikia']}. Fakto DAR "
            f"NEŽINAI — užduok klausimą, nekonstatuok.{kodel} "
            f"(Atsarginė: „{payload['klausimas']}“)"
        )
    if kind == "recap":
        return f"- PASITIKSLINK: ar teisingai supratai — {payload['faktai']}."
    # findings
    if payload.get("pasiulymas"):
        spr = f" {payload['pasiulymas']}"
    elif payload.get("sprendimai"):
        spr = f" Pasiūlyk pasirinkimą ({payload['sprendimai']}) ir paklausk, kaip darome."
    else:
        spr = ""
    return (
        "- IŠVADOS MOMENTAS: Registracija dar NEĮVYKO — sakyk „užregistruosiu“, "
        f"niekada „užregistravau“. Kartu nustatėme — {payload['faktai']}. "
        f"Išvada: {payload['isvada']}.{spr}"
    )


def plan_branches(engine: Any) -> dict[str, Any] | None:
    """What would the NEXT directive be for each candidate answer to the OPEN
    evidence question? Pure — works on copies; None when there is nothing
    safe to speculate on."""
    from .evidence import (
        CLIENT,
        client_facts_lt,
        fault_isvada,
        fault_pasiulymas,
        hypothesis_status,
        next_missing,
        set_fact,
        solution_descriptions,
        spec_for,
    )

    s = engine.state
    r = s.resolution or {}
    verdict = r.get("verdict")
    key = getattr(engine, "_evidence_last_ask_key", None)
    if not verdict or not key or s.case_closed:
        return None
    spec = spec_for(verdict)
    if not spec:
        return None
    item = (spec.get("client") or {}).get(key) or {}
    values = list((item.get("atsakymai") or {}).keys())
    if not values:
        from .evidence import _PENDING_ANSWERS

        values = [v for v, _marks in _PENDING_ANSWERS.get(str(key), [])]
    if not values and key == "has_computer":
        values = ["yes", "no"]
    if not values:
        return None

    branches: dict[str, dict[str, Any]] = {}
    for value in values[:3]:
        ev2 = copy.deepcopy(s.evidence)
        set_fact(ev2, str(key), str(value), CLIENT, s.turn_count)
        status = hypothesis_status(ev2, spec)
        if status == "refuted":
            continue  # pivot path — deterministic machinery handles it live
        if status == "confirmed":
            if getattr(engine, "_recap_state", "") != "done":
                branches[str(value)] = {
                    "kind": "recap",
                    "key": None,
                    "directive": _directive_line("recap", {"faktai": client_facts_lt(ev2)}),
                }
            elif not getattr(engine, "_findings_announced", False):
                branches[str(value)] = {
                    "kind": "findings",
                    "key": None,
                    "directive": _directive_line(
                        "findings",
                        {
                            "faktai": client_facts_lt(ev2),
                            "isvada": fault_isvada(verdict) or "",
                            "sprendimai": " ARBA ".join(solution_descriptions(verdict)),
                            "pasiulymas": fault_pasiulymas(verdict) or "",
                        },
                    ),
                }
            continue  # confirmed + everything said -> solution machinery, skip
        nxt = next_missing(ev2, spec, False)
        if nxt is None:
            continue
        key2, item2 = nxt
        if not item2.get("reikia"):
            continue
        branches[str(value)] = {
            "kind": "evidence",
            "key": key2,
            "directive": _directive_line(
                "evidence",
                {
                    "reikia": str(item2["reikia"]),
                    "kodel": str(item2.get("kodel") or ""),
                    "klausimas": str(item2.get("klausimas") or ""),
                },
            ),
        }
    if not branches:
        return None
    return {"pending_key": str(key), "verdict": verdict, "branches": branches}


# --- precompute (background thread; never touches engine state) --------------


def _speculative_narrate(engine: Any, directive: str) -> str | None:
    """One standalone narrator call: persona+style prompt + recent dialogue +
    the goal directive. No tools, no engine state."""
    try:
        from src.services.llm.client import llm_completion

        from .narrator_flow import _directive_system_prompt

        history = [
            {"role": m["role"], "content": (m.get("content") or "")[:300]}
            for m in engine.state.messages[-6:]
            if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
        ]
        messages = (
            [{"role": "system", "content": _directive_system_prompt()}]
            + history
            + [
                {
                    "role": "system",
                    "content": "KNOWN FACTS (already resolved this call — do not ask again):\n"
                    + directive,
                }
            ]
        )
        content = llm_completion(
            messages=messages,
            model=engine.config.model,
            temperature=engine.config.temperature,
            max_tokens=220,
        )
        return (content or "").strip() or None
    except Exception as e:  # pragma: no cover - speculation must never break
        logger.debug(f"speculative narrate failed: {e}")
        return None


def precompute(engine: Any, synthesize) -> None:
    """Fill engine._spec_cache for the open question's branches. Runs in a
    background thread; the cache is a plain dict swap (atomic enough for the
    serialized WS turn loop)."""
    if not enabled():
        return
    try:
        plan = plan_branches(engine)
        if not plan:
            engine._spec_cache = None
            return
        for _value, br in plan["branches"].items():
            text = _speculative_narrate(engine, br["directive"])
            if not text or "?" not in text:
                continue  # a directive turn must end in the one question
            br["text"] = text
            try:
                br["audio"] = synthesize(text) if synthesize else b""
            except Exception:  # pragma: no cover
                br["audio"] = b""
        plan["branches"] = {v: b for v, b in plan["branches"].items() if b.get("text")}
        engine._spec_cache = plan if plan["branches"] else None
        engine.tracer.emit(
            "speculation",
            action="prepared",
            key=plan["pending_key"],
            branches=sorted(plan["branches"]) if plan["branches"] else [],
        )
    except Exception as e:  # pragma: no cover - never break the call
        logger.debug(f"speculation precompute failed: {e}")
        engine._spec_cache = None


# --- matching (serve gates; conservative by design) ---------------------------


def match(engine: Any, transcript: str) -> dict[str, Any] | None:
    """The prepared branch for THIS utterance — or None on ANY doubt.
    Consumes the cache either way (one shot per question)."""
    cache = getattr(engine, "_spec_cache", None)
    engine._spec_cache = None
    if not cache or not enabled() or not transcript:
        return None
    key = cache["pending_key"]
    if getattr(engine, "_evidence_last_ask_key", None) != key:
        return None
    from .evidence import extract_client_facts, read_pending_answer, spec_for
    from .resolution import (
        detect_farewell,
        detect_refuse_or_ticket,
        is_real_question,
    )

    if (
        is_real_question(transcript)
        or "?" in transcript
        or detect_refuse_or_ticket(transcript) is not None
        or detect_farewell(transcript)
    ):
        return None
    spec = spec_for(cache["verdict"]) or {}
    item = (spec.get("client") or {}).get(key)
    value = read_pending_answer(key, transcript, item)
    if value is None:
        return None
    extra = {k: v for k, v in extract_client_facts(transcript).items() if k != key}
    if extra:
        return None  # the utterance carries MORE than the branch fact
    # Length/conjunction guard: a longer or compound utterance may carry
    # content our extractors do not model ("Nedega, bet keičiau routerį") —
    # conservative by design, the normal path handles it.
    low = f" {transcript.lower()} "
    if len(transcript.split()) > 4 or any(
        m in low for m in (" bet ", " o ", " taip pat ", " dar ")
    ):
        return None
    branch = cache["branches"].get(str(value))
    if not branch:
        return None
    engine.tracer.emit("speculation", action="match", key=key, value=str(value))
    return branch

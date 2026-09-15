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

import contextlib
import copy
import json
import logging
import os
from typing import Any

from .contract.locale import maybe_phrase, vocab

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


def plan_branches(state: Any, rt: Any) -> dict[str, Any] | None:
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

    s = state
    r = s.resolution.procedure or {}
    verdict = r.get("verdict")
    key = state.diagnosis.pending_evidence_key
    if not verdict or not key or s.closing.case_closed:
        return None
    spec = spec_for(verdict)
    if not spec:
        return None
    item = (spec.get("client") or {}).get(key) or {}
    values = list((item.get("atsakymai") or {}).keys())
    if not values:
        from .contract.locale import vocab_map

        values = [v for v, _marks in vocab_map("pending_answers").get(str(key), [])]
    if not values and key == "has_computer":
        values = ["yes", "no"]
    if not values:
        return None

    branches: dict[str, dict[str, Any]] = {}
    for value in values[:3]:
        ev2 = copy.deepcopy(s.diagnosis.evidence)
        set_fact(ev2, str(key), str(value), CLIENT, s.dialog.turn_count)
        status = hypothesis_status(ev2, spec)
        if status == "refuted":
            continue  # pivot path — deterministic machinery handles it live
        if status == "confirmed":
            if state.diagnosis.facts_recap_state != "done":
                branches[str(value)] = {
                    "kind": "recap",
                    "key": None,
                    "directive": _directive_line("recap", {"faktai": client_facts_lt(ev2)}),
                }
            elif not state.diagnosis.findings_announced:
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
                    "kodel": str(maybe_phrase(item2.get("kodel")) or ""),
                    "klausimas": str(maybe_phrase(item2.get("klausimas")) or ""),
                },
            ),
        }
    if not branches:
        return None
    return {"pending_key": str(key), "verdict": verdict, "branches": branches}


# --- precompute (background thread; never touches engine state) --------------


def _speculative_narrate(state: Any, rt: Any, directive: str) -> str | None:
    """One standalone narrator call: persona+style prompt + recent dialogue +
    the goal directive. No tools, no engine state."""
    try:
        from src.services.llm.client import llm_completion

        from .narrator_flow import _directive_system_prompt

        history = [
            {"role": m["role"], "content": (m.get("content") or "")[:300]}
            for m in state.messages[-6:]
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
            model=rt.config.model,
            temperature=rt.config.temperature,
            max_tokens=220,
        )
        return (content or "").strip() or None
    except Exception as e:  # pragma: no cover - speculation must never break
        logger.debug(f"speculative narrate failed: {e}")
        return None


def precompute(state: Any, rt: Any, synthesize) -> None:
    """Fill rt.speculation["cache"] for the open question's branches. Runs in a
    background thread; the cache is a plain dict swap (atomic enough for the
    serialized WS turn loop)."""
    if not enabled():
        return
    try:
        plan = plan_branches(state, rt)
        if not plan:
            rt.speculation["cache"] = None
            return
        for _value, br in plan["branches"].items():
            text = _speculative_narrate(state, rt, br["directive"])
            if not text or "?" not in text:
                continue  # a directive turn must end in the one question
            br["text"] = text
            try:
                br["audio"] = synthesize(text) if synthesize else b""
            except Exception:  # pragma: no cover
                br["audio"] = b""
        plan["branches"] = {v: b for v, b in plan["branches"].items() if b.get("text")}
        rt.speculation["cache"] = plan if plan["branches"] else None
        rt.tracer.emit(
            "speculation",
            action="prepared",
            key=plan["pending_key"],
            branches=sorted(plan["branches"]) if plan["branches"] else [],
        )
    except Exception as e:  # pragma: no cover - never break the call
        logger.debug(f"speculation precompute failed: {e}")
        rt.speculation["cache"] = None


# --- matching (serve gates; conservative by design) ---------------------------


def match(state: Any, rt: Any, transcript: str) -> dict[str, Any] | None:
    """The prepared branch for THIS utterance — or None on ANY doubt.
    Consumes the cache either way (one shot per question)."""
    cache = rt.speculation.get("cache")
    rt.speculation["cache"] = None
    if not cache or not enabled() or not transcript:
        return None
    key = cache["pending_key"]
    if state.diagnosis.pending_evidence_key != key:
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
    if len(transcript.split()) > 4 or any(m in low for m in vocab("compound_marks")):
        return None
    branch = cache["branches"].get(str(value))
    if not branch:
        return None
    rt.tracer.emit("speculation", action="match", key=key, value=str(value))
    return branch


def apply_bg_diagnosis(state: Any, rt: Any) -> None:
    """S2 gate: fold the background telemetry read in ONLY as a refresh —
    in the solution/bridge phase, or when the fresh verdict FLIPS the
    story, it is discarded (the solution steps read at the right moments
    themselves)."""
    from .narrator_flow import update_state_from_observation

    bg = state.turn.bg_diagnosis
    if not bg:
        return
    state.turn.bg_diagnosis = None
    # A-2R (2026-09-07): with no identified customer the telemetry has no
    # one to belong to — after reopen it used to restore the dropped
    # account's diagnosis.
    if not state.identity.customer_id:
        return
    with contextlib.suppress(Exception):
        r0 = state.resolution.procedure or {}
        in_solution = bool(
            r0.get("solution_synced")
            or state.resolution.bridge_plug_reported
            or state.resolution.bridge_bound
        )
        fresh = ((json.loads(bg) or {}).get("verdict") or {}).get("reason")
        current = r0.get("verdict")
        if not in_solution and (not current or fresh == current):
            update_state_from_observation(state, rt, "diagnose_connection", bg)
            rt.tracer.emit("speculation", action="bg_diagnosis_applied")
        else:
            rt.tracer.emit("speculation", action="bg_diagnosis_discarded", fresh=fresh)


def consume_injected_reply(state: Any, rt: Any) -> str | None:
    """S1 speculation: the precomputed reply for the ACTIVE directive (set
    by the voice layer when the caller's answer matched a prepared
    branch). Consumed only when the drive actually produced the predicted
    directive — any mismatch falls back to the normal LLM path."""
    inj = state.turn.injected_reply
    if not inj:
        return None
    state.turn.injected_reply = None
    kind, key, text = inj.get("kind"), inj.get("key"), inj.get("text")
    if not text:
        return None
    if kind == "evidence":
        d = state.turn.directives.evidence
        if d and d.get("key") == key:
            rt.tracer.emit("speculation", action="hit", kind=kind, key=key)
            return str(text)
    elif (
        kind == "recap"
        and state.turn.directives.recap
        or kind == "findings"
        and state.turn.directives.findings
    ):
        rt.tracer.emit("speculation", action="hit", kind=kind)
        return str(text)
    rt.tracer.emit("speculation", action="miss", kind=kind, key=key)
    return None

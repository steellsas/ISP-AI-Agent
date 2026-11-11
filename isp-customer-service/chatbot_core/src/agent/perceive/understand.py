"""Understanding pass — the understanding layer (Ledger v2.5, agreed 2026-08-10).

ONE small-model JSON call per caller turn in the diagnosis stage reads the
reply IN CONTEXT (the pending question, the fault's evidence needs, the ledger,
the last conversation turns) and returns:

    facts       — canonical evidence values it heard (validated against the spec),
    type        — answer | question | deviation | confusion | contradiction,
    understood  — half-sentence of WHAT was understood (the narrator's
                  acknowledgement: "Gerai — routerį radote."),
    confusion   — what exactly the caller did not understand (drives the
                  re-explain-DIFFERENTLY wording),
    confidence  — 0..1.

It is a SENSOR: it never touches state. The ENGINE decides — facts go through
the same set_fact discipline (conflicts, telemetry-over-words), type feeds the
existing routes (side_topic, clarify). Returns None on ANY failure so the
caller falls back to the deterministic keyword extractor — a conversation must
never stall on a model hiccup. Gated by UNDERSTAND=on (config page); unit
tests run with CLASSIFIER=off which disables it too.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..contract import limits

logger = logging.getLogger(__name__)

TURN_TYPES = {"answer", "question", "deviation", "confusion", "contradiction"}

# Canonical values per key — the model may only pick from these (plus omit).
_ALLOWED = {
    "device_present": {"found", "not_found"},
    "lights": {"off", "on", "blinking"},
    "power_cable": {"plugged", "unplugged"},
    "outlet_works": {"tried", "not_working"},
    "has_computer": {"yes", "no"},
    # Bridge phase (2026-08-12): the COMPUTER's network state after the cable
    # was replugged — without this key, "rodo LAN veikia" landed on the ROUTER
    # lights and dragged the call back to a buried hypothesis (live).
    "lan_active": {"active", "inactive"},
}


def perception_model(fallback: str | None) -> str | None:
    """The PERCEPTION-family model (VOICE_PLAN tempo wave): the understand
    pass and the step classifier may run on a FASTER model than the narrator
    (e.g. groq/openai/gpt-oss-120b — Groq inference is ~10x quicker, and the
    perception JSON task is enum-validated, so it degrades safely). Set via
    PERCEPTION_MODEL on the config page; 'default'/empty = the agent model."""
    m = os.getenv("PERCEPTION_MODEL", "").strip()
    return m if m and m != "default" else fallback


def enabled() -> bool:
    if os.getenv("CLASSIFIER", "on").lower() == "off":
        return False  # deterministic test mode — no model calls at all
    return os.getenv("UNDERSTAND", "on").lower() == "on"


REPLY_STATUSES = (
    "answered", "doing", "asks_back", "pushback", "not_now", "refuses", "off_topic"
)  # fmt: skip


def _merged_allowed(extra: dict[str, set[str]] | None) -> dict[str, set[str]]:
    """EVERY fact a caller can state (`fact_catalog`, 2026-11-06) + whatever the active spec
    adds. Collect everything, use by branch: before this only the active card's needs were
    allowed, and „Patikrinau, WiFi įjungtas" had no key to land on (eval S9)."""
    from ..fact_catalog import allowed_map

    merged = {k: set(v) for k, v in _ALLOWED.items()}
    for k, vals in allowed_map().items():
        merged[k] = merged.get(k, set()) | vals
    for k, vals in (extra or {}).items():
        merged[k] = merged.get(k, set()) | {str(v) for v in vals}
    return merged


def _knowledge_map() -> tuple[str, list[str]]:
    """Agento ŽINIŲ ŽEMĖLAPIS promptui: ką jis apie save žino turįs.

    Andrius (2026-09-25): *„rag žinios tai agento žinios supratimui ir informacijos papildymui —
    agentas turi susirasti sau informaciją"*. Todėl paieškos įvadas yra ne kliento sakinys, o AGENTO
    sprendimas, ko jam reikia. Išmatuota (68 klausimai): kliento sakiniu randama 57 %, LLM laisvai
    sugalvotu poreikiu 53 % (blogiau!), o LLM pasirinkimu IŠ ŠIO ŽEMĖLAPIO — 69 %. Skirtumas
    paprastas: čia modeliui nebereikia atspėti mūsų žodžių, jis renkasi iš to, kas tikrai yra.

    Žemėlapis yra dokumentų pavadinimai, tad naujas dokumentas jį išplečia savaime. Prie kelių šimtų
    dokumentų jį reikės sutraukti (pvz. iki rūšių ar temų), bet prie septyniolikos tai septyniolika
    eilučių.
    """
    from ..knowledge_base import documents

    sources = [doc["source"] for doc in documents()]
    listing = "\n".join(f"    {i + 1}. {doc['title']}" for i, doc in enumerate(documents()))
    return listing, sources


def _may_ask(utterance: str) -> bool:
    """Could this turn be the caller asking us something? Generous on purpose: a „?" from the
    STT, or a question by its words — a missed question loses its document, an extra one only
    costs the list."""
    from .detectors import is_real_question

    return "?" in (utterance or "") or is_real_question(utterance)


def _system(
    anchor: str,
    needs: str,
    ledger: str,
    allowed_map: dict[str, set[str]],
    step_options: dict[str, str] | None = None,
    ticket_stage: str | None = None,
    problem_options: dict[str, str] | None = None,
    *,
    with_knowledge: bool = True,
) -> str:
    """Render the merged perception prompt from prompts/sensors/*.md (R4:
    understanding + step classification in ONE call; R5: instructions live in
    files, code only fills the tokens)."""
    from ..fact_catalog import fact_line
    from ..prompts import load_node_prompt

    allowed = "\n".join(fact_line(k, v) for k, v in sorted(allowed_map.items()))
    step_json = ""
    step_rules = ""
    if step_options:
        opts = "\n".join(f'    - "{k}": {v}' for k, v in step_options.items())
        step_json = ', "status": "' + "|".join(REPLY_STATUSES) + '"'
        step_rules = load_node_prompt("sensors/perception_step").replace("<<options>>", opts)
    extra_json, extra_rules = "", ""
    # Žinių žemėlapis dedamas TIK tada, kai jis gali būti reikalingas. Kontakto dialogo metu
    # (`ticket_stage`) klausimas yra uždaras — vardas, laikas, telefonas — ir 17 papildomų eilučių
    # promptą tik praskiedžia. Išmatuota: su jomis D5 paskutinis „Ačiū, viso gero" nustojo būti
    # skaitomas kaip atsakymas („bet kada"), ir tiketas nebeįvyko (2026-09-25).
    #
    # Ir tik tada, kai klientas gali KLAUSTI: ~4 tūkst. simbolių sąrašas eidavo su kiekvienu „taip"
    # ir „neveikia" (2026-11-11: ~1/3 prompto) — atsakymui jo niekada nereikia.
    listing, _sources = ("", []) if ticket_stage or not with_knowledge else _knowledge_map()
    if listing:
        extra_json += ', "knowledge": int|null'
        extra_rules += "\n" + load_node_prompt("sensors/knowledge_route").replace(
            "<<documents>>", listing
        )
    if ticket_stage:
        # The contact dialogue's answer, read in the SAME call (wave 2a).
        extra_json += ', "ticket": {"value": str|null, "type": "answer|question|refusal|other"}'
        extra_rules += "\n" + load_node_prompt(f"sensors/ticket_reader_{ticket_stage}")
    if problem_options:
        problem_opts = "\n".join(f'    - "{k}": {v}' for k, v in problem_options.items())
        extra_json += ', "problem": {"label": str|null, "confidence": 0.0-1.0}'
        extra_rules += "\n" + load_node_prompt("sensors/problem_in_perception").replace(
            "<<options>>", problem_opts
        )
    return (
        load_node_prompt("sensors/perception")
        .replace("<<anchor>>", anchor)
        .replace("<<needs>>", needs)
        .replace("<<ledger>>", ledger or "(nieko)")
        .replace("<<allowed>>", allowed)
        .replace("<<step_json>>", step_json + extra_json)
        .replace("<<step_rules>>", step_rules + extra_rules)
        .strip()
    )


def understand(
    utterance: str,
    *,
    anchor: str,
    needs: str,
    ledger_summary: str,
    history_tail: list[dict[str, str]] | None = None,
    model: str | None = None,
    allowed_extra: dict[str, set[str]] | None = None,
    step_options: dict[str, str] | None = None,
    ticket_stage: str | None = None,
    problem_options: dict[str, str] | None = None,
    step_answers: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Read one caller turn. None on any failure -> keyword fallback.

    R4 perception merge: when `step_options` is given (an asked CONFIRM/INSTRUCT
    step awaits its answer), the SAME call also classifies the reply against the
    step's routing keys — the result rides back as `step` and replaces the
    separate classifier.classify_step call (one LLM round-trip fewer per turn).
    """
    if not utterance or not utterance.strip():
        return None
    allowed_map = _merged_allowed(allowed_extra)
    try:
        from src.services.llm.client import llm_json_completion

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": _system(
                    anchor,
                    needs,
                    ledger_summary,
                    allowed_map,
                    step_options,
                    ticket_stage=ticket_stage,
                    problem_options=problem_options,
                    with_knowledge=_may_ask(utterance),
                ),
            }
        ]
        for m in (history_tail or [])[-limits.get("understand_history_messages") :]:
            role = "assistant" if m.get("role") == "assistant" else "user"
            content = (m.get("content") or "")[:200]
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": utterance[:400]})
        data = llm_json_completion(
            messages=messages,
            model=perception_model(model),
            role="perception",
            temperature=limits.get("perception_temperature"),
            max_tokens=limits.get("perception_max_tokens"),
        )
        if not isinstance(data, dict):
            return None
        turn_type = str(data.get("type") or "answer").lower()
        if turn_type not in TURN_TYPES:
            turn_type = "answer"
        raw_facts = data.get("facts")
        facts: dict[str, str] = {}
        quotes: dict[str, str] = {}
        hedged: set[str] = set()
        if isinstance(raw_facts, dict) and isinstance(raw_facts.get("quote"), str):
            # A flattened fact (gpt-4o-mini, 2026-11-06): {"restored": "yes", "quote": "dabar
            # veikia"}. With ONE fact the quote is plainly its own; with more it is nobody's.
            flat = dict(raw_facts)
            quote_word = flat.pop("quote")
            doubt = flat.pop("hedged", False) is True
            if len(flat) == 1:
                key, value = next(iter(flat.items()))
                raw_facts = {key: {"value": value, "quote": quote_word, "hedged": doubt}}
            else:
                raw_facts = flat
        if isinstance(raw_facts, dict):
            for k, v in raw_facts.items():
                # Wave 2a: a fact may come as {"value": …, "quote": the caller's words} —
                # the quote is what makes a hallucination checkable. A bare value still
                # parses (older models, facts read from context).
                value, quote = (
                    (v.get("value"), v.get("quote")) if isinstance(v, dict) else (v, None)
                )
                if isinstance(value, list):
                    # Eval S9 (2026-11-06): ["yes"] was dropped whole — one value is a value.
                    value = value[0] if len(value) == 1 else None
                if isinstance(quote, list):
                    quote = " ".join(str(q) for q in quote)
                if k in allowed_map and str(value) in allowed_map[k]:
                    facts[k] = str(value)
                    if quote:
                        quotes[k] = str(quote)[:120]
                    if isinstance(v, dict) and v.get("hedged") is True:
                        hedged.add(k)
        confidence = float(data.get("confidence") or 0.5)
        # Hallucination guards (live 2026-08-10: "Galim patikrinti, ką man
        # reikia daryti?" came back with FIVE facts the caller never said,
        # poisoning the ledger and forcing two phantom clarifies):
        # a question/confusion does not STATE facts, and low-confidence facts
        # are worse than no facts — the deterministic layers cover the gap.
        # 2026-11-06: a QUESTION may carry a fact too („Wi-Fi įjungiau, bet kur slaptažodis?") —
        # the quote check guards it now; only a turn that did not make sense states nothing.
        if turn_type == "confusion" or confidence < limits.get("understand_facts_min_confidence"):
            facts = {}
        elif turn_type == "question":
            # A question states a fact only in the caller's OWN words (live 2026-08-10: five
            # unquoted facts came back for „Galim patikrinti, ką man reikia daryti?").
            facts = {k: v for k, v in facts.items() if quotes.get(k)}
        # Merged step classification (R4): validated exactly like the standalone
        # classifier — unknown labels are dropped so the walker falls back.
        step: dict[str, Any] | None = None
        status: str | None = None
        if step_options:
            status = str(data.get("status") or "").strip().lower() or None
            if status not in REPLY_STATUSES:
                status = None
            step = step_from_status(status, facts, quotes, step_options, step_answers)
        ticket = data.get("ticket") if isinstance(data.get("ticket"), dict) else None
        if ticket is not None:
            answer_type = str(ticket.get("type") or "other").lower()
            value = ticket.get("value")
            ticket = {
                "type": answer_type
                if answer_type in ("answer", "question", "refusal", "other")
                else "other",
                "value": str(value)[:80].strip() if value not in (None, "", "null") else None,
            }
        problem = data.get("problem") if isinstance(data.get("problem"), dict) else None
        if problem is not None:
            label = problem.get("label")
            problem = {
                "label": str(label) if label not in (None, "", "null") else None,
                "confidence": max(0.0, min(1.0, float(problem.get("confidence") or 0.0))),
            }
        # Kurio dokumento agentui reikia. Numeris verčiamas į kelią ir tikrinamas prieš TĄ PATĮ
        # sąrašą, kuris buvo prompte: modelio sugalvotas numeris tyliai atmetamas.
        _listing, sources = _knowledge_map()
        picked = data.get("knowledge")
        knowledge = None
        try:
            index = int(picked)
            if 1 <= index <= len(sources):
                knowledge = sources[index - 1]
        except (TypeError, ValueError):
            knowledge = None
        return {
            "facts": facts,
            "quotes": quotes,
            "knowledge": knowledge,
            "ticket": ticket,
            "problem": problem,
            "type": turn_type,
            "understood": str(data.get("understood") or "")[:200],
            "confusion": str(data.get("confusion") or "")[:200],
            "confidence": confidence,
            "step": step,
            "status": status,
            "hedged": sorted(hedged),
        }
    except Exception as e:  # any failure -> deterministic fallback
        logger.warning(f"understand pass failed: {e}")
        return None


def step_from_status(
    status: str | None,
    facts: dict[str, str],
    quotes: dict[str, str],
    options: dict[str, str],
    answers: dict[str, str] | None,
) -> dict[str, Any] | None:
    """The asked step's answer in the shape the engine reads, made from the reply STATUS and
    the FACTS (2026-11-06: the model no longer returns a separate step label).

    An instruction: answered → done, doing → waiting. A question: the label is the one whose
    `fact=value` the facts carry. „answered" with no such fact is not an answer (the phantom
    answer: „Aha, supratau") — the step is asked again, briefly. A fact with no quote is the
    model's guess: it rides as the label, so the engine confirms it before using it.
    """
    if status is None:
        return None
    unclear = {"label": "unclear", "is_answer": False, "internally_inconsistent": False}
    if set(options) == {"done", "waiting"}:
        if status == "answered":
            return {"label": "done", "is_answer": True, "internally_inconsistent": False,
                    "confidence": 1.0}  # fmt: skip
        label = "waiting" if status == "doing" else "unclear"
        return {**unclear, "label": label, "confidence": 1.0}
    if status == "answered":
        for label, stated in (answers or {}).items():
            if label not in options or "=" not in stated:
                continue
            key, value = stated.split("=", 1)
            if facts.get(key) == value:
                return {
                    "label": label,
                    "is_answer": True,
                    "internally_inconsistent": False,
                    "confidence": 1.0 if quotes.get(key) else 0.6,
                }
        # The phantom answer: answered, but nothing this step waits for. No VALUE comes from it
        # — yet it is not „still doing" either: the engine's own readers („ištraukiau ir
        # įkišau atgal" = done) still get to read it (eval S6, 2026-11-06).
        return {**unclear, "is_answer": True, "confidence": 1.0}
    return {**unclear, "confidence": 1.0}


def understand_ticket(
    utterance: str, *, stage: str, anchor: str, model: str | None = None
) -> dict[str, Any] | None:
    """Read one TICKET-DIALOGUE answer (stage: 'phone' | 'hours') in context —
    predicting caller phrasing is impossible ("Bet kada galima per pietus iš
    ryto" is an HOURS answer, not a question). Returns
    {"value": str|None, "type": "answer|question|refusal|other"};
    None on any failure -> the keyword logic decides as before."""
    if not utterance or not utterance.strip() or stage not in ("phone", "hours"):
        return None
    from ..prompts import load_node_prompt

    task = load_node_prompt(f"sensors/ticket_reader_{stage}")
    system = (
        load_node_prompt("sensors/ticket_reader")
        .replace("<<anchor>>", anchor)
        .replace("<<task>>", task)
    )
    try:
        from src.services.llm.client import llm_json_completion

        data = llm_json_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": utterance[:300]},
            ],
            model=perception_model(model),
            role="ticket_reader",
            temperature=limits.get("perception_temperature"),
            max_tokens=limits.get("perception_max_tokens"),
        )
        if not isinstance(data, dict):
            return None
        answer_type = str(data.get("type") or "other").lower()
        if answer_type not in ("answer", "question", "refusal", "other"):
            answer_type = "other"
        value = data.get("value")
        value = str(value)[:80].strip() if value not in (None, "", "null") else None
        return {"value": value, "type": answer_type}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"understand_ticket failed: {e}")
        return None

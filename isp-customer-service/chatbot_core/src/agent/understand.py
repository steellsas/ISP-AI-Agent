"""SUPRATIMO pass'as — the understanding layer (Ledger v2.5, agreed 2026-08-10).

ONE small-model JSON call per caller turn in the diagnosis stage reads the
reply IN CONTEXT (the pending question, the fault's evidence needs, the ledger,
the last conversation turns) and returns:

    faktai      — canonical evidence values it heard (validated against the spec),
    tipas       — atsakymas | klausimas | nukrypimas | nesupratimas | prieštaravimas,
    supratau    — half-sentence of WHAT was understood (the narrator's
                  acknowledgement: "Gerai — routerį radote."),
    neaiskumas  — what exactly the caller did not understand (drives the
                  re-explain-DIFFERENTLY wording),
    pasitikejimas — 0..1.

It is a SENSOR: it never touches state. The ENGINE decides — facts go through
the same set_fact discipline (conflicts, telemetry-over-words), tipas feeds the
existing routes (side_topic, clarify). Returns None on ANY failure so the
caller falls back to the deterministic keyword extractor — a conversation must
never stall on a model hiccup. Gated by UNDERSTAND=on (config page); unit
tests run with CLASSIFIER=off which disables it too.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_TIPAI = {"atsakymas", "klausimas", "nukrypimas", "nesupratimas", "prieštaravimas"}

# Canonical values per key — the model may only pick from these (plus omit).
_ALLOWED = {
    "device_present": {"rado", "nerado"},
    "lights": {"nedega", "dega", "mirksi"},
    "power_cable": {"įkištas", "atjungtas"},
    "outlet_works": {"bandyta", "neveikia"},
    "has_computer": {"yes", "no"},
}


def enabled() -> bool:
    if os.getenv("CLASSIFIER", "on").lower() == "off":
        return False  # deterministic test mode — no model calls at all
    return os.getenv("UNDERSTAND", "on").lower() == "on"


def _system(anchor: str, needs: str, ledger: str) -> str:
    allowed = "; ".join(f"{k}: {sorted(v)}" for k, v in _ALLOWED.items())
    return (
        "Tu skaitai KLIENTO atsakymą lietuviškame ISP pagalbos skambutyje. STT "
        "tekstas gali būti darkytas — spręsk pagal PRASMĘ ir kontekstą, ne pagal "
        "raides.\n"
        f"AGENTO PASKUTINIS KLAUSIMAS: „{anchor}“\n"
        f"KĄ GEDIMUI REIKIA IŠSIAIŠKINTI: {needs}\n"
        f"KAS JAU ŽINOMA: {ledger or '(nieko)'}\n"
        "Grąžink TIK JSON:\n"
        '{"faktai": {raktas: reikšmė, ...}, "tipas": "atsakymas|klausimas|'
        'nukrypimas|nesupratimas|prieštaravimas", "supratau": "puse sakinio kas '
        'suprasta", "neaiskumas": "ko klientas nesuprato arba tuščia", '
        '"pasitikejimas": 0.0-1.0}\n'
        f"- faktai: TIK šie raktai ir reikšmės: {allowed}. Rašyk tik tai, ką "
        "klientas REALIAI pasakė (tiesiogiai ar iš konteksto: „Radau.“ atsakant į "
        "„Radote?“ = device_present: rado; „ne daganiai viena“ laukiant lempučių = "
        "lights: nedega). NIEKO nespėk.\n"
        "- tipas: atsakymas (atsako į klausimą, kad ir dalinai); klausimas "
        "(klausia mūsų — apie gedimą AR šalutinio); nukrypimas (kalba ne apie "
        "gedimą, neklausia); nesupratimas (sako, kad nesupranta / neranda / "
        "nežino kaip); prieštaravimas (paneigia, ką sakė anksčiau pagal KAS JAU "
        "ŽINOMA).\n"
        "- supratau: trumpa santrauka agentui atspindėti klientui (lietuviškai).\n"
        "- neaiskumas: pildyk tik kai tipas=nesupratimas — KO konkrečiai nesuprato."
    )


def understand(
    utterance: str,
    *,
    anchor: str,
    needs: str,
    ledger_summary: str,
    history_tail: list[dict[str, str]] | None = None,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Read one caller turn. None on any failure -> keyword fallback."""
    if not utterance or not utterance.strip():
        return None
    try:
        from src.services.llm.client import llm_json_completion

        messages: list[dict[str, str]] = [
            {"role": "system", "content": _system(anchor, needs, ledger_summary)}
        ]
        for m in (history_tail or [])[-4:]:
            role = "assistant" if m.get("role") == "assistant" else "user"
            content = (m.get("content") or "")[:200]
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": utterance[:400]})
        data = llm_json_completion(messages=messages, model=model)
        if not isinstance(data, dict):
            return None
        tipas = str(data.get("tipas") or "atsakymas").lower()
        if tipas not in _TIPAI:
            tipas = "atsakymas"
        raw_facts = data.get("faktai")
        facts: dict[str, str] = {}
        if isinstance(raw_facts, dict):
            for k, v in raw_facts.items():
                if k in _ALLOWED and str(v) in _ALLOWED[k]:
                    facts[k] = str(v)
        return {
            "faktai": facts,
            "tipas": tipas,
            "supratau": str(data.get("supratau") or "")[:200],
            "neaiskumas": str(data.get("neaiskumas") or "")[:200],
            "pasitikejimas": float(data.get("pasitikejimas") or 0.5),
        }
    except Exception as e:  # any failure -> deterministic fallback
        logger.warning(f"understand pass failed: {e}")
        return None

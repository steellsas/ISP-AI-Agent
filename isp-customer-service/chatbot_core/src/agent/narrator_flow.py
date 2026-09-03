"""
Narrator flow — what the LLM narrator sees and how tool results reach it:
message assembly, the KNOWN FACTS block, per-step tool scoping, playbook
injection, tool-result augmentation and state updates from observations.

R3 extraction (docs/ROADMAP_REFACTORING.md par. 4): moved verbatim out of
ReactAgent. Functions take the engine explicitly; intra-family calls go
through the engine delegate seam. execute_tool resolves lazily from
react_agent so the tests' import-fallback stubs apply.
"""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import logging
import os  # noqa: F401
import re  # noqa: F401
from typing import Any  # noqa: F401

from .glossary import DIAGNOSIS_LT as _DIAGNOSIS_LT  # noqa: F401
from .glossary import PROBLEM_LT as _PROBLEM_LT

logger = logging.getLogger(__name__)


def execute_tool(name, args):
    """Lazy pass-through to react_agent's execute_tool (test stubs included)."""
    from . import react_agent

    return react_agent.execute_tool(name, args)


_DIRECTIVE_PROMPT: str | None = None


def _directive_system_prompt() -> str:
    """Persona + style only — the lean system prompt for directive turns.
    Cached module-wide (byte-stable => provider prompt cache friendly)."""
    global _DIRECTIVE_PROMPT
    if _DIRECTIVE_PROMPT is None:
        from .prompts import load_node_prompt

        parts = []
        for name in ("partials/identity", "partials/style", "partials/directives"):
            try:
                parts.append(load_node_prompt(name))
            except Exception:  # pragma: no cover - a missing partial degrades soft
                pass
        parts.append(
            "Kalbi telefonu lietuviškai. Vykdyk TIK žemiau esančią KNOWN FACTS "
            "bloko direktyvą — nieko daugiau nesiūlyk ir neklausk."
        )
        _DIRECTIVE_PROMPT = "\n\n".join(p for p in parts if p)
    return _DIRECTIVE_PROMPT


def build_messages(engine, user_input: str = None) -> list:
    """
    Build the message payload for one LLM call.

    Token cost grows with conversation length because the whole history is
    resent every turn. To keep voice latency and cost bounded we send only
    a recent *window* of history (see _prune_history) plus a compact block
    of durable facts re-injected from AgentState (see _state_facts_block),
    so pruning old messages never loses the resolved customer/problem/ticket
    context. The full transcript still lives in AgentState.messages.

    Prompt-cache friendliness: the system prompt is kept BYTE-STABLE across
    turns so providers can cache the prefix. The durable-fact block changes
    as the call progresses, so it goes in a SEPARATE trailing system message
    (just before the new user input) rather than being concatenated into the
    system content — concatenating would mutate the system message every turn
    and bust the cache (the real cost, not the few fact tokens).
    """
    # Stable system prefix (cacheable). DIRECTIVE turns (zones 1–3) swap in a
    # MINIMAL persona-only prompt: the full prompt's identification/procedure
    # partials kept overriding the directive (live 2026-08-20: the model
    # offered the address on the anamnesis turn, straight from the procedure
    # text) — a directive turn has exactly ONE instruction, the facts block.
    directive_turn = bool(
        getattr(engine, "_ident_directive", None) or getattr(engine, "_ticket_directive", None)
    )
    if directive_turn:
        messages = [{"role": "system", "content": _directive_system_prompt()}]
    else:
        # Prompt hygiene step 1 (Andrius 2026-08-26): the NODE prompt is
        # static per stage — folded into the LEADING system message it joins
        # the cacheable prefix (one stable prefix per node; providers keep
        # several prefixes warm in parallel). It used to trail the facts
        # block, re-sent uncached every turn.
        prefix = engine.system_prompt
        if engine._node_prompt:
            prefix = f"{prefix}\n\n{engine._node_prompt}"
        messages = [{"role": "system", "content": prefix}]

    # Istorija v2 (hygiene step 3): when the window cut older turns, a short
    # DETERMINISTIC summary from STATE bridges the gap — the model never sees
    # a conversation that starts mid-air.
    summary = history_summary(engine)
    if summary:
        messages.append({"role": "system", "content": summary})

    # Add recent conversation history (windowed, tool-pairing safe)
    messages.extend(engine._prune_history(engine.state.messages))

    # Durable facts as a trailing system message (kept OUT of the cached
    # prefix). None until something is resolved this call.
    facts = engine._state_facts_block()
    if facts:
        messages.append({"role": "system", "content": facts})

    # Add new user input if provided
    if user_input:
        messages.append({"role": "user", "content": user_input})

    # Debug: what the LLM actually SEES this turn — the dynamic facts block is
    # where "why did it say that" lives. Off by default (would bloat the trace);
    # DEBUG_LLM=1 turns it on. The stable system prompt is omitted (it never
    # changes); full messages only when DEBUG_LLM=full.
    if os.environ.get("DEBUG_LLM"):
        payload: dict[str, Any] = {
            "node": engine._active_node,
            "facts": facts,
            "tools": sorted(t["function"]["name"] for t in engine._scoped_tools_schema()),
            "history_msgs": len(messages) - 1,
        }
        if os.environ.get("DEBUG_LLM") == "full":
            payload["messages"] = messages
        engine.tracer.emit("llm_input", **payload)

    return messages


def scoped_tools_schema(engine) -> list:
    """The tool schema for the current node — all tools, or the subset a graph
    node restricted the model to (engine._active_tool_names).

    Per-step scoping while a resolution strategy is active: the engine owns all
    diagnostics (withheld); an ACTION/ESCALATE step exposes ONLY its tool so the
    model does that action once; a CONFIRM step (or a case being closed) exposes
    NO action tool. This prevents both 'binds before confirm' and the tool-call
    loop where the model re-calls the one exposed tool until the 5-call limit."""
    # Case closed mid-turn (bind resolved / ticket registered): no tools at all,
    # so the model narrates the close instead of looping tool calls to the limit
    # (which surfaced the 'negaliu apdoroti' fallback).
    if engine.state.case_closed:
        return []
    # Directive turns are SPEECH-ONLY (zones 1–3, live 2026-08-20): with tools
    # exposed the model grabbed resolve_address on the anamnesis turn and
    # skipped the whole ladder — the engine owns the mechanics, the narrator
    # only words the one goal in the facts block.
    if getattr(engine, "_ident_directive", None) or getattr(engine, "_ticket_directive", None):
        return []
    schema = engine.tools_schema
    if engine._active_tool_names is not None:
        schema = [
            t for t in schema if t.get("function", {}).get("name") in engine._active_tool_names
        ]
    if engine.state.resolution is not None:
        from .resolution import StepKind, get_strategy

        strat = get_strategy(engine.state.resolution.get("verdict"))
        step = strat.step(engine.state.resolution.get("step", "")) if strat else None
        if step is not None:
            # Scope to EXACTLY this step's tools. A CONFIRM / INSTRUCT / VERIFY
            # step has NONE — the model just talks while the engine owns the
            # diagnostics, the action and the closing. This is what stops the
            # model spamming an unrelated lookup while it "waits" (observed:
            # check_outages looped to the call limit -> 'negaliu apdoroti').
            allowed = step.tools
            # An ACTION step exposes its tool ONLY as a fallback if the engine
            # has not already run it. Once action_done is set, WITHHOLD it — the
            # model only announces; otherwise the single exposed tool gets
            # re-called to the limit (observed: update_mac x6 -> 'negaliu apdoroti').
            if step.kind == StepKind.ACTION and engine.state.resolution.get("action_done"):
                allowed = frozenset()
            schema = [t for t in schema if t.get("function", {}).get("name") in allowed]
        else:
            schema = [
                t
                for t in schema
                if (n := t.get("function", {}).get("name")) not in engine._STRATEGY_DIAG_TOOLS
                and n not in engine._STRATEGY_ACTION_TOOLS
            ]
    return schema


def history_summary(engine) -> str | None:
    """Hygiene step 3 (istorija v2, Andrius 2026-08-27): when older turns fall
    out of the window, the narrator gets a 1–2 line DETERMINISTIC summary
    built from STATE — zero LLM cost, never hallucinates, always fresh. The
    full transcript stays in AgentState.messages (nothing is deleted)."""
    s = engine.state
    if len(s.messages) <= engine.config.history_window_messages:
        return None  # nothing was cut — no summary needed
    bits: list[str] = []
    if s.problem_type:
        when = f", dingo {s.anamnesis_when}" if s.anamnesis_when else ""
        trig = f", po: {s.anamnesis_trigger}" if s.anamnesis_trigger else ""
        bits.append(f"Problema: {s.problem_type}{when}{trig}")
    if s.customer_id:
        bits.append(f"Klientas: {s.customer_address or s.customer_id}")
    if s.caller_name:
        bits.append(f"skambina {s.caller_name}")
    r = s.resolution or {}
    if r.get("verdict"):
        from .glossary import DIAGNOSIS_LT

        gloss = DIAGNOSIS_LT.get(r["verdict"], r["verdict"])
        bits.append(f"Diagnozė: {gloss}")
    if s.evidence:
        from .evidence import summary_lt

        est = summary_lt(s.evidence)
        if est:
            bits.append(f"Nustatyta: {est}")
    if s.ticket_id:
        bits.append(f"Tiketas: {s.ticket_id}")
    if not bits:
        return None
    return (
        "POKALBIO PRADŽIOS SANTRAUKA (senesnės replikos praleistos; faktai "
        "galioja): " + "; ".join(bits) + "."
    )


_RECALL_MARKS = ("minejau", "sakiau", "kartoju", "jau aiskinau", "anksciau sakiau")


def recall_lines(engine) -> str | None:
    """Hygiene step 3 — the RECALL trigger: when the caller references their
    own earlier words ("juk SAKIAU…"), the matching OLD user lines (outside
    the window) are pulled back into the facts block for THIS turn. Pure
    keyword overlap on folded content words — no vectors, no latency."""
    from .evidence import _fold

    s = engine.state
    heard = _fold(s.last_heard or "")
    if not heard or not any(m in heard for m in _RECALL_MARKS):
        return None
    window = engine.config.history_window_messages
    old = s.messages[:-window] if len(s.messages) > window else []
    old_user = [m.get("content") or "" for m in old if m.get("role") == "user"]
    if not old_user:
        return None
    words = {w for w in heard.split() if len(w) >= 5}
    scored = []
    for text in old_user:
        overlap = sum(1 for w in _fold(text).split() if len(w) >= 5 and w in words)
        if overlap:
            scored.append((overlap, text))
    if not scored:
        return None
    scored.sort(key=lambda p: -p[0])
    picks = [t[:160] for _n, t in scored[:2]]
    quoted = " / ".join(f"„{t}“" for t in picks)
    return (
        "- KLIENTAS PRIMENA, KĄ SAKĖ ANKSČIAU — jo ankstesnės frazės: "
        f"{quoted}. Atsižvelk į jas ir neprašyk kartoti."
    )


def prune_history(engine, messages: list) -> list:
    """
    Return the most recent slice of history that fits the configured window.

    Pairing safety: native tool calling requires every role:"tool" message to
    be preceded by the assistant message that issued the matching tool_calls.
    A naive "last N" cut can land mid-exchange and orphan a tool result, which
    the chat API rejects (400). So if the window would start on a tool result,
    we walk the start index left until it lands on the owning assistant
    message, keeping the exchange intact.
    """
    window = engine.config.history_window_messages
    if window <= 0 or len(messages) <= window:
        return list(messages)

    start = len(messages) - window
    while start > 0 and messages[start].get("role") == "tool":
        start -= 1
    return messages[start:]


def state_facts_block(engine) -> str | None:
    """
    Render durable facts from AgentState as a short system addendum.

    These survive history pruning (they live in AgentState, not the message
    log), so re-injecting them keeps the model from re-asking for details it
    already resolved. Returns None when nothing has been resolved yet.
    """
    s = engine.state
    facts: list[str] = []
    # Side-topic turn (deviation): the ONLY permitted content is the FAQ hit
    # (or an honest "not my area"), then the RETURN ANCHOR — the engine's
    # exact pending question. Leads the block; nothing else competes.
    if engine._side_topic_this_turn:
        from .faq import match as faq_match

        hits = faq_match(s.last_heard)
        zinios = " ".join(f"[{e.get('tema')}] {e['atsakymas']}" for e in hits) or (
            "(šiai temai ŽINOMO ATSAKYMO NĖRA — mandagiai pasakyk, kad tai ne tavo sritis)"
        )
        # The topic is DETERMINISTIC when the FAQ matched — the model once
        # copied a prompt example ("Klausiate apie kainą") for topics the
        # caller never raised; naming the real topic removes the template.
        tema = str(hits[0].get("tema", "")).replace("_", " ") if hits else ""
        tema_line = (
            f"Kliento tema: {tema}. "
            if tema
            else "Temą įvardink iš PASKUTINĖS kliento frazės — jokių kitų temų. "
        )
        facts.append(
            "- NUKRYPIMAS NUO GEDIMO: klientas klausia šalutinio dalyko. "
            f"{tema_line}Atsakyk VIENU-DVIEM sakiniais TIK pagal ŽINOMUS "
            f"ATSAKYMUS: {zinios} NIEKO neišgalvok (jokių sumų, terminų, "
            f"pažadų). Tada BŪTINAI grįžk prie gedimo — pakartok: "
            f"„{engine.anchor_text()}“"
        )
    # Ticket-dialogue off-script turn: the caller asked something instead of
    # answering the stage question — give the LLM the answers it may need and
    # the EXACT question to re-ask. Leads the block; nothing else competes.
    if engine._ticket_stage in ("phone", "hours"):
        from .identification import phrase

        pending = (
            phrase("ticket_phone") if engine._ticket_stage == "phone" else phrase("ticket_hours")
        )
        facts.append(
            "- TIKETO DIALOGAS: registruojame gedimą (priežastis: "
            f"{engine._ticket_need()}). Skambinančiojo numeris: "
            f"{engine._fmt_phone(s.caller_phone) or 'nežinomas'}. Tiketas DAR "
            "neužregistruotas — nesakyk „užregistravau“. Atsakyk į kliento "
            f"klausimą VIENU sakiniu ir būtinai pakartok klausimą: „{pending}“"
        )
    # Ticket refusal WITH solving content (2026-08-11): the dialogue was
    # dropped, the call stays OPEN — the reply returns to the fix.
    if getattr(engine, "_resume_fix_note", False):
        engine._resume_fix_note = False
        facts.append(
            "- KLIENTAS ATSISAKĖ REGISTRACIJOS IR NORI TĘSTI SPRENDIMĄ: pasakyk "
            "vienu sakiniu, kad meistro neregistruoji, ir GRĮŽK prie paskutinės "
            "sprendimo instrukcijos — pakartok ją arba atsakyk į kliento "
            "klausimą apie ją. Pokalbio NEbaik."
        )
    # A (2026-08-21): secondary problems — before the goodbye the agent asks
    # back about the OTHER complaints heard mid-call ("minėjot, kad lėtai
    # veikė — ar dabar gerai?"); they are already on the ticket.
    if s.case_closed and getattr(s, "secondary_problems", None):
        temos = "; ".join(f"„{x['tekstas']}“" for x in s.secondary_problems)
        facts.append(
            "- PAPILDOMOS PROBLEMOS (prieš atsisveikinant PASITEIRAUK): klientas "
            f"pokalbyje minėjo: {temos}. Paklausk, ar tai dar aktualu; pasakyk, "
            "kad meistrui perduota (jau įrašyta registracijoje)."
        )

    # C (Andrius 2026-08-20): RETURN AFTER A DETOUR — the reply re-anchors from
    # the LEDGER (kur esame, ką padarėme, kas liko / gal jau sprendimas), never
    # improvises a fresh diagnostic (live: 'ar prijungtas prie maitinimo?' re-
    # asked after a detour while all three facts were already established).
    if getattr(engine, "_resync_note", False):
        engine._resync_note = False
        nustatyta = ""
        if s.evidence:
            from .evidence import summary_lt as _sum

            nustatyta = _sum(s.evidence)
        facts.append(
            "- GRĮŽTAME PRIE SPRENDIMO (po nukrypimo): vienu sakiniu primink, kur "
            + ("esame — nustatyta: " + nustatyta + " — " if nustatyta else "esame ")
            + "ir tęsk NUO DABARTINIO TIKSLO pagal žemiau esančias direktyvas "
            "(DAR AIŠKINAMĖS / IŠVADOS MOMENTAS / KLAUSK DABAR). NIEKO neklausk "
            "iš naujo, kas jau nustatyta; jei išvada jau aiški — pasakyk ją ir "
            "siūlyk sprendimą."
        )
    # D1 delivery ledger (2026-08-25): a barge-in cut the previous reply — the
    # caller heard only its beginning. The unheard tail is surfaced ONCE so the
    # narrator can weave the essential part back in instead of assuming it
    # landed (live: the agent referenced instructions the caller never heard).
    tail = getattr(engine, "_undelivered_tail", None)
    if tail:
        engine._undelivered_tail = None
        facts.append(
            f"- KLIENTAS NEGIRDĖJO (pertraukė): „{tail[:160]}“ — jei svarbu, "
            "pasakyk trumpai savais žodžiais."
        )
    # Duplex-hearing 2: words the caller said OVER the agent's voice — the
    # facts already landed via the deterministic ingest; the narrator just
    # shows it HEARD ("kaip minėjot…") and never re-asks what these answered.
    oh = getattr(engine, "_overlay_heard", None)
    if oh:
        engine._overlay_heard = None
        quoted = " / ".join(f"„{t[:120]}“" for t in oh)
        facts.append(
            f"- KOL KALBĖJAI, KLIENTAS ĮSITERPĖ: {quoted} — atsižvelk į tai; "
            "jei tai atsakymas į tavo klausimą, nekartok klausimo."
        )
    # Andrius 2026-08-26: the cut-off QUESTION never reached the caller — they
    # were NOT answering it. React to what they said, then ask it anew.
    uq = getattr(engine, "_unheard_question", None)
    if uq:
        engine._unheard_question = None
        facts.append(
            "- KLAUSIMAS NEIŠĖJO Į ETERĮ: klientas TAVO klausimo negirdėjo "
            "(pertraukė anksčiau), tad jo žodžiai — NE atsakymas į jį. "
            "Pirmiausia sureaguok į tai, ką klientas pasakė, tada užduok "
            f"klausimą iš naujo savais žodžiais (vienas „?“): „{uq[:160]}“"
        )
    # Understanding-pass directives (2026-08-10): the acknowledgement makes
    # the caller feel HEARD; the confusion note turns re-asks into
    # re-EXPLANATIONS aimed at what was actually not understood.
    u = getattr(engine, "_last_understanding", None)
    if u is not None and not engine._side_topic_this_turn and not s.case_closed:
        if u.get("supratau"):
            facts.append(
                f"- PATVIRTINK, ką supratai, puse sakinio („{u['supratau']}“) — "
                "tada tęsk vienu kitu klausimu/žingsniu. KREIPKIS į klientą "
                "(„Supratau — …“), niekada nekalbėk apie jį trečiuoju asmeniu "
                "(NE „Klientas sutinka…“)."
            )
        if u.get("tipas") == "nesupratimas" and u.get("neaiskumas"):
            facts.append(
                f"- KLIENTAS NESUPRATO: {u['neaiskumas']} — paaiškink KITAIS "
                "žodžiais, paprasčiau, buitiškai; to paties sakinio nekartok."
            )
    # Per-turn guards (deterministic, set in _pre_turn_guards) lead the block —
    # they override the model's own reading of the last reply.
    if getattr(engine, "_addr_confirm_note", None):
        facts.append(engine._addr_confirm_note)
    # F2: the failed lookup's per-level diagnosis — the narrator tells the
    # caller what WAS found and asks to correct only the missing part.
    if getattr(engine, "_addr_diag_note", None) and not s.customer_id:
        facts.append(engine._addr_diag_note)
    # F3 (Andrius 2026-08-20): a caller who is NOT giving the address gets ONE
    # warm encouragement with the WHY and the hints — never an endless re-ask.
    if (
        not s.customer_id
        and s.problem_type
        and s.turn_count >= 4
        and not s.profile.street.value
        and not getattr(engine, "_addr_encouraged", False)
    ):
        engine._addr_encouraged = True
        facts.append(
            "- PARAGINIMAS DĖL ADRESO (vieną kartą, šiltai): paaiškink, KODĖL "
            "adreso reikia — be jo nematai kliento linijos ir negali patikrinti "
            "gedimo. Užuominos: sutartis gali būti kito šeimos nario vardu; "
            "gatvės pavadinimas galėjo pasikeisti; užtenka gatvės ir namo "
            "numerio. Paklausk, ką klientas žino."
        )
    if getattr(engine, "_reopen_note", False) and not s.customer_id:
        facts.append(
            "- KLIENTAS PATIKSLINO: skambina dėl KITO adreso nei buvo nustatyta. "
            "Atsiprašyk vienu sakiniu ir paprašyk pasakyti adresą, dėl kurio "
            "skambina (jei jau pasakė — žr. HEARD ADDRESS ir naudok jį). Ankstesnio "
            "adreso ir jo diagnozės NEBEminėk."
        )
    # Proactive mass-outage (the ONE time the phone is used up front): if the
    # caller's street has an active outage, inform immediately instead of
    # identifying. Leads the block so it drives the FIRST reply. Reveals only
    # the street, and as a question — not an identity claim.
    if s.preflight_outage and not s.customer_id and not s.case_closed:
        o = s.preflight_outage
        eta = f", atstatymas iki {o['eta']}" if o.get("eta") else ""
        facts.append(
            f"- PROACTIVE OUTAGE: the caller's number is registered on {o['street']}, "
            f"which has an ACTIVE mass outage{eta}. The caller has NOT named this "
            f"street — do NOT say 'Girdžiu {o['street']}' or claim they mentioned it. "
            f"Ask NEUTRALLY and WAIT for their answer: 'Ar skambinate dėl "
            f"{o['street']}?'. ONLY after they confirm, inform about the outage + "
            f"estimated time and then call close_case(reason='outage'). Do NOT run "
            f"identification (no 'Radau sutartį', no house/apartment). If they name a "
            f"DIFFERENT street, drop this and ask for the address."
        )

    # Phone account: the caller's number is in the DB. Offer its registered
    # address FIRST (before asking them to dictate anything) — the number is
    # already tied to that address, so it reveals nothing new and saves the
    # STT-fragile spoken house/apartment. Fires until they name a DIFFERENT
    # street (then they are calling about someone else's address — case B).
    # Every named part must match (or be unsaid): if the caller gives the same
    # street but a DIFFERENT flat ("Tilžės 60, butas 3"), this is someone else's
    # address — stop offering, or the model reuses the phone's parts and resolves
    # the WRONG customer (observed: said butas 3, resolved butas 7).
    def _fits(said, mine) -> bool:
        return not said or str(said).lower() == str(mine or "").lower()

    from .identification import extra_questions_guidance, offer_phone_address

    if (
        offer_phone_address()
        and not s.customer_id
        and not s.preflight_outage
        and s.phone_candidate
        and s.phone_candidate.get("street")
        # Directive turns (zones 2–3, live 2026-08-20): this block told the
        # model to OFFER the address and it obeyed — on the anamnesis turn.
        # The ladder decides WHEN the offer happens; the block yields.
        and not getattr(engine, "_ident_directive", None)
        and not getattr(engine, "_ticket_directive", None)
        # Ladder order (live 2026-08-21): the offer comes AFTER the problem
        # and the anamnesis — a garbled first utterance must not trigger it.
        and s.problem_type
        and _fits(s.profile.street.value, s.phone_candidate.get("street"))
        and _fits(s.profile.house.value, s.phone_candidate.get("house"))
        and _fits(s.profile.apartment.value, s.phone_candidate.get("apartment"))
    ):
        c = s.phone_candidate
        flat = f", butas {c['apartment']}" if c.get("apartment") else ""
        flat_arg = f", apartment_number='{c['apartment']}'" if c.get("apartment") else ""
        facts.append(
            f"- PHONE ACCOUNT: the caller's number is registered at {c['address']}. "
            f"Offer THIS address FIRST, before asking them to dictate anything: "
            f'"Ar skambinate dėl {c["street"]} {c["house"]}{flat}?". On yes, call '
            f"resolve_address(city='{c['city']}', street='{c['street']}', "
            f"house_number='{c['house']}'{flat_arg}) to identify, then diagnose. If they "
            f"say a DIFFERENT address (someone else's — that is allowed), ask them to "
            f"state the address where the fault is and take THAT."
        )
    # DB-grounded verdict on the accumulated address (set in the prefill).
    if engine._db_address_note and not s.customer_id:
        facts.append(engine._db_address_note)
    # Extra verification questions declared in identification.yaml (e.g. the name),
    # asked while still identifying. Empty by default → nothing added.
    if not s.customer_id:
        extra = extra_questions_guidance()
        if extra:
            facts.append(extra)
    if s.customer_id:
        facts.append(f"- Customer ID: {s.customer_id}")
    if s.customer_name:
        facts.append(f"- Customer name: {s.customer_name}")
    if s.customer_address:
        facts.append(f"- Address: {s.customer_address}")
    if s.problem_type:
        facts.append(f"- Problem type: {s.problem_type}")
    if s.symptoms:
        parts = ", ".join(f"{k}={v}" for k, v in s.symptoms.items())
        facts.append(f"- SYMPTOMAI (kliento): {parts}.")
    if s.ticket_id:
        facts.append(f"- Ticket: {s.ticket_id}")
    if s.case_closed and s.is_complete:
        # The caller said goodbye / "no more" — END on ONE short farewell.
        facts.append(
            "- POKALBIS BAIGTAS: klientas atsisveikino / neturi daugiau klausimų. "
            "Pasakyk TIK vieną trumpą atsisveikinimą („Ačiū, kad paskambinote. "
            "Geros dienos!“) ir NIEKO daugiau — jokių naujų klausimų."
        )
    elif s.case_closed:
        facts.append(f"- Byla UŽDARYTA (priežastis: {s.closed_reason or 'resolved'}).")
        # Engine-registered ticket (consent-free ESCALATE): the narrator ANNOUNCES
        # the registration — it must not ask permission or offer to register again.
        if s.closed_reason == "registered" and s.ticket_id:
            facts.append(
                "- UŽREGISTRUOTA: gedimas jau užregistruotas (variklis tai padarė). "
                "Pasakyk vienu sakiniu: užregistravau gedimą, kolegos susisieks ir "
                "detaliau paaiškins. NEklausk sutikimo, NEsiūlyk registruoti dar "
                "kartą, neskaityk ticket ID."
            )
        # Just resolved: confirm briefly, then OFFER one more thing and WAIT — do
        # NOT sign off yet (the engine ends the call once the caller declines).
        if s.closed_reason == "resolved" and s.resolution:
            facts.append(
                "- IŠSPRĘSTA: klientas patvirtino, kad internetas veikia. Trumpai "
                "padžiaukis, kad sutvarkyta, ir paklausk „Ar dar kuo nors galiu "
                "padėti?“. NEatsisveikink dar, NEklausk apie įrangą, NEprašyk "
                "tikrinti iš naujo."
            )
    # Repeat-guard nudge (scaled): the caller's last reply did not advance us.
    # Don't loop the same question — acknowledge, narrow, then change tactic.
    # The account-code tactic belongs to IDENTIFICATION only — once the customer is
    # known it leaked into late-call narration ("Gal turite abonento kodą?" right
    # after registering a ticket, observed live).
    if s.stuck_count >= 2 and not s.customer_id:
        facts.append(
            "- STRIGTI: to paties klausimo NEBEKARTOK. Pakeisk taktiką — pasiūlyk "
            "abonento kodą („Gal turite abonento kodą nuo sąskaitos?“) arba "
            "užregistruok problemą atskambinimui."
        )
    elif s.stuck_count >= 2:
        facts.append(
            "- STRIGTI: to paties klausimo NEBEKARTOK. Perfrazuok kitaip arba "
            "pasiūlyk užregistruoti gedimą (technikas susisieks). NEklausk abonento "
            "kodo — klientas jau identifikuotas."
        )
    elif s.stuck_count == 1:
        extra = (
            " Praeitą klausimą uždavei pažodžiui — BŪTINAI perfrazuok."
            if engine._repeated_verbatim
            else ""
        )
        if s.last_heard:
            # We DID hear them — we just could not use it. Never say "neišgirdau"
            # here: reflect the actual words and name the part that is unclear, so
            # the caller knows they were heard and what exactly to repeat.
            facts.append(
                f"- NESUPRATAU (girdėjau!): klientas ką tik pasakė „{s.last_heard}“, bet "
                "iš to nepavyko paimti, ko reikia. NESAKYK „neišgirdau“ — pasakyk, ką "
                "girdėjai ir ko NEsupratai, ir paprašyk pakartoti TIK tą dalį: "
                "„Girdžiu „…“, bet nesupratau gatvės — pakartokite ją, prašau.“ Jei "
                "klientas iš tikrųjų kalba APIE KĄ KITA (klausia ko nors, tikslinasi) — "
                "atsakyk į TAI, o ne kartok savo klausimą." + extra
            )
        else:
            # Silence. The caller may just be listening or thinking, so do NOT
            # apologise at them — "neišgirdau" after they said nothing reads as if
            # THEY failed. Leave the pause; simply ask for what is needed.
            facts.append(
                "- TYLA (klientas nieko nepasakė): NESAKYK „neišgirdau“ — jis gali "
                "tiesiog klausytis ar galvoti. Ramiai, be atsiprašinėjimo, paklausk "
                "to, ko reikia (pvz. gatvės), arba pasitikslink „Ar mane girdite?“. "
                "Neskubėk." + extra
            )
    # Raw-buffer reconciliation: once we're stuck AND still unidentified, hand
    # the LLM EVERYTHING the caller said so far. VAD/STT splits and garbles
    # spoken numbers ("šešiasdešimt" -> "šešias dešimt" -> a fragment that
    # parses as 10, not 60); no single turn resolves, but the whole buffer
    # lets the model infer the intended address. Only kicks in when the
    # deterministic path has stalled, so the clean case stays LLM-free.
    if not s.customer_id and s.stuck_count >= 1 and len(s.heard_utterances) >= 2:
        recent = " | ".join(s.heard_utterances[-8:])
        facts.append(
            "- ALL HEARD (reconcile): the caller has said these pieces so far: "
            f'"{recent}". STT may have split or garbled a spoken number '
            '("šešiasdešimt" 60 can arrive as "šešias dešimt" and mis-parse to 10). '
            "Infer the MOST LIKELY full address from everything above (prefer the "
            "latest correction), then call resolve_address with it — do not make the "
            "caller repeat again if you can reasonably infer it."
        )
    # Outage reported (restricted mode): an active outage IS the answer, so stop
    # identifying/diagnosing — but stay available for the caller's follow-ups
    # (ETA, compensation) and close only when they are done (close_case).
    if s.outage_reported and not s.case_closed:
        facts.append(
            "- GEDIMAS PASKELBTAS šiai gatvei — tai galutinis atsakymas. NEklausk "
            "namo/buto, NEdiagnozuok, NEsiūlyk maitinimo/laidų. Atsakyk į kliento "
            "klausimus apie gedimą (laikas, eiga, kompensacija; gali naudoti "
            "search_knowledge). Kai klientas supranta / lauks — kviesk "
            "close_case(reason='outage')."
        )
    # Diagnostic findings (case state), per domain: durable current truth, so
    # the agent reconciles them with the caller and never re-runs / loses them.
    # Only active domains are surfaced (lean — history lives in the trace, §12.7).
    # BUT once the strategy has run the action (telemetry_fixed recorded), the
    # raw finding is STALE — surfacing "foreign_mac: kitas įrenginys" post-bind
    # made the agent re-narrate the solved problem ("dar nepririštas") every
    # turn. Past the bind, the step's own hint is the single source of truth.
    past_action = bool(s.resolution) and "telemetry_fixed" in (s.resolution or {})
    # Identification ladder's last rung: the caller-intro question is OWED (asked
    # this reply) — the deferred check result comes next turn, so the finding facts
    # are suppressed to keep the model from blurting it alongside the question.
    caller_pending = bool(s.customer_id) and engine._result_pending and not s.caller_name
    if caller_pending:
        from .identification import caller_question

        facts.append(
            "- IDENTIFIKACIJOS PABAIGA: patikra atlikta, bet rezultato dar "
            f"NESAKYK. Šiame atsakyme TIK klausimas: „{caller_question()}“. "
            "Jokio rezultato, jokių instrukcijų."
        )
    elif s.customer_id and engine._result_pending and s.caller_name:
        # The caller introduced themselves — deliver the deferred result NOW.
        facts.append("- REZULTATO PRISTATYMAS:" + engine._result_narration_tail())
    # KREIPINYS (live 2026-08-25: the LLM addressed the caller "Giedriau" — the
    # DB account holder's name for that address — while the caller had said
    # "Andrius". The tool results carry the contract holder's name; it is
    # ACCOUNT DATA, not a greeting, and the caller need not be the holder).
    if s.customer_id:
        if s.caller_name:
            facts.append(
                f"- KREIPINYS: „{s.caller_name}“ (arba be vardo). Įrankių "
                "rezultatuose matomo SUTARTIES SAVININKO vardo neminėk."
            )
        else:
            facts.append(
                "- KREIPINYS: vardo nežinome — nesikreipk vardu; įrankių "
                "rezultatuose matomo savininko vardo neminėk."
            )
    if not past_action and not caller_pending:
        for domain, d in s.diagnosis.items():
            gloss = _DIAGNOSIS_LT.get(d.get("reason"), d.get("reason") or "—")
            facts.append(
                f"- DIAGNOSTIKA [{domain}] ({d.get('group')}, pusė={d.get('side')}): {gloss}."
            )
    # What we believe and why — so the agent reasons out loud instead of issuing
    # orders, and can CONFIRM the cause at the end ("taigi dėl X ir nebuvo").
    h = None if caller_pending else s.hypothesis
    if h:
        because = "; ".join(h["because"])
        if h["status"] == "confirmed":
            facts.append(
                f"- HIPOTEZĖ PASITVIRTINO: „{_DIAGNOSIS_LT.get(h['cause'], h['cause'])}“ "
                f"({h['settled_by']}). Trumpai pasakyk klientui, kad būtent dėl to ir "
                "neveikė — jam svarbu suprasti, kas buvo."
            )
        elif h["status"] == "testing":
            facts.append(
                f"- KO DABAR IEŠKAU: „{_DIAGNOSIS_LT.get(h['cause'], h['cause'])}“. "
                f"Kuo remiuosi: {because}. Kai tinka, pasakyk tai savais žodžiais "
                "(„matau X, todėl manau, kad Y“) — bet trumpai ir ne kas ėjimą."
            )
    if s.rejected_hypotheses and not s.case_closed:
        ruled = ", ".join(_DIAGNOSIS_LT.get(x["cause"], x["cause"]) for x in s.rejected_hypotheses)
        facts.append(f"- JAU ATMESTA (nebesiūlyk ir nebetikrink): {ruled}.")
    # The turn did not move the conversation on. Say WHY, so the agent responds to
    # what the caller actually did instead of re-asking the same sentence.
    if s.awaiting and not s.case_closed:
        from .resolution import INTENT_CONFUSED, INTENT_IN_PROGRESS, INTENT_QUESTION

        if s.last_intent == INTENT_IN_PROGRESS:
            facts.append(
                "- KLIENTAS DAR DARO: jis sakė, kad tuoj/eina/atsineš — dar NEatliko. "
                "Trumpai patvirtink, kad palauksi („Gerai, palauksiu — pasakykite, "
                "kai būsite pasiruošęs“) ir LAUK. NEkartok instrukcijos, NEtark, kad "
                "nepavyko, ir NEeik toliau."
            )
        elif s.last_intent == INTENT_QUESTION:
            facts.append(
                "- KLIENTAS PAKLAUSĖ: pirma ATSAKYK į jo klausimą paprastai, tada "
                "švelniai grįžk prie to, ko prašei. Nekartok savo klausimo neatsakęs."
            )
        elif s.last_intent == INTENT_CONFUSED:
            if s.step_confusions >= 2:
                facts.append(
                    "- VIS DAR NESUPRANTA (jau 2+ kartus): nustok aiškinti tą patį. "
                    "Paimk MAŽIAUSIĄ įmanomą dalį — vieną fizinį veiksmą, kurį "
                    "galima padaryti per sekundę („Ar matote dėžutę su lemputėmis? "
                    "Tiesiog pasakykite taip ar ne“) — ir eik po vieną tokį. Jei ir "
                    "tai nepavyksta, pasiūlyk užregistruoti, kad atvyktų technikas."
                )
            else:
                facts.append(
                    "- KLIENTAS NESUPRATO: NEkartok tų pačių žodžių. Suskaidyk šį "
                    "žingsnį į MAŽESNĮ — pirma nuvesk, KUR pažiūrėti ir kaip tai "
                    "atrodo, ir paprašyk tik to vieno dalyko."
                )
        if s.awaiting_turns >= 3:
            facts.append(
                "- ILGAI LAUKIAM: praėjo keli ėjimai be pastūmėjimo. Pasitikslink "
                "žmogiškai, kaip sekasi ir kur jis dabar („Ar pavyksta rasti? Gal "
                "pasakykite, ką matote“), arba pasiūlyk registruoti gedimą."
            )
    # The caller told us they do not follow the jargon — repeating the same words
    # louder does not help. Give the model plain, visual equivalents to use.
    if s.clarity_level == "basic" and not s.case_closed:
        facts.append(
            "- PAPRASTAI: klientas sakė, kad nesupranta techninių žodžių. Kalbėk "
            "VAIZDŽIAI, be žargono, po VIENĄ veiksmą. Vietoj terminų sakyk: "
            "routeris = „dėžutė su lemputėmis“; WAN/interneto lizdas = „lizdas, į "
            "kurį įkištas kabelis, ateinantis iš sienos, dažnai atskiras ir "
            "pažymėtas Internet“; LAN = „kiti lizdai šalia, į kuriuos jungiami "
            "namų įrenginiai“; MAC = „įrenginio numeris mūsų sistemoje“. Nurodyk, "
            "KUR pažiūrėti („routerio galinėje pusėje“), o ne tik KĄ."
        )
    # Just rejected a hypothesis and switched: let the caller HEAR the rethink, so
    # a failed first attempt reads as an engineer working the problem (we have a
    # Plan B) rather than a script that silently restarts.
    if s.pivoted_from and not s.case_closed:
        old = _DIAGNOSIS_LT.get(s.pivoted_from, s.pivoted_from)
        facts.append(
            f"- PERSIGALVOJIMAS: bandėme priežastį „{old}“ ir tai NEPADĖJO "
            "(telemetrija). Pradėk atsakymą tuo, žmogiškai ir trumpai: kad tai "
            "nepadėjo, vadinasi priežastis kita, ir ką dabar tikrini. Tada tęsk "
            "pagal ŠĮ ŽINGSNĮ. NEapsimesk, kad ankstesnio bandymo nebuvo, ir "
            "NEkartok jo."
        )
    # INFORM (no strategy — billing/outage): the news went out in the activation
    # reply (arc v3). The JAU PRANEŠTA marker stops the model re-reading the same
    # news every turn (observed live: "sustabdyta dėl skolos" said 3×).
    if s.resolution is None and s.diagnosis and not s.case_closed:
        if getattr(engine, "_news_told", False):
            facts.append(
                "- ŽINIA JAU PASAKYTA: nebekartok „patikrinau / sustabdyta / "
                "avarija“ teksto. Atsakyk į kliento klausimą, arba paklausk „Ar dar "
                "kuo galiu padėti?“ ir užbaik pokalbį."
            )
    # Active resolution strategy: inject ONLY the current step's playbook
    # section (never the whole doc — a streaming model would run several steps
    # ahead). This is the "what to do NOW" for the step the engine is on.
    if s.resolution and not s.case_closed:
        from .playbook import get_step
        from .resolution import get_strategy

        strat = get_strategy(s.resolution.get("verdict"))
        step = strat.step(s.resolution.get("step", "")) if strat else None
        # Directive isolation (live 2026-08-21): with B2 the walker pointer
        # loads the step's hint + RAG section even while the ledger has moved
        # on to the recap / findings — and the hint ("check the power lead,
        # try another socket") won over the directive twice. A directive
        # turn carries ONE instruction: no step hint, no playbook section.
        directive_active = bool(
            getattr(engine, "_evidence_directive", None)
            or getattr(engine, "_recap_directive", None)
            or getattr(engine, "_findings_directive", None)
            or getattr(engine, "_ticket_directive", None)
            or getattr(engine, "_ident_directive", None)
        )
        # Step facts wait while the caller-intro question is owed (see above).
        if step is not None and not caller_pending and not directive_active:
            if step.rag_section is not None:
                section = get_step(strat.rag_doc, step.rag_section)
                if section:
                    # Observability: WHICH knowledge chunk feeds THIS step (the
                    # trace otherwise never shows the RAG injection — only
                    # DEBUG_LLM did, with far too much noise).
                    engine._emit_rag_injection(strat.rag_doc, step.rag_section, step.id, section)
                    facts.append(
                        "- PLAYBOOK — your INTERNAL guidance for THIS step (Lithuanian "
                        "content). Act on it, do NOT read it to the caller verbatim, "
                        "ask ONE thing at a time. Say ONLY what THIS step is about — "
                        "do NOT invent instructions it does not mention (no rebooting, "
                        "no lights, no cables unless this step says so). If the caller's "
                        "answer was unclear, ask THIS SAME thing again in other words:\n" + section
                    )
            if step.hint:
                facts.append(f"- THIS STEP: {step.hint}")
    # Before ANY problem is stated, identification must not run ahead: no
    # address offers, no checks — first learn WHY they call (live: the LLM
    # offered the address on a greeting; the ladder then re-offered it).
    if not s.customer_id and not s.problem_type and not s.preflight_outage:
        facts.append(
            "- PROBLEMA DAR NEPASAKYTA: NESIŪLYK adreso ir nieko netikrinsi — "
            "pirmiausia paklausk, kokia problema / kuo gali padėti."
        )
    # Deterministically heard address parts (NLU Track A prefill). Surface them
    # so the model passes THESE to resolve_address instead of re-extracting
    # garbled STT (observed: NLU heard "Aušros g. 8" but the model sent
    # "Raušuos"). Only relevant before the customer is identified.
    if not s.customer_id:
        p = s.profile
        heard = [
            f"{label}={slot.value}"
            for label, slot in (
                ("city", p.city),
                ("street", p.street),
                ("house", p.house),
                ("apartment", p.apartment),
            )
            if slot.value
        ]
        if heard:
            facts.append(
                "- HEARD ADDRESS (deterministic — PREFER these over re-extracting "
                "from the raw text): " + ", ".join(heard) + ". Pass them to "
                "resolve_address unless the caller explicitly corrects them."
            )
    # Phone candidate is NOT surfaced to the model. Identification is
    # address-first: the agent always asks for the service address and
    # resolve_address is what commits the customer_id. The preflight
    # phone_candidate stays in AgentState for SILENT use only — a
    # deterministic cross-check (does the stated address match the caller's
    # account?) and the mass-outage fast-path — never as an address to
    # offer. Surfacing it caused the model to (a) re-ask the same
    # confirmation without ever committing the id, and (b) present a
    # user-stated address as "skambinate iš numerio, registruoto adresu ..."
    # even for callers with no account on file.

    # Evidence ledger — the narrator's grounding: settled facts are never
    # re-asked, and nothing outside the ledger may be claimed as checked.
    if s.evidence and s.customer_id and not s.case_closed:
        from .evidence import summary_lt

        facts.append(
            "- ĮRODYMŲ ŽURNALAS (nustatyta šį pokalbį — NEBEKLAUSK ir "
            f"neprieštarauk): {summary_lt(s.evidence)}"
        )

    # Situational awareness (Andrius 2026-08-13: "jei žinome, KĄ reikia
    # išsiaiškinti, nesvarbu kokiais klausimais — svarbu tai gauti"): the
    # still-open goals, so the narrator adapts to the conversation and pulls
    # a wandering caller back to what is missing instead of drifting.
    if s.customer_id and not s.case_closed and (s.resolution or {}).get("verdict"):
        from .evidence import open_goals_lt

        goals = open_goals_lt(s.evidence, s.resolution.get("verdict"))
        if goals:
            facts.append(
                f"- DAR AIŠKINAMĖS (pokalbio tikslas — tai nustatyti): {goals}. "
                "Jei klientas nuklydo nuo temos — atsakyk trumpai, primink, kur "
                "esame, ir grąžink pokalbį prie to, kas dar neišsiaiškinta. "
                "Kai tikslų liko 1–2, PASAKYK klientui pažangą savais žodžiais "
                "(pvz. „beliko patikrinti rozetę — ir bus aišku“)."
            )

    # Bridge-phase anchor for the NARRATOR too (live 2026-08-13: it slid back
    # to router questions after the cable was already replugged — the anchor
    # existed only in the solver's context).
    if getattr(engine, "_bridge_plug_reported", False):
        facts.append(
            "- TILTO FAZĖ: routeris jau pripažintas sugedusiu, kabelis PERKIŠTAS į "
            "kompiuterį — apie routerį, jo lemputes ar maitinimą NEBEKLAUSK ir "
            "nebegrįžk. Kalbame tik apie kompiuterio prijungimą."
        )

    # Zone 2 (skriptai -> direktyvos): the transition to the ADDRESS — a smooth
    # hand-over from the problem talk instead of a canned line. The OFFER's
    # question core stays verbatim (the confirm guard keys off it).
    # Turn'o gramatika (etalonas 2026-09-03): the JUST-landed answer's declared
    # MEANING — the reaction carries it instead of parroting the fact
    # („Vadinasi, maitinimą gauna, bet tinklo nemato."). One-shot.
    fm = getattr(engine, "_fact_meaning", None)
    if fm:
        engine._fact_meaning = None
        tema, reiksme, prasme = fm
        facts.append(
            f"- KĄ TIK PAAIŠKĖJO: {tema} — „{reiksme}“. TAI REIŠKIA: {prasme}. "
            "Reakcijoje vienu sakiniu pasakyk ŠIĄ REIKŠMĘ (ne patį faktą), "
            "tada kitas žingsnis."
        )
    # Frazynas: the caller JUST introduced themselves — accept warmly, once.
    if getattr(engine, "_name_heard", False):
        engine._name_heard = False
        if s.caller_name and s.caller_name != "nenurodyta":
            facts.append(
                f"- KLIENTAS PRISISTATĖ: pradėk šiltu priėmimu — „Malonu, "
                f"{s.caller_name}!“ (arba panašiai) — ir tęsk mintį."
            )
    idd = getattr(engine, "_ident_directive", None)
    if idd:
        # W1-1 (Andrius 2026-08-25): the opening already said WHEN it broke —
        # the caller must HEAR they were heard, one short acknowledgement
        # before the address ask, never a repeated "kada dingo?".
        if getattr(engine, "_opening_heard_note", False):
            engine._opening_heard_note = False
            when = s.anamnesis_when or s.anamnesis_trigger or ""
            facts.append(
                "- KLIENTAS JAU PASAKĖ, kada dingo"
                + (f" („{when}“)" if when else "")
                + " — pora žodžių parodyk, kad išgirdai (pvz. „Aišku — nuo "
                "vakar.“), ir NEKLAUSK, kada dingo."
            )
        if idd["kind"] == "address_offer":
            # Perėjimas BE ŠUOLIO (Andrius 2026-09-03, gyvas skambutis: po
            # problemos iškart nuskambėjo plika šerdis be išgirdimo): pirma
            # trumpa reakcija į tai, ką klientas KĄ TIK pasakė, tada jungtis
            # į adresą. Šerdis lieka žodis į žodį — sargas nuo jos priklauso.
            prob = _PROBLEM_LT.get(s.problem_type or "", "")
            girdejimas = f" („Suprantu — {prob}.“)" if prob else ""
            facts.append(
                "- IDENTIFIKACIJOS ŽINGSNIS: pirmu TRUMPU sakiniu parodyk, kad "
                f"išgirdai, ką klientas pasakė{girdejimas}, tada jungtis — "
                "patikrai reikia adreso — ir klausimo šerdis ŽODIS Į ŽODĮ: "
                f"„Ar skambinate dėl {idd['adresas']}?“ Adreso nekeisk. "
                "Visos replikos pavyzdys: „Suprantu — dingo internetas. "
                f"Patikrinsiu liniją — ar skambinate dėl {idd['adresas']}?“"
            )
        elif idd["kind"] == "anamnesis":
            facts.append(
                "- ANAMNEZĖS ŽINGSNIS: išsiaiškink, KADA dingo internetas ir ar prieš "
                "tai buvo koks įvykis (audra, remontas, kažką keitė) — neklausk to, "
                f"kas jau aišku. (Atsarginė: „{idd['fallback']}“)"
            )
        elif idd["kind"] == "problem_gate":
            facts.append(
                "- PROBLEMOS VARTAI: klientas dar nepasakė aiškios MŪSŲ srities "
                "problemos. TAVO KOMPETENCIJA: sprendi TIK interneto ir televizijos "
                "techninius gedimus — sąskaitų, sutarčių ar kitų klausimų NESPRENDI "
                "ir tai pasakai atvirai. Išsiaiškink, ar klientas turi interneto ar "
                "TV bėdą. Jei tema ne tavo (sąskaita, „vaikai neklauso“) — mandagiai "
                "įvardink ribą ir paklausk, ar yra ryšio ar TV problema. Jei klientas "
                "KLAUSIA — atsakyk vienu sakiniu ir vėl paklausk problemos. NEKLAUSK "
                f"adreso ir nieko netikrink. (Atsarginė: „{idd['fallback']}“)"
            )
        elif idd["kind"] == "anamnesis_followup":
            facts.append(
                "- ANAMNEZĖS ŽINGSNIS: klientas nežino, kada dingo — paklausk, kada "
                f"paskutinį kartą internetas TIKRAI veikė. (Atsarginė: „{idd['fallback']}“)"
            )
        else:
            facts.append(
                "- IDENTIFIKACIJOS ŽINGSNIS: paaiškink, kad patikrai iki buto reikia "
                f"adreso, ir paklausk TIK adreso. (Atsarginė: „{idd['fallback']}“)"
            )

    # Zone 1 (skriptai -> direktyvos): the ticket dialogue's question moments,
    # worded by the narrator into the conversation's flow — the engine still
    # owns the stages and the capture; only the WORDING is free.
    td = getattr(engine, "_ticket_directive", None)
    if td:
        from .ticket_flow import ticket_need

        if td["kind"] == "phone_intro":
            if getattr(engine, "_bridge_bound", False):
                goal = (
                    "pranešk gerą žinią — internetas kol kas veikia per kompiuterį — "
                    "ir kad registruoji meistrą dėl naujo routerio; paklausk TIK "
                    "vieno: ar susisiekimui tinka numeris, iš kurio klientas skambina"
                )
            else:
                goal = (
                    f"pranešk, kad telefonu šito neišspręsim ({ticket_need(engine)}) "
                    "ir kad registruoji meistrą; paklausk TIK vieno: ar susisiekimui "
                    "tinka numeris, iš kurio klientas skambina"
                )
        elif td["kind"] == "hours":
            # P2 (live 2026-08-26): the LLM echoed the just-captured number
            # back with the "is kurio skambinate" template — the number is
            # DONE, this turn is hours only.
            goal = (
                "paklausk TIK vieno: kada klientui patogiausia sulaukti "
                "skambučio. Numeris JAU užfiksuotas — jo nebeminėk ir nebeklausk"
            )
        else:
            goal = "paklausk TIK vieno: ar susisiekimui tinka numeris, iš kurio klientas skambina"
        facts.append(
            f"- TIKETO ŽINGSNIS: {goal}. Registracija dar NEĮVYKO — sakyk "
            f"„užregistruosiu“, niekada „užregistravau“. (Atsarginė: „{td['fallback']}“)"
        )

    # Persona: the RECAP as a goal directive — read the gathered facts back in
    # the narrator's own words, one short sentence, never the label:value dump.
    rd = getattr(engine, "_recap_directive", None)
    if rd:
        facts.append(f"- PASITIKSLINK: ar teisingai supratai — {rd['faktai']}.")

    # Persona: the FINDINGS moment as a goal directive — the narrator states
    # what was established, the conclusion and the choice BRIEFLY in its own
    # words (never the 'label: value; label: value' template dump).
    fd = getattr(engine, "_findings_directive", None)
    if fd:
        # Ticket-first faults script their own offer (`pasiulymas` in the
        # pack): the primary outcome first, the convenience as the question.
        if fd.get("pasiulymas"):
            spr = f" {fd['pasiulymas']}"
        elif fd.get("sprendimai"):
            spr = f" Pasiūlyk pasirinkimą ({fd['sprendimai']}) ir paklausk, kaip darome."
        else:
            spr = ""
        # W0-E (live 2026-08-25): the findings turn said "Užregistravau" while
        # create_ticket was still turns away — the tense rule rides here too.
        tense = (
            ""
            if s.ticket_id
            else " Registracija dar NEĮVYKO — jei ją mini, sakyk „užregistruosiu“, "
            "niekada „užregistravau“."
        )
        facts.append(
            f"- IŠVADOS MOMENTAS:{tense} kartu nustatėme — {fd['faktai']}. "
            f"Išvada: {fd['isvada']}.{spr}"
        )

    # Step awareness (L2, VOICE_PLAN 1 žingsnis): the narrator knows the
    # CURRENT step's goal — the reaction becomes evaluative ("Gerai — radote"
    # / "Ne, ne šis kabelis"), not a bare "supratau"; and a REPEATED step is
    # repeated with an explanation, never as if asked the first time.
    _r = s.resolution or {}
    if _r.get("verdict") and not s.case_closed:
        from .resolution import get_strategy as _get_strategy

        _strat = _get_strategy(_r.get("verdict"))
        _step = _strat.step(_r.get("step", "")) if _strat else None
        if _step is not None and getattr(_step, "tikslas", ""):
            facts.append(
                f"- ŠIO ŽINGSNIO TIKSLAS: {_step.tikslas}. Reaguodamas į kliento "
                "atsakymą ĮVERTINK, ar tikslas pasiektas — trumpa vertinanti "
                "reakcija („Gerai — radote“ / „Ne, ne šis kabelis“), tada tęsk."
            )
        if _step is not None and (_r.get("presented") or {}).get(_step.id, 0) >= 2:
            facts.append(
                "- ŽINGSNIS KARTOJAMAS: šio žingsnio klausimą jau uždavei — "
                "trumpai paaiškink, KODĖL klausi dar kartą („dar kartą, nes "
                "noriu būti tikras…“), tada klausk."
            )

    # Persona (R5c, Andrius 2026-08-13): the evidence question as a GOAL
    # directive — the narrator words it naturally in the conversation's flow
    # instead of reading the pack's scripted sentence. Hard limits keep it
    # safe: ONE question, this goal only, no invented facts.
    directive = getattr(engine, "_evidence_directive", None)
    if directive:
        kodel = f" Kodėl tikriname: {directive['kodel']}." if directive.get("kodel") else ""
        # The OTHER still-open goals are named as off-limits (eval 2026-08-21:
        # asked "which device" and "laidu ar Wi-Fi" in one breath — the
        # connection type is a later fact with its own turn).
        kiti = ""
        if (s.resolution or {}).get("verdict"):
            from .evidence import open_goals_lt as _ogl

            rest = [
                g.strip()
                for g in _ogl(s.evidence, s.resolution.get("verdict")).split(";")
                if g.strip() and g.strip() != str(directive["reikia"]).strip()
            ]
            if rest:
                kiti = (
                    " KITŲ DALYKŲ DAR NEKLAUSK IR NEMINĖK (jiems bus savas turn'as): "
                    + "; ".join(rest)
                    + "."
                )
        # Facts diet (hygiene step 2, 2026-08-27): the shared scaffold lives
        # ONCE in partials/directives.md (cached prefix) — the line carries
        # only the DATA of this turn's goal.
        facts.append(
            f"- KLAUSK DABAR: išsiaiškink — {directive['reikia']}. Fakto DAR "
            f"NEŽINAI — užduok klausimą, nekonstatuok.{kodel}{kiti} "
            f"(Atsarginė: „{directive['klausimas']}“)"
        )

    # Istorija v2: the caller referenced their OWN earlier words — pull the
    # matching old lines (outside the window) back in for this turn.
    recall = recall_lines(engine)
    if recall:
        facts.append(recall)

    # W2 tylusis analitikas: advisory notes from the background read — they
    # shape the WORDING only; on any clash the directives above win. One-shot.
    notes = getattr(engine, "_analyst_notes", None)
    if notes:
        engine._analyst_notes = None
        facts.append(
            "- TYLIOJO ANALITIKO PASTABOS (patariamosios — faktų ir eigos "
            "NEkeičia; jei prieštarauja aukščiau esančioms direktyvoms, "
            "ignoruok): " + " | ".join(str(n) for n in notes[:2])
        )

    if not facts:
        return None

    return "KNOWN FACTS (already resolved this call — do not ask again):\n" + "\n".join(facts)


def emit_rag_injection(engine, doc: str | None, section: int, step_id: str, text: str) -> None:
    """Emit a `rag` trace event when a playbook section is injected for a step —
    deduped on (doc, section, step) so the multi-call turn (LLM + tool follow-up)
    logs it once, and a step change logs the new section."""
    key = (doc, section, step_id)
    if getattr(engine, "_last_rag_key", None) == key:
        return
    engine._last_rag_key = key
    preview = " ".join((text or "").split())[:90]
    engine.tracer.emit("rag", doc=doc, section=section, step=step_id, preview=preview)


def mark_step_presented(engine) -> None:
    """After the agent replies while on a strategy step, record that the step's
    message (a CONFIRM question, an INSTRUCT instruction, or the ACTION announce)
    has now been presented — so the caller's NEXT reply advances the walker."""
    engine.state.pivoted_from = None  # the rethink has now been said — say it once
    s = engine.state
    # Identification ladder bookkeeping: while the caller-intro question is owed,
    # the strategy step's question was NOT asked this reply — do not mark it. Once
    # the caller introduced themselves and the RESULT was narrated, the deferral
    # closes (inform news counted as told).
    if s.customer_id and engine._result_pending:
        if not s.caller_name:
            return  # the reply asked WHO is calling — nothing else was presented
        engine._result_pending = False
        if s.resolution is None:
            engine._news_told = True
    r = engine.state.resolution
    if not r:
        return
    from .resolution import StepKind, get_strategy

    strat = get_strategy(r.get("verdict"))
    step = strat.step(r.get("step", "")) if strat else None
    if step is not None and step.kind in (
        StepKind.CONFIRM,
        StepKind.INSTRUCT,
        StepKind.ACTION,
        StepKind.ESCALATE,  # the consent question ("ar tinka?") — Phase 3.11 B
    ):
        r["asked"] = True
        # Freshness stamp (2026-08-11): while the solver/evidence drive owns
        # the turns, the walker step's question ages — three live calls were
        # killed by a many-turns-stale dr_intro reading a reply as its own
        # answer. The asked-step routing only trusts a RECENT question.
        r["asked_at"] = len(engine.state.messages)
        # Presentation counter (L2): a step presented the 2nd+ time gets the
        # ŽINGSNIS KARTOJAMAS directive — repeat WITH an explanation.
        counts = r.setdefault("presented", {})
        counts[step.id] = counts.get(step.id, 0) + 1


def augment_resolve_result(engine, observation: str) -> str:
    """Identification just landed — diagnose in the SAME turn.

    Otherwise the identification turn has nothing real left to say (the address is
    already confirmed) and the model fills the gap: it invents "nėra žinomų
    gedimų", asks "kokie įrenginiai prijungti?", and a debtor only hears about the
    debt a turn later — or the caller goes quiet and the call stalls before any
    diagnosis. Running it here lets ONE reply confirm the address and deliver the
    finding."""
    try:
        obs = json.loads(observation)
    except (TypeError, ValueError):
        return observation
    if not obs.get("success") or not engine.state.customer_id:
        return observation
    if not engine.ensure_diagnosed():
        return observation
    # The address was JUST confirmed (that is what triggered this diagnose) — the
    # lookup hint still says "patvirtink adresą klientui", and the narrator obeying
    # it re-asked the ADDRESS instead of moving on. Neutralize the stale hint.
    obs["hint"] = "Adresas JAU patvirtintas — nebeklausk adreso."
    # Arc v3 (2026-07-31, Andrius' variant 1): identification is SEPARATE from
    # diagnosis — the engine has already diagnosed silently (state-only), and this
    # ONE reply narrates the check announce AND its real result in sequence:
    # "Patikrinsiu būseną šiuo adresu… Patikrinau: [rezultatas]." No caller-ack
    # turn (a told-to-wait caller stays silent -> dead air), and no deferred-finding
    # vacuum for the model to hallucinate into (observed: it invented a router
    # story for a debtor). When async telemetry lands (Phase 5), the announce and
    # the result naturally split into two real turns.
    obs["message"] = (obs.get("message", "") or "").strip() + engine._result_narration_tail()
    return json.dumps(obs, ensure_ascii=False)


def result_narration_tail(engine) -> str:
    """The narration directive once the identity has committed and the silent
    diagnose ran. Identification LADDER (2026-07-31): if the caller-intro question
    is still owed (WHO is calling — name + relation, for the record), ask THAT
    first and hold the result one turn (_result_pending); otherwise narrate the
    check announce + the REAL result in this one reply (arc v3)."""
    from .identification import ask_caller, caller_question

    if ask_caller() and not engine.state.caller_name:
        engine._result_pending = True
        return (
            " Identifikacijos pabaiga: patikra atlikta TYLIAI, bet rezultato dar "
            f"NESAKYK. Šiame atsakyme TIK: „{caller_question()}“ (galima trumpai "
            "patvirtinti adresą prieš klausimą). Jokio rezultato, jokių instrukcijų."
        )
    d = engine.state.diagnosis.get("network") or {}
    gloss = _DIAGNOSIS_LT.get(d.get("reason"), d.get("reason") or "—")
    if engine.state.resolution:
        return (
            f" Patikra atlikta. REZULTATAS: {gloss}. Šiame VIENAME atsakyme, šia "
            "tvarka: (1) 'Patikrinsiu būseną šiuo adresu… Patikrinau:' (2) trumpai "
            "pasakyk rezultatą ir kas tai greičiausiai yra, (3) užduok ŠIO ŽINGSNIO "
            "klausimą (jis atlieka „ar darome?“ vaidmenį). NEkartok adreso klausimo, "
            "NEkartok anamnezės klausimo, jokių instrukcijų sąrašo — vienas klausimas."
        )
    engine._news_told = True  # the news goes out in THIS reply — never repeat it
    return (
        f" Patikra atlikta. ŽINIA: {gloss}. Šiame VIENAME atsakyme, šia tvarka: "
        "(1) 'Patikrinsiu būseną šiuo adresu… Patikrinau:' (2) pasakyk žinią "
        "VIENĄ kartą trumpai (jei skola — BŪTINAI pridėk: „apmokėjus sąskaitą, "
        "paslauga bus įjungta“), (3) paklausk „Ar dar kuo galiu padėti?“. "
        "NEkartok adreso klausimo ir daugiau šios žinios NEBEKARTOK."
    )


def augment_tool_result(engine, name: str, observation: str) -> str:
    """Deterministic post-action chaining + telemetry verification (B6 strategy).

    update_mac ALONE does not restore service — the port must be reset and the
    line re-checked. Rather than trust the model to remember the whole sequence
    (observed: it bound nothing and closed on the caller's word), the engine
    chains it: after a successful update_mac it runs reset_port and re-reads the
    telemetry, and hands the model a VERIFIED outcome to narrate (what the
    provider side actually shows, not what the caller claims)."""
    if name == "resolve_address":
        return engine._augment_resolve_result(observation)
    if name != "update_mac":
        return observation
    try:
        obs = json.loads(observation)
    except (TypeError, ValueError):
        return observation
    if not obs.get("success"):
        return observation  # nothing bound (e.g. no_observed_mac) — leave as is
    cid = engine.state.customer_id
    try:
        rp = json.loads(execute_tool("reset_port", {"customer_id": cid}))
        engine.tracer.emit("tool_call", name="reset_port", args={"customer_id": cid})
        obs["auto_reset_port"] = bool(rp.get("success"))
    except Exception:  # pragma: no cover - best-effort
        obs["auto_reset_port"] = None
    reason_now = engine._fresh_diagnose_reason()
    fixed = reason_now not in engine._UNRESOLVED_LINE_FAULTS
    obs["telemetry_after"] = reason_now
    obs["fixed"] = fixed
    gloss = _DIAGNOSIS_LT.get(reason_now, reason_now or "—")

    # Do NOT close or advance here. The bind was announced THIS turn; the walker
    # advances bind_mac -> confirm_restored on the caller's next reply, where we
    # ASK them and re-read telemetry before deciding resolve / client-side /
    # escalate (_advance_restored). Just record the telemetry reading.
    r = engine.state.resolution
    if r is not None:
        r["telemetry_fixed"] = fixed
    obs["message"] = (
        obs.get("message", "") or ""
    ).strip() + f" Portas perkrautas. Telemetrija dabar: {gloss}."
    return json.dumps(obs, ensure_ascii=False)


def update_state_from_observation(engine, action: str, observation: str):
    """Update agent state based on tool observation."""
    try:
        obs_data = json.loads(observation)

        # Fold the per-level address resolution into the durable slots on
        # EVERY resolve_address call (success or not) — what the caller said
        # accumulates as structured memory, protected from low-confidence
        # overwrites (slots.Slot.propose).
        if action == "resolve_address" and isinstance(obs_data.get("resolution"), dict):
            engine.state.profile.update_from_resolution(obs_data["resolution"])
            # F2 (2026-08-20): a failed lookup speaks its DIAGNOSIS — what was
            # found and what was not — so the caller can correct themselves
            # ("Vilniaus gatvę randu, bet 39 numerio nematau").
            if not obs_data.get("success"):
                from .identification_flow import address_diag_note

                engine._addr_diag_note = address_diag_note(obs_data)
            else:
                engine._addr_diag_note = None

        if action in ("find_customer", "resolve_address") and obs_data.get("success"):
            # resolve_address nests the normalized profile under `customer`;
            # find_customer returns it flat. Same shape either way.
            profile = obs_data.get("customer") or obs_data
            addresses = profile.get("addresses") or []
            # Normalized addresses carry `full_address` (primary first
            # when available).
            primary = next(
                (a for a in addresses if a.get("is_primary")),
                addresses[0] if addresses else {},
            )
            if profile.get("customer_id"):
                engine.state.set_customer_info(
                    customer_id=profile.get("customer_id"),
                    name=profile.get("name"),
                    address=primary.get("full_address"),
                )

        elif action == "create_ticket" and obs_data.get("success"):
            engine.state.ticket_id = obs_data.get("ticket_id")
            # Inside a resolution strategy (escalate step), the fault is now
            # registered — close the case so create_ticket is withdrawn and the
            # model narrates the close instead of re-registering in a loop.
            if engine.state.resolution and not engine.state.case_closed:
                engine.state.case_closed = True
                engine.state.closed_reason = "registered"

        # Diagnostic findings -> case state under their DOMAIN, so the agent
        # reconciles them with the customer and never loses / re-runs them, and
        # new fault families attach additively (§12.1).
        if action == "diagnose_connection" and isinstance(obs_data.get("verdict"), dict):
            v = obs_data["verdict"]
            engine.state.diagnosis["network"] = {
                "group": v.get("group"),
                "side": v.get("side"),
                "action": v.get("action"),
                "reason": v.get("reason"),
                "signals": v.get("signals"),
            }
            # Ledger: telemetry facts are ground truth — every (re)diagnose
            # lands on the evidence with full history (a re-check after a fix
            # OVERWRITES the value; the caller's words never do).
            from .evidence import TELEMETRY, set_fact

            turn = engine.state.turn_count
            if v.get("reason"):
                set_fact(engine.state.evidence, "verdict", v["reason"], TELEMETRY, turn)
            if v.get("side"):
                set_fact(engine.state.evidence, "side", v["side"], TELEMETRY, turn)
            # A verdict IS a hypothesis — record what we now believe and why, so
            # the agent can say it aloud and later report how it settled.
            engine._open_hypothesis(v.get("reason"))
            # Activate / re-evaluate the resolution strategy for this verdict
            # (dynamic pivot: a re-diagnose with a different verdict switches
            # strategy). None = generic inform/instruct flow.
            from .resolution import get_strategy

            strat = get_strategy(v.get("reason"))
            # Never pivot back into a hypothesis the telemetry already disproved —
            # that is how a re-diagnose after a failed fix would loop forever.
            if strat is not None and strat.verdict not in engine.state.failed_hypotheses:
                prev = (engine.state.resolution or {}).get("verdict")
                if prev != strat.verdict:  # new or pivoted
                    engine.state.resolution = {
                        "verdict": strat.verdict,
                        "step": strat.steps[0].id,
                    }

        # An active outage for the caller's street -> restricted mode (NOT a
        # close): the caller still asks "when fixed? / compensation?", so the
        # agent stays in a tool-having node but stops diagnosing (facts block).
        # By the gate, a returned `affected` here is already street-specific.
        if action == "check_outages" and obs_data.get("affected"):
            engine.state.outage_reported = True

        # close_case signal -> flip the router to the closing stage. The model
        # owns WHEN (it read the caller's confirmation); the gate already
        # backstopped premature/unfounded closes.
        if action == "close_case" and obs_data.get("case_closed"):
            engine.state.case_closed = True
            engine.state.closed_reason = obs_data.get("reason")

    except json.JSONDecodeError:
        pass

"""
Evidence-declared drive (Ledger v2) — question selection, hypothesis routing
and the one-shot checkpoints around it.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of
ReactAgent. Pure ledger mechanics (set_fact, hypothesis_status, next_missing,
solution_for) stay in agent/evidence.py; this module is the CONVERSATIONAL
drive over them: what to ask next, when to recap, when to double-check a
refuting fact, when to give up on a key. Functions take the engine explicitly.
"""

from __future__ import annotations

import os
from typing import Any


def revive_gave_up_key(engine: Any, spec: dict) -> str | None:
    """ONE second chance for a given-up key that BLOCKS confirmation
    (Andrius 2026-08-12): 'neaišku' on a patvirtinta-required key froze the
    hypothesis forever. At the dead-end moment the agent asks it once more,
    plainly and with the reason; the answer lands through the pending
    machinery (the give-up marker is replaceable by design). Never loops —
    one revival per key per call."""
    from .evidence import LABELS
    from .identification import phrase

    ev = engine.state.evidence
    for cond in spec.get("patvirtinta_kai") or []:
        if "=" not in cond:
            continue
        key = cond.split("=", 1)[0].strip()
        entry = ev.get(key)
        if entry is None or entry.get("value") != "neaišku":
            continue
        if key in getattr(engine, "_revived_keys", set()):
            continue
        engine._revived_keys = getattr(engine, "_revived_keys", set()) | {key}
        item = (spec.get("client") or {}).get(key) or {}
        engine._evidence_last_ask_key = key
        engine.tracer.emit("evidence", action="revive_ask", key=key)
        return phrase(
            "reask_reason",
            tema=LABELS.get(key, key),
            klausimas=str(item.get("patikslinimas") or item.get("klausimas") or ""),
        )
    return None


def maybe_facts_recap(engine: Any) -> str | None:
    """Recap-and-confirm CHECKPOINT (Andrius 2026-08-11: 'pasitikslinti, o
    ne kurti'): the first confirmed moment first READS BACK what the caller
    told us — a misheard fact gets corrected here instead of driving a
    wrong solution. Asked once; whatever the answer, the flow moves on next
    turn (corrections land through the normal ingest/conflict machinery)."""
    state = getattr(engine, "_recap_state", "")
    if state == "done":
        return None
    if state == "pending":
        engine._recap_state = "done"
        engine.tracer.emit("decision", intent="facts_recap", action="answered")
        return None
    from .evidence import client_facts_lt
    from .identification import phrase

    faktai = client_facts_lt(engine.state.evidence)
    if not faktai:
        engine._recap_state = "done"
        return None
    # Persona (Andrius 2026-08-20: "Pasitikslinu: routeris surastas: rado; …"
    # is the last remaining label:value dump read to a human) — in narrator
    # mode the recap becomes a goal directive, said in the narrator's words
    # ("Taip, jūs sakote — lemputės nedega net pakeitus rozetę, ar taip?").
    if os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on":
        engine._recap_directive = {"faktai": faktai}
        engine._recap_state = "pending"
        engine.tracer.emit("decision", intent="facts_recap", action="ask_narrator")
        return None  # the narrator speaks the recap
    engine._recap_state = "pending"
    engine.tracer.emit("decision", intent="facts_recap", action="ask")
    return phrase("facts_recap", faktai=faktai)


def refuting_client_fact(engine: Any, spec: dict) -> tuple[str, str] | None:
    """The CLIENT-stated fact that currently refutes the hypothesis — the
    one worth double-checking before pivoting (telemetry needs no confirm)."""
    from .evidence import CLIENT, _cond_holds

    ev = engine.state.evidence
    for cond in spec.get("paneigta_kai") or []:
        if "=" in cond and _cond_holds(ev, cond, False):
            key = cond.split("=", 1)[0].strip()
            entry = ev.get(key)
            if entry is not None and entry.get("source") == CLIENT:
                return key, str(entry.get("value"))
    return None


def maybe_refute_confirm(engine: Any, spec: dict) -> str | None:
    """One confirm question before abandoning the hypothesis on a
    CLIENT-stated fact (Andrius 2026-08-11: guard against premature
    rejection — STT garbles flip facts). 'Taip' -> pivot proceeds; a
    correction lands via ingest and un-refutes on its own."""
    state = getattr(engine, "_refute_state", "")
    if state == "done":
        return None
    if state == "pending":
        engine._refute_state = "done"
        engine.tracer.emit("decision", intent="refute_confirm", action="answered")
        return None
    kv = refuting_client_fact(engine, spec)
    if kv is None:
        engine._refute_state = "done"  # telemetry-backed — trust it
        return None
    key, value = kv
    from .evidence import LABELS, VALUE_LT
    from .identification import phrase

    engine._refute_state = "pending"
    engine.tracer.emit("decision", intent="refute_confirm", action="ask", key=key)
    return phrase(
        "refute_confirm",
        tema=LABELS.get(key, key),
        reiksme=VALUE_LT.get(value, value),
    )


def evidence_question_open(engine: Any) -> str | None:
    """The evidence key whose question is OUT and still unanswered — the one
    question the caller is actually answering right now. The ingest clears
    the pending key the moment a fact lands on it, so a non-None here means
    this turn's reply did NOT read as an answer to it."""
    key = getattr(engine, "_evidence_last_ask_key", None)
    if not key:
        return None
    entry = engine.state.evidence.get(key)
    if entry is not None and entry.get("value") not in (None, "neaišku"):
        return None
    return key


def negation_clarify_reply(engine: Any, key: str) -> str | None:
    """Scripted clarify for a bare-"ne" reply to the open evidence question
    (Andrius 2026-08-11: clarify what the "ne" refers to instead of acting).
    Wording comes from the fault file (`patikslinimas` per key) so every fault
    can name its own two readings; generic phrase as fallback. Counts as an
    ask — the give-up cap still ends an unreadable loop."""
    from .evidence import spec_for
    from .identification import phrase

    if engine._evidence_asks.get(key, 0) >= 2:
        return None  # already asked twice — let the drive give up, not loop
    spec = spec_for((engine.state.resolution or {}).get("verdict")) or {}
    item = (spec.get("client") or {}).get(key) or {}
    engine._evidence_asks[key] = engine._evidence_asks.get(key, 0) + 1
    engine.tracer.emit("evidence", action="negation_clarify", key=key)
    return str(
        item.get("patikslinimas")
        or phrase("negation_clarify", klausimas=str(item.get("klausimas") or ""))
    ).strip()


def evidence_drive(engine: Any, user_input: str | None) -> str | None:
    """Evidence-declared direction (Ledger v2): pick the next question from
    MISSING evidence, compute the hypothesis from the ledger, and route the
    declared solution. Returns the reply text, or None when the spec is
    absent / the solver should take the turn (bridge instructions, refuted
    pivot, nothing left to ask)."""
    from .evidence import (
        CLIENT,
        hypothesis_status,
        next_missing,
        set_fact,
        solution_for,
        spec_for,
    )

    s = engine.state
    r = s.resolution or {}
    spec = spec_for(r.get("verdict"))
    if spec is None:
        return None
    # W1-2 svarbos vartai: a parked story-flipping fact gets its ONE confirm
    # question before anything else — the ledger stays clean until the caller
    # says "taip" (STT garbles poison exactly these facts).
    fc = getattr(engine, "_fact_confirm", None)
    if fc is not None:
        from .evidence import LABELS, VALUE_LT
        from .identification import phrase as _phrase

        engine._fact_confirm = None
        engine._fact_confirm_asked = fc
        engine.tracer.emit("decision", intent="fact_confirm", action="ask", key=fc[0])
        return _phrase(
            "refute_confirm",
            tema=LABELS.get(fc[0], fc[0]),
            reiksme=VALUE_LT.get(fc[1], fc[1]),
        )
    # Captured BEFORE any new ask below overwrites it: was a question already
    # out when the caller spoke? Needed for the bare-"ne" clarify.
    pending_before = evidence_question_open(engine)
    status = hypothesis_status(s.evidence, spec)
    if status == "refuted":
        # One confirm question before the pivot when the refuting fact came
        # from the CALLER's words — STT garbles flip facts (2026-08-11).
        refute_reply = maybe_refute_confirm(engine, spec)
        if refute_reply is not None:
            return refute_reply
        # A lit lamp disproves the dead-router path — sync the walker to the
        # declared pivot step so NOTHING rewinds, then let it continue.
        target = spec.get("paneigta_veda")
        if target and r.get("step") != target:
            engine._goto_step(r, target)
            engine.tracer.emit(
                "decision", intent="evidence", action="pivot", to=target, reason="refuted"
            )
        return None
    confirmed = status == "confirmed"
    # FINDINGS announce (2026-08-10): the FIRST confirmed moment is the
    # transition the caller must HEAR — what we checked together, the
    # conclusion, the options — before any solution question. Composed
    # deterministically from the ledger + the fault's file (isvada,
    # sprendimai aprasymai), so every newly declared fault gets it free.
    announce = ""
    if confirmed and not getattr(engine, "_findings_announced", False):
        # Recap checkpoint FIRST: read the gathered facts back and let the
        # caller confirm or correct before any conclusion is announced.
        recap = maybe_facts_recap(engine)
        if recap is not None:
            return recap
        if getattr(engine, "_recap_directive", None):
            return None  # the narrator asks the recap; findings come next turn
        engine._findings_announced = True
        from .evidence import client_facts_lt, fault_isvada, solution_descriptions
        from .identification import phrase

        faktai_lt = client_facts_lt(s.evidence)
        isvada = fault_isvada(r.get("verdict")) or engine._ticket_need()
        sprendimai = solution_descriptions(r.get("verdict"))
        if faktai_lt and isvada:
            # Persona (Andrius 2026-08-13: the template dump "Ką patikrinome:
            # routeris surastas: rado; …" is words FOR the agent, not speech) —
            # in narrator mode the findings go out as a GOAL directive and the
            # narrator says them briefly in its own words.
            if os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on":
                from .evidence import fault_pasiulymas

                engine._findings_directive = {
                    "faktai": faktai_lt,
                    "isvada": isvada,
                    "sprendimai": " ARBA ".join(sprendimai) if sprendimai else "",
                    "pasiulymas": fault_pasiulymas(r.get("verdict")) or "",
                }
                engine.tracer.emit("decision", intent="findings", action="announce_narrator")
                return None  # the narrator speaks the findings + the choice
            announce = (
                phrase(
                    "findings_announce",
                    faktai=faktai_lt,
                    priezastis=isvada,
                    sprendimai=" ARBA ".join(sprendimai) if sprendimai else "—",
                )
                + " "
            )
            engine.tracer.emit("decision", intent="findings", action="announce")
    if confirmed:
        solution = solution_for(s.evidence, r.get("verdict"))
        if solution == "ticket":
            engine.tracer.emit(
                "drive_decision",
                action="escalate",
                accepted=True,
                reason="evidence: solution=ticket",
            )
            return announce + engine._drive_escalate(None)
        if solution == "bridge":
            # Fix 2 (Andrius 2026-08-21): the bridge is WALKED through the pack's
            # guided steps (dr_pick_cable -> dr_plug_pc -> see/bind/verify)
            # instead of the solver's one-liner "kai prijungsite — pasakykite":
            # the step hints say WHICH cable and WHERE, and a "kaip tai
            # padaryti?" gets the step explained. Synced ONCE, like walker.
            from .evidence import solution_step

            target = solution_step(s.evidence, r.get("verdict"))
            goto = getattr(engine, "_goto_step", None)
            if (
                target
                and r.get("solution_synced") != target
                and r.get("step") != target
                and callable(goto)
            ):
                goto(r, target)
                r["solution_synced"] = target
                engine.tracer.emit(
                    "decision", intent="evidence", action="pivot", to=target, reason="solution"
                )
            elif target:
                r.setdefault("solution_synced", target)
            if announce:
                engine._pending_announce = announce
            return None  # the walker owns the bridge steps from here
        if solution == "walker":
            # R4b: the declared solution is a WALKER step — sync the walker to
            # it ONCE (solution_synced marker: re-syncing every turn would drag
            # the tree back to the solution step it has already walked past)
            # and hand the turn over. The findings announce, if any, goes out
            # as THIS reply; the step's own question follows next turn.
            from .evidence import solution_step

            target = solution_step(s.evidence, r.get("verdict"))
            if target and r.get("solution_synced") != target and r.get("step") != target:
                engine._goto_step(r, target)
                r["solution_synced"] = target
                engine.tracer.emit(
                    "decision", intent="evidence", action="pivot", to=target, reason="solution"
                )
            elif target:
                r.setdefault("solution_synced", target)
            return announce or None
    missing = next_missing(s.evidence, spec, confirmed)
    if missing is None:
        # Nothing left to ask but no confirmation either — a given-up key
        # ("neaišku") may be BLOCKING it forever (live 2026-08-12: the
        # frozen hypothesis dropped the call to solver improvisation).
        # ONE direct revival per key, then genuinely hand over.
        if not confirmed:
            revival = revive_gave_up_key(engine, spec)
            if revival is not None:
                return revival
        if announce:
            engine._pending_announce = announce
        return None
    key, item = missing
    asks = engine._evidence_asks.get(key, 0)
    # Wait signal (C, live 2026-08-20): "palaukit, ateinu" is the caller GOING
    # to do the thing — acknowledge and WAIT; never burn a retry or hammer the
    # question at someone who is walking to the router.
    if asks >= 1 and user_input:
        from .resolution import INTENT_IN_PROGRESS, detect_turn_intent

        if detect_turn_intent(user_input) == INTENT_IN_PROGRESS:
            from .identification import phrase

            engine.tracer.emit(
                "drive_decision", action="wait", accepted=True, reason="in_progress", key=key
            )
            reply = phrase("wait_ack")
            return (announce + reply) if announce else reply
    if asks >= 2:
        # Asked twice (normal + paprasciau), still nothing readable — record
        # "neaišku" and move on; an unreadable caller must never loop us.
        set_fact(s.evidence, key, "neaišku", CLIENT, s.turn_count)
        engine.tracer.emit("evidence", action="gave_up", key=key)
        if getattr(engine, "_evidence_last_ask_key", None) == key:
            # A given-up key must not read as an OPEN question forever —
            # the walker's ownership gate keys off this.
            engine._evidence_last_ask_key = None
        inner = evidence_drive(engine, user_input)
        if inner is None:
            if announce:
                engine._pending_announce = announce
            return None
        return announce + inner
    # B2 pointer (2026-08-21): a fact may name the walker step that carries
    # its RAG section / hint / tikslas (`zingsnis:` on the evidence item) —
    # the walker FOLLOWS the ledger instead of reading answers itself.
    z = item.get("zingsnis")
    if z and r.get("step") != z:
        from .resolution import get_strategy

        strat = get_strategy(r.get("verdict"))
        goto = getattr(engine, "_goto_step", None)
        if strat is not None and strat.step(str(z)) is not None and callable(goto):
            goto(r, str(z))
            engine.tracer.emit(
                "decision", intent="evidence", action="pivot", to=str(z), reason="fact pointer"
            )
    engine._evidence_asks[key] = asks + 1
    engine._evidence_last_ask_key = key  # for the barge-in cancel rollback
    # Persona (R5c): the FIRST ask goes to the NARRATOR as a goal directive —
    # it words the question naturally with its full persona + context. Retries,
    # clarifies and facts with `formuluote: skriptas` stay scripted (precision
    # beats style on a repeat). NARRATOR_QUESTIONS=off reverts everything.
    if (
        asks == 0
        and os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on"
        and str(item.get("formuluote") or "") != "skriptas"
        and item.get("reikia")
    ):
        engine._evidence_directive = {
            "key": key,
            "reikia": str(item["reikia"]),
            "kodel": str(item.get("kodel") or ""),
            "klausimas": str(item.get("klausimas") or ""),
        }
        engine.tracer.emit(
            "drive_decision",
            action="ask_evidence",
            accepted=True,
            reason="narrator-worded",
            key=key,
            level=1,
        )
        if announce:
            engine._pending_announce = announce
        return None  # the narrator asks — walker holds on the open question
    text = item.get("klausimas") if asks == 0 else (item.get("paprasciau") or item.get("klausimas"))
    # The caller hears WHY we ask before what to press (Andrius 2026-08-11:
    # "kad klientas žinotų kodėl prašo to ar kito") — once, on the first ask.
    if asks == 0 and item.get("kodel"):
        text = f"{text} {item['kodel']}"
    # Re-ask says WHY it repeats (garsus mąstymas, Andrius 2026-08-11): the
    # caller hears the agent is unsure about the SAME thing, not deaf.
    if asks == 1:
        from .evidence import LABELS
        from .identification import phrase

        text = phrase("reask_reason", tema=LABELS.get(key, key), klausimas=str(text))
    # Bare "Ne." to THIS key's open question: the no has no object — clarify
    # what is denied instead of re-asking the same words (live 2026-08-11).
    if pending_before == key:
        from .resolution import is_bare_negation

        if is_bare_negation(user_input):
            from .identification import phrase

            text = item.get("patikslinimas") or phrase(
                "negation_clarify", klausimas=str(item.get("klausimas") or "")
            )
            engine.tracer.emit("evidence", action="negation_clarify", key=key)
        # DONE-report without a result ("Mhm, patikrinau") — acknowledge the
        # work and ask WHAT was found (ka_radote from faults.yaml).
        if getattr(engine, "_done_report_key", None) == key:
            from .identification import phrase

            engine._done_report_key = None
            text = phrase(
                "done_report_clarify",
                klausimas=str(item.get("ka_radote") or item.get("klausimas") or ""),
            )
            engine.tracer.emit("evidence", action="done_report_clarify", key=key)
    engine.tracer.emit(
        "drive_decision",
        action="ask_evidence",
        accepted=True,
        reason=None,
        key=key,
        level=asks + 1,
    )
    return announce + str(text)

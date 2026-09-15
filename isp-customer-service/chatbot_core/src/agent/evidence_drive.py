"""
Evidence-declared drive (Ledger v2) — question selection, hypothesis routing
and the one-shot checkpoints around it.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of ReactAgent.
Pure ledger mechanics (set_fact, hypothesis_status, next_missing, solution_for) stay
in agent/evidence.py; this module is the CONVERSATIONAL drive over them: what to ask
next, when to recap, when to double-check a refuting fact, when to give up on a key.
Functions take (state, rt) — the call state and the AgentRuntime.
"""

from __future__ import annotations

import os
from typing import Any

from .contract.locale import maybe_phrase
from .evidence import UNKNOWN, gloss_label, gloss_value


def revive_gave_up_key(state: Any, rt: Any, spec: dict) -> str | None:
    """ONE second chance for a given-up key that BLOCKS confirmation
    (Andrius 2026-08-12): 'neaišku' on a patvirtinta-required key froze the
    hypothesis forever. At the dead-end moment the agent asks it once more,
    plainly and with the reason; the answer lands through the pending
    machinery (the give-up marker is replaceable by design). Never loops —
    one revival per key per call."""
    from .contract.locale import phrase

    ev = state.diagnosis.evidence
    for cond in spec.get("confirmed_when") or []:
        if "=" not in cond:
            continue
        key = cond.split("=", 1)[0].strip()
        entry = ev.get(key)
        if entry is None or entry.get("value") != UNKNOWN:
            continue
        if key in state.diagnosis.revived_evidence_keys:
            continue
        state.diagnosis.revived_evidence_keys = [
            *state.diagnosis.revived_evidence_keys,
            key,
        ]
        item = (spec.get("client") or {}).get(key) or {}
        state.diagnosis.pending_evidence_key = key
        rt.tracer.emit("evidence", action="revive_ask", key=key)
        return phrase(
            "identification.reask_reason",
            topic=gloss_label(key),
            question=str(maybe_phrase(item.get("clarify_key") or item.get("question_key")) or ""),
        )
    return None


def maybe_facts_recap(state: Any, rt: Any) -> str | None:
    """Recap-and-confirm CHECKPOINT (Andrius 2026-08-11: 'pasitikslinti, o
    ne kurti'): the first confirmed moment first READS BACK what the caller
    told us — a misheard fact gets corrected here instead of driving a
    wrong solution. Asked once; whatever the answer, the flow moves on next
    turn (corrections land through the normal ingest/conflict machinery)."""
    recap_state = state.diagnosis.facts_recap_state
    if recap_state == "done":
        return None
    if recap_state == "pending":
        state.diagnosis.facts_recap_state = "done"
        rt.tracer.emit("decision", intent="facts_recap", action="answered")
        return None
    from .contract.locale import phrase
    from .evidence import client_facts_lt

    faktai = client_facts_lt(state.diagnosis.evidence)
    if not faktai:
        state.diagnosis.facts_recap_state = "done"
        return None
    # Persona (Andrius 2026-08-20: "Pasitikslinu: routeris surastas: rado; …"
    # is the last remaining label:value dump read to a human) — in narrator
    # mode the recap becomes a goal directive, said in the narrator's words
    # ("Taip, jūs sakote — lemputės nedega net pakeitus rozetę, ar taip?").
    if os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on":
        state.turn.directives.recap = {"faktai": faktai}
        state.diagnosis.facts_recap_state = "pending"
        rt.tracer.emit("decision", intent="facts_recap", action="ask_narrator")
        return None  # the narrator speaks the recap
    state.diagnosis.facts_recap_state = "pending"
    rt.tracer.emit("decision", intent="facts_recap", action="ask")
    return phrase("identification.facts_recap", facts=faktai)


def refuting_client_fact(state: Any, rt: Any, spec: dict) -> tuple[str, str] | None:
    """The CLIENT-stated fact that currently refutes the hypothesis — the
    one worth double-checking before pivoting (telemetry needs no confirm)."""
    from .evidence import CLIENT, _cond_holds

    ev = state.diagnosis.evidence
    for cond in spec.get("refuted_when") or []:
        if "=" in cond and _cond_holds(ev, cond, False):
            key = cond.split("=", 1)[0].strip()
            entry = ev.get(key)
            if entry is not None and entry.get("source") == CLIENT:
                return key, str(entry.get("value"))
    return None


def maybe_refute_confirm(state: Any, rt: Any, spec: dict) -> str | None:
    """One confirm question before abandoning the hypothesis on a
    CLIENT-stated fact (Andrius 2026-08-11: guard against premature
    rejection — STT garbles flip facts). 'Taip' -> pivot proceeds; a
    correction lands via ingest and un-refutes on its own."""
    refute_state = state.diagnosis.refute_confirm_state
    if refute_state == "done":
        return None
    if refute_state == "pending":
        state.diagnosis.refute_confirm_state = "done"
        rt.tracer.emit("decision", intent="refute_confirm", action="answered")
        return None
    kv = refuting_client_fact(state, rt, spec)
    if kv is None:
        state.diagnosis.refute_confirm_state = "done"  # telemetry-backed — trust it
        return None
    key, value = kv
    from .contract.locale import phrase

    state.diagnosis.refute_confirm_state = "pending"
    rt.tracer.emit("decision", intent="refute_confirm", action="ask", key=key)
    return phrase(
        "identification.refute_confirm",
        topic=gloss_label(key),
        value=gloss_value(value),
    )


def evidence_question_open(state: Any, rt: Any) -> str | None:
    """The evidence key whose question is OUT and still unanswered — the one
    question the caller is actually answering right now. The ingest clears
    the pending key the moment a fact lands on it, so a non-None here means
    this turn's reply did NOT read as an answer to it."""
    key = state.diagnosis.pending_evidence_key
    if not key:
        return None
    entry = state.diagnosis.evidence.get(key)
    if entry is not None and entry.get("value") not in (None, UNKNOWN):
        return None
    return key


def negation_clarify_reply(state: Any, rt: Any, key: str) -> str | None:
    """Scripted clarify for a bare-"ne" reply to the open evidence question
    (Andrius 2026-08-11: clarify what the "ne" refers to instead of acting).
    Wording comes from the fault file (`patikslinimas` per key) so every fault
    can name its own two readings; generic phrase as fallback. Counts as an
    ask — the give-up cap still ends an unreadable loop."""
    from .contract.locale import phrase
    from .evidence import spec_for

    if state.diagnosis.evidence_ask_counts.get(key, 0) >= 2:
        return None  # already asked twice — let the drive give up, not loop
    spec = spec_for((state.resolution.procedure or {}).get("verdict")) or {}
    item = (spec.get("client") or {}).get(key) or {}
    state.diagnosis.evidence_ask_counts[key] = state.diagnosis.evidence_ask_counts.get(key, 0) + 1
    rt.tracer.emit("evidence", action="negation_clarify", key=key)
    return str(
        maybe_phrase(item.get("clarify_key"))
        or phrase(
            "identification.negation_clarify",
            question=str(maybe_phrase(item.get("question_key")) or ""),
        )
    ).strip()


def _sync_walker_solution(state: Any, rt: Any, s: Any, r: dict) -> None:
    """Sync the walker to the declared `tada: walker` solution step ONCE
    (solution_synced marker: re-syncing every turn would drag the tree back
    to the solution step it has already walked past) and hand the turn over
    — the step's own hint/question goes out next."""
    from .evidence import solution_step
    from .walker_flow import goto_step

    target = solution_step(s.diagnosis.evidence, r.get("verdict"))
    if target and r.get("solution_synced") != target and r.get("step") != target:
        goto_step(state, rt, r, target)
        r["solution_synced"] = target
        rt.tracer.emit("decision", intent="evidence", action="pivot", to=target, reason="solution")
    elif target:
        r.setdefault("solution_synced", target)
    return None


def evidence_drive(state: Any, rt: Any, user_input: str | None) -> str | None:
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
    from .solver_flow import drive_escalate
    from .ticket_flow import ticket_need
    from .walker_flow import goto_step

    s = state
    r = s.resolution.procedure or {}
    spec = spec_for(r.get("verdict"))
    if spec is None:
        return None
    # W1-2 svarbos vartai: a parked story-flipping fact gets its ONE confirm
    # (see _sync_walker_solution below for the shared solution-sync mechanics)
    # question before anything else — the ledger stays clean until the caller
    # says "taip" (STT garbles poison exactly these facts).
    fc = state.diagnosis.fact_confirm_pending
    if fc is not None:
        from .contract.locale import phrase as _phrase

        state.diagnosis.fact_confirm_pending = None
        state.diagnosis.fact_confirm_asked = fc
        rt.tracer.emit("decision", intent="fact_confirm", action="ask", key=fc.key)
        return _phrase(
            "identification.refute_confirm",
            topic=gloss_label(fc.key),
            value=gloss_value(fc.value),
        )
    # Captured BEFORE any new ask below overwrites it: was a question already
    # out when the caller spoke? Needed for the bare-"ne" clarify.
    pending_before = evidence_question_open(state, rt)
    status = hypothesis_status(s.diagnosis.evidence, spec)
    if status == "refuted":
        # One confirm question before the pivot when the refuting fact came
        # from the CALLER's words — STT garbles flip facts (2026-08-11).
        refute_reply = maybe_refute_confirm(state, rt, spec)
        if refute_reply is not None:
            return refute_reply
        # A lit lamp disproves the dead-router path — sync the walker to the
        # declared pivot step so NOTHING rewinds, then let it continue.
        from .faults import step_by_role

        pivot = step_by_role(r.get("verdict"), spec.get("on_refuted") or "")
        target = pivot.id if pivot else None
        if target and r.get("step") != target:
            goto_step(state, rt, r, target)
            rt.tracer.emit(
                "decision", intent="evidence", action="pivot", to=target, reason="refuted"
            )
        return None
    confirmed = status == "confirmed"
    # FINDINGS announce (2026-08-10): the FIRST confirmed moment is the
    # transition the caller must HEAR — what we checked together, the
    # conclusion, the options — before any solution question. Composed
    # deterministically from the ledger + the fault's file (isvada,
    # solution descriptions), so every newly declared fault gets it free.
    announce = ""
    if confirmed and not state.diagnosis.findings_announced:
        from .evidence import solution_for as _solution_for

        # A fully DETERMINED walker solution needs no findings ritual (S6
        # pakibęs routeris, 2026-08-31): the recap+announce checkpoint exists
        # for real decision points — the caller still choosing between
        # solutions (bridge vs ticket). When the facts already pin a single
        # `tada: walker` step, the ritual only delays the sync a turn (or
        # more), the walker never takes over and the narrator improvises.
        # The step's own hint explains the finding and instructs in ONE move.
        if _solution_for(s.diagnosis.evidence, r.get("verdict")) == "procedure":
            state.diagnosis.findings_announced = True
            return _sync_walker_solution(state, rt, s, r)
        # Recap checkpoint FIRST: read the gathered facts back and let the
        # caller confirm or correct before any conclusion is announced.
        recap = maybe_facts_recap(state, rt)
        if recap is not None:
            return recap
        if state.turn.directives.recap:
            return None  # the narrator asks the recap; findings come next turn
        state.diagnosis.findings_announced = True
        from .contract.locale import phrase
        from .evidence import client_facts_lt, fault_conclusion, solution_descriptions

        faktai_lt = client_facts_lt(s.diagnosis.evidence)
        isvada = fault_conclusion(r.get("verdict")) or ticket_need(state, rt)
        sprendimai = solution_descriptions(r.get("verdict"))
        if faktai_lt and isvada:
            # Persona (Andrius 2026-08-13: the template dump "Ką patikrinome:
            # routeris surastas: rado; …" is words FOR the agent, not speech) —
            # in narrator mode the findings go out as a GOAL directive and the
            # narrator says them briefly in its own words.
            if os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on":
                from .evidence import fault_offer_goal

                state.turn.directives.findings = {
                    "faktai": faktai_lt,
                    "isvada": isvada,
                    "sprendimai": " ARBA ".join(sprendimai) if sprendimai else "",
                    "pasiulymas": fault_offer_goal(r.get("verdict")) or "",
                }
                rt.tracer.emit("decision", intent="findings", action="announce_narrator")
                return None  # the narrator speaks the findings + the choice
            announce = (
                phrase(
                    "identification.findings_announce",
                    facts=faktai_lt,
                    reason=isvada,
                    solutions=" ARBA ".join(sprendimai) if sprendimai else "—",
                )
                + " "
            )
            rt.tracer.emit("decision", intent="findings", action="announce")
    if confirmed:
        solution = solution_for(s.diagnosis.evidence, r.get("verdict"))
        if solution == "ticket":
            rt.tracer.emit(
                "drive_decision",
                action="escalate",
                accepted=True,
                reason="evidence: solution=ticket",
            )
            return announce + drive_escalate(state, rt, None)
        if solution == "bridge":
            # Fix 2 (Andrius 2026-08-21): the bridge is WALKED through the pack's
            # guided steps (locate_cable -> plug -> see/bind/verify)
            # instead of the solver's one-liner "kai prijungsite — pasakykite":
            # the step hints say WHICH cable and WHERE, and a "kaip tai
            # padaryti?" gets the step explained. Synced ONCE, like walker.
            from .evidence import solution_step

            target = solution_step(s.diagnosis.evidence, r.get("verdict"))
            if target and r.get("solution_synced") != target and r.get("step") != target:
                goto_step(state, rt, r, target)
                r["solution_synced"] = target
                rt.tracer.emit(
                    "decision", intent="evidence", action="pivot", to=target, reason="solution"
                )
            elif target:
                r.setdefault("solution_synced", target)
            if announce:
                state.diagnosis.pending_announcement = announce
            return None  # the walker owns the bridge steps from here
        if solution == "procedure":
            # R4b: the declared solution is a WALKER step — sync the walker to
            # it ONCE and hand the turn over. The findings announce, if any,
            # goes out as THIS reply; the step's question follows next turn.
            _sync_walker_solution(state, rt, s, r)
            return announce or None
    missing = next_missing(s.diagnosis.evidence, spec, confirmed)
    if missing is None:
        # Nothing left to ask but no confirmation either — a given-up key
        # ("neaišku") may be BLOCKING it forever (live 2026-08-12: the
        # frozen hypothesis dropped the call to solver improvisation).
        # ONE direct revival per key, then genuinely hand over.
        if not confirmed:
            revival = revive_gave_up_key(state, rt, spec)
            if revival is not None:
                return revival
        if announce:
            state.diagnosis.pending_announcement = announce
        return None
    key, item = missing
    asks = state.diagnosis.evidence_ask_counts.get(key, 0)
    # Wait signal (C, live 2026-08-20): "palaukit, ateinu" is the caller GOING
    # to do the thing — acknowledge and WAIT; never burn a retry or hammer the
    # question at someone who is walking to the router.
    if asks >= 1 and user_input:
        from .resolution import INTENT_IN_PROGRESS, detect_turn_intent

        if detect_turn_intent(user_input) == INTENT_IN_PROGRESS:
            from .contract.locale import phrase

            rt.tracer.emit(
                "drive_decision", action="wait", accepted=True, reason="in_progress", key=key
            )
            reply = phrase("identification.wait_ack")
            return (announce + reply) if announce else reply
    if asks >= 2:
        # Asked twice (normal + paprasciau), still nothing readable — record
        # "neaišku" and move on; an unreadable caller must never loop us.
        set_fact(s.diagnosis.evidence, key, UNKNOWN, CLIENT, s.dialog.turn_count)
        rt.tracer.emit("evidence", action="gave_up", key=key)
        if state.diagnosis.pending_evidence_key == key:
            # A given-up key must not read as an OPEN question forever —
            # the walker's ownership gate keys off this.
            state.diagnosis.pending_evidence_key = None
        inner = evidence_drive(state, rt, user_input)
        if inner is None:
            if announce:
                state.diagnosis.pending_announcement = announce
            return None
        return announce + inner
    # B2 pointer (2026-08-21): a fact may name the walker step that carries
    # its RAG section / hint / goal (`step_role:` on the evidence item) —
    # the walker FOLLOWS the ledger instead of reading answers itself.
    from .faults import step_by_role

    pointed = step_by_role(r.get("verdict"), item.get("step_role") or "")
    z = pointed.id if pointed else None
    if z and r.get("step") != z:
        if pointed is not None:
            goto_step(state, rt, r, str(z))
            rt.tracer.emit(
                "decision", intent="evidence", action="pivot", to=str(z), reason="fact pointer"
            )
    state.diagnosis.evidence_ask_counts[key] = asks + 1
    state.diagnosis.pending_evidence_key = key  # for the barge-in cancel rollback
    # B-wave registry (shadow): the evidence question is the walker family's
    # ask — both the narrator-worded first ask and the scripted retries pass
    # through here, so the asks counter mirrors the retry ladder.
    from .dialog_registry import register as _q_register

    _q_register(state, rt, "walker", f"evidence:{key}")
    # Persona (R5c): the FIRST ask goes to the NARRATOR as a goal directive —
    # it words the question naturally with its full persona + context. Retries,
    # clarifies and facts with `wording: scripted` stay scripted (precision
    # beats style on a repeat). NARRATOR_QUESTIONS=off reverts everything.
    if (
        asks == 0
        and os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on"
        and str(item.get("wording") or "") != "scripted"
        and item.get("goal")
    ):
        state.turn.directives.evidence = {
            "key": key,
            "reikia": str(item["goal"]),
            "kodel": str(maybe_phrase(item.get("why_key")) or ""),
            "klausimas": str(maybe_phrase(item.get("question_key")) or ""),
        }
        rt.tracer.emit(
            "drive_decision",
            action="ask_evidence",
            accepted=True,
            reason="narrator-worded",
            key=key,
            level=1,
        )
        if announce:
            state.diagnosis.pending_announcement = announce
        return None  # the narrator asks — walker holds on the open question
    text = maybe_phrase(
        item.get("question_key")
        if asks == 0
        else (item.get("simpler_key") or item.get("question_key"))
    )
    # The caller hears WHY we ask before what to press (Andrius 2026-08-11:
    # "kad klientas žinotų kodėl prašo to ar kito") — once, on the first ask.
    if asks == 0 and item.get("why_key"):
        text = f"{text} {maybe_phrase(item['why_key'])}"
    # Re-ask says WHY it repeats (garsus mąstymas, Andrius 2026-08-11): the
    # caller hears the agent is unsure about the SAME thing, not deaf.
    if asks == 1:
        from .contract.locale import phrase

        text = phrase(
            "identification.reask_reason",
            topic=gloss_label(key),
            question=str(text),
        )
    # Bare "Ne." to THIS key's open question: the no has no object — clarify
    # what is denied instead of re-asking the same words (live 2026-08-11).
    if pending_before == key:
        from .resolution import is_bare_negation

        if is_bare_negation(user_input):
            from .contract.locale import phrase

            text = maybe_phrase(item.get("clarify_key")) or phrase(
                "identification.negation_clarify",
                question=str(maybe_phrase(item.get("question_key")) or ""),
            )
            rt.tracer.emit("evidence", action="negation_clarify", key=key)
        # DONE-report without a result ("Mhm, patikrinau") — acknowledge the
        # work and ask WHAT was found (ka_radote from faults.yaml).
        if state.turn.done_report_key == key:
            from .contract.locale import phrase

            state.turn.done_report_key = None
            text = phrase(
                "identification.done_report_clarify",
                question=str(
                    maybe_phrase(item.get("ask_result_key") or item.get("question_key")) or ""
                ),
            )
            rt.tracer.emit("evidence", action="done_report_clarify", key=key)
    rt.tracer.emit(
        "drive_decision",
        action="ask_evidence",
        accepted=True,
        reason=None,
        key=key,
        level=asks + 1,
    )
    return announce + str(text)

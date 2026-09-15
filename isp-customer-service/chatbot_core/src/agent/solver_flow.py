"""
Solver flow — the THINKER drive: context building, the gated solve loop,
the disciplined bridge fix, the failure ladder and the escalate hand-off.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of ReactAgent.
The pure pieces stay put: solver.py (the LLM reasoner), gate.py (the deterministic
policy). Functions take (state, rt) — the call state and the AgentRuntime. tools run
through rt.tools (the gateway).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .contract import limits
from .contract.locale import phrase, vocab
from .dialog_utils import last_agent_question
from .trace import trace_note

# --- Solver DRIVES (Phase 3.8 step 5a) -----------------------------------
# Behind SOLVER_DRIVE (default off), for the piloted directions only, the solver runs
# the turn: it reads the RAG playbook + dialogue + telemetry, decides the next action,
# the gate validates + the engine executes safety actions by code, and the reply is the
# solver's spoken text. The walker stays the default and handles every other direction.

logger = logging.getLogger(__name__)


def narrator(state, rt):
    from .graph_v2.runtime import narrator as _narrator

    return _narrator(state, rt)


def build_solver_context(state: Any, rt: Any, user_input: str | None) -> str:
    """Compact situation snapshot the solver reasons over: the live hypothesis, the
    raw telemetry facts (line-side truth), the caller's latest turn, and where the
    walker currently is."""
    s = state
    h = s.diagnosis.hypothesis or {}
    net = s.diagnosis.verdicts.get("network") or {}
    sig = net.get("signals") or {}
    r = s.resolution.procedure or {}
    lines: list[str] = []
    # Recent dialogue so the solver knows WHERE in the procedure it is (which steps
    # already happened) instead of re-reasoning from scratch each turn.
    recent = [
        m
        for m in s.messages
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ][-limits.get("solver_context_messages") :]
    if recent:
        convo = "\n".join(
            f"{'Caller' if m['role'] == 'user' else 'Agent'}: {m['content']}" for m in recent
        )
        lines.append(f"CONVERSATION SO FAR:\n{convo}\n")
    lines.append(
        f'THE CALLER JUST SAID: "{user_input or ""}" (intent={s.dialog.last_intent or "?"})'
    )
    if h:
        because = "; ".join(h.get("because", []) or [])
        lines.append(f"HYPOTHESIS: {h.get('cause')} (status={h.get('status')}); because: {because}")
    # The ANALYSIS (Step 2): the caller's half of the picture — the thinker reasons
    # from BOTH sides, not telemetry alone.
    if s.intake.anamnesis_raw:
        bits = [f'in words: "{s.intake.anamnesis_raw}"']
        if s.intake.anamnesis_when:
            bits.append(f"went down: {s.intake.anamnesis_when}")
        if s.intake.anamnesis_trigger:
            bits.append(f"after: {s.intake.anamnesis_trigger}")
        lines.append("ANAMNESIS (caller): " + "; ".join(bits))
    if s.intake.symptoms:
        lines.append("SYMPTOMS: " + ", ".join(f"{k}={v}" for k, v in s.intake.symptoms.items()))
    if s.identity.caller_name:
        lines.append(
            f"CALLER: {s.identity.caller_name} (relation to the contract: {s.identity.caller_relation})"
        )
    if net.get("reason"):
        lines.append(f"TELEMETRY CANDIDATE (verdict tree): {net.get('reason')}")
    if sig:
        keys = (
            "port_link",
            "switch_status",
            "observed_mac",
            "registered_mac",
            "crc_error_rate",
            "dhcp_status",
            "incident",
            "billing_suspended",
        )
        facts = ", ".join(f"{k}={sig.get(k)}" for k in keys if sig.get(k) is not None)
        if facts:
            lines.append(f"TELEMETRY (signals): {facts}")
    # Evidence ledger (Ledger v1): what is already ESTABLISHED — the thinker
    # asks only for what is missing and never re-asks a settled fact.
    if s.diagnosis.evidence:
        from .evidence import summary_lt

        lines.append(
            f"EVIDENCE LEDGER (established — DO NOT ASK AGAIN): {summary_lt(s.diagnosis.evidence)}"
        )
    # Bridge-phase anchor (2026-08-12): after the plug report the solver
    # kept sliding back to router/power questions — the router is HISTORY.
    if state.resolution.bridge_plug_reported:
        lines.append(
            "BRIDGE PHASE: the router is already considered dead and the cable is MOVED to "
            "the computer — do NOT ask about the router lights/power any more. The work now: "
            "connecting the computer (visibility on the line, the computer's LAN state)."
        )
    lines.append(
        f"WALKER now: verdict={r.get('verdict')} step={r.get('step')} awaiting={s.dialog.awaiting}"
    )
    # Process journal (awareness №3): the transitions already walked — the
    # thinker sees the path ("what already happened"), so it never re-proposes a step
    # the call has moved past.
    if r.get("journal"):
        lines.append(
            "STEPS WALKED (already happened): "
            + "; ".join(r["journal"][-limits.get("solver_context_journal_entries") :])
        )
    # The full procedure for this fault (the solver reasons over the WHOLE playbook to
    # pick the next action — unlike the narrator, which sees one isolated step).
    if r.get("verdict"):
        from .playbook import full_doc
        from .resolution import get_strategy

        strat = get_strategy(r.get("verdict"))
        doc = full_doc(strat.rag_doc) if strat and strat.rag_doc else None
        if doc:
            lines.append(f"\nPROCEDURE (playbook — follow it to drive the flow):\n{doc}")
    return "\n".join(lines)


def shadow_solve(state: Any, rt: Any, user_input: str | None) -> None:
    """SHADOW: compute the solver's decision and log it next to the walker's move.
    Never drives the reply. No-op unless SOLVER_SHADOW=on and a strategy is active."""
    if os.getenv("SOLVER_SHADOW", "off").lower() != "on":
        return
    if not state.resolution.procedure or state.closing.case_closed:
        return
    try:
        from .faults import pack_verdicts
        from .gate import INTERNAL_ACTIONS, gate
        from .solver import solve

        decision = solve(
            build_solver_context(state, rt, user_input),
            model=rt.config.solver_model or rt.config.model,
        )
        r = state.resolution.procedure or {}
        step = r.get("step")

        # Counters the gate reasons over (owned here so the gate stays pure). Track
        # them even in shadow so the bailout/loop safeguards are exercised for real.
        state.resolution.solver_cycles = (
            state.resolution.solver_cycles + 1 if step == state.resolution.solver_prev_step else 0
        )
        state.resolution.solver_prev_step = step
        conf = decision.confidence if decision else 0.0
        state.resolution.solver_low_conf_streak = (
            state.resolution.solver_low_conf_streak + 1
            if conf < limits.get("solver_confidence_floor")
            else 0
        )
        if decision and decision.next_action in INTERNAL_ACTIONS:
            state.resolution.solver_internal_hops += 1
        else:
            state.resolution.solver_internal_hops = 0

        result = gate(
            decision,
            known_hypotheses=pack_verdicts(),
            low_conf_streak=state.resolution.solver_low_conf_streak,
            cycles_in_step=state.resolution.solver_cycles,
            internal_hops=state.resolution.solver_internal_hops,
        )
        rt.tracer.emit(
            "shadow_decision",
            walker_verdict=r.get("verdict"),
            walker_step=step,
            solver=(decision.model_dump() if decision else None),
            gate={
                "action": result.action,
                "accepted": result.accepted,
                "bailout": result.bailout,
                "reason": result.reason,
            },
        )
    except Exception as e:  # shadow must never affect the live turn
        logger.warning(f"shadow solver failed: {e}")
        trace_note(rt.tracer, state, "solver_shadow", str(e))


def plug_report(state: Any, rt: Any, user_input: str | None) -> bool:
    """A completed plug-into-computer report, read IN CONTEXT: when the
    agent's LAST question was about the computer cable, the plug verb alone
    suffices — the caller need not repeat the word "kompiuteris". Live
    2026-08-11: "Įkišau, laukiu", "įkištas iki galo" (passive) and
    "pririškite tada" (an explicit bind request!) all failed the
    same-sentence rule and the bind never ran."""
    if not user_input:
        return False
    from .evidence import _fold
    from .resolution import detect_plugged

    low = _fold(user_input)
    last_q = _fold(last_agent_question(state) or "")
    computer = vocab("fact_computer_words")
    if not any(w in low for w in computer) and not any(w in last_q for w in computer):
        return False  # not the bridge context — a cable reseat is not a bind
    if detect_plugged(user_input):
        return True
    from .evidence import _mark_hit

    if any(_mark_hit(low, m) for m in vocab("bind_request")):
        return True
    # Passive done-forms answering the plug instruction (live 2026-08-13:
    # "jungtas, LAN rodo" — STT drops the prefix — never unlocked the bind).
    return any(_mark_hit(low, m) for m in vocab("plugged_passive"))


def solver_drive_turn(state: Any, rt: Any, user_input: str | None) -> str | None:
    """Solver-driven turn — the THINKER drives the piloted directions (Step 3,
    default ON since 2026-08-03; SOLVER_DRIVE=off reverts to the walker). Returns
    the reply text, or None to fall back to the walker (no strategy, not a piloted
    direction, a solver failure — or DETERMINISTIC MECHANICS in progress: the
    identification ladder, the clarify contract and the wrap-up stay engine-owned,
    the thinker never overrides them)."""
    from .evidence_drive import evidence_drive
    from .walker_flow import goto_step

    if os.getenv("SOLVER_DRIVE", "on").lower() != "on":
        return None
    r = state.resolution.procedure
    if not r or state.closing.case_closed:
        return None
    # One driver (D-03): every pack with evidence is led by the evidence layer and
    # the solver; a pack without evidence (unclear_fault) is its procedure alone.
    from .faults import evidence_led

    if not evidence_led(r.get("verdict")):
        return None
    # Engine mechanics first: while the ladder / clarify flow owns the turn, the
    # thinker waits (scripted replies and guards are deterministic territory).
    if (
        state.identity.result_pending
        or state.dialog.end_confirm_pending
        or state.dialog.resume_hold_due
    ):
        return None
    # B-wave switch (2026-09-08): a higher-priority open question (safety/
    # ident/ticket) owns the turn — the solver waits like the walker does.
    from .dialog_registry import OWNER_PRIORITY
    from .dialog_registry import active as _q_active

    _q = _q_active(state, rt)
    if _q is not None and OWNER_PRIORITY.get(_q.owner, 99) < OWNER_PRIORITY["walker"]:
        return None
    if state.ticket.stage:
        return None  # the ticket dialogue owns the turn
    if state.diagnosis.evidence_conflict:
        return None  # the scripted conflict clarification owns the turn
    if state.turn.side_topic_active:
        return None  # the side_topic node owns the turn (answer + anchor)
    # POLICY turns never belong to the thinker (2026-08-07: a refusal
    # ("neturiu laiko") got a solver `wait`→`close` and the call ended with
    # NO ticket, bypassing the refuse→registration policy; a goodbye
    # mid-strategy must go through the end-confirm). Returning None hands
    # the turn to the walker + guards, which own those policies.
    from .resolution import detect_farewell, detect_refuse_or_ticket

    if detect_farewell(user_input) or detect_refuse_or_ticket(user_input) is not None:
        return None
    from .identification import ask_caller

    if ask_caller() and not state.identity.caller_name:
        return None  # identification ladder not finished yet
    # Discipline rule (2026-08-06, eval S4): a reported plug-in INTO THE
    # COMPUTER runs the bind path deterministically — the solver answered
    # "Įkišau į kompiuterį" with yet another disambiguate and the bind never
    # happened. drive_propose_fix keeps all its own discipline (device must
    # actually be visible before any bind). Round 4 (2026-08-11): the report
    # is read IN CONTEXT (plug_report) and REMEMBERED — "Įkišau, laukiu"
    # without the word "kompiuteris" counted for nothing and the bind never
    # ran while the caller kept repeating they had done it.
    from .resolution import detect_no_device

    if plug_report(state, rt, user_input):
        state.resolution.bridge_plug_reported = True
        reply = drive_propose_fix(state, rt, "", user_input)
        return narrator(state, rt)._commit_driven_reply(user_input, reply)
    # Discipline rule (2026-08-05): "no device" after the bridge OFFER is
    # ENGINE territory — with nothing to bridge through, the only solutions
    # are ticket-shaped, so escalate NOW. Left to the solver, this answer
    # spawned a disambiguate streak ("patikrinkime dar kartą…" x6) and,
    # after the bailout, a full walker rewind to dr_intro (observed live).
    # The EXTRACTOR reads the answer ("Neturiu kito routerio, tik
    # kompiuterį" is a YES — the loose detector escalated on it).
    from .evidence import extract_client_facts

    last_q = (last_agent_question(state) or "").lower()
    has_pc = extract_client_facts(user_input).get("has_computer")
    if any(w in last_q for w in vocab("fact_computer_words")) and (
        has_pc == "no" or (has_pc is None and detect_no_device(user_input))
    ):
        rt.tracer.emit(
            "drive_decision",
            action="escalate",
            accepted=True,
            reason="no device after bridge offer — deterministic",
        )
        return narrator(state, rt)._commit_driven_reply(user_input, drive_escalate(state, rt, None))
    # Ledger v2: the fault declares its EVIDENCE (faults.yaml) — the engine
    # asks the first missing fact, confirms/refutes from the ledger and picks
    # the declared solution. Deterministic; runs even after a solver bench,
    # so there is never a "step to rewind to". None -> the solver's turn.
    evidence_reply = evidence_drive(state, rt, user_input)
    if evidence_reply is not None:
        return narrator(state, rt)._commit_driven_reply(user_input, evidence_reply)
    # Persona (R5c): the drive delegated the question's WORDING to the narrator
    # (goal directive in the facts block) — hand the turn to the narrator path.
    # Same for the FINDINGS moment (facts + conclusion + choice, said humanly).
    if (
        state.turn.directives.evidence
        or state.turn.directives.findings
        or state.turn.directives.recap
    ):
        return None
    # R4b: a confirmed hypothesis with a WALKER solution means the step tree
    # owns the execution from here — hand every turn to the walker instead of
    # improvising with the LLM solver (which is for gaps, not for declared paths).
    from .evidence import hypothesis_status, solution_for, spec_for

    _spec = spec_for(r.get("verdict"))
    if (
        _spec is not None
        and hypothesis_status(state.diagnosis.evidence, _spec) == "confirmed"
        and solution_for(state.diagnosis.evidence, r.get("verdict")) in ("procedure", "bridge")
        and r.get("solution_synced")
    ):
        return None  # the walker takes this and every following turn
    # Distrust-loop bailout (deterministic): the solver repeated itself or kept
    # re-confirming ("disambiguate") turn after turn despite clear answers — the
    # prompt rule did not hold it (observed live: 6x "patikrinkime dar kartą…";
    # in eval: 6/8 turns of variously-worded disambiguate). The promised backstop
    # takes over: the DETERMINISTIC WALKER resumes this direction for the rest of
    # the call; its own guards (stuck counter, escalate) handle the endgame.
    if state.resolution.drive_disabled:
        return None
    if state.resolution.drive_repeats >= limits.get("solver_drive_repeat_bailout"):
        state.resolution.drive_disabled = True
        state.resolution.drive_repeats = 0
        state.resolution.drive_last_reply = None
        rt.tracer.emit(
            "drive_decision",
            action="bailout_to_walker",
            accepted=False,
            reason="distrust loop (repeat/disambiguate streak)",
        )
        trace_note(
            rt.tracer,
            state,
            "solver_drive",
            "distrust loop — walker resumes",
            level="warn",
        )
        # Ledger-position sync (round 4, 2026-08-11): a mid-bridge bailout
        # resumed at a long-stale dr_intro and improvised into a ticket one
        # step from a working bridge. With a CONFIRMED hypothesis the walker
        # lands on the solution step the fault file declares (`step_role`).
        from .evidence import hypothesis_status, solution_step, spec_for
        from .resolution import get_strategy

        r = state.resolution.procedure or {}
        spec = spec_for(r.get("verdict"))
        strat = get_strategy(r.get("verdict"))
        target = None
        if spec and hypothesis_status(state.diagnosis.evidence, spec) == "confirmed":
            target = solution_step(state.diagnosis.evidence, r.get("verdict"))
        elif spec:
            # UNCONFIRMED dead end (evidence exhausted, revival spent):
            # resuming at the long-stale intro re-walked the WHOLE ladder
            # (live 2026-08-12: power cable re-asked from scratch). The
            # honest endgame is the registration offer.
            esc = strat.by_role("escalate") if strat else None
            target = esc.id if esc else None
        if target and strat and strat.step(target) and r.get("step") != target:
            goto_step(state, rt, r, target)
            rt.tracer.emit(
                "decision",
                intent="evidence",
                action="pivot",
                to=target,
                reason="bailout sync",
            )
        return None  # the walker takes this and every following turn
    try:
        reply = drive(state, rt, user_input)
    except Exception as e:  # a solver failure falls back to the walker (no bookkeeping yet)
        logger.error(f"solver drive failed: {e}")
        trace_note(rt.tracer, state, "solver_drive", str(e), level="error")
        return None
    # The findings announce stashed by the evidence layer rides on the
    # solver's first reply (the bridge path returns None to hand over).
    pending_announce = state.diagnosis.pending_announcement
    if pending_announce:
        reply = pending_announce + reply
        state.diagnosis.pending_announcement = ""
    # Committed to driving this turn — do the same end-of-turn bookkeeping the walker
    # path gets from run_turn_scoped_stream: user_turn trace, dialogue history (the solver reads
    # it next turn), and the shared reply finalisation (case snapshot + agent_reply).
    if user_input:
        state.dialog.last_heard = user_input.strip()
        rt.tracer.emit("user_turn", text=user_input)
        state.messages.append({"role": "user", "content": user_input})
    state.messages.append({"role": "assistant", "content": reply})
    narrator(state, rt)._finalize_reply(reply)
    return reply


def drive(state: Any, rt: Any, user_input: str | None) -> str:
    from .faults import pack_verdicts
    from .gate import gate
    from .resolution import detect_turn_intent
    from .solver import solve

    state.dialog.last_intent = detect_turn_intent(user_input)
    state.resolution.drive_turns = state.resolution.drive_turns + 1

    context = build_solver_context(state, rt, user_input)
    # Anti-repeat nudge: last reply repeated an earlier one — tell the solver the
    # answer is already GIVEN and it must take a DIFFERENT next step.
    if state.resolution.drive_repeats >= limits.get("solver_drive_repeat_nudge_at"):
        context += (
            "\nIMPORTANT: your previous question REPEATED, and the caller has already answered "
            "and confirmed. ACCEPT that answer as a fact and take the NEXT step (another "
            "hypothesis, an offer or the registration) — do NOT ask the same again."
        )
    # A few internal (silent) hops are allowed — reread/pivot re-read the line — before
    # a client-facing action is forced. Hard turn cap escalates rather than looping.
    for _ in range(limits.get("solver_internal_hops_max") + 1):
        decision = solve(context, model=rt.config.solver_model or rt.config.model)
        # Normalize the free-form hypothesis to the ACTIVE direction before the
        # gate: the solver words the same belief freely ("routeris sugedęs,
        # nes…"), and the gate then blocked the direction's OWN fix as a
        # "mutation on unmapped hypothesis" — the announced bind never ran
        # (observed: "pririšiu" spoken, update_mac not called). Working the SAME
        # fault in other words is not a new hypothesis; a real pivot names a
        # DIFFERENT known cause, which stays gated.
        if decision is not None and decision.current_hypothesis not in pack_verdicts():
            decision = decision.model_copy(
                update={
                    "current_hypothesis": (state.resolution.procedure or {}).get("verdict") or ""
                }
            )
        conf = decision.confidence if decision else 0.0
        state.resolution.solver_low_conf_streak = (
            state.resolution.solver_low_conf_streak + 1
            if conf < limits.get("solver_confidence_floor")
            else 0
        )
        forced = state.resolution.drive_turns > limits.get("solver_drive_max_turns")
        result = gate(
            decision,
            known_hypotheses=pack_verdicts(),
            low_conf_streak=state.resolution.solver_low_conf_streak,
            # The REAL per-question cycle count (the same-reply streak) — with a
            # flat 0 here the gate's stuck detector was blind and the solver
            # looped one question 6x (observed live).
            cycles_in_step=(
                limits.get("solver_drive_max_turns") + 1
                if forced
                else state.resolution.drive_repeats
            ),
            internal_hops=state.resolution.solver_internal_hops,
        )
        action = result.action
        rt.tracer.emit(
            "drive_decision",
            action=action,
            accepted=result.accepted,
            bailout=result.bailout,
            reason=result.reason,
            hypothesis=(decision.current_hypothesis if decision else None),
            confidence=conf,
        )
        say = (decision.narrator_instruction if decision else "").strip()
        # Never SPEAK an instruction whose action the gate overrode — the words
        # would promise what will not run ("pririšiu" with the bind blocked).
        if decision is not None and not result.accepted:
            say = ""

        if action in ("reread_telemetry", "pivot"):
            state.resolution.solver_internal_hops += 1
            refresh_diagnosis(state, rt)  # re-read the line, then decide again
            continue
        state.resolution.solver_internal_hops = 0

        if action == "propose_fix":
            return drive_propose_fix(state, rt, say, user_input)
        if action == "escalate":
            return drive_escalate(state, rt, decision)
        if action == "close":
            return close_or_register(state, rt, say)
        # client-facing: ask / disambiguate / instruct / verify / wait — track the
        # DISTRUST streak so the next turn's nudge/gate/bailout see the loop:
        # a verbatim repeat OR consecutive disambiguates (any wording) count.
        reply = say or phrase(
            f"solver.{action}" if action in ("verify", "wait") else "solver.repeat_please"
        )
        norm = " ".join(reply.lower().split())
        repeated = norm == state.resolution.drive_last_reply
        re_disambiguate = (
            action == "disambiguate" and state.resolution.drive_last_action == "disambiguate"
        )
        if repeated or re_disambiguate:
            state.resolution.drive_repeats = state.resolution.drive_repeats + 1
        else:
            state.resolution.drive_repeats = 0
        state.resolution.drive_last_reply = norm
        state.resolution.drive_last_action = action
        if repeated:
            # Verbatim repeat still went out — at least SAY why it repeats
            # (Andrius 2026-08-11: the caller must hear the agent knows it
            # is asking the same thing).
            reply = phrase("identification.repeat_ack") + reply
        return reply
    return phrase("solver.clarify_again")


def close_or_register(state: Any, rt: Any, say: str) -> str:
    """Ticket-first close (Andrius 2026-08-13: 'the point is a broken router and
    the ticket must be registered; secondary — temporary internet'): the
    bridge is TEMPORARY, so a solver 'close' after a successful bridge may not
    end the call without the router-replacement registration — it becomes the
    escalate (live: 'Aš radu internetas' -> close -> ticket=None)."""
    from .walker_flow import settle_hypothesis

    r = state.resolution.procedure or {}
    bridged = bool(r.get("telemetry_fixed")) or state.resolution.bridge_bound
    if bridged and not state.ticket.ticket_id:
        rt.tracer.emit(
            "drive_decision",
            action="escalate",
            accepted=True,
            reason="close overridden: bridge is temporary — register the router ticket",
        )
        return drive_escalate(state, rt, None)
    state.closing.case_closed = True
    state.closing.closed_reason = "resolved"
    settle_hypothesis(state, rt, "confirmed", "the fix worked (solver)")
    return say or phrase("solver.resolved")


def refresh_diagnosis(state: Any, rt: Any) -> None:
    """Re-read the line so the solver reasons over CURRENT telemetry (fixes the stale-
    snapshot issue). Keeps the active strategy; only refreshes the signals."""
    from .walker_flow import ensure_diagnosed

    state.diagnosis.verdicts.pop("network", None)
    ensure_diagnosed(state, rt)


def drive_propose_fix(state: Any, rt: Any, say: str, user_input: str | None) -> str:
    """Execute the bind the solver proposed — under DISCIPLINE (Andrius,
    2026-08-04): a change runs ONLY when the client actually DID the work and
    thereby agreed to it. The solver anticipated the playbook's ending and had the
    engine bind FOUR turns early (before the caller even said they own a computer
    — observed live). Preconditions, in order:
      1. the caller's CURRENT turn reports a completed plug-in ("įkišau…"), OR the
         line already OBSERVES a device (production: it shows up on its own);
         otherwise -> no tools, keep instructing;
      2. never twice — a completed bind is recorded and not repeated;
      3. after the (demo) simulation, bind only if a device is actually observed —
         never bind blind."""
    from .executor_flow import simulate_bridge_connection
    from .narrator_flow import augment_tool_result
    from .walker_flow import goto_step

    cid = state.identity.customer_id
    if state.resolution.bridge_bound:
        return say or phrase("solver.already_bound")

    def _device_visible() -> bool:
        # The tool's verdict envelope carries no signals — device presence is read
        # from the REASON: "no_mac_observed" = the line still sees nothing; any
        # other verdict (foreign_mac after the plug-in) = a device is there.
        try:
            from .tooling import telemetry

            d = telemetry(state, rt, mode="recheck", reason="bridge_device_check").data
            from .faults import verdict_flag

            return verdict_flag((d.get("verdict") or {}).get("reason"), "device_visible")
        except Exception:  # pragma: no cover - best-effort read
            return False

    # Ledger: the offer question is already answered when the ledger holds
    # has_computer=yes — never re-ask an established fact.
    ev_pc = state.diagnosis.evidence.get("has_computer")
    if ev_pc is not None and ev_pc.get("value") == "yes":
        state.resolution.bridge_offered = True
    # Plug-report MEMORY (round 4, 2026-08-11): the report is remembered
    # across turns — the caller said "Įkišau, laukiu" three turns ago and
    # kept being asked to plug in because each NEW turn no longer contained
    # the plug verb. W0-A (live 2026-08-25): the raw detect_plugged fallback
    # is GONE — a power-cable reseat ("ištraukiu, vėl įkišau") read as the
    # bridge plug and the solver jumped to see-device checks mid-power-talk.
    # plug_report keeps the unlock, WITH the computer-context requirement.
    if plug_report(state, rt, user_input):
        state.resolution.bridge_plug_reported = True
    visible = _device_visible()
    # W0-A: the fix may not START before the bridge was even OFFERED — with no
    # offer, no computer on the ledger and no device on the line, a remembered
    # "plug" was about some other cable. Reset it and make the offer first.
    ev_pc0 = state.diagnosis.evidence.get("has_computer")
    if (
        not visible
        and not state.resolution.bridge_offered
        and (ev_pc0 is None or ev_pc0.get("value") != "yes")
        # An explicit plug-into-COMPUTER report THIS turn implies they have
        # one — the offer would be absurd ("Įkišau į kompiuterį" -> bind path).
        and not plug_report(state, rt, user_input)
    ):
        state.resolution.bridge_plug_reported = False
        state.resolution.bridge_offered = True
        rt.tracer.emit(
            "drive_decision", action="fix_deferred", accepted=False, reason="bridge not offered"
        )
        return phrase("solver.bridge_offer")
    if not state.resolution.bridge_plug_reported and not visible:
        # The work is not done yet — the fix must WAIT for the client. And the
        # FIRST deferral must be the actual TRANSITION + OFFER: live 2026-08-05
        # the solver jumped straight to bind-speak ("pririšiu įrenginį") without
        # ever saying the router is dead or asking about a computer — the caller
        # answered "Apie kokį kompiuterį kalbat?".
        rt.tracer.emit(
            "drive_decision", action="fix_deferred", accepted=False, reason="not plugged yet"
        )
        if not state.resolution.bridge_offered:
            state.resolution.bridge_offered = True
            return phrase("solver.bridge_offer")
        return phrase("solver.bridge_wait_plug")
    simulate_bridge_connection(state, rt)
    # Bind only when the line ACTUALLY sees a device now (never blind).
    if not _device_visible():
        rt.tracer.emit(
            "drive_decision", action="fix_deferred", accepted=False, reason="no device observed"
        )
        return bridge_fail_step(state, rt)
    try:
        bind = rt.tools.run(
            state, rt, "update_mac", {"customer_id": cid}, reason="bridge_bind", apply=False
        )
        augment_tool_result(state, rt, "update_mac", bind.observation)  # chains reset + re-diagnose
        state.resolution.bridge_bound = True
    except Exception as e:
        trace_note(rt.tracer, state, "drive_propose_fix", str(e), level="error")
    # Position the walker on the VERIFY step (the step after the bind, read
    # structurally) — the reply below asks "ar internetas atsirado?", so the
    # caller's "jau atsistatė!" must route as RESTORED. Live 2026-08-12 the
    # walker sat on a stale instruct step and the success died unheard: the
    # call drifted into ticket talk over a WORKING line.
    from .resolution import get_strategy, next_step_id

    r = state.resolution.procedure or {}
    strat = get_strategy(r.get("verdict"))
    bind = strat.by_role("bind_device") if strat else None
    if bind is not None:
        target = next_step_id(strat, bind.id, None)
        if strat.step(target) is not None and r.get("step") != target:
            goto_step(state, rt, r, target)
            r["asked"] = True  # the verify question goes out in THIS reply
            r["asked_at"] = len(state.messages) + 1
            from .dialog_registry import register as _q_register

            _q_register(state, rt, "walker", f"step:{target}")
            rt.tracer.emit(
                "decision", intent="evidence", action="pivot", to=target, reason="bind verify"
            )
    # C (Andrius 2026-08-21): the VISIBILITY status is spoken deterministically
    # — the caller hears that we checked, that we SEE the device, and that the
    # bind happened (the solver's own wording skipped the "matau" part live).
    from .contract.locale import phrase as _phrase

    return _phrase("identification.bridge_bound")


def bridge_fail_step(state: Any, rt: Any) -> str:
    """The plug is REPORTED but telemetry still sees nothing — a declared
    failure ladder instead of the same re-check forever (Andrius
    2026-08-12): (1) say the line does not see the device, re-check the
    cable; (2) check the COMPUTER's network card (lan_active — the answer
    lands on the ledger); (3) name the possible incoming-cable problem and
    register the technician, with what-was-tried on the ticket."""
    from .contract.locale import maybe_phrase, phrase, template
    from .evidence import fault_bridge_fail, gloss_value, spec_for

    verdict = (state.resolution.procedure or {}).get("verdict")
    stage = state.resolution.bridge_fail_stage
    if stage == 0:
        state.resolution.bridge_fail_stage = 1
        return phrase("solver.bridge_not_seen")
    if stage == 1:
        state.resolution.bridge_fail_stage = 2
        spec = spec_for(verdict) or {}
        item = (spec.get("client") or {}).get("lan_active") or {}
        # The answer reads against THIS key (pending machinery, universal).
        state.diagnosis.pending_evidence_key = "lan_active"
        state.diagnosis.evidence_ask_counts["lan_active"] = (
            state.diagnosis.evidence_ask_counts.get("lan_active", 0) + 1
        )
        rt.tracer.emit("drive_decision", action="bridge_fail_lan_check", accepted=True)
        return str(maybe_phrase(item.get("question_key")) or phrase("solver.bridge_lan_check"))
    # Stage 2+: LAN answered (or unreadable) and the line is still empty —
    # the technician takes it from here; the attempt goes on the ticket.
    texts = fault_bridge_fail(verdict)
    lan = (state.diagnosis.evidence.get("lan_active") or {}).get("value") or "not_checked"
    state.ticket.bridge_fail_note = (
        texts.get("ticket_note") or template("ticket.details.bridge_failed")
    ).format(lan=gloss_value(lan, "lan_active"))
    rt.tracer.emit(
        "drive_decision",
        action="bridge_fail_escalate",
        accepted=True,
        reason=f"{phrase('evidence.label.lan_active')}: {lan}",
    )
    pastaba = texts.get("notice") or phrase("solver.bridge_failed_notice")
    return pastaba + " " + drive_escalate(state, rt, None)


def drive_escalate(state: Any, rt: Any, decision) -> str:
    """Register the fault and close — through the SAME state-built ticket machinery
    as everywhere else (its ad-hoc create_ticket used to write a raw verdict key as
    the details, lose ticket_id from the record, and then ASK permission for a
    ticket it had already created — observed live). The announce is deterministic:
    the ticket exists, so the words state a fact, never ask."""
    from .resolution import get_strategy
    from .ticket_flow import begin_ticket_dialogue, ticket_stage_reply

    s = state
    r = s.resolution.procedure or {}
    strat = get_strategy(r.get("verdict"))
    # The bridge already restored internet on the PC -> this is the
    # register-router shape (temporary bridge note rides on the ticket).
    bridged = bool(r.get("telemetry_fixed")) or state.resolution.bridge_bound
    step = None
    if strat is not None:
        step = strat.by_role("register_after_bridge") if bridged else strat.by_role("escalate")
        if step is None:
            step = strat.by_role("escalate")
    if not r.get("escalate_reason"):
        r["escalate_reason"] = "phone_fix_failed"
    # Contacts first (2026-08-04): the dialogue collects the number + hours, then
    # _finish_ticket_dialogue registers and closes. The bridged note rides on the
    # final announce via the ctx.
    begin_ticket_dialogue(state, rt, step)
    if state.ticket.context is not None and bridged:
        state.ticket.context.note = phrase("solver.bridged_ticket_note")
    return ticket_stage_reply(state, rt)

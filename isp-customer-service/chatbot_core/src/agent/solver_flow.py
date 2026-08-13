"""
Solver flow — the MĄSTYTOJAS drive: context building, the gated solve loop,
the disciplined bridge fix, the failure ladder and the escalate hand-off.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of
ReactAgent. The pure pieces stay put: solver.py (the LLM reasoner),
gate.py (the deterministic policy). Functions take the engine explicitly;
execute_tool is imported lazily from react_agent so the tests'
import-fallback stubs keep working.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def build_solver_context(engine: Any, user_input: str | None) -> str:
    """Compact situation snapshot the solver reasons over: the live hypothesis, the
    raw telemetry facts (line-side truth), the caller's latest turn, and where the
    walker currently is."""
    s = engine.state
    h = s.hypothesis or {}
    net = s.diagnosis.get("network") or {}
    sig = net.get("signals") or {}
    r = s.resolution or {}
    lines: list[str] = []
    # Recent dialogue so the solver knows WHERE in the procedure it is (which steps
    # already happened) instead of re-reasoning from scratch each turn.
    recent = [
        m
        for m in s.messages
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ][-8:]
    if recent:
        convo = "\n".join(
            f"{'Klientas' if m['role'] == 'user' else 'Agentas'}: {m['content']}" for m in recent
        )
        lines.append(f"POKALBIS IKI ŠIOL:\n{convo}\n")
    lines.append(f'KLIENTAS KĄ TIK PASAKĖ: "{user_input or ""}" (intent={s.last_intent or "?"})')
    if h:
        because = "; ".join(h.get("because", []) or [])
        lines.append(f"HIPOTEZĖ: {h.get('cause')} (status={h.get('status')}); nes: {because}")
    # The ANALYSIS (Step 2): the caller's half of the picture — the thinker reasons
    # from BOTH sides, not telemetry alone.
    if s.anamnesis_raw:
        bits = [f'žodžiais: "{s.anamnesis_raw}"']
        if s.anamnesis_when:
            bits.append(f"dingo {s.anamnesis_when}")
        if s.anamnesis_trigger:
            bits.append(f"po: {s.anamnesis_trigger}")
        lines.append("ANAMNEZĖ (klientas): " + "; ".join(bits))
    if s.symptoms:
        lines.append("SIMPTOMAI: " + ", ".join(f"{k}={v}" for k, v in s.symptoms.items()))
    if s.caller_name:
        lines.append(f"SKAMBINA: {s.caller_name} (ryšys su sutartimi: {s.caller_relation})")
    if net.get("reason"):
        lines.append(f"TELEMETRIJOS KANDIDATAS (verdict tree): {net.get('reason')}")
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
            lines.append(f"TELEMETRIJA (signalai): {facts}")
    # Evidence ledger (Ledger v1): what is already ESTABLISHED — the thinker
    # asks only for what is missing and never re-asks a settled fact.
    if s.evidence:
        from .evidence import summary_lt

        lines.append(f"ĮRODYMŲ ŽURNALAS (nustatyta — NEBEKLAUSK): {summary_lt(s.evidence)}")
    # Bridge-phase anchor (2026-08-12): after the plug report the solver
    # kept sliding back to router/power questions — the router is HISTORY.
    if getattr(engine, "_bridge_plug_reported", False):
        lines.append(
            "TILTO FAZĖ: routeris jau pripažintas sugedusiu ir kabelis PERKIŠTAS į "
            "kompiuterį — apie routerio lemputes/maitinimą NEBEKLAUSK. Darbas dabar: "
            "kompiuterio prijungimas (linijos matomumas, kompiuterio LAN būsena)."
        )
    lines.append(
        f"WALKER dabar: verdict={r.get('verdict')} step={r.get('step')} awaiting={s.awaiting}"
    )
    # The full procedure for this fault (the solver reasons over the WHOLE playbook to
    # pick the next action — unlike the narrator, which sees one isolated step).
    if r.get("verdict"):
        from .playbook import full_doc
        from .resolution import get_strategy

        strat = get_strategy(r.get("verdict"))
        doc = full_doc(strat.rag_doc) if strat and strat.rag_doc else None
        if doc:
            lines.append(f"\nPROCEDŪRA (playbook — sek ja, kad vestum srautą):\n{doc}")
    return "\n".join(lines)


def shadow_solve(engine: Any, user_input: str | None) -> None:
    """SHADOW: compute the solver's decision and log it next to the walker's move.
    Never drives the reply. No-op unless SOLVER_SHADOW=on and a strategy is active."""
    if os.getenv("SOLVER_SHADOW", "off").lower() != "on":
        return
    if not engine.state.resolution or engine.state.case_closed:
        return
    try:
        from .gate import DEFAULT_POLICY, INTERNAL_ACTIONS, gate
        from .resolution import STRATEGIES
        from .solver import solve

        decision = solve(
            engine._build_solver_context(user_input),
            model=engine.config.solver_model or engine.config.model,
        )
        r = engine.state.resolution or {}
        step = r.get("step")

        # Counters the gate reasons over (owned here so the gate stays pure). Track
        # them even in shadow so the bailout/loop safeguards are exercised for real.
        engine._solver_cycles = engine._solver_cycles + 1 if step == engine._solver_prev_step else 0
        engine._solver_prev_step = step
        conf = decision.confidence if decision else 0.0
        engine._solver_low_conf = (
            engine._solver_low_conf + 1 if conf < DEFAULT_POLICY["confidence_floor"] else 0
        )
        if decision and decision.next_action in INTERNAL_ACTIONS:
            engine._solver_internal_hops += 1
        else:
            engine._solver_internal_hops = 0

        result = gate(
            decision,
            known_hypotheses=set(STRATEGIES),
            low_conf_streak=engine._solver_low_conf,
            cycles_in_step=engine._solver_cycles,
            internal_hops=engine._solver_internal_hops,
        )
        engine.tracer.emit(
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
        engine._trace_note("solver_shadow", str(e))


def plug_report(engine: Any, user_input: str | None) -> bool:
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
    last_q = _fold(engine._last_agent_question() or "")
    if "kompiuter" not in low and "kompiuter" not in last_q:
        return False  # not the bridge context — a cable reseat is not a bind
    if detect_plugged(user_input):
        return True
    from .evidence import _mark_hit

    if _mark_hit(low, "pririsk"):  # "pririškite tada" — asks for the bind itself
        return True
    # Passive done-forms answering the plug instruction (live 2026-08-13:
    # "jungtas, LAN rodo" — STT drops the prefix — never unlocked the bind).
    return any(
        _mark_hit(low, m) for m in ("įkištas", "prijungtas", "pajungtas", "jungtas", "kištas")
    )


def solver_drive_turn(engine: Any, user_input: str | None) -> str | None:
    """Solver-driven turn — the MĄSTYTOJAS drives the piloted directions (Step 3,
    default ON since 2026-08-03; SOLVER_DRIVE=off reverts to the walker). Returns
    the reply text, or None to fall back to the walker (no strategy, not a piloted
    direction, a solver failure — or DETERMINISTIC MECHANICS in progress: the
    identification ladder, the clarify contract and the wrap-up stay engine-owned,
    the thinker never overrides them)."""
    if os.getenv("SOLVER_DRIVE", "on").lower() != "on":
        return None
    r = engine.state.resolution
    if not r or engine.state.case_closed:
        return None
    # R4b: the PACK declares its driver (meta.vairuotojas) — the solver takes a
    # fault when its file says so; the legacy frozenset stays the fallback for
    # packs that declare nothing (today: no_mac_observed).
    from .faults import driver

    drv = driver(r.get("verdict"))
    if drv == "walker":
        return None
    if drv != "solveris" and r.get("verdict") not in engine._SOLVER_DRIVE_VERDICTS:
        return None
    # Engine mechanics first: while the ladder / clarify flow owns the turn, the
    # thinker waits (scripted replies and guards are deterministic territory).
    if engine._result_pending or engine._end_confirm_pending or engine._resume_hold:
        return None
    if engine._ticket_stage:
        return None  # the ticket dialogue owns the turn
    if engine._evidence_conflict:
        return None  # the scripted conflict clarification owns the turn
    if engine._side_topic_this_turn:
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

    if ask_caller() and not engine.state.caller_name:
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

    if engine._plug_report(user_input):
        engine._bridge_plug_reported = True
        reply = engine._drive_propose_fix("", user_input)
        return engine._commit_driven_reply(user_input, reply)
    # Discipline rule (2026-08-05): "no device" after the bridge OFFER is
    # ENGINE territory — with nothing to bridge through, the only solutions
    # are ticket-shaped, so escalate NOW. Left to the solver, this answer
    # spawned a disambiguate streak ("patikrinkime dar kartą…" x6) and,
    # after the bailout, a full walker rewind to dr_intro (observed live).
    # The EXTRACTOR reads the answer ("Neturiu kito routerio, tik
    # kompiuterį" is a YES — the loose detector escalated on it).
    from .evidence import extract_client_facts

    last_q = (engine._last_agent_question() or "").lower()
    has_pc = extract_client_facts(user_input).get("has_computer")
    if "kompiuter" in last_q and (
        has_pc == "no" or (has_pc is None and detect_no_device(user_input))
    ):
        engine.tracer.emit(
            "drive_decision",
            action="escalate",
            accepted=True,
            reason="no device after bridge offer — deterministic",
        )
        return engine._commit_driven_reply(user_input, engine._drive_escalate(None))
    # Ledger v2: the fault declares its EVIDENCE (faults.yaml) — the engine
    # asks the first missing fact, confirms/refutes from the ledger and picks
    # the declared solution. Deterministic; runs even after a solver bench,
    # so there is never a "step to rewind to". None -> the solver's turn.
    evidence_reply = engine._evidence_drive(user_input)
    if evidence_reply is not None:
        return engine._commit_driven_reply(user_input, evidence_reply)
    # Persona (R5c): the drive delegated the question's WORDING to the narrator
    # (goal directive in the facts block) — hand the turn to the narrator path.
    # Same for the FINDINGS moment (facts + conclusion + choice, said humanly).
    if getattr(engine, "_evidence_directive", None) or getattr(engine, "_findings_directive", None):
        return None
    # R4b: a confirmed hypothesis with a WALKER solution means the step tree
    # owns the execution from here — hand every turn to the walker instead of
    # improvising with the LLM solver (which is for gaps, not for declared paths).
    from .evidence import hypothesis_status, solution_for, spec_for

    _spec = spec_for(r.get("verdict"))
    if (
        _spec is not None
        and hypothesis_status(engine.state.evidence, _spec) == "confirmed"
        and solution_for(engine.state.evidence, r.get("verdict")) == "walker"
    ):
        return None  # the walker takes this and every following turn
    # Distrust-loop bailout (deterministic): the solver repeated itself or kept
    # re-confirming ("disambiguate") turn after turn despite clear answers — the
    # prompt rule did not hold it (observed live: 6x "patikrinkime dar kartą…";
    # in eval: 6/8 turns of variously-worded disambiguate). The promised backstop
    # takes over: the DETERMINISTIC WALKER resumes this direction for the rest of
    # the call; its own guards (stuck counter, escalate) handle the endgame.
    if getattr(engine, "_drive_disabled", False):
        return None
    if getattr(engine, "_drive_repeats", 0) >= 2:
        engine._drive_disabled = True
        engine._drive_repeats = 0
        engine._drive_last_reply = None
        engine.tracer.emit(
            "drive_decision",
            action="bailout_to_walker",
            accepted=False,
            reason="distrust loop (repeat/disambiguate streak)",
        )
        engine._trace_note("solver_drive", "distrust loop — walker resumes", level="warn")
        # Ledger-position sync (round 4, 2026-08-11): a mid-bridge bailout
        # resumed at a long-stale dr_intro and improvised into a ticket one
        # step from a working bridge. With a CONFIRMED hypothesis the walker
        # lands on the solution step the fault file declares (`zingsnis`).
        from .evidence import hypothesis_status, solution_step, spec_for
        from .resolution import get_strategy

        r = engine.state.resolution or {}
        spec = spec_for(r.get("verdict"))
        strat = get_strategy(r.get("verdict"))
        target = None
        if spec and hypothesis_status(engine.state.evidence, spec) == "confirmed":
            target = solution_step(engine.state.evidence, r.get("verdict"))
        elif spec:
            # UNCONFIRMED dead end (evidence exhausted, revival spent):
            # resuming at the long-stale intro re-walked the WHOLE ladder
            # (live 2026-08-12: power cable re-asked from scratch). The
            # honest endgame is the registration offer.
            target = "escalate"
        if target and strat and strat.step(target) and r.get("step") != target:
            engine._goto_step(r, target)
            engine.tracer.emit(
                "decision",
                intent="evidence",
                action="pivot",
                to=target,
                reason="bailout sync",
            )
        return None  # the walker takes this and every following turn
    try:
        reply = engine._drive(user_input)
    except Exception as e:  # a solver failure falls back to the walker (no bookkeeping yet)
        logger.error(f"solver drive failed: {e}")
        engine._trace_note("solver_drive", str(e), level="error")
        return None
    # The findings announce stashed by the evidence layer rides on the
    # solver's first reply (the bridge path returns None to hand over).
    pending_announce = getattr(engine, "_pending_announce", "")
    if pending_announce:
        reply = pending_announce + reply
        engine._pending_announce = ""
    # Committed to driving this turn — do the same end-of-turn bookkeeping the walker
    # path gets from run_turn_scoped: user_turn trace, dialogue history (the solver reads
    # it next turn), and the shared reply finalisation (case snapshot + agent_reply).
    if user_input:
        engine.state.last_heard = user_input.strip()
        engine.tracer.emit("user_turn", text=user_input)
        engine.state.messages.append({"role": "user", "content": user_input})
    engine.state.messages.append({"role": "assistant", "content": reply})
    engine._finalize_reply(reply)
    return reply


def drive(engine: Any, user_input: str | None) -> str:
    from .gate import DEFAULT_POLICY, gate
    from .resolution import STRATEGIES, detect_turn_intent
    from .solver import solve

    engine.state.last_intent = detect_turn_intent(user_input)
    engine._drive_turns = getattr(engine, "_drive_turns", 0) + 1

    context = engine._build_solver_context(user_input)
    # Anti-repeat nudge: last reply repeated an earlier one — tell the solver the
    # answer is already GIVEN and it must take a DIFFERENT next step.
    if getattr(engine, "_drive_repeats", 0) >= 1:
        context += (
            "\nSVARBU: tavo praėjęs klausimas KARTOJOSI, o klientas jau atsakė ir "
            "patvirtino. PRIIMK tą atsakymą kaip faktą ir ženk KITĄ žingsnį (kita "
            "hipotezė, pasiūlymas ar registracija) — to paties NEBEKLAUSK."
        )
    # A few internal (silent) hops are allowed — reread/pivot re-read the line — before
    # a client-facing action is forced. Hard turn cap escalates rather than looping.
    for _ in range(DEFAULT_POLICY["internal_hops_max"] + 1):
        decision = solve(context, model=engine.config.solver_model or engine.config.model)
        # Normalize the free-form hypothesis to the ACTIVE direction before the
        # gate: the solver words the same belief freely ("routeris sugedęs,
        # nes…"), and the gate then blocked the direction's OWN fix as a
        # "mutation on unmapped hypothesis" — the announced bind never ran
        # (observed: "pririšiu" spoken, update_mac not called). Working the SAME
        # fault in other words is not a new hypothesis; a real pivot names a
        # DIFFERENT known cause, which stays gated.
        if decision is not None and decision.current_hypothesis not in STRATEGIES:
            decision = decision.model_copy(
                update={"current_hypothesis": (engine.state.resolution or {}).get("verdict") or ""}
            )
        conf = decision.confidence if decision else 0.0
        engine._solver_low_conf = (
            engine._solver_low_conf + 1 if conf < DEFAULT_POLICY["confidence_floor"] else 0
        )
        forced = engine._drive_turns > engine._DRIVE_MAX_TURNS
        result = gate(
            decision,
            known_hypotheses=set(STRATEGIES),
            low_conf_streak=engine._solver_low_conf,
            # The REAL per-question cycle count (the same-reply streak) — with a
            # flat 0 here the gate's stuck detector was blind and the solver
            # looped one question 6x (observed live).
            cycles_in_step=(
                engine._DRIVE_MAX_TURNS + 1 if forced else getattr(engine, "_drive_repeats", 0)
            ),
            internal_hops=engine._solver_internal_hops,
        )
        action = result.action
        engine.tracer.emit(
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
            engine._solver_internal_hops += 1
            engine._refresh_diagnosis()  # re-read the line, then decide again
            continue
        engine._solver_internal_hops = 0

        if action == "propose_fix":
            return engine._drive_propose_fix(say, user_input)
        if action == "escalate":
            return engine._drive_escalate(decision)
        if action == "close":
            return close_or_register(engine, say)
        # client-facing: ask / disambiguate / instruct / verify / wait — track the
        # DISTRUST streak so the next turn's nudge/gate/bailout see the loop:
        # a verbatim repeat OR consecutive disambiguates (any wording) count.
        defaults = {
            "verify": "Patikrinkite, prašau, ar internetas jau atsirado.",
            "wait": "Gerai, palauksiu — pasakykite, kai būsite pasiruošę.",
        }
        reply = say or defaults.get(action, "Atsiprašau, ar galėtumėte pakartoti?")
        norm = " ".join(reply.lower().split())
        repeated = norm == getattr(engine, "_drive_last_reply", None)
        re_disambiguate = (
            action == "disambiguate"
            and getattr(engine, "_drive_last_action", None) == "disambiguate"
        )
        if repeated or re_disambiguate:
            engine._drive_repeats = getattr(engine, "_drive_repeats", 0) + 1
        else:
            engine._drive_repeats = 0
        engine._drive_last_reply = norm
        engine._drive_last_action = action
        if repeated:
            # Verbatim repeat still went out — at least SAY why it repeats
            # (Andrius 2026-08-11: the caller must hear the agent knows it
            # is asking the same thing).
            from .identification import phrase

            reply = phrase("repeat_ack") + reply
        return reply
    return "Sekundėlę — patikslinkim dar kartą."


def close_or_register(engine: Any, say: str) -> str:
    """Ticket-first close (Andrius 2026-08-13: 'esmė yra sugedęs routeris ir
    tiketas turi būti registruotas; šalutinis — internetas laikinai'): the
    bridge is TEMPORARY, so a solver 'close' after a successful bridge may not
    end the call without the router-replacement registration — it becomes the
    escalate (live: 'Aš radu internetas' -> close -> ticket=None)."""
    r = engine.state.resolution or {}
    bridged = bool(r.get("telemetry_fixed")) or getattr(engine, "_bridge_bound", False)
    if bridged and not engine.state.ticket_id:
        engine.tracer.emit(
            "drive_decision",
            action="escalate",
            accepted=True,
            reason="close overridden: bridge is temporary — register the router ticket",
        )
        return engine._drive_escalate(None)
    engine.state.case_closed = True
    engine.state.closed_reason = "resolved"
    engine._settle_hypothesis("confirmed", "sprendimas suveikė (solveris)")
    return say or "Puiku, džiaugiuosi, kad sutvarkėme!"


def refresh_diagnosis(engine: Any) -> None:
    """Re-read the line so the solver reasons over CURRENT telemetry (fixes the stale-
    snapshot issue). Keeps the active strategy; only refreshes the signals."""
    engine.state.diagnosis.pop("network", None)
    engine.ensure_diagnosed()


def drive_propose_fix(engine: Any, say: str, user_input: str | None) -> str:
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
    from .react_agent import execute_tool
    from .resolution import detect_plugged

    cid = engine.state.customer_id
    if getattr(engine, "_bridge_bound", False):
        return say or "Įrenginys jau pririštas — patikrinkite, ar internetas atsirado."

    def _device_visible() -> bool:
        # The tool's verdict envelope carries no signals — device presence is read
        # from the REASON: "no_mac_observed" = the line still sees nothing; any
        # other verdict (foreign_mac after the plug-in) = a device is there.
        try:
            d = json.loads(execute_tool("diagnose_connection", {"customer_id": cid}))
            return ((d.get("verdict") or {}).get("reason")) != "no_mac_observed"
        except Exception:  # pragma: no cover - best-effort read
            return False

    # Ledger: the offer question is already answered when the ledger holds
    # has_computer=yes — never re-ask an established fact.
    ev_pc = engine.state.evidence.get("has_computer")
    if ev_pc is not None and ev_pc.get("value") == "yes":
        engine._drive_bridge_offered = True
    # Plug-report MEMORY (round 4, 2026-08-11): the report is remembered
    # across turns — the caller said "Įkišau, laukiu" three turns ago and
    # kept being asked to plug in because each NEW turn no longer contained
    # the plug verb. detect_plugged alone keeps the pre-round-4 unlock (the
    # solver only proposes the fix in the bridge phase).
    if engine._plug_report(user_input) or detect_plugged(user_input):
        engine._bridge_plug_reported = True
    if not getattr(engine, "_bridge_plug_reported", False) and not _device_visible():
        # The work is not done yet — the fix must WAIT for the client. And the
        # FIRST deferral must be the actual TRANSITION + OFFER: live 2026-08-05
        # the solver jumped straight to bind-speak ("pririšiu įrenginį") without
        # ever saying the router is dead or asking about a computer — the caller
        # answered "Apie kokį kompiuterį kalbat?".
        engine.tracer.emit(
            "drive_decision", action="fix_deferred", accepted=False, reason="not plugged yet"
        )
        if not getattr(engine, "_drive_bridge_offered", False):
            engine._drive_bridge_offered = True
            return (
                "Panašu, kad routeris sugedęs — telefonu jo neprikelsime. Galiu "
                "laikinai paleisti internetą per kompiuterį, kol gausite naują "
                "routerį. Ar turite kompiuterį?"
            )
        return "Kai prijungsite kabelį prie kompiuterio, pasakykite — tada pririšiu įrenginį."
    engine._simulate_bridge_connection()
    # Bind only when the line ACTUALLY sees a device now (never blind).
    if not _device_visible():
        engine.tracer.emit(
            "drive_decision", action="fix_deferred", accepted=False, reason="no device observed"
        )
        return engine._bridge_fail_step()
    try:
        obs = execute_tool("update_mac", {"customer_id": cid})
        engine.tracer.emit("tool_call", name="update_mac", args={"customer_id": cid})
        engine._augment_tool_result("update_mac", obs)  # chains reset_port + re-diagnose
        engine._bridge_bound = True
    except Exception as e:
        engine._trace_note("drive_propose_fix", str(e), level="error")
    # Position the walker on the VERIFY step (the step after the bind, read
    # structurally) — the reply below asks "ar internetas atsirado?", so the
    # caller's "jau atsistatė!" must route as RESTORED. Live 2026-08-12 the
    # walker sat on a stale instruct step and the success died unheard: the
    # call drifted into ticket talk over a WORKING line.
    from .resolution import get_strategy, next_step_id

    r = engine.state.resolution or {}
    strat = get_strategy(r.get("verdict"))
    if strat and strat.step("dr_bind"):
        target = next_step_id(strat, "dr_bind", None)
        if strat.step(target) is not None and r.get("step") != target:
            engine._goto_step(r, target)
            r["asked"] = True  # the verify question goes out in THIS reply
            r["asked_at"] = len(engine.state.messages) + 1
            engine.tracer.emit(
                "decision", intent="evidence", action="pivot", to=target, reason="bind verify"
            )
    return say or "Matau jūsų kompiuterį linijoje — pririšau. Patikrinkite, ar internetas atsirado."


def bridge_fail_step(engine: Any) -> str:
    """The plug is REPORTED but telemetry still sees nothing — a declared
    failure ladder instead of the same re-check forever (Andrius
    2026-08-12): (1) say the line does not see the device, re-check the
    cable; (2) check the COMPUTER's network card (lan_active — the answer
    lands on the ledger); (3) name the possible incoming-cable problem and
    register the technician, with what-was-tried on the ticket."""
    from .evidence import LABELS, VALUE_LT, fault_bridge_fail, spec_for

    verdict = (engine.state.resolution or {}).get("verdict")
    stage = getattr(engine, "_bridge_fail_stage", 0)
    if stage == 0:
        engine._bridge_fail_stage = 1
        return (
            "Kol kas linijoje dar nematome jūsų kompiuterio — patikrinkite, ar "
            "kabelis įkištas iki galo, ir pasakykite."
        )
    if stage == 1:
        engine._bridge_fail_stage = 2
        spec = spec_for(verdict) or {}
        item = (spec.get("client") or {}).get("lan_active") or {}
        # The answer reads against THIS key (pending machinery, universal).
        engine._evidence_last_ask_key = "lan_active"
        engine._evidence_asks["lan_active"] = engine._evidence_asks.get("lan_active", 0) + 1
        engine.tracer.emit("drive_decision", action="bridge_fail_lan_check", accepted=True)
        return str(
            item.get("klausimas")
            or "Tinkle vis dar nesimato jūsų įrenginio. Ar kompiuterio tinklo (LAN) "
            "ryšys rodomas kaip aktyvus?"
        )
    # Stage 2+: LAN answered (or unreadable) and the line is still empty —
    # the technician takes it from here; the attempt goes on the ticket.
    texts = fault_bridge_fail(verdict)
    lan = (engine.state.evidence.get("lan_active") or {}).get("value") or "nepatikrinta"
    engine._bridge_fail_note = (
        texts.get("prierasas")
        or "Laikinai pajungti internetą per kompiuterį NEPAVYKO (LAN: {lan})."
    ).format(lan=VALUE_LT.get(lan, lan))
    engine.tracer.emit(
        "drive_decision",
        action="bridge_fail_escalate",
        accepted=True,
        reason=f"{LABELS.get('lan_active')}: {lan}",
    )
    pastaba = texts.get("pastaba") or "Įrenginio linijoje vis dar nesimato."
    return pastaba + " " + engine._drive_escalate(None)


def drive_escalate(engine: Any, decision) -> str:
    """Register the fault and close — through the SAME state-built ticket machinery
    as everywhere else (its ad-hoc create_ticket used to write a raw verdict key as
    the details, lose ticket_id from the record, and then ASK permission for a
    ticket it had already created — observed live). The announce is deterministic:
    the ticket exists, so the words state a fact, never ask."""
    from .resolution import get_strategy

    s = engine.state
    r = s.resolution or {}
    strat = get_strategy(r.get("verdict"))
    # The bridge already restored internet on the PC -> this is the
    # register-router shape (temporary bridge note rides on the ticket).
    bridged = bool(r.get("telemetry_fixed")) or getattr(engine, "_bridge_bound", False)
    step = None
    if strat is not None:
        step = strat.step("dr_register_router") if bridged else strat.step("escalate")
        if step is None:
            step = strat.step("escalate")
    if not r.get("escalate_reason"):
        r["escalate_reason"] = "Sprendimas telefonu nepavyko."
    # Contacts first (2026-08-04): the dialogue collects the number + hours, then
    # _finish_ticket_dialogue registers and closes. The bridged note rides on the
    # final announce via the ctx.
    engine._begin_ticket_dialogue(step)
    if engine._ticket_ctx is not None and bridged:
        engine._ticket_ctx["note"] = (
            " Internetas kol kas veiks per kompiuterį; kai turėsite naują routerį, "
            "paskambinkite — pririšime, ir veiks visi namai."
        )
    return engine._ticket_stage_reply()

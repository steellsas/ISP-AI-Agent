"""How a tool result reaches the conversation: the playbook injection trace, the
step-presented bookkeeping, the result narration tail, and the state updates an
observation causes. What the speaker SEES lives in agent/speak/ (M5).
"""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import logging
import os  # noqa: F401
import re  # noqa: F401
from typing import Any  # noqa: F401

from .contract.locale import phrase_or, vocab

logger = logging.getLogger(__name__)


def emit_rag_injection(state, rt, doc: str | None, section: int, step_id: str, text: str) -> None:
    """Emit a `rag` trace event when a playbook section is injected for a step —
    deduped on (doc, section, step) so the multi-call turn (LLM + tool follow-up)
    logs it once, and a step change logs the new section."""
    key = [doc, section, step_id]
    if state.dialog.last_rag_injection_key == key:
        return
    state.dialog.last_rag_injection_key = key
    preview = " ".join((text or "").split())[:90]
    rt.tracer.emit("rag", doc=doc, section=section, step=step_id, preview=preview)


def mark_step_presented(state, rt) -> None:
    """After the agent replies while on a strategy step, record that the step's
    message (a CONFIRM question, an INSTRUCT instruction, or the ACTION announce)
    has now been presented — so the caller's NEXT reply advances the walker."""
    state.diagnosis.pivoted_from = None  # the rethink has now been said — say it once
    s = state
    # Identification ladder bookkeeping: while the caller-intro question is owed,
    # the strategy step's question was NOT asked this reply — do not mark it. Once
    # the caller introduced themselves and the RESULT was narrated, the deferral
    # closes (inform news counted as told).
    if s.identity.customer_id and state.identity.result_pending:
        if not s.identity.caller_name:
            return  # the reply asked WHO is calling — nothing else was presented
        state.identity.result_pending = False
        if s.resolution.procedure is None:
            state.diagnosis.news_delivered = True
    r = state.resolution.procedure
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
        r["asked_at"] = len(state.messages)
        # B-wave registry (shadow): the step's question/instruction was just
        # presented — it is now the walker's active question. Live 2026-09-08:
        # the end-confirm and wrap-up replies are NOT the step's question, so
        # they must not re-register it (asks inflated to 5 on a solved call).
        from .decide.question import active as _q_active
        from .decide.question import clear_owner as _q_clear_owner
        from .decide.question import register as _q_register

        _q = _q_active(state, rt)
        if state.dialog.end_confirm_pending:
            pass  # this reply asked the end-confirm question, not the step's
        elif _q is not None and _q.owner == "safety":
            # Live 2026-09-09 (N1): the reply just asked a SAFETY question
            # (cannot-now clarify) — clobbering it with the step let the
            # refuse guard consume the clarify ANSWER and start a ticket.
            pass
        elif state.closing.case_closed:
            _q_clear_owner(state, rt, "walker")  # the case is over — wrap-up owns the turns
        else:
            _q_register(state, rt, "walker", f"step:{step.id}")
        # Presentation counter (L2): a step presented the 2nd+ time gets the
        # ŽINGSNIS KARTOJAMAS directive — repeat WITH an explanation.
        counts = r.setdefault("presented", {})
        counts[step.id] = counts.get(step.id, 0) + 1


def augment_resolve_result(state, rt, observation: str) -> str:
    """Identification just landed — diagnose in the SAME turn.

    Otherwise the identification turn has nothing real left to say (the address is
    already confirmed) and the model fills the gap: it invents "nėra žinomų
    gedimų", asks "kokie įrenginiai prijungti?", and a debtor only hears about the
    debt a turn later — or the caller goes quiet and the call stalls before any
    diagnosis. Running it here lets ONE reply confirm the address and deliver the
    finding."""
    from .execute.diagnosis import ensure_diagnosed

    try:
        obs = json.loads(observation)
    except (TypeError, ValueError):
        return observation
    if not obs.get("success") or not state.identity.customer_id:
        return observation
    if not ensure_diagnosed(state, rt):
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
    obs["message"] = (obs.get("message", "") or "").strip() + result_narration_tail(state, rt)
    return json.dumps(obs, ensure_ascii=False)


def _result_question(state) -> str:
    """The one question the result turn ends with: the first thing still MISSING from
    the ledger, or this step's own question when the ledger is silent."""
    from .evidence import open_goals_lt

    verdict = (state.resolution.procedure or {}).get("verdict")
    goals = open_goals_lt(state.diagnosis.evidence, verdict) if verdict else ""
    first = next((g.strip() for g in goals.split(";") if g.strip()), "")
    if first:
        return f"užduok klausimą apie: {first} (jis atlieka „ar darome?“ vaidmenį)."
    return "užduok ŠIO ŽINGSNIO klausimą (jis atlieka „ar darome?“ vaidmenį)."


def result_narration_tail(state, rt) -> str:
    """The narration directive once the identity has committed and the silent
    diagnose ran. Identification LADDER (2026-07-31): if the caller-intro question
    is still owed (WHO is calling — name + relation, for the record), ask THAT
    first and hold the result one turn (identity.result_pending); otherwise narrate the
    check announce + the REAL result in this one reply (arc v3)."""
    from .identification import ask_caller, caller_question

    if ask_caller() and not state.identity.caller_name:
        state.identity.result_pending = True
        return (
            " Identifikacijos pabaiga: patikra atlikta TYLIAI, bet rezultato dar "
            f"NESAKYK. Šiame atsakyme TIK: „{caller_question()}“ (galima trumpai "
            "patvirtinti adresą prieš klausimą). Jokio rezultato, jokių instrukcijų."
        )
    d = state.diagnosis.verdicts.get("network") or {}
    gloss = phrase_or(f"verdict.{d.get('reason')}.gloss", d.get("reason") or "—")
    if state.resolution.procedure:
        # F-11: what the caller already told us is on the ledger by now (the pack's
        # activation seeds it from the whole call), so the question is the first OPEN
        # goal — asking the pack's first question regardless re-asked "visuose ar tik
        # viename?" right after the caller opened with "neveikia visuose įrenginiuose".
        return (
            f" Patikra atlikta. REZULTATAS: {gloss}. Šiame VIENAME atsakyme, šia "
            "tvarka: (1) 'Patikrinsiu būseną šiuo adresu… Patikrinau:' (2) trumpai "
            f"pasakyk rezultatą ir kas tai greičiausiai yra, (3) {_result_question(state)} "
            "NEkartok adreso klausimo, NEkartok anamnezės klausimo, jokių instrukcijų "
            "sąrašo — vienas klausimas."
        )
    state.diagnosis.news_delivered = True  # the news goes out in THIS reply — never repeat it
    return (
        f" Patikra atlikta. ŽINIA: {gloss}. Šiame VIENAME atsakyme, šia tvarka: "
        "(1) 'Patikrinsiu būseną šiuo adresu… Patikrinau:' (2) pasakyk žinią "
        "VIENĄ kartą trumpai (jei skola — BŪTINAI pridėk: „apmokėjus sąskaitą, "
        "paslauga bus įjungta“), (3) paklausk „Ar dar kuo galiu padėti?“. "
        "NEkartok adreso klausimo ir daugiau šios žinios NEBEKARTOK."
    )


def augment_tool_result(state, rt, name: str, observation: str) -> str:
    """Deterministic post-action chaining + telemetry verification (B6 strategy).

    update_mac ALONE does not restore service — the port must be reset and the
    line re-checked. Rather than trust the model to remember the whole sequence
    (observed: it bound nothing and closed on the caller's word), the engine
    chains it: after a successful update_mac it runs reset_port and re-reads the
    telemetry, and hands the model a VERIFIED outcome to narrate (what the
    provider side actually shows, not what the caller claims)."""
    from .execute.diagnosis import fresh_diagnose_reason

    if name == "resolve_address":
        return augment_resolve_result(state, rt, observation)
    if name != "update_mac":
        return observation
    try:
        obs = json.loads(observation)
    except (TypeError, ValueError):
        return observation
    if not obs.get("success"):
        return observation  # nothing bound (e.g. no_observed_mac) — leave as is
    cid = state.identity.customer_id
    try:
        rp = rt.tools.run(
            state, rt, "reset_port", {"customer_id": cid}, reason="reset_after_bind", apply=False
        ).data
        obs["auto_reset_port"] = bool(rp.get("success"))
    except Exception:  # pragma: no cover - best-effort
        obs["auto_reset_port"] = None
    reason_now = fresh_diagnose_reason(state, rt)
    from .faults import verdict_flag

    fixed = not verdict_flag(reason_now, "unresolved_after_fix")
    obs["telemetry_after"] = reason_now
    obs["fixed"] = fixed
    gloss = phrase_or(f"verdict.{reason_now}.gloss", reason_now or "—")

    # Do NOT close or advance here. The bind was announced THIS turn; the walker
    # advances bind_device -> verify_restored on the caller's next reply, where we
    # ASK them and re-read telemetry before deciding resolve / client-side /
    # escalate (_advance_restored). Just record the telemetry reading.
    r = state.resolution.procedure
    if r is not None:
        r["telemetry_fixed"] = fixed
    obs["message"] = (
        obs.get("message", "") or ""
    ).strip() + f" Portas perkrautas. Telemetrija dabar: {gloss}."
    return json.dumps(obs, ensure_ascii=False)


def update_state_from_observation(state, rt, action: str, observation: str):
    """Update agent state based on tool observation."""
    from .decide.hypothesis import activate_hypothesis

    try:
        obs_data = json.loads(observation)

        # Fold the per-level address resolution into the durable slots on
        # EVERY resolve_address call (success or not) — what the caller said
        # accumulates as structured memory, protected from low-confidence
        # overwrites (slots.Slot.propose).
        if action == "resolve_address" and isinstance(obs_data.get("resolution"), dict):
            state.identity.profile.update_from_resolution(obs_data["resolution"])
            # F2 (2026-08-20): a failed lookup speaks its DIAGNOSIS — what was
            # found and what was not — so the caller can correct themselves
            # ("Vilniaus gatvę randu, bet 39 numerio nematau").
            if not obs_data.get("success"):
                from .execute.identification import address_diag_note

                state.turn.address_lookup_note = address_diag_note(obs_data)
                res_levels = obs_data.get("resolution") or {}
                street_lvl = res_levels.get("street") or {}
                # HONEST not-exists (Andrius 2026-09-10 rev.2): every failed
                # street reading lands on the attempt tracker; the SAME
                # transcript coming back means the agent heard RIGHT and the
                # street simply is not served — say so instead of pushing
                # codes/letters at a correctly-heard address.
                _given = str(street_lvl.get("given") or "")
                if _given and street_lvl.get("status") not in (None, "ok", "not_in_city"):
                    from .decide.rules.identification import _register_street_attempt

                    if (
                        _register_street_attempt(state, rt, _given) == "identical"
                        and not state.identity.street_not_exists_said
                    ):
                        state.identity.street_not_exists_due = True
                # Vietovės PASIŪLYMAS (T-5, 2026-09-04): „Žeimių g. yra
                # Ginkūnuose" — įsimenam siūlomą vietovę; klientui patvirtinus
                # miesto slotas persijungia (prefill vielos) ir paieška vyksta
                # TEN. Tikslinimas NĖRA bandymas — fails nekeliam.
                elsewhere = street_lvl.get("found_elsewhere") or []
                if street_lvl.get("status") == "not_in_city" and elsewhere:
                    state.identity.suggested_city = elsewhere[0].get("city")
                # №2 (perdirbta 2026-09-04): nesėkme laikoma tik GATVĖS/NAMO
                # lygmens fiasko; „trūksta buto/pavardės" ar vietovės
                # pasiūlymas — tikslinimas, ne nesėkmė.
                house_lvl = res_levels.get("house") or {}
                apt_lvl = res_levels.get("apartment") or {}
                clarification = (
                    street_lvl.get("status") == "not_in_city"
                    or apt_lvl.get("status") == "required"
                    or any(
                        w in str(obs_data.get("hint") or "").lower() for w in vocab("surname_words")
                    )
                )
                if not clarification and (
                    street_lvl.get("status") not in (None, "ok")
                    or house_lvl.get("status") not in (None, "ok")
                ):
                    state.identity.address_resolve_failures = (
                        state.identity.address_resolve_failures + 1
                    )
            else:
                state.turn.address_lookup_note = None
                state.identity.suggested_city = None
                # B-wave registry: identification committed on ANY successful
                # resolve (the LLM's own tool call included) — the ident
                # question must never outlive it and freeze the walker.
                from .decide.question import clear_owner as _q_clear_owner

                _q_clear_owner(state, rt, "ident")
                state.identity.address_resolve_failures = 0

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
                state.identity.set_customer(
                    customer_id=profile.get("customer_id"),
                    name=profile.get("name"),
                    address=primary.get("full_address"),
                )

        elif action == "create_ticket" and obs_data.get("success"):
            state.ticket.ticket_id = obs_data.get("ticket_id")
            # Inside a resolution strategy (escalate step), the fault is now
            # registered — close the case so create_ticket is withdrawn and the
            # model narrates the close instead of re-registering in a loop.
            if state.resolution.procedure and not state.closing.case_closed:
                state.closing.case_closed = True
                state.closing.closed_reason = "registered"

        # Diagnostic findings -> case state under their DOMAIN, so the agent
        # reconciles them with the customer and never loses / re-runs them, and
        # new fault families attach additively (§12.1).
        if action == "diagnose_connection" and isinstance(obs_data.get("verdict"), dict):
            v = obs_data["verdict"]
            state.diagnosis.verdicts["network"] = {
                "group": v.get("group"),
                "side": v.get("side"),
                "action": v.get("action"),
                "reason": v.get("reason"),
                # Live 2026-09-09 (the debt template rendered its FALLBACK):
                # signals ride at the payload's TOP level, not inside the
                # verdict — v.get("signals") was always None, so billing_debt
                # (and the solver's telemetry facts) never reached the state.
                "signals": obs_data.get("signals") or v.get("signals"),
            }
            # Ledger: telemetry facts are ground truth — every (re)diagnose
            # lands on the evidence with full history (a re-check after a fix
            # OVERWRITES the value; the caller's words never do).
            from .evidence import TELEMETRY, set_fact

            turn = state.dialog.turn_count
            if v.get("reason"):
                set_fact(state.diagnosis.evidence, "verdict", v["reason"], TELEMETRY, turn)
            if v.get("side"):
                set_fact(state.diagnosis.evidence, "side", v["side"], TELEMETRY, turn)
            # Activate the resolution strategy for this verdict. A procedure already
            # running on another cause is NOT switched (D-05): the recheck only puts
            # the belief in doubt, and the caller confirms the new symptom first
            # (decide/rules/hypothesis_confirm). None = generic inform/instruct flow.
            from .resolution import get_strategy

            strat = get_strategy(v.get("reason"))
            prev = (state.resolution.procedure or {}).get("verdict")
            # Never pivot back into a hypothesis the telemetry already disproved —
            # that is how a re-diagnose after a failed fix would loop forever.
            if strat is not None and strat.verdict not in state.diagnosis.failed_hypotheses:
                if prev is None:
                    # A verdict IS a hypothesis — record what we now believe and why,
                    # so the agent can say it aloud and later report how it settled.
                    activate_hypothesis(state, rt, v.get("reason"))
                    state.resolution.procedure = {
                        "verdict": strat.verdict,
                        "step": strat.steps[0].id,
                    }
                elif prev != strat.verdict:
                    from .decide.hypothesis import doubt

                    doubt(state, rt, "verdict", "verdict", prev, strat.verdict, source="telemetry")
            elif prev is None:
                activate_hypothesis(state, rt, v.get("reason"))

        # An active outage for the caller's street -> restricted mode (NOT a
        # close): the caller still asks "when fixed? / compensation?", so the
        # agent stays in a tool-having node but stops diagnosing (facts block).
        # By the gate, a returned `affected` here is already street-specific.
        if action == "check_outages" and obs_data.get("affected"):
            state.diagnosis.outage_reported = True

        # close_case signal -> flip the router to the closing stage. The model
        # owns WHEN (it read the caller's confirmation); the gate already
        # backstopped premature/unfounded closes.
        if action == "close_case" and obs_data.get("case_closed"):
            state.closing.case_closed = True
            state.closing.closed_reason = obs_data.get("reason")

    except json.JSONDecodeError:
        pass

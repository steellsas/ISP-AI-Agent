"""What a tool result does to the call.

The gateway commits the raw observation; these functions read it the way the engine
needs it: a resolve/lookup result becomes the identification's note, a fix action chains
its verification, and a diagnose observation lands the verdict, the ledger facts and the
belief (a new cause under an active procedure becomes a contradiction, never a silent
switch — D-05)."""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import os  # noqa: F401
import re  # noqa: F401
from typing import Any  # noqa: F401

from ..contract.locale import phrase_or, vocab


def augment_resolve_result(state, rt, observation: str) -> str:
    """Identification just landed — diagnose in the SAME turn.

    Otherwise the identification turn has nothing real left to say (the address is
    already confirmed) and the model fills the gap: it invents "nėra žinomų
    gedimų", asks "kokie įrenginiai prijungti?", and a debtor only hears about the
    debt a turn later — or the caller goes quiet and the call stalls before any
    diagnosis. Running it here lets ONE reply confirm the address and deliver the
    finding."""
    from ..execute.diagnosis import ensure_diagnosed

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
    from ..speak.context_card import result_narration_tail

    obs["message"] = (obs.get("message", "") or "").strip() + result_narration_tail(state, rt)
    return json.dumps(obs, ensure_ascii=False)


def augment_tool_result(state, rt, name: str, observation: str) -> str:
    """Deterministic post-action chaining + telemetry verification (B6 strategy).

    update_mac ALONE does not restore service — the port must be reset and the
    line re-checked. Rather than trust the model to remember the whole sequence
    (observed: it bound nothing and closed on the caller's word), the engine
    chains it: after a successful update_mac it runs reset_port and re-reads the
    telemetry, and hands the model a VERIFIED outcome to narrate (what the
    provider side actually shows, not what the caller claims)."""
    from ..execute.diagnosis import fresh_diagnose_reason

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
    from ..faults import verdict_flag

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
    from ..decide.hypothesis import activate_hypothesis

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
                from ..execute.identification import address_diag_note

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
                    from ..decide.rules.identification import _register_street_attempt

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
                from ..decide.question import clear_owner as _q_clear_owner

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
                    services=profile.get("services"),
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
            from ..evidence import TELEMETRY, set_fact

            turn = state.dialog.turn_count
            if v.get("reason"):
                set_fact(state.diagnosis.evidence, "verdict", v["reason"], TELEMETRY, turn)
            if v.get("side"):
                set_fact(state.diagnosis.evidence, "side", v["side"], TELEMETRY, turn)
            # Activate the resolution strategy for this verdict. A procedure already
            # running on another cause is NOT switched (D-05): the recheck only puts
            # the belief in doubt, and the caller confirms the new symptom first
            # (decide/rules/hypothesis_confirm). None = generic inform/instruct flow.
            from ..resolution import get_strategy

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
                    from ..decide.hypothesis import doubt

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

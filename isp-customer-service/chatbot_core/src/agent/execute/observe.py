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


def chain_after_bind(state, rt, name: str, observation: str) -> str:
    """The bind's own chain: update_mac ALONE does not restore service — the port must be
    reset and the line re-checked, and the narrator is handed a VERIFIED outcome (what
    the provider side shows, not what the caller claims; it used to bind nothing and
    close on the caller's word).

    Wave 1b: this is the only chaining left in the observation path, and the two places
    that bind call it explicitly. A hidden resolve -> diagnose chain lived here too; the
    identification rule decides that itself now."""
    from ..execute.diagnosis import fresh_diagnose_reason

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
                    open_tickets=profile.get("open_tickets"),
                )

        elif action == "create_ticket" and obs_data.get("success"):
            state.ticket.ticket_id = obs_data.get("ticket_id")
            # Inside a resolution strategy (escalate step), the fault is now
            # registered — close the case so create_ticket is withdrawn and the
            # model narrates the close instead of re-registering in a loop.
            if state.resolution.procedure and not state.closing.case_closed:
                from ..closing import close_call

                close_call(state, rt, "registered")

        # Diagnostic findings -> case state under their DOMAIN, so the agent
        # reconciles them with the customer and never loses / re-runs them, and
        # new fault families attach additively (§12.1).
        if action == "diagnose_connection":
            # Wave 3: the reading becomes FACTS (knowledge/signals.yaml) and the fault
            # cards reason over them. The verdict below is the v1 path, still running.
            from ..ledger import record_telemetry

            record_telemetry(state, rt, obs_data.get("signals"))
            # The raw reading stays available for the inform templates (a debt's amount, an
            # outage's ETA) and for the equipment catalogue (the caller's model).
            network = state.diagnosis.verdicts.setdefault("network", {})
            network["signals"] = obs_data.get("signals") or network.get("signals")

        # An active outage for the caller's street -> restricted mode (NOT a
        # close): the caller still asks "when fixed? / compensation?", so the
        # agent stays in a tool-having node but stops diagnosing (facts block).
        # By the gate, a returned `affected` here is already street-specific.
        if action == "check_outages" and obs_data.get("affected"):
            state.diagnosis.outage_reported = True

    except json.JSONDecodeError:
        pass

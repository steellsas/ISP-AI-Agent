"""
Executor flow — the ONLY place tools run and tickets are registered.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of
ReactAgent — the deterministic tool-access gate, the gated tool-call loop,
the STATE-driven idempotent ticket registration and the demo bridge
simulation. Functions take the engine explicitly; execute_tool is imported
lazily from react_agent so the tests' import-fallback stubs keep working.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def gate_tool(engine: Any, name: str, args: dict) -> str | None:
    """
    Deterministic tool-access gate.

    Returns a corrective observation (JSON string) when a technical tool is
    called before identification, or with a customer_id that is not the
    identified one — otherwise None (the call proceeds). This moves the "no
    diagnostics before identification" / "never act on a guessed id" rules
    out of the prompt and into code, so a hallucinated `diagnose_connection`
    cannot fire (observed: customer_id='1' on an unidentified caller).
    """
    # check_outages must be street-specific. A city-only query returns OTHER
    # streets' outages, which the model then misattributes to the caller
    # (observed). Require a street (area="Miestas, Gatvė") OR a customer_id —
    # the house/apartment is NOT required (street-level check is valid pre-house).
    if name == "check_outages":
        area = (args.get("area") or "").strip()
        if area and "," not in area and not args.get("customer_id"):
            return json.dumps(
                {
                    "success": False,
                    "error": "city_only",
                    "message": (
                        "check_outages reikalauja gatvės: perduok area='Miestas, "
                        "Gatvė' (ne vien miestą) arba customer_id. Tik-miesto "
                        "patikra grąžina kitų gatvių gedimus."
                    ),
                },
                ensure_ascii=False,
            )
        return None

    # close_case: reason-specific backstop so an over-eager model can't end the
    # call prematurely. "resolved" needs an identified customer; "outage" needs
    # an outage to have actually been reported.
    if name == "close_case":
        reason = args.get("reason", "resolved")
        if reason == "resolved":
            if not engine.state.customer_id:
                return json.dumps(
                    {
                        "success": False,
                        "error": "not_identified",
                        "message": "Negalima uždaryti kaip 'resolved' neidentifikavus kliento.",
                    },
                    ensure_ascii=False,
                )
            # Verify-gate: telemetry is the source of truth. If a fresh
            # diagnose still shows the line fault, the fix has NOT taken —
            # block "resolved" so the agent can't close on the caller's word
            # (observed: B6 closed as resolved without ever binding the MAC).
            reason_now = engine._fresh_diagnose_reason()
            if reason_now in engine._UNRESOLVED_LINE_FAULTS:
                from .glossary import DIAGNOSIS_LT

                gloss = DIAGNOSIS_LT.get(reason_now, reason_now)
                return json.dumps(
                    {
                        "success": False,
                        "error": "not_fixed",
                        "message": (
                            f"Telemetrija dar rodo gedimą ({gloss}) — dar NEsutvarkyta, "
                            "neuždaryk kaip 'resolved'. Atlik reikiamą veiksmą (pvz. "
                            "update_mac + reset_port) ir per-tikrink diagnostiką."
                        ),
                    },
                    ensure_ascii=False,
                )
        if reason == "outage" and not engine.state.outage_reported:
            return json.dumps(
                {
                    "success": False,
                    "error": "no_outage",
                    "message": (
                        "close_case(reason='outage') leidžiama tik po to, kai "
                        "check_outages patvirtino aktyvų gedimą."
                    ),
                },
                ensure_ascii=False,
            )
        return None

    if name not in engine._GATED_TOOLS:
        return None
    if not engine.state.customer_id:
        return json.dumps(
            {
                "success": False,
                "error": "not_identified",
                "message": (
                    "Klientas dar neidentifikuotas. Pirma surask ir patvirtink "
                    "adresą (resolve_address) — tik tada galima diagnozė ar veiksmai."
                ),
            }
        )
    cid = args.get("customer_id")
    if cid and cid != engine.state.customer_id:
        return json.dumps(
            {
                "success": False,
                "error": "id_mismatch",
                "message": (
                    f"customer_id turi būti identifikuoto kliento: "
                    f"{engine.state.customer_id}. Nenaudok kito ar spėto id."
                ),
            }
        )
    return None


def execute_tool_calls(engine: Any, message: Any) -> list[dict]:
    """Echo the assistant tool-call message, run each tool through the gate,
    append results to history, trace, and update state. Returns the executed
    list. Shared by step() (non-streaming) and the streaming loop."""
    from .react_agent import execute_tool

    engine.state.messages.append(engine._assistant_tool_message(message))
    executed = []
    for tc in message.tool_calls:
        name = tc.function.name
        raw_args = tc.function.arguments or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            logger.warning(f"[AGENT] Bad tool arguments for {name}: {raw_args!r}")
            engine._trace_note("tool_args", f"{name}: bad JSON args {raw_args!r}")
            args = {}

        logger.info(f"[AGENT] Tool call: {name}")
        engine.tracer.emit("tool_call", name=name, args=args)

        gate = gate_tool(engine, name, args)
        if gate is not None:
            observation, tool_ms = gate, 0
            engine._update_state_from_observation(name, observation)
        else:
            _t = time.perf_counter()
            observation = execute_tool(name, args)
            tool_ms = round((time.perf_counter() - _t) * 1000.0)
            # Commit state BEFORE augmenting: resolve_address sets customer_id
            # here, and the augment then diagnoses in the same turn (it read a
            # not-yet-committed id and skipped, so the strategy never activated —
            # the whole dead-router walk fell back to free-form LLM). _update reads
            # only raw tool fields, never the ones augment adds, so the order is safe.
            engine._update_state_from_observation(name, observation)
            observation = engine._augment_tool_result(name, observation)

        engine.state.messages.append(
            {"role": "tool", "tool_call_id": tc.id, "content": observation}
        )
        engine._trace_tool_result(name, observation, tool_ms)
        engine.state.add_observation(observation)
        executed.append({"name": name, "arguments": args, "observation": observation})
    return executed


def register_ticket_from_state(engine: Any, step) -> None:
    """Build + create the ticket DETERMINISTICALLY from state (Phase 3.10/3.11 B):
    cause from the hypothesis/verdict, actions from this call's trace — never from
    the model's free text (which once invented an invalid ticket_type). Idempotent:
    an existing ticket is never duplicated. Best-effort: a failure is traced and the
    close still proceeds (the call record keeps the outcome)."""
    from .glossary import DIAGNOSIS_LT, TICKET_NEED_LT
    from .react_agent import execute_tool

    s = engine.state
    if s.ticket_id or not s.customer_id:
        return
    cause = (s.hypothesis or {}).get("cause") or (s.resolution or {}).get("verdict") or ""
    gloss = DIAGNOSIS_LT.get(cause, cause or "nenustatyta")
    details = f"Gedimas: {s.problem_type or 'internetas'} — {gloss}."
    need = TICKET_NEED_LT.get(cause)
    if need:
        # Sentence-cased as its own sentence — "Reikalinga: reikalingas…" doubled up.
        details += f" {need[0].upper()}{need[1:]}."
    # Bridge attempt outcome (2026-08-12): the technician reads WHAT was
    # already tried — "pajungti PC nepavyko (LAN aktyvus)" changes what
    # they bring and check first.
    if getattr(engine, "_bridge_fail_note", None):
        details += f" {engine._bridge_fail_note}"
    # Contacts from the ticket dialogue (2026-08-04): who to reach and when.
    if s.contact_phone or s.caller_name:
        kas = s.caller_name or "skambinęs asmuo"
        rel = f" ({s.caller_relation})" if s.caller_relation else ""
        details += f" Kontaktas: {kas}{rel}, tel. {s.contact_phone or s.caller_phone}"
        if s.contact_hours:
            details += f", skambinti: {s.contact_hours}"
        details += "."
    # The caller's anamnesis rides on the ticket — the human sees WHEN it broke
    # and after what, not just the telemetry verdict (Step 2 analysis).
    if s.anamnesis_when or s.anamnesis_trigger or s.anamnesis_raw:
        bits = []
        if s.anamnesis_when:
            bits.append(f"dingo {s.anamnesis_when}")
        if s.anamnesis_trigger:
            bits.append(f"po: {s.anamnesis_trigger}")
        details += f" Klientas: {', '.join(bits) if bits else s.anamnesis_raw}."
    if step is not None and step.id == "dr_register_router":
        details += " Laikinas tiltas per kompiuterį veikia; routeris sugedęs, reikia keisti."
    # Ledger: what the CALLER established (client-side evidence) — the human
    # taking over sees the checked physical facts, not just telemetry.
    client_bits = []
    from .evidence import CLIENT as _EV_CLIENT
    from .evidence import LABELS as _EV_LABELS
    from .evidence import VALUE_LT as _EV_VALUES

    for key, e in s.evidence.items():
        if e.get("source") == _EV_CLIENT and not e.get("conflict"):
            client_bits.append(
                f"{_EV_LABELS.get(key, key)}: {_EV_VALUES.get(e['value'], e['value'])}"
            )
    if client_bits:
        details += f" Patikrinta su klientu: {'; '.join(client_bits)}."
    # Why it was not solved (refusal / demand / not home) — recorded on the ticket
    # so the technician knows the context (policy 2026-07-30).
    reason_note = (s.resolution or {}).get("escalate_reason")
    if reason_note:
        details += f" {reason_note}"
    # What was already TRIED and ruled out — the human taking over must not redo
    # it (after-hours philosophy 2026-08-03: the agent attempts, a person takes
    # over via the ticket with the full attempt history).
    tried = list(s.failed_hypotheses) + [
        x.get("cause") for x in s.rejected_hypotheses if x.get("cause")
    ]
    if tried:
        glosses = ", ".join(DIAGNOSIS_LT.get(c, c) for c in dict.fromkeys(tried))
        details += f" Bandyta/atmesta: {glosses}."
    # A (2026-08-21): secondary problems the caller mentioned mid-call — the
    # technician checks them on the same visit.
    if getattr(s, "secondary_problems", None):
        extra = "; ".join(f"{x['tipas']}: „{x['tekstas']}“" for x in s.secondary_problems)
        details += f" Papildomai patikrinti: {extra}."
    actions = engine._tools_called_this_session()
    args = {
        "customer_id": s.customer_id,
        "problem_type": "technician_visit",
        "problem_description": details,
        "priority": "high",
        "notes": ("Atlikta: " + ", ".join(actions)) if actions else "",
    }
    try:
        engine.tracer.emit("tool_call", name="create_ticket", args={"customer_id": s.customer_id})
        obs = execute_tool("create_ticket", args)
        engine._trace_tool_result("create_ticket", obs)
        engine._update_state_from_observation("create_ticket", obs)  # sets ticket_id
    except Exception as e:  # pragma: no cover - defensive
        engine._trace_note("register_ticket", str(e), level="error")


def simulate_router_reboot_action(engine: Any) -> None:
    """DEMO/TEST only (SIMULATE_REBOOT=on): reflect the caller power-cycling the
    router (S6) — the demo port flaps and traffic returns, so the reboot-check
    telemetry read sees what a real reboot produces. Off by default → live demo
    calls use the „Perkrauti routerį" button instead (the human plays the
    physical world); production sees the real flap on its own."""
    if os.getenv("SIMULATE_REBOOT", "off").lower() != "on":
        return
    cid = engine.state.customer_id
    if not cid:
        return
    try:
        from .tools import simulate_router_reboot

        res = simulate_router_reboot(cid)
        engine.tracer.emit("tool_call", name="simulate_router_reboot", args={"customer_id": cid})
        if isinstance(res, dict) and res.get("success"):
            engine._note_evidence("klientas perkrovė routerį — portas mirktelėjo (simuliuota)")
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning(f"router reboot sim failed: {e}")
        engine._trace_note("reboot_sim", str(e))


def simulate_bridge_connection(engine: Any) -> None:
    """DEMO/TEST only (SIMULATE_BRIDGE=on): reflect the caller plugging a PC into the
    wall cable by making an unbound device appear on the line, so the bridge can
    VERIFY it. Off by default → production never fakes a device (the real one appears
    on its own). Best-effort: a failure just leaves the line unchanged."""
    if os.getenv("SIMULATE_BRIDGE", "off").lower() != "on":
        return
    cid = engine.state.customer_id
    if not cid:
        return
    try:
        from .tools import simulate_bridge_connect

        res = simulate_bridge_connect(cid)
        engine.tracer.emit("tool_call", name="simulate_bridge_connect", args={"customer_id": cid})
        if isinstance(res, dict) and res.get("success"):
            engine._note_evidence("klientas prijungė įrenginį — matomas linijoje (simuliuota)")
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning(f"bridge connection sim failed: {e}")
        engine._trace_note("bridge_sim", str(e))

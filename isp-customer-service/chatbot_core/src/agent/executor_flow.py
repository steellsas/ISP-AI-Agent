"""
Executor flow — the ONLY place tools run and tickets are registered.

The STATE-driven idempotent ticket registration and the demo bridge simulation
(the engine runs every tool through the gateway; the LLM calls none). Functions take
(state, rt) — the call state and the AgentRuntime. tools run through rt.tools (the
gateway).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .contract.locale import phrase_or
from .execute.ticket import NO_NUMBER, caller_id
from .trace import tools_called_this_session, trace_note

logger = logging.getLogger(__name__)


def register_ticket_from_state(state: Any, rt: Any) -> None:
    """Build + create the ticket DETERMINISTICALLY from state (Phase 3.10/3.11 B):
    cause from the hypothesis/verdict, actions from this call's trace — never from
    the model's free text (which once invented an invalid ticket_type). Idempotent:
    an existing ticket is never duplicated. Best-effort: a failure is traced and the
    close still proceeds (the call record keeps the outcome)."""

    s = state
    if s.ticket.ticket_id or not s.identity.customer_id:
        return
    if s.ticket.request_type:
        _register_request(state, rt)
        return
    # Wave 4a: the fault the CASE settled on IS the cause. This read two fields the wave-3
    # deletions emptied, so a Case-driven ticket said "Gedimas: internet_down — nenustatyta"
    # while the engine knew exactly what the line showed (live 2026-09-23).
    cause = (
        s.case.fault
        or (s.diagnosis.verdicts.get("network") or {}).get("reason")
        or (s.diagnosis.hypothesis or {}).get("cause")
        or ""
    )
    from .contract.locale import phrase

    gloss = phrase_or(f"verdict.{cause}.gloss", cause or phrase("ticket.details.unknown_cause"))
    # The card's own reading of the checks: the cause they support and why (2026-11-24).
    found, because, covered = _card_reading(s)
    gloss = found or gloss
    details = phrase(
        "ticket.details.fault",
        # In words, not the engine's key: a technician read "Gedimas: internet_down" and
        # "Gedimas: tv" (live 2026-09-23).
        problem=phrase_or(
            f"problem_label.{s.intake.problem_type}",
            s.intake.problem_type or phrase("ticket.details.default_problem"),
        ),
        gloss=gloss,
    )
    if because:
        details += phrase("ticket.details.because", items="; ".join(because))
    # The same wording the caller heard, and under the same honesty rule: a card's
    # `escalate.need` describes the state after its fix ran, so a fix that never ran is
    # written as a suspicion (live 2026-09-23: a ticket claimed the router was rebooted).
    from .decide.rules.ticket import ticket_need as _need_wording

    need = _need_wording(s, rt)
    if need and _fold(need) in _fold(details):
        need = None  # the cause sentence already says it — a ticket is not an echo chamber
    if need:
        # Sentence-cased as its own sentence — "Reikalinga: reikalingas…" doubled up.
        details += f" {need[0].upper()}{need[1:]}."
    # WHY it was registered (knowledge/registracija.yaml) — the technician reads it first.
    from .contract.registration import for_the_ticket

    why = for_the_ticket(s.ticket.reason)
    if why:
        details += f" Registruota, nes: {why}."
    # Bridge attempt outcome (2026-08-12): the technician reads WHAT was
    # already tried — "pajungti PC nepavyko (LAN aktyvus)" changes what
    # they bring and check first.
    if state.ticket.bridge_fail_note:
        details += f" {state.ticket.bridge_fail_note}"
    # Contacts from the ticket dialogue (2026-08-04): who to reach and when.
    if s.ticket.contact_phone or s.identity.caller_name:
        kas = s.identity.caller_name or phrase("ticket.details.default_contact")
        details += phrase(
            "ticket.details.contact",
            who=kas,
            relation=_relation(s),
            phone=s.ticket.contact_phone or caller_id(s) or NO_NUMBER,
        )
        if s.ticket.contact_hours:
            details += phrase(
                "ticket.details.contact_hours", hours=s.ticket.contact_hours.rstrip(".")
            )
        details += "."
    # The caller's anamnesis rides on the ticket — the human sees WHEN it broke
    # and after what, not just the telemetry verdict (Step 2 analysis).
    if s.intake.anamnesis_when or s.intake.anamnesis_trigger or s.intake.anamnesis_raw:
        bits = []
        if s.intake.anamnesis_when:
            bits.append(
                phrase(
                    "ticket.details.anamnesis_when",
                    when=phrase_or(
                        f"anamnesis.when.{s.intake.anamnesis_when}", s.intake.anamnesis_when
                    ),
                )
            )
        if s.intake.anamnesis_trigger:
            bits.append(
                phrase(
                    "ticket.details.anamnesis_trigger",
                    trigger=phrase_or(
                        f"anamnesis.trigger.{s.intake.anamnesis_trigger}",
                        s.intake.anamnesis_trigger,
                    ),
                )
            )
        details += phrase(
            "ticket.details.anamnesis", text=", ".join(bits) if bits else s.intake.anamnesis_raw
        )
    # Ledger: what the CALLER established (client-side evidence) — the human
    # taking over sees the checked physical facts, not just telemetry.
    client_bits = _checked_with_client(s, covered)
    if client_bits:
        details += phrase("ticket.details.checked", facts="; ".join(client_bits))
    # Ta pati išvada, kurią išgirdo klientas, keliauja ir meistrui: kas PADARYTA, kas veikia
    # dabar ir ko nepavyko. Vienas šaltinis (`case_rule._summary_words`) dviem adresatams —
    # gyvai 2026-10-02 tikete buvo „laikinas internetas pasiūlytas", nors jis buvo PALEISTAS.
    told = s.case.summary or {}
    if told.get("padaryta"):
        details += phrase("ticket.details.done", works=told["padaryta"])
    elif s.case.worked:
        # No conclusion turn (the caller agreed to paid help right after the offer): the work
        # done on the phone is still the ticket's.
        did = [phrase_or(f"summary.did.{m}", "") for m in s.case.worked]
        did = [d for d in dict.fromkeys(did) if d]
        if did:
            details += phrase("ticket.details.done", works=", ".join(did))
    if told.get("dabar"):
        details += phrase("ticket.details.bridge_live")
    if told.get("nepavyko"):
        details += phrase("ticket.details.not_done", items=told["nepavyko"])
    # What was already TRIED — the human taking over must not redo it (after-hours
    # philosophy 2026-08-03: the agent attempts, a person takes over via the ticket with
    # the full attempt history).
    tried = _tried_causes(s)
    if tried:
        glosses = ", ".join(phrase_or(f"verdict.{c}.gloss", c) for c in dict.fromkeys(tried))
        details += phrase("ticket.details.tried", causes=glosses)
    # A (2026-08-21): secondary problems the caller mentioned mid-call — the
    # technician checks them on the same visit.
    extra = [_extra_item(x) for x in getattr(s.intake, "secondary_problems", None) or []]
    extra = [x for x in extra if x]
    if extra:
        details += phrase("ticket.details.extra", items="; ".join(extra))
    # What the caller could NOT tell us, and what the call ran on instead.
    details += _unanswered_and_assumed(s)
    # The card's own words for why a technician is needed, as the Case recorded them.
    note = (s.case.facts or {}).get("_ticket_note")
    if note and not found:  # the cause line already says it, and better
        details += f" {note[0].upper()}{note[1:]}."
    when = (s.case.facts or {}).get("_available_when")
    if when:
        details += phrase("ticket.details.available_when", when=when)
    hung_up = (s.case.facts or {}).get("_hangup_note")
    if hung_up:
        details += f" {hung_up}"
    from .ticket_types import for_call

    not_reached = _steps_not_reached(s)
    if not_reached:
        details += phrase("ticket.details.not_reached", items=", ".join(not_reached))
    checks = _technician_checks(s)
    if checks:
        details += phrase("ticket.details.technician", items="; ".join(checks))
    ticket_type = for_call(cause, s.ticket.reason)
    if ticket_type == "call_unfinished" and cause and _line_said_healthy(cause) and not not_reached:
        # Two sources disagree (Andrius, 2026-10-22): the person calling back reads both.
        details += phrase("ticket.details.line_vs_client")
    actions = tools_called_this_session(rt.tracer)
    args = {
        "customer_id": s.identity.customer_id,
        "ticket_type": ticket_type,
        "problem_type": s.intake.problem_type,
        "problem_description": details,
        "notes": phrase("ticket.details.actions", tools=", ".join(actions)) if actions else "",
    }
    try:
        # The state update sets ticket_id.
        rt.tools.run(state, rt, "create_ticket", args, reason="register_ticket")
    except Exception as e:  # pragma: no cover - defensive
        trace_note(rt.tracer, state, "register_ticket", str(e), level="error")
    if s.ticket.ticket_id:
        s.ticket.ticket_type = ticket_type


# What arranged the call, not what was found: the technician does not need „gali prieiti" or
# „laikinas prijungimas: jums tinka" (live 2026-11-24). `restored` is the summary's to say.
_NOT_FINDINGS = frozenset(
    {
        "reachable",
        "device_ready",
        "later_agreed",
        "bridge_agreed",
        "has_computer",
        "fix_wanted",
        "guide_agreed",
        "restored",
    }
)


# What the caller tells about the call itself, whatever the card: where and since when.
# Not `fail_device`: „Turiu kompiuterį" to the bridge offer was heard in passing as „neveikia
# kompiuteryje" (replay 2026-11-24) — a card that needs the device asks it itself.
_CALL_FACTS = frozenset(
    {"fail_scope", "connection_type", "recent_events", "changed_device", "rebooted"}
)


def _card_facts(s: Any) -> set[str]:
    """The facts this fault's card asks or its steps produce (empty: no card, no filter)."""
    from .contract import cards as catalog

    card = catalog.card(s.case.fault) if s.case.fault else None
    if card is None:
        return set()
    known = set(card.needs)
    for solution in card.solution:
        for call in solution.steps:
            spec = catalog.module(call.module)
            known |= set(spec.produces if spec is not None else [])
    return known


def _card_reading(s: Any) -> tuple[str | None, list[str], set[str]]:
    """The card's `escalate.cause` / `escalate.because` lines whose facts hold, and the facts
    those lines speak for (they are not listed a second time)."""
    from .contract import cards as catalog
    from .contract.locale import maybe_phrase
    from .contract.schema import Condition

    card = catalog.card(s.case.fault) if s.case.fault else None
    esc = card.escalate if card is not None else None
    if esc is None or not (esc.cause or esc.because):
        return None, [], set()
    facts = dict(s.case.facts)

    def holds(line: Any) -> bool:
        return all(Condition.parse(t).holds(facts) is True for t in line.when)

    found = next((maybe_phrase(line.say) for line in esc.cause if holds(line)), None)
    because = [maybe_phrase(line.say) for line in esc.because if holds(line)]
    covered = {Condition.parse(t).fact for line in esc.because if holds(line) for t in line.when}
    return found, [b for b in because if b], covered


def _checked_with_client(s: Any, covered: set[str]) -> list[str]:
    """„Patikrinta su klientu": each finding once, as the engine holds it now.

    One list from both stores (the reader's evidence and the Case's own answers), the value
    from the Case — the engine's later reading wins over the model's first one (live
    2026-11-24: „lemputės: dega", though the caller said none was on). A fact with no human
    label is the engine's own; a fact another listed one already says („laidas įkištas" next to
    „maitinimo laidas įkištas") is left out.
    """
    from .evidence import CLIENT as _EV_CLIENT
    from .evidence import gloss_label, gloss_value
    from .ledger import _same_news

    keys = [
        key
        for key, e in s.diagnosis.evidence.items()
        # A fact only heard in passing („seeded") was never checked with the caller.
        if e.get("source") == _EV_CLIENT and not e.get("conflict") and not e.get("seeded")
    ]
    # The answers to the Case's own steps (Wi-Fi on, own network, cable in) are the caller's
    # too — the person taking over must not ask them again.
    keys += list(s.case.said or [])
    known = _card_facts(s)
    listed: dict[str, str] = {}
    for key in dict.fromkeys(keys):
        if key.startswith("_") or key in _NOT_FINDINGS or key in covered:
            continue
        if known and key not in known and key not in _CALL_FACTS:
            continue  # the model's own name for a check this card made under its own
        entry = s.diagnosis.evidence.get(key) or {}
        value = s.case.facts.get(key) or entry.get("value")
        if not value or gloss_label(key) == key:
            continue
        listed[key] = str(value)
    said_elsewhere = {
        key
        for key, value in listed.items()
        if any(
            name != key and (name in listed or name in covered)
            for name, _ in _same_news(key, value)
        )
    }
    return [
        f"{gloss_label(key)}: {gloss_value(value, key)}"
        for key, value in listed.items()
        if key not in said_elsewhere
    ]


def _extra_item(x: dict[str, Any]) -> str | None:
    """One side complaint for the ticket — an unnamed one only when it says something."""
    from .contract.locale import phrase, vocab

    text = (x.get("text") or "").strip()
    if not text:
        return None
    if x.get("type"):
        return phrase("ticket.details.extra_item", type=x["type"], text=text)
    words = [w.strip('.,!?…„“"') for w in text.lower().split()]
    if not any(w.startswith(m) for w in words for m in vocab("secondary_problem_marks")):
        return None
    return phrase("ticket.details.extra_item_plain", text=text)


def _steps_not_reached(s: Any) -> list[str]:
    """The fix's steps the call never got to — the technician starts there.

    Not a step whose answer the caller already gave (live 2026-11-24: „nespėta patikrinti:
    routerio maitinimas", though the caller had said the lead was in and the outlet worked),
    nor one the card would not have run (`run_when` / `skip_when` / `done_when`).
    """
    from .contract import cards as catalog
    from .contract.locale import phrase_or
    from .contract.schema import Condition

    card = catalog.card(s.case.fault) if s.case.fault else None
    if card is None or s.case.solution is None:
        return []
    done = set(s.case.worked) | set(s.case.did)
    facts = dict(s.case.facts)
    said = set(s.case.said or [])
    names = []
    for call in card.solution[s.case.solution].steps[s.case.step :]:
        name = phrase_or(f"summary.step_name.{call.module}", None)
        if not name or call.module in done or name in names:
            continue
        spec = catalog.module(call.module)
        if spec is not None and spec.produces and any(f in said for f in spec.produces):
            continue  # the caller answered it
        run_when = getattr(call, "run_when", None) or []
        if run_when and not all(Condition.parse(t).holds(facts) is True for t in run_when):
            continue
        skip_when = getattr(call, "skip_when", None) or []  # any one is enough
        if any(Condition.parse(t).holds(facts) is True for t in skip_when):
            continue
        done_when = getattr(call, "done_when", None) or []  # all of them (IR)
        if done_when and all(Condition.parse(t).holds(facts) is True for t in done_when):
            continue
        names.append(name)
    return names


def _technician_checks(s: Any) -> list[str]:
    from .contract import cards as catalog
    from .contract.locale import maybe_phrase

    card = catalog.card(s.case.fault) if s.case.fault else None
    if card is None or card.escalate is None:
        return []
    return [w for w in (maybe_phrase(k) for k in card.escalate.checks) if w]


def _line_said_healthy(cause: str) -> bool:
    from .faults import verdict_flag

    return bool(verdict_flag(cause, "healthy_up_to_router"))


def _fold(text: str) -> str:
    """Lowercased, for the "is this the same sentence again" check."""
    return " ".join((text or "").lower().split()).strip(" .")


def _tried_causes(s: Any) -> list[str]:
    """Ką ŠIS skambutis jau bandė ir ką pakeliui atmetė — meistrui, kad nedarytų to paties.

    Iki 8c bangos tai buvo skaitoma iš `diagnosis.failed_hypotheses` ir
    `rejected_hypotheses`, kuriuos v2 variklis tik IŠVALO (`identification.py`) ir niekada
    nepildo — tad `ticket.details.tried` tikete neatsirasdavo niekada. Case'as tą pačią
    informaciją turi:

    * `case.spent` — gedimai, kurių sprendimas BUVO paleistas ir nepadėjo;
    * `case.announced` — gedimai, apie kuriuos jau kalbėjome su klientu; jei faktai juos nuo
      tada atmetė, tai ir yra „patikrinta ir atmesta".

    Visų `ruled_out` kortelių nevardijam sąmoningai: telemetrija jų atmeta po dešimt, ir
    meistrui tai ne žinia, o triukšmas. Dabartinis gedimas sąraše nefigūruoja — jis tikete
    jau yra kaip priežastis.
    """
    from .case import candidates

    closed = {c.fault for c in candidates(s.case.facts or {}) if c.status == "ruled_out"}
    fault = s.case.fault
    spent = [f for f in (s.case.spent or []) if f != fault]
    rejected = [f for f in (s.case.announced or []) if f in closed and f != fault]
    return list(dict.fromkeys(spent + rejected))


def _unanswered_and_assumed(s: Any) -> str:
    """What stayed unknown, and what the call ran on instead (wave 4a).

    A technician reading "neatsakė, ar neveikia visuose įrenginiuose; dirbome su prielaida,
    kad visuose" knows what to check first — and knows the agent did not invent an answer.
    """
    from .contract.locale import phrase
    from .evidence import gloss_label
    from .facts import gloss

    bits: list[str] = []
    assumed = dict(getattr(s.case, "assumed", None) or {})
    left_out = {d.get("fact") for d in getattr(s.case, "declined", None) or []}
    for fact in getattr(s.case, "unavailable", None) or []:
        if fact in left_out and fact not in assumed:
            continue  # already in „nepatikrinta: … (nenorėjote)"
        said = gloss(fact, assumed[fact]) if fact in assumed else None
        if said:
            bits.append(phrase("ticket.details.assumed_item", fact=gloss_label(fact), value=said))
        else:
            bits.append(gloss_label(fact))
    if not bits:
        return ""
    return phrase("ticket.details.unanswered", items="; ".join(bits))


def _relation(s: Any) -> str:
    """„ (nuomininkas)" — the caller's relation to the contract as the ticket reads it."""
    from .contract.locale import phrase_or

    rel = s.identity.caller_relation
    words = phrase_or(f"ticket.details.relation.{rel}", None) if rel else None
    return f" ({words})" if words else ""


def _debt_dispute_details(state: Any, rt: Any, said: str) -> str:
    """A disputed debt for the accounting: what the system shows, what the caller says they
    paid (when, how, how much) and their questions — the payment is searched by these."""
    from .contract.locale import phrase
    from .inform import inform_text

    s = state
    reason = (s.diagnosis.verdicts.get("network") or {}).get("reason")
    system = inform_text(state, rt, reason, key="ticket_key")
    if s.ticket.request_type != "billing_request" or not system:
        return ""
    from .decide.rules.requests import debt_claim_text

    claim = debt_claim_text(state)
    out = system
    out += (
        phrase("ticket.details.debt_claim", claim=claim)
        if claim
        else phrase("ticket.details.debt_said", text=said.rstrip("."))
    )
    if s.closing.debt_questions:
        qs = " ".join(q.rstrip("?.") + "?" for q in s.closing.debt_questions)
        out += phrase("ticket.details.debt_questions", questions=qs)
    return out


def _register_request(state: Any, rt: Any) -> None:
    """A question for the responsible person: the caller's own words, typed by intent, with
    who to call and when — nothing interpreted (the agent does not know this area)."""
    from .contract.locale import phrase
    from .intents import intent_for_ticket_type
    from .perceive.nlu import classify_problem

    s = state
    # What the caller said about it — not the "Taip" / name answers of identification.
    heard = s.intake.heard_utterances
    about = [u for u in heard if classify_problem(u) == s.intake.problem_type] or heard[:1]
    said = s.ticket.request_note or " / ".join(about[:3]) or s.intake.problem_type or ""
    details = _debt_dispute_details(state, rt, said) or phrase(
        "ticket.details.request",
        type=phrase_or(f"request_label.{s.ticket.request_type}", s.ticket.request_type),
        text=said,
    )
    if s.ticket.contact_phone or s.identity.caller_name:
        details += phrase(
            "ticket.details.contact",
            who=s.identity.caller_name or phrase("ticket.details.default_contact"),
            relation=_relation(s),
            phone=s.ticket.contact_phone or caller_id(s) or NO_NUMBER,
        )
        if s.ticket.contact_hours:
            details += phrase(
                "ticket.details.contact_hours", hours=s.ticket.contact_hours.rstrip(".")
            )
        details += "."
    args = {
        "customer_id": s.identity.customer_id,
        "ticket_type": s.ticket.request_type,
        # What the request is about (a disputed debt on an internet call is `billing`):
        # a later call about the internet is not a repeat of it (D-12).
        "problem_type": intent_for_ticket_type(s.ticket.request_type) or s.intake.problem_type,
        "problem_description": details,
    }
    try:
        rt.tools.run(state, rt, "create_ticket", args, reason="register_request")
    except Exception as e:  # pragma: no cover - defensive
        trace_note(rt.tracer, state, "register_request", str(e), level="error")
    if s.ticket.ticket_id:
        s.ticket.ticket_type = s.ticket.request_type


def simulate_router_reboot_action(state: Any, rt: Any) -> None:
    """DEMO/TEST only (SIMULATE_REBOOT=on): reflect the caller power-cycling the
    router (S6) — the demo port flaps and traffic returns, so the reboot-check
    telemetry read sees what a real reboot produces. Off by default → live demo
    calls use the „Perkrauti routerį" button instead (the human plays the
    physical world); production sees the real flap on its own."""

    if os.getenv("SIMULATE_REBOOT", "off").lower() != "on":
        return
    cid = state.identity.customer_id
    if not cid:
        return
    try:
        res = rt.tools.run(
            state,
            rt,
            "simulate_router_reboot",
            {"customer_id": cid},
            reason="simulate_reboot",
            apply=False,
        ).data
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning(f"router reboot sim failed: {e}")
        trace_note(rt.tracer, state, "reboot_sim", str(e))


def simulate_bridge_connection(state: Any, rt: Any) -> None:
    """DEMO/TEST only (SIMULATE_BRIDGE=on): reflect the caller plugging a PC into the
    wall cable by making an unbound device appear on the line, so the bridge can
    VERIFY it. Off by default → production never fakes a device (the real one appears
    on its own). Best-effort: a failure just leaves the line unchanged."""

    if os.getenv("SIMULATE_BRIDGE", "off").lower() != "on":
        return
    cid = state.identity.customer_id
    if not cid:
        return
    try:
        res = rt.tools.run(
            state,
            rt,
            "simulate_bridge_connect",
            {"customer_id": cid},
            reason="simulate_bridge",
            apply=False,
        ).data
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning(f"bridge connection sim failed: {e}")
        trace_note(rt.tracer, state, "bridge_sim", str(e))

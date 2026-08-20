"""
Identification flow — the deterministic identification ladder around the pure
helpers in agent/identification.py (phrases, policy) and agent/nlu.py.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of
ReactAgent — the phone preflight, the NLU slot prefill, the accumulated-address
DB check, the identity reopen, and the scripted-ladder reply composer.
Functions take the engine explicitly. execute_tool is imported lazily from
react_agent so the tests' import-fallback stubs keep working.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def preflight_phone(engine: Any) -> None:
    """Look up the caller's number at the START of the call (deterministic).

    Runs once, in code (not via the LLM), so by the customer's first turn the
    phone account — if any — is already known and the agent can offer its
    address for confirmation without a tool round-trip. Stored as an
    UNCONFIRMED candidate (anchor rule), never as a confirmed customer.
    """
    from .react_agent import execute_tool

    phone = engine.state.caller_phone
    if not phone or phone == "unknown":
        return
    engine.state.preflight_done = True
    try:
        result = json.loads(execute_tool("find_customer", {"phone": phone}))
    except Exception:
        return
    if not result.get("success"):
        engine.tracer.emit("preflight", found=False)
        return
    addresses = result.get("addresses") or []
    primary = next(
        (a for a in addresses if a.get("is_primary")),
        addresses[0] if addresses else {},
    )
    engine.state.phone_candidate = {
        "customer_id": result.get("customer_id"),
        "name": result.get("name"),
        "address": primary.get("full_address"),
        # Structured parts for the phone cross-check: if the caller names this
        # street, offer the full address to confirm instead of making them
        # dictate the house/apartment (spoken numbers are STT-fragile).
        "city": primary.get("city"),
        "street": primary.get("street"),
        "house": primary.get("house_number"),
        "apartment": primary.get("apartment_number"),
    }
    engine.tracer.emit("preflight", found=True, customer_id=result.get("customer_id"))

    # Proactive mass-outage awareness (roadmap 6b): if this caller's street
    # has an active outage, remember it so the FIRST reply can inform right
    # away — no full identification needed (everyone at that street is down).
    try:
        outage = json.loads(
            execute_tool("check_outages", {"customer_id": result.get("customer_id")})
        )
    except Exception:
        return
    if outage.get("affected") and outage.get("active_outages"):
        first = outage["active_outages"][0]
        eta = first.get("estimated_resolution") or ""
        engine.state.preflight_outage = {
            "street": first.get("street"),
            "eta": eta[11:16] if len(eta) >= 16 else eta,  # HH:MM, voice-friendly
            "description": first.get("description"),
        }
        engine.tracer.emit("preflight_outage", street=first.get("street"))


def prefill_slots_from_text(engine: Any, text: str) -> None:
    """Deterministic NLU Track A: extract the address from the caller's turn and
    propose it into the slots BEFORE the LLM runs (docs/pokalbio_variklis.md §4).

    The reading is the high-confidence floor — registry-validated street +
    normalized numbers — so the slots get a reliable source independent of the
    LLM. Proposed as HEARD; resolve_address upgrades a confirmed hit to
    RESOLVED. Best-effort: any failure (DB, import) silently no-ops the turn.
    """
    s = engine.state
    # Raw utterance buffer: keep every caller turn verbatim so nothing is lost
    # when VAD/STT splits an utterance into fragments. Feeds the LLM
    # reconciliation fact when the deterministic slots stall (see
    # _state_facts_block), and the future async silent re-processing.
    if text and text.strip():
        s.heard_utterances.append(text.strip())

    # Problem classification (R1) — independent of the registry/DB, so it runs
    # even if address extraction fails. A revisable hypothesis: a clearer later
    # statement overrides (docs/pokalbio_variklis.md §12.2).
    try:
        from .nlu import classify_problem, extract_symptoms

        problem = classify_problem(text)
        if problem:
            s.problem_type = problem
        # Revisable: a clearer later mention overrides an earlier reading.
        s.symptoms.update(extract_symptoms(text))
    except Exception:  # pragma: no cover - best-effort
        pass

    # Phase gate (Andrius 2026-08-13): once the caller IS identified, numbers
    # and street-like words are CONTENT ("nei 1 lemputė nedega"), never an
    # address — stop extracting entirely; an address CORRECTION reopens
    # identification through its own path (_reopen_identification) instead.
    if s.customer_id:
        return

    # Address-evidence gate: only scan the turn for an address when it plausibly
    # CONTAINS one — a digit or an address word in the utterance, or the agent just
    # asked for the address. Without this, fuzzy street matching read an ADDRESS out
    # of the anamnesis answer ("po AUDROS" -> "Aušros g.") and the bogus street slot
    # blocked the phone-address offer, derailing identification (observed).
    low = (text or "").lower()
    has_addr_evidence = any(ch.isdigit() for ch in low) or any(
        w in low for w in ("gatv", " g.", "prospekt", "alėj", "aikšt", "kaim", "adres", "but")
    )
    if not has_addr_evidence:
        q = (engine._last_agent_question() or "").lower()
        asked_address = any(w in q for w in ("adres", "gatv", "namo", "numer", "but"))
        if not asked_address:
            return  # no address in sight — do not fuzzy-match one into the slots
    try:
        from .nlu import extract_address, load_registry
        from .slots import SlotStatus
        from .tools import get_db

        if engine._registry is None:
            engine._registry = load_registry(get_db())
        streets, localities = engine._registry
        reading = extract_address(text, streets, localities)
    except Exception:  # pragma: no cover - best-effort, never break a turn
        logger.debug("NLU prefill failed", exc_info=True)
        return

    p = s.profile
    conf = reading.street_confidence or 0.6
    if reading.city:
        p.city.propose(reading.city, conf, SlotStatus.HEARD)
    if reading.street:
        p.street.propose(reading.street, conf, SlotStatus.HEARD)
    # A bare number with NO street context is not an address (Andrius
    # 2026-08-13: STT wrote "Viena neveikia" as "1 neveikia" -> house=1 -> the
    # LLM fuzzy-matched a street the caller never said). House/apartment land
    # only when a street is known — said now or already in the slots.
    if reading.house and (reading.street or p.street.value):
        p.house.propose(reading.house, conf, SlotStatus.HEARD)
    if reading.apartment and (reading.street or p.street.value):
        p.apartment.propose(reading.apartment, conf, SlotStatus.HEARD)

    # If the caller names a DIFFERENT street than the pre-flight outage was
    # for, that outage is not theirs — drop it so its proactive instruction
    # stops polluting the rest of the call (observed: the agent kept
    # apologising and re-mentioning the outage after the caller switched
    # streets).
    if reading.street and s.preflight_outage and reading.street != s.preflight_outage.get("street"):
        s.preflight_outage = None

    engine.tracer.emit(
        "nlu",
        problem=s.problem_type,
        city=reading.city,
        street=reading.street,
        house=reading.house,
        apartment=reading.apartment,
        confidence=round(reading.street_confidence, 2),
    )

    # DB-ground everything heard so far (any order, across fragments).
    revalidate_accumulated_address(engine)


def revalidate_accumulated_address(engine: Any) -> None:
    """Check the ACCUMULATED address slots against the DB every turn and stash
    the DB's verdict for the facts block.

    The tools can always validate what is real — which streets exist, in which
    village, which house numbers are on a street — so we lean on that instead
    of the last (often garbled) fragment. resolve_address is called with ALL
    slots gathered so far, in any order; its `hint` already says the exact next
    step ("Radau sutartį adresu … — patvirtink", "Paklausk namo numerio",
    "Dainų ar Dailės?", "Namo 6 … nerandu"). Read-only: the id is committed only
    when the agent confirms with the caller (anchor rule), never here.
    """
    from .react_agent import execute_tool

    engine._db_address_note = None
    s = engine.state
    if s.customer_id or not s.profile.street.value:
        return
    p = s.profile
    args: dict[str, str] = {"street": p.street.value}
    if p.city.value:
        args["city"] = p.city.value
    if p.house.value:
        args["house_number"] = p.house.value
    if p.apartment.value:
        args["apartment_number"] = p.apartment.value
    try:
        res = json.loads(execute_tool("resolve_address", args))
    except Exception:  # pragma: no cover - best-effort, never break a turn
        return
    hint = res.get("hint")
    if hint:
        engine._db_address_note = (
            f"- DB CHECK (everything heard so far → {args}): {hint} "
            "Act on THIS (the DB), not on the last thing you misheard; if it is a "
            "match, confirm that exact address; if a part is missing/unclear, ask "
            "only for it. Do NOT read out a list of street names for the caller to "
            "pick from — if the street is unclear, ask them to repeat it."
        )


def reopen_identification(engine: Any, user_input: str) -> None:
    """The caller corrected the address AFTER identification — drop the identity and
    every per-account conclusion; keep only the conversation. The router sends the
    next turn back to address_validation (customer_id is None again)."""
    s = engine.state
    engine._trace_note(
        "reopen_identity",
        f"caller says a DIFFERENT address; dropping {s.customer_id}",
        level="warn",
    )
    s.customer_id = None
    s.customer_name = None
    s.customer_address = None
    s.address_confirmed = False
    s.resolution = None
    s.diagnosis.clear()
    s.hypothesis = None
    s.failed_hypotheses.clear()
    s.rejected_hypotheses.clear()
    s.pivoted_from = None
    s.outage_reported = False
    # Ledger + its machinery (review 2026-08-07): the EVIDENCE belongs to the
    # dropped account — stale telemetry facts (the old verdict!) must never
    # survive an address correction. The ticket dialogue, ask counters and
    # deviation streak reset with it; the thinker gets a clean slate too.
    s.evidence.clear()
    engine._evidence_asks.clear()
    engine._evidence_last_ask_key = None
    engine._evidence_conflict = None
    engine._evidence_conflict_asked = None
    engine._side_topic_this_turn = False
    engine._side_topic_turns = 0
    engine._ticket_stage = None
    engine._ticket_ctx = None
    engine._drive_bridge_offered = False
    engine._drive_disabled = False
    engine._drive_repeats = 0
    engine._findings_announced = False
    engine._pending_announce = ""
    engine._escalate_clarify_asked = False
    engine._escalate_clarify_pending = False
    engine._resume_fix_note = False
    engine._recap_state = ""
    engine._refute_state = ""
    engine._done_report_key = None
    engine._bridge_plug_reported = False
    engine._bridge_fail_stage = 0
    engine._bridge_fail_note = None
    engine._revived_keys = set()
    from .slots import ClientProfileState

    s.profile = ClientProfileState()
    engine._db_address_note = None
    engine._news_told = False  # a new address may carry different news
    engine._result_pending = False
    engine._end_confirm_pending = False
    engine._resume_hold = False
    engine._bridge_bound = False  # a different account starts clean
    # Re-extract address parts from THIS utterance (the correction often carries
    # the new address: "ne, skambinu dėl Dainų 5").
    prefill_slots_from_text(engine, user_input)
    engine._reopen_note = True


def identification_scripted_reply(engine: Any, user_input: str | None) -> str | None:
    """Deterministic identification-ladder replies (2026-07-31, IDENTIFICATION
    ONLY): the mechanical turns are COMPOSED by the engine from the phrases in
    identification.yaml — the LLM repeatedly reordered or skipped them (promised
    a check without the result, relapsed into confirm rounds, skipped the caller
    question, captured 'Taip.' as a name). An off-script caller turn (a question)
    returns None so the LLM answers it; the ladder resumes next turn. Solving and
    free dialogue never come here."""
    s = engine.state
    if s.case_closed:
        return None
    from .identification import caller_question, phrase
    from .resolution import is_real_question

    # Ticket-confirmation dialogue: contacts before every registration. An
    # off-script question falls to the ticket node's LLM (facts carry the
    # pending stage question to re-ask); the mechanical turns stay scripted.
    if engine._ticket_stage in ("phone", "hours"):
        if engine._ticket_offscript:
            return None
        scripted = engine._ticket_stage_reply()
        # Zone 1 (skriptai -> direktyvos, Andrius 2026-08-20): the QUESTION
        # moments go to the narrator as a goal directive — it words them into
        # the conversation's flow; retries and the cancel-confirm stay
        # scripted (precision beats style on a repeat). Off-switch reverts.
        import os as _os

        kind = (engine._ticket_ctx or {}).get("last_kind")
        if _os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on" and kind in (
            "phone_intro",
            "phone",
            "hours",
        ):
            engine._ticket_directive = {"kind": kind, "fallback": scripted}
            return None  # the ticket node's narrator speaks (facts directive)
        return scripted
    if engine._ticket_stage == "done":
        return engine._finish_ticket_dialogue()
    if engine._ticket_stage == "cancelled":
        engine._ticket_stage = None
        engine._ticket_ctx = None
        s.case_closed = True
        s.closed_reason = "declined"
        s.is_complete = True
        return "Gerai — gedimo neregistruoju. " + phrase("goodbye")
    # Side-topic FRAME (3rd consecutive deviation): the LLM answered twice
    # and the caller keeps drifting — the return is scripted now. With a
    # CONFIRMED hypothesis the frame is the solve-together-or-technician
    # choice (Andrius 2026-08-07: maximise solving by phone).
    if engine._side_topic_this_turn and engine._side_topic_turns >= 3:
        engine._side_topic_turns = 0
        from .evidence import hypothesis_status, spec_for

        spec = spec_for((s.resolution or {}).get("verdict"))
        if spec is not None and hypothesis_status(s.evidence, spec) == "confirmed":
            return phrase("solve_or_ticket")
        return phrase("back_to_issue", inkaras=engine.anchor_text())
    # Ledger conflict clarify (ONE question, engine-composed): "sakėte X,
    # dabar Y — kaip yra iš tiesų?" — the next answer settles the fact.
    if engine._evidence_conflict:
        from .evidence import LABELS, VALUE_LT

        key, old, new = engine._evidence_conflict
        engine._evidence_conflict = None
        engine._evidence_conflict_asked = key
        return phrase(
            "evidence_conflict",
            tema=LABELS.get(key, key),
            a=VALUE_LT.get(old, old),
            b=VALUE_LT.get(new, new),
        )
    # Farewell-mid-process clarify (any stage): ONE deterministic confirm question.
    if engine._end_confirm_pending:
        return phrase("confirm_end")
    # Uncorroborated bare "ne" tried to route the walker into ESCALATE — ask
    # the solve-or-register choice instead of crossing the one-way door
    # (2026-08-11). The next turn routes normally: a repeated no escalates.
    if getattr(engine, "_escalate_clarify_pending", False):
        engine._escalate_clarify_pending = False
        return phrase("escalate_clarify")
    # Bare "ne" while the evidence drive's question is open, on the WALKER
    # path (farewell/refuse-shaped turns land here; the drive words its own
    # clarify): say what the "ne" could mean instead of acting on it.
    from .resolution import is_bare_negation

    open_key = engine._evidence_question_open()
    if open_key and is_bare_negation(user_input):
        clarify = engine._negation_clarify_reply(open_key)
        if clarify:
            return clarify
    if user_input and is_real_question(user_input):
        return None  # off-script — the LLM answers; guards kept the ladder state
    # INTAKE (not yet identified): the anamnesis question and the address
    # offer/ask are mechanical too — the LLM repeated the anamnesis and slid the
    # whole ladder by a turn (observed in eval).
    if not s.customer_id:
        # Small talk BEFORE any problem is stated gets a scripted greeting-back
        # — never the LLM (which jumped to the address offer on "Labadiena!",
        # duplicating the ladder's own later offer; live 2026-08-06).
        if not s.problem_type and user_input:
            from .resolution import is_greeting

            if is_greeting(user_input):
                return phrase("ask_problem")
        p = s.profile
        has_addr = bool(p.street.value or p.house.value)
        if s.problem_type and not s.anamnesis_asked and not s.preflight_outage and not has_addr:
            s.anamnesis_asked = True
            return _anamnesis_move(engine, "anamnesis", phrase("anamnesis_question"))
        # E (Andrius 2026-08-20): the follow-up rung — the caller did not know
        # WHEN it broke, so we asked when it last WORKED; the answer narrows
        # the time window for the analysis ("vakar veikė" -> broke overnight).
        if getattr(engine, "_anamnesis_followup", False) and user_input and not has_addr:
            engine._anamnesis_followup = False
            from .nlu import extract_anamnesis

            read = extract_anamnesis(user_input)
            s.anamnesis_when = read.get("when") or user_input.strip(" .!?,")[:80]
            s.anamnesis_raw = (
                f"{s.anamnesis_raw or ''} | paskutinį kartą veikė: {user_input.strip()[:80]}"
            )
            engine.tracer.emit(
                "anamnesis", text=s.anamnesis_raw, when=s.anamnesis_when, followup=True
            )
            return _address_move(engine, s)
        if s.anamnesis_asked and s.anamnesis_raw is None and user_input and not has_addr:
            s.anamnesis_raw = user_input.strip()[:200]
            from .nlu import extract_anamnesis

            read = extract_anamnesis(s.anamnesis_raw)
            s.anamnesis_when = read.get("when")
            s.anamnesis_trigger = read.get("trigger")
            engine.tracer.emit(
                "anamnesis",
                text=s.anamnesis_raw,
                when=s.anamnesis_when,
                trigger=s.anamnesis_trigger,
            )
            # E: nothing usable heard ("nežinau") — ONE follow-up rung about
            # the last time the service worked, then on to the address.
            if s.anamnesis_when in (None, "nežino") and not s.anamnesis_trigger:
                engine._anamnesis_followup = True
                return _anamnesis_move(engine, "anamnesis_followup", phrase("anamnesis_last_used"))
            return _address_move(engine, s)
        return None
    # WRAP-UP after the news (inform mode): the business is DONE — any further
    # turn that is not a question/wants-more wraps up DETERMINISTICALLY. Garbled
    # goodbyes ("Nusigaro" = "viso gero") had the model loop "nesupratau,
    # pakartokite" after a delivered debt notice (observed live: the caller could
    # not end the call).
    if (
        s.resolution is None
        and (engine._news_told or s.outage_reported)
        and not engine._result_pending
    ):
        low = (user_input or "").lower()
        wants_more = is_real_question(user_input) or any(
            m in low
            for m in (
                "klausim",
                "palauk",
                "dar ",
                "noriu",
                "minut",
                "sekund",
                "skol",
            )
        )
        if wants_more:
            return None  # a question / wants something — the LLM handles it
        s.case_closed = True
        s.closed_reason = "outage" if s.outage_reported else "inform"
        s.is_complete = True
        engine.tracer.emit("decision", intent="wrap_up", action="close", to=s.closed_reason)
        return phrase("goodbye")
    if not engine._result_pending:
        return None
    if not s.caller_name:
        # The caller-intro question turn (with the address echo on a fresh
        # commit) + the CHECKING cue — the engine resolves/diagnoses silently
        # here, and without the cue the caller thinks nothing started
        # (live 2026-08-07: "nepasako, kad patikrins").
        parts = []
        if engine._just_identified and s.customer_address:
            parts.append(phrase("echo_address", adresas=s.customer_address))
            parts.append(phrase("checking_note"))
        engine._just_identified = False
        parts.append(caller_question())
        return " ".join(p for p in parts if p)
    # The caller introduced themselves — deliver the deferred result. INFORM
    # verdicts are fully mechanical; a strategy result (finding + step question)
    # stays with the LLM (returns None; the REZULTATO facts directive drives it).
    if s.resolution is not None:
        return None
    from .glossary import DIAGNOSIS_LT

    d = s.diagnosis.get("network") or {}
    reason = d.get("reason")
    zinia = DIAGNOSIS_LT.get(reason, reason or "")
    if not zinia:
        return None
    zinia = zinia[0].upper() + zinia[1:]  # sentence-cased after "…iki jūsų buto."
    bits = [phrase("thanks"), phrase("check_result", zinia=zinia + ".")]
    if reason == "billing_suspended":
        bits.append(phrase("billing_extra"))
    # Outage news carries the ETA when the preflight knows it.
    if reason == "active_outage" and (s.preflight_outage or {}).get("eta"):
        bits.append(f"Numatomas atstatymas iki {s.preflight_outage['eta']}.")
    bits.append(phrase("anything_else"))
    engine._result_pending = False
    engine._news_told = True
    return " ".join(b for b in bits if b)


def _anamnesis_move(engine, kind: str, fallback: str):
    """Zone 3 (skriptai -> direktyvos): the anamnesis questions go to the
    narrator — it adapts to what the caller already said (one or several
    things asked in one breath, per the answer). Off-switch keeps the script."""
    import os as _os

    if _os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on":
        engine._ident_directive = {"kind": kind, "adresas": None, "fallback": fallback}
        return None  # the narrator words it (facts directive)
    return fallback


def _address_move(engine, s):
    """Zone 2 (skriptai -> direktyvos): the transition to the address — offer
    the phone-candidate address or ask for one. In narrator mode the moment
    becomes a goal directive (a smooth hand-over from the problem talk); the
    OFFER question's core stays verbatim ("Ar skambinate dėl X?") because the
    deterministic confirm guard keys off it. Off-switch keeps the scripts."""
    import os as _os

    from .identification import offer_phone_address, phrase

    c = s.phone_candidate
    if offer_phone_address() and c and c.get("street") and not s.preflight_outage:
        flat = f", butas {c['apartment']}" if c.get("apartment") else ""
        adresas = f"{c['street']} {c.get('house')}{flat}"
        kind, fallback = "address_offer", phrase("address_offer", adresas=adresas)
    else:
        adresas = None
        kind, fallback = "address_ask", phrase("address_ask")
    if _os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on":
        engine._ident_directive = {"kind": kind, "adresas": adresas, "fallback": fallback}
        return None  # the narrator words the transition (facts directive)
    return fallback


def address_diag_note(obs: dict) -> str | None:
    """F2 (Andrius 2026-08-20): a FAILED address lookup must tell the caller
    exactly what WAS found and what was not — 'Vilniaus gatvę randu, bet 39
    numerio nematau' lets the caller correct themselves. Composed from the
    resolver's per-level diagnosis into a narrator directive; None when there
    is nothing more specific than the generic re-ask."""
    res = obs.get("resolution") or {}
    city = res.get("city") or {}
    street = res.get("street") or {}
    house = res.get("house") or {}
    place = city.get("matched") or city.get("given") or ""
    vieta = f" mieste {place}" if place else ""
    bits: list[str] = []
    st = street.get("status")
    if st in ("not_found", "not_in_city"):
        g = street.get("given") or "nurodytos gatvės"
        line = f"gatvės „{g}“{vieta} NERANDU"
        elsewhere = street.get("found_elsewhere") or []
        if elsewhere:
            kur = ", ".join(str(e.get("city") or e) for e in elsewhere[:3])
            line += f", bet tokia gatvė yra: {kur} — paklausk, ar ne ten"
        else:
            line += " (gal ji vadinasi kitaip? pavadinimai keičiasi)"
        bits.append(line)
    elif st == "unclear" and street.get("fuzzy_candidates"):
        cands = ", ".join(str(c) for c in street["fuzzy_candidates"][:3])
        bits.append(f"gatvės neišgirdau tiksliai — panašios: {cands}; paklausk, kuri")
    elif st in ("ok", "derived", "recovered") and house.get("status") == "not_found":
        g = street.get("matched") or street.get("given") or "gatvę"
        line = f"gatvę {g}{vieta} RANDU, bet namo {house.get('given')} numerio NĖRA"
        known = house.get("known_houses") or []
        if known:
            line += f" (toje gatvėje yra: {', '.join(str(h) for h in known[:6])})"
        line += " — paprašyk patikslinti namo numerį"
        bits.append(line)
    elif city.get("status") == "ambiguous":
        alts = city.get("alternatives") or city.get("candidates") or []
        kur = ", ".join(str(a.get("city") if isinstance(a, dict) else a) for a in alts[:3])
        bits.append(f"tokia gatvė yra keliuose miestuose ({kur}) — paklausk, kuriame")
    if not bits:
        return None
    return (
        "- ADRESO PAIEŠKOS DIAGNOZĖ (pasakyk klientui BŪTENT tai — kas rasta ir ko "
        "ne, savais žodžiais, trumpai — ir paprašyk patikslinti TIK trūkstamą "
        "dalį): " + "; ".join(bits) + ". Neišgalvok adresų."
    )

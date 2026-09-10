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
        from .faults import problem_politika
        from .nlu import classify_problem, extract_symptoms

        problem = classify_problem(text)
        # №4 tęsinys (etalonas 2026-09-03): atsakymas į savininko patikslinimą
        # atnaujina santykį („žmonos vardu sudaryta" → family) — vienas skaitymas.
        if (
            getattr(engine, "_holder_clarify_open", False)
            and getattr(engine, "_holder_clarify_asked", False)
            and text
        ):
            engine._holder_clarify_open = False
            engine._holder_clarify_asked = False
            from .identification import detect_caller_relation as _dcr

            _rel = _dcr(text)
            if _rel and _rel != "unknown":
                s.caller_relation = _rel
                engine.tracer.emit(
                    "caller_intro", name=s.caller_name, relation=_rel, clarified=True
                )
        # Competence policy (2026-09-02): nelieciam/pokalbis types NEVER become
        # the call's problem_type — the gate answers with the declared boundary
        # phrase instead of opening identification ("kodėl tokia sąskaita?" is
        # not a fault). Stashed one-shot for the reply layer.
        if problem and problem_politika(problem) in ("nelieciam", "pokalbis"):
            if s.problem_type is None:
                engine._boundary_problem = problem
            problem = None
        if problem:
            # A (Andrius 2026-08-21): the PRIMARY goal is the caller's stated
            # call reason and NEVER flips mid-call (an STT garble switched it
            # to billing live). Later mentions of other problems become
            # SECONDARY — noted, asked about at the end, listed on the ticket.
            if s.problem_type is None:
                s.problem_type = problem
            elif (
                problem != s.problem_type
                and s.resolution is not None
                and not s.case_closed
                and not getattr(engine, "_ticket_stage", None)
                and len((text or "").split()) >= 3  # garbles ("Žemės gatvės") are not complaints
            ):
                if not any(x.get("tipas") == problem for x in s.secondary_problems):
                    s.secondary_problems.append(
                        {
                            "tipas": problem,
                            "tekstas": (text or "").strip()[:120],
                            "turn": s.turn_count,
                        }
                    )
            elif not s.customer_id and s.resolution is None:
                s.problem_type = problem  # early self-correction is fine
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

    # №2 (etalonas 2026-09-03): kodo laukimo fazėje adresų skaitytuvas TYLI —
    # kodo skaitmenys ne namo numeris, o fuzzy gatvių paieška iš tokių frazių
    # („Neturiu jokio KODO" → „Sodo g.", gyva I5) tik teršia slotus.
    # NLU wave block 2 (live 2026-09-07: "Šiauliai, Tilžės gatvė 60, butas 3"
    # was swallowed in code mode): a FULL dictation — an explicit street WORD
    # in the turn — wakes the reader; bare digits stay silenced (the code).
    if getattr(engine, "_awaiting_account_code", False):
        low_cd = (text or "").lower()
        if not any(w in low_cd for w in ("gatv", " g.", "prospekt", "alėj", "alej", "aikšt")):
            return
    # NLU wave block 4: the spelling turn carries LETTERS ("K kaip Kaunas"),
    # not an address — the fuzzy reader would turn the anchor words into a
    # city/street; the rung's spell reader owns this turn.
    if getattr(engine, "_spell_mode", False):
        return
    # NLU wave D1 (live 2026-09-10: STT invented "Žeimių g.", the slot locked
    # at conf 1.0 and the ladder pushed Ginkūnai for THREE turns over "aš
    # apie Žeimių gatvę nieko NESAKIAU"): a denial naming the heard street
    # DROPS it — and counts as a real miss on the road to the spelling round.
    _low_d = (text or "").lower()
    if s.profile.street.value and any(m in _low_d for m in ("nesakiau", "nesakau", "ne apie")):
        from .evidence import _fold as _fd

        _st = _fd(str(s.profile.street.value).replace(" g.", ""))[:5]
        if _st and _st in _fd(text or ""):
            from .slots import Slot as _Slot

            engine._denied_street = _fd(str(s.profile.street.value))
            s.profile.street = _Slot()
            s.profile.house = _Slot()
            engine._addr_resolve_fails = getattr(engine, "_addr_resolve_fails", 0) + 1
            engine._addr_diag_note = None
            engine.tracer.emit(
                "decision",
                intent="street_denied",
                action="slot_dropped",
                fails=engine._addr_resolve_fails,
            )
            # NE return: sakinys gali nešti ir PATAISYMĄ ("nesakiau Žeimių,
            # sakiau TILŽĖS gatvė 60") — skaitymas tęsiasi, tik paneigtos
            # gatvės nebesiūlome (žr. propose žemiau).
    # Address-evidence gate: only scan the turn for an address when it plausibly
    # CONTAINS one — a digit or an address word in the utterance, or the agent just
    # asked for the address. Without this, fuzzy street matching read an ADDRESS out
    # of the anamnesis answer ("po AUDROS" -> "Aušros g.") and the bogus street slot
    # blocked the phone-address offer, derailing identification (observed).
    # Vietovės pasiūlymo VIELOS (gyva T-5, Andrius: „agentas pasiūlė ir
    # klientas patvirtino — tikrinamas kitas regionas"): resolveris pasakė
    # „Žeimių g. yra Ginkūnuose", klientas patvirtina (arba pamini kaimą) —
    # miesto slotas persijungia ir kita paieška vyksta TEN, ne Šiauliuose.
    sug = getattr(engine, "_addr_city_suggestion", None)
    if sug and text:
        from .evidence import _fold as _fold_sug
        from .resolution import DETECTORS as _DET

        mentioned = _fold_sug(str(sug))[:5] in _fold_sug(text)
        if mentioned or _DET["yes_no"](text) == "yes":
            from .slots import SlotStatus as _SS

            s.profile.city.propose(str(sug), 0.95, _SS.RESOLVED)
            engine._addr_city_suggestion = None
            engine.tracer.emit(
                "decision", intent="city_suggestion", action="accepted", value=str(sug)
            )

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
    # NLU wave block 3 (live 2026-09-07: resolve kept going out with the
    # stale 6/60 while the caller dictated the full correct address): a FULL
    # dictation — street AND house heard in THIS turn — is the caller's
    # authoritative statement and overrides earlier fragment readings.
    if reading.street and reading.house:
        conf = max(conf, 0.99)
    # D1: the street the caller just DENIED never comes back from its own
    # denial sentence ("apie Žeimių gatvę nesakiau" fuzzy-matches Žeimių) —
    # re-read the turn against the registry WITHOUT it, so a correction in
    # the same sentence ("…sakiau TILŽĖS gatvė 60") still lands.
    _denied = getattr(engine, "_denied_street", None)
    engine._denied_street = None
    if _denied and reading.street:
        from .evidence import _fold as _fd2

        if _fd2(reading.street) == _denied:
            streets2 = [st for st in streets if _fd2(st) != _denied]
            reading = extract_address(text, streets2, localities)
            conf = reading.street_confidence or 0.6
            if reading.street and reading.house:
                conf = max(conf, 0.99)
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
    # №2 (etalonas 2026-09-03): ŠIS turn'as davė adreso pažangos — abonento
    # kodo pakopos skaitiklis nulinamas (dalimis diktuojamas adresas niekada
    # neturi nuriedėti į kodo klausimą). Pažanga skaitosi tik su TIKRA adreso
    # Adreso PAŽANGA nulina pakopos skaitiklius (2026-09-04 perdirbimas:
    # skaitliukai gyvena _account_code_rung; čia tik pažangos signalas).
    _evid = any(ch.isdigit() for ch in low) or any(
        w in low for w in ("gatv", " g.", "prospekt", "alėj", "aikšt", "kaim", "adres", "but")
    )
    if _evid and (reading.street or reading.house or reading.apartment):
        engine._addr_empty_turns = 0
        engine._addr_unrecognized = 0

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
    # A-2R (live 2026-09-07): the background telemetry read belongs to the
    # DROPPED account — after reopen it kept flooding the cleared diagnosis/
    # hypothesis back in and the narrator drove the old analysis question.
    # Thrown away with everything else.
    engine._bg_diagnosis = None
    # B-wave registry: the whole dialogue restarts — no question survives.
    engine._active_question = None
    # A-2R follow-up (Andrius 2026-09-07): on an address change EVERYTHING
    # restarts — only the caller's name and the problem survive (plus the
    # caller's own story: it describes the REAL place). The old phone
    # candidate is not offered again (the ladder would re-offer the dropped
    # address), and the identification counters and the account-code mode
    # return to a clean slate.
    s.phone_candidate = None
    engine._awaiting_account_code = False
    engine._code_grace = 0
    engine._addr_empty_turns = 0
    engine._addr_unrecognized = 0
    engine._addr_resolve_fails = 0
    engine._addr_city_suggestion = None
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


def _problem_gate_reply(engine: Any, s: Any, user_input: str) -> str | None:
    """Problem GATE with the classification cascade (DIALOGO_ETALONAS,
    2026-09-02). No identification until an in-scope problem is reached:

      1. a pending explicit-confirm guess: „taip" commits (problem_type set,
         caller falls through to the intake ladder THIS turn);
      2. an L1-recognized boundary type (nelieciam/pokalbis) gets its
         file-declared `atsakymas` — competence stated, no identification;
      3. L2: the LLM reads the CONTEXT against the catalog — sprendzia with
         high confidence commits (implicit confirmation), medium asks the
         type's `patvirtinimas` question, a boundary type answers its phrase;
      4. otherwise the old ladder: scripted ask x2, narrator directive, and
         only after ~5 fruitless exchanges the polite close. Reaching a
         problem at ANY rung reopens the flow — the counter never kills a
         conversation that is moving forward."""
    import os as _os

    from .faults import problem_atsakymas, problem_patvirtinimas, problem_politika
    from .identification import phrase
    from .resolution import DETECTORS, is_real_question

    # 1) the caller answers last turn's "Ar gerai suprantu — …?"
    pg = getattr(engine, "_problem_guess", None)
    if pg is not None:
        engine._problem_guess = None
        if DETECTORS["yes_no"](user_input) == "yes":
            s.problem_type = pg
            engine.tracer.emit(
                "decision", intent="problem_gate", action="guess_confirmed", value=pg
            )
            return None  # committed — the intake ladder continues this turn
        # a "ne"/correction falls through; a NAMED problem was already read
        # by the ingest (then this gate is not even entered)
    # 2) boundary type recognized by the trigger layer this turn
    bp = getattr(engine, "_boundary_problem", None)
    if bp is not None:
        engine._boundary_problem = None
        engine._ask_problem_count = getattr(engine, "_ask_problem_count", 0) + 1
        engine.tracer.emit("decision", intent="problem_gate", action="boundary", value=bp)
        return problem_atsakymas(bp) or phrase("ask_problem")
    p_asks = getattr(engine, "_ask_problem_count", 0)
    engine._ask_problem_count = p_asks + 1
    asking = "?" in user_input or is_real_question(user_input)
    # N riba (Andrius 2026-09-03): ne klientas / neaiški situacija — po
    # GATE_MAX_TURNS nevaisingų apsikeitimų mandagus uždarymas BE tiketo
    # (tiketas be customer_id mechaniškai neįmanomas). Configurable knob.
    try:
        gate_max = int(_os.environ.get("GATE_MAX_TURNS", "5"))
    except ValueError:
        gate_max = 5
    if p_asks + 1 >= gate_max:
        s.case_closed = True
        s.closed_reason = "declined"
        engine.tracer.emit("decision", intent="problem_gate", action="close")
        return phrase("no_problem_goodbye")
    # 3) L2 — context classification against the file catalog. The LLM reads
    # the ACCUMULATED tail, not just this turn (2026-09-02, Andrius: „kai
    # informacija pasipildo, ateina supratimas" — VAD/STT splits a story into
    # fragments, but the meaning lives across them: „Oras kažkoks netoks." +
    # „gal dėl to neturiu interneto?" is ONE thought).
    if _os.getenv("CLASSIFIER", "on").lower() != "off":
        from .nlu import classify_problem_llm

        tail = [u for u in getattr(s, "heard_utterances", [])[-3:] if u]
        ctx = " ".join(tail)[-400:] or (user_input or "")
        label, conf = classify_problem_llm(ctx, model=engine.config.model)
        if label:
            pol = problem_politika(label)
            engine.tracer.emit(
                "decision",
                intent="problem_gate",
                action="llm_guess",
                value=label,
                reason=f"{pol}:{conf:.2f}",
            )
            if pol in ("sprendzia", "registruoja"):
                if conf >= 0.8:
                    s.problem_type = label  # implicit confirmation — the
                    return None  # narrator acknowledges it naturally
                if conf >= 0.5:
                    engine._problem_guess = label
                    q = problem_patvirtinimas(label)
                    if q:
                        return q
            elif conf >= 0.5:  # nelieciam / pokalbis from context
                return problem_atsakymas(label) or phrase("ask_problem")
    # 4) the pre-cascade ladder
    if p_asks < 2 and not asking:
        return phrase("ask_problem")
    if _os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on":
        engine._ident_directive = {
            "kind": "problem_gate",
            "adresas": None,
            "fallback": phrase("ask_problem"),
        }
        return None  # the narrator words it (isolated directive turn)
    if asking:
        return None  # scripted mode: a question goes to the LLM
    return phrase("ask_problem")


def _looks_like_address(text: str | None) -> bool:
    """A reply that itself NAMES an address (street word or a digit) — counts
    as a yes to 'ar tikrai kitas adresas?'."""
    low = (text or "").lower()
    return any(ch.isdigit() for ch in low) or any(
        w in low for w in ("gatv", " g.", "prospekt", "alėj", "kaim", "but")
    )


def _extract_account_code(text: str | None) -> str | None:
    """The subscriber code from a spoken reply: 'AB-10104', 'ab 10104', or —
    while the code question is pending — bare 4-6 digits ('vienas nulis…' the
    STT already writes as digits). Conservative: nothing else matches."""
    import re as _re

    low = (text or "").lower().replace(" ", "").replace("-", "").replace("–", "")
    m = _re.search(r"ab(\d{4,6})", low)
    if m:
        return f"AB-{m.group(1)}"
    m = _re.search(r"^\D*(\d{4,6})\D*$", (text or "").replace(" ", ""))
    if m:
        return f"AB-{m.group(1)}"
    return None


_BIG_CITIES = ("vilni", "kaun", "klaipėd", "klaiped", "panevėž", "panevez", "alyt", "marijampol")


def _has_address_content(text: str | None) -> bool:
    """The turn CARRIES address material (a digit, a street word, a place) —
    such a turn is never a 'fruitless' one, whatever the resolver said."""
    low = (text or "").lower()
    return any(ch.isdigit() for ch in low) or any(
        w in low
        for w in ("gatv", " g.", "prospekt", "alėj", "alej", "aikšt", "kaim", "šiaul", "siaul")
    )


def _speak_code(code: str) -> str:
    """TTS-friendly form of the code for confirmation: "AB-10104" -> "A B 1 0 1 0 4"."""
    digits = "".join(ch for ch in code if ch.isdigit())
    return "A B " + " ".join(digits)


def _spell_prefix(text: str | None) -> str:
    """First letters from an anchor-word spelling. Two spoken forms exist:
    "K kaip Kaunas" (the letter BEFORE "kaip") and the caller's spontaneous
    "taip kaip tėtis, ir kaip Ignas" (the anchor AFTER "kaip" — live
    2026-09-10). Per pair: a single-letter token before "kaip" wins; else the
    first letter of the word after it. Without any "kaip", every word's
    first letter counts ("Kaunas Upė" -> "ku")."""
    toks = [t.strip(".,!?-").lower() for t in (text or "").split() if t.strip(".,!?-")]
    if not toks:
        return ""
    letters: list[str] = []
    if "kaip" in toks:
        for i, t in enumerate(toks):
            if t != "kaip":
                continue
            before = toks[i - 1] if i > 0 else ""
            after = toks[i + 1] if i + 1 < len(toks) else ""
            if len(before) == 1 and before.isalpha():
                letters.append(before)
            elif after.isalpha():
                letters.append(after[0])
    else:
        letters = [t[0] for t in toks if t.isalpha() and len(t) >= 2]
    return "".join(letters)


def _register_street_attempt(engine: Any, garble: str) -> str | None:
    """Track failed street readings across turns (Andrius 2026-09-10 rev.2):
    'identical' — the SAME transcript came back, the agent hears it
    CONSISTENTLY, so it heard RIGHT and the street simply is not in the
    registry (the honest not-exists / are-you-our-client branch);
    'similar' — a close-but-different garble, the ASR is unstable (fuzzy
    suggestions and the code rung handle it); None — first sighting."""
    from .evidence import _fold
    from .nlu import street_match_score

    g = _fold((garble or "").replace("gatvė", "").replace(" g.", "").strip())[:24].strip()
    if len(g) < 3:
        return None
    attempts = getattr(engine, "_street_attempts", None) or []
    verdict: str | None = None
    for prev in attempts:
        if prev == g:
            verdict = "identical"
            break
        if street_match_score(g, prev) >= 0.55:
            verdict = "similar"
    attempts.append(g)
    engine._street_attempts = attempts[-4:]
    return verdict


def _street_by_prefix_and_garble(engine: Any, prefix: str, garble: str | None) -> str | None:
    """The letters as a FUZZY FILTER (Andrius 2026-09-10): the registry is
    narrowed to streets starting with the spelled prefix, and the HEARD
    garble is fuzzy-matched inside that small subset with a LOWERED bar —
    letter + garble together beat either alone. Without a garble, the
    shortest prefix match wins (the caller spelled the name itself)."""
    from .evidence import _fold
    from .nlu import load_registry, street_match_score
    from .tools import get_db

    if engine._registry is None:
        engine._registry = load_registry(get_db())
    streets, _ = engine._registry
    want = _fold(prefix)
    subset = [st for st in streets if _fold(st).startswith(want)]
    if not subset:
        return None
    if garble:
        best = max(subset, key=lambda st: street_match_score(garble, st))
        if street_match_score(garble, best) >= 0.4:
            return best
    return min(subset, key=len)


def _street_by_prefix(engine: Any, prefix: str) -> str | None:
    """The registry street whose folded name starts with the spelled prefix —
    the shortest match wins (the caller spelled the NAME, not the suffix)."""
    from .evidence import _fold
    from .nlu import load_registry
    from .tools import get_db

    if engine._registry is None:
        engine._registry = load_registry(get_db())
    streets, _ = engine._registry
    want = _fold(prefix)
    matches = [st for st in streets if _fold(st).startswith(want)]
    if not matches:
        return None
    return min(matches, key=len)


def _lookup_by_code(engine: Any, s: Any, code: str):
    """find_customer(account_code) -> candidate + the aloud address offer, or
    None when the code is not in the DB."""
    import json as _json

    from .react_agent import execute_tool

    try:
        res = _json.loads(execute_tool("find_customer", {"account_code": code}))
    except Exception:
        res = {}
    if not res.get("success"):
        engine.tracer.emit("decision", intent="account_code", action="not_found", value=code)
        return None
    engine._awaiting_account_code = False
    addresses = res.get("addresses") or []
    primary = next((a for a in addresses if a.get("is_primary")), addresses[0] if addresses else {})
    s.phone_candidate = {
        "customer_id": res.get("customer_id"),
        "name": res.get("name"),
        "address": primary.get("full_address"),
        "city": primary.get("city"),
        "street": primary.get("street"),
        "house": primary.get("house_number"),
        "apartment": primary.get("apartment_number"),
    }
    engine.tracer.emit("decision", intent="account_code", action="found", value=code)
    # A-3 transparency (Andrius 2026-09-07): the agent SAYS which code it
    # heard — the caller hears our action and catches a mistake before we
    # move on. The code path is always scripted (never the narrator's whim);
    # the "ar skambinate dėl" core stays verbatim — the confirm guard keys
    # off it.
    from .identification import phrase as _phrase

    c = s.phone_candidate
    if c.get("street"):
        flat = f", butas {c['apartment']}" if c.get("apartment") else ""
        adresas = f"{c['street']} {c.get('house')}{flat}"
        # B-wave registry: the echo-offer IS the address-offer question
        # (live 2026-09-08: this path bypassed _address_move and the offer
        # went out unregistered).
        from .dialog_registry import register as _q_register

        _q_register(engine, "ident", "address_offer", adresas=adresas)
        return _phrase("account_code_echo_offer", kodas=_speak_code(code), adresas=adresas)
    # The address is OFFERED aloud for confirmation, never assumed.
    return _address_move(engine, s)


def _account_code_rung(engine: Any, s: Any, user_input: str | None):
    """Etalonas №2/№5, PERDIRBTA po gyvų T-5/T-6 (Andrius 2026-09-04: pakopa
    skaičiavo ir PRODUKTYVIUS patikslinimo turn'us, o kodo režimas tapo
    kurčias — kliento adreso/pavardės patikslinimai atsimušdavo į „kodas
    atrodo taip"). Principai:

      * TIKSLINIMAS NĖRA BANDYMAI — pavardės/vietovės/diagnozės ratai
        skaitiklių nekelia; bet koks adreso turinys tuščių skaitiklį nulina.
      * Miestas ne zonoje (Vilnius, Kaunas…) — pasakoma IŠ KARTO, be jokių
        skaitiklių („šiame mieste abonentų nėra — gal Šiauliuose?").
      * Kodo režimas — PASIŪLYMAS, ne spąstai: kodas skaitomas kiekvieną
        turn'ą; ne-kodo TURINYS praleidžiamas į normalią eigą (agentas
        klauso!); tik AIŠKUS „neturiu kodo" veda į sąžiningą pabaigą.
      * Nenorint sakyti adreso: 2 tušti turn'ai → PERSPĖJIMAS (be adreso nei
        išspręsti, nei registruoti negalėsiu), dar 2 → uždarymas
        „nenustatyta gedimo vieta".

    Returns (handled, reply)."""
    import os as _os

    from .identification import phrase

    if not user_input:
        return False, None
    # R3 (live 2026-09-10: "Taip kaip tėtis ir kaip Ignas" went unheard): the
    # caller may START spelling on their own — two "kaip <žodis>" pairs in an
    # address-phase turn ARE a letters answer, no mode needed.
    if (
        not getattr(engine, "_spell_mode", False)
        and user_input.lower().count(" kaip ") >= 2
        and (
            getattr(engine, "_street_attempts", None)
            or "gatv" in (engine._last_agent_question() or "").lower()
        )
    ):
        engine._spell_mode = True
        engine._spell_done = True
        engine.tracer.emit("decision", intent="street_spell", action="client_initiated")
    # NLU wave block 4 (paraidžiui): the spelling answer is read FIRST — the
    # anchor-word first letters narrow the registry by prefix AND fuzzy the
    # last heard garble inside that subset (letters help fuzzy, never replace
    # it — Andrius 2026-09-10); a miss falls to the account-code rung.
    if getattr(engine, "_spell_mode", False):
        engine._spell_mode = False
        prefix = _spell_prefix(user_input)
        _garble = (getattr(engine, "_street_attempts", None) or [None])[-1]
        cand = (
            _street_by_prefix_and_garble(engine, prefix, _garble)
            if len(prefix) >= (1 if _garble else 2)
            else None
        )
        if cand:
            from .dialog_registry import register as _q_register
            from .slots import SlotStatus

            s.profile.street.propose(cand, 0.9, SlotStatus.HEARD)
            engine._addr_unrecognized = 0
            engine._addr_empty_turns = 0
            _q_register(engine, "ident", "address_ask")
            engine.tracer.emit(
                "decision", intent="street_spell", action="matched", value=cand, prefix=prefix
            )
            return True, phrase("spell_result", raides=" ".join(prefix.upper()), gatve=cand)
        engine.tracer.emit("decision", intent="street_spell", action="miss", prefix=prefix)
        engine._awaiting_account_code = True
        engine._code_grace = 0
        from .dialog_registry import register as _q_register

        _q_register(engine, "ident", "account_code")
        return True, phrase("account_code_ask")
    # 0) Kodas girdimas VISADA (ne tik „režime") — klientas gali jį pasakyti
    # bet kada, taip pat po perspėjimo frazės.
    code = _extract_account_code(user_input)
    if code and (getattr(engine, "_awaiting_account_code", False) or "ab" in user_input.lower()):
        reply = _lookup_by_code(engine, s, code)
        if reply is not None:
            return True, reply
        if getattr(engine, "_awaiting_account_code", False):
            # A-3 transparency: say WHAT we heard — the caller sees where
            # the mishearing happened.
            from .dialog_registry import register as _q_register

            _q_register(engine, "ident", "account_code")
            return True, phrase("account_code_miss", kodas=_speak_code(code))
    if getattr(engine, "_awaiting_account_code", False):
        low = user_input.lower()
        explicit_no = any(
            m in low
            for m in (
                "neturiu",
                "nėra jokio",
                "nera jokio",
                "nežinau kodo",
                "nezinau kodo",
                "nesu klientas",
                "nesu abonent",
            )
        )
        if explicit_no:
            s.case_closed = True
            s.closed_reason = "declined"
            engine.tracer.emit("decision", intent="account_code", action="not_client_close")
            return True, phrase("not_client_goodbye")
        # A-banga P3c (gyva #3: „A. B." → LLM haliucinavo „nerastas"): klientas
        # KALBA apie kodą, bet skaitmenų neperskaitėm — scripted pagalba, ne LLM.
        if "kod" in low:
            from .dialog_registry import register as _q_register

            _q_register(engine, "ident", "account_code")
            engine.tracer.emit("decision", intent="account_code", action="retry_help")
            return True, phrase("account_code_retry")
        # Ne kodas, o TURINYS (adresas, pavardė, pasakojimas) — praleidžiam į
        # normalią eigą; po poros tokių turn'ų kodo režimas tyliai užgęsta.
        # NE return: tušti turn'ai toliau artina perspėjimo/uždarymo ribą
        # (kodo režimas jos nebeįšaldo).
        grace = getattr(engine, "_code_grace", 0) + 1
        engine._code_grace = grace
        if grace >= 2:
            engine._awaiting_account_code = False
    if not s.problem_type:
        return False, None
    # HONEST not-exists branch (Andrius 2026-09-10 rev.2): the SAME transcript
    # repeated — the agent hears it consistently, so it heard RIGHT and such
    # a street simply is not in the service area. Say so and draw the client
    # boundary (paslaugos tik savo klientams); code listening arms so an
    # insisting client has a way in.
    if getattr(engine, "_street_not_exists_due", False) and not getattr(
        engine, "_street_not_exists_said", False
    ):
        engine._street_not_exists_due = False
        engine._street_not_exists_said = True
        engine._awaiting_account_code = True
        engine._code_grace = 0
        from .dialog_registry import register as _q_register

        _q_register(engine, "ident", "street_not_exists")
        engine.tracer.emit("decision", intent="street_not_exists", action="say")
        return True, phrase("street_not_exists")
    # 1) Miestas ne aptarnavimo zonoje — IŠ KARTO, vieną kartą. SVARBU:
    # „Vilniaus GATVĖ" yra Šiaulių gatvė, ne miestas — miesto žodis, po kurio
    # eina gatvės indikatorius, yra GATVĖS pavadinimas (gyvas testų lūžis).
    import re as _re

    low = user_input.lower()
    _city_mention = any(
        _re.search(c + r"\w*", low) and not _re.search(c + r"\w*\s+(g\.|g\b|gatv)", low)
        for c in _BIG_CITIES
        if c in low
    )
    if (
        _city_mention
        and "šiaul" not in low
        and "siaul" not in low
        and not getattr(engine, "_city_not_served_said", False)
    ):
        engine._city_not_served_said = True
        from .dialog_registry import register as _q_register

        _q_register(engine, "ident", "city_not_served")
        engine.tracer.emit("decision", intent="account_code", action="city_not_served")
        return True, phrase("city_not_served")
    # 1b) LOOP'as (Andrius: „kai loopas prasideda — galvojama apie kitus
    # būdus"): trys TIKROS gatvės/namo paieškos nesėkmės (tikslinimai —
    # butas/pavardė/vietovė — nesiskaito) → PIRMA paraidžiui, tada kodas.
    if getattr(engine, "_addr_resolve_fails", 0) >= 3:
        engine._addr_resolve_fails = 0
        engine._awaiting_account_code = True
        engine._code_grace = 0
        from .dialog_registry import register as _q_register

        _q_register(engine, "ident", "account_code")
        engine.tracer.emit("decision", intent="account_code", action="ask", reason="resolve_loop")
        return True, phrase("account_code_ask")
    # 2) Skaitikliai. TIKSLINIMO fazė (pavardės klausimas, diagnozės nota,
    # vietovės pasiūlymas) skaitiklių NEliečia.
    last_q = (engine._last_agent_question() or "").lower()
    clarifying = (
        "pavard" in last_q
        # P3 (live 2026-09-07): a question that ECHOES a concrete address
        # (including an LLM-worded one — "Taigi, Tilžės g. 60, butas 3,
        # taip?") — a "Taip." answering it is clarification, not an empty
        # turn. Narrow rule: digit + street word, so "Koks adresas?" and the
        # warning (no digits) cannot freeze the counters.
        or (any(ch.isdigit() for ch in last_q) and ("gatv" in last_q or " g." in last_q))
        or getattr(engine, "_addr_diag_note", None)
        or getattr(engine, "_addr_city_suggestion", None)
    )
    if clarifying:
        return False, None
    # Skaitikliai gyvi tik kai adreso KLAUSIMAS jau nuskambėjo (eval I4:
    # pati problemos frazė „Neveikia internetas" buvo suskaičiuota kaip
    # tuščias bandymas ir perspėjimas iššoko per anksti).
    if not s.anamnesis_asked:
        return False, None
    try:
        limit = int(_os.environ.get("IDENT_MAX_TURNS", "4"))
    except ValueError:
        limit = 4
    # R4 (live 2026-09-10: "Tilžiukos." counted as an EMPTY turn and the call
    # CLOSED on a cooperating caller): when the last question asked for the
    # street/address, a bare word attempt IS address content — a garbled
    # street name, not silence. It also feeds the repeat tracker: the same
    # word coming back arms the letters round.
    street_asked = any(w in last_q for w in ("gatv", "adres", "pavadinim"))
    alpha_attempt = (
        street_asked
        and not _has_address_content(user_input)
        and any(t.strip(".,!?").isalpha() and len(t.strip(".,!?")) >= 4 for t in user_input.split())
    )
    if alpha_attempt:
        _word = max(
            (t.strip(".,!?") for t in user_input.split() if t.strip(".,!?").isalpha()),
            key=len,
        )
        _rep = _register_street_attempt(engine, _word)
        if _rep == "identical" and not getattr(engine, "_street_not_exists_said", False):
            engine._street_not_exists_said = True
            engine._awaiting_account_code = True
            engine._code_grace = 0
            from .dialog_registry import register as _q_register

            _q_register(engine, "ident", "street_not_exists")
            engine.tracer.emit("decision", intent="street_not_exists", action="say")
            return True, phrase("street_not_exists")
    if _has_address_content(user_input) or alpha_attempt:
        engine._addr_empty_turns = 0
        # Turinys yra, bet registras jo VISAI neatpažįsta (nei sloto, nei
        # diagnozės) — po dviejų tokių siūlom kodą.
        if not s.profile.street.value and not getattr(engine, "_addr_diag_note", None):
            n = getattr(engine, "_addr_unrecognized", 0) + 1
            engine._addr_unrecognized = n
            if n >= 2:
                engine._awaiting_account_code = True
                engine._code_grace = 0
                from .dialog_registry import register as _q_register

                _q_register(engine, "ident", "account_code")
                engine.tracer.emit(
                    "decision", intent="account_code", action="ask", reason="unrecognized"
                )
                return True, phrase("account_code_ask")
        else:
            engine._addr_unrecognized = 0
        return False, None
    # 3) Tuščias turn'as (jokio adreso turinio): perspėjimas → uždarymas.
    n = getattr(engine, "_addr_empty_turns", 0) + 1
    engine._addr_empty_turns = n
    if n == max(2, limit - 2) and not getattr(engine, "_addr_warned", False):
        engine._addr_warned = True
        # A-banga P3a (gyva #3): perspėjimas MINI kodą — nuo šio momento kodo
        # klausymas įjungtas (praleidimo semantika turinį saugo).
        engine._awaiting_account_code = True
        engine._code_grace = 0
        from .dialog_registry import register as _q_register

        _q_register(engine, "ident", "address_need")
        engine.tracer.emit("decision", intent="account_code", action="warn")
        return True, phrase("address_need_warning")
    if n >= limit:
        s.case_closed = True
        s.closed_reason = "declined"
        engine.tracer.emit("decision", intent="account_code", action="no_location_close")
        return True, phrase("no_location_goodbye")
    return False, None


def identification_scripted_reply(engine: Any, user_input: str | None) -> str | None:
    """Deterministic identification-ladder replies (2026-07-31, IDENTIFICATION
    ONLY): the mechanical turns are COMPOSED by the engine from the phrases in
    identification.yaml — the LLM repeatedly reordered or skipped them (promised
    a check without the result, relapsed into confirm rounds, skipped the caller
    question, captured 'Taip.' as a name). An off-script caller turn (a question)
    returns None so the LLM answers it; the ladder resumes next turn. Solving and
    free dialogue never come here."""
    s = engine.state
    # P-C (2026-09-08): the walker's 'callback' terminal just closed the case
    # (homework agreed) — the goodbye is scripted, warm and deterministic.
    if getattr(engine, "_callback_goodbye_due", False):
        engine._callback_goodbye_due = False
        from .identification import phrase as _cb_phrase

        return _cb_phrase("callback_goodbye")
    if s.case_closed:
        return None
    from .identification import caller_question, phrase
    from .resolution import is_real_question

    # Adreso KEITIMO patvirtinimas (etalonas №3, Andrius 2026-09-03): kliento
    # užsiminimas apie kitą adresą po identifikacijos NEbeperjungia iš karto —
    # pirma vienas patvirtinimo klausimas; „taip" (ar aiškus naujas adresas)
    # atidaro identifikaciją iš naujo, kitoks atsakymas — liekam prie esamo.
    # №4 (etalonas 2026-09-03): sakosi savininkas kitu vardu — SCRIPTED
    # patikslinimas (naratorius gyvai nurungė notą ir patvirtino „Jūs, Petrai,
    # esate savininkas"; privatumo taisyklė per svarbi improvizacijai). DB
    # vardo frazėje NĖRA; atsakymas kitą turn'ą atnaujina santykį (prefill).
    if getattr(engine, "_holder_clarify_open", False) and not getattr(
        engine, "_holder_clarify_asked", False
    ):
        engine._holder_clarify_asked = True
        from .dialog_registry import register as _q_register

        _q_register(engine, "ident", "holder_clarify")
        engine.tracer.emit("decision", intent="holder_name", action="clarify_ask")
        return phrase("holder_mismatch_clarify")
    # A-2b (Andrius 2026-09-07, live: "negaliu pasakyti, dėl kokio adreso"):
    # the caller ASKS which address the call is about — the CONFIRMED address
    # is not a secret; on the contrary, this is how the caller catches our
    # mistake. Deterministic scripted answer, never the LLM's whim; the
    # phrase itself invites a correction.
    if (
        user_input
        and "adres" in user_input.lower()
        and any(k in user_input.lower() for k in ("kok", "kur"))
        and is_real_question(user_input)
    ):
        if s.customer_id and s.customer_address:
            engine._reopen_reask = False  # the info answer replaces the re-ask
            engine.tracer.emit("decision", intent="address_info", action="disclose")
            return phrase("current_address_info", adresas=s.customer_address)
        if not s.customer_id:
            # A-2R-b follow-up (live 2026-09-07): the question arrived MID
            # identification (after reopen) — say WHAT we are clarifying:
            # the heard address (with the "dėl šio adreso" confirm core the
            # guard keys off), or that we have no address yet.
            p = s.profile
            if p.street.value:
                adr = f"{p.street.value} {p.house.value or ''}".strip()
                engine.tracer.emit("decision", intent="address_info", action="progress")
                return phrase("ident_address_heard", adresas=adr)
            engine.tracer.emit("decision", intent="address_info", action="none_yet")
            return phrase("ident_address_none")
    # This layer ASKS the address-change question; the ANSWER is read by
    # pre_turn_guards (the deterministic turn head) so the solver/walker
    # cannot consume it (live A-2 defect). Only the ask/re-ask side is here.
    pending_reopen = getattr(engine, "_reopen_confirm_pending", None)
    if pending_reopen is not None:
        from .dialog_registry import register as _q_register

        adresas = s.customer_address or "dabartinio adreso"
        if not getattr(engine, "_reopen_confirm_asked", False):
            engine._reopen_confirm_asked = True
            engine._reopen_confirm_asks = 1
            _q_register(engine, "safety", "reopen_confirm", adresas=adresas)
            engine.tracer.emit("decision", intent="reopen_confirm", action="ask")
            return phrase("reopen_confirm", adresas=adresas)
        if getattr(engine, "_reopen_reask", False):
            engine._reopen_reask = False
            engine._reopen_confirm_asks = getattr(engine, "_reopen_confirm_asks", 1) + 1
            _q_register(engine, "safety", "reopen_confirm", adresas=adresas)
            return phrase("repeat_ack") + phrase("reopen_confirm", adresas=adresas)
        return None  # the guards already read the answer; the narrator continues

    # A-banga P1 (Andrius 2026-09-04, gyva #6: „Ne patogu" ignoruotas):
    # negalėjimo-DABAR mini-kopėčios sprendimo fazėje — STOP, išsiaiškinti KAS
    # nepatogu, tada pasiūlyti kelią (registracija / perskambinimas / tęsiam).
    cn_state = getattr(engine, "_cannot_now_state", None)
    if cn_state == "asked" and user_input:
        from .dialog_registry import clear as _q_clear
        from .dialog_registry import register as _q_register

        engine._cannot_now_state = None
        _q_clear(engine, "cannot_now_clarify")
        low_cl = user_input.lower()
        # N2b (live 2026-09-09): "Aš Jums perskambinsiu" IN the clarify answer
        # is the whole decision — close warm right here, no offer round.
        if any(m in low_cl for m in ("perskambin", "paskambinsiu", "pats paskambin")):
            engine._cannot_now_done = True
            s.case_closed = True
            s.closed_reason = "callback"
            engine.tracer.emit("decision", intent="cannot_now", action="callback_close")
            return phrase("callback_goodbye")
        # N2 (live 2026-09-09: "Negaliu, nes esu nenuose" got RESUME and the
        # walker pushed another check): the caller was just asked "ar negalite
        # dabar patikrinti?" — a rambling answer about being away IS a yes.
        # RESUME only on a clear back-to-solving signal; everything else
        # offers the way out.
        resumed = any(
            m in low_cl for m in ("galiu", "radau", "viskas gerai", "veikia", "nereikia", "jau ")
        ) and not any(m in low_cl for m in ("negaliu", "nerandu"))
        if not resumed:
            engine._cannot_now_state = "offered"
            _q_register(engine, "safety", "cannot_now_offer")
            engine.tracer.emit("decision", intent="cannot_now", action="offer")
            return phrase("cannot_now_offer")
        engine.tracer.emit("decision", intent="cannot_now", action="resume")
        return None  # paaiškino kitaip — tęsiam kelią (turinys jau ingest'e)
    if cn_state == "offered" and user_input:
        from .dialog_registry import clear as _q_clear

        engine._cannot_now_state = None
        engine._cannot_now_done = True
        _q_clear(engine, "cannot_now_offer")
        low_cn = user_input.lower()
        if any(
            m in low_cn
            for m in ("perskambin", "paskambinsiu", "pats paskambin", "vėliau", "veliau")
        ):
            s.case_closed = True
            s.closed_reason = "callback"
            engine.tracer.emit("decision", intent="cannot_now", action="callback_close")
            return phrase("callback_goodbye")
        from .resolution import DETECTORS as _DET_CN2
        from .resolution import detect_refuse_or_ticket

        if (
            detect_refuse_or_ticket(user_input) == "demand"
            or _DET_CN2["yes_no"](user_input) == "yes"
            or "registr" in low_cn
            or "meistr" in low_cn
        ):
            from .resolution import STRATEGIES as _STR

            # P-E: the ticket intro must speak the honest state — the caller
            # could not act NOW; nothing was performed.
            if s.resolution is not None:
                s.resolution["escalate_reason"] = (
                    "Klientas negali dabar atlikti veiksmų prie įrenginio."
                )
            engine.tracer.emit("decision", intent="cannot_now", action="ticket")
            engine._begin_ticket_dialogue(_STR["unclear_fault"].step("escalate"))
            return None  # tiketo dialogo intro — kitas žingsnis
        return None
    if (
        cn_state is None
        and not getattr(engine, "_cannot_now_done", False)
        and s.resolution
        and s.customer_id
        and not engine._ticket_stage
        and user_input
    ):
        from .dialog_registry import pack_owns_cannot_now as _pack_cn
        from .resolution import detect_cannot_now as _dcn

        if _dcn(user_input) and not _pack_cn(engine):
            from .dialog_registry import register as _q_register

            engine._cannot_now_state = "asked"
            _q_register(engine, "safety", "cannot_now_clarify")
            engine.tracer.emit("decision", intent="cannot_now", action="clarify_ask")
            return phrase("cannot_now_clarify")

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
    if (
        user_input
        and is_real_question(user_input)
        and (s.problem_type or s.customer_id)
        # Kodo fazės klausimas („o kur jį rasti?") eina į pakopą — retry
        # frazė su UŽUOMINA kur ieškoti ir YRA atsakymas (etalonas №2).
        and not getattr(engine, "_awaiting_account_code", False)
        # NLU wave block 4: "V KAIP Vilnius" is the spelling answer, not a
        # question — the rung's spell reader owns the armed turn; two "kaip"
        # pairs are spelling-shaped even without the mode (client-initiated).
        and not getattr(engine, "_spell_mode", False)
        and user_input.lower().count(" kaip ") < 2
    ):
        return None  # off-script — the LLM answers; guards kept the ladder state
        # (pre-problem questions fall through to the problem GATE below)
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
            # Live 2026-08-21: a garbled opener ("Atsikai, daro") fell to the
            # LLM, which offered the address before any problem was stated.
            # 2026-09-02: the gate grew the L2 classification ladder — see
            # _problem_gate_reply. A commit there (LLM guess accepted) falls
            # THROUGH to the intake ladder the same turn: reaching a problem
            # never ends the call, only never reaching one does.
            _has_addr0 = bool(s.profile.street.value or s.profile.house.value)
            if not _has_addr0:
                reply = _problem_gate_reply(engine, s, user_input)
                if s.problem_type is None:
                    return reply
                # gate commit — continue to anamnesis/address this turn
        p = s.profile
        has_addr = bool(p.street.value or p.house.value)
        # №2/№5 (etalonas 2026-09-03): abonento kodo pakopa — kai adresas
        # neaiškėja, metodas keičiamas; kodo laukimo fazė skaito atsakymą.
        # Telefono kandidato pasiūlymo srautas neskaičiuojamas (jis turi savo
        # patvirtinimo mechaniką).
        if getattr(engine, "_awaiting_account_code", False) or not s.phone_candidate:
            handled, reply = _account_code_rung(engine, s, user_input)
            if handled:
                return reply
        if s.problem_type and not s.anamnesis_asked and not s.preflight_outage and not has_addr:
            # DIALOGO_ETALONAS #2 (Andrius 2026-09-01/03): the OPENING
            # anamnesis QUESTION is gone — capture-first keeps whatever the
            # caller already said ("vakar dingo, po audros"), and the targeted
            # anamnesis lives in the PACKS, asked with telemetry context only
            # when the verdict needs it. A blind "kada dingo? gal po audros?"
            # wasted a turn on every fast-path call (live 2026-09-03: the
            # answer "kaimynai remontą darys" fed nothing — the verdict was a
            # billing block). anamnesis_asked stays as the ladder-live marker
            # (the deterministic address-resolve gate keys off it).
            s.anamnesis_asked = True
            if user_input:
                from .nlu import extract_anamnesis

                read = extract_anamnesis(user_input)
                if read.get("when") not in (None, "nežino") or read.get("trigger"):
                    s.anamnesis_raw = user_input.strip()[:200]
                    s.anamnesis_when = read.get("when")
                    s.anamnesis_trigger = read.get("trigger")
                    engine.tracer.emit(
                        "anamnesis",
                        text=s.anamnesis_raw,
                        when=s.anamnesis_when,
                        trigger=s.anamnesis_trigger,
                        from_opening=True,
                    )
                    engine._opening_heard_note = True
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
                # Closing wave block 2 (live: these were swallowed by the
                # goodbye): payment claims and follow-up asks are CONTENT.
                "sumokėj",
                "sumokej",
                "apmokėj",
                "apmokej",
                "kiek",
                "kada",
                "anks",
                "neveik",
                "kain",
            )
        )
        if wants_more:
            return None  # a question / wants something — the LLM handles it
        # Closing wave block 2 (live 2026-09-08: "Vilma" — the caller's NAME —
        # got a deaf goodbye): a content-bearing turn is NOT a goodbye. Up to
        # two such turns get an LLM reaction (with a directive to react and
        # re-offer the close); the cap keeps garbled goodbyes ("Nusigaro")
        # from looping the wrap-up forever.
        from .resolution import detect_farewell as _df
        from .resolution import is_backchannel as _bc

        content = bool(user_input) and not _df(user_input) and not _bc(user_input)
        n = getattr(engine, "_wrap_content_turns", 0)
        if content and n < 2:
            engine._wrap_content_turns = n + 1
            engine._wrap_react_note = True
            engine.tracer.emit("decision", intent="wrap_up", action="react", turns=n + 1)
            return None  # the narrator reacts to WHAT was said, then re-offers
        s.case_closed = True
        s.closed_reason = "outage" if s.outage_reported else "inform"
        s.is_complete = True
        # aiskumo_salyga (declared in informavimas.yaml): the inform template
        # spoke all its elements before this close — trace it for the audits.
        from .informavimas import clarity_declaration

        _reason = (s.diagnosis.get("network") or {}).get("reason")
        _salyga = clarity_declaration(_reason)
        if _salyga:
            engine.tracer.emit("clarity", reason=_reason, salyga=_salyga, told=engine._news_told)
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
        from .dialog_registry import register as _q_register

        _q_register(engine, "ident", "caller_name")
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
    # Closing wave (2026-09-08): the inform SPEECH lives in
    # knowledge/informavimas.yaml — the template carries the details (debt
    # amount, months, last payment; outage place and ETA) and its own
    # "Patikrinau…" opening, so check_result/billing_extra are not repeated.
    from .informavimas import inform_text

    inf = inform_text(engine, reason)
    if inf:
        engine._result_pending = False
        engine._news_told = True
        engine.tracer.emit("decision", intent="inform", action="template", reason=reason)
        return " ".join([phrase("thanks"), inf, phrase("anything_else")])
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


def _address_move(engine, s):
    """Zone 2 (skriptai -> direktyvos): the transition to the address — offer
    the phone-candidate address or ask for one. In narrator mode the moment
    becomes a goal directive (a smooth hand-over from the problem talk); the
    OFFER question's core stays verbatim ("Ar skambinate dėl X?") because the
    deterministic confirm guard keys off it. Off-switch keeps the scripts."""
    import os as _os

    from .dialog_registry import register as _q_register
    from .identification import offer_phone_address, phrase

    c = s.phone_candidate
    if offer_phone_address() and c and c.get("street") and not s.preflight_outage:
        flat = f", butas {c['apartment']}" if c.get("apartment") else ""
        adresas = f"{c['street']} {c.get('house')}{flat}"
        kind, fallback = "address_offer", phrase("address_offer", adresas=adresas)
    else:
        adresas = None
        kind, fallback = "address_ask", phrase("address_ask")
    _q_register(engine, "ident", kind, adresas=adresas)
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

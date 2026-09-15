"""
Identification flow — the deterministic identification ladder around the pure
helpers in agent/identification.py (phrases, policy) and agent/nlu.py.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of ReactAgent —
the phone preflight, the NLU slot prefill, the accumulated-address DB check, the
identity reopen, and the scripted-ladder reply composer. Functions take (state, rt)
— the call state and the AgentRuntime. tools run through rt.tools (the gateway).
"""

from __future__ import annotations

import logging
from typing import Any

from .contract import limits
from .contract.locale import phrase_or, vocab
from .dialog_utils import last_agent_question
from .faults import verdict_flag
from .trace import trace_note

logger = logging.getLogger(__name__)


def preflight_phone(state: Any, rt: Any) -> None:
    """Look up the caller's number at the START of the call (deterministic).

    Runs once, in code (not via the LLM), so by the customer's first turn the
    phone account — if any — is already known and the agent can offer its
    address for confirmation without a tool round-trip. Stored as an
    UNCONFIRMED candidate (anchor rule), never as a confirmed customer.
    """
    phone = state.identity.caller_phone
    if not phone or phone == "unknown":
        return
    state.identity.preflight_done = True
    try:
        result = rt.tools.run(
            state, rt, "find_customer", {"phone": phone}, reason="preflight_phone", apply=False
        ).data
    except Exception:
        return
    if not result.get("success"):
        rt.tracer.emit("preflight", found=False)
        return
    addresses = result.get("addresses") or []
    primary = next(
        (a for a in addresses if a.get("is_primary")),
        addresses[0] if addresses else {},
    )
    state.identity.phone_candidate = {
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
    rt.tracer.emit("preflight", found=True, customer_id=result.get("customer_id"))

    # Proactive mass-outage awareness (roadmap 6b): if this caller's street
    # has an active outage, remember it so the FIRST reply can inform right
    # away — no full identification needed (everyone at that street is down).
    try:
        outage = rt.tools.run(
            state,
            rt,
            "check_outages",
            {"customer_id": result.get("customer_id")},
            reason="preflight_outage",
            apply=False,
        ).data
    except Exception:
        return
    if outage.get("affected") and outage.get("active_outages"):
        first = outage["active_outages"][0]
        eta = first.get("estimated_resolution") or ""
        state.identity.preflight_outage = {
            "street": first.get("street"),
            "eta": eta[11:16] if len(eta) >= 16 else eta,  # HH:MM, voice-friendly
            "description": first.get("description"),
        }
        rt.tracer.emit("preflight_outage", street=first.get("street"))


def prefill_slots_from_text(state: Any, rt: Any, text: str) -> None:
    """Deterministic NLU Track A: extract the address from the caller's turn and
    propose it into the slots BEFORE the LLM runs (docs/pokalbio_variklis.md §4).

    The reading is the high-confidence floor — registry-validated street +
    normalized numbers — so the slots get a reliable source independent of the
    LLM. Proposed as HEARD; resolve_address upgrades a confirmed hit to
    RESOLVED. Best-effort: any failure (DB, import) silently no-ops the turn.
    """
    s = state
    # Raw utterance buffer: keep every caller turn verbatim so nothing is lost
    # when VAD/STT splits an utterance into fragments. Feeds the LLM
    # reconciliation fact when the deterministic slots stall (see
    # _state_facts_block), and the future async silent re-processing.
    if text and text.strip():
        s.intake.heard_utterances.append(text.strip())

    # Problem classification (R1) — independent of the registry/DB, so it runs
    # even if address extraction fails. A revisable hypothesis: a clearer later
    # statement overrides (docs/pokalbio_variklis.md §12.2).
    try:
        from .faults import BOUNDARY_POLICIES, problem_policy
        from .nlu import classify_problem, extract_symptoms

        problem = classify_problem(text)
        # №4 continued (reference dialogue 2026-09-03): the answer to the holder
        # clarification updates the relation („žmonos vardu sudaryta" → family) — one read.
        if state.identity.holder_clarify_open and state.identity.holder_clarify_asked and text:
            state.identity.holder_clarify_open = False
            state.identity.holder_clarify_asked = False
            from .identification import detect_caller_relation as _dcr

            _rel = _dcr(text)
            if _rel and _rel != "unknown":
                s.identity.caller_relation = _rel
                rt.tracer.emit(
                    "caller_intro", name=s.identity.caller_name, relation=_rel, clarified=True
                )
        # Competence policy (2026-09-02): not_ours/chat types NEVER become
        # the call's problem_type — the gate answers with the declared boundary
        # phrase instead of opening identification ("kodėl tokia sąskaita?" is
        # not a fault). Stashed one-shot for the reply layer.
        if problem and problem_policy(problem) in BOUNDARY_POLICIES:
            if s.intake.problem_type is None:
                state.intake.boundary_problem = problem
            problem = None
        if problem:
            # A (Andrius 2026-08-21): the PRIMARY goal is the caller's stated
            # call reason and NEVER flips mid-call (an STT garble switched it
            # to billing live). Later mentions of other problems become
            # SECONDARY — noted, asked about at the end, listed on the ticket.
            if s.intake.problem_type is None:
                s.intake.problem_type = problem
            elif (
                problem != s.intake.problem_type
                and s.resolution.procedure is not None
                and not s.closing.case_closed
                and not state.ticket.stage
                and len((text or "").split()) >= 3  # garbles ("Žemės gatvės") are not complaints
            ):
                if not any(x.get("type") == problem for x in s.intake.secondary_problems):
                    s.intake.secondary_problems.append(
                        {
                            "type": problem,
                            "text": (text or "").strip()[:120],
                            "turn": s.dialog.turn_count,
                        }
                    )
            elif not s.identity.customer_id and s.resolution.procedure is None:
                s.intake.problem_type = problem  # early self-correction is fine
        # Revisable: a clearer later mention overrides an earlier reading.
        s.intake.symptoms.update(extract_symptoms(text))
    except Exception:  # pragma: no cover - best-effort
        pass

    # Phase gate (Andrius 2026-08-13): once the caller IS identified, numbers
    # and street-like words are CONTENT ("nei 1 lemputė nedega"), never an
    # address — stop extracting entirely; an address CORRECTION reopens
    # identification through its own path (_reopen_identification) instead.
    if s.identity.customer_id:
        return

    # №2 (reference dialogue 2026-09-03): while waiting for the code the address
    # reader stays SILENT — code digits are not a house number, and a fuzzy street
    # search over such phrases („Neturiu jokio KODO" → „Sodo g.", live I5) only
    # pollutes the slots.
    # NLU wave block 2 (live 2026-09-07: "Šiauliai, Tilžės gatvė 60, butas 3"
    # was swallowed in code mode): a FULL dictation — an explicit street WORD
    # in the turn — wakes the reader; bare digits stay silenced (the code).
    if state.identity.account_code_mode:
        low_cd = (text or "").lower()
        if not any(w in low_cd for w in vocab("street_words")):
            return
    # NLU wave block 4: the spelling turn carries LETTERS ("K kaip Kaunas"),
    # not an address — the fuzzy reader would turn the anchor words into a
    # city/street; the rung's spell reader owns this turn.
    if state.identity.spell_mode:
        return
    # NLU wave D1 (live 2026-09-10: STT invented "Žeimių g.", the slot locked
    # at conf 1.0 and the ladder pushed Ginkūnai for THREE turns over "aš
    # apie Žeimių gatvę nieko NESAKIAU"): a denial naming the heard street
    # DROPS it — and counts as a real miss on the road to the spelling round.
    denied_street = None
    _low_d = (text or "").lower()
    if s.identity.profile.street.value and any(m in _low_d for m in vocab("street_denial")):
        from .evidence import _fold as _fd

        _st = _fd(str(s.identity.profile.street.value).replace(" g.", ""))[:5]
        if _st and _st in _fd(text or ""):
            from .slots import Slot as _Slot

            denied_street = _fd(str(s.identity.profile.street.value))
            s.identity.profile.street = _Slot()
            s.identity.profile.house = _Slot()
            state.identity.address_resolve_failures = state.identity.address_resolve_failures + 1
            state.turn.address_lookup_note = None
            rt.tracer.emit(
                "decision",
                intent="street_denied",
                action="slot_dropped",
                fails=state.identity.address_resolve_failures,
            )
            # NO return: the sentence may also carry a CORRECTION ("nesakiau Žeimių,
            # sakiau TILŽĖS gatvė 60") — reading continues, we just no longer
            # offer the denied street (see propose below).
    # Address-evidence gate: only scan the turn for an address when it plausibly
    # CONTAINS one — a digit or an address word in the utterance, or the agent just
    # asked for the address. Without this, fuzzy street matching read an ADDRESS out
    # of the anamnesis answer ("po AUDROS" -> "Aušros g.") and the bogus street slot
    # blocked the phone-address offer, derailing identification (observed).
    # Locality suggestion WIRING (live T-5, Andrius: "the agent suggested and
    # the caller confirmed — another region is checked"): the resolver said
    # „Žeimių g. yra Ginkūnuose", the caller confirms (or names the village) —
    # the city slot switches and the next lookup runs THERE, not in Šiauliai.
    sug = state.identity.suggested_city
    if sug and text:
        from .evidence import _fold as _fold_sug
        from .resolution import DETECTORS as _DET

        mentioned = _fold_sug(str(sug))[:5] in _fold_sug(text)
        if mentioned or _DET["yes_no"](text) == "yes":
            from .slots import SlotStatus as _SS

            s.identity.profile.city.propose(str(sug), 0.95, _SS.RESOLVED)
            state.identity.suggested_city = None
            rt.tracer.emit("decision", intent="city_suggestion", action="accepted", value=str(sug))

    low = (text or "").lower()
    has_addr_evidence = any(ch.isdigit() for ch in low) or any(
        w in low for w in vocab("address_words")
    )
    if not has_addr_evidence:
        q = (last_agent_question(state) or "").lower()
        asked_address = any(w in q for w in vocab("address_question_words"))
        if not asked_address:
            return  # no address in sight — do not fuzzy-match one into the slots
    try:
        from .nlu import extract_address
        from .slots import SlotStatus

        registry = rt.tools.address_registry()
        streets, localities = registry.streets, registry.localities
        reading = extract_address(text, streets, localities)
    except Exception:  # pragma: no cover - best-effort, never break a turn
        logger.debug("NLU prefill failed", exc_info=True)
        return

    p = s.identity.profile
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
    _denied = denied_street
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
    # №2 (reference dialogue 2026-09-03): THIS turn made address progress — the
    # subscriber-code rung counter resets (an address dictated in parts must never
    # slide into the code question). Progress only counts with REAL address
    # Address PROGRESS resets the rung counters (2026-09-04 rework: the
    # counters live in _account_code_rung; this is only the progress signal).
    _evid = any(ch.isdigit() for ch in low) or any(w in low for w in vocab("address_words"))
    if _evid and (reading.street or reading.house or reading.apartment):
        state.identity.address_empty_turns = 0
        state.identity.address_unrecognized_turns = 0

    # If the caller names a DIFFERENT street than the pre-flight outage was
    # for, that outage is not theirs — drop it so its proactive instruction
    # stops polluting the rest of the call (observed: the agent kept
    # apologising and re-mentioning the outage after the caller switched
    # streets).
    if (
        reading.street
        and s.identity.preflight_outage
        and reading.street != s.identity.preflight_outage.get("street")
    ):
        s.identity.preflight_outage = None

    rt.tracer.emit(
        "nlu",
        problem=s.intake.problem_type,
        city=reading.city,
        street=reading.street,
        house=reading.house,
        apartment=reading.apartment,
        confidence=round(reading.street_confidence, 2),
    )

    # DB-ground everything heard so far (any order, across fragments).
    revalidate_accumulated_address(state, rt)


def revalidate_accumulated_address(state: Any, rt: Any) -> None:
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
    state.turn.db_address_note = None
    s = state
    if s.identity.customer_id or not s.identity.profile.street.value:
        return
    p = s.identity.profile
    args: dict[str, str] = {"street": p.street.value}
    if p.city.value:
        args["city"] = p.city.value
    if p.house.value:
        args["house_number"] = p.house.value
    if p.apartment.value:
        args["apartment_number"] = p.apartment.value
    try:
        res = rt.tools.run(
            state, rt, "resolve_address", args, reason="revalidate_address", apply=False
        ).data
    except Exception:  # pragma: no cover - best-effort, never break a turn
        return
    hint = res.get("hint")
    if hint:
        state.turn.db_address_note = (
            f"- DB CHECK (everything heard so far → {args}): {hint} "
            "Act on THIS (the DB), not on the last thing you misheard; if it is a "
            "match, confirm that exact address; if a part is missing/unclear, ask "
            "only for it. Do NOT read out a list of street names for the caller to "
            "pick from — if the street is unclear, ask them to repeat it."
        )


def reopen_identification(state: Any, rt: Any, user_input: str) -> None:
    """The caller corrected the address AFTER identification — drop the identity and
    every per-account conclusion; keep only the conversation. The router sends the
    next turn back to address_validation (customer_id is None again)."""
    s = state
    trace_note(
        rt.tracer,
        state,
        "reopen_identity",
        f"caller says a DIFFERENT address; dropping {s.identity.customer_id}",
        level="warn",
    )
    s.identity.customer_id = None
    s.identity.customer_name = None
    s.identity.customer_address = None
    s.identity.address_confirmed = False
    s.resolution.procedure = None
    s.diagnosis.verdicts.clear()
    s.diagnosis.hypothesis = None
    s.diagnosis.failed_hypotheses.clear()
    s.diagnosis.rejected_hypotheses.clear()
    s.diagnosis.pivoted_from = None
    s.diagnosis.outage_reported = False
    # Ledger + its machinery (review 2026-08-07): the EVIDENCE belongs to the
    # dropped account — stale telemetry facts (the old verdict!) must never
    # survive an address correction. The ticket dialogue, ask counters and
    # deviation streak reset with it; the thinker gets a clean slate too.
    s.diagnosis.evidence.clear()
    # A-2R (live 2026-09-07): the background telemetry read belongs to the
    # DROPPED account — after reopen it kept flooding the cleared diagnosis/
    # hypothesis back in and the narrator drove the old analysis question.
    # Thrown away with everything else.
    state.turn.bg_diagnosis = None
    # B-wave registry: the whole dialogue restarts — no question survives.
    state.dialog.active_question = None
    # A-2R follow-up (Andrius 2026-09-07): on an address change EVERYTHING
    # restarts — only the caller's name and the problem survive (plus the
    # caller's own story: it describes the REAL place). The old phone
    # candidate is not offered again (the ladder would re-offer the dropped
    # address), and the identification counters and the account-code mode
    # return to a clean slate.
    s.identity.phone_candidate = None
    state.identity.account_code_mode = False
    state.identity.account_code_grace_turns = 0
    state.identity.address_empty_turns = 0
    state.identity.address_unrecognized_turns = 0
    state.identity.address_resolve_failures = 0
    state.identity.suggested_city = None
    state.diagnosis.evidence_ask_counts.clear()
    state.diagnosis.pending_evidence_key = None
    state.diagnosis.evidence_conflict = None
    state.diagnosis.evidence_conflict_asked_key = None
    state.turn.side_topic_active = False
    state.dialog.side_topic_streak = 0
    state.ticket.stage = None
    state.ticket.context = None
    state.resolution.bridge_offered = False
    state.resolution.drive_disabled = False
    state.resolution.drive_repeats = 0
    state.diagnosis.findings_announced = False
    state.diagnosis.pending_announcement = ""
    state.resolution.escalate_clarify_asked = False
    state.resolution.escalate_clarify_due = False
    state.ticket.resume_fix_note = False
    state.diagnosis.facts_recap_state = ""
    state.diagnosis.refute_confirm_state = ""
    state.turn.done_report_key = None
    state.resolution.bridge_plug_reported = False
    state.resolution.bridge_fail_stage = 0
    state.ticket.bridge_fail_note = None
    state.diagnosis.revived_evidence_keys = []
    from .slots import ClientProfileState

    s.identity.profile = ClientProfileState()
    state.turn.db_address_note = None
    state.diagnosis.news_delivered = False  # a new address may carry different news
    state.identity.result_pending = False
    state.dialog.end_confirm_pending = False
    state.dialog.resume_hold_due = False
    state.resolution.bridge_bound = False  # a different account starts clean
    # Re-extract address parts from THIS utterance (the correction often carries
    # the new address: "ne, skambinu dėl Dainų 5").
    prefill_slots_from_text(state, rt, user_input)
    state.turn.reopen_note = True


def _problem_gate_reply(state: Any, rt: Any, s: Any, user_input: str) -> str | None:
    """Problem GATE with the classification cascade (DIALOGO_ETALONAS,
    2026-09-02). No identification until an in-scope problem is reached:

      1. a pending explicit-confirm guess: „taip" commits (problem_type set,
         caller falls through to the intake ladder THIS turn);
      2. an L1-recognized boundary type (not_ours/chat) gets its
         file-declared boundary reply — competence stated, no identification;
      3. L2: the LLM reads the CONTEXT against the catalog — solve with
         high confidence commits (implicit confirmation), medium asks the
         type's confirm question, a boundary type answers its reply;
      4. otherwise the old ladder: scripted ask x2, narrator directive, and
         only after ~5 fruitless exchanges the polite close. Reaching a
         problem at ANY rung reopens the flow — the counter never kills a
         conversation that is moving forward."""
    import os as _os

    from .contract.locale import phrase
    from .faults import problem_boundary_reply, problem_confirm_question, problem_policy
    from .resolution import DETECTORS, is_real_question

    # 1) the caller answers last turn's "Ar gerai suprantu — …?"
    pg = state.intake.problem_guess
    if pg is not None:
        state.intake.problem_guess = None
        if DETECTORS["yes_no"](user_input) == "yes":
            s.intake.problem_type = pg
            rt.tracer.emit("decision", intent="problem_gate", action="guess_confirmed", value=pg)
            return None  # committed — the intake ladder continues this turn
        # a "ne"/correction falls through; a NAMED problem was already read
        # by the ingest (then this gate is not even entered)
    # 2) boundary type recognized by the trigger layer this turn
    bp = state.intake.boundary_problem
    if bp is not None:
        state.intake.boundary_problem = None
        state.intake.ask_problem_count = state.intake.ask_problem_count + 1
        rt.tracer.emit("decision", intent="problem_gate", action="boundary", value=bp)
        return problem_boundary_reply(bp) or phrase("identification.ask_problem")
    p_asks = state.intake.ask_problem_count
    state.intake.ask_problem_count = p_asks + 1
    asking = "?" in user_input or is_real_question(user_input)
    # N limit (Andrius 2026-09-03): not a customer / unclear situation — after
    # GATE_MAX_TURNS fruitless exchanges a polite close WITHOUT a ticket
    # (a ticket without customer_id is mechanically impossible). Configurable knob.
    gate_max = limits.get("problem_gate_max_turns")
    if p_asks + 1 >= gate_max:
        s.closing.case_closed = True
        s.closing.closed_reason = "declined"
        rt.tracer.emit("decision", intent="problem_gate", action="close")
        return phrase("identification.no_problem_goodbye")
    # 3) L2 — context classification against the file catalog. The LLM reads
    # the ACCUMULATED tail, not just this turn (2026-09-02, Andrius: "as the
    # information adds up, understanding comes" — VAD/STT splits a story into
    # fragments, but the meaning lives across them: „Oras kažkoks netoks." +
    # „gal dėl to neturiu interneto?" is ONE thought).
    if _os.getenv("CLASSIFIER", "on").lower() != "off":
        from .nlu import classify_problem_llm

        tail = [
            u
            for u in getattr(s.intake, "heard_utterances", [])[
                -limits.get("problem_classifier_heard_tail") :
            ]
            if u
        ]
        ctx = " ".join(tail)[-400:] or (user_input or "")
        label, conf = classify_problem_llm(ctx, model=rt.config.model)
        if label:
            pol = problem_policy(label)
            rt.tracer.emit(
                "decision",
                intent="problem_gate",
                action="llm_guess",
                value=label,
                reason=f"{pol}:{conf:.2f}",
            )
            if pol in ("solve", "register"):
                if conf >= limits.get("problem_llm_commit_confidence"):
                    s.intake.problem_type = label  # implicit confirmation — the
                    return None  # narrator acknowledges it naturally
                if conf >= limits.get("problem_llm_confirm_confidence"):
                    state.intake.problem_guess = label
                    q = problem_confirm_question(label)
                    if q:
                        return q
            elif conf >= limits.get(
                "problem_llm_confirm_confidence"
            ):  # not_ours / chat from context
                return problem_boundary_reply(label) or phrase("identification.ask_problem")
    # 4) the pre-cascade ladder
    if p_asks < limits.get("problem_gate_scripted_asks") and not asking:
        return phrase("identification.ask_problem")
    if _os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on":
        state.turn.directives.ident = {
            "kind": "problem_gate",
            "adresas": None,
            "fallback": phrase("identification.ask_problem"),
        }
        return None  # the narrator words it (isolated directive turn)
    if asking:
        return None  # scripted mode: a question goes to the LLM
    return phrase("identification.ask_problem")


def _looks_like_address(text: str | None) -> bool:
    """A reply that itself NAMES an address (street word or a digit) — counts
    as a yes to 'ar tikrai kitas adresas?'."""
    low = (text or "").lower()
    return any(ch.isdigit() for ch in low) or any(w in low for w in vocab("address_named_words"))


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


def _has_address_content(text: str | None) -> bool:
    """The turn CARRIES address material (a digit, a street word, a place) —
    such a turn is never a 'fruitless' one, whatever the resolver said."""
    low = (text or "").lower()
    return any(ch.isdigit() for ch in low) or any(
        w in low for w in (*vocab("address_content_words"), *vocab("served_city_stems"))
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
    anchor = vocab("spell_anchor")[0]
    if anchor in toks:
        for i, t in enumerate(toks):
            if t != anchor:
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


def _register_street_attempt(state: Any, rt: Any, garble: str) -> str | None:
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
    attempts = state.identity.street_attempts or []
    verdict: str | None = None
    for prev in attempts:
        if prev == g:
            verdict = "identical"
            break
        if street_match_score(g, prev) >= 0.55:
            verdict = "similar"
    attempts.append(g)
    state.identity.street_attempts = attempts[-4:]
    return verdict


def _street_by_prefix_and_garble(
    state: Any, rt: Any, prefix: str, garble: str | None
) -> str | None:
    """The letters as a FUZZY FILTER (Andrius 2026-09-10): the registry is
    narrowed to streets starting with the spelled prefix, and the HEARD
    garble is fuzzy-matched inside that small subset with a LOWERED bar —
    letter + garble together beat either alone. Without a garble, the
    shortest prefix match wins (the caller spelled the name itself)."""
    from .evidence import _fold
    from .nlu import street_match_score

    streets = rt.tools.address_registry().streets
    want = _fold(prefix)
    subset = [st for st in streets if _fold(st).startswith(want)]
    if not subset:
        return None
    if garble:
        best = max(subset, key=lambda st: street_match_score(garble, st))
        if street_match_score(garble, best) >= 0.4:
            return best
    return min(subset, key=len)


def _street_by_prefix(state: Any, rt: Any, prefix: str) -> str | None:
    """The registry street whose folded name starts with the spelled prefix —
    the shortest match wins (the caller spelled the NAME, not the suffix)."""
    from .evidence import _fold

    streets = rt.tools.address_registry().streets
    want = _fold(prefix)
    matches = [st for st in streets if _fold(st).startswith(want)]
    if not matches:
        return None
    return min(matches, key=len)


def _lookup_by_code(state: Any, rt: Any, s: Any, code: str):
    """find_customer(account_code) -> candidate + the aloud address offer, or
    None when the code is not in the DB."""
    try:
        res = rt.tools.run(
            state, rt, "find_customer", {"account_code": code}, reason="account_code", apply=False
        ).data
    except Exception:
        res = {}
    if not res.get("success"):
        rt.tracer.emit("decision", intent="account_code", action="not_found", value=code)
        return None
    state.identity.account_code_mode = False
    addresses = res.get("addresses") or []
    primary = next((a for a in addresses if a.get("is_primary")), addresses[0] if addresses else {})
    s.identity.phone_candidate = {
        "customer_id": res.get("customer_id"),
        "name": res.get("name"),
        "address": primary.get("full_address"),
        "city": primary.get("city"),
        "street": primary.get("street"),
        "house": primary.get("house_number"),
        "apartment": primary.get("apartment_number"),
    }
    rt.tracer.emit("decision", intent="account_code", action="found", value=code)
    # A-3 transparency (Andrius 2026-09-07): the agent SAYS which code it
    # heard — the caller hears our action and catches a mistake before we
    # move on. The code path is always scripted (never the narrator's whim);
    # the "ar skambinate dėl" core stays verbatim — the confirm guard keys
    # off it.
    from .contract.locale import phrase as _phrase

    c = s.identity.phone_candidate
    if c.get("street"):
        flat = f", butas {c['apartment']}" if c.get("apartment") else ""
        adresas = f"{c['street']} {c.get('house')}{flat}"
        # B-wave registry: the echo-offer IS the address-offer question
        # (live 2026-09-08: this path bypassed _address_move and the offer
        # went out unregistered).
        from .dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "address_offer", address=adresas)
        return _phrase(
            "identification.account_code_echo_offer", code=_speak_code(code), address=adresas
        )
    # The address is OFFERED aloud for confirmation, never assumed.
    return _address_move(state, rt, s)


def _account_code_rung(state: Any, rt: Any, s: Any, user_input: str | None):
    """Reference dialogue №2/№5, REWORKED after live T-5/T-6 (Andrius 2026-09-04:
    the rung also counted PRODUCTIVE clarification turns, and code mode went
    deaf — the caller's address/surname clarifications bounced off „kodas
    atrodo taip"). Principles:

      * CLARIFYING IS NOT AN ATTEMPT — surname/locality/diagnosis rounds do
        not raise the counters; any address content resets the empty counter.
      * City outside the zone (Vilnius, Kaunas…) — said AT ONCE, without any
        counters („šiame mieste abonentų nėra — gal Šiauliuose?").
      * Code mode is an OFFER, not a trap: the code is read every turn;
        non-code CONTENT passes through to the normal flow (the agent
        listens!); only a CLEAR „neturiu kodo" leads to an honest ending.
      * Unwilling to give the address: 2 empty turns → WARNING (without an
        address I can neither solve nor register), 2 more → close
        „nenustatyta gedimo vieta".

    Returns (handled, reply)."""

    from .contract.locale import phrase

    if not user_input:
        return False, None
    # R3 (live 2026-09-10: "Taip kaip tėtis ir kaip Ignas" went unheard): the
    # caller may START spelling on their own — two "kaip <word>" pairs in an
    # address-phase turn ARE a letters answer, no mode needed.
    if (
        not state.identity.spell_mode
        and user_input.lower().count(f" {vocab('spell_anchor')[0]} ") >= 2
        and (
            state.identity.street_attempts
            or any(
                w in (last_agent_question(state) or "").lower()
                for w in vocab("street_question_words")
            )
        )
    ):
        state.identity.spell_mode = True
        rt.tracer.emit("decision", intent="street_spell", action="client_initiated")
    # NLU wave block 4 (letter by letter): the spelling answer is read FIRST — the
    # anchor-word first letters narrow the registry by prefix AND fuzzy the
    # last heard garble inside that subset (letters help fuzzy, never replace
    # it — Andrius 2026-09-10); a miss falls to the account-code rung.
    if state.identity.spell_mode:
        state.identity.spell_mode = False
        prefix = _spell_prefix(user_input)
        _garble = (state.identity.street_attempts or [None])[-1]
        cand = (
            _street_by_prefix_and_garble(state, rt, prefix, _garble)
            if len(prefix) >= (1 if _garble else 2)
            else None
        )
        if cand:
            from .dialog_registry import register as _q_register
            from .slots import SlotStatus

            s.identity.profile.street.propose(cand, 0.9, SlotStatus.HEARD)
            state.identity.address_unrecognized_turns = 0
            state.identity.address_empty_turns = 0
            _q_register(state, rt, "ident", "address_ask")
            rt.tracer.emit(
                "decision", intent="street_spell", action="matched", value=cand, prefix=prefix
            )
            return True, phrase(
                "identification.spell_result", letters=" ".join(prefix.upper()), street=cand
            )
        rt.tracer.emit("decision", intent="street_spell", action="miss", prefix=prefix)
        state.identity.account_code_mode = True
        state.identity.account_code_grace_turns = 0
        from .dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "account_code")
        return True, phrase("identification.account_code_ask")
    # 0) The code is heard ALWAYS (not only "in mode") — the caller may say it
    # at any time, including after the warning phrase.
    code = _extract_account_code(user_input)
    if code and (state.identity.account_code_mode or "ab" in user_input.lower()):
        reply = _lookup_by_code(state, rt, s, code)
        if reply is not None:
            return True, reply
        if state.identity.account_code_mode:
            # A-3 transparency: say WHAT we heard — the caller sees where
            # the mishearing happened.
            from .dialog_registry import register as _q_register

            _q_register(state, rt, "ident", "account_code")
            return True, phrase("identification.account_code_miss", code=_speak_code(code))
    if state.identity.account_code_mode:
        low = user_input.lower()
        explicit_no = any(m in low for m in vocab("no_account_code"))
        if explicit_no:
            s.closing.case_closed = True
            s.closing.closed_reason = "declined"
            rt.tracer.emit("decision", intent="account_code", action="not_client_close")
            return True, phrase("identification.not_client_goodbye")
        # A-wave P3c (live #3: „A. B." → the LLM hallucinated „nerastas"): the caller
        # TALKS about the code but we read no digits — scripted help, not the LLM.
        if any(m in low for m in vocab("account_code_words")):
            from .dialog_registry import register as _q_register

            _q_register(state, rt, "ident", "account_code")
            rt.tracer.emit("decision", intent="account_code", action="retry_help")
            return True, phrase("identification.account_code_retry")
        # Not a code but CONTENT (address, surname, story) — pass it through to
        # the normal flow; after a couple of such turns code mode quietly turns off.
        # NO return: empty turns keep moving toward the warning/close limit
        # (code mode no longer freezes it).
        grace = state.identity.account_code_grace_turns + 1
        state.identity.account_code_grace_turns = grace
        if grace >= limits.get("account_code_grace_turns"):
            state.identity.account_code_mode = False
    if not s.intake.problem_type:
        return False, None
    # HONEST not-exists branch (Andrius 2026-09-10 rev.2): the SAME transcript
    # repeated — the agent hears it consistently, so it heard RIGHT and such
    # a street simply is not in the service area. Say so and draw the client
    # boundary (services for our own customers only); code listening arms so an
    # insisting client has a way in.
    if state.identity.street_not_exists_due and not state.identity.street_not_exists_said:
        state.identity.street_not_exists_due = False
        state.identity.street_not_exists_said = True
        state.identity.account_code_mode = True
        state.identity.account_code_grace_turns = 0
        from .dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "street_not_exists")
        rt.tracer.emit("decision", intent="street_not_exists", action="say")
        return True, phrase("identification.street_not_exists")
    # 1) City outside the service area — AT ONCE, only once. IMPORTANT:
    # „Vilniaus GATVĖ" is a street in Šiauliai, not a city — a city word followed
    # by a street marker is a STREET name (a live test break).
    import re as _re

    low = user_input.lower()
    _city_mention = any(
        _re.search(c + r"\w*", low) and not _re.search(c + r"\w*\s+(g\.|g\b|gatv)", low)
        for c in vocab("big_city_stems")
        if c in low
    )
    if (
        _city_mention
        and not any(c in low for c in vocab("served_city_stems"))
        and not state.identity.city_not_served_said
    ):
        state.identity.city_not_served_said = True
        from .dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "city_not_served")
        rt.tracer.emit("decision", intent="account_code", action="city_not_served")
        return True, phrase("identification.city_not_served")
    # 1b) LOOP (Andrius: "when a loop starts — think of other ways"): three
    # REAL street/house lookup failures (clarifications — apartment/surname/
    # locality — do not count) → FIRST letter by letter, then the code.
    if state.identity.address_resolve_failures >= limits.get("address_resolve_failures_max"):
        state.identity.address_resolve_failures = 0
        state.identity.account_code_mode = True
        state.identity.account_code_grace_turns = 0
        from .dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "account_code")
        rt.tracer.emit("decision", intent="account_code", action="ask", reason="resolve_loop")
        return True, phrase("identification.account_code_ask")
    # 2) Counters. The CLARIFICATION phase (surname question, diagnosis note,
    # locality suggestion) does NOT touch the counters.
    last_q = (last_agent_question(state) or "").lower()
    clarifying = (
        any(w in last_q for w in vocab("surname_words"))
        # P3 (live 2026-09-07): a question that ECHOES a concrete address
        # (including an LLM-worded one — "Taigi, Tilžės g. 60, butas 3,
        # taip?") — a "Taip." answering it is clarification, not an empty
        # turn. Narrow rule: digit + street word, so "Koks adresas?" and the
        # warning (no digits) cannot freeze the counters.
        or (
            any(ch.isdigit() for ch in last_q)
            and any(w in last_q for w in vocab("street_mark_words"))
        )
        or state.turn.address_lookup_note
        or state.identity.suggested_city
    )
    if clarifying:
        return False, None
    # Counters are live only once the address QUESTION has been asked (eval I4:
    # the problem phrase itself „Neveikia internetas" was counted as an
    # empty attempt and the warning fired too early).
    if not s.intake.anamnesis_asked:
        return False, None
    limit = limits.get("ident_max_empty_turns")
    # R4 (live 2026-09-10: "Tilžiukos." counted as an EMPTY turn and the call
    # CLOSED on a cooperating caller): when the last question asked for the
    # street/address, a bare word attempt IS address content — a garbled
    # street name, not silence. It also feeds the repeat tracker: the same
    # word coming back arms the letters round.
    street_asked = any(w in last_q for w in vocab("street_asked_words"))
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
        _rep = _register_street_attempt(state, rt, _word)
        if _rep == "identical" and not state.identity.street_not_exists_said:
            state.identity.street_not_exists_said = True
            state.identity.account_code_mode = True
            state.identity.account_code_grace_turns = 0
            from .dialog_registry import register as _q_register

            _q_register(state, rt, "ident", "street_not_exists")
            rt.tracer.emit("decision", intent="street_not_exists", action="say")
            return True, phrase("identification.street_not_exists")
    if _has_address_content(user_input) or alpha_attempt:
        state.identity.address_empty_turns = 0
        # There is content, but the registry does NOT recognise it at all (no
        # slot, no diagnosis) — after two such turns we offer the code.
        if not s.identity.profile.street.value and not state.turn.address_lookup_note:
            n = state.identity.address_unrecognized_turns + 1
            state.identity.address_unrecognized_turns = n
            if n >= limits.get("address_unrecognized_turns_max"):
                state.identity.account_code_mode = True
                state.identity.account_code_grace_turns = 0
                from .dialog_registry import register as _q_register

                _q_register(state, rt, "ident", "account_code")
                rt.tracer.emit(
                    "decision", intent="account_code", action="ask", reason="unrecognized"
                )
                return True, phrase("identification.account_code_ask")
        else:
            state.identity.address_unrecognized_turns = 0
        return False, None
    # 3) Empty turn (no address content): warning → close.
    n = state.identity.address_empty_turns + 1
    state.identity.address_empty_turns = n
    if (
        n == max(limits.get("ident_warn_min_empty_turns"), limit - 2)
        and not state.identity.address_warned
    ):
        state.identity.address_warned = True
        # A-wave P3a (live #3): the warning MENTIONS the code — from now on code
        # listening is on (the pass-through semantics keep the content).
        state.identity.account_code_mode = True
        state.identity.account_code_grace_turns = 0
        from .dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "address_need")
        rt.tracer.emit("decision", intent="account_code", action="warn")
        return True, phrase("identification.address_need_warning")
    if n >= limit:
        s.closing.case_closed = True
        s.closing.closed_reason = "declined"
        rt.tracer.emit("decision", intent="account_code", action="no_location_close")
        return True, phrase("identification.no_location_goodbye")
    return False, None


def identification_scripted_reply(state: Any, rt: Any, user_input: str | None) -> str | None:
    """Deterministic identification-ladder replies (2026-07-31, IDENTIFICATION
    ONLY): the mechanical turns are COMPOSED by the engine from the phrases in
    identification.yaml — the LLM repeatedly reordered or skipped them (promised
    a check without the result, relapsed into confirm rounds, skipped the caller
    question, captured 'Taip.' as a name). An off-script caller turn (a question)
    returns None so the LLM answers it; the ladder resumes next turn. Solving and
    free dialogue never come here."""
    from .evidence_drive import evidence_question_open, negation_clarify_reply
    from .executor_flow import register_ticket_from_state
    from .perception_flow import anchor_text
    from .ticket_flow import begin_ticket_dialogue, finish_ticket_dialogue, ticket_stage_reply

    s = state
    # P-C (2026-09-08): the walker's 'callback' terminal just closed the case
    # (homework agreed) — the goodbye is scripted, warm and deterministic.
    if state.closing.callback_goodbye_due:
        state.closing.callback_goodbye_due = False
        from .contract.locale import phrase as _cb_phrase

        return _cb_phrase("identification.callback_goodbye")
    if s.closing.case_closed:
        return None
    from .contract.locale import phrase
    from .identification import caller_question
    from .resolution import is_real_question

    # Address CHANGE confirmation (reference dialogue №3, Andrius 2026-09-03): a
    # caller's mention of another address after identification NO longer switches
    # at once — first one confirmation question; „taip" (or a clear new address)
    # reopens identification, any other answer — we stay with the current one.
    # №4 (reference dialogue 2026-09-03): the caller claims to be the holder under
    # another name — a SCRIPTED clarification (live, the narrator overrode the note
    # and confirmed „Jūs, Petrai, esate savininkas"; the privacy rule is too
    # important to improvise). The DB name is NOT in the phrase; the answer next
    # turn updates the relation (prefill).
    if state.identity.holder_clarify_open and not state.identity.holder_clarify_asked:
        state.identity.holder_clarify_asked = True
        from .dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "holder_clarify")
        rt.tracer.emit("decision", intent="holder_name", action="clarify_ask")
        return phrase("identification.holder_mismatch_clarify")
    # A-2b (Andrius 2026-09-07, live: "negaliu pasakyti, dėl kokio adreso"):
    # the caller ASKS which address the call is about — the CONFIRMED address
    # is not a secret; on the contrary, this is how the caller catches our
    # mistake. Deterministic scripted answer, never the LLM's whim; the
    # phrase itself invites a correction.
    if (
        user_input
        and any(w in user_input.lower() for w in vocab("address_topic_words"))
        and any(k in user_input.lower() for k in vocab("which_words"))
        and is_real_question(user_input)
    ):
        if s.identity.customer_id and s.identity.customer_address:
            state.identity.reopen_reask_due = False  # the info answer replaces the re-ask
            rt.tracer.emit("decision", intent="address_info", action="disclose")
            return phrase(
                "identification.current_address_info", address=s.identity.customer_address
            )
        if not s.identity.customer_id:
            # A-2R-b follow-up (live 2026-09-07): the question arrived MID
            # identification (after reopen) — say WHAT we are clarifying:
            # the heard address (with the "dėl šio adreso" confirm core the
            # guard keys off), or that we have no address yet.
            p = s.identity.profile
            if p.street.value:
                adr = f"{p.street.value} {p.house.value or ''}".strip()
                rt.tracer.emit("decision", intent="address_info", action="progress")
                return phrase("identification.ident_address_heard", address=adr)
            rt.tracer.emit("decision", intent="address_info", action="none_yet")
            return phrase("identification.ident_address_none")
    # This layer ASKS the address-change question; the ANSWER is read by
    # pre_turn_guards (the deterministic turn head) so the solver/walker
    # cannot consume it (live A-2 defect). Only the ask/re-ask side is here.
    pending_reopen = state.identity.reopen_confirm_utterance
    if pending_reopen is not None:
        from .dialog_registry import register as _q_register

        adresas = s.identity.customer_address or phrase("identification.current_address_unknown")
        if not state.identity.reopen_confirm_asked:
            state.identity.reopen_confirm_asked = True
            state.identity.reopen_confirm_asks = 1
            _q_register(state, rt, "safety", "reopen_confirm", address=adresas)
            rt.tracer.emit("decision", intent="reopen_confirm", action="ask")
            return phrase("identification.reopen_confirm", address=adresas)
        if state.identity.reopen_reask_due:
            state.identity.reopen_reask_due = False
            state.identity.reopen_confirm_asks = state.identity.reopen_confirm_asks + 1
            _q_register(state, rt, "safety", "reopen_confirm", address=adresas)
            return phrase("identification.repeat_ack") + phrase(
                "identification.reopen_confirm", address=adresas
            )
        return None  # the guards already read the answer; the narrator continues

    # A-wave P1 (Andrius 2026-09-04, live #6: „Ne patogu" ignored): the
    # cannot-do-it-NOW mini-ladder in the solving phase — STOP, find out WHAT is
    # inconvenient, then offer a way (registration / call back / continue).
    cn_state = state.dialog.cannot_now_state
    if cn_state == "asked" and user_input:
        from .dialog_registry import clear as _q_clear
        from .dialog_registry import register as _q_register

        state.dialog.cannot_now_state = None
        _q_clear(state, rt, "cannot_now_clarify")
        low_cl = user_input.lower()
        # N2b (live 2026-09-09): "Aš Jums perskambinsiu" IN the clarify answer
        # is the whole decision — close warm right here, no offer round.
        if any(m in low_cl for m in vocab("will_call_back")):
            state.dialog.cannot_now_done = True
            s.closing.case_closed = True
            s.closing.closed_reason = "callback"
            rt.tracer.emit("decision", intent="cannot_now", action="callback_close")
            return phrase("identification.callback_goodbye")
        # N2 (live 2026-09-09: "Negaliu, nes esu nenuose" got RESUME and the
        # walker pushed another check): the caller was just asked "ar negalite
        # dabar patikrinti?" — a rambling answer about being away IS a yes.
        # RESUME only on a clear back-to-solving signal; everything else
        # offers the way out.
        resumed = any(m in low_cl for m in vocab("resume_solving")) and not any(
            m in low_cl for m in vocab("resume_solving_denied")
        )
        if not resumed:
            state.dialog.cannot_now_state = "offered"
            _q_register(state, rt, "safety", "cannot_now_offer")
            rt.tracer.emit("decision", intent="cannot_now", action="offer")
            return phrase("identification.cannot_now_offer")
        rt.tracer.emit("decision", intent="cannot_now", action="resume")
        return None  # explained otherwise — continue the path (content already ingested)
    if cn_state == "offered" and user_input:
        from .dialog_registry import clear as _q_clear

        state.dialog.cannot_now_state = None
        state.dialog.cannot_now_done = True
        _q_clear(state, rt, "cannot_now_offer")
        low_cn = user_input.lower()
        if any(m in low_cn for m in (*vocab("will_call_back"), *vocab("later_words"))):
            s.closing.case_closed = True
            s.closing.closed_reason = "callback"
            rt.tracer.emit("decision", intent="cannot_now", action="callback_close")
            return phrase("identification.callback_goodbye")
        from .resolution import DETECTORS as _DET_CN2
        from .resolution import detect_refuse_or_ticket

        if (
            detect_refuse_or_ticket(user_input) == "demand"
            or _DET_CN2["yes_no"](user_input) == "yes"
            or any(m in low_cn for m in vocab("ticket_words"))
        ):
            from .faults import step_by_role

            # P-E: the ticket intro must speak the honest state — the caller
            # could not act NOW; nothing was performed.
            if s.resolution.procedure is not None:
                s.resolution.procedure["escalate_reason"] = "cannot_now"
            rt.tracer.emit("decision", intent="cannot_now", action="ticket")
            begin_ticket_dialogue(state, rt, step_by_role("unclear_fault", "escalate"))
            return None  # ticket dialogue intro — the next step
        return None
    if (
        cn_state is None
        and not state.dialog.cannot_now_done
        and s.resolution.procedure
        and s.identity.customer_id
        and not state.ticket.stage
        and user_input
    ):
        from .dialog_registry import pack_owns_cannot_now as _pack_cn
        from .resolution import detect_cannot_now as _dcn

        if _dcn(user_input) and not _pack_cn(state, rt):
            from .dialog_registry import register as _q_register

            state.dialog.cannot_now_state = "asked"
            _q_register(state, rt, "safety", "cannot_now_clarify")
            rt.tracer.emit("decision", intent="cannot_now", action="clarify_ask")
            return phrase("identification.cannot_now_clarify")

    # Ticket-confirmation dialogue: contacts before every registration. An
    # off-script question falls to the ticket node's LLM (facts carry the
    # pending stage question to re-ask); the mechanical turns stay scripted.
    if state.ticket.stage in ("phone", "hours"):
        if state.turn.ticket_offscript_question:
            return None
        scripted = ticket_stage_reply(state, rt)
        # Zone 1 (scripts -> directives, Andrius 2026-08-20): the QUESTION
        # moments go to the narrator as a goal directive — it words them into
        # the conversation's flow; retries and the cancel-confirm stay
        # scripted (precision beats style on a repeat). Off-switch reverts.
        import os as _os

        ctx = state.ticket.context
        kind = ctx.last_kind if ctx else None
        if _os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on" and kind in (
            "phone_intro",
            "phone",
            "hours",
        ):
            state.turn.directives.ticket = {"kind": kind, "fallback": scripted}
            return None  # the ticket node's narrator speaks (facts directive)
        return scripted
    if state.ticket.stage == "done":
        return finish_ticket_dialogue(state, rt)
    if state.ticket.stage == "cancelled":
        state.ticket.stage = None
        state.ticket.context = None
        s.closing.case_closed = True
        s.closing.closed_reason = "declined"
        s.closing.is_complete = True
        return phrase("ticket.declined") + phrase("identification.goodbye")
    # Side-topic FRAME (3rd consecutive deviation): the LLM answered twice
    # and the caller keeps drifting — the return is scripted now. With a
    # CONFIRMED hypothesis the frame is the solve-together-or-technician
    # choice (Andrius 2026-08-07: maximise solving by phone).
    if state.turn.side_topic_active and state.dialog.side_topic_streak >= limits.get(
        "side_topic_streak_max"
    ):
        state.dialog.side_topic_streak = 0
        from .evidence import hypothesis_status, spec_for

        spec = spec_for((s.resolution.procedure or {}).get("verdict"))
        if spec is not None and hypothesis_status(s.diagnosis.evidence, spec) == "confirmed":
            return phrase("identification.solve_or_ticket")
        return phrase("identification.back_to_issue", anchor=anchor_text(state, rt))
    # Ledger conflict clarify (ONE question, engine-composed): "sakėte X,
    # dabar Y — kaip yra iš tiesų?" — the next answer settles the fact.
    if state.diagnosis.evidence_conflict:
        from .evidence import gloss_label, gloss_value

        conflict = state.diagnosis.evidence_conflict
        key, old, new = conflict.key, conflict.old, conflict.new
        state.diagnosis.evidence_conflict = None
        state.diagnosis.evidence_conflict_asked_key = key
        return phrase(
            "identification.evidence_conflict",
            topic=gloss_label(key),
            a=gloss_value(old, key),
            b=gloss_value(new, key),
        )
    # Farewell-mid-process clarify (any stage): ONE deterministic confirm question.
    if state.dialog.end_confirm_pending:
        return phrase("identification.confirm_end")
    # Uncorroborated bare "ne" tried to route the walker into ESCALATE — ask
    # the solve-or-register choice instead of crossing the one-way door
    # (2026-08-11). The next turn routes normally: a repeated no escalates.
    if state.resolution.escalate_clarify_due:
        state.resolution.escalate_clarify_due = False
        return phrase("identification.escalate_clarify")
    # Bare "ne" while the evidence drive's question is open, on the WALKER
    # path (farewell/refuse-shaped turns land here; the drive words its own
    # clarify): say what the "ne" could mean instead of acting on it.
    from .resolution import is_bare_negation

    open_key = evidence_question_open(state, rt)
    if open_key and is_bare_negation(user_input):
        clarify = negation_clarify_reply(state, rt, open_key)
        if clarify:
            return clarify
    if (
        user_input
        and is_real_question(user_input)
        and (s.intake.problem_type or s.identity.customer_id)
        # A code-phase question („o kur jį rasti?") goes to the rung — the retry
        # phrase with a HINT where to look IS the answer (reference dialogue №2).
        and not state.identity.account_code_mode
        # NLU wave block 4: "V KAIP Vilnius" is the spelling answer, not a
        # question — the rung's spell reader owns the armed turn; two "kaip"
        # pairs are spelling-shaped even without the mode (client-initiated).
        and not state.identity.spell_mode
        and user_input.lower().count(" kaip ") < 2
    ):
        return None  # off-script — the LLM answers; guards kept the ladder state
        # (pre-problem questions fall through to the problem GATE below)
    # INTAKE (not yet identified): the anamnesis question and the address
    # offer/ask are mechanical too — the LLM repeated the anamnesis and slid the
    # whole ladder by a turn (observed in eval).
    if not s.identity.customer_id:
        # Small talk BEFORE any problem is stated gets a scripted greeting-back
        # — never the LLM (which jumped to the address offer on "Labadiena!",
        # duplicating the ladder's own later offer; live 2026-08-06).
        if not s.intake.problem_type and user_input:
            from .resolution import is_greeting

            if is_greeting(user_input):
                return phrase("identification.ask_problem")
            # Live 2026-08-21: a garbled opener ("Atsikai, daro") fell to the
            # LLM, which offered the address before any problem was stated.
            # 2026-09-02: the gate grew the L2 classification ladder — see
            # _problem_gate_reply. A commit there (LLM guess accepted) falls
            # THROUGH to the intake ladder the same turn: reaching a problem
            # never ends the call, only never reaching one does.
            _has_addr0 = bool(s.identity.profile.street.value or s.identity.profile.house.value)
            if not _has_addr0:
                reply = _problem_gate_reply(state, rt, s, user_input)
                if s.intake.problem_type is None:
                    return reply
                # gate commit — continue to anamnesis/address this turn
        p = s.identity.profile
        has_addr = bool(p.street.value or p.house.value)
        # №2/№5 (reference dialogue 2026-09-03): the subscriber-code rung — when
        # the address does not clear up, the method changes; the code-waiting phase
        # reads the answer. The phone-candidate offer flow is not counted (it has
        # its own confirmation mechanics).
        if state.identity.account_code_mode or not s.identity.phone_candidate:
            handled, reply = _account_code_rung(state, rt, s, user_input)
            if handled:
                return reply
        if (
            s.intake.problem_type
            and not s.intake.anamnesis_asked
            and not s.identity.preflight_outage
            and not has_addr
        ):
            # DIALOGO_ETALONAS #2 (Andrius 2026-09-01/03): the OPENING
            # anamnesis QUESTION is gone — capture-first keeps whatever the
            # caller already said ("vakar dingo, po audros"), and the targeted
            # anamnesis lives in the PACKS, asked with telemetry context only
            # when the verdict needs it. A blind "kada dingo? gal po audros?"
            # wasted a turn on every fast-path call (live 2026-09-03: the
            # answer "kaimynai remontą darys" fed nothing — the verdict was a
            # billing block). anamnesis_asked stays as the ladder-live marker
            # (the deterministic address-resolve gate keys off it).
            s.intake.anamnesis_asked = True
            if user_input:
                from .nlu import extract_anamnesis

                read = extract_anamnesis(user_input)
                if read.get("when") not in (None, "unknown") or read.get("trigger"):
                    s.intake.anamnesis_raw = user_input.strip()[:200]
                    s.intake.anamnesis_when = read.get("when")
                    s.intake.anamnesis_trigger = read.get("trigger")
                    rt.tracer.emit(
                        "anamnesis",
                        text=s.intake.anamnesis_raw,
                        when=s.intake.anamnesis_when,
                        trigger=s.intake.anamnesis_trigger,
                        from_opening=True,
                    )
                    state.intake.opening_heard_note = True
            return _address_move(state, rt, s)
        return None
    # WRAP-UP after the news (inform mode): the business is DONE — any further
    # turn that is not a question/wants-more wraps up DETERMINISTICALLY. Garbled
    # goodbyes ("Nusigaro" = "viso gero") had the model loop "nesupratau,
    # pakartokite" after a delivered debt notice (observed live: the caller could
    # not end the call).
    if (
        s.resolution.procedure is None
        and (state.diagnosis.news_delivered or s.diagnosis.outage_reported)
        and not state.identity.result_pending
    ):
        low = (user_input or "").lower()
        wants_more = is_real_question(user_input) or any(
            m in low for m in vocab("inform_wants_more")
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
        n = state.closing.wrap_content_turns
        if content and n < limits.get("wrap_content_turns_max"):
            state.closing.wrap_content_turns = n + 1
            state.closing.wrap_react_note = True
            rt.tracer.emit("decision", intent="wrap_up", action="react", turns=n + 1)
            return None  # the narrator reacts to WHAT was said, then re-offers
        s.closing.case_closed = True
        s.closing.closed_reason = "outage" if s.diagnosis.outage_reported else "inform"
        s.closing.is_complete = True
        # clarity requirements (declared in inform.yaml): the inform template
        # spoke all its elements before this close — trace it for the audits.
        from .inform import clarity_declaration

        _reason = (s.diagnosis.verdicts.get("network") or {}).get("reason")
        _required = clarity_declaration(_reason)
        if _required:
            rt.tracer.emit(
                "clarity",
                reason=_reason,
                required=_required,
                told=state.diagnosis.news_delivered,
            )
        rt.tracer.emit("decision", intent="wrap_up", action="close", to=s.closing.closed_reason)
        return phrase("identification.goodbye")
    if not state.identity.result_pending:
        return None
    if not s.identity.caller_name:
        # The caller-intro question turn (with the address echo on a fresh
        # commit) + the CHECKING cue — the engine resolves/diagnoses silently
        # here, and without the cue the caller thinks nothing started
        # (live 2026-08-07: "nepasako, kad patikrins").
        parts = []
        if state.identity.just_identified and s.identity.customer_address:
            parts.append(phrase("identification.echo_address", address=s.identity.customer_address))
            parts.append(phrase("identification.checking_note"))
        state.identity.just_identified = False
        from .dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "caller_name")
        parts.append(caller_question())
        return " ".join(p for p in parts if p)
    # The caller introduced themselves — deliver the deferred result. INFORM
    # verdicts are fully mechanical; a strategy result (finding + step question)
    # stays with the LLM (returns None; the REZULTATO facts directive drives it).
    if s.resolution.procedure is not None:
        return None

    d = s.diagnosis.verdicts.get("network") or {}
    reason = d.get("reason")
    # Closing wave (2026-09-08): the inform SPEECH lives in
    # knowledge/inform.yaml — the template carries the details (debt
    # amount, months, last payment; outage place and ETA) and its own
    # "Patikrinau…" opening, so check_result/billing_extra are not repeated.
    from .inform import inform_text

    inf = inform_text(state, rt, reason)
    if inf:
        # B3 inform verdicts (node/switch fault, Andrius 2026-09-11): the
        # template PROMISES "meistrai jau užregistruoti" — the engine makes it
        # true by registering the ticket itself before the words go out.
        if verdict_flag(reason, "auto_ticket") and not s.ticket.ticket_id:
            register_ticket_from_state(state, rt, None)
        state.identity.result_pending = False
        state.diagnosis.news_delivered = True
        rt.tracer.emit("decision", intent="inform", action="template", reason=reason)
        return " ".join(
            [phrase("identification.thanks"), inf, phrase("identification.anything_else")]
        )
    zinia = phrase_or(f"verdict.{reason}.gloss", reason or "")
    if not zinia:
        return None
    zinia = zinia[0].upper() + zinia[1:]  # sentence-cased after "…iki jūsų buto."
    bits = [
        phrase("identification.thanks"),
        phrase("identification.check_result", news=zinia + "."),
    ]
    if verdict_flag(reason, "inform") == "debt":
        bits.append(phrase("identification.billing_extra"))
    # Outage news carries the ETA when the preflight knows it.
    if verdict_flag(reason, "inform") == "outage" and (s.identity.preflight_outage or {}).get(
        "eta"
    ):
        bits.append(phrase("identification.outage_eta", eta=s.identity.preflight_outage["eta"]))
    bits.append(phrase("identification.anything_else"))
    state.identity.result_pending = False
    state.diagnosis.news_delivered = True
    return " ".join(b for b in bits if b)


def _address_move(state, rt, s):
    """Zone 2 (scripts -> directives): the transition to the address — offer
    the phone-candidate address or ask for one. In narrator mode the moment
    becomes a goal directive (a smooth hand-over from the problem talk); the
    OFFER question's core stays verbatim ("Ar skambinate dėl X?") because the
    deterministic confirm guard keys off it. Off-switch keeps the scripts."""
    import os as _os

    from .contract.locale import phrase
    from .dialog_registry import register as _q_register
    from .identification import offer_phone_address

    c = s.identity.phone_candidate
    if offer_phone_address() and c and c.get("street") and not s.identity.preflight_outage:
        flat = f", butas {c['apartment']}" if c.get("apartment") else ""
        adresas = f"{c['street']} {c.get('house')}{flat}"
        kind, fallback = "address_offer", phrase("identification.address_offer", address=adresas)
    else:
        adresas = None
        kind, fallback = "address_ask", phrase("identification.address_ask")
    _q_register(state, rt, "ident", kind, address=adresas)
    if _os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on":
        state.turn.directives.ident = {
            "kind": kind,
            "adresas": adresas,
            "fallback": fallback,
        }
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

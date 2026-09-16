"""Address slots from the caller's words — the deterministic NLU reading proposed
into the slots, re-validated against the registry every turn."""

from __future__ import annotations

import logging
from typing import Any

from ..contract.locale import vocab
from ..dialog_utils import last_agent_question

logger = logging.getLogger(__name__)


def _registry_streets_fold(state, rt) -> list[str]:
    """Folded registry street names (without the „g." suffix) — for the other-address
    signal."""
    try:
        from ..evidence import _fold

        names = rt.tools.address_registry().street_names
        return [_fold(str(n).replace(" g.", "")) for n in names]
    except Exception:  # pragma: no cover - best-effort
        return []


def mentions_other_street(state, rt, text: str | None) -> bool:
    """A-wave P2 (live #4, 2026-09-04: „mano ADARAS yra Tilžės gatvė 60" —
    STT garbled the word „adresas", the correction detector stayed silent, and
    the narrator "acknowledged" the change IN WORDS only): an identified
    caller's turn carrying ANOTHER registry street name + a digit is a
    correction candidate — whether or not the word „adresas" was said."""
    if not text or not state.identity.customer_id:
        return False
    if not any(ch.isdigit() for ch in text):
        return False
    from ..evidence import _fold

    low = _fold(text)
    current = _fold(str(state.identity.customer_address or ""))
    return any(
        len(st) >= 4 and st in low and st not in current for st in _registry_streets_fold(state, rt)
    )


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
    # the speaker's context card), and the future async silent re-processing.
    if text and text.strip():
        s.intake.heard_utterances.append(text.strip())

    # Problem classification (R1) — independent of the registry/DB, so it runs
    # even if address extraction fails. A revisable hypothesis: a clearer later
    # statement overrides (docs/pokalbio_variklis.md §12.2).
    try:
        from ..intents import BOUNDARY_POLICIES, problem_policy
        from .nlu import classify_problem, extract_symptoms

        problem = classify_problem(text)
        # №4 continued (reference dialogue 2026-09-03): the answer to the holder
        # clarification updates the relation („žmonos vardu sudaryta" → family) — one read.
        if state.identity.holder_clarify_open and state.identity.holder_clarify_asked and text:
            state.identity.holder_clarify_open = False
            state.identity.holder_clarify_asked = False
            from .caller import detect_caller_relation as _dcr

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
        from ..evidence import _fold as _fd

        _st = _fd(str(s.identity.profile.street.value).replace(" g.", ""))[:5]
        if _st and _st in _fd(text or ""):
            from ..slots import Slot as _Slot

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
        from ..evidence import _fold as _fold_sug
        from .detectors import DETECTORS as _DET

        mentioned = _fold_sug(str(sug))[:5] in _fold_sug(text)
        if mentioned or _DET["yes_no"](text) == "yes":
            from ..slots import SlotStatus as _SS

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
        from ..slots import SlotStatus
        from .nlu import extract_address

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
        from ..evidence import _fold as _fd2

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

    # The caller names a DIFFERENT street than the held outage's — it is not theirs.
    if (
        reading.street
        and s.identity.held_outage
        and reading.street != s.identity.held_outage.get("street")
    ):
        s.identity.held_outage = None

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

"""Identification rules (§5 rows 5, 8-10) — the ladder around agent/identification.py:
the identity reopen, the problem gate, the account-code rung, the address ladder and the
street spelling round. The caller's words reach the slots through agent/perceive."""

from __future__ import annotations

import logging
from typing import Any

from ...contract import limits
from ...contract.locale import vocab
from ...dialog_utils import last_agent_question
from ...trace import trace_note

logger = logging.getLogger(__name__)


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
    s.identity.held_outage = None  # it belonged to the dropped candidate
    state.identity.account_code_mode = False
    state.identity.account_code_grace_turns = 0
    state.identity.address_empty_turns = 0
    state.identity.address_unrecognized_turns = 0
    state.identity.address_resolve_failures = 0
    state.identity.suggested_city = None
    state.diagnosis.evidence_ask_counts.clear()
    state.diagnosis.pending_evidence_key = None
    state.diagnosis.contradiction = None
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
    state.diagnosis.refute_confirmed = False
    state.turn.done_report_key = None
    state.resolution.bridge_plug_reported = False
    state.resolution.bridge_fail_stage = 0
    state.ticket.bridge_fail_note = None
    state.diagnosis.revived_evidence_keys = []
    from ...slots import ClientProfileState

    s.identity.profile = ClientProfileState()
    state.turn.db_address_note = None
    state.diagnosis.news_delivered = False  # a new address may carry different news
    state.identity.result_pending = False
    state.dialog.end_confirm_pending = False
    state.dialog.resume_hold_due = False
    state.resolution.bridge_bound = False  # a different account starts clean
    # Re-extract address parts from THIS utterance (the correction often carries
    # the new address: "ne, skambinu dėl Dainų 5").
    from ...perceive.slots import prefill_slots_from_text

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

    from ...contract.locale import phrase
    from ...intents import problem_boundary_reply, problem_confirm_question, problem_policy
    from ...perceive.detectors import DETECTORS, is_real_question

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
        from ...perceive.nlu import classify_problem_llm

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
    from ...evidence import _fold
    from ...perceive.nlu import street_match_score

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
    from ...evidence import _fold
    from ...perceive.nlu import street_match_score

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
    from ...evidence import _fold

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
    from ...contract.locale import phrase as _phrase

    c = s.identity.phone_candidate
    if c.get("street"):
        flat = f", butas {c['apartment']}" if c.get("apartment") else ""
        adresas = f"{c['street']} {c.get('house')}{flat}"
        # B-wave registry: the echo-offer IS the address-offer question
        # (live 2026-09-08: this path bypassed _address_move and the offer
        # went out unregistered).
        from ...decide.question import register as _q_register

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

    from ...contract.locale import phrase

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
            from ...decide.question import register as _q_register
            from ...slots import SlotStatus

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
        from ...decide.question import register as _q_register

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
            from ...decide.question import register as _q_register

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
            from ...decide.question import register as _q_register

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
        from ...decide.question import register as _q_register

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
        from ...decide.question import register as _q_register

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
        from ...decide.question import register as _q_register

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
            from ...decide.question import register as _q_register

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
                from ...decide.question import register as _q_register

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
        from ...decide.question import register as _q_register

        _q_register(state, rt, "ident", "address_need")
        rt.tracer.emit("decision", intent="account_code", action="warn")
        return True, phrase("identification.address_need_warning")
    if n >= limit:
        s.closing.case_closed = True
        s.closing.closed_reason = "declined"
        rt.tracer.emit("decision", intent="account_code", action="no_location_close")
        return True, phrase("identification.no_location_goodbye")
    return False, None


def _address_move(state, rt, s):
    """Zone 2 (scripts -> directives): the transition to the address — offer
    the phone-candidate address or ask for one. In narrator mode the moment
    becomes a goal directive (a smooth hand-over from the problem talk); the
    OFFER question's core stays verbatim ("Ar skambinate dėl X?") because the
    deterministic confirm guard keys off it. Off-switch keeps the scripts."""
    import os as _os

    from ...contract.locale import phrase
    from ...decide.question import register as _q_register
    from ...identification import offer_phone_address

    c = s.identity.phone_candidate
    if offer_phone_address() and c and c.get("street"):
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


def engine_resolve_from_slots(state, rt) -> bool:
    """Deterministic identification commit from clearly-heard slots: the ENGINE
    calls resolve_address (+ the silent diagnose) itself — no LLM tool-call
    hesitancy, no confirm-round relapse. True when a customer committed."""
    from ...execute.diagnosis import ensure_diagnosed

    p = state.identity.profile
    args: dict[str, str] = {
        "street": str(p.street.value),
        "house_number": str(p.house.value),
    }
    if p.apartment.value:
        args["apartment_number"] = str(p.apartment.value)
    if p.city.value:
        args["city"] = str(p.city.value)
    try:
        rt.tools.run(state, rt, "resolve_address", args, reason="resolve_from_slots")
    except Exception as e:  # pragma: no cover - best-effort
        trace_note(rt.tracer, state, "engine_resolve", str(e), level="error")
        return False
    if not state.identity.customer_id:
        return False
    release_held_outage(state, rt)
    # B-wave registry: the identification question (address/code) got its
    # answer — a contract committed; the next question (the name) is
    # registered by its own owner.
    from ...decide.question import clear_owner as _q_clear_owner

    _q_clear_owner(state, rt, "ident")
    ensure_diagnosed(state, rt)
    return True


def release_held_outage(state: Any, rt: Any) -> None:
    """The identity just committed: the outage held for the phone candidate is released
    when this IS that customer, and discarded when the caller turned out to be calling
    about another address (D-09)."""
    held = state.identity.held_outage
    if not held:
        return
    if held.get("customer_id") == state.identity.customer_id:
        rt.tracer.emit("held_outage", action="released", street=held.get("street"))
        return
    state.identity.held_outage = None
    rt.tracer.emit("held_outage", action="discarded", street=held.get("street"))

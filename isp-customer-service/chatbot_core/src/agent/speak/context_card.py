"""The context card — the engine's current truth for the speaking LLM (D-02).

Every line comes from typed state or the turn's plan: what is known, what is being
tested, what the caller just said, and the ONE goal this reply must reach. No line may
change WHAT happens — the rules in `decide` chose that; the card only says what the
speaker may say and must not say.

Sections, in the order they carry weight on a phone call:
  SIDE TOPIC / TICKET DIALOGUE  the turn is off the fault path — they lead
  DELIVERY                      what the caller did or did not hear (voice)
  JUST HEARD                    this turn's understanding pass
  CALLER / PROBLEM / TICKET     durable identity and case facts
  CASE                          closed, registered, resolved states
  DIALOGUE                      stuck, silence, waiting, plain-words requests
  HYPOTHESIS / EVIDENCE         what we believe, why, what is settled and open
  STEP                          the procedure step's goal, hint and playbook
  PLAN GOAL                     the one instruction for this reply
"""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import os  # noqa: F401
import re  # noqa: F401
from typing import Any  # noqa: F401

from ..contract.locale import phrase, phrase_or

HEADER = "CONTEXT CARD (the engine's truth for this reply — never re-ask what it holds):"


def context_card(state, rt) -> str | None:
    """The card for this turn, or None when nothing is known yet."""
    lines: list[str] = []
    for section in (
        _side_topic,
        _ticket_dialogue,
        _delivery,
        _just_heard,
        _identification_notes,
        _case_facts,
        _dialogue_state,
        _hypothesis,
        _evidence,
        _step,
        _plan_goal,
        _recall_and_notes,
    ):
        lines += section(state, rt) or []
    if not lines:
        return None
    return HEADER + "\n" + "\n".join(f"- {line}" for line in lines)


# --- the turn is off the fault path ------------------------------------------------------


def _side_topic(state, rt) -> list[str]:
    """A deviation: the ONLY permitted content is the FAQ hit (or an honest "not my
    area"), then the return anchor — the engine's exact pending question."""
    if not state.turn.side_topic_active:
        return []
    from ..dialog_utils import anchor_text
    from ..faq import match as faq_match

    hits = faq_match(state.dialog.last_heard)
    known = " ".join(f"[{e.get('topic')}] {phrase(e['answer_key'])}" for e in hits) or (
        "(NO KNOWN ANSWER for this topic - say politely that it is not your area)"
    )
    # The topic is DETERMINISTIC when the FAQ matched — the model once copied a prompt
    # example ("Klausiate apie kainą") for a topic the caller never raised.
    topic = phrase(f"faq_topic.{hits[0]['topic']}") if hits else ""
    naming = (
        f"The caller's topic: {topic}. "
        if topic
        else "Name the topic from the caller's LAST phrase - no other topic. "
    )
    return [
        "SIDE TOPIC: the caller asked about something other than the fault. "
        f"{naming}Answer in ONE or TWO sentences using ONLY these known answers: "
        f"{known} Invent NOTHING (no sums, deadlines, promises). Then ALWAYS return to the "
        f"fault by repeating: „{anchor_text(state, rt)}“"
    ]


def _ticket_dialogue(state, rt) -> list[str]:
    """The caller asked something instead of answering the contact question."""
    from ..execute.ticket import fmt_phone

    out: list[str] = []
    if state.ticket.stage in ("phone", "hours"):
        from ..decide.rules.ticket import ticket_need

        pending = phrase(
            "identification.ticket_phone"
            if state.ticket.stage == "phone"
            else "identification.ticket_hours"
        )
        out.append(
            "TICKET DIALOGUE: we are registering the fault (reason: "
            f"{ticket_need(state, rt)}). The caller's number: "
            f"{fmt_phone(state.identity.caller_phone) or 'unknown'}. The ticket is NOT "
            "registered yet — never say „užregistravau“. Answer the caller's question in "
            f"ONE sentence and then repeat the question: „{pending}“"
        )
    # A refusal WITH solving content: the dialogue was dropped, the call stays open.
    if state.ticket.resume_fix_note:
        state.ticket.resume_fix_note = False
        out.append(
            "REGISTRATION DECLINED, THE CALLER WANTS TO KEEP SOLVING: say in one sentence "
            "that you are not registering a technician, and GO BACK to the last solving "
            "instruction — repeat it or answer their question about it. Do NOT end the call."
        )
    return out


# --- what reached the caller's ear -------------------------------------------------------


def _delivery(state, rt) -> list[str]:
    """Voice delivery notes: a barge-in cut the reply, the caller spoke over it, or the
    question never went out. One-shot — each is consumed as it is rendered."""
    out: list[str] = []
    tail = state.voice.undelivered_tail
    if tail:
        state.voice.undelivered_tail = None
        out.append(
            f"NOT HEARD (the caller cut in): „{tail[:160]}“ — if it matters, say it again "
            "briefly in your own words."
        )
    overlay = state.voice.overlay_heard
    if overlay:
        state.voice.overlay_heard = None
        quoted = " / ".join(f"„{t[:120]}“" for t in overlay)
        out.append(
            f"SPOKEN OVER YOU: {quoted} — take it into account; if it answers your "
            "question, do not ask it again."
        )
    unheard = state.voice.unheard_question
    if unheard:
        state.voice.unheard_question = None
        out.append(
            "YOUR QUESTION NEVER WENT OUT: the caller did not hear it (they cut in "
            "earlier), so their words are NOT an answer to it. React to what they said "
            f"first, then ask it anew in your own words (one „?“): „{unheard[:160]}“"
        )
    return out


def _just_heard(state, rt) -> list[str]:
    """The understanding pass: the acknowledgement that makes the caller feel heard, and
    what they did not understand."""
    u = state.turn.understanding
    if u is None or state.turn.side_topic_active or state.closing.case_closed:
        return []
    out: list[str] = []
    understood = (u.get("understood") or "").strip()
    # The pass's summary is INTERNAL wording, often third-person about the caller; quoted
    # verbatim it became the agent's broadcast thought („Supratau — Paulius atliko veiksmą“
    # spoken TO Paulius). Then the instruction goes out without the quote.
    name = (state.identity.caller_name or "").strip()
    third_person = (bool(name) and name.lower() in understood.lower()) or any(
        m in understood.lower()
        for m in ("klientas", "klientė", "kliente", "naudotojas", "vartotojas")
    )
    if understood and third_person:
        out.append(
            "ACKNOWLEDGE in half a sentence IN YOUR OWN WORDS, addressing the caller in the "
            "SECOND person („Gerai, kad padarėte…“, „Aišku, darote…“) — never quote an "
            "internal summary and never speak about the caller in the third person."
        )
    elif understood:
        out.append(
            f"ACKNOWLEDGE what you understood in half a sentence („{understood}“) — then "
            "continue with one question or step. Address the CALLER („Supratau — …“), never "
            "speak about them in the third person (NOT „Klientas sutinka…“)."
        )
    if u.get("type") == "confusion" and u.get("confusion"):
        out.append(
            f"NOT UNDERSTOOD BY THE CALLER: {u['confusion']} — explain in OTHER, simpler, "
            "everyday words; do not repeat the same sentence."
        )
    return out


# --- identification ----------------------------------------------------------------------


def _identification_notes(state, rt) -> list[str]:
    """Address notes the guards wrote this turn, the encouragement, the phone account, the
    proactive outage and the deterministically heard address parts."""
    s = state
    out: list[str] = []
    if state.turn.address_confirm_note:
        out.append(state.turn.address_confirm_note)
    # The failed lookup's per-level diagnosis: tell the caller what WAS found and ask to
    # correct only the missing part.
    if state.turn.address_lookup_note and not s.identity.customer_id:
        out.append(state.turn.address_lookup_note)
    if (
        not s.identity.customer_id
        and s.intake.problem_type
        and s.dialog.turn_count >= 4
        and not s.identity.profile.street.value
        and not state.identity.address_encouraged
    ):
        state.identity.address_encouraged = True
        out.append(
            "ADDRESS ENCOURAGEMENT (once, warmly): explain WHY you need the address — "
            "without it you cannot see the caller's line or check the fault. Hints: the "
            "contract may be in another family member's name; a street may have been "
            "renamed; the street and house number are enough. Ask what they know."
        )
    if state.closing.wrap_react_note:
        state.closing.wrap_react_note = False
        out.append(
            "WRAP-UP PHASE: the business is done but the caller SAID something — react to "
            "THAT specifically: a name → welcome them warmly („Malonu!“); they PAID → "
            "confirm the service comes back automatically within an hour after payment; a "
            "new problem → answer briefly. No long re-explanations. End with „Ar dar kuo "
            "galiu padėti?“."
        )
    if state.turn.reopen_note and not s.identity.customer_id:
        out.append(
            "THE CALLER CORRECTED US: they are calling about a DIFFERENT address than the "
            "one we resolved. Apologise in one sentence and ask for the address they are "
            "calling about (if they already said it — see HEARD ADDRESS and use it). Do not "
            "mention the previous address or its diagnosis again."
        )
    out += _phone_account(state, rt)
    if state.turn.db_address_note and not s.identity.customer_id:
        out.append(state.turn.db_address_note)
    if not s.identity.customer_id:
        from ..identification import extra_questions_guidance

        extra = extra_questions_guidance()
        if extra:
            out.append(extra)
    return out


def _phone_account(state, rt) -> list[str]:
    """The caller's number is in the DB: offer ITS address first — the number is already
    tied to it, so it reveals nothing new and saves the STT-fragile spoken house number.
    Every named part must match (or be unsaid): the same street with a DIFFERENT flat is
    someone else's address (observed: said butas 3, resolved butas 7)."""
    s = state
    from ..identification import offer_phone_address

    def fits(said, mine) -> bool:
        return not said or str(said).lower() == str(mine or "").lower()

    c = s.identity.phone_candidate
    if not (
        offer_phone_address()
        and not s.identity.customer_id
        and c
        and c.get("street")
        # A directive turn owns the moment — the ladder decides WHEN the offer happens.
        and not state.turn.directives.ident
        and not state.turn.directives.ticket
        # The offer comes AFTER the problem and the anamnesis — a garbled first utterance
        # must not trigger it.
        and s.intake.problem_type
        and fits(s.identity.profile.street.value, c.get("street"))
        and fits(s.identity.profile.house.value, c.get("house"))
        and fits(s.identity.profile.apartment.value, c.get("apartment"))
    ):
        return []
    flat = f", butas {c['apartment']}" if c.get("apartment") else ""
    return [
        f"PHONE ACCOUNT: the caller's number is registered at {c['address']}. Offer THIS "
        "address FIRST, before asking them to dictate anything: "
        f"„Ar skambinate dėl {c['street']} {c['house']}{flat}?“. A clean yes identifies them "
        "(the engine looks the address up). If they say a DIFFERENT address (someone "
        "else's — that is allowed), ask them to state the address where the fault is and "
        "take THAT."
    ]


# --- durable case facts --------------------------------------------------------------------


def _case_facts(state, rt) -> list[str]:
    """Identity, problem, ticket, and the closed-case states."""
    s = state
    out: list[str] = []
    if s.identity.customer_id:
        out.append(f"Customer ID: {s.identity.customer_id}")
    if s.identity.customer_name:
        out.append(f"Customer name: {s.identity.customer_name}")
    if s.identity.customer_address:
        out.append(f"Address: {s.identity.customer_address}")
    if s.intake.problem_type:
        out.append(f"Problem type: {s.intake.problem_type}")
    if s.intake.symptoms:
        parts = ", ".join(f"{k}={v}" for k, v in s.intake.symptoms.items())
        out.append(f"SYMPTOMS (the caller's): {parts}.")
    if s.ticket.ticket_id:
        out.append(f"Ticket: {s.ticket.ticket_id}")
    out += _debt_facts(state, rt)
    if s.closing.case_closed and s.closing.is_complete:
        out.append(
            "CALL OVER: the caller said goodbye / has nothing more. Say ONLY one short "
            "farewell („Ačiū, kad paskambinote. Geros dienos!“) and NOTHING else — no new "
            "questions."
        )
    elif s.closing.case_closed:
        out.append(f"CASE CLOSED (reason: {s.closing.closed_reason or 'resolved'}).")
        # An engine-registered ticket (consent-free escalate): ANNOUNCE it — never ask
        # permission or offer to register again.
        if s.closing.closed_reason == "registered" and s.ticket.ticket_id:
            out.append(
                "REGISTERED: the fault is already registered (the engine did it). Say in one "
                "sentence that you registered the fault and colleagues will get in touch and "
                "explain in more detail. Do NOT ask for consent, do NOT offer to register "
                "again, do not read the ticket ID."
            )
        # Just resolved: confirm briefly, then OFFER one more thing and WAIT — the engine
        # ends the call once the caller declines.
        if s.closing.closed_reason == "resolved" and s.resolution.procedure:
            out.append(
                "SOLVED: the caller confirmed the internet works. Be glad briefly and ask "
                "„Ar dar kuo nors galiu padėti?“. Do NOT say goodbye yet, do NOT ask about "
                "equipment, do NOT ask them to check again."
            )
    return out


def _debt_facts(state, rt) -> list[str]:
    """The debt figures of a suspended service are OURS to state — they explain why the
    internet is off (live: „kokia skola?“ got „nematau… buhalterija“). Only billing
    DISPUTES go to customer service."""
    from ..faults import verdict_flag

    net = state.diagnosis.verdicts.get("network") or {}
    if verdict_flag(net.get("reason"), "inform") != "debt":
        return []
    debt = (net.get("signals") or {}).get("billing_debt") or {}
    if not debt.get("amount"):
        return []
    from ..contract.locale import lang

    bits = [f"skola {lang().money(float(debt['amount']))}"]
    months = lang().months(debt.get("months") or [])
    if months:
        bits.append(f"už {months}")
    last_payment = lang().date(debt.get("last_payment"))
    if last_payment:
        bits.append(f"paskutinis mokėjimas gautas {last_payment}")
    return [
        "DEBT FACTS (asked about the sum or the months — SAY these numbers, they are in "
        "your system): "
        + "; ".join(bits)
        + ". After payment the service comes back automatically within an hour. Send them to "
        "customer service ONLY for invoice disputes or a breakdown; never offer to connect "
        "them to any department — you have no such service."
    ]


# --- the dialogue's own state ----------------------------------------------------------------


def _dialogue_state(state, rt) -> list[str]:
    """Stuck ladder, silence, the caller's intent while we wait, plain-words requests."""
    s = state
    out: list[str] = []
    out += _stuck(state, rt)
    # Once stuck AND still unidentified, hand over EVERYTHING the caller said: VAD/STT
    # splits and garbles spoken numbers, and no single turn resolves — the whole buffer
    # lets the model infer the intended address.
    if (
        not s.identity.customer_id
        and s.dialog.stuck_count >= 1
        and len(s.intake.heard_utterances) >= 2
    ):
        recent = " | ".join(s.intake.heard_utterances[-8:])
        out.append(
            f'ALL HEARD (reconcile): the caller has said these pieces so far: "{recent}". '
            "STT may have split or garbled a spoken number („šešiasdešimt“ 60 can arrive as "
            "„šešias dešimt“ and mis-parse to 10). Infer the MOST LIKELY full address from "
            "everything above (prefer the latest correction) and say it back for a yes/no "
            "confirmation — do not make the caller repeat again if you can reasonably infer it."
        )
    if s.diagnosis.outage_reported and not s.closing.case_closed:
        out.append(
            "OUTAGE ANNOUNCED for this street — that IS the final answer. Do NOT ask for the "
            "house or flat, do NOT diagnose, do NOT suggest power or cables. Answer the "
            "caller's questions about the outage (time, progress, compensation). When they "
            "understand / will wait — say goodbye; the engine closes the call."
        )
    out += _awaiting(state, rt)
    if s.dialog.clarity_level == "basic" and not s.closing.case_closed:
        out.append(
            "PLAIN WORDS: the caller said they do not follow technical words. Speak "
            "VISUALLY, no jargon, ONE action at a time. Instead of terms say: routeris = "
            "„dėžutė su lemputėmis“; the WAN/internet socket = „lizdas, į kurį įkištas "
            "kabelis, ateinantis iš sienos, dažnai atskiras ir pažymėtas Internet“; LAN = "
            "„kiti lizdai šalia, į kuriuos jungiami namų įrenginiai“; MAC = „įrenginio "
            "numeris mūsų sistemoje“. Say WHERE to look („routerio galinėje pusėje“), not "
            "only WHAT."
        )
    return out


def _stuck(state, rt) -> list[str]:
    """The caller's last reply did not advance us: acknowledge, narrow, change tactic —
    never loop the same question. The account-code tactic belongs to identification only."""
    s = state
    if s.dialog.stuck_count >= 2 and not s.identity.customer_id:
        return [
            "STUCK: do NOT repeat the same question. Change tactic — offer the account code "
            "(„Gal turite abonento kodą nuo sąskaitos?“) or register the problem for a "
            "call-back."
        ]
    if s.dialog.stuck_count >= 2:
        return [
            "STUCK: do NOT repeat the same question. Rephrase it differently or offer to "
            "register the fault (a technician will get in touch). Do NOT ask for the account "
            "code — the caller is already identified."
        ]
    if s.dialog.stuck_count != 1:
        return []
    extra = (
        " You asked the previous question word for word — you MUST rephrase it."
        if state.dialog.last_reply_repeated
        else ""
    )
    if s.dialog.last_heard:
        # We DID hear them — we just could not use it. Never say „neišgirdau“ here.
        return [
            f"DID NOT UNDERSTAND (but heard!): the caller just said „{s.dialog.last_heard}“ "
            "and it did not give what is needed. Do NOT say „neišgirdau“ — say what you heard "
            "and what was unclear, and ask them to repeat ONLY that part: „Girdžiu „…“, bet "
            "nesupratau gatvės — pakartokite ją, prašau.“ If the caller is actually talking "
            "ABOUT SOMETHING ELSE (asking, clarifying) — answer THAT instead of repeating "
            "your question." + extra
        ]
    # Silence. They may be listening or thinking, so do not apologise at them —
    # „neišgirdau“ after they said nothing reads as if THEY failed.
    return [
        "SILENCE (the caller said nothing): do NOT say „neišgirdau“ — they may just be "
        "listening or thinking. Calmly, without apologising, ask for what is needed (e.g. "
        "the street), or check in with „Ar mane girdite?“. Do not rush." + extra
    ]


def _awaiting(state, rt) -> list[str]:
    """Why the turn did not move us on — so the reply answers what the caller actually did
    instead of re-asking the same sentence."""
    s = state
    if not s.dialog.awaiting or s.closing.case_closed:
        return []
    from ..perceive.detectors import INTENT_CONFUSED, INTENT_IN_PROGRESS, INTENT_QUESTION

    out: list[str] = []
    if s.dialog.last_intent == INTENT_IN_PROGRESS:
        out.append(
            "THE CALLER IS STILL DOING IT: they said they are going / fetching / about to — "
            "it is NOT done yet. Briefly confirm that you will wait („Gerai, palauksiu — "
            "pasakykite, kai būsite pasiruošęs“) and WAIT. Do NOT repeat the instruction, do "
            "NOT assume it failed, do NOT move on."
        )
    elif s.dialog.last_intent == INTENT_QUESTION:
        out.append(
            "THE CALLER ASKED SOMETHING: answer their question simply first, then gently "
            "return to what you asked for. Never repeat your question without answering."
        )
    elif s.dialog.last_intent == INTENT_CONFUSED:
        if s.dialog.step_confusions >= 2:
            out.append(
                "STILL NOT FOLLOWING (2+ times): stop explaining the same thing. Take the "
                "SMALLEST possible piece — one physical action doable in a second („Ar matote "
                "dėžutę su lemputėmis? Tiesiog pasakykite taip ar ne“) — and go one such step "
                "at a time. If that fails too, offer to register a technician visit."
            )
        else:
            out.append(
                "THE CALLER DID NOT FOLLOW: do NOT repeat the same words. Break this step into "
                "a SMALLER one — first lead them to WHERE to look and what it looks like, and "
                "ask for that one thing only."
            )
    if s.dialog.awaiting_turns >= 3:
        out.append(
            "LONG WAIT: several turns without progress. Check in like a human, ask how it is "
            "going and where they are („Ar pavyksta rasti? Gal pasakykite, ką matote“), or "
            "offer to register the fault."
        )
    return out


# --- what we believe and what is settled ------------------------------------------------------


def _caller_pending(state) -> bool:
    """The identification ladder's last rung: the caller-intro question is owed this reply,
    so the deferred check result and the findings stay out of it."""
    return bool(
        state.identity.customer_id
        and state.identity.result_pending
        and not state.identity.caller_name
    )


def _hypothesis(state, rt) -> list[str]:
    """Telemetry findings, the working belief, what was ruled out, and a pivot."""
    s = state
    out: list[str] = []
    if _caller_pending(state):
        from ..identification import caller_question

        out.append(
            "IDENTIFICATION, LAST RUNG: the check is done but do NOT give the result yet. "
            f"This reply carries ONLY the question: „{caller_question()}“. No result, no "
            "instructions."
        )
    elif s.identity.customer_id and s.identity.result_pending and s.identity.caller_name:
        from .context_card import result_narration_tail

        out.append("DELIVER THE RESULT:" + result_narration_tail(state, rt))
    # The tool results carry the CONTRACT HOLDER's name; it is account data, not a
    # greeting, and the caller need not be the holder (live: addressed as „Giedriau“ while
    # the caller had said „Andrius“).
    if s.identity.customer_id:
        if s.identity.caller_name:
            out.append(
                f"ADDRESS THEM AS: „{s.identity.caller_name}“ (or with no name). Never "
                "mention the CONTRACT HOLDER's name seen in tool results."
            )
        else:
            out.append(
                "ADDRESS THEM AS: we do not know the name — do not use one; never mention the "
                "holder's name seen in tool results."
            )
    # Once the strategy has run its action the raw finding is STALE — past the bind the
    # step's own hint is the single source of truth.
    past_action = bool(s.resolution.procedure) and "telemetry_fixed" in (
        s.resolution.procedure or {}
    )
    if not past_action and not _caller_pending(state):
        for domain, d in s.diagnosis.verdicts.items():
            gloss = phrase_or(f"verdict.{d.get('reason')}.gloss", d.get("reason") or "—")
            out.append(f"TELEMETRY [{domain}] ({d.get('group')}, side={d.get('side')}): {gloss}.")
    h = None if _caller_pending(state) else s.diagnosis.hypothesis
    if h:
        cause = phrase_or(f"verdict.{h['cause']}.gloss", h["cause"])
        if h["status"] == "confirmed":
            out.append(
                f"HYPOTHESIS CONFIRMED: „{cause}“ ({h['settled_by']}). Tell the caller briefly "
                "that this is exactly why it did not work — they want to understand."
            )
        elif h["status"] == "testing":
            out.append(
                f"WHAT I AM TESTING: „{cause}“. On what: {'; '.join(h['because'])}. When it "
                "fits, say it in your own words („matau X, todėl manau, kad Y“) — briefly, and "
                "not every turn."
            )
    if s.diagnosis.rejected_hypotheses and not s.closing.case_closed:
        ruled = ", ".join(
            phrase_or(f"verdict.{x['cause']}.gloss", x["cause"])
            for x in s.diagnosis.rejected_hypotheses
        )
        out.append(f"ALREADY RULED OUT (do not suggest or check again): {ruled}.")
    # A failed first attempt must read as an engineer working the problem (we have a plan
    # B), not as a script that silently restarts.
    if s.diagnosis.pivoted_from and not s.closing.case_closed:
        old = phrase_or(f"verdict.{s.diagnosis.pivoted_from}.gloss", s.diagnosis.pivoted_from)
        out.append(
            f"RETHINK: we tried the cause „{old}“ and it did NOT help (telemetry). Open your "
            "reply with that, humanly and briefly: it did not help, so the cause is another "
            "one, and what you are checking now. Then continue with THIS STEP. Do NOT pretend "
            "the earlier attempt never happened, and do not repeat it."
        )
    # INFORM (no strategy — billing/outage): the news went out in the activation reply.
    if (
        s.resolution.procedure is None
        and s.diagnosis.verdicts
        and not s.closing.case_closed
        and s.diagnosis.news_delivered
    ):
        out.append(
            "THE NEWS IS ALREADY OUT: do not repeat the „patikrinau / sustabdyta / avarija“ "
            "text. Answer the caller's question, or ask „Ar dar kuo galiu padėti?“ and end "
            "the call."
        )
    return out


def _evidence(state, rt) -> list[str]:
    """The ledger: settled facts are never re-asked, open goals keep the turn on course."""
    s = state
    out: list[str] = []
    if not s.identity.customer_id and not s.intake.problem_type:
        out.append(
            "THE PROBLEM IS NOT STATED YET: do NOT offer an address and check nothing — first "
            "ask what the problem is / how you can help."
        )
    if not s.identity.customer_id:
        p = s.identity.profile
        heard = [
            f"{label}={slot.value}"
            for label, slot in (
                ("city", p.city),
                ("street", p.street),
                ("house", p.house),
                ("apartment", p.apartment),
            )
            if slot.value
        ]
        if heard:
            out.append(
                "HEARD ADDRESS (deterministic — PREFER these over re-extracting from the raw "
                "text): " + ", ".join(heard) + ". Use THESE when you say the address back, "
                "unless the caller explicitly corrects them."
            )
    if s.diagnosis.evidence and s.identity.customer_id and not s.closing.case_closed:
        from ..evidence import summary_lt

        out.append(
            "ESTABLISHED THIS CALL (never ask again and never contradict): "
            f"{summary_lt(s.diagnosis.evidence)}"
        )
    # The still-open goals, so the speaker pulls a wandering caller back to what is missing
    # instead of drifting.
    if (
        s.identity.customer_id
        and not s.closing.case_closed
        and (s.resolution.procedure or {}).get("verdict")
    ):
        from ..evidence import open_goals_lt

        goals = open_goals_lt(s.diagnosis.evidence, s.resolution.procedure.get("verdict"))
        if goals:
            out.append(
                f"STILL TO FIND OUT (the conversation's goal): {goals}. If the caller drifts — "
                "answer briefly, remind them where we are, and bring the conversation back to "
                "what is still open. With 1–2 goals left, TELL the caller the progress in your "
                "own words (e.g. „beliko patikrinti rozetę — ir bus aišku“)."
            )
    if state.resolution.bridge_plug_reported:
        out.append(
            "BRIDGE PHASE: the router is already declared faulty and the cable is REPLUGGED "
            "into the computer — do NOT ask about the router, its lights or power again. We "
            "are only talking about the computer's connection."
        )
    # The just-landed answer's declared MEANING — the reaction carries it instead of
    # parroting the fact („Vadinasi, maitinimą gauna, bet tinklo nemato.“). One-shot.
    meaning = state.diagnosis.fact_meaning
    if meaning:
        state.diagnosis.fact_meaning = None
        topic, value, means = meaning
        out.append(
            f"JUST LEARNED: {topic} — „{value}“. THIS MEANS: {means}. In your reaction say "
            "THIS MEANING in one sentence (not the raw fact), then the next step."
        )
    return out


def _step(state, rt) -> list[str]:
    """The procedure step the engine is on: its playbook section, hint and goal."""
    s = state
    out: list[str] = []
    if not (s.resolution.procedure and not s.closing.case_closed):
        return out
    from ..execute.step import emit_rag_injection
    from ..playbook import get_step
    from ..resolution import get_strategy

    strat = get_strategy(s.resolution.procedure.get("verdict"))
    step = strat.step(s.resolution.procedure.get("step", "")) if strat else None
    if step is None:
        return out
    # Directive isolation: a directive turn carries ONE instruction — no step hint, no
    # playbook section (the hint used to win over the directive). A check-back on a fact
    # the caller already gave counts too: the step's own question is exactly what must
    # NOT be asked this turn (F-11).
    directive_active = bool(
        state.turn.directives.evidence
        or state.turn.directives.recap
        or state.turn.directives.findings
        or state.turn.directives.ticket
        or state.turn.directives.ident
        or s.resolution.procedure.get("heard_confirm")
    )
    if not _caller_pending(state) and not directive_active:
        if step.rag_section is not None:
            section = get_step(strat.rag_doc, step.rag_section)
            if section:
                # Observability: WHICH knowledge chunk feeds THIS step.
                emit_rag_injection(state, rt, strat.rag_doc, step.rag_section, step.id, section)
                out.append(
                    "PLAYBOOK — your INTERNAL guidance for THIS step (Lithuanian content). Act "
                    "on it, do NOT read it to the caller verbatim, ask ONE thing at a time. Say "
                    "ONLY what THIS step is about — do NOT invent instructions it does not "
                    "mention (no rebooting, no lights, no cables unless this step says so). If "
                    "the caller's answer was unclear, ask THIS SAME thing again in other "
                    "words:\n" + section
                )
        if step.hint:
            out.append(f"THIS STEP: {step.hint}")
    if getattr(step, "goal", "") and not directive_active:
        out.append(
            f"STEP GOAL: {step.goal}. Reacting to the caller's answer, JUDGE whether the "
            "goal is reached — a short evaluating reaction („Gerai — radote“ / „Ne, ne šis "
            "kabelis“), then continue."
        )
    if (s.resolution.procedure.get("presented") or {}).get(step.id, 0) >= 2:
        out.append(
            "STEP REPEATED: you already asked this step's question — briefly explain WHY you "
            "are asking again („dar kartą, nes noriu būti tikras…“), then ask."
        )
    return out


# --- the one instruction for this reply --------------------------------------------------------


def _plan_goal(state, rt) -> list[str]:
    """The goal directives the rules composed this turn: the identification moment, the
    ticket question, the recap, the findings, the evidence question. Normally exactly one
    of them is set, and it is what this reply must achieve."""
    out: list[str] = []
    out += _goal_secondary_problems(state, rt)
    out += _goal_resync(state, rt)
    out += _goal_caller_intro(state, rt)
    out += _goal_identification(state, rt)
    out += _goal_ticket(state, rt)
    out += _goal_recap_and_findings(state, rt)
    out += _goal_evidence(state, rt)
    return out


def _goal_secondary_problems(state, rt) -> list[str]:
    """Before the goodbye the agent asks back about the OTHER complaints heard mid-call;
    they are already on the ticket."""
    s = state
    if not (s.closing.case_closed and getattr(s.intake, "secondary_problems", None)):
        return []
    topics = "; ".join(f"„{x['text']}“" for x in s.intake.secondary_problems)
    return [
        "PLAN GOAL — SECONDARY PROBLEMS (ask before saying goodbye): the caller mentioned "
        f"{topics}. Ask whether it is still relevant; say it was passed to the technician "
        "(already on the registration)."
    ]


def _goal_resync(state, rt) -> list[str]:
    """Return after a detour: re-anchor from the LEDGER, never improvise a fresh diagnostic
    (live: „ar prijungtas prie maitinimo?“ re-asked after a detour while all three facts
    were already established)."""
    if not state.dialog.resync_note:
        return []
    state.dialog.resync_note = False
    established = ""
    if state.diagnosis.evidence:
        from ..evidence import summary_lt

        established = summary_lt(state.diagnosis.evidence)
    return [
        "PLAN GOAL — BACK TO SOLVING (after the detour): in one sentence remind where we "
        + (f"are — established: {established} — " if established else "are ")
        + "and continue from the CURRENT goal below (STILL TO FIND OUT / FINDINGS MOMENT / "
        "ASK NOW). Ask NOTHING again that is already established; if the conclusion is clear "
        "— say it and offer the solution."
    ]


def _goal_caller_intro(state, rt) -> list[str]:
    """The caller just introduced themselves — accept warmly, once."""
    if not state.identity.caller_name_heard:
        return []
    state.identity.caller_name_heard = False
    name = state.identity.caller_name
    if not name or name == "nenurodyta":
        return []
    return [
        f"THE CALLER INTRODUCED THEMSELVES: open with a warm welcome — „Malonu, {name}!“ (or "
        "similar) — and carry on with your thought."
    ]


def _goal_identification(state, rt) -> list[str]:
    """The identification moment: the address offer, the problem gate, the address ask."""
    s = state
    idd = state.turn.directives.ident
    if not idd:
        return []
    out: list[str] = []
    # The opening already said WHEN it broke — the caller must HEAR they were heard, one
    # short acknowledgement before the address ask, never a repeated „kada dingo?“.
    if state.intake.opening_heard_note:
        state.intake.opening_heard_note = False
        when = (
            phrase_or(f"anamnesis.when.{s.intake.anamnesis_when}", s.intake.anamnesis_when)
            if s.intake.anamnesis_when
            else phrase_or(
                f"anamnesis.trigger.{s.intake.anamnesis_trigger}", s.intake.anamnesis_trigger
            )
            if s.intake.anamnesis_trigger
            else ""
        )
        out.append(
            "THE CALLER ALREADY SAID when it broke"
            + (f" („{when}“)" if when else "")
            + " — show in a couple of words that you heard it (e.g. „Aišku — nuo vakar.“), and "
            "do NOT ask when it broke."
        )
    if idd["kind"] == "address_offer":
        # No jump: first a short reaction to what the caller JUST said, then the bridge into
        # the address. The question's core stays word for word — the deterministic confirm
        # guard keys off it.
        problem = phrase_or(f"problem_label.{s.intake.problem_type or ''}", "")
        heard = f" („Suprantu — {problem}.“)" if problem else ""
        out.append(
            "PLAN GOAL — IDENTIFICATION STEP: with the first SHORT sentence show that you "
            f"heard what the caller said{heard}, then bridge — the check needs the address — "
            f"and the question's core WORD FOR WORD: „Ar skambinate dėl {idd['adresas']}?“ Do "
            "not change the address. Whole reply example: „Suprantu — dingo internetas. "
            f"Patikrinsiu liniją — ar skambinate dėl {idd['adresas']}?“"
        )
    elif idd["kind"] == "problem_gate":
        out.append(
            "PLAN GOAL — PROBLEM GATE: the caller has not named a clear problem in OUR area. "
            "YOUR COMPETENCE: you solve ONLY internet and TV technical faults — invoices, "
            "contracts and other matters you do NOT solve, and you say so openly. Find out "
            "whether they have an internet or TV problem. If the topic is not yours (an "
            "invoice, „vaikai neklauso“) — name the boundary politely and ask whether there is "
            "a connection or TV problem. If the caller ASKS something — answer in one sentence "
            "and ask about the problem again. Do NOT ask for the address and check nothing. "
            f"(Backup: „{idd['fallback']}“)"
        )
    else:
        out.append(
            "PLAN GOAL — IDENTIFICATION STEP: explain that a check down to the flat needs the "
            f"address, and ask ONLY for the address. (Backup: „{idd['fallback']}“)"
        )
    return out


def _goal_ticket(state, rt) -> list[str]:
    """The ticket dialogue's question moments — the engine owns the stages and the capture;
    only the WORDING is free."""
    td = state.turn.directives.ticket
    if not td:
        return []
    from ..decide.rules.ticket import ticket_need

    if td["kind"] == "phone_intro":
        if state.resolution.bridge_bound:
            goal = (
                "give the good news — the internet works through the computer for now — and "
                "that you are registering a technician for a new router; ask ONE thing only: "
                "whether the number they are calling from suits for contact"
            )
        else:
            goal = (
                f"tell them this cannot be solved over the phone ({ticket_need(state, rt)}) and "
                "that you are registering a technician; ask ONE thing only: whether the number "
                "they are calling from suits for contact"
            )
    elif td["kind"] == "hours":
        # The LLM echoed the just-captured number back with the „iš kurio skambinate“
        # template — the number is DONE, this turn is hours only.
        goal = (
            "ask ONE thing only: when it is most convenient for the caller to be called. The "
            "number is ALREADY captured — do not mention or ask it again"
        )
    else:
        goal = "ask ONE thing only: whether the number the caller is calling from suits for contact"
    return [
        f"PLAN GOAL — TICKET STEP: {goal}. The registration has NOT happened — say "
        f"„užregistruosiu“, never „užregistravau“. (Backup: „{td['fallback']}“)"
    ]


def _goal_recap_and_findings(state, rt) -> list[str]:
    """The recap reads the gathered facts back in the speaker's own words; the findings
    moment states what was established, the conclusion and the choice."""
    out: list[str] = []
    rd = state.turn.directives.recap
    if rd:
        out.append(
            f"PLAN GOAL — CHECK BACK: did you understand it right — {rd['faktai']}. End with a "
            "confirming question („ar taip?“)."
        )
    fd = state.turn.directives.findings
    if fd:
        # Ticket-first faults script their own offer (`offer_goal` in the pack): the primary
        # outcome first, the convenience as the question.
        if fd.get("offer"):
            solution = f" {fd['offer']}"
        elif fd.get("solutions"):
            solution = f" Offer the choice ({fd['solutions']}) and ask how we proceed."
        else:
            solution = ""
        # The findings turn said „Užregistravau“ while create_ticket was still turns away.
        tense = (
            ""
            if state.ticket.ticket_id
            else " The registration has NOT happened — if you mention it, say "
            "„užregistruosiu“, never „užregistravau“."
        )
        out.append(
            f"PLAN GOAL — FINDINGS MOMENT:{tense} together we established — {fd['faktai']}. "
            f"Conclusion: {fd['isvada']}.{solution} Two or three sentences, no lists or colons."
        )
    return out


def _goal_evidence(state, rt) -> list[str]:
    """The evidence question as a goal: the speaker words it naturally in the conversation's
    flow instead of reading the pack's scripted sentence."""
    s = state
    directive = state.turn.directives.evidence
    if not directive:
        return []
    why = f" Why we check it: {directive['kodel']}." if directive.get("kodel") else ""
    # The OTHER still-open goals are named as off-limits (eval: asked „which device“ and
    # „laidu ar Wi-Fi“ in one breath — the connection type is a later fact with its own turn).
    others = ""
    if (s.resolution.procedure or {}).get("verdict"):
        from ..evidence import open_goals_lt

        rest = [
            g.strip()
            for g in open_goals_lt(
                s.diagnosis.evidence, s.resolution.procedure.get("verdict")
            ).split(";")
            if g.strip() and g.strip() != str(directive["reikia"]).strip()
        ]
        if rest:
            others = (
                " Do NOT ask about or mention the OTHER things yet (each gets its own turn): "
                + "; ".join(rest)
                + "."
            )
    return [
        f"PLAN GOAL — ASK NOW: find out — {directive['reikia']}. You do NOT know this fact yet "
        f"— ask a question, do not state it.{why}{others} (Backup: „{directive['klausimas']}“)"
    ]


def _recall_and_notes(state, rt) -> list[str]:
    """The caller's own earlier words they referenced, and the analyst's advisory notes."""
    from .history import recall_lines

    out: list[str] = []
    recall = recall_lines(state, rt)
    if recall:
        out.append(recall)
    out += _analyst_tone(state)
    return out


def _analyst_tone(state) -> list[str]:
    """The analyst's tone signals: how the caller is doing, never what to do. One-shot —
    the deciding signals were applied by the engine when they arrived."""
    signals = state.voice.analyst_signals
    if not signals:
        return []
    state.voice.analyst_signals = None
    out = []
    for signal in signals:
        quote = f" („{signal['quote']}“)" if signal.get("quote") else ""
        if signal.get("type") == "frustration":
            out.append(
                f"TONE: the caller is losing patience{quote} — acknowledge it plainly, keep "
                "the reply short, and make the next step the smallest possible one."
            )
        elif signal.get("type") == "off_topic":
            out.append(
                f"OFF THE QUESTION: the caller's last words do not answer what you asked{quote} "
                "— answer them briefly, then bring the conversation back to your question."
            )
    return out


def _result_question(state, rt) -> str:
    """The one question the result turn ends with: a check-back when the caller already
    told us what this step asks (F-11), otherwise the first thing still MISSING from the
    ledger, or this step's own question when the ledger is silent."""
    from ..decide.rules.evidence import seeded_step_confirm
    from ..evidence import open_goals_lt

    heard = seeded_step_confirm(state, rt, None)
    if heard:
        return f"pasitikslink ŽODIS Į ŽODĮ: „{heard}“ (klientas tai jau sakė — neklausk iš naujo)."
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
    from ..identification import ask_caller, caller_question

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
            f"pasakyk rezultatą ir kas tai greičiausiai yra, (3) {_result_question(state, rt)} "
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

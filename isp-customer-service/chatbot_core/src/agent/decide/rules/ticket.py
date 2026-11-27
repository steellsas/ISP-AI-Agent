"""Ticket rules — the contact dialogue before a registration (§5 row 3).

The caller's answer to the number / hours question is read first (capture, one retry
each, the cancel-confirm, the callback wish); then the dialogue asks its next
question, registers once both contacts are known, or ends on a confirmed refusal.
"""

from __future__ import annotations

import re
from typing import Any

from ...closing import close_call
from ...contract import limits
from ...contract.locale import phrase_or, vocab, vocab_map
from ...execute.ticket import NO_NUMBER, caller_id
from ..plan import Action, Say, TurnPlan

STAGE = "ticket"


def caller_owed(state: Any) -> bool:
    """A ticket started right at identification (a request, a no-path fault) still owes
    the caller-name question: it comes before the contact dialogue."""
    s = state
    return bool(s.identity.customer_id and s.identity.result_pending and not s.identity.caller_name)


def plan(state: Any, rt: Any) -> TurnPlan | None:

    s = state
    user_input = s.turn.user_input
    if s.ticket.stage not in ("phone", "hours") or not user_input or s.closing.case_closed:
        return None
    if caller_owed(state):
        return None  # the answer is the caller's name — the identification ladder reads it
    ticket_capture(state, rt, user_input)
    if s.ticket.stage is None and s.case.facts.pop("_reopened", None):
        return None  # the Case takes the turn again: the step the finding opens
    # A first-person "I will call back" closed the dialogue — the warm goodbye.
    if s.closing.callback_goodbye_due:
        s.closing.callback_goodbye_due = False
        return _scripted("ticket.callback_close", key="identification.callback_goodbye")
    if s.ticket.stage in ("phone", "hours"):
        rule, words = ticket_question_turn(state, rt)
        if words is None:
            return TurnPlan(owner="ticket", rule=rule, say=Say(kind="directive", stage=STAGE))
        return _scripted(rule, text=words)
    if s.ticket.stage == "done":
        return TurnPlan(
            owner="ticket",
            rule="ticket.register",
            action=Action(type="register_ticket"),
            say=Say(kind="phrase", stage=STAGE),
        )
    if s.ticket.stage == "cancelled":
        from ...contract.locale import phrase

        s.ticket.stage = None
        s.ticket.context = None
        return _scripted(
            "ticket.cancelled",
            text=phrase("ticket.declined") + phrase("identification.goodbye"),
            action=Action(type="close", name="declined", args={"complete": True}),
        )
    # The caller refused the registration but wants to keep solving — the narrator
    # says so and re-anchors the last instruction.
    return TurnPlan(
        owner="ticket", rule="ticket.back_to_solving", say=Say(kind="directive", stage=STAGE)
    )


def _scripted(
    rule: str, key: str | None = None, text: str | None = None, action: Any = None
) -> TurnPlan:
    return TurnPlan(
        owner="ticket",
        rule=rule,
        action=action or Action(type="none"),
        say=Say(kind="phrase", key=key, text=text, stage=STAGE),
    )


def ticket_capture(state, rt, user_input: str) -> None:
    """Ticket-dialogue capture: the previous reply asked for the contact number /
    hours — read the answer. A question falls through to the LLM (the stage stays
    and re-asks); a farewell fast-forwards with defaults (the caller is done
    talking — register with what we have)."""

    s = state
    from ...perceive.detectors import detect_farewell, detect_ticket_consent

    state.turn.ticket_offscript_question = False
    low_q = (user_input or "").lower()
    from ...graph_v2.state import TicketContext

    ctx = state.ticket.context or TicketContext()
    # Cancel-confirm answer (2026-08-11): the previous reply asked
    # "registruoti, ar tikrai nereikia?" — read THIS turn against that
    # question only. Live, a bare "Ne." (a barge-in crumb) cancelled the
    # ticket AND closed the call in one breath; cancelling is a one-way
    # door, so it now takes a confirmed refusal.
    cancel_confirm_out, ctx.cancel_confirm_out = ctx.cancel_confirm_out, False
    from .case_rule import reopen_on_finding

    if reopen_on_finding(state, rt, user_input):
        # „Aš dabar patikrinau, Wi-Fi išjungtas" while the contacts are taken: a finding the fix
        # can act on — back to it, not „nesupratau numerio" (live 2026-11-05).
        abort_ticket_to_solving(state, rt)
        return
    if cancel_confirm_out:
        from ...perceive.detectors import is_bare_negation

        # "Ne, tai pajunkim tą kompiuterį" refuses the TICKET, not the
        # help — back to solving, never back to the phone question.
        if wants_to_keep_solving(state, rt, user_input):
            abort_ticket_to_solving(state, rt)
            return
        if is_bare_negation(user_input) or any(
            m in low_q for m in vocab("ticket_cancel_confirmed")
        ):
            state.ticket.stage = "cancelled"
            from ...decide.question import clear_owner as _q_clear_owner

            _q_clear_owner(state, rt, "ticket")
            rt.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
            return
        # Anything else resumes the registration — the stage re-asks (a number the caller
        # dictated is read back again rather than forgotten).
        ctx.ask_phone_confirm = bool(state.ticket.stage == "phone" and ctx.phone_pending)
        rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_confirm_resumed")
        return
    # #79 (live 2026-11-20): the caller chose the technician, then — while we asked for the
    # number — „Aš prie routerio, darom". Their own choice, so their own change of mind: back
    # to the fix (the Case keeps its place).
    if (
        state.ticket.reason == "klientas_praso"
        and state.case.fault
        and state.case.in_progress
        and not state.ticket.ticket_id
    ):
        from .case_rule import technician_choice

        if technician_choice(user_input) == "try":
            abort_ticket_to_solving(state, rt)
            state.case.summarised = False
            state.case.facts.pop("_escalate_why", None)
            return
    # Understanding pass first (2026-08-10, Andrius): caller phrasing
    # cannot be predicted — "Bet kada galima per pietus iš ryto" IS an
    # P5 (closing wave, live 2026-09-07: "Gerai, aš paskambinsiu vėliau"
    # mid-ticket-dialogue got "ar tiks numeris?"): a first-person "I will
    # call back" IS a callback wish, not a contact answer — the caller
    # does not want the registration now. Same warm close as the
    # cannot-now ladder: no ticket, callback goodbye.
    if any(m in low_q for m in vocab("will_call_back_first_person")):
        state.ticket.stage = None
        state.ticket.context = None
        from ...decide.question import clear_owner as _q_clear_owner

        _q_clear_owner(state, rt, "ticket")
        close_call(state, rt, "callback")
        state.closing.callback_goodbye_due = True
        rt.tracer.emit("decision", intent="ticket_dialogue", action="callback_close")
        return
    # hours answer, but "galima" sat on the keyword question list and
    # diverted it. The model reads the answer against THIS question;
    # keyword logic below stays as the fallback when it is unavailable.
    # „Užrašiau … — ar teisingai?" is answered before any reading of the contact answer: the
    # readers would take its „Taip" for „the number I call from".
    phone_confirm_out, ctx.phone_confirm_out = ctx.phone_confirm_out, False
    if phone_confirm_out and state.ticket.stage == "phone" and ctx.phone_pending:
        _read_phone_confirm(state, rt, ctx, user_input)
        return
    und_handled = False
    from ...perceive import understand as _und

    if _und.enabled():
        # Wave 2a: the contact answer rides on THIS turn's one reading; only a turn
        # that was never read (a direct caller in tests) asks for its own.
        read = state.turn.perception or {}
        ut = read.get("ticket") if read.get("utterance") == user_input else None
        if ut is None:
            ut = _und.understand_ticket(
                user_input,
                stage=state.ticket.stage,
                anchor=(s.dialog.last_question or ""),
                model=rt.config.model,
            )
        if ut is not None:
            und_handled = True
            rt.tracer.emit(
                "understand_ticket",
                stage=state.ticket.stage,
                type=ut["type"],
                value=ut.get("value"),
            )
            if ut["type"] == "question":
                # Echo of our own offer (D, live 2026-08-20): "Ar tiks tas,
                # iš kurio skambinu?" repeated back with rising intonation
                # is CONSENT — answering it and re-asking doubled the
                # question. Fuzzy overlap with what we just asked decides.
                if state.ticket.stage == "phone":
                    from ...barge_in import token_overlap

                    if caller_id(state) and token_overlap(
                        user_input, s.dialog.last_question or ""
                    ) >= limits.get("echo_overlap_threshold"):
                        s.ticket.contact_phone = caller_id(state)
                        state.ticket.stage = "hours"
                        rt.tracer.emit(
                            "decision", intent="ticket_dialogue", action="phone_echo_consent"
                        )
                        return
                state.turn.ticket_offscript_question = True
                rt.tracer.emit("decision", intent="ticket_dialogue", action="question")
                return
            if ut["type"] == "refusal":
                # Refusal WITH solving content skips the confirm — the
                # caller told us what they want: keep fixing.
                if wants_to_keep_solving(state, rt, user_input):
                    abort_ticket_to_solving(state, rt)
                    return
                # One confirm round before the one-way door (2026-08-11):
                # "Ne." to "ar tiks šis numeris?" may mean "kitu numeriu",
                # not "neregistruokite" — clarify before dropping the
                # ticket the caller was just promised.
                _refuse_registration(state, rt, ctx)
                return
            if not getattr(ctx, f"{state.ticket.stage}_asked", False):
                return  # trigger-swallow guard (question not asked yet)
            value = ut.get("value")
            if value:
                # The reading is a value only when the caller's own words carry it; otherwise
                # the keyword/retry path below reads the answer.
                if state.ticket.stage == "phone":
                    if value == "same_number" and caller_id(state):
                        s.ticket.contact_phone = caller_id(state)
                        rt.tracer.emit(
                            "decision", intent="ticket_dialogue", action="phone_captured"
                        )
                        state.ticket.stage = "hours"
                        return
                    number = _grounded_phone(value, user_input)
                    if number:
                        _take_phone(state, rt, ctx, number)
                        return
                    if len(re.sub(r"\D", "", value)) >= 6:
                        rt.tracer.emit(
                            "decision", intent="ticket_dialogue", action="phone_not_grounded"
                        )
                else:
                    own = _clean_hours(user_input)
                    said = re.sub(r"[?!]", " ", value).strip(" .,")
                    when = hours_words(own)
                    # A clock time read from the caller's own words is final; „bet kada" or a
                    # part of the day may be narrowed by a reading made of their words — and
                    # only by one that is itself a time.
                    if not re.search(r"\d", when) and _hours_grounded(said, user_input):
                        when = hours_words(said) or when or _hours_only(said)
                    if when:
                        s.ticket.contact_hours = when[:80]
                        rt.tracer.emit(
                            "decision", intent="ticket_dialogue", action="hours_captured"
                        )
                        state.ticket.stage = "done"
                        return
                    rt.tracer.emit(
                        "decision", intent="ticket_dialogue", action="hours_not_grounded"
                    )
            # No value — fall through to the keyword/retry machinery.
    # W0-C (live 2026-08-25): STT turned "patogiausia" into "KODĖL
    # tokiausia skambinti nuo 17-18 val." — the question keyword diverted
    # a perfectly good answer to the LLM and the capture never saw it.
    # CONTENT BEATS FORM: an utterance carrying a plausible answer for the
    # CURRENT stage is read by the capture machinery, question-shaped or not.
    # Digits only — "Bet kada galima skambinti?" is the caller ASKING and
    # must still divert; a garbled question-word around "nuo 17-18" is not.
    if state.ticket.stage == "phone":
        _answer_content = len(re.sub(r"\D", "", user_input or "")) >= 6
    else:
        _answer_content = bool(re.search(r"\d", user_input or ""))
    if (
        not und_handled
        and not _answer_content
        and any(m in low_q for m in vocab("ticket_offscript_question"))
    ):
        # Keyword question-divert (fallback only): the pass, when it ran,
        # already said this is NOT a question.
        state.turn.ticket_offscript_question = True
        rt.tracer.emit("decision", intent="ticket_dialogue", action="question")
        return
    # Explicit "do not register" cancels the dialogue (their call, their
    # choice) — after ONE confirm round; the scripted reply closes with a
    # goodbye only on the confirmed refusal.
    if not und_handled and any(m in low_q for m in vocab("ticket_cancel")):
        if wants_to_keep_solving(state, rt, user_input):
            abort_ticket_to_solving(state, rt)
            return
        _refuse_registration(state, rt, ctx)
        return
    if detect_farewell(user_input):
        state.ticket.stage = "done"
        return
    # An answer counts ONLY after its question was actually ASKED. The
    # dialogue can begin mid-turn (escalate fires while processing the
    # caller's utterance) — live 2026-08-05 the TRIGGER phrase "Neturi
    # kompiutera" was swallowed as the phone number.
    if not getattr(ctx, f"{state.ticket.stage}_asked", False):
        return
    if state.ticket.stage == "phone":
        from ...perceive.detectors import is_backchannel

        digits = re.sub(r"[^\d+]", "", user_input)
        own = caller_id(state)
        if len(re.sub(r"\D", "", digits)) >= 6:
            _take_phone(state, rt, ctx, digits[:20])
            return
        elif own and (detect_ticket_consent(user_input) == "yes" or is_backchannel(user_input)):
            # "tiks šis" / a garbled yes ("T." — STT of "Taip", observed
            # live as tel. on the ticket) — the number they call from.
            s.ticket.contact_phone = own
        elif own and ctx.phone_retry:
            # Second unclear answer — default to the caller-ID and move on.
            s.ticket.contact_phone = own
        elif not own and ctx.phone_retries >= limits.get("hidden_number_asks_max"):
            # #80: a hidden number and none said — registered all the same, and the ticket
            # says there is no number to call (never "unknown").
            s.ticket.contact_phone = NO_NUMBER
        else:
            # Not a number, not a yes — the agent SAYS what it needs and
            # re-asks ONCE ("understand the answer, re-ask when it is not
            # one" — 2026-08-05); garbage never lands on the ticket.
            ctx.phone_retry = True
            ctx.phone_retries += 1
            ctx.ask_retry = "phone"
            rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_retry")
            return
        rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_captured")
        state.ticket.stage = "hours"
    else:
        when = hours_words(_clean_hours(user_input))
        plausible = bool(when)
        if not plausible and not ctx.hours_retry:
            ctx.hours_retry = True
            ctx.ask_retry = "hours"
            rt.tracer.emit("decision", intent="ticket_dialogue", action="hours_retry")
            return
        # Strip trailing STT punctuation — "Bet kada?" landed on the ticket
        # (and in the announce) with the question mark. Second unclear
        # answer defaults to "bet kada" (spoken back in the announce).
        s.ticket.contact_hours = when[:80] if plausible else "bet kada"
        rt.tracer.emit("decision", intent="ticket_dialogue", action="hours_captured")
        state.ticket.stage = "done"
    return


# Laiko atsakymo skaitymas (hours_words): paliekam tik raides, skaitmenis, dvitaškį ir brūkšnį.
_CLEAN_RE = re.compile(r"[^\w\s:\-\u2013]")
_SPACE_RE = re.compile(r"\s+")
_HOUR = r"(\d{1,2})(?::\d{2})?"
_HOUR_RE = re.compile(_HOUR)
_NUO_IKI_RE = re.compile(r"(?:nuo\s+)?" + _HOUR + r"[^\d]{0,14}?iki\s+" + _HOUR)
_DASH_RE = re.compile(_HOUR + r"\s*[-\u2013]\s*" + _HOUR)
_PO_RE = re.compile(r"(po)\s+(?:\w+\s+){0,2}?" + _HOUR)
_IKI_RE = re.compile(r"(iki)\s+(?:\w+\s+){0,2}?" + _HOUR)
_APIE_RE = re.compile(r"(apie)\s+(?:\w+\s+){0,2}?" + _HOUR)


def hours_words(text: str) -> str:
    """Kada skambinti — perskaitoma eilutė, arba "" jei atsakyme laiko nėra.

    Gyvai 2026-10-05 į tiketą pakliuvo „na dvylikos, iki trilykos, valandos", anksčiau —
    „6 00 123 0"; abu atrodė „patikimi", nes turėjo skaitmenį ar žodį „val". Meistrui tai
    neperskaitoma, tad laikas dabar SURENKAMAS: valandų žodžiai paverčiami skaičiais (ASR juos
    darko, tad lyginama žodžio pradžia), o iš jų statoma „nuo 12 iki 13 val.", „po 17 val."
    arba dienos dalis („bet kada", „vakarais"). Neperskaitomas atsakymas grąžina "" — tada
    suveikia esamas vienas perklausimas, o po jo „bet kada".
    """
    low = _CLEAN_RE.sub(" ", (text or "").lower())
    low = _SPACE_RE.sub(" ", low).strip()
    if not low:
        return ""
    words = vocab_map("hour_words")
    spelled = [
        next((digits for stem, digits in words.items() if token.startswith(stem)), token)
        for token in low.split()
    ]
    low = " ".join(spelled)
    anytime = any(w in low for w in vocab("hours_anytime_words"))
    when = [w for w in vocab("hours_when_words") if w in low]
    # Live 2026-10-12: „Nuo 5 iki 6 vakare" went on the ticket as „nuo 5 iki 6 val." (a
    # technician would call at five in the morning), „Rytoj, nuo 8 iki 10" lost „rytoj", and
    # „darbo laiku" became „bet kada". The day and the part of the day are part of WHEN.
    day = next((d for stem, d in vocab_map("hours_day_words").items() if stem in low), "")
    pm = any(w in low for w in vocab("hours_pm_words"))
    prefix = f"{day} " if day else ""

    def _clock(hour: int) -> int:
        return hour + 12 if pm and hour < 12 else hour

    span = _NUO_IKI_RE.search(low) or _DASH_RE.search(low)
    if span:
        first, second = int(span.group(1)), int(span.group(2))
        if second < first and second + 12 <= 24:
            second += 12  # „nuo 12 iki 1" runs into the afternoon: 12–13
        if first <= 24 and second <= 24:
            return f"{prefix}nuo {_clock(first)} iki {_clock(second)} val."
    one = _PO_RE.search(low) or _IKI_RE.search(low) or _APIE_RE.search(low)
    if one and int(one.group(2)) <= 24:
        return f"{prefix}{one.group(1)} {_clock(int(one.group(2)))} val."
    if any(w in low for w in vocab("hours_workday_words")):
        return f"{prefix}darbo laiku"
    if anytime:
        return f"{prefix}bet kada"
    if when:
        # Dienos dalis perskaitoma ir kliento žodžiais („per pietus arba ryte"), tad sakinys su
        # ja paliekamas, o ne suvienodinamas iki vieno žodžio.
        said = _hours_only(_SPACE_RE.sub(" ", re.sub(r"[?!]", " ", text or "")).strip(" .,"))
        return said if len(said.split()) <= 6 else when[0]
    hours = [int(h) for h in _HOUR_RE.findall(low) if int(h) <= 24]
    if len(hours) == 1:
        return f"{prefix}apie {_clock(hours[0])} val."
    return ""  # nei laiko, nei dienos dalies — perklausiam


def _hours_only(text: str) -> str:
    """Keep the part of the answer that says WHEN.

    A caller answers a whole thought — "Galit meistrą registruoti. Nuo 12 iki 1" — and all of
    it landed on the ticket and was read back to them ("Skambinsime ***0106, galit meistrą
    registruoti. Nuo 12 iki 1", live 2026-09-23). Sentences with a time stay, the rest goes;
    when nothing looks like a time, the answer is kept whole.
    """
    parts = [p.strip(" .,") for p in re.split(r"(?<=[.!?])\s+", text) if p.strip(" .,")]
    if len(parts) < 2:
        return text
    marks = vocab("contact_hours_marks")
    kept = [p for p in parts if re.search(r"\d", p) or any(m in p.lower() for m in marks)]
    return " ".join(kept) if kept else text


def _clean_hours(text: str) -> str:
    """The hours answer without STT punctuation — „Bet kada? Bet kurio laiko?" carries „?"
    mid-string, and none of it belongs on the ticket or in the announce."""
    clean = (text or "").strip().strip(" .?!,")
    return re.sub(r"\s+", " ", re.sub(r"[?!]", " ", clean)).strip(" .,")


_DIGIT_RUN_RE = re.compile(r"\d[\d\s\-]*\d|\d")


def _said_numbers(text: str) -> set[str]:
    """The numbers the caller said — each run of digits („8 612 34567") as one number, as
    written and with spoken number words read as digits."""
    from ...contract.locale import lang

    raw = text or ""
    runs = _DIGIT_RUN_RE.findall(raw) + _DIGIT_RUN_RE.findall(lang().normalize_numbers(raw))
    return {re.sub(r"\D", "", run) for run in runs}


def _national(digits: str) -> str:
    """A Lithuanian number without its country code or trunk prefix (370… / 8…)."""
    if digits.startswith("370") and len(digits) == 11:
        return digits[3:]
    if digits.startswith("8") and len(digits) == 9:
        return digits[1:]
    return digits


def _same_phone(a: str, b: str) -> bool:
    return _national(re.sub(r"\D", "", a)) == _national(re.sub(r"\D", "", b))


def _grounded_phone(value: str, user_input: str) -> str | None:
    """The ticket reader's number, when the caller said that whole number; else None."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 6:
        return None
    if any(_national(digits) == _national(said) for said in _said_numbers(user_input)):
        return re.sub(r"[^\d+]", "", value)[:20]
    return None


def _hours_grounded(value: str, user_input: str) -> bool:
    """The ticket reader's hours are made of the caller's words: every number is one they
    said, and every word shares its stem with one of theirs (Lithuanian endings change:
    „ryte" / „ryto", „pietų" / „pietus"); short words („po", „iki") must match whole."""
    from ...contract.locale import lang

    value_low = lang().normalize_numbers(value or "").lower()
    said_low = lang().normalize_numbers(user_input or "").lower()
    if not set(re.findall(r"\d+", value_low)) <= set(re.findall(r"\d+", said_low)):
        return False
    said_words = re.findall(r"[^\W\d_]+", said_low)
    glue = set(vocab("hours_glue_words"))
    for word in re.findall(r"[^\W\d_]+", value_low):
        if word in glue:
            continue
        if len(word) <= 2:
            if word not in said_words:
                return False
            continue
        stem = word[: 3 if len(word) <= 4 else 4]
        if not any(w.startswith(stem) for w in said_words):
            return False
    return True


def _take_phone(state: Any, rt: Any, ctx: Any, number: str) -> None:
    """A number the caller said. The caller ID is taken as it is; any other number is read
    back („Užrašiau … — ar teisingai?") and lands on the ticket only on a yes."""
    own = caller_id(state)
    state.ticket.context = ctx
    ctx.phone_confirm_unclear = False
    if own and _same_phone(number, own):
        ctx.phone_pending = None
        state.ticket.contact_phone = own
        state.ticket.stage = "hours"
        rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_captured")
        return
    ctx.phone_pending = number
    ctx.ask_phone_confirm = True
    rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_confirm")


def _refuse_registration(state: Any, rt: Any, ctx: Any) -> None:
    """„Neregistruokit": one confirm round before the one-way door, then cancelled."""
    if ctx.cancel_confirm_asked:
        state.ticket.stage = "cancelled"
        from ...decide.question import clear_owner as _q_clear_owner

        _q_clear_owner(state, rt, "ticket")
        rt.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
        return
    ctx.cancel_confirm_asked = True
    ctx.ask_cancel_confirm = True
    rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_confirm")


def _take_pending(state: Any, rt: Any, ctx: Any, action: str) -> None:
    state.ticket.contact_phone = ctx.phone_pending
    ctx.phone_pending = None
    ctx.phone_confirm_unclear = False
    rt.tracer.emit("decision", intent="ticket_dialogue", action=action)


def phone_confirm_answer(state: Any, rt: Any, pending: str, user_input: str) -> tuple[str, str]:
    """What the caller answered to „Užrašiau {numeris} — ar teisingai?": (kind, number).

    kind is "same" (the read-back number again), "new" (another number, given as `number`),
    "question", "keep_solving", "cancel", "no", "yes", "farewell" or "unclear". Read in this
    order: a number beats every word around it, a question beats a yes inside it."""
    from ...perceive.detectors import (
        detect_farewell,
        detect_ticket_consent,
        is_backchannel,
        is_bare_negation,
        is_real_question,
    )

    said = re.sub(r"[^\d+]", "", user_input or "")
    if len(re.sub(r"\D", "", said)) >= 6:
        return ("same", pending) if _same_phone(said, pending) else ("new", said[:20])
    if is_real_question(user_input):
        return "question", ""
    if wants_to_keep_solving(state, rt, user_input):
        return "keep_solving", ""
    if any(m in (user_input or "").lower() for m in vocab("ticket_cancel")):
        return "cancel", ""
    consent = detect_ticket_consent(user_input)
    if consent == "no" or is_bare_negation(user_input):
        return "no", ""
    if consent == "yes" or is_backchannel(user_input):
        return "yes", ""
    if detect_farewell(user_input):
        return "farewell", ""
    return "unclear", ""


def read_back_repeated(state: Any, pending: str) -> bool:
    """The agent's last reply said the read-back number — a yes after it answers the read-back,
    not the answer to the caller's question."""
    last = next(
        (m.get("content") or "" for m in reversed(state.messages) if m.get("role") == "assistant"),
        "",
    )
    return any(len(n) >= 6 and _same_phone(n, pending) for n in _said_numbers(last))


def answers_read_back(state: Any, ctx: Any, kind: str) -> bool:
    """After a question, a yes / no / unclear word answers the read-back only when the reply
    repeated it; otherwise the read-back is asked again."""
    after_question, ctx.phone_confirm_after_question = ctx.phone_confirm_after_question, False
    if not after_question or kind not in ("yes", "no", "unclear"):
        return True
    return read_back_repeated(state, ctx.phone_pending)


def _read_phone_confirm(state: Any, rt: Any, ctx: Any, user_input: str) -> None:
    """The answer to „Užrašiau {numeris} — ar teisingai?": the same number again or a yes takes
    it, a new number is read back in turn, a no asks for it again; a question is answered and the
    read-back stays; „neregistruokit" goes to the cancel-confirm; a goodbye registers with the
    number they dictated; an unclear answer repeats the read-back once."""
    kind, number = phone_confirm_answer(state, rt, ctx.phone_pending, user_input)
    if not answers_read_back(state, ctx, kind):
        ctx.ask_phone_confirm = True
        rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_confirm_repeat")
        return
    if kind == "same":
        _take_pending(state, rt, ctx, "phone_confirmed")
        state.ticket.stage = "hours"
        return
    if kind == "new":
        _take_phone(state, rt, ctx, number)
        return
    if kind == "question":
        ctx.phone_confirm_out = True  # the next answer is still read against the read-back
        ctx.phone_confirm_after_question = True
        state.turn.ticket_offscript_question = True
        rt.tracer.emit("decision", intent="ticket_dialogue", action="question")
        return
    if kind == "keep_solving":
        abort_ticket_to_solving(state, rt)
        return
    if kind == "cancel":
        _refuse_registration(state, rt, ctx)
        return
    if kind == "no":
        ctx.phone_pending = None
        ctx.phone_confirm_unclear = False
        ctx.ask_phone_reask = True
        rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_reask")
        return
    if kind == "yes":
        _take_pending(state, rt, ctx, "phone_confirmed")
        state.ticket.stage = "hours"
        return
    if kind == "farewell":
        # The caller is done talking: the number they dictated beats the caller ID or none.
        _take_pending(state, rt, ctx, "phone_taken_on_farewell")
        state.ticket.stage = "done"
        return
    if not ctx.phone_confirm_unclear:
        ctx.phone_confirm_unclear = True
        ctx.ask_phone_confirm = True
        rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_confirm_repeat")
        return
    ctx.phone_pending = None
    ctx.phone_confirm_unclear = False
    ctx.ask_phone_reask = True
    rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_reask")


def ticket_need(state: Any, rt: Any) -> str:
    """Human wording of WHY the ticket is needed ("reikalingas naujas
    maršrutizatorius"), for the intro announce and the ticket itself — never
    the raw verdict key."""
    from ...contract.locale import phrase
    from ...evidence import fault_need

    s = state
    if s.ticket.request_type:
        return phrase("ticket.need_request")
    # Wave 3: the fault is the Case's, and its reason is the card's (`escalate.need`). A
    # damaged cable used to announce itself as "gedimo tipas neaiškus" because this read the
    # walker's verdict, which no longer exists.
    cause = s.case.fault or (s.diagnosis.verdicts.get("network") or {}).get("reason") or ""
    from ...contract import cards as _cards
    from ...contract.locale import maybe_phrase as _maybe

    card = _cards.card(cause)
    if card is not None and card.escalate and card.escalate.need and _fix_was_tried(s, cause):
        card_need = _maybe(card.escalate.need)
        if card_need:
            return card_need
    if card is not None and not _fix_was_tried(s, cause):
        # P-E, again (live 2026-09-23): "routeris perkrautas, bet ryšys neatsistatė" went out
        # on a call where nobody was ever asked to reboot anything. A card's `escalate.need`
        # describes the state AFTER its fix ran; until it has, the honest wording is what we
        # SUSPECT and that we could not check it together.
        gloss = phrase_or(f"verdict.{cause}.gloss", None)
        prefix = phrase("ticket.need_suspected", gloss=gloss) if gloss else ""
        return prefix + phrase("ticket.need_not_checked")
    # The unclear fault names no cause to the caller (no telemetry jargon).
    if cause == "unclear_fault":
        return phrase("ticket.need_unclear")
    need = fault_need(cause) or phrase_or(
        f"verdict.{cause}.ticket_need", None
    )  # file first, code fallback
    if need:
        return need
    # No verdict at all — an in-scope fault the agent's knowledge cannot
    # resolve. HONEST ticket type (Andrius 2026-09-02): "neaiškus gedimas" —
    # feeds the analysis/improvement loop instead of an improvised cause.
    if not cause:
        return phrase("ticket.need_unclear")
    return phrase_or(f"verdict.{cause}.gloss", cause)


def _fix_was_tried(s: Any, cause: str) -> bool:
    """May the card's own `escalate.need` wording be used?

    Yes when its fix actually ran (`spent`, or a step was retried), and yes when the card has
    no phone fix at all — then its wording describes the situation, not an action ("routerį
    reikia sukonfigūruoti — telefonu to nepadarysime"). No when there IS something to try and
    nobody tried it: that wording would claim a reboot that never happened (live 2026-09-23).
    """
    if cause and cause in (s.case.spent or []):
        return True
    if bool(s.case.attempts) or bool(s.resolution.bridge_bound):
        return True
    if _work_done(s):
        # The Case walked real work this call — a reboot, a bridge, a bind, a written
        # procedure. Live 2026-09-30: the computer was plugged in and BOUND, the caller said
        # the internet was back, and the ticket still said „įtariama, kad linijoje nematoma
        # jokio įrenginio" — the wording for a call where nothing had been tried.
        return True
    return not _has_phone_fix(cause)


def _work_done(s: Any) -> bool:
    """Did the Case actually DO something this call (not just ask)?"""
    from ...contract import cards as _cards

    for name in s.case.did or []:
        spec = _cards.module(name)
        if spec is not None and spec.kind in ("instruct", "action"):
            return True
    return False


def _has_phone_fix(cause: str) -> bool:
    """Does this card ask the caller to DO anything, or is a technician its only answer?"""
    from ...contract import cards as _cards

    card = _cards.card(cause) if cause else None
    if card is None:
        return False
    for solution in card.solution:
        for call in solution.steps:
            spec = _cards.module(call.module)
            if spec is not None and spec.kind != "escalate":
                return True
    return False


def wants_to_keep_solving(state: Any, rt: Any, user_input: str | None) -> bool:
    """A ticket refusal that CARRIES solving content ("Ne, tai mes pajunkim
    tą kompiuterį…") — the caller is refusing the REGISTRATION, not the
    help. Live 2026-08-11: this was read as plain refusal, the dialogue
    resumed the phone question and the call closed registered while the
    caller was still asking for the bridge."""
    from ...evidence import extract_client_facts
    from ...perceive.detectors import detect_refuse_or_ticket

    # An explicit registration DEMAND is never a keep-solving signal, no matter
    # what other words ride along ("nenoriu tikrinti toliau, UŽREGISTRUOKIT" —
    # live 2026-08-13: 'tikrin'/'toliau' marks cancelled the demanded dialogue).
    if detect_refuse_or_ticket(user_input) == "demand":
        return False

    low = (user_input or "").lower()
    if bool(extract_client_facts(user_input)):
        return True
    # Polarity guard (live 2026-08-13): "nebeSPRENDžiam" matched the 'sprend'
    # mark and cancelled the ticket dialogue the caller had just DEMANDED. A
    # mark only counts when the word carrying it is not itself negated.
    for token in low.split():
        word = token.strip(".,!?…")
        if any(m in word for m in vocab("continue_solving_marks")) and not word.startswith(
            vocab("negation_prefixes")
        ):
            return True
    return False


def abort_ticket_to_solving(state: Any, rt: Any) -> None:
    """Drop the ticket dialogue WITHOUT closing the call and hand the turn
    back to solving — the narrator says so and re-anchors the last
    instruction (directive consumed in the facts block)."""
    state.ticket.stage = None
    state.ticket.context = None
    state.ticket.resume_fix_note = True
    state.dialog.resync_note = True  # C: re-anchor from the ledger, no improvising
    from ...decide.question import clear_owner as _q_clear_owner

    _q_clear_owner(state, rt, "ticket")
    rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_to_solving")


def ticket_stage_reply(state: Any, rt: Any) -> str:
    """The scripted reply for the CURRENT dialogue stage. The first phone ask
    carries the intro (phone solving is over -> registering, and WHY), so the
    caller hears the transition before the contact questions. Marks the stage
    question as ASKED — only then does the capture accept an answer — and
    speaks the retry phrasing after an unclear answer."""
    from ...contract.locale import phrase
    from ...decide.question import register as _q_register
    from ...graph_v2.state import TicketContext

    ctx = state.ticket.context or TicketContext()
    if ctx.ask_cancel_confirm:
        ctx.ask_cancel_confirm = False
        ctx.cancel_confirm_out = True
        ctx.last_kind = "cancel_confirm"
        _q_register(state, rt, "ticket", "ticket_cancel")
        if state.ticket.request_type:
            return phrase("identification.ticket_cancel_confirm_request")
        return phrase("identification.ticket_cancel_confirm")
    if ctx.ask_phone_confirm:
        from ...execute.ticket import fmt_phone

        ctx.ask_phone_confirm = False
        ctx.phone_confirm_out = True
        ctx.last_kind = "phone_confirm"
        _q_register(state, rt, "ticket", "ticket_phone_confirm")
        return phrase("identification.ticket_phone_confirm", phone=fmt_phone(ctx.phone_pending))
    if ctx.ask_phone_reask:
        ctx.ask_phone_reask = False
        ctx.last_kind = "phone_reask"
        _q_register(state, rt, "ticket", "ticket_phone")
        return phrase("identification.ticket_phone_reask")
    retry, ctx.ask_retry = ctx.ask_retry, None
    if retry == "phone":
        ctx.last_kind = "retry_phone"
        _q_register(state, rt, "ticket", "ticket_phone")
        if not caller_id(state):
            return phrase("identification.ticket_phone_hidden_retry")
        return phrase("identification.ticket_phone_retry")
    if retry == "hours":
        ctx.last_kind = "retry_hours"
        _q_register(state, rt, "ticket", "ticket_hours")
        return phrase("identification.ticket_hours_retry")
    if state.ticket.stage == "hours":
        ctx.hours_asked = True
        ctx.last_kind = "hours"
        _q_register(state, rt, "ticket", "ticket_hours")
        return phrase("identification.ticket_hours")
    parts = []
    if not ctx.intro_done:
        ctx.intro_done = True
        ctx.last_kind = "phone_intro"
        # After a WORKING bridge "telefonu išspręsti nepavyks" is jarring —
        # the internet just came back (live 2026-08-12). The intro then
        # states the success and registers the ROUTER replacement.
        if state.ticket.request_type:
            parts.append(phrase("identification.ticket_intro_request"))
        elif state.ticket.reason == "visi_veiksmai":
            parts.append(phrase("identification.ticket_intro_all_done"))
        elif state.ticket.reason == "klientas_praso":
            # They asked for a technician: no „neišspręsime" — it was their choice (#79: said
            # on a dead-router call before a single check).
            parts.append(phrase("identification.ticket_intro_asked"))
        elif state.ticket.reason == "kliento_pagalba":
            # The caller agreed to PAID help with their own device: no „neišspręsime", no fault.
            parts.append(phrase("identification.ticket_intro_paid_help"))
        elif state.resolution.bridge_bound:
            parts.append(phrase("identification.ticket_intro_bridge"))
        elif _callback_only(state):
            parts.append(phrase("identification.ticket_intro_unfinished"))
        else:
            parts.append(phrase("identification.ticket_intro", reason=ticket_need(state, rt)))
    else:
        ctx.last_kind = "phone"
    ctx.phone_asked = True
    _q_register(state, rt, "ticket", "ticket_phone")
    # #80 (live 2026-11-20): a hidden number got „Ar tiks numeris, iš kurio skambinate?" and
    # „tiks" put "unknown" on the ticket — without a caller ID the number is asked for.
    parts.append(
        phrase("identification.ticket_phone")
        if caller_id(state)
        else phrase("identification.ticket_phone_hidden")
    )
    return " ".join(parts)


def _callback_only(state: Any) -> bool:
    from ...ticket_types import callback_only

    return callback_only(state.case.fault, state.ticket.reason)


def ticket_question_turn(state: Any, rt: Any) -> tuple[str, str | None]:
    """The contact question of this turn (stage phone/hours): (rule id, words). No
    words = the narrator speaks: an off-script question, or — Zone 1 (scripts ->
    directives, Andrius 2026-08-20) — a QUESTION moment worded into the flow of the
    conversation (the directive carries the scripted fallback); retries and the
    cancel-confirm stay scripted (precision beats style on a repeat)."""
    import os

    if state.turn.ticket_offscript_question:
        return "ticket.offscript_question", None
    scripted = ticket_stage_reply(state, rt)
    ctx = state.ticket.context
    kind = ctx.last_kind if ctx else None
    if os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on" and kind in (
        "phone_intro",
        "phone",
        "hours",
    ):
        state.turn.directives.ticket = {"kind": kind, "fallback": scripted}
        return f"ticket.ask_{kind}", None
    return f"ticket.{kind}", scripted

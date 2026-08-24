"""
Perception flow — reading the caller's turn before anyone acts on it: the
evidence ingest (SUPRATIMO pass + keyword extractor), side-topic
classification, the anchor question, and the pre-turn guard sweep.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of
ReactAgent; R4 merges the understand/intent/classifier calls into ONE fast
LLM call here. Functions take the engine explicitly; intra-family calls go
through the engine delegate seam. execute_tool resolves lazily from
react_agent so the tests' import-fallback stubs apply.
"""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import logging
import os  # noqa: F401
import re
from typing import Any  # noqa: F401

from .glossary import DIAGNOSIS_LT as _DIAGNOSIS_LT  # noqa: F401

logger = logging.getLogger(__name__)


def execute_tool(name, args):
    """Lazy pass-through to react_agent's execute_tool (test stubs included)."""
    from . import react_agent

    return react_agent.execute_tool(name, args)


def step_perception_options(engine: Any):
    """(options, step) for the merged perception call — the SAME routing-key
    meanings walker_flow.classify_confirm_and_route / classify_instruct_and_advance
    build for the standalone classifier, computed once at perception time.
    Returns (None, None) when no asked step awaits an answer (or CLASSIFIER=off,
    the deterministic test mode)."""
    from .resolution import StepKind, get_strategy

    if os.getenv("CLASSIFIER", "on").lower() == "off":
        return None, None
    r = engine.state.resolution or {}
    strat = get_strategy(r.get("verdict")) if r else None
    step = strat.step(r.get("step", "")) if strat else None
    if step is None or not r.get("asked") or not engine._asked_recently(r):
        return None, None
    if step.kind is StepKind.CONFIRM and step.on and step.id != "confirm_restored":
        from .detectors import glosses as detector_glosses
        from .faults import step_options as declared_options

        declared = declared_options(r.get("verdict"), step.id)
        glosses = detector_glosses(step.detector or "yes_no")
        options: dict[str, str] = {}
        for raw in step.on:
            key = str(getattr(raw, "value", raw))
            options[key] = (declared or {}).get(key) or glosses.get(key, key)
        return options, step
    if step.kind is StepKind.INSTRUCT:
        from .detectors import glosses as detector_glosses

        return detector_glosses("instruct_done"), step
    return None, None


def ingest_client_evidence(engine, user_input: str | None) -> None:
    """Ledger v1: read the caller's utterance into the evidence ledger (called
    from the diagnosis node, so BOTH the driven and the walker path see it).
    A contradicting canonical value flags a conflict -> ONE scripted
    clarification; the next answer for that key settles it (extraction, or a
    bare yes/no polarity read; nothing readable -> the pending value wins so
    the call never loops on the clarify)."""
    s = engine.state
    # Stale-understanding hygiene (2026-08-10): the acknowledgement directive
    # leaked a PREVIOUS turn's "supratau" into the ticket dialogue's reply
    # ("Routeris sugedęs, laukiame naujo. Gerai. O kada…"). Every turn starts
    # with a clean read — the early-returns below must not keep the old one.
    engine._last_understanding = None
    engine._evidence_directive = None  # persona: fresh narrator directive per turn
    engine._findings_directive = None
    engine._recap_directive = None
    engine._ticket_directive = None
    engine._ident_directive = None
    if not user_input or not s.customer_id or s.case_closed or engine._ticket_stage:
        return
    from .evidence import CLIENT, extract_client_facts, polarity, set_fact

    # SUPRATIMO pass'as (2026-08-10): the primary sensor — one small-model
    # call reads the reply IN CONTEXT (pending question, fault needs,
    # ledger, history). Any failure -> the deterministic keyword layer
    # below, so the call never stalls on a model hiccup.
    facts: dict[str, str] | None = None
    engine._last_understanding = None
    from . import understand as _und

    if _und.enabled():
        from .evidence import spec_for, summary_lt

        spec = spec_for((s.resolution or {}).get("verdict"))
        needs = (
            "; ".join(
                f"{k}: {item.get('reikia', '')}" for k, item in (spec.get("client") or {}).items()
            )
            if spec
            else ""
        )
        allowed_extra = {
            k: set((item.get("atsakymai") or {}).keys())
            for k, item in ((spec.get("client") or {}) if spec else {}).items()
            if item.get("atsakymai")
        }
        # R4 perception merge: when an asked step awaits its answer, the SAME
        # call classifies the reply against the step's routing keys — the
        # walker consumes the cached result instead of a second LLM round-trip.
        step_options, active_step = step_perception_options(engine)
        engine._perception_step = None
        u = _und.understand(
            user_input,
            anchor=engine.anchor_text(),
            needs=needs,
            ledger_summary=summary_lt(s.evidence) if s.evidence else "",
            history_tail=[m for m in s.messages[-5:] if m.get("role") in ("user", "assistant")],
            model=engine.config.model,
            allowed_extra=allowed_extra,
            step_options=step_options,
        )
        if u is not None:
            engine._last_understanding = u
            facts = dict(u["faktai"])
            if u.get("zingsnis") and active_step is not None:
                engine._perception_step = {
                    "step_id": active_step.id,
                    "input": user_input,
                    "obs": u["zingsnis"],
                }
            engine.tracer.emit(
                "understand",
                tipas=u["tipas"],
                supratau=u["supratau"],
                neaiskumas=u["neaiskumas"],
                pasitikejimas=u["pasitikejimas"],
                faktai=u["faktai"],
                zingsnis=u.get("zingsnis"),
            )
    # The deterministic keyword layer ALWAYS runs (2026-08-12): it used to be
    # a fallback only, so when the pass answered with EMPTY faktai (the
    # confidence guard wipes low-confidence reads) the extractor never got a
    # chance — "Pabandžiau kitą rozetę, kiti įrenginiai veikia" lost
    # outlet_works and the hypothesis froze (live). Pass facts win on
    # overlap; keywords fill the keys the pass did not provide.
    kw_facts = extract_client_facts(user_input)
    kw_disagreements: dict[str, str] = {}
    if facts is None:
        facts = kw_facts
    else:
        for k, v in kw_facts.items():
            if k not in facts:
                facts[k] = v
            elif facts[k] != v:
                # The two readers DISAGREE on the SAME turn (live 2026-08-12:
                # the pass pinned "neveikia" on the OUTLET while keywords
                # read the correct "bandyta" — the silent pass win skipped
                # the recap and the announce). Neither wins silently: both
                # values go through set_fact below and the conflict clarify
                # settles it with the caller.
                kw_disagreements[k] = v
                engine.tracer.emit(
                    "evidence",
                    action="reader_disagreement",
                    key=k,
                    pass_value=facts[k],
                    kw_value=v,
                )
    # The JUST-ASKED evidence question gives short answers their meaning:
    # "Radau." to "Radote?" (no noun -> the general extractor is blind)
    # became a give-up live 2026-08-10. Context read fills ONLY the pending
    # key, and only when the general pass found nothing for it.
    pending = getattr(engine, "_evidence_last_ask_key", None)
    pending_entry = s.evidence.get(pending) if pending else None
    u_tipas = (engine._last_understanding or {}).get("tipas")
    # DONE-report without a result (live 2026-08-11): "Mhm, patikrinau."
    # says the check happened, not what it FOUND — yet the pass invented
    # power_cable=atjungtas (echoed from the agent's own explanation) and
    # the hypothesis never confirmed. A pass fact for the pending key on
    # such a turn stands only if the utterance itself corroborates it
    # (the key's markers / the keyword extractor); otherwise it is dropped
    # and the drive asks WHAT was found ("pasitikslinti, o ne kurti").
    engine._done_report_key = None
    if engine._last_understanding is not None and pending and pending in facts:
        from .resolution import is_bare_done_report

        if is_bare_done_report(user_input) and (
            pending_entry is None or pending_entry.get("value") == "neaišku"
        ):
            from .evidence import read_pending_answer as _rpa
            from .evidence import spec_for as _spec_for

            _spec = _spec_for((s.resolution or {}).get("verdict"))
            _item = (_spec.get("client") or {}).get(pending) if _spec else None
            corroborated = (
                _rpa(pending, user_input, _item) == facts[pending]
                or extract_client_facts(user_input).get(pending) == facts[pending]
            )
            if not corroborated:
                engine.tracer.emit(
                    "evidence",
                    action="done_report_value_dropped",
                    key=pending,
                    value=facts[pending],
                )
                del facts[pending]
                engine._done_report_key = pending
    # SUPPLEMENT, not just fallback (2026-08-10 round 2): the pass returned
    # tipas=atsakymas with an empty faktai for "…sakiau, kad RADAU" and the
    # key was given up on. When the pass failed OR answered without the
    # pending key, the deterministic context read fills that ONE key —
    # conservative marks + the conflict machinery guard against misreads.
    if (
        (engine._last_understanding is None or u_tipas == "atsakymas")
        and pending
        and pending not in facts
        and (pending_entry is None or pending_entry.get("value") == "neaišku")
    ):
        from .evidence import read_pending_answer, spec_for

        spec = spec_for((s.resolution or {}).get("verdict"))
        spec_item = (spec.get("client") or {}).get(pending) if spec else None
        value = read_pending_answer(pending, user_input, spec_item)
        if value is not None:
            facts[pending] = value
    turn = s.turn_count
    # A clarify is out — settle that key first.
    pending_key = engine._evidence_conflict_asked
    if pending_key:
        value = facts.get(pending_key)
        if value is None and pending_key == "has_computer":
            value = polarity(user_input)
        entry = s.evidence.get(pending_key)
        if value is not None:
            set_fact(s.evidence, pending_key, value, CLIENT, turn)
        elif entry is not None and entry.get("conflict"):
            # Unreadable answer — keep the LATEST stated value, stop asking.
            set_fact(s.evidence, pending_key, entry.get("pending"), CLIENT, turn)
        engine._evidence_conflict_asked = None
        engine.tracer.emit(
            "evidence",
            action="conflict_resolved",
            key=pending_key,
            value=(s.evidence.get(pending_key) or {}).get("value"),
        )
        facts.pop(pending_key, None)
    if pending and pending in facts:
        engine._evidence_last_ask_key = None  # answered — later "taip" maps to nothing old
    # Contradiction corroboration (2026-08-10): an LLM fact that FLIPS an
    # already-established ledger entry needs the keyword extractor to read
    # the same flip from the utterance — otherwise it is dropped and the
    # established fact stands ("Neturi kompiuterio" hallucinated
    # device_present=nerado against a settled "rado" and forced a phantom
    # clarify). New facts (no entry yet) are accepted as before.
    if engine._last_understanding is not None and facts:
        kw = extract_client_facts(user_input)
        for key in list(facts):
            entry = s.evidence.get(key)
            if (
                entry is not None
                and entry.get("source") == CLIENT
                and not entry.get("conflict")
                and entry.get("value") not in ("neaišku",)
                and entry.get("value") != facts[key]
                and kw.get(key) != facts[key]
            ):
                # Second corroboration source (live 2026-08-11): the general
                # extractor needs the TOPIC word in the sentence ("laidas"),
                # but the caller answers "Tai įkištas" without naming it —
                # the pass already says the utterance is ABOUT this key, so
                # the key's OWN answer markers corroborate the flip too.
                from .evidence import read_pending_answer, spec_for

                spec = spec_for((s.resolution or {}).get("verdict"))
                spec_item = (spec.get("client") or {}).get(key) if spec else None
                if read_pending_answer(key, user_input, spec_item) == facts[key]:
                    continue
                engine.tracer.emit(
                    "evidence", action="uncorroborated_flip_dropped", key=key, value=facts[key]
                )
                del facts[key]
    for key, value in facts.items():
        entry = set_fact(s.evidence, key, value, CLIENT, turn)
        if entry.get("conflict") and engine._evidence_conflict is None:
            engine._evidence_conflict = (key, entry["value"], entry["pending"])
            engine.tracer.emit(
                "evidence",
                action="conflict",
                key=key,
                old=entry["value"],
                new=entry["pending"],
            )
        else:
            engine.tracer.emit("evidence", action="fact", key=key, value=value)
    # Reader disagreements land SECOND: on a fresh key this flags the
    # conflict (one scripted clarify settles it); if the flip guard dropped
    # the pass value above, the keyword read simply stands as the fact.
    for key, kw_value in kw_disagreements.items():
        entry = set_fact(s.evidence, key, kw_value, CLIENT, turn)
        if entry.get("conflict") and engine._evidence_conflict is None:
            engine._evidence_conflict = (key, entry["value"], entry["pending"])
            engine.tracer.emit(
                "evidence",
                action="conflict",
                key=key,
                old=entry["value"],
                new=entry["pending"],
            )
        else:
            engine.tracer.emit("evidence", action="fact", key=key, value=kw_value)


def anchor_text(engine) -> str:
    """The exact place to return to after a deviation — the engine's LAST
    asked question (deterministic), never the LLM's memory of it. Trimmed
    to the QUESTION sentence only: anchoring the whole reply re-read a long
    announce back at the caller (live 2026-08-10)."""
    q = (engine.state.last_question or "").strip()
    if not q:
        return "Ar tęsiame gedimo sprendimą?"
    sentences = re.split(r"(?<=[.!?])\s+", q)
    questions = [x for x in sentences if x.strip().endswith("?")]
    return (questions[-1] if questions else sentences[-1]).strip()


def classify_side_topic(engine, user_input: str | None) -> bool:
    """Is THIS turn a deviation (a real question with no usable facts)
    during analysis/solving? Sets the per-turn flag + the streak; a
    productive turn resets the streak. Mechanics turns (ticket dialogue,
    conflict clarify, end-confirm) are never deviations — their owners
    handle them."""
    from .evidence import extract_client_facts
    from .resolution import is_real_question

    s = engine.state
    engine._side_topic_this_turn = False
    if not user_input or not s.customer_id or s.case_closed or engine._ticket_stage:
        return False
    if engine._evidence_conflict or engine._end_confirm_pending or engine._resume_hold:
        return False
    # Ticket demand is NEVER a side topic (live 2026-08-13: "Išregistruoti
    # meistrą ir paleisti internetą…" got tipas=nukrypimas and the side_topic
    # LLM talked the caller OUT of the registration) — the demand machinery
    # in the solving path owns this turn.
    from .resolution import detect_refuse_or_ticket

    if detect_refuse_or_ticket(user_input) == "demand":
        engine._side_topic_turns = 0
        engine.tracer.emit("decision", intent="side_topic", action="ticket_demand_passthrough")
        return False
    # How-to / help requests while an instruction or question stands are ON
    # TASK by definition (live 2026-08-21: "O kaip tai padaryti?" at the
    # bridge instruction got the FAQ "ne mano sritis") — the step explains.
    if is_howto(user_input) and (
        getattr(engine, "_evidence_last_ask_key", None) or (s.resolution or {}).get("asked")
    ):
        engine._side_topic_turns = 0
        engine.tracer.emit("decision", intent="side_topic", action="on_task_howto")
        return False
    # The understanding pass judged this turn IN CONTEXT — but its tipas is
    # ONE model field, and side_topic FREEZES the engine, so a single sensor
    # may not decide alone (live 2026-08-10: "Galim dabar patikrinti" got
    # tipas=klausimas and the answer was answered with a price non-sequitur).
    # CORROBORATION rule: enter only when a deterministic signal agrees —
    # a question word in the text or a FAQ keyword hit.
    u = getattr(engine, "_last_understanding", None)
    if u is not None:
        if u["tipas"] in ("klausimas", "nukrypimas") and not u["faktai"]:
            if extract_client_facts(user_input):
                # The keyword layer read facts the pass missed — an
                # informative interruption, not a deviation (they already
                # landed on the ledger via the always-on supplement).
                engine._side_topic_turns = 0
                return False
            from .faq import match as faq_match

            # A question ABOUT the current instruction is NOT a deviation
            # (live 2026-08-11: "Kur jungti tą kabelį į kompiuterį?" got
            # "tai nėra mano sritis"). FAQ topics stay side topics.
            if not faq_match(user_input) and engine._on_task_question(user_input):
                engine.tracer.emit("decision", intent="side_topic", action="on_task")
                engine._side_topic_turns = 0
                return False
            corroborated = is_real_question(user_input) or bool(faq_match(user_input))
            if corroborated:
                engine._side_topic_this_turn = True
                engine._side_topic_turns += 1
                engine.tracer.emit(
                    "decision",
                    intent="side_topic",
                    action="enter",
                    streak=engine._side_topic_turns,
                )
                return True
            # The model felt a deviation but the text carries no question —
            # treat as an on-topic turn (the evidence/solver flow continues).
            engine.tracer.emit("decision", intent="side_topic", action="uncorroborated")
            engine._side_topic_turns = 0
            return False
        engine._side_topic_turns = 0
        return False
    if not is_real_question(user_input):
        engine._side_topic_turns = 0
        return False
    if extract_client_facts(user_input):
        # An informative interruption ANSWERS things — not a deviation.
        engine._side_topic_turns = 0
        return False
    from .faq import match as faq_match

    if not faq_match(user_input) and engine._on_task_question(user_input):
        engine.tracer.emit("decision", intent="side_topic", action="on_task")
        engine._side_topic_turns = 0
        return False
    engine._side_topic_this_turn = True
    engine._side_topic_turns += 1
    engine.tracer.emit(
        "decision", intent="side_topic", action="enter", streak=engine._side_topic_turns
    )
    return True


_HOWTO = (
    "kaip ",
    "kaip?",
    "padėk",
    "padek",
    "nežinau kaip",
    "nezinau kaip",
    "kokie kabel",
    "kokį kabel",
    "koki kabel",
    "kur jung",
    "kur kišt",
    "kur kist",
    "ką daryti",
    "ka daryti",
    "paaiškink",
    "paaiskink",
)


def is_howto(text: str | None) -> bool:
    """A 'how do I do that / help me' request — about the standing task."""
    low = f" {(text or '').lower()} "
    return any(m in low for m in _HOWTO)


def on_task_question(engine, user_input: str | None) -> bool:
    """The 'deviation' shares content words with the agent's LAST reply —
    it is a question ABOUT the current instruction ("Kur jungti tą
    kabelį?"), not a side topic; the solver/narrator answers it in place.
    Folded prefix-overlap (≥5 chars) so inflections and dropped diacritics
    still match ("jungti" ~ "prijungsite", "kabelį" ~ "kabelio")."""
    last = engine._last_agent_question() or ""
    if not last or not user_input:
        return False
    from .evidence import _fold

    last_f = _fold(last)
    for tok in _fold(user_input).replace("?", " ").replace(",", " ").split():
        tok = tok.strip(".!?")
        if len(tok) >= 5 and tok[:5] in last_f:
            return True
    return False


def pre_turn_guards(engine, user_input: str) -> None:
    """Deterministic per-turn guards, run BEFORE the LLM sees the turn.

    (1) Address-offer reply guard: a reply to "Ar skambinate dėl X?" commits the
        account ONLY on a CLEAN yes — a garbled/mixed reply ("Taip, nebija" = STT
        mangle of a denial) vetoes the commit and the agent re-asks (observed live:
        wrong apartment's debt read to the caller).
    (2) Reopen identification: an already-identified caller says they are calling
        about a DIFFERENT address -> drop the identity and ask for the address
        again instead of carrying on about the wrong account."""
    s = engine.state
    engine._addr_confirm_note = None
    engine._addr_diag_note = None  # F2: fresh lookup diagnosis per turn
    engine._ident_directive = None  # zone 2: ingest may not run pre-identification
    engine._reopen_note = False
    if not user_input:
        return
    # (-2) Ticket-dialogue capture: the previous scripted reply asked for the
    # contact number / hours — read the answer. A question falls through to the
    # LLM (the stage stays and re-asks); a farewell fast-forwards with defaults
    # (the caller is done talking — register with what we have).
    if engine._ticket_stage in ("phone", "hours"):
        from .resolution import detect_farewell, detect_ticket_consent

        engine._ticket_offscript = False
        low_q = (user_input or "").lower()
        ctx = engine._ticket_ctx if engine._ticket_ctx is not None else {}
        # Cancel-confirm answer (2026-08-11): the previous reply asked
        # "registruoti, ar tikrai nereikia?" — read THIS turn against that
        # question only. Live, a bare "Ne." (a barge-in crumb) cancelled the
        # ticket AND closed the call in one breath; cancelling is a one-way
        # door, so it now takes a confirmed refusal.
        if ctx.pop("cancel_confirm_out", False):
            from .resolution import is_bare_negation

            # "Ne, tai pajunkim tą kompiuterį" refuses the TICKET, not the
            # help — back to solving, never back to the phone question.
            if engine._wants_to_keep_solving(user_input):
                engine._abort_ticket_to_solving()
                return
            if is_bare_negation(user_input) or any(
                m in low_q for m in ("neregistruok", "nereikia", "atšauk", "atsauk", "nenoriu")
            ):
                engine._ticket_stage = "cancelled"
                engine.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
                return
            # Anything else resumes the registration — the stage re-asks.
            engine.tracer.emit(
                "decision", intent="ticket_dialogue", action="cancel_confirm_resumed"
            )
            return
        # SUPRATIMO pass'as pirmiau (2026-08-10, Andrius): caller phrasing
        # cannot be predicted — "Bet kada galima per pietus iš ryto" IS an
        # hours answer, but "galima" sat on the keyword question list and
        # diverted it. The model reads the answer against THIS question;
        # keyword logic below stays as the fallback when it is unavailable.
        und_handled = False
        from . import understand as _und

        if _und.enabled():
            ut = _und.understand_ticket(
                user_input,
                stage=engine._ticket_stage,
                anchor=(s.last_question or ""),
                model=engine.config.model,
            )
            if ut is not None:
                und_handled = True
                engine.tracer.emit(
                    "understand_ticket",
                    stage=engine._ticket_stage,
                    tipas=ut["tipas"],
                    reiksme=ut.get("reiksme"),
                )
                if ut["tipas"] == "klausimas":
                    # Echo of our own offer (D, live 2026-08-20): "Ar tiks tas,
                    # iš kurio skambinu?" repeated back with rising intonation
                    # is CONSENT — answering it and re-asking doubled the
                    # question. Fuzzy overlap with what we just asked decides.
                    if engine._ticket_stage == "phone":
                        from .barge_in import token_overlap

                        if token_overlap(user_input, s.last_question or "") >= 0.8:
                            s.contact_phone = s.caller_phone
                            engine._ticket_stage = "hours"
                            engine.tracer.emit(
                                "decision", intent="ticket_dialogue", action="phone_echo_consent"
                            )
                            return
                    engine._ticket_offscript = True
                    engine.tracer.emit("decision", intent="ticket_dialogue", action="question")
                    return
                if ut["tipas"] == "atsisakymas":
                    # Refusal WITH solving content skips the confirm — the
                    # caller told us what they want: keep fixing.
                    if engine._wants_to_keep_solving(user_input):
                        engine._abort_ticket_to_solving()
                        return
                    # One confirm round before the one-way door (2026-08-11):
                    # "Ne." to "ar tiks šis numeris?" may mean "kitu numeriu",
                    # not "neregistruokite" — clarify before dropping the
                    # ticket the caller was just promised.
                    if ctx.get("cancel_confirm_asked"):
                        engine._ticket_stage = "cancelled"
                        engine.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
                        return
                    ctx["cancel_confirm_asked"] = True
                    ctx["ask_cancel_confirm"] = True
                    engine.tracer.emit(
                        "decision", intent="ticket_dialogue", action="cancel_confirm"
                    )
                    return
                if not ctx.get(f"{engine._ticket_stage}_asked"):
                    return  # trigger-swallow guard (question not asked yet)
                value = ut.get("reiksme")
                if value:
                    if engine._ticket_stage == "phone":
                        digits = re.sub(r"\D", "", value)
                        if value == "tas_pats":
                            s.contact_phone = s.caller_phone
                        elif len(digits) >= 6:
                            s.contact_phone = re.sub(r"[^\d+]", "", value)[:20]
                        else:
                            value = None  # not a usable number — keyword/retry path
                        if value is not None:
                            engine.tracer.emit(
                                "decision", intent="ticket_dialogue", action="phone_captured"
                            )
                            engine._ticket_stage = "hours"
                            return
                    else:
                        s.contact_hours = re.sub(r"[?!]", " ", value).strip(" .,")[:80]
                        engine.tracer.emit(
                            "decision", intent="ticket_dialogue", action="hours_captured"
                        )
                        engine._ticket_stage = "done"
                        return
                # No reiksme — fall through to the keyword/retry machinery.
        if not und_handled and any(
            m in low_q
            for m in (
                "kodėl",
                "kodel",
                "kiek",
                "kam ",
                "kas čia",
                "kas cia",
                "kokiu",
                "koks ",
                "kokia ",
                "galima",
                "ar ",
            )
        ):
            # Keyword question-divert (fallback only): the pass, when it ran,
            # already said this is NOT a question.
            engine._ticket_offscript = True
            engine.tracer.emit("decision", intent="ticket_dialogue", action="question")
            return
        # Explicit "do not register" cancels the dialogue (their call, their
        # choice) — after ONE confirm round; the scripted reply closes with a
        # goodbye only on the confirmed refusal.
        if not und_handled and any(
            m in low_q
            for m in ("neregistruok", "nereikia regi", "nereikia tiket", "atšauk", "atsauk")
        ):
            if engine._wants_to_keep_solving(user_input):
                engine._abort_ticket_to_solving()
                return
            if ctx.get("cancel_confirm_asked"):
                engine._ticket_stage = "cancelled"
                engine.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
                return
            ctx["cancel_confirm_asked"] = True
            ctx["ask_cancel_confirm"] = True
            engine.tracer.emit("decision", intent="ticket_dialogue", action="cancel_confirm")
            return
        if detect_farewell(user_input):
            engine._ticket_stage = "done"
            return
        # An answer counts ONLY after its question was actually ASKED. The
        # dialogue can begin mid-turn (escalate fires while processing the
        # caller's utterance) — live 2026-08-05 the TRIGGER phrase "Neturi
        # kompiutera" was swallowed as the phone number.
        if not ctx.get(f"{engine._ticket_stage}_asked"):
            return
        clean = user_input.strip().strip(" .?!,")
        if engine._ticket_stage == "phone":
            from .resolution import is_backchannel

            digits = re.sub(r"[^\d+]", "", user_input)
            if len(re.sub(r"\D", "", digits)) >= 6:
                s.contact_phone = digits[:20]
            elif detect_ticket_consent(user_input) == "yes" or is_backchannel(user_input):
                # "tiks šis" / a garbled yes ("T." — STT of "Taip", observed
                # live as tel. on the ticket) — the number they call from.
                s.contact_phone = s.caller_phone
            elif ctx.get("phone_retry"):
                # Second unclear answer — default to the caller-ID and move on.
                s.contact_phone = s.caller_phone
            else:
                # Not a number, not a yes — the agent SAYS what it needs and
                # re-asks ONCE ("understand the answer, re-ask when it is not
                # one" — 2026-08-05); garbage never lands on the ticket.
                ctx["phone_retry"] = True
                ctx["ask_retry"] = "phone"
                engine.tracer.emit("decision", intent="ticket_dialogue", action="phone_retry")
                return
            engine.tracer.emit("decision", intent="ticket_dialogue", action="phone_captured")
            engine._ticket_stage = "hours"
        else:
            # STT sticks "?" mid-string too ("Bet kada? Bet kurio laiko?") —
            # scrub ALL question/exclamation marks before the ticket/announce.
            clean = re.sub(r"\s+", " ", re.sub(r"[?!]", " ", clean)).strip(" .,")
            low_h = clean.lower()
            plausible = bool(re.search(r"\d", low_h)) or any(
                m in low_h
                for m in (
                    "bet kada",
                    "bet kad",
                    "kada nor",
                    "visada",
                    "ryt",
                    "vakar",
                    "val",
                    "darbo",
                    "diena",
                    "dien",
                    "po ",
                    "iki ",
                    "nuo ",
                    "savait",
                    "pirmad",
                    "antrad",
                    "trečiad",
                    "treciad",
                    "ketvirtad",
                    "penktad",
                    "šeštad",
                    "sestad",
                    "sekmad",
                    "dabar",
                    "šiandien",
                    "siandien",
                )
            )
            if not plausible and not ctx.get("hours_retry"):
                ctx["hours_retry"] = True
                ctx["ask_retry"] = "hours"
                engine.tracer.emit("decision", intent="ticket_dialogue", action="hours_retry")
                return
            # Strip trailing STT punctuation — "Bet kada?" landed on the ticket
            # (and in the announce) with the question mark. Second unclear
            # answer defaults to "bet kada" (spoken back in the announce).
            s.contact_hours = clean[:80] if plausible else "bet kada"
            engine.tracer.emit("decision", intent="ticket_dialogue", action="hours_captured")
            engine._ticket_stage = "done"
        return
    # (-1) Farewell mid-process is a signal to CLARIFY, never to close (policy
    # 2026-08-03): "viso gero" heard during identification / troubleshooting /
    # before the news gets ONE confirm question; only the confirmation ends the
    # call — through the outcome (registration when a strategy is active).
    from .resolution import detect_farewell, detect_ticket_consent

    if engine._end_confirm_pending and not s.case_closed:
        engine._end_confirm_pending = False
        if detect_farewell(user_input) or detect_ticket_consent(user_input) == "yes":
            if s.resolution is not None:
                from .resolution import get_strategy

                strat = get_strategy(s.resolution.get("verdict"))
                esc = strat.step("escalate") if strat else None
                s.resolution["escalate_reason"] = "Klientas nutraukė pokalbį."
                if esc is not None:
                    engine._begin_ticket_dialogue(esc)  # contacts, then register+close
                else:
                    s.case_closed = True
                    s.closed_reason = "declined"
            else:
                s.case_closed = True
                s.closed_reason = "declined"
            engine.tracer.emit("decision", intent="end_confirmed", action="close")
        else:
            # Changed their mind — hold the walker THIS turn so a "ne, tęskime"
            # is not misrouted as a step answer; resume next turn.
            engine._resume_hold = True
            engine._resync_note = True  # C: re-anchor from the ledger, no improvising
            engine.tracer.emit("decision", intent="end_declined", action="resume")
        return
    mid_process = not s.case_closed and (
        not s.customer_id
        or s.resolution is not None
        or engine._result_pending
        or (bool(s.diagnosis) and not (engine._news_told or s.outage_reported))
    )
    if mid_process and detect_farewell(user_input):
        engine._end_confirm_pending = True
        engine.tracer.emit("decision", intent="farewell_mid_process", action="confirm_end")
        return
    # (0) Caller-intro capture: the previous reply asked WHO is calling (the
    # identification ladder's last rung) — record the answer verbatim (for the
    # RECORD, 5d rule) + a keyword relation read. The deferred check result goes
    # out in THIS turn's reply (see the RESULT facts directive).
    if s.customer_id and engine._result_pending and not s.caller_name:
        from .identification import detect_caller_relation
        from .resolution import detect_farewell, is_real_question

        # Question by WORDS only — STT sticks "?" onto rising intonation
        # ("Tomas? Ne, mano vardas Tomas…" is the ANSWER, not a question).
        if is_real_question(user_input):
            return  # off-script — the LLM answers; the ladder re-asks next turn
        if not detect_farewell(user_input):
            # Wait/consent-only replies are NOT a name ("Taip.", "Laukiu, laukiu"
            # were captured as names live) — record "nenurodyta" and move on.
            tokens = [t.strip(".,!?") for t in user_input.lower().split()]
            _NOT_A_NAME = {
                "taip",
                "ne",
                "gerai",
                "laukiu",
                "aha",
                "mhm",
                "jo",
                "ačiū",
                "aciu",
                "ok",
                "okey",
                "nesu",
                "na",
                "nu",
                "tai",
            }
            if tokens and all(t in _NOT_A_NAME for t in tokens if t):
                s.caller_name = "nenurodyta"
                s.caller_relation = "unknown"
            else:
                # The bare NAME, not the sentence — "Taip. Mano vardas Andrius.
                # Taip, aš sutartį sudaręs asmuo." went on the ticket verbatim.
                from .identification import extract_caller_name

                s.caller_name = extract_caller_name(user_input) or user_input.strip()[:120]
                s.caller_relation = detect_caller_relation(user_input)
            engine.tracer.emit("caller_intro", name=s.caller_name, relation=s.caller_relation)
        return
    if not s.customer_id:
        q = (engine._last_agent_question() or "").lower()
        if "skambinate dėl" in q or "dėl šio adreso" in q or "adreso skambinate" in q:
            from .resolution import detect_address_confirm

            verdict = detect_address_confirm(user_input)
            if verdict == "yes" and s.phone_candidate and s.phone_candidate.get("street"):
                # Clean YES to the phone-address OFFER: the ENGINE commits the
                # identity from the candidate parts right now (the model's own
                # resolve-then-narrate path kept relapsing into confirm rounds
                # and skipping the caller question — observed live). The scripted
                # ladder reply asks WHO is calling next.
                c = s.phone_candidate
                p = s.profile
                from .slots import SlotStatus

                p.street.propose(c["street"], 1.0, SlotStatus.HEARD)
                p.house.propose(str(c.get("house") or ""), 1.0, SlotStatus.HEARD)
                if c.get("apartment"):
                    p.apartment.propose(str(c["apartment"]), 1.0, SlotStatus.HEARD)
                if c.get("city"):
                    p.city.propose(str(c["city"]), 1.0, SlotStatus.HEARD)
                if engine._engine_resolve_from_slots():
                    engine._trace_note("address_confirm", "offer confirmed; engine resolve")
                    engine._just_identified = True
                    from .identification import ask_caller

                    if ask_caller() and not s.caller_name:
                        engine._result_pending = True
                return
            if verdict != "yes":
                # Direct accept (arc v3.1): the caller DICTATED a full other address
                # in this very turn (NLU heard street+house clearly) — the ENGINE
                # resolves + diagnoses it RIGHT NOW (asking the model to call the
                # tool proved unreliable: it narrated "patikrinsiu" without acting,
                # then relapsed into a redundant confirm round). The reply then
                # echoes the address and continues per the identification ladder.
                p = engine.state.profile
                # Street/city inherit from the OFFERED address when the correction
                # names only the house/flat ("Ne, dėl 60 buto 3" — same street;
                # observed live: the engine path did not fire without this).
                if not p.street.value and p.house.value and s.phone_candidate:
                    from .slots import SlotStatus

                    if s.phone_candidate.get("street"):
                        p.street.propose(s.phone_candidate["street"], 0.9, SlotStatus.HEARD)
                    if not p.city.value and s.phone_candidate.get("city"):
                        p.city.propose(str(s.phone_candidate["city"]), 0.9, SlotStatus.HEARD)
                if p.street.value and p.house.value:
                    engine._trace_note(
                        "address_confirm",
                        "offer corrected with a full dictated address; engine resolve",
                    )
                    if engine._engine_resolve_from_slots():
                        engine._just_identified = True
                        from .identification import ask_caller

                        if ask_caller() and not s.caller_name:
                            engine._result_pending = True
                        engine._addr_confirm_note = (
                            "- IDENTIFIKUOTA (variklis jau atliko patikrą): "
                            f"adresas {s.customer_address}. Atsakymo pradžioje "
                            "pakartok adresą („Supratau — <adresas>.“) ir tęsk "
                            "pagal žemiau esančią kryptį."
                        )
                    else:
                        engine._addr_confirm_note = (
                            "- KLIENTAS PASAKĖ KITĄ ADRESĄ, bet jo patikrinti "
                            "nepavyko (žr. HEARD ADDRESS) — patikslink trūkstamą "
                            "dalį arba paprašyk pakartoti."
                        )
                else:
                    engine._addr_confirm_note = (
                        "- ADRESAS NEPATVIRTINTAS: kliento atsakymas AIŠKIAI "
                        "nepatvirtino pasiūlyto adreso (girdisi neigimas ar "
                        "neaiškumas). NEkviesk resolve_address su pasiūlytu adresu. "
                        "Jei klientas įvardijo KITĄ adresą (žr. HEARD ADDRESS) — "
                        "naudok TĄ. Kitu atveju mandagiai perklausk: „Atsiprašau, "
                        "nesupratau — dėl kokio adreso skambinate?“"
                    )
                    engine._trace_note(
                        "address_confirm",
                        f"offer not confirmed (verdict={verdict}); veto commit",
                        level="warn",
                    )
    elif not s.case_closed:
        from .resolution import detect_address_correction

        if detect_address_correction(user_input):
            engine._reopen_identification(user_input)


def engine_resolve_from_slots(engine) -> bool:
    """Deterministic identification commit from clearly-heard slots: the ENGINE
    calls resolve_address (+ the silent diagnose) itself — no LLM tool-call
    hesitancy, no confirm-round relapse. True when a customer committed."""
    p = engine.state.profile
    args: dict[str, str] = {
        "street": str(p.street.value),
        "house_number": str(p.house.value),
    }
    if p.apartment.value:
        args["apartment_number"] = str(p.apartment.value)
    if p.city.value:
        args["city"] = str(p.city.value)
    try:
        obs = execute_tool("resolve_address", args)
    except Exception as e:  # pragma: no cover - best-effort
        engine._trace_note("engine_resolve", str(e), level="error")
        return False
    engine.tracer.emit("tool_call", name="resolve_address", args=args)
    engine._trace_tool_result("resolve_address", obs)
    engine._update_state_from_observation("resolve_address", obs)
    if not engine.state.customer_id:
        return False
    engine.ensure_diagnosed()
    return True

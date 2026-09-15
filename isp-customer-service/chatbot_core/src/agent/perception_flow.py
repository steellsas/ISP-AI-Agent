"""
Perception flow — reading the caller's turn before anyone acts on it: the
evidence ingest (SUPRATIMO pass + keyword extractor), side-topic
classification, the anchor question, and the pre-turn guard sweep.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of ReactAgent; R4
merges the understand/intent/classifier calls into ONE fast LLM call here. Functions
take (state, rt) — the call state and the AgentRuntime; flows call each other
directly; tools run through rt.tools (the gateway).
"""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import logging
import os  # noqa: F401
import re
from typing import Any  # noqa: F401

from .contract import limits
from .contract.locale import phrase, vocab, vocab_set
from .dialog_utils import asked_recently, last_agent_question
from .trace import trace_note

logger = logging.getLogger(__name__)


def step_perception_options(state: Any, rt: Any):
    """(options, step) for the merged perception call — the SAME routing-key
    meanings walker_flow.classify_confirm_and_route / classify_instruct_and_advance
    build for the standalone classifier, computed once at perception time.
    Returns (None, None) when no asked step awaits an answer (or CLASSIFIER=off,
    the deterministic test mode)."""
    from .resolution import StepKind, get_strategy

    if os.getenv("CLASSIFIER", "on").lower() == "off":
        return None, None
    r = state.resolution.procedure or {}
    strat = get_strategy(r.get("verdict")) if r else None
    step = strat.step(r.get("step", "")) if strat else None
    if step is None or not r.get("asked") or not asked_recently(state, r):
        return None, None
    if step.kind is StepKind.CONFIRM and step.on and step.role != "verify_restored":
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


def ingest_client_evidence(state, rt, user_input: str | None) -> None:
    """Ledger v1: read the caller's utterance into the evidence ledger (called
    from the diagnosis node, so BOTH the driven and the walker path see it).
    A contradicting canonical value flags a conflict -> ONE scripted
    clarification; the next answer for that key settles it (extraction, or a
    bare yes/no polarity read; nothing readable -> the pending value wins so
    the call never loops on the clarify)."""
    s = state
    # Stale-understanding hygiene (2026-08-10): the acknowledgement directive
    # leaked a PREVIOUS turn's "understood" into the ticket dialogue's reply
    # ("Routeris sugedęs, laukiame naujo. Gerai. O kada…"). Every turn starts
    # with a clean read — the early-returns below must not keep the old one.
    state.turn.understanding = None
    state.turn.directives.evidence = None  # persona: fresh narrator directive per turn
    state.turn.directives.findings = None
    state.turn.directives.recap = None
    state.turn.directives.ticket = None
    state.turn.directives.ident = None
    if not user_input or not s.identity.customer_id or s.closing.case_closed or state.ticket.stage:
        return
    from .evidence import CLIENT, extract_client_facts, polarity, set_fact

    # SUPRATIMO pass'as (2026-08-10): the primary sensor — one small-model
    # call reads the reply IN CONTEXT (pending question, fault needs,
    # ledger, history). Any failure -> the deterministic keyword layer
    # below, so the call never stalls on a model hiccup.
    facts: dict[str, str] | None = None
    state.turn.understanding = None
    from . import understand as _und

    if _und.enabled():
        from .evidence import spec_for, summary_lt

        spec = spec_for((s.resolution.procedure or {}).get("verdict"))
        needs = (
            "; ".join(
                f"{k}: {item.get('goal', '')}" for k, item in (spec.get("client") or {}).items()
            )
            if spec
            else ""
        )
        allowed_extra = {
            k: set((item.get("answers") or {}).keys())
            for k, item in ((spec.get("client") or {}) if spec else {}).items()
            if item.get("answers")
        }
        # R4 perception merge: when an asked step awaits its answer, the SAME
        # call classifies the reply against the step's routing keys — the
        # walker consumes the cached result instead of a second LLM round-trip.
        step_options, active_step = step_perception_options(state, rt)
        state.turn.perception_step = None
        u = _und.understand(
            user_input,
            anchor=anchor_text(state, rt),
            needs=needs,
            ledger_summary=summary_lt(s.diagnosis.evidence) if s.diagnosis.evidence else "",
            history_tail=[m for m in s.messages[-5:] if m.get("role") in ("user", "assistant")],
            model=rt.config.model,
            allowed_extra=allowed_extra,
            step_options=step_options,
        )
        if u is not None:
            state.turn.understanding = u
            facts = dict(u["facts"])
            if u.get("step") and active_step is not None:
                state.turn.perception_step = {
                    "step_id": active_step.id,
                    "input": user_input,
                    "obs": u["step"],
                }
            rt.tracer.emit(
                "understand",
                type=u["type"],
                understood=u["understood"],
                confusion=u["confusion"],
                confidence=u["confidence"],
                facts=u["facts"],
                step=u.get("step"),
            )
    # The deterministic keyword layer ALWAYS runs (2026-08-12): it used to be
    # a fallback only, so when the pass answered with EMPTY facts (the
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
                rt.tracer.emit(
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
    pending = state.diagnosis.pending_evidence_key
    # 2026-09-03 (eval S6 flake): the pack's FIRST question can go out from
    # the STEP HINT (the narrator, before the drive's own ask bookkeeping) —
    # then diagnosis.pending_evidence_key is still None and the deterministic answer
    # read was skipped, leaving the fact to the LLM pass's mercy. When no ask
    # is pending, the NEXT MISSING evidence key of the active pack stands in:
    # its conservative `answers` marks still have to hit, so an unrelated
    # utterance commits nothing.
    if pending is None:
        try:
            from .evidence import next_missing as _next_missing
            from .evidence import spec_for as _spec_for0

            _spec0 = _spec_for0((s.resolution.procedure or {}).get("verdict"))
            if _spec0:
                _nm = _next_missing(s.diagnosis.evidence, _spec0, True)
                if _nm:
                    pending = _nm[0]
        except Exception:  # pragma: no cover - best-effort
            pending = None
    pending_entry = s.diagnosis.evidence.get(pending) if pending else None
    # DONE-report without a result (live 2026-08-11): "Mhm, patikrinau."
    # says the check happened, not what it FOUND — yet the pass invented
    # power_cable=atjungtas (echoed from the agent's own explanation) and
    # the hypothesis never confirmed. A pass fact for the pending key on
    # such a turn stands only if the utterance itself corroborates it
    # (the key's markers / the keyword extractor); otherwise it is dropped
    # and the drive asks WHAT was found ("pasitikslinti, o ne kurti").
    state.turn.done_report_key = None
    if state.turn.understanding is not None and pending and pending in facts:
        from .resolution import is_bare_done_report

        if is_bare_done_report(user_input) and (
            pending_entry is None or pending_entry.get("value") == "unknown"
        ):
            from .evidence import read_pending_answer as _rpa
            from .evidence import spec_for as _spec_for

            _spec = _spec_for((s.resolution.procedure or {}).get("verdict"))
            _item = (_spec.get("client") or {}).get(pending) if _spec else None
            corroborated = (
                _rpa(pending, user_input, _item) == facts[pending]
                or extract_client_facts(user_input).get(pending) == facts[pending]
            )
            if not corroborated:
                rt.tracer.emit(
                    "evidence",
                    action="done_report_value_dropped",
                    key=pending,
                    value=facts[pending],
                )
                del facts[pending]
                state.turn.done_report_key = pending
    # SUPPLEMENT, not just fallback (2026-08-10 round 2): the pass returned
    # type=answer with empty facts for "…sakiau, kad RADAU" and the
    # key was given up on. When the pass failed OR answered without the
    # pending key, the deterministic context read fills that ONE key —
    # conservative marks + the conflict machinery guard against misreads.
    # 2026-09-03 (eval S6 flake): the read no longer requires the pass to have
    # TYPED the turn as "answer" — gpt-oss occasionally mislabels a clean
    # answer ("Visuose įrenginiuose" while fail_scope is pending) and the
    # deterministic vocabulary hit was thrown away with it. The pack's
    # `answers` marks are the conservative floor: a hit on the PENDING key
    # is a hit, whatever the LLM called the sentence.
    if (
        pending
        and pending not in facts
        and (pending_entry is None or pending_entry.get("value") == "unknown")
    ):
        from .evidence import read_pending_answer, spec_for

        spec = spec_for((s.resolution.procedure or {}).get("verdict"))
        spec_item = (spec.get("client") or {}).get(pending) if spec else None
        value = read_pending_answer(pending, user_input, spec_item)
        if value is not None:
            facts[pending] = value
    turn = s.dialog.turn_count
    # W1-2 svarbos vartai — the ANSWER to a standing fact-confirm question
    # ("Tik pasitikslinsiu — sakėte, kad rozetė neveikia?"): a yes commits the
    # parked value; anything else drops it (a correction lands as a normal
    # fact from THIS utterance below).
    fca = state.diagnosis.fact_confirm_asked
    if fca and user_input:
        state.diagnosis.fact_confirm_asked = None
        g_key, g_value = fca.key, fca.value
        from .evidence import _fold, _mark_hit

        low_c = _fold(user_input)
        if any(_mark_hit(low_c, m) for m in vocab("fact_confirm_yes")):
            set_fact(s.diagnosis.evidence, g_key, g_value, CLIENT, turn)
            rt.tracer.emit("evidence", action="fact_confirmed", key=g_key, value=g_value)
            facts.pop(g_key, None)
        else:
            rt.tracer.emit("evidence", action="fact_withdrawn", key=g_key, value=g_value)
    # A clarify is out — settle that key first.
    pending_key = state.diagnosis.evidence_conflict_asked_key
    if pending_key:
        value = facts.get(pending_key)
        if value is None and pending_key == "has_computer":
            value = polarity(user_input)
        entry = s.diagnosis.evidence.get(pending_key)
        if value is not None:
            set_fact(s.diagnosis.evidence, pending_key, value, CLIENT, turn)
        elif entry is not None and entry.get("conflict"):
            # Unreadable answer — keep the LATEST stated value, stop asking.
            set_fact(s.diagnosis.evidence, pending_key, entry.get("pending"), CLIENT, turn)
        state.diagnosis.evidence_conflict_asked_key = None
        rt.tracer.emit(
            "evidence",
            action="conflict_resolved",
            key=pending_key,
            value=(s.diagnosis.evidence.get(pending_key) or {}).get("value"),
        )
        facts.pop(pending_key, None)
    if pending and pending in facts:
        state.diagnosis.pending_evidence_key = None  # answered — later "taip" maps to nothing old
    # Contradiction corroboration (2026-08-10): an LLM fact that FLIPS an
    # already-established ledger entry needs the keyword extractor to read
    # the same flip from the utterance — otherwise it is dropped and the
    # established fact stands ("Neturi kompiuterio" hallucinated
    # device_present=nerado against a settled "rado" and forced a phantom
    # clarify). New facts (no entry yet) are accepted as before.
    if state.turn.understanding is not None and facts:
        kw = extract_client_facts(user_input)
        for key in list(facts):
            entry = s.diagnosis.evidence.get(key)
            if (
                entry is not None
                and entry.get("source") == CLIENT
                and not entry.get("conflict")
                and entry.get("value") not in ("unknown",)
                and entry.get("value") != facts[key]
                and kw.get(key) != facts[key]
            ):
                # Second corroboration source (live 2026-08-11): the general
                # extractor needs the TOPIC word in the sentence ("laidas"),
                # but the caller answers "Tai įkištas" without naming it —
                # the pass already says the utterance is ABOUT this key, so
                # the key's OWN answer markers corroborate the flip too.
                from .evidence import read_pending_answer, spec_for

                spec = spec_for((s.resolution.procedure or {}).get("verdict"))
                spec_item = (spec.get("client") or {}).get(key) if spec else None
                if read_pending_answer(key, user_input, spec_item) == facts[key]:
                    continue
                rt.tracer.emit(
                    "evidence", action="uncorroborated_flip_dropped", key=key, value=facts[key]
                )
                del facts[key]
    for key, value in facts.items():
        # W1-2 svarbos vartai (Andrius 2026-08-25, live: STT „rozetė NEVEIKĖ"
        # tyliai užnuodijo žurnalą ir solveris pasiklydo): NAUJAS faktas su
        # pack'o pažymėta `confirm_values:` reikšme, atėjęs NE kaip atsakymas į
        # užduotą klausimą, pirma PATIKSLINAMAS — ne komituojamas. Kai
        # skaitytuvai NESUTARIA dėl šio rakto, jį valdo konflikto mechanika
        # (jos scriptinis klausimas — tas pats pasitikslinimas).
        if key not in kw_disagreements and _story_flip_gate(state, rt, key, str(value), pending):
            continue
        entry = set_fact(s.diagnosis.evidence, key, value, CLIENT, turn)
        if not (entry.get("conflict") and _conflict_to_clarify(state, rt, key, entry)):
            rt.tracer.emit("evidence", action="fact", key=key, value=value)
            _note_fact_meaning(state, rt, key, str(value))
            # B-wave registry: the asked evidence question just got its
            # answer — close it (a different key's fact leaves it open).
            from .dialog_registry import clear as _q_clear

            _q_clear(state, rt, f"evidence:{key}")
    # Reader disagreements land SECOND: on a fresh key this flags the
    # conflict (one scripted clarify settles it); if the flip guard dropped
    # the pass value above, the keyword read simply stands as the fact.
    for key, kw_value in kw_disagreements.items():
        entry = set_fact(s.diagnosis.evidence, key, kw_value, CLIENT, turn)
        if not (entry.get("conflict") and _conflict_to_clarify(state, rt, key, entry)):
            rt.tracer.emit("evidence", action="fact", key=key, value=kw_value)
            _note_fact_meaning(state, rt, key, str(kw_value))


def _note_fact_meaning(state, rt, key: str, value: str) -> None:
    """Turn'o gramatikos 2 dalis (etalonas, 2026-09-03): pack'o `reiskia:`
    laukas deklaruoja, KĄ atsakymas reiškia („dega tik pirma" → „gauna
    maitinimą, bet nemato tinklo") — the narrator's reaction then CARRIES the
    meaning instead of parroting the fact. One-shot note; declared per value
    in the ACTIVE pack's evidence item, so wording is a file edit."""
    from .evidence import gloss_label, spec_for

    spec = spec_for((state.resolution.procedure or {}).get("verdict")) or {}
    item = (spec.get("client") or {}).get(key) or {}
    meaning = (item.get("meaning") or {}).get(value)
    if meaning:
        state.diagnosis.fact_meaning = [
            gloss_label(key),
            value,
            str(meaning),
        ]
        rt.tracer.emit("evidence", action="fact_meaning", key=key, value=value)


def _registry_streets_fold(state, rt) -> list[str]:
    """Folded registry street names (be „g." uodegos) — kito-adreso signalui."""
    try:
        from .evidence import _fold

        names = rt.tools.address_registry().street_names
        return [_fold(str(n).replace(" g.", "")) for n in names]
    except Exception:  # pragma: no cover - best-effort
        return []


def _mentions_other_street(state, rt, text: str | None) -> bool:
    """A-banga P2 (gyva #4, 2026-09-04: „mano ADARAS yra Tilžės gatvė 60" —
    STT sudarkė žodį „adresas" ir korekcijos detektorius tylėjo, o naratorius
    ŽODŽIU „pripažino" keitimą): identifikuoto kliento turn'as, kuriame yra
    KITOS registro gatvės vardas + skaitmuo, yra korekcijos kandidatas —
    nesvarbu, ar nuskambėjo žodis „adresas"."""
    if not text or not state.identity.customer_id:
        return False
    if not any(ch.isdigit() for ch in text):
        return False
    from .evidence import _fold

    low = _fold(text)
    current = _fold(str(state.identity.customer_address or ""))
    return any(
        len(st) >= 4 and st in low and st not in current for st in _registry_streets_fold(state, rt)
    )


def _holder_name_matches(state, rt, caller_name: str) -> bool:
    """Does the caller's stated first name plausibly match the CRM account
    holder's name? Fuzzy by 4-letter prefix (STT garbles endings). True also
    when the holder name is unknown — no basis to challenge."""
    from .evidence import _fold

    holder = state.identity.customer_name or (state.identity.phone_candidate or {}).get("name")
    if not holder:
        return True
    caller_tokens = [t for t in _fold(caller_name).split() if len(t) >= 3]
    holder_tokens = [t for t in _fold(str(holder)).split() if len(t) >= 3]
    if not caller_tokens or not holder_tokens:
        return True
    for c in caller_tokens:
        for h in holder_tokens:
            if c[:4] == h[:4]:
                return True
    return False


def _conflict_to_clarify(state, rt, key: str, entry: dict) -> bool:
    """A conflicting CLIENT re-reading landed on `key`. The scripted clarify
    loop is reserved for keys the ACTIVE pack DECLARES (its own questions —
    e.g. mires 'lights'): those genuinely flip the story, so the caller
    settles them. An UNDECLARED key is side-chatter vocabulary (S6 live
    2026-08-31: 'lights' dega/nedega readings while the pack's question was
    about the internet light BLINKING — the clarify loop hijacked two turns
    and swallowed a clear NO): it resolves SILENTLY to the newest reading,
    history keeps both, no turn is spent. Returns True when the conflict was
    consumed here (flagged for clarify or silently settled)."""
    from .evidence import spec_for

    spec = spec_for((state.resolution.procedure or {}).get("verdict")) or {}
    if key in (spec.get("client") or {}):
        if state.diagnosis.evidence_conflict is None:
            from .evidence import EvidenceConflict

            state.diagnosis.evidence_conflict = EvidenceConflict(
                key=key, old=entry["value"], new=entry["pending"]
            )
            rt.tracer.emit(
                "evidence", action="conflict", key=key, old=entry["value"], new=entry["pending"]
            )
            return True
        return False  # declared, but another clarify already open — old behaviour
    old = entry["value"]
    entry["value"] = entry.pop("pending", old)
    entry["conflict"] = False
    rt.tracer.emit("evidence", action="conflict_silent", key=key, old=old, new=entry["value"])
    return True


def _story_flip_gate(state, rt, key: str, value: str, pending: str | None) -> bool:
    """W1-2 svarbos vartai: should this NEW volunteered fact be parked for a
    confirm question instead of a silent commit? The pack DECLARES which
    values deserve it (`confirm_values:` on the evidence item — file-editable,
    like every behaviour), so only genuinely story-flipping, STT-garble-prone
    values gate (live 2026-08-25: 'rozetė NEVEIKĖ'). True only when ALL hold:
    no gate already open, the key is NOT the one just asked (direct answers
    are trusted; `pending` is snapshotted by the caller — the ingest clears
    the live attribute before the commit loop), and the ledger has no entry
    yet (existing entries belong to the conflict machinery)."""
    s = state
    if state.diagnosis.fact_confirm_pending or state.diagnosis.fact_confirm_asked:
        return False
    if key == pending:
        return False
    if s.diagnosis.evidence.get(key) is not None:
        return False
    from .evidence import spec_for

    spec = spec_for((s.resolution.procedure or {}).get("verdict")) or {}
    item = (spec.get("client") or {}).get(key) or {}
    gated_values = [str(v) for v in (item.get("confirm_values") or [])]
    if value not in gated_values:
        return False
    from .evidence import FactConfirm

    state.diagnosis.fact_confirm_pending = FactConfirm(key=key, value=value)
    rt.tracer.emit("evidence", action="fact_gate", key=key, value=value)
    return True


def ingest_overlay(state, rt, text: str) -> None:
    """Duplex-hearing 2 ŽINGSNIS: deterministic-only ingest for words spoken
    OVER the agent's voice — address slots and evidence vocabularies, through
    the same importance gates as normal turns. No LLM pass, no turn, no
    routing: overlay speech may only FILL facts, never steer."""
    from .identification_flow import prefill_slots_from_text

    if not text:
        return
    s = state
    if not s.identity.customer_id:
        prefill_slots_from_text(state, rt, text)  # address parts said over us
    from .evidence import CLIENT, extract_client_facts, read_pending_answer, set_fact, spec_for

    facts = dict(extract_client_facts(text))
    pending = state.diagnosis.pending_evidence_key
    if pending and pending not in facts:
        spec = spec_for((s.resolution.procedure or {}).get("verdict"))
        item = (spec.get("client") or {}).get(pending) if spec else None
        value = read_pending_answer(str(pending), text, item)
        if value is not None:
            facts[pending] = value
    for key, value in facts.items():
        if _story_flip_gate(state, rt, key, str(value), pending):
            continue
        entry = set_fact(s.diagnosis.evidence, key, value, CLIENT, s.dialog.turn_count)
        if entry.get("conflict") and state.diagnosis.evidence_conflict is None:
            from .evidence import EvidenceConflict

            state.diagnosis.evidence_conflict = EvidenceConflict(
                key=key, old=entry["value"], new=entry["pending"]
            )
            rt.tracer.emit(
                "evidence", action="conflict", key=key, old=entry["value"], new=entry["pending"]
            )
        else:
            rt.tracer.emit("evidence", action="fact_overlay", key=key, value=value)


def anchor_text(state, rt) -> str:
    """The exact place to return to after a deviation — the engine's LAST
    asked question (deterministic), never the LLM's memory of it. Trimmed
    to the QUESTION sentence only: anchoring the whole reply re-read a long
    announce back at the caller (live 2026-08-10)."""
    q = (state.dialog.last_question or "").strip()
    if not q:
        return phrase("system.default_anchor")
    sentences = re.split(r"(?<=[.!?])\s+", q)
    questions = [x for x in sentences if x.strip().endswith("?")]
    return (questions[-1] if questions else sentences[-1]).strip()


def classify_side_topic(state, rt, user_input: str | None) -> bool:
    """Is THIS turn a deviation (a real question with no usable facts)
    during analysis/solving? Sets the per-turn flag + the streak; a
    productive turn resets the streak. Mechanics turns (ticket dialogue,
    conflict clarify, end-confirm) are never deviations — their owners
    handle them."""
    from .evidence import extract_client_facts
    from .resolution import is_real_question

    s = state
    state.turn.side_topic_active = False
    if not user_input or not s.identity.customer_id or s.closing.case_closed or state.ticket.stage:
        return False
    if (
        state.diagnosis.evidence_conflict
        or state.dialog.end_confirm_pending
        or state.dialog.resume_hold_due
    ):
        return False
    # Ticket demand is NEVER a side topic (live 2026-08-13: "Išregistruoti
    # meistrą ir paleisti internetą…" got type=deviation and the side_topic
    # LLM talked the caller OUT of the registration) — the demand machinery
    # in the solving path owns this turn.
    from .resolution import detect_refuse_or_ticket

    if detect_refuse_or_ticket(user_input) == "demand":
        state.dialog.side_topic_streak = 0
        rt.tracer.emit("decision", intent="side_topic", action="ticket_demand_passthrough")
        return False
    # How-to / help requests while an instruction or question stands are ON
    # TASK by definition (live 2026-08-21: "O kaip tai padaryti?" at the
    # bridge instruction got the FAQ "ne mano sritis") — the step explains.
    if is_howto(user_input) and (
        state.diagnosis.pending_evidence_key or (s.resolution.procedure or {}).get("asked")
    ):
        state.dialog.side_topic_streak = 0
        rt.tracer.emit("decision", intent="side_topic", action="on_task_howto")
        return False
    # The understanding pass judged this turn IN CONTEXT — but its type is
    # ONE model field, and side_topic FREEZES the engine, so a single sensor
    # may not decide alone (live 2026-08-10: "Galim dabar patikrinti" got
    # type=question and the answer was answered with a price non-sequitur).
    # CORROBORATION rule: enter only when a deterministic signal agrees —
    # a question word in the text or a FAQ keyword hit.
    u = state.turn.understanding
    if u is not None:
        if u["type"] in ("question", "deviation") and not u["facts"]:
            if extract_client_facts(user_input):
                # The keyword layer read facts the pass missed — an
                # informative interruption, not a deviation (they already
                # landed on the ledger via the always-on supplement).
                state.dialog.side_topic_streak = 0
                return False
            from .faq import match as faq_match

            # A question ABOUT the current instruction is NOT a deviation
            # (live 2026-08-11: "Kur jungti tą kabelį į kompiuterį?" got
            # "tai nėra mano sritis"). FAQ topics stay side topics.
            if not faq_match(user_input) and on_task_question(state, rt, user_input):
                rt.tracer.emit("decision", intent="side_topic", action="on_task")
                state.dialog.side_topic_streak = 0
                return False
            corroborated = is_real_question(user_input) or bool(faq_match(user_input))
            if corroborated:
                state.turn.side_topic_active = True
                state.dialog.side_topic_streak += 1
                rt.tracer.emit(
                    "decision",
                    intent="side_topic",
                    action="enter",
                    streak=state.dialog.side_topic_streak,
                )
                return True
            # The model felt a deviation but the text carries no question —
            # treat as an on-topic turn (the evidence/solver flow continues).
            rt.tracer.emit("decision", intent="side_topic", action="uncorroborated")
            state.dialog.side_topic_streak = 0
            return False
        state.dialog.side_topic_streak = 0
        return False
    if not is_real_question(user_input):
        state.dialog.side_topic_streak = 0
        return False
    if extract_client_facts(user_input):
        # An informative interruption ANSWERS things — not a deviation.
        state.dialog.side_topic_streak = 0
        return False
    from .faq import match as faq_match

    if not faq_match(user_input) and on_task_question(state, rt, user_input):
        rt.tracer.emit("decision", intent="side_topic", action="on_task")
        state.dialog.side_topic_streak = 0
        return False
    state.turn.side_topic_active = True
    state.dialog.side_topic_streak += 1
    rt.tracer.emit(
        "decision",
        intent="side_topic",
        action="enter",
        streak=state.dialog.side_topic_streak,
    )
    return True


def is_howto(text: str | None) -> bool:
    """A 'how do I do that / help me' request — about the standing task."""
    low = f" {(text or '').lower()} "
    return any(m in low for m in vocab("howto_marks"))


def on_task_question(state, rt, user_input: str | None) -> bool:
    """The 'deviation' shares content words with the agent's LAST reply —
    it is a question ABOUT the current instruction ("Kur jungti tą
    kabelį?"), not a side topic; the solver/narrator answers it in place.
    Folded prefix-overlap (≥5 chars) so inflections and dropped diacritics
    still match ("jungti" ~ "prijungsite", "kabelį" ~ "kabelio")."""
    last = last_agent_question(state) or ""
    if not last or not user_input:
        return False
    from .evidence import _fold

    last_f = _fold(last)
    for tok in _fold(user_input).replace("?", " ").replace(",", " ").split():
        tok = tok.strip(".!?")
        if len(tok) >= 5 and tok[:5] in last_f:
            return True
    return False


def pre_turn_guards(state, rt, user_input: str) -> None:
    """Deterministic per-turn guards, run BEFORE the LLM sees the turn.

    (1) Address-offer reply guard: a reply to "Ar skambinate dėl X?" commits the
        account ONLY on a CLEAN yes — a garbled/mixed reply ("Taip, nebija" = STT
        mangle of a denial) vetoes the commit and the agent re-asks (observed live:
        wrong apartment's debt read to the caller).
    (2) Reopen identification: an already-identified caller says they are calling
        about a DIFFERENT address -> drop the identity and ask for the address
        again instead of carrying on about the wrong account."""
    from .identification_flow import prefill_slots_from_text, reopen_identification
    from .ticket_flow import abort_ticket_to_solving, begin_ticket_dialogue, wants_to_keep_solving

    s = state
    state.turn.address_confirm_note = None
    state.turn.address_lookup_note = None  # F2: fresh lookup diagnosis per turn
    state.turn.directives.ident = None  # zone 2: ingest may not run pre-identification
    state.turn.reopen_note = False
    if not user_input:
        return
    # (-2) Ticket-dialogue capture: the previous scripted reply asked for the
    # contact number / hours — read the answer. A question falls through to the
    # LLM (the stage stays and re-asks); a farewell fast-forwards with defaults
    # (the caller is done talking — register with what we have).
    if state.ticket.stage in ("phone", "hours"):
        from .resolution import detect_farewell, detect_ticket_consent

        state.turn.ticket_offscript_question = False
        low_q = (user_input or "").lower()
        from .graph_v2.state import TicketContext

        ctx = state.ticket.context or TicketContext()
        # Cancel-confirm answer (2026-08-11): the previous reply asked
        # "registruoti, ar tikrai nereikia?" — read THIS turn against that
        # question only. Live, a bare "Ne." (a barge-in crumb) cancelled the
        # ticket AND closed the call in one breath; cancelling is a one-way
        # door, so it now takes a confirmed refusal.
        cancel_confirm_out, ctx.cancel_confirm_out = ctx.cancel_confirm_out, False
        if cancel_confirm_out:
            from .resolution import is_bare_negation

            # "Ne, tai pajunkim tą kompiuterį" refuses the TICKET, not the
            # help — back to solving, never back to the phone question.
            if wants_to_keep_solving(state, rt, user_input):
                abort_ticket_to_solving(state, rt)
                return
            if is_bare_negation(user_input) or any(
                m in low_q for m in vocab("ticket_cancel_confirmed")
            ):
                state.ticket.stage = "cancelled"
                from .dialog_registry import clear_owner as _q_clear_owner

                _q_clear_owner(state, rt, "ticket")
                rt.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
                return
            # Anything else resumes the registration — the stage re-asks.
            rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_confirm_resumed")
            return
        # SUPRATIMO pass'as pirmiau (2026-08-10, Andrius): caller phrasing
        # cannot be predicted — "Bet kada galima per pietus iš ryto" IS an
        # P5 (closing wave, live 2026-09-07: "Gerai, aš paskambinsiu vėliau"
        # mid-ticket-dialogue got "ar tiks numeris?"): a first-person "I will
        # call back" IS a callback wish, not a contact answer — the caller
        # does not want the registration now. Same warm close as the
        # cannot-now ladder: no ticket, callback goodbye.
        if any(m in low_q for m in vocab("will_call_back_first_person")):
            state.ticket.stage = None
            state.ticket.context = None
            from .dialog_registry import clear_owner as _q_clear_owner

            _q_clear_owner(state, rt, "ticket")
            s.closing.case_closed = True
            s.closing.closed_reason = "callback"
            state.closing.callback_goodbye_due = True
            rt.tracer.emit("decision", intent="ticket_dialogue", action="callback_close")
            return
        # hours answer, but "galima" sat on the keyword question list and
        # diverted it. The model reads the answer against THIS question;
        # keyword logic below stays as the fallback when it is unavailable.
        und_handled = False
        from . import understand as _und

        if _und.enabled():
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
                        from .barge_in import token_overlap

                        if token_overlap(user_input, s.dialog.last_question or "") >= limits.get(
                            "echo_overlap_threshold"
                        ):
                            s.ticket.contact_phone = s.identity.caller_phone
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
                    if ctx.cancel_confirm_asked:
                        state.ticket.stage = "cancelled"
                        from .dialog_registry import clear_owner as _q_clear_owner

                        _q_clear_owner(state, rt, "ticket")
                        rt.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
                        return
                    ctx.cancel_confirm_asked = True
                    ctx.ask_cancel_confirm = True
                    rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_confirm")
                    return
                if not getattr(ctx, f"{state.ticket.stage}_asked", False):
                    return  # trigger-swallow guard (question not asked yet)
                value = ut.get("value")
                if value:
                    if state.ticket.stage == "phone":
                        digits = re.sub(r"\D", "", value)
                        if value == "same_number":
                            s.ticket.contact_phone = s.identity.caller_phone
                        elif len(digits) >= 6:
                            s.ticket.contact_phone = re.sub(r"[^\d+]", "", value)[:20]
                        else:
                            value = None  # not a usable number — keyword/retry path
                        if value is not None:
                            rt.tracer.emit(
                                "decision", intent="ticket_dialogue", action="phone_captured"
                            )
                            state.ticket.stage = "hours"
                            return
                    else:
                        s.ticket.contact_hours = re.sub(r"[?!]", " ", value).strip(" .,")[:80]
                        rt.tracer.emit(
                            "decision", intent="ticket_dialogue", action="hours_captured"
                        )
                        state.ticket.stage = "done"
                        return
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
            if ctx.cancel_confirm_asked:
                state.ticket.stage = "cancelled"
                from .dialog_registry import clear_owner as _q_clear_owner

                _q_clear_owner(state, rt, "ticket")
                rt.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
                return
            ctx.cancel_confirm_asked = True
            ctx.ask_cancel_confirm = True
            rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_confirm")
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
        clean = user_input.strip().strip(" .?!,")
        if state.ticket.stage == "phone":
            from .resolution import is_backchannel

            digits = re.sub(r"[^\d+]", "", user_input)
            if len(re.sub(r"\D", "", digits)) >= 6:
                s.ticket.contact_phone = digits[:20]
            elif detect_ticket_consent(user_input) == "yes" or is_backchannel(user_input):
                # "tiks šis" / a garbled yes ("T." — STT of "Taip", observed
                # live as tel. on the ticket) — the number they call from.
                s.ticket.contact_phone = s.identity.caller_phone
            elif ctx.phone_retry:
                # Second unclear answer — default to the caller-ID and move on.
                s.ticket.contact_phone = s.identity.caller_phone
            else:
                # Not a number, not a yes — the agent SAYS what it needs and
                # re-asks ONCE ("understand the answer, re-ask when it is not
                # one" — 2026-08-05); garbage never lands on the ticket.
                ctx.phone_retry = True
                ctx.ask_retry = "phone"
                rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_retry")
                return
            rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_captured")
            state.ticket.stage = "hours"
        else:
            # STT sticks "?" mid-string too ("Bet kada? Bet kurio laiko?") —
            # scrub ALL question/exclamation marks before the ticket/announce.
            clean = re.sub(r"\s+", " ", re.sub(r"[?!]", " ", clean)).strip(" .,")
            low_h = clean.lower()
            plausible = bool(re.search(r"\d", low_h)) or any(
                m in low_h for m in vocab("contact_hours_marks")
            )
            if not plausible and not ctx.hours_retry:
                ctx.hours_retry = True
                ctx.ask_retry = "hours"
                rt.tracer.emit("decision", intent="ticket_dialogue", action="hours_retry")
                return
            # Strip trailing STT punctuation — "Bet kada?" landed on the ticket
            # (and in the announce) with the question mark. Second unclear
            # answer defaults to "bet kada" (spoken back in the announce).
            s.ticket.contact_hours = clean[:80] if plausible else "bet kada"
            rt.tracer.emit("decision", intent="ticket_dialogue", action="hours_captured")
            state.ticket.stage = "done"
        return
    # (-1) Farewell mid-process is a signal to CLARIFY, never to close (policy
    # 2026-08-03): "viso gero" heard during identification / troubleshooting /
    # before the news gets ONE confirm question; only the confirmation ends the
    # call — through the outcome (registration when a strategy is active).
    from .resolution import detect_farewell, detect_ticket_consent

    if state.dialog.end_confirm_pending and not s.closing.case_closed:
        state.dialog.end_confirm_pending = False
        if detect_farewell(user_input) or detect_ticket_consent(user_input) == "yes":
            if s.resolution.procedure is not None:
                from .resolution import get_strategy

                strat = get_strategy(s.resolution.procedure.get("verdict"))
                esc = strat.by_role("escalate") if strat else None
                s.resolution.procedure["escalate_reason"] = "caller_ended_call"
                if esc is not None:
                    begin_ticket_dialogue(state, rt, esc)  # contacts, then register+close
                else:
                    s.closing.case_closed = True
                    s.closing.closed_reason = "declined"
            else:
                s.closing.case_closed = True
                s.closing.closed_reason = "declined"
            rt.tracer.emit("decision", intent="end_confirmed", action="close")
        else:
            # Changed their mind — hold the walker THIS turn so a "ne, tęskime"
            # is not misrouted as a step answer; resume next turn.
            state.dialog.resume_hold_due = True
            state.dialog.resync_note = True  # C: re-anchor from the ledger, no improvising
            rt.tracer.emit("decision", intent="end_declined", action="resume")
        return
    # A-2 (live 2026-09-07: "Taip taip dėl KITO adreso" was consumed by the
    # walker, and a later side-topic turn burned the question): the SAFETY
    # question's answer is read HERE — in the deterministic turn head, BEFORE
    # the solver/walker. One-owner principle: the last question asked owns
    # the turn. An unclear answer does NOT burn the question — one re-ask,
    # only then written off as "stay with the current address".
    if state.identity.reopen_confirm_utterance is not None and state.identity.reopen_confirm_asked:
        from .dialog_registry import clear as _q_clear
        from .identification_flow import _looks_like_address
        from .resolution import DETECTORS

        pending = state.identity.reopen_confirm_utterance
        verdict = DETECTORS["yes_no"](user_input)
        if verdict == "yes" or _looks_like_address(user_input):
            state.identity.reopen_confirm_utterance = None
            state.identity.reopen_confirm_asked = False
            _q_clear(state, rt, "reopen_confirm")
            rt.tracer.emit("decision", intent="reopen_confirm", action="confirmed")
            reopen_identification(state, rt, pending)
            # P1 (live 2026-09-07): the pending phrase often already yielded a
            # good address (conf 1.0) — the answer's STT garble ("Tildziai
            # 660-3") must not stomp it; the answer is read only when the
            # address is still missing.
            p = s.identity.profile
            if _looks_like_address(user_input) and not (p.street.value and p.house.value):
                prefill_slots_from_text(state, rt, user_input)  # the answer names it
            # A-2R (live 2026-09-07): the new address was usually ALREADY
            # heard (in the pending phrase "mano adresas Tilžės 60") —
            # identification continues RIGHT NOW: the engine tries resolve;
            # success = new customer, failure leaves the diagnosis note
            # (e.g. "which apartment?"), and the next question belongs to
            # identification, not the old analysis.
            if p.street.value and p.house.value:
                trace_note(
                    rt.tracer,
                    state,
                    "reopen_identity",
                    "new address already heard; engine resolve",
                )
                if engine_resolve_from_slots(state, rt):
                    state.identity.just_identified = True
                    from .identification import ask_caller

                    if ask_caller() and not s.identity.caller_name:
                        state.identity.result_pending = True
            return
        state.dialog.resume_hold_due = True  # the answer belongs to THIS question, not the walker
        if verdict == "no":
            state.identity.reopen_confirm_utterance = None
            state.identity.reopen_confirm_asked = False
            _q_clear(state, rt, "reopen_confirm")
            rt.tracer.emit("decision", intent="reopen_confirm", action="declined")
        elif state.identity.reopen_confirm_asks < limits.get("reopen_confirm_max_asks"):
            state.identity.reopen_reask_due = True  # the scripted layer re-asks the question
            rt.tracer.emit("decision", intent="reopen_confirm", action="reask")
        else:
            state.identity.reopen_confirm_utterance = None
            state.identity.reopen_confirm_asked = False
            _q_clear(state, rt, "reopen_confirm")
            rt.tracer.emit("decision", intent="reopen_confirm", action="declined_unclear")
        return
    # P-D (live 2026-09-08: "nepatogu, nesu namuose" — the walker's refuse
    # guard escalated into a TICKET in the same turn, and the cannot-now
    # ladder never got its chance because ticket_stage was already set): a
    # cannot-now signal registers a SAFETY question in the turn head, so the
    # registry priority guard holds the walker/solver and the scripted ladder
    # asks its clarify this very turn.
    if (
        s.identity.customer_id
        and s.resolution.procedure
        and not state.ticket.stage
        and not s.closing.case_closed
        and state.dialog.cannot_now_state is None
        and not state.dialog.cannot_now_done
    ):
        from .dialog_registry import pack_owns_cannot_now
        from .resolution import detect_cannot_now as _dcn_head

        # P-C: an ability_check/locate_device/homework step's question IS the pack's
        # own cannot-now handling — the shield stands down, the walker routes.
        if _dcn_head(user_input) and not pack_owns_cannot_now(state, rt):
            from .dialog_registry import register as _q_register

            _q_register(state, rt, "safety", "cannot_now")  # priority shield this turn
            rt.tracer.emit("decision", intent="cannot_now", action="shield")
    mid_process = not s.closing.case_closed and (
        not s.identity.customer_id
        or s.resolution.procedure is not None
        or state.identity.result_pending
        or (
            bool(s.diagnosis.verdicts)
            and not (state.diagnosis.news_delivered or s.diagnosis.outage_reported)
        )
    )
    if mid_process and detect_farewell(user_input):
        # F1 (live 2026-09-09: "Gerai, sutariam, viso gero" answering the
        # HOMEWORK consent got "Ar tikrai norite baigti?" twice): on the
        # homework step a farewell IS the consent — the walker routes it
        # to the callback terminal; the end-confirm must not intercept.
        from .dialog_registry import active as _q_act

        _qa = _q_act(state, rt)
        from .faults import role_of

        _qa_role = (
            role_of((s.resolution.procedure or {}).get("verdict"), _qa.key.removeprefix("step:"))
            if _qa is not None and _qa.key.startswith("step:")
            else None
        )
        if _qa_role != "homework":
            state.dialog.end_confirm_pending = True
            rt.tracer.emit("decision", intent="farewell_mid_process", action="confirm_end")
            return
    # (0) Caller-intro capture: the previous reply asked WHO is calling (the
    # identification ladder's last rung) — record the answer verbatim (for the
    # RECORD, 5d rule) + a keyword relation read. The deferred check result goes
    # out in THIS turn's reply (see the RESULT facts directive).
    if s.identity.customer_id and state.identity.result_pending and not s.identity.caller_name:
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
            if tokens and all(t in vocab_set("not_a_name") for t in tokens if t):
                s.identity.caller_name = "nenurodyta"
                s.identity.caller_relation = "unknown"
            else:
                # The bare NAME, not the sentence — "Taip. Mano vardas Andrius.
                # Taip, aš sutartį sudaręs asmuo." went on the ticket verbatim.
                from .identification import extract_caller_name

                s.identity.caller_name = extract_caller_name(user_input) or user_input.strip()[:120]
                s.identity.caller_relation = detect_caller_relation(user_input)
                # Frazynas (etalonas, 2026-09-03): the caller JUST introduced
                # themselves — the next reply opens with a warm acceptance
                # („Malonu, Tomai") instead of a dry „Supratau — X". One-shot.
                state.identity.caller_name_heard = True
            rt.tracer.emit(
                "caller_intro", name=s.identity.caller_name, relation=s.identity.caller_relation
            )
            # B-wave registry: the caller-name question just got its answer.
            from .dialog_registry import clear as _q_clear

            _q_clear(state, rt, "caller_name")
            # №4 (etalonas 2026-09-03): sakosi SAVININKAS, bet vardas nesutampa
            # su DB sutarties vardu — vienas mandagus patikslinimas, DB vardo
            # NEgarsinant (privatumo riba). Fuzzy: STT darkymui („Andrijus" ~
            # „Andrius") užtenka 4 raidžių prefikso sutapimo.
            if s.identity.caller_relation == "holder" and s.identity.caller_name not in (
                None,
                "nenurodyta",
            ):
                if not _holder_name_matches(state, rt, s.identity.caller_name):
                    state.identity.holder_clarify_open = True
                    state.identity.holder_clarify_asked = False
                    rt.tracer.emit("decision", intent="holder_name", action="mismatch_clarify")
        return
    if not s.identity.customer_id:
        q = (last_agent_question(state) or "").lower()
        if any(m in q for m in vocab("address_offer_question")):
            from .resolution import detect_address_confirm

            verdict = detect_address_confirm(user_input)
            if (
                verdict == "yes"
                and s.identity.phone_candidate
                and s.identity.phone_candidate.get("street")
            ):
                # Clean YES to the phone-address OFFER: the ENGINE commits the
                # identity from the candidate parts right now (the model's own
                # resolve-then-narrate path kept relapsing into confirm rounds
                # and skipping the caller question — observed live). The scripted
                # ladder reply asks WHO is calling next.
                c = s.identity.phone_candidate
                p = s.identity.profile
                from .slots import SlotStatus

                p.street.propose(c["street"], 1.0, SlotStatus.HEARD)
                p.house.propose(str(c.get("house") or ""), 1.0, SlotStatus.HEARD)
                if c.get("apartment"):
                    p.apartment.propose(str(c["apartment"]), 1.0, SlotStatus.HEARD)
                if c.get("city"):
                    p.city.propose(str(c["city"]), 1.0, SlotStatus.HEARD)
                if engine_resolve_from_slots(state, rt):
                    trace_note(
                        rt.tracer,
                        state,
                        "address_confirm",
                        "offer confirmed; engine resolve",
                    )
                    state.identity.just_identified = True
                    from .identification import ask_caller

                    if ask_caller() and not s.identity.caller_name:
                        state.identity.result_pending = True
                return
            if verdict == "yes":
                # A-2R-b (2026-09-07): a "taip" to an address confirm WITHOUT
                # a phone candidate (e.g. after reopen, address heard in the
                # slots) — the engine commits from the slots; a block of
                # flats leaves the apartment note.
                p_y = s.identity.profile
                if p_y.street.value and p_y.house.value:
                    trace_note(
                        rt.tracer,
                        state,
                        "address_confirm",
                        "slots confirmed; engine resolve",
                    )
                    if engine_resolve_from_slots(state, rt):
                        state.identity.just_identified = True
                        from .identification import ask_caller

                        if ask_caller() and not s.identity.caller_name:
                            state.identity.result_pending = True
                    return
            if verdict != "yes":
                # Direct accept (arc v3.1): the caller DICTATED a full other address
                # in this very turn (NLU heard street+house clearly) — the ENGINE
                # resolves + diagnoses it RIGHT NOW (asking the model to call the
                # tool proved unreliable: it narrated "patikrinsiu" without acting,
                # then relapsed into a redundant confirm round). The reply then
                # echoes the address and continues per the identification ladder.
                p = state.identity.profile
                # Street/city inherit from the OFFERED address when the correction
                # names only the house/flat ("Ne, dėl 60 buto 3" — same street;
                # observed live: the engine path did not fire without this).
                if not p.street.value and p.house.value and s.identity.phone_candidate:
                    from .slots import SlotStatus

                    if s.identity.phone_candidate.get("street"):
                        p.street.propose(
                            s.identity.phone_candidate["street"], 0.9, SlotStatus.HEARD
                        )
                    if not p.city.value and s.identity.phone_candidate.get("city"):
                        p.city.propose(
                            str(s.identity.phone_candidate["city"]), 0.9, SlotStatus.HEARD
                        )
                if p.street.value and p.house.value:
                    trace_note(
                        rt.tracer,
                        state,
                        "address_confirm",
                        "offer corrected with a full dictated address; engine resolve",
                    )
                    if engine_resolve_from_slots(state, rt):
                        state.identity.just_identified = True
                        from .identification import ask_caller

                        if ask_caller() and not s.identity.caller_name:
                            state.identity.result_pending = True
                        state.turn.address_confirm_note = (
                            "- IDENTIFIKUOTA (variklis jau atliko patikrą): "
                            f"adresas {s.identity.customer_address}. Atsakymo pradžioje "
                            "pakartok adresą („Supratau — <adresas>.“) ir tęsk "
                            "pagal žemiau esančią kryptį."
                        )
                    else:
                        state.turn.address_confirm_note = (
                            "- KLIENTAS PASAKĖ KITĄ ADRESĄ, bet jo patikrinti "
                            "nepavyko (žr. HEARD ADDRESS) — patikslink trūkstamą "
                            "dalį arba paprašyk pakartoti."
                        )
                else:
                    state.turn.address_confirm_note = (
                        "- ADRESAS NEPATVIRTINTAS: kliento atsakymas AIŠKIAI "
                        "nepatvirtino pasiūlyto adreso (girdisi neigimas ar "
                        "neaiškumas). NEkviesk resolve_address su pasiūlytu adresu. "
                        "Jei klientas įvardijo KITĄ adresą (žr. HEARD ADDRESS) — "
                        "naudok TĄ. Kitu atveju mandagiai perklausk: „Atsiprašau, "
                        "nesupratau — dėl kokio adreso skambinate?“"
                    )
                    trace_note(
                        rt.tracer,
                        state,
                        "address_confirm",
                        f"offer not confirmed (verdict={verdict}); veto commit",
                        level="warn",
                    )
        else:
            # arc v3.2 (eval I2 2026-08-27, po prompt-prefix pertvarkos): the
            # caller dictated or CORRECTED the address ("Ai, atsiprašau — 29
            # namas") and the model either answered "Radau…" for a NONEXISTENT
            # house without calling the tool, or relapsed into a confirm round.
            # Same rule as the offer path: clearly heard street+house AND a
            # digit in THIS utterance (an address part was just said) -> the
            # ENGINE resolves right now; a failed resolve leaves the per-level
            # diagnosis note (namo 39 nerandu, yra 29/31) for the narrator.
            import re as _re

            p = s.identity.profile
            if (
                s.intake.anamnesis_asked  # the address ladder is live (not the opener)
                and p.street.value
                and p.house.value
                and _re.search(r"\d", user_input or "")
            ):
                trace_note(rt.tracer, state, "address_ask", "dictated address; engine resolve")
                if engine_resolve_from_slots(state, rt):
                    state.identity.just_identified = True
                    from .identification import ask_caller

                    if ask_caller() and not s.identity.caller_name:
                        state.identity.result_pending = True
                    state.turn.address_confirm_note = (
                        "- IDENTIFIKUOTA (variklis jau atliko patikrą): "
                        f"adresas {s.identity.customer_address}. Atsakymo pradžioje "
                        "pakartok adresą („Supratau — <adresas>.“) ir tęsk "
                        "pagal žemiau esančią kryptį."
                    )
    elif not s.closing.case_closed:
        from .resolution import detect_address_correction

        if (
            detect_address_correction(user_input) or _mentions_other_street(state, rt, user_input)
        ) and not state.identity.reopen_confirm_utterance:
            # Etalonas №3 (2026-09-03): PIRMA patvirtinimo klausimas, tik tada
            # identifikacija atsidaro iš naujo — STT darkymas nebemeta pokalbio
            # ant kito adreso be kliento „taip".
            state.identity.reopen_confirm_utterance = user_input
            state.identity.reopen_confirm_asked = False
            rt.tracer.emit("decision", intent="reopen_confirm", action="pending")


def engine_resolve_from_slots(state, rt) -> bool:
    """Deterministic identification commit from clearly-heard slots: the ENGINE
    calls resolve_address (+ the silent diagnose) itself — no LLM tool-call
    hesitancy, no confirm-round relapse. True when a customer committed."""
    from .walker_flow import ensure_diagnosed

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
    # B-wave registry: the identification question (address/code) got its
    # answer — a contract committed; the next question (the name) is
    # registered by its own owner.
    from .dialog_registry import clear_owner as _q_clear_owner

    _q_clear_owner(state, rt, "ident")
    ensure_diagnosed(state, rt)
    return True


def raise_clarity(state: Any, user_input: str | None) -> None:
    """Once the caller says they do not follow the wording ("kas tas WAN?"),
    stay in plain language for the rest of the call. One-way: a caller who was
    lost once should not be dropped back into jargon two steps later."""
    from .resolution import detect_confusion

    if state.dialog.clarity_level == "standard" and detect_confusion(user_input):
        state.dialog.clarity_level = "basic"

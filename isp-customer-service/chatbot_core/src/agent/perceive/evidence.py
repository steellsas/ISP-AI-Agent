"""Evidence ingest — the caller's words onto the evidence ledger: the understanding
pass, the keyword readers, the pending-question read, and the importance gates
(conflict, story flip) that park a doubtful fact for a confirm question."""

from __future__ import annotations

import os
from typing import Any

from ..contract.locale import vocab
from ..dialog_utils import anchor_text, asked_recently


def step_perception_options(state: Any, rt: Any):
    """(options, step) for the merged perception call — the SAME routing-key
    meanings procedure.classify_confirm_and_route / classify_instruct_and_advance
    build for the standalone classifier, computed once at perception time.
    Returns (None, None) when no asked step awaits an answer (or CLASSIFIER=off,
    the deterministic test mode)."""
    from ..resolution import StepKind, get_strategy

    if os.getenv("CLASSIFIER", "on").lower() == "off":
        return None, None
    r = state.resolution.procedure or {}
    strat = get_strategy(r.get("verdict")) if r else None
    step = strat.step(r.get("step", "")) if strat else None
    if step is None or not r.get("asked") or not asked_recently(state, r):
        return None, None
    if step.kind is StepKind.CONFIRM and step.on and step.role != "verify_restored":
        from ..detectors import glosses as detector_glosses
        from ..faults import step_options as declared_options

        declared = declared_options(r.get("verdict"), step.id)
        glosses = detector_glosses(step.detector or "yes_no")
        options: dict[str, str] = {}
        for raw in step.on:
            key = str(getattr(raw, "value", raw))
            options[key] = (declared or {}).get(key) or glosses.get(key, key)
        return options, step
    if step.kind is StepKind.INSTRUCT:
        from ..detectors import glosses as detector_glosses

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
    from ..evidence import CLIENT, extract_client_facts, polarity, set_fact

    # Understanding pass (2026-08-10): the primary sensor — one small-model
    # call reads the reply IN CONTEXT (pending question, fault needs,
    # ledger, history). Any failure -> the deterministic keyword layer
    # below, so the call never stalls on a model hiccup.
    facts: dict[str, str] | None = None
    state.turn.understanding = None
    from . import understand as _und

    if _und.enabled():
        from ..evidence import spec_for, summary_lt

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
            from ..evidence import next_missing as _next_missing
            from ..evidence import spec_for as _spec_for0

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
    # and the drive asks WHAT was found ("clarify, don't invent").
    state.turn.done_report_key = None
    if state.turn.understanding is not None and pending and pending in facts:
        from .detectors import is_bare_done_report

        if is_bare_done_report(user_input) and (
            pending_entry is None or pending_entry.get("value") == "unknown"
        ):
            from ..evidence import read_pending_answer as _rpa
            from ..evidence import spec_for as _spec_for

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
        from ..evidence import read_pending_answer, spec_for

        spec = spec_for((s.resolution.procedure or {}).get("verdict"))
        spec_item = (spec.get("client") or {}).get(pending) if spec else None
        value = read_pending_answer(pending, user_input, spec_item)
        if value is not None:
            facts[pending] = value
    turn = s.dialog.turn_count
    # W1-2 importance gate — the ANSWER to a standing fact-confirm question
    # ("Tik pasitikslinsiu — sakėte, kad rozetė neveikia?"): a yes commits the
    # parked value; anything else drops it (a correction lands as a normal
    # fact from THIS utterance below).
    from ..decide import hypothesis

    fca = hypothesis.answered(state, rt, "flip") if user_input else None
    if fca:
        g_key, g_value = fca.fact_key, fca.now_value
        from ..evidence import _fold, _mark_hit

        low_c = _fold(user_input)
        if any(_mark_hit(low_c, m) for m in vocab("fact_confirm_yes")):
            set_fact(s.diagnosis.evidence, g_key, g_value, CLIENT, turn)
            rt.tracer.emit("evidence", action="fact_confirmed", key=g_key, value=g_value)
            facts.pop(g_key, None)
        else:
            rt.tracer.emit("evidence", action="fact_withdrawn", key=g_key, value=g_value)
    # A clarify is out — settle that key first.
    conflict = hypothesis.answered(state, rt, "conflict")
    pending_key = conflict.fact_key if conflict else None
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
                from ..evidence import read_pending_answer, spec_for

                spec = spec_for((s.resolution.procedure or {}).get("verdict"))
                spec_item = (spec.get("client") or {}).get(key) if spec else None
                if read_pending_answer(key, user_input, spec_item) == facts[key]:
                    continue
                rt.tracer.emit(
                    "evidence", action="uncorroborated_flip_dropped", key=key, value=facts[key]
                )
                del facts[key]
    for key, value in facts.items():
        # W1-2 importance gate (Andrius 2026-08-25, live: STT „rozetė NEVEIKĖ"
        # silently poisoned the journal and the solver got lost): a NEW fact with
        # a value the pack marks in `confirm_values:`, arriving NOT as the answer
        # to an asked question, is first CLARIFIED — not committed. When the
        # readers DISAGREE on this key, the conflict machinery owns it
        # (its scripted question is the same clarification).
        if key not in kw_disagreements and _story_flip_gate(state, rt, key, str(value), pending):
            continue
        entry = set_fact(s.diagnosis.evidence, key, value, CLIENT, turn)
        if not (entry.get("conflict") and _conflict_to_clarify(state, rt, key, entry)):
            rt.tracer.emit("evidence", action="fact", key=key, value=value)
            _note_fact_meaning(state, rt, key, str(value))
            # B-wave registry: the asked evidence question just got its
            # answer — close it (a different key's fact leaves it open).
            from ..decide.question import clear as _q_clear

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
    """Turn grammar part 2 (reference dialogue, 2026-09-03): the pack's `reiskia:`
    field declares WHAT the answer means („dega tik pirma" → „gauna
    maitinimą, bet nemato tinklo") — the narrator's reaction then CARRIES the
    meaning instead of parroting the fact. One-shot note; declared per value
    in the ACTIVE pack's evidence item, so wording is a file edit."""
    from ..evidence import gloss_label, spec_for

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
    from ..evidence import spec_for

    spec = spec_for((state.resolution.procedure or {}).get("verdict")) or {}
    if key in (spec.get("client") or {}):
        from ..decide import hypothesis

        if hypothesis.doubt(state, rt, "conflict", key, entry["value"], entry["pending"]):
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
    """W1-2 importance gate: should this NEW volunteered fact be parked for a
    confirm question instead of a silent commit? The pack DECLARES which
    values deserve it (`confirm_values:` on the evidence item — file-editable,
    like every behaviour), so only genuinely story-flipping, STT-garble-prone
    values gate (live 2026-08-25: 'rozetė NEVEIKĖ'). True only when ALL hold:
    no gate already open, the key is NOT the one just asked (direct answers
    are trusted; `pending` is snapshotted by the caller — the ingest clears
    the live attribute before the commit loop), and the ledger has no entry
    yet (existing entries belong to the conflict machinery)."""
    s = state
    if state.diagnosis.contradiction is not None:
        return False
    if key == pending:
        return False
    if s.diagnosis.evidence.get(key) is not None:
        return False
    from ..evidence import spec_for

    spec = spec_for((s.resolution.procedure or {}).get("verdict")) or {}
    item = (spec.get("client") or {}).get(key) or {}
    gated_values = [str(v) for v in (item.get("confirm_values") or [])]
    if value not in gated_values:
        return False
    from ..decide import hypothesis

    hypothesis.doubt(state, rt, "flip", key, None, value)
    rt.tracer.emit("evidence", action="fact_gate", key=key, value=value)
    return True


def ingest_overlay(state, rt, text: str) -> None:
    """Duplex-hearing STEP 2: deterministic-only ingest for words spoken
    OVER the agent's voice — address slots and evidence vocabularies, through
    the same importance gates as normal turns. No LLM pass, no turn, no
    routing: overlay speech may only FILL facts, never steer."""
    from .slots import prefill_slots_from_text

    if not text:
        return
    s = state
    if not s.identity.customer_id:
        prefill_slots_from_text(state, rt, text)  # address parts said over us
    from ..evidence import CLIENT, extract_client_facts, read_pending_answer, set_fact, spec_for

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
        from ..decide import hypothesis

        if entry.get("conflict") and hypothesis.doubt(
            state, rt, "conflict", key, entry["value"], entry["pending"]
        ):
            rt.tracer.emit(
                "evidence", action="conflict", key=key, old=entry["value"], new=entry["pending"]
            )
        else:
            rt.tracer.emit("evidence", action="fact_overlay", key=key, value=value)

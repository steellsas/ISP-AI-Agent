"""What one caller turn was — ONE reading, in one shape (wave 2a).

The same utterance used to be read by three or four paths (the LLM pass, the keyword
extractor, the pending-key reader, the step classifier), each with its own shape, and
~8 arbitration guards decided whose answer counted. This module gives the reading a
single shape and two cheap rules that replace most of that arbitration:

**The fast path.** A closed answer to a standing question ("taip", "ne", "dega",
"palaukit") is read deterministically — no LLM call, no latency. Most voice turns are
exactly that.

**Quote grounding.** A fact the LLM reports must come with the caller's own words, and
the code checks that those words are really in the utterance. A hallucinated fact has no
quote to show (live 2026-08-10: five facts the caller never said poisoned the ledger).

The engine still decides what a reading MEANS — this module only reads.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# How the reading was taken.
Source = Literal["fast_path", "llm", "keywords"]


class Fact(BaseModel):
    """One canonical fact value plus the caller's words that support it."""

    value: str
    quote: str | None = None
    grounded: bool = True  # False = the quote could not be found in the utterance


class Perception(BaseModel):
    """One turn, read once."""

    source: Source = "keywords"
    turn_type: str = "answer"  # answer | question | deviation | confusion | contradiction
    facts: dict[str, Fact] = Field(default_factory=dict)
    # The answer to the step whose question is out: {label, is_answer, confidence, …}.
    step: dict[str, Any] | None = None
    understood: str = ""  # half-sentence the narrator may reflect back
    confusion: str = ""
    confidence: float = 0.5
    # What was read — a reading belongs to ONE utterance.
    utterance: str | None = None
    # The contact dialogue's answer, when one was asked: {value, type}.
    ticket: dict[str, Any] | None = None
    # What the caller's problem sounds like, when the call has none yet: {label, confidence}.
    problem: dict[str, Any] | None = None
    # Kurio žinių dokumento agentui reikia ŠIAM klausimui, jei jis ko nors klausė. Sprendimas yra
    # AGENTO: jis renkasi iš savo žinių žemėlapio, o ne ieško kliento sakiniu (išmatuota: 69 %
    # prieš 57 %). `None` reiškia „nieko nereikia" arba „ne mūsų sritis".
    knowledge: str | None = None

    def values(self) -> dict[str, str]:
        """The facts as the ledger takes them (key -> canonical value)."""
        return {key: fact.value for key, fact in self.facts.items()}

    def as_understanding(self) -> dict[str, Any]:
        """The shape the rest of the engine already reads (`turn.understanding`)."""
        return {
            "facts": self.values(),
            "type": self.turn_type,
            "understood": self.understood,
            "confusion": self.confusion,
            "confidence": self.confidence,
            "step": self.step,
            "knowledge": self.knowledge,
        }


def fast_read(
    state: Any,
    utterance: str,
    options: dict[str, str] | None,
    step: Any = None,
) -> Perception | None:
    """A closed answer to a standing question, read without the model. None = this turn
    needs the full reading.

    Only SHORT utterances qualify (`short_utterance_max_words`): the moment a caller adds
    anything of their own, the meaning is no longer a lookup.
    """
    from ..contract import limits
    from .detectors import detect_yes_no, is_backchannel, is_real_question

    text = (utterance or "").strip()
    if not text or is_real_question(text):
        return None
    if len(text.split()) > limits.get("short_utterance_max_words"):
        return None
    if is_backchannel(text):
        # "mhm", "gerai" — heard, nothing claimed.
        return Perception(source="fast_path", turn_type="answer", confidence=1.0)
    pending = _pending_fact(state, text)
    if pending is not None:
        key, value = pending
        step = _step_from(options, detect_yes_no(text)) if options else None
        return Perception(
            source="fast_path",
            turn_type="answer",
            facts={key: Fact(value=value, quote=text)},
            step=step,
            # The narrator reflects the answer back ("Gerai — lemputės nedega"): on this
            # path the half-sentence comes from the pack's own wording, not the model.
            understood=_said(key, value),
            confidence=1.0,
        )
    return _closed_answer(state, text, options, step)


def _closed_answer(
    state: Any, text: str, options: dict[str, str] | None, step: Any
) -> Perception | None:
    """Atsakymas į UŽDARĄ klausimą, perskaitytas žingsnio paties skaitytuvu (L1, 2026-10-05).

    Variklyje žodynas jau yra PIRMAS (`case_rule`: *„Žodynas lieka pirmas — jis nemokamas ir
    tikslus"*), o modelis — antra eilė. Vadinasi, kai šio žingsnio skaitytuvas sakinį perskaito,
    modelio kvietimas tam ėjimui nieko neprideda, tik kainuoja ~1,6 s. Išmatuota 2026-10-05:
    `fast_path` suveikdavo 2 ėjimuose iš 53.

    Modelis paliekamas visur, kur jis tikrai reikalingas: klausimui (`is_real_question` —
    aukščiau), nesupratimui, kontaktų dialogui, nežinomai problemai ir ilgam sakiniui, kuriame
    be atsakymo gali būti pasakyta dar kažkas.
    """
    from ..contract import limits
    from ..modules import label_from
    from .detectors import INTENT_DONE, INTENT_IN_PROGRESS, detect_confusion, detect_turn_intent

    if not options or getattr(step, "module", None) is None:
        # Tik v2 Case kelias: ten klausimas yra modulio, jo skaitytuvas deklaruotas kortelėje,
        # ir variklis tuo skaitytuvu eina pirmas. v1 vedlio žingsnį kaip anksčiau skaito modelis.
        return None
    if state.ticket.stage in ("phone", "hours") or not state.intake.problem_type:
        return None  # kontaktų dialogą ir problemos atpažinimą skaito modelis
    if detect_confusion(text):
        return None  # „nesupratau" — ne atsakymas, o darbas narratoriui
    if len(text.split()) > limits.get("fast_read_max_words"):
        return None
    if set(options) == {"done", "waiting"}:
        # Nurodymo žingsnis: „padariau" ir „einu" žodynas skaito pats (INTENT_*), ir variklis
        # būtent tais signalais ir eina (`_reported_done`, `_model_says_still_working`).
        intent = detect_turn_intent(text)
        if intent == INTENT_DONE:
            label, is_answer = "done", True
        elif intent == INTENT_IN_PROGRESS:
            label, is_answer = "waiting", False
        else:
            return None
    else:
        label = label_from(getattr(step, "detector", None), text)
        if label is None or label not in options:
            return None
        is_answer = True
    return Perception(
        source="fast_path",
        turn_type="answer",
        step={
            "label": label,
            "is_answer": is_answer,
            "internally_inconsistent": False,
            "confidence": 1.0,
        },
        # Patvirtinimo pusė sakinio („lemputės nedega") iki šiol atėjo iš modelio; be jos
        # atsakymas nustotų atliepti tai, ką klientas ką tik pasakė. Ji statoma iš pakuotės
        # pačios reikšmių, lygiai kaip kitame greitajame kelyje.
        understood=_said_from_step(state, label) or "",
        confidence=1.0,
    )


def _said_from_step(state: Any, label: str) -> str | None:
    """Ką ši etiketė reiškia pakuotės žodžiais — arba None, jei nieko."""
    from .. import modules
    from ..contract import cards as catalog
    from ..equipment import for_signals

    case = getattr(state, "case", None)
    if case is None or not case.fault or case.solution is None:
        return None
    card = catalog.card(case.fault)
    if card is None:
        return None
    steps = card.solution[case.solution].steps
    if not 0 <= case.step < len(steps):
        return None
    signals = ((state.diagnosis.verdicts or {}).get("network") or {}).get("signals") or {}
    call = steps[case.step]
    # Patvirtinam tai, kas yra KLIENTO („lemputės nedega"), ne tai, ką iš to supranta linija
    # (`wan_link=down`): be šito ėjo „Supratau — wan_link down".
    answer = modules.client_fact(call, state.dialog.last_heard) or modules.answer_from_label(
        call, label, device=for_signals(signals)
    )
    if not answer:
        return None
    key, value = answer
    from ..evidence import gloss_label, gloss_value

    if gloss_label(key) == key or gloss_value(value, key) == value:
        return None  # pakuotė šio fakto žmonių kalba neįvardija — tada geriau nieko
    return _said(key, value)


def _said(key: str, value: str) -> str:
    """How this answer reads back, from the pack's own labels ("routerio lemputės
    nedega") — the narrator reflects it, so it must read like speech."""
    from ..evidence import gloss_label, gloss_value

    return f"{gloss_label(key)} {gloss_value(value, key)}".strip()


def _pending_fact(state: Any, text: str) -> tuple[str, str] | None:
    """The evidence question that is out, answered by this short utterance."""
    from .evidence import unasked_pending_cleared

    key = unasked_pending_cleared(state)
    if not key:
        return None
    from ..evidence import read_pending_answer, spec_for

    spec = spec_for((state.resolution.procedure or {}).get("verdict")) or {}
    item = (spec.get("client") or {}).get(key)
    value = read_pending_answer(str(key), text, item)
    return (str(key), value) if value is not None else None


def _step_from(options: dict[str, str], outcome: Any) -> dict[str, Any] | None:
    """A yes/no the asked step branches on (only when the step offers that branch)."""
    if outcome is None:
        return None
    label = str(getattr(outcome, "value", outcome)).lower()
    if label not in options:
        return None
    return {"label": label, "is_answer": True, "internally_inconsistent": False, "confidence": 1.0}


def ground(perception: Perception, utterance: str) -> Perception:
    """Drop every fact the caller's own words do not support.

    Kiekvienas faktas turi turėti CITATĄ, ir ta citata turi būti tame sakinyje. Iki 7d bangos
    faktas BE citatos buvo praleidžiamas „variklio koroboravimo taisyklėms" — ir būtent taip
    prasilįsdavo haliucinacijos: gyvai 2026-10-02 į „Džiugiu, Girino." modelis grąžino
    `has_computer=no` su paaiškinimu „klientas džiaugiasi, bet neturi kompiuterio". Melas su
    citata buvo atmetamas, be citatos — ne.

    Saugioji pusė yra ta pati, kurios prašė Andrius: geriau paklausti, nei spėti. Uždavinio
    atsakymą ir toliau nešioja atskiras, patikimas kanalas (`perception.step`).
    """
    from ..evidence import _fold

    said = _fold(utterance or "")
    kept: dict[str, Fact] = {}
    for key, fact in perception.facts.items():
        quote = (fact.quote or "").strip()
        if not quote:
            kept[key] = fact.model_copy(update={"grounded": False})
            continue
        if _fold(quote) in said:
            kept[key] = fact
        else:
            kept[key] = fact.model_copy(update={"grounded": False})
    return perception.model_copy(update={"facts": kept})


def read_turn(state: Any, rt: Any, utterance: str | None) -> Perception | None:
    """Read this turn ONCE and put the reading on the turn scratch.

    One call covers everything the turn needs read: the evidence facts, the asked
    step's answer, the contact dialogue's answer and — while the call's problem is
    still unknown — what the caller's problem sounds like. Before wave 2a those were
    three separate model calls in three different places.
    """
    from . import understand as _und
    from .evidence import step_perception_options

    state.turn.perception = None
    state.turn.understanding = None
    state.turn.perception_step = None
    if not utterance or not utterance.strip():
        return None
    options, active_step = step_perception_options(state, rt)
    quick = fast_read(state, utterance, options, active_step)
    if quick is not None:
        return _record(state, rt, quick, active_step, utterance)
    if not _und.enabled() or not _needs_reading(state):
        return None
    data = _und.understand(
        utterance,
        anchor=_anchor(state, rt),
        needs=_needs(state),
        ledger_summary=_ledger(state),
        history_tail=[m for m in state.messages[-5:] if m.get("role") in ("user", "assistant")],
        model=rt.config.model,
        allowed_extra=_allowed_extra(state),
        step_options=options,
        ticket_stage=state.ticket.stage if state.ticket.stage in ("phone", "hours") else None,
        problem_options=_problem_options(state),
    )
    if data is None:
        return None
    read = ground(
        Perception(
            source="llm",
            turn_type=data["type"],
            facts={
                key: Fact(value=value, quote=(data.get("quotes") or {}).get(key))
                for key, value in data["facts"].items()
            },
            step=data.get("step"),
            understood=data["understood"],
            confusion=data["confusion"],
            confidence=data["confidence"],
            ticket=data.get("ticket"),
            problem=data.get("problem"),
            knowledge=data.get("knowledge"),
        ),
        utterance,
    )
    # A fact whose quote is NOT in what the caller said is dropped: a hallucination has
    # no words to show for itself.
    for key, fact in read.facts.items():
        if not fact.grounded:
            rt.tracer.emit(
                "evidence", action="fact_ungrounded", key=key, value=fact.value, quote=fact.quote
            )
    read = read.model_copy(update={"facts": {k: f for k, f in read.facts.items() if f.grounded}})
    return _record(state, rt, read, active_step, utterance)


def _needs_reading(state: Any) -> bool:
    """Does this turn need the model at all?

    Only when something is waiting to be read: a fault is being diagnosed, the contact
    dialogue asked something, or the call still has no problem. An address turn with the
    problem already known is read by the deterministic slot layer (wave 2a: without this
    the reading ran on EVERY turn — 212 calls for 214 turns in the eval).
    """
    if state.ticket.stage in ("phone", "hours"):
        return True
    if not state.intake.problem_type:
        return True
    return bool(state.identity.customer_id) and not state.closing.case_closed


def _record(state: Any, rt: Any, read: Perception, active_step: Any, utterance: str) -> Perception:
    read = read.model_copy(update={"utterance": utterance})
    state.turn.perception = read.model_dump(mode="json")
    # The contact dialogue speaks its own scripted lines — a narrator acknowledgement
    # of what was "understood" there once leaked a diagnosis half-sentence into it.
    if not state.ticket.stage:
        state.turn.understanding = read.as_understanding()
    if read.step and active_step is not None:
        state.turn.perception_step = {
            "step_id": active_step.id,
            "input": utterance,
            "obs": read.step,
        }
    rt.tracer.emit(
        "perception",
        source=read.source,
        turn_type=read.turn_type,
        understood=read.understood,
        confusion=read.confusion,
        confidence=read.confidence,
        facts=read.values(),
        step=read.step,
        ticket=read.ticket,
        problem=read.problem,
    )
    return read


def _anchor(state: Any, rt: Any) -> str:
    from ..dialog_utils import anchor_text

    return anchor_text(state, rt)


def _spec(state: Any) -> dict[str, Any]:
    """The client facts in play, from the CARDS (wave 3): the fault the Case settled on, or
    every open one while it has not."""
    from ..evidence import spec_for

    return spec_for(state.case.fault) or {}


def _needs(state: Any) -> str:
    """What the active fault still needs to know (empty outside a fault)."""
    client = _spec(state).get("client") or {}
    return "; ".join(f"{k}: {item.get('goal', '')}" for k, item in client.items())


def _ledger(state: Any) -> str:
    from ..evidence import summary_lt

    return summary_lt(state.diagnosis.evidence) if state.diagnosis.evidence else ""


def _allowed_extra(state: Any) -> dict[str, set[str]]:
    """Fact values the ACTIVE pack declares beyond the built-in ones."""
    client = _spec(state).get("client") or {}
    return {
        key: set((item.get("answers") or {}).keys())
        for key, item in client.items()
        if item.get("answers")
    }


def _problem_options(state: Any) -> dict[str, str] | None:
    """The problem catalog, while the call has no problem yet."""
    if state.intake.problem_type:
        return None
    from ..intents import problem_catalog_options

    return problem_catalog_options() or None

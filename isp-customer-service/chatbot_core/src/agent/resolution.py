"""Resolution strategy registry + step sequencer (pure, unit-testable).

Each diagnosis VERDICT maps to a Strategy = an ordered list of Steps. The engine
walks the steps DETERMINISTICALLY — the model cannot skip: per turn it exposes
only the current step's tools + content, and the engine advances afterwards.

Step kinds:
- CONFIRM  — ask the caller a yes/no and WAIT (client-facing).
- ACTION   — backend tool(s) the engine runs SILENTLY, then verifies (no wait).
- INSTRUCT — guide the caller through one step and WAIT (client does something).
- VERIFY   — re-read telemetry; decide fixed -> resolve, or not -> retry/escalate.
             A fresh verdict here can PIVOT the whole flow to another strategy.
- ESCALATE — register the fault (ticket) and close.

This module is PURE (no LLM, no DB, no I/O) so the sequencing is unit-testable;
the engine (react_agent) wires the tool calls, telemetry and prompts around it.
Adding a fault = one Strategy here + one RAG doc — the skeleton does not change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .contract import limits
from .contract.locale import vocab, vocab_re, vocab_set


class StepKind(str, Enum):
    CONFIRM = "confirm"
    ACTION = "action"
    INSTRUCT = "instruct"
    VERIFY = "verify"
    ESCALATE = "escalate"


class Outcome(str, Enum):
    """What the last turn produced, fed back to advance the sequence."""

    YES = "yes"  # caller confirmed / step succeeded
    NO = "no"  # caller declined / denied
    FIXED = "fixed"  # verify: telemetry shows the line restored
    NOT_FIXED = "not_fixed"  # verify: fault persists (same verdict)
    PIVOT = "pivot"  # verify: telemetry shows a DIFFERENT verdict


@dataclass(frozen=True)
class Step:
    """One node in a strategy. `tools` are exposed to the LLM this turn; for an
    ACTION step `tool_actions` are what the ENGINE runs silently (backend + verify).
    `rag_section` names the "### Žingsnis N" chunk to inject (RAG chunking, step 2).
    """

    id: str
    kind: StepKind
    # What the step DOES in the procedure (`role:` in the pack) — the engine acts
    # on roles, never on step ids (D-18).
    role: str = ""
    hint: str = ""  # LT guidance shown to the LLM for THIS step only
    # The step's GOAL in the caller's terms (`goal:` in the pack) — the
    # narrator states it, evaluates the caller's move against it ("Gerai —
    # radote" / "Ne, ne šis kabelis") and knows what "done" means here.
    goal: str = ""
    tools: frozenset[str] = frozenset()  # tools the LLM may call this step
    tool_actions: tuple[str, ...] = ()  # backend tools the engine runs (ACTION)
    # 0-based index of the "### Žingsnis N" section in the strategy's RAG doc to
    # inject for THIS step (only that section, never the whole file). None = none.
    rag_section: int | None = None
    # CONFIRM only: which detector reads the caller's reply into a routing KEY
    # ("yes_no" default, "restored", "scope", "conn"). The key indexes `on`.
    detector: str = ""
    # Routing by key -> next step id. Keys are detector outputs ("yes"/"no" or
    # "all"/"phone"/… ). Missing key = fall through to the next step in order.
    # "resolve"/"escalate"/"end" are terminal sentinels.
    on: dict[str, str] = field(default_factory=dict)
    # INSTRUCT/ACTION only: explicit next step (overrides fall-through), so two
    # instruct chains can converge on the same verify step.
    goto: str = ""
    # ESCALATE only: ask the caller's consent before registering (default). False =
    # the registration is a NECESSITY, not an offer (e.g. register_after_bridge after a
    # working bridge — the router IS dead): the engine registers on arrival and the
    # narrator only ANNOUNCES it ("užregistravau, kolegos susisieks ir paaiškins").
    consent: bool = True


@dataclass(frozen=True)
class Strategy:
    verdict: str
    rag_doc: str | None
    steps: tuple[Step, ...]

    def step(self, step_id: str) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def by_role(self, role: str) -> Step | None:
        return next((s for s in self.steps if s.role == role), None)

    def index_of(self, step_id: str) -> int:
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                return i
        return -1


# Terminal sentinels a step can route to. "escalate" is a real ESCALATE step (the
# agent registers a fault there), so it is NOT a terminal — only resolve/end are.
TERMINALS = frozenset({"resolve", "end"})


def next_step_id(strategy: Strategy, current_id: str, outcome: str | None) -> str:
    """Given the current step and the turn's routing KEY (a detector output: "yes",
    "no", "all", "wifi"… — Outcome members work too, since Outcome is a str Enum),
    return the next step id (or a terminal sentinel). Explicit `on` routing wins;
    otherwise fall through to the next step in order; past the last step -> 'end'."""
    step = strategy.step(current_id)
    if step is None:
        return "end"
    if outcome is not None and outcome in step.on:
        return step.on[outcome]
    i = strategy.index_of(current_id)
    if i < 0 or i + 1 >= len(strategy.steps):
        return "end"
    return strategy.steps[i + 1].id


def confirms_device_change(text: str | None) -> bool:
    """True if the caller clearly stated they changed/connected a device."""
    if not text:
        return False
    low = text.lower()
    if any(m in low for m in vocab("neg")):
        return False
    return any(m in low for m in vocab("device_change"))


def detect_yes_no(text: str | None) -> Outcome | None:
    """YES / NO / None from a free-text caller reply (Lithuanian). Denials win over
    affirmatives ('routerio nekeičiau' -> NO), so an ambiguous or negative answer
    never advances a CONFIRM step into a binding action."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in vocab("neg")):
        return Outcome.NO
    if vocab_re("bare_no").search(low):
        return Outcome.NO
    if any(m in low for m in vocab("pos")):
        return Outcome.YES
    return None


def detect_restored(text: str | None) -> Outcome | None:
    """YES (internet is back) / NO (still down) / None, for the verify_restored
    step. Separate from detect_yes_no because the vocabulary differs and 'neveikia'
    must read as NO even though it contains 'veik'."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in vocab("restored_no")):
        return Outcome.NO
    if vocab_re("bare_no").search(low) or low.strip() in vocab("bare_no_replies"):
        return Outcome.NO
    if any(m in low for m in vocab("restored_yes")):
        return Outcome.YES
    # "jo" only as a standalone word — as a substring it matched "nepadėjo"/"jos"
    # (live 2026-09-11 / S6) and flipped a NO report to YES.
    if vocab_re("bare_yes_jo").search(low):
        return Outcome.YES
    return None


def detect_reboot_check(text: str | None) -> Outcome | None:
    """YES/NO/None for the S6 post-reboot check ("ar lemputė mirksi?
    pabandykite atsidaryti puslapį"). Dedicated vocabulary: NEGATION WINS
    ("dega, bet nemirksi" = NO), plain "dega" alone is UNCLEAR (a burning
    light is not working internet), the classifier settles the rest via the
    pack's `answers:` glosses."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in vocab("reboot_no")):
        return Outcome.NO
    if vocab_re("bare_no").search(low) or low.strip() in vocab("bare_no_replies"):
        return Outcome.NO
    if any(m in low for m in vocab("reboot_yes")):
        return Outcome.YES
    return None


def detect_scope(text: str | None) -> str | None:
    """Route the "all devices or one?" question. Returns 'all', 'phone' (a Wi-Fi-only
    device — phone/tablet/TV), 'computer', or None if unclear. A named single device
    implies scope=one, so we key off the device word first."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in vocab("one_phone")) or vocab_re("tv_word").search(low):
        return "phone"
    if any(m in low for m in vocab("one_computer")):
        return "computer"
    if any(m in low for m in vocab("all_mark")):
        return "all"
    # "tik viename" WITHOUT naming the device: scope answered, device not — route to
    # the WHICH-device step ('one'), never guess a device (guessing "computer" once
    # made the agent ask a phone user about cables). Checked AFTER _ALL_MARK so "nei
    # viename" (= none work = all down) is not misread as one.
    if any(m in low for m in vocab("one_mark")):
        return "one"
    return None


def detect_conn(text: str | None) -> str | None:
    """Route "wired or Wi-Fi?". Returns 'wired', 'wifi', or None. Wi-Fi is tested
    FIRST because "belaidis" (wireless) contains "laid". A phone/tablet can only be
    wireless, so naming one answers the question."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in vocab("conn_wifi")) or any(m in low for m in vocab("wireless_only")):
        return "wifi"
    if any(m in low for m in vocab("conn_wired")):
        return "wired"
    return None


def detect_port(text: str | None) -> str | None:
    """Route the incoming-cable question. 'wan' (Internet/WAN port — correct) / 'lan'
    (LAN or another port — must move) / None if unclear (stay and re-ask, do NOT
    assume). LAN is tested first so an explicit 'LAN' wins."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in vocab("port_lan")):
        return "lan"
    if any(m in low for m in vocab("port_wan")):
        return "wan"
    return None


def detect_lights(text: str | None) -> str | None:
    """Route "is any light on the router lit?". 'yes' / 'no' / None if unclear."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in vocab("lights_no")) or vocab_re("bare_no").search(low):
        return "no"
    if any(m in low for m in vocab("lights_yes")):
        return "yes"
    return None


def detect_have_device(text: str | None) -> str | None:
    """Route "do you have a computer / another router we could plug into?".

    Read CLAUSE BY CLAUSE: "neturiu kito routerio, aš tik kompiuterį turiu" is a YES —
    a computer is exactly what the bridge needs. Scanning the whole sentence for
    "neturiu" answered NO and told the caller nothing could be done, with a usable
    machine sitting right there."""
    if not text:
        return None
    low = text.lower()
    clauses = [c for c in vocab_re("clause_split").split(low) if c.strip()]
    saw_device_clause = False
    for c in clauses:
        if not any(d in c for d in vocab("usable_device")):
            continue
        saw_device_clause = True
        if not any(m in c for m in vocab("device_denial")) and not vocab_re("bare_no").search(c):
            return "yes"  # a device named without being denied — that is enough
    if saw_device_clause:
        return "no"  # every device they mentioned was denied
    # No device named at all — fall back to a plain yes/no, denial first.
    if (
        any(m in low for m in vocab("neg"))
        or vocab("device_denial")[0] in low
        or vocab_re("bare_no").search(low)
    ):
        return "no"
    if any(m in low for m in vocab("device_yes")) or any(m in low for m in vocab("pos")):
        return "yes"
    return None


def _yn(text: str | None) -> str | None:
    o = detect_yes_no(text)
    return o.value if o else None


def _restored(text: str | None) -> str | None:
    o = detect_restored(text)
    return o.value if o else None


# Named detectors a CONFIRM step selects with Step.detector. Each maps the caller's
# reply to a routing KEY (or None = unclear, stay and re-ask).
def _reboot_check(text: str | None) -> str | None:
    o = detect_reboot_check(text)
    return o.value if o else None


DETECTORS = {
    "yes_no": _yn,
    "restored": _restored,
    "reboot_check": _reboot_check,
    "scope": detect_scope,
    "conn": detect_conn,
    "port": detect_port,
    "lights": detect_lights,
    "have_device": detect_have_device,
}


# --- Turn intent -------------------------------------------------------------
# What KIND of turn the caller just took. Only ANSWER and DONE may advance a step;
# everything else holds the walker where it is. Without this every non-answer
# ("einu prie routerio", "nesuprantu", "o kiek kainuos?") collapsed into "repeat the
# question", and the agent ran ahead of the caller.
INTENT_ANSWER = "answer"  # a real answer to what we asked -> route it
INTENT_IN_PROGRESS = "in_progress"  # "einu / atsinešiu / tuoj" -> wait, do NOT check
INTENT_DONE = "done"  # "padariau / įkišau" -> the action completed
INTENT_QUESTION = "question"  # asking us something -> answer it, stay
INTENT_CONFUSED = "confused"  # does not follow -> explain finer, stay
INTENT_SILENCE = "silence"  # nothing usable -> wait, do not scold
INTENT_UNKNOWN = "unknown"  # safe default: hold and ask, never advance


def detect_turn_intent(text: str | None) -> str:
    """Classify the caller's turn before the walker routes it.

    Deterministic on purpose (same reasoning as the step detectors): the model
    phrases, the engine decides whether the conversation may move. Order matters —
    confusion and questions are checked before completion words, because "nesuprantu,
    ką padariau" is confusion, not a completed action."""
    if not text or not text.strip():
        return INTENT_SILENCE
    low = text.lower()
    if detect_confusion(low):
        return INTENT_CONFUSED
    if "?" in low or any(m in low for m in vocab("question_marks")):
        return INTENT_QUESTION
    if any(m in low for m in vocab("in_progress")):
        return INTENT_IN_PROGRESS
    if any(m in low for m in vocab("done")):
        return INTENT_DONE
    return INTENT_ANSWER


def detect_confusion(text: str | None) -> bool:
    """True when the caller signals they do not follow the technical wording ("kas tas
    WAN?", "nesuprantu", "neišmanau"). Raises the clarity level for the rest of the
    call so the agent explains in plain, visual words instead of repeating jargon."""
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in vocab("confused"))


def detect_address_confirm(text: str | None) -> str | None:
    """Read the reply to an address OFFER ("Ar skambinate dėl X?") without trusting a
    bare leading "taip": 'yes' only when the confirmation is CLEAN, 'no' when they
    deny / name another address, None when mixed or garbled (-> re-ask, never commit).

    Live bug this guards: STT turned "ne, 60-7" into "Taip, nebija" — the model saw
    "Taip…" and committed the WRONG apartment. Problem words ("neveikia", "nėra
    interneto") are not denials; any OTHER "ne-" token alongside a "taip" is."""
    if not text or not text.strip():
        return None
    low = text.lower()
    if any(m in low for m in vocab("addr_no")):
        return "no"
    ne_tokens = [
        t
        for t in vocab_re("negated_word").findall(low)
        # the PROBLEM being negated is not an address denial:
        if not t.startswith(vocab("problem_negations"))
    ]
    has_yes = any(m in low for m in vocab("address_yes"))
    if ne_tokens:
        return "no" if not has_yes else None  # mixed "taip…ne…" garble -> re-ask
    return "yes" if has_yes else None


def detect_cannot_now(text: str | None) -> bool:
    """True when the caller signals they CANNOT act right now (not at home,
    inconvenient, no time) — the flow must STOP and clarify, never push the
    next instruction."""
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in vocab("cannot_now"))


def detect_address_correction(text: str | None) -> bool:
    """True when an ALREADY-identified caller says they are calling about a different
    address ("tai ne dėl to adreso skambinu", "kitas butas") — the engine must reopen
    identification instead of carrying on about the wrong account (observed live)."""
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in vocab("addr_no"))


def detect_refuse_or_ticket(text: str | None) -> str | None:
    """'demand' (register it, now) / 'refuse' (won't troubleshoot) / None.

    Polarity-aware for DEMAND marks (2026-08-13): "NEregistruokite" carries the
    'registruok' substring but is the OPPOSITE of a demand — a mark only counts
    when the word carrying it is not itself negated."""
    if not text:
        return None
    low = text.lower()
    for token in low.split():
        word = token.strip(".,!?…")
        if word.startswith(vocab("negation_prefixes")):
            continue
        if any(m in word for m in vocab("ticket_demand")):
            return "demand"
        if any(m in word for m in vocab("ticket_demand_inf")) and any(
            c in low for c in vocab("ticket_demand_intent")
        ):
            return "demand"
    if any(m in low for m in vocab("ticket_refuse")):
        return "refuse"
    return None


def is_greeting(text: str | None) -> bool:
    """A short greeting/small-talk opener with NO problem content ("Labadiena!").
    Live 2026-08-06: such a turn fell to the LLM, which jumped straight to the
    address offer BEFORE any problem was stated — the ladder then re-offered it
    and the caller got the same question twice."""
    if not text:
        return False
    low = text.lower()
    if len(low.split()) > limits.get("greeting_max_words"):
        return False
    return any(m in low for m in vocab("greeting"))


def detect_no_device(text: str | None) -> bool:
    """The caller has NO device to bridge through ("neturiu kompiuterio", "tik
    telefonas"). Meaningful only right after the bridge OFFER — the caller
    checks the question context. Discipline rule 2026-08-05: this answer routes
    to the TICKET deterministically; the thinker may not wander back to
    re-checks (observed live: 6x disambiguate after "Neturiu.", then a full
    walker rewind to dr_intro)."""
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in vocab("no_device"))


def detect_plugged(text: str | None) -> bool:
    """True when the caller reports a COMPLETED plug-in ("įkišau į kompiuterį") — the
    discipline gate for a bind: the change runs only after the client actually did
    the work (and thereby agreed to it), never on the solver's anticipation.
    Diacritics-folded (STT drops nosinės); negation-prefix aware ("dar
    NEprijungiau" is not a report)."""
    if not text:
        return False
    from .evidence import _fold, _mark_hit

    low = _fold(text)
    return any(_mark_hit(low, m) for m in vocab("plugged"))


def detect_ticket_consent(text: str | None) -> str | None:
    """'yes' / 'no' / None from the caller's reply to "užregistruosiu gedimą — ar
    tinka?". Denials win; a bare "ne" is a decline; anything unclear returns None so
    the step holds and re-asks instead of registering on a garble."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in vocab("consent_no")):
        return "no"
    if vocab_re("bare_no").search(low):
        return "no"
    if any(m in low for m in vocab("consent_yes")):
        return "yes"
    return None


def detect_farewell(text: str | None) -> bool:
    """True when, after the case is closed, the caller signals they are done — a
    goodbye or a plain 'no' to 'anything else?'. Used to end the call so the agent
    does not loop goodbyes. A 'no' that carries a new question/topic does NOT count.
    The bare-"ne"/"viskas" fallback fires only on SHORT utterances (<=3 words): a long
    sentence containing "ne" is content, not a goodbye ("Ne, mano vardas Tomas, aš
    esu kaimynas" was read as a farewell and hung up on the caller — observed live)."""
    if not text:
        return False
    low = text.lower()
    words = [t.strip(".,!?…") for t in low.split()]
    tokens = set(words)

    # "Ačiū, nereikia" / "nebereikia" = polite done-signal (live 2026-08-13:
    # the thanks swallowed the refusal and the agent read it as gratitude).
    if "?" not in low and (
        tokens & vocab_set("no_longer_needed")
        or (tokens & vocab_set("not_needed") and tokens & vocab_set("thanks_words"))
    ):
        return True

    # "iki"/"ate" must match as WHOLE WORDS — as substrings they hide inside
    # "neveIKIa" / "ATEina" and read a fault report as a goodbye (caught by tests
    # the moment farewell started being checked on every turn). And "iki" counts
    # ONLY standalone — as a PREPOSITION it is content, not a goodbye: "Pajungtas
    # IKI GALO" ended a live bridge in a ticket (2026-08-11), "iki 17 valandos"
    # is a ticket-hours answer, "Iki šau" is STT of "Įkišau". A goodbye "iki" is
    # the LAST word or leads a farewell phrase ("iki pasimatymo").
    def _standalone_goodbye(word: str) -> bool:
        for i, w in enumerate(words):
            if w != word:
                continue
            nxt = words[i + 1] if i + 1 < len(words) else None
            if nxt is None or nxt in vocab_set("goodbye_followers"):
                return True
        return False

    if any(m in low for m in vocab("farewell")):
        return True
    if any(w in tokens and _standalone_goodbye(w) for w in vocab("standalone_goodbye")):
        return True
    has_followup = any(w in low for w in vocab("followup_marks"))
    short = len(low.split()) <= limits.get("short_utterance_max_words")
    # Bare "ne" is NEVER a farewell (Andrius 2026-08-20): a lone "Ne." to a
    # standing question is an ANSWER — its owner clarifies what the "ne"
    # means. Only "viskas"-style closers reach the pure-decline fallback.
    if not (short and not has_followup and any(w in low for w in vocab("closing_done"))):
        return False
    # The bare-"ne" fallback must be a PURE decline — every token a known
    # closing word. "Ne daganiai 1." (STT of "nedega nė viena") fast-forwarded
    # the ticket dialogue to done-with-defaults (observed live 2026-08-10):
    # unknown content words mean the caller is SAYING something, not leaving.
    return all(not t or t in vocab_set("closing_words") for t in tokens)


def is_backchannel(text: str | None) -> bool:
    """True for a bare acknowledgement noise / one-letter crumb — hold, don't route."""
    if not text:
        return False
    tokens = [t.strip(".,!?…") for t in text.lower().split()]
    tokens = [t for t in tokens if t]
    return bool(tokens) and all(t in vocab_set("backchannel") for t in tokens)


def is_bare_done_report(text: str | None) -> bool:
    """A DONE-report without a result: "Mhm, patikrinau." says the caller DID
    the check but not WHAT they found. Live 2026-08-11 the understanding pass
    invented the missing value (power_cable=atjungtas — echoed from the agent's
    own explanation) and the hypothesis never confirmed. Such a turn earns an
    acknowledge-and-ask-what-you-found clarify, never an invented fact.
    "Patikrinau, laidas įkištas" carries content — not bare."""
    if not text:
        return False
    tokens = [t.strip(".,!?…") for t in text.lower().split()]
    tokens = [t for t in tokens if t and t not in vocab_set("done_acks")]
    if not tokens or len(tokens) > limits.get("short_utterance_max_words"):
        return False
    return all(any(t.startswith(s) for s in vocab("done_stems")) for t in tokens)


def is_bare_negation(text: str | None) -> bool:
    """A short negation-only reply ("Ne.", "Ne, nežinau.") — a NO without an object.
    It says nothing about WHAT is denied: the pending check, the whole process, or
    a truncated "ne(dega)…" after a barge-in (live 2026-08-11: exactly that "Ne."
    was read as "won't check together" and killed the call with a cancelled
    ticket). Such a reply may answer a clarify question, never drive a destructive
    transition on its own."""
    if not text:
        return False
    tokens = [t.strip(".,!?…") for t in text.lower().split()]
    tokens = [t for t in tokens if t]
    if not tokens or len(tokens) > limits.get("short_utterance_max_words"):
        return False
    return any(t in vocab_set("negation_tokens") for t in tokens) and all(
        t in vocab_set("negation_tokens") or len(t) <= 2 for t in tokens
    )


def is_real_question(text: str | None) -> bool:
    """A QUESTION by its words, not by punctuation — STT sticks '?' onto rising
    intonation ("Tomas?"), which is not the caller asking us something. Token
    based (2026-08-07): "Aš skola kokia." closed the call because the old
    substring list required "kokia " with a trailing space."""
    if not text:
        return False
    low = text.lower()
    if any(m in low for m in vocab("question_marks")) or any(
        low.startswith(w) for w in vocab("question_openers")
    ):
        return True
    tokens = [t.strip(".,!?") for t in low.split()]
    return any(t in vocab_set("question_tokens") for t in tokens)


def get_strategy(verdict: str | None) -> Strategy | None:
    """The strategy for a diagnosis verdict reason, or None if unhandled (the
    caller falls back to the generic instruct/inform flow).

    Built from the fault pack (`knowledge/faults/`) — changing a procedure or adding
    a fault is a file edit. Imported lazily to keep the module free of a cycle."""
    if not verdict:
        return None
    from .faults import build_strategy

    return build_strategy(verdict)


def verify_target(strategy: Strategy, fixed: bool) -> str | None:
    """The terminal a strategy's VERIFY step routes to for a fixed / not-fixed
    telemetry outcome (e.g. 'resolve' / 'escalate'). None if it has no VERIFY step.
    Used by the engine after a silent action to decide resolve vs escalate."""
    vstep = next((s for s in strategy.steps if s.kind == StepKind.VERIFY), None)
    if vstep is None:
        return None
    return next_step_id(strategy, vstep.id, Outcome.FIXED if fixed else Outcome.NOT_FIXED)

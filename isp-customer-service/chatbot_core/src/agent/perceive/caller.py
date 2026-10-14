"""The caller's introduction — the name, the relation to the contract, and whether
the name plausibly matches the contract holder."""

from __future__ import annotations

from ..contract.locale import vocab, vocab_map, vocab_set, vocab_text


def holder_name_matches(state, rt, caller_name: str) -> bool:
    """Does the caller's stated first name plausibly match the CRM account
    holder's name? Fuzzy by 4-letter prefix (STT garbles endings). True also
    when the holder name is unknown — no basis to challenge."""

    holder = state.identity.customer_name or (state.identity.phone_candidate or {}).get("name")
    if not holder:
        return True
    return holder_spelling(state, caller_name) is not None or not _tokens(caller_name, holder)


def _tokens(caller_name: str, holder: str | None) -> bool:
    from ..evidence import _fold

    return bool(
        [t for t in _fold(caller_name).split() if len(t) >= 3]
        and [t for t in _fold(str(holder or "")).split() if len(t) >= 3]
    )


def holder_spelling(state, caller_name: str) -> str | None:
    """The holder's own spelling of the name the caller said, when what we heard is that name
    garbled by speech recognition („Gedrus" → „Giedrius", „Paulus" → „Paulius"); None when it
    is a different name. Saying it back reveals nothing — it is the name the caller gave.

    2026-10-14: a 4-letter prefix was too strict („gedr" ≠ „gied") and opened the „contract in
    another name" question for the holder himself.
    """
    from ..evidence import _fold

    holder = state.identity.customer_name or (state.identity.phone_candidate or {}).get("name")
    if not holder:
        return None
    for c in [t for t in _fold(caller_name).split() if len(t) >= 3]:
        for raw in str(holder).split():
            h = _fold(raw)
            if len(h) < 3:
                continue
            if c[:4] == h[:4] or (min(len(c), len(h)) >= 4 and _distance(c, h) <= 2):
                return raw.capitalize()
    return None


def _distance(a: str, b: str) -> int:
    """Edit distance — how many letters differ (insert, drop, swap one)."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def detect_caller_relation(text: str | None) -> str:
    """Keyword-read the caller's relation to the contract from their intro. Record
    + confidence signal only — never a gate."""
    if not text:
        return "unknown"
    low = text.lower()
    # Relation words WIN over a contract mention: "žmona sutartį sudariusio" names the
    # HOLDER'S wife — the caller is family, even though "sutart..." appears.
    for rel in ("family", "tenant", "helper"):
        if any(m in low for m in vocab_map("caller_relation_marks")[rel]):
            return rel
    if any(m in low for m in vocab("caller_not_holder")):
        return "other"  # explicitly not the holder, relation unstated
    if any(m in low for m in vocab_map("caller_relation_marks")["holder"]):
        return "holder"
    if any(m in low for m in vocab("caller_plain_yes")):
        return "holder"  # a plain yes to "ar jūs sutartį sudaręs asmuo?"
    return "unknown"


def extract_caller_name(text: str | None) -> str | None:
    """Pull the bare NAME out of an intro sentence — "Mano vardas Andrius" -> "Andrius".
    The pattern after "vardas/vardu" wins; otherwise the first capitalized token that
    is not a filler. None when nothing name-like is found (caller stays verbatim-less;
    the capture records "nenurodyta" via its own filter)."""
    if not text:
        return None
    import re as _re

    m = _re.search(rf"vard(?:as|u)(?:\s+yra)?\s+({vocab_text('name_word')})", text, _re.IGNORECASE)
    if m:
        return m.group(1).capitalize()
    for tok in _re.findall(vocab_text("name_word"), text):
        if tok.lower() not in vocab_set("name_stop_words") and len(tok) >= 3:
            if _garbled_marker(tok):
                continue  # „Panavardos" — STT of „mano vardas" (live 2026-10-12)
            return tok
    return None


def _garbled_marker(token: str) -> bool:
    """A word that is no name: the name QUESTION's own vocabulary mangled by STT, or a filler."""
    low = token.lower()
    if len(set(low)) <= 2:
        return True  # „Ėėė", „Mmm" — a filler sound, not a name
    return any(m in low for m in vocab("name_marker_stems"))


def introduced_name(text: str | None) -> str | None:
    """A name the caller GAVE unasked — „Labą dieną, esu Paulius, neveikia internetas".

    Strict on purpose (it runs over sentences that were about something else): only after an
    introduction marker, and only a capitalised word that is not a filler. „Aš esu darbe" is
    no name. Live 2026-10-12 the caller said „esu Paulius" first and was asked for the name
    anyway („tikiuosi minėjau").
    """
    if not text:
        return None
    import re as _re

    markers = "|".join(_re.escape(m) for m in vocab("caller_intro_markers"))
    m = _re.search(
        rf"(?:^|[\s,.;])(?:{markers})\s+({vocab_text('name_word')})", text, _re.IGNORECASE
    )
    if not m:
        return None
    name = m.group(1)
    if not name[:1].isupper() or name.lower() in vocab_set("name_stop_words"):
        return None
    after = text[m.end() :].strip().lower().split()
    if after and (
        after[0][:1].isdigit() or any(after[0].startswith(w) for w in vocab("not_name_followers"))
    ):
        return None  # „čia Vilniaus g. 29" — an address, not a name
    if len(name) < 3 or _garbled_marker(name):
        return None
    return name.capitalize()

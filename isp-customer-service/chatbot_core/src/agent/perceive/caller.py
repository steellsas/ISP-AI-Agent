"""The caller's introduction — the name, the relation to the contract, and whether
the name plausibly matches the contract holder."""

from __future__ import annotations

from ..contract.locale import vocab, vocab_map, vocab_set, vocab_text


def holder_name_matches(state, rt, caller_name: str) -> bool:
    """Does the caller's stated first name plausibly match the CRM account
    holder's name? Fuzzy by 4-letter prefix (STT garbles endings). True also
    when the holder name is unknown — no basis to challenge."""
    from ..evidence import _fold

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
            return tok
    return None

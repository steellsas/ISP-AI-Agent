"""Did the speaker keep the step? The engine's check on a guided step the speaker worded.

The speaker words a guided step for the moment (`phrase_guided_steps`, live 2026-11-10: the
written words sounded the same whatever the caller had just said). What the caller must still
get is the step itself: the thing to tap or name, the action, and — for a question — a
question. On 11-05 a free paraphrase asked something else and the caller answered that, so a
reply that lost the step is not spoken: the written words go out instead.

Only words, never meaning: the check is cheap and deterministic, and it errs towards the
written words (they are always correct, only less natural).
"""

from __future__ import annotations

import re

# „Pamiršti“, "Wi-Fi" — a name the caller looks for on the screen must survive word for word.
_QUOTED = re.compile(r"[„\"“]([^„\"“”]{2,40})[“”\"]")
_WORD = re.compile(r"[A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūž][A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūž-]*")
# Lithuanian endings change with the sentence; the first letters carry the word.
_STEM = 5
# Words that carry no part of the step: politeness, pace, the frame around the action.
_FRAME = {
    "pasak",  # pasakykite
    "praša",  # prašau
    "galit",  # galite
    "paban",  # pabandykite
    "nesku",  # neskubėkite
    "pirmi",  # pirmiausia
    "reiki",  # reikia
    "matys",  # matysite
    "turėt",  # turėtų
}
# Share of the step's own words the reply has to keep.
_KEEP = 0.5


def _stems(text: str) -> set[str]:
    out = set()
    for word in _WORD.findall(text or ""):
        low = word.casefold()
        if len(low) < 6 and "-" not in low:
            continue
        stem = low[:_STEM]
        if stem in _FRAME:
            continue
        out.add(stem)
    return out


def lost(reply: str, step_words: str) -> str | None:
    """Why the reply does not carry the step — or None when it does."""
    said = (reply or "").strip()
    if not said:
        return "empty"
    step = (step_words or "").strip()
    if not step:
        return None
    low = said.casefold()
    if step.rstrip().endswith("?") and "?" not in said:
        return "no_question"
    for name in _QUOTED.findall(step):
        if name.strip().casefold() not in low:
            return f"lost_name:{name.strip()}"
    wanted = _stems(step)
    if wanted:
        kept = wanted & _stems(said)
        if len(kept) < _KEEP * len(wanted):
            missing = sorted(wanted - kept)
            return "lost_words:" + ",".join(missing[:6])
    return None

"""The reply guard — the phone rules a streamed reply must keep, enforced WHILE it
streams (review finding AB).

The old length cap trimmed the reply after streaming: the caller had already heard
every word, only the history got shortened. Here the reply is checked before it goes
out, so what is cut is never spoken or recorded:

- ONE question per reply: the reply ends with the first question sentence.
- Short replies: once the reply is past `reply_stop_chars`, it ends at the next
  sentence end (a single long sentence still goes out whole — never mid-sentence).
- Sentence rules (wave 10): the reply is let out a SENTENCE at a time, so a sentence the
  engine forbids (`drop`, e.g. a registration promise nothing backs) is never heard, and
  a sentence can be repaired first (`fix`, e.g. Cyrillic look-alike letters). The voice
  path speaks per sentence anyway, so holding one costs no audio time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

_SENTENCE_END = ".!?"
# Closing marks that belong to the sentence they end („Ar dega?“ — the quote stays).
_CLOSERS = "\"'”“»)"


@dataclass
class ReplyGuard:
    stop_chars: int
    drop: Callable[[str], bool] | None = None
    fix: Callable[[str], str] | None = None
    text: str = ""  # what went out
    stopped: str | None = field(default=None)  # why the reply ended early
    dropped: list[str] = field(default_factory=list)  # sentences the engine withheld
    _pending: str = ""

    def feed(self, token: str) -> str:
        """What may go out now — whole sentences only; sets `stopped` when the reply ends."""
        if self.stopped:
            return ""
        out = ""
        buf = self._pending + token
        start = 0
        i = 0
        while i < len(buf):
            ch = buf[i]
            if ch not in _SENTENCE_END:
                i += 1
                continue
            end = i + 1
            if ch == "." and end < len(buf) and buf[end].isalnum():
                i += 1
                continue  # a decimal or an abbreviation inside a word ("1.5", "g.60")
            while end < len(buf) and buf[end] in _CLOSERS:
                end += 1
            out += self._release(buf[start:end], question=ch == "?")
            start = i = end
            if self.stopped:
                self._pending = ""
                return out
        self._pending = buf[start:]
        return out

    def flush(self) -> str:
        """The unfinished tail at the end of the stream."""
        if self.stopped or not self._pending.strip():
            self._pending = ""
            return ""
        tail, self._pending = self._pending, ""
        return self._release(tail, question=False)

    def _release(self, sentence: str, *, question: bool) -> str:
        if self.fix is not None:
            sentence = self.fix(sentence)
        if self.drop is not None and self.drop(sentence):
            self.dropped.append(sentence.strip())
            return ""
        if question:
            self.stopped = "one_question"
        elif len(self.text) + len(sentence) >= self.stop_chars:
            self.stopped = "length"
        self.text += sentence
        return sentence


# Cyrillic letters inside a Lithuanian reply. An open model slips into Russian tokens mid-word
# (live eval K1, 2026-10-08: „skурti"); TTS then cannot read the word. They are written as the
# Latin letters they SOUND like — the model meant a sound, not a shape.
_CYRILLIC = str.maketrans(
    {
        **dict(
            zip("абвгдезиклмнопрстуфАБВГДЕЗИКЛМНОПРСТУФ", "abvgdeziklmnoprstufABVGDEZIKLMNOPRSTUF")
        ),
        "і": "i",
        "І": "I",
        "ы": "y",
        "й": "j",
        "х": "ch",
        "ж": "ž",
        "ш": "š",
        "ч": "č",
        "ц": "c",
    }
)


def latin_lookalikes(sentence: str) -> str:
    """The sentence with Cyrillic letters written as the Latin letters they sound like."""
    return sentence.translate(_CYRILLIC)

"""The reply guard — the phone rules a streamed reply must keep, enforced WHILE it
streams (review finding AB).

The old length cap trimmed the reply after streaming: the caller had already heard
every word, only the history got shortened. Here each token is checked before it goes
out, so what is cut is never generated, spoken or recorded:

- ONE question per reply: the reply ends with the first question sentence.
- Short replies: once the reply is past `reply_stop_chars`, it ends at the next
  sentence end (a single long sentence still goes out whole — never mid-sentence).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_SENTENCE_END = ".!?"
# Closing marks that belong to the sentence they end („Ar dega?“ — the quote stays).
_CLOSERS = "\"'”“»)"


@dataclass
class ReplyGuard:
    stop_chars: int
    text: str = ""
    stopped: str | None = field(default=None)  # why the reply ended early

    def feed(self, token: str) -> str:
        """The part of `token` that may go out; sets `stopped` when the reply ends."""
        if self.stopped:
            return ""
        for i, ch in enumerate(token):
            if ch not in _SENTENCE_END:
                continue
            end = i + 1
            if ch == "." and end < len(token) and token[end].isalnum():
                continue  # a decimal or an abbreviation inside a word ("1.5", "g.60")
            while end < len(token) and token[end] in _CLOSERS:
                end += 1
            if ch == "?":
                self.stopped = "one_question"
            elif len(self.text) + end >= self.stop_chars:
                self.stopped = "length"
            if self.stopped:
                part = token[:end]
                self.text += part
                return part
        self.text += token
        return token

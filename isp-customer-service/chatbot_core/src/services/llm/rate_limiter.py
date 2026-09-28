"""LLM rate limiter — a minute window for the provider, a budget per conversation.

Two different fears, and until wave 5 they shared one counter:

* **the provider and the bill** — how many calls per minute this PROCESS may make;
* **a runaway call** — how many calls ONE conversation may spend before something is
  clearly looping.

The second was counted per process too (`max_per_session` on a process-global singleton),
which is right for a single CLI call and wrong for a server: after ~100 LLM calls the API
refused every caller until a restart, and the eval had to raise the ceiling on every loaded
copy of the module just to get through a suite. We hit it ourselves twice while measuring
(ROADMAP R-16, finding F-2).

The budget is now counted per conversation, keyed by a ContextVar that `AgentSession` sets
around every turn, and a finished call's counter is dropped by the finalizer.
"""

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    pass


# Which conversation the calls in this task belong to. "process" is the honest default: a
# script or a test calling the LLM directly has no conversation.
_conversation: ContextVar[str] = ContextVar("llm_conversation", default="process")

# How many conversations' counters to keep. The finalizer drops a call's counter when it
# ends, so this only bounds the leak when a transport dies without finalizing.
_CONVERSATIONS_KEPT = 64


@contextmanager
def conversation_scope(conversation_id: str):
    """Count the LLM calls made inside this block against `conversation_id`."""
    token = _conversation.set(conversation_id or "process")
    try:
        yield
    finally:
        _conversation.reset(token)


def current_conversation() -> str:
    return _conversation.get()


class RateLimiter:
    """A minute window per process, a call budget per conversation."""

    def __init__(self, max_per_minute: int = 30, max_per_conversation: int = 100):
        self.max_per_minute = max_per_minute
        self.max_per_conversation = max_per_conversation
        self.minute_calls: list[float] = []
        self.conversation_calls: dict[str, int] = {}

    def check(self) -> tuple[bool, str]:
        """
        Check if a call is allowed.

        Returns:
            (allowed, reason)
        """
        now = time.time()

        # Clean old minute calls
        self.minute_calls = [t for t in self.minute_calls if now - t < 60]

        # Check minute limit
        if len(self.minute_calls) >= self.max_per_minute:
            wait_time = 60 - (now - self.minute_calls[0])
            return False, f"Rate limit: {self.max_per_minute}/min. Wait {wait_time:.0f}s"

        # Check this conversation's budget
        spent = self.conversation_calls.get(_conversation.get(), 0)
        if spent >= self.max_per_conversation:
            return False, f"Conversation limit: {self.max_per_conversation} calls reached"

        return True, "OK"

    def check_or_raise(self):
        """Check rate limit and raise if exceeded."""
        allowed, reason = self.check()
        if not allowed:
            logger.warning(f"Rate limit exceeded: {reason}")
            raise RateLimitError(reason)

    def record_call(self):
        """Record a successful call."""
        self.minute_calls.append(time.time())
        key = _conversation.get()
        self.conversation_calls[key] = self.conversation_calls.get(key, 0) + 1
        while len(self.conversation_calls) > _CONVERSATIONS_KEPT:
            self.conversation_calls.pop(next(iter(self.conversation_calls)))

    def forget(self, conversation_id: str) -> None:
        """The call ended — its budget is no longer anyone's business."""
        self.conversation_calls.pop(conversation_id, None)

    def reset(self):
        """Reset rate limiter."""
        self.minute_calls = []
        self.conversation_calls = {}
        logger.info("Rate limiter reset")

    def get_status(self) -> dict:
        """Get current rate limit status for UI."""
        now = time.time()
        self.minute_calls = [t for t in self.minute_calls if now - t < 60]
        spent = self.conversation_calls.get(_conversation.get(), 0)

        return {
            "calls_this_minute": len(self.minute_calls),
            "max_per_minute": self.max_per_minute,
            "remaining_this_minute": self.max_per_minute - len(self.minute_calls),
            "conversation": _conversation.get(),
            "calls_this_conversation": spent,
            "max_per_conversation": self.max_per_conversation,
            "remaining_this_conversation": self.max_per_conversation - spent,
            "conversations_tracked": len(self.conversation_calls),
            "can_call": self.check()[0],
        }

    def update_limits(self, max_per_minute: int = None, max_per_conversation: int = None):
        """Update rate limits."""
        if max_per_minute is not None:
            self.max_per_minute = max_per_minute
        if max_per_conversation is not None:
            self.max_per_conversation = max_per_conversation


# =============================================================================
# Global Rate Limiter Instance
# =============================================================================

_rate_limiter: RateLimiter = None


def get_rate_limiter() -> RateLimiter:
    """Get rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def reset_rate_limiter():
    """Reset rate limiter."""
    global _rate_limiter
    _rate_limiter = RateLimiter()


def forget_conversation(conversation_id: str) -> None:
    """Drop a finished call's budget (the finalizer calls this)."""
    get_rate_limiter().forget(conversation_id)

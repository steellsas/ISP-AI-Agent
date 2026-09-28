"""The LLM budget belongs to a conversation, the minute window to the process (R-16).

Before wave 5 both counters were per process: an API server spent the 100-call budget across
everyone's calls and then refused new ones until a restart, and an eval run had to raise the
ceiling to finish a suite.
"""

from services.llm.rate_limiter import (
    _CONVERSATIONS_KEPT,
    RateLimiter,
    conversation_scope,
    current_conversation,
)


def _spend(limiter: RateLimiter, calls: int) -> None:
    for _ in range(calls):
        limiter.record_call()


def test_one_conversation_spending_its_budget_does_not_block_another():
    limiter = RateLimiter(max_per_minute=1000, max_per_conversation=3)

    with conversation_scope("call-A"):
        _spend(limiter, 3)
        allowed, reason = limiter.check()
        assert not allowed and "Conversation limit" in reason

    with conversation_scope("call-B"):
        assert limiter.check()[0], "a fresh call must have its own budget"


def test_the_budget_survives_across_turns_of_the_same_call():
    """A runaway call is still stopped: the counter is per conversation, not per turn."""
    limiter = RateLimiter(max_per_minute=1000, max_per_conversation=2)

    with conversation_scope("call-A"):  # turn 1
        _spend(limiter, 2)
    with conversation_scope("call-A"):  # turn 2
        assert not limiter.check()[0]


def test_the_minute_window_stays_process_wide():
    """The provider does not care which call the traffic came from."""
    limiter = RateLimiter(max_per_minute=2, max_per_conversation=1000)

    with conversation_scope("call-A"):
        _spend(limiter, 2)
    with conversation_scope("call-B"):
        allowed, reason = limiter.check()
        assert not allowed and "/min" in reason


def test_forget_frees_a_finished_calls_budget():
    limiter = RateLimiter(max_per_minute=1000, max_per_conversation=1)

    with conversation_scope("call-A"):
        _spend(limiter, 1)
        assert not limiter.check()[0]
        limiter.forget("call-A")  # what the finalizer does when the call ends
        assert limiter.check()[0]


def test_counters_are_bounded_when_a_call_never_finalizes():
    limiter = RateLimiter(max_per_minute=100_000, max_per_conversation=10)

    for i in range(_CONVERSATIONS_KEPT + 20):
        with conversation_scope(f"call-{i}"):
            limiter.record_call()

    assert len(limiter.conversation_calls) == _CONVERSATIONS_KEPT


def test_calls_outside_a_conversation_are_the_process():
    assert current_conversation() == "process"

    limiter = RateLimiter(max_per_minute=1000, max_per_conversation=1)
    limiter.record_call()  # e.g. a script or a measurement, no call in progress

    assert limiter.conversation_calls == {"process": 1}
    assert limiter.get_status()["conversation"] == "process"

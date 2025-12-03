"""
LLM Rate Limiter

Prevents excessive API calls.
"""

import time
import logging

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    pass


class RateLimiter:
    """Simple rate limiter for LLM calls."""
    
    def __init__(self, max_per_minute: int = 30, max_per_session: int = 100):
        self.max_per_minute = max_per_minute
        self.max_per_session = max_per_session
        self.minute_calls: list[float] = []
        self.session_calls: int = 0
    
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
        
        # Check session limit
        if self.session_calls >= self.max_per_session:
            return False, f"Session limit: {self.max_per_session} calls reached"
        
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
        self.session_calls += 1
    
    def reset(self):
        """Reset rate limiter."""
        self.minute_calls = []
        self.session_calls = 0
        logger.info("Rate limiter reset")
    
    def get_status(self) -> dict:
        """Get current rate limit status for UI."""
        now = time.time()
        self.minute_calls = [t for t in self.minute_calls if now - t < 60]
        
        return {
            "calls_this_minute": len(self.minute_calls),
            "max_per_minute": self.max_per_minute,
            "remaining_this_minute": self.max_per_minute - len(self.minute_calls),
            "calls_this_session": self.session_calls,
            "max_per_session": self.max_per_session,
            "remaining_this_session": self.max_per_session - self.session_calls,
            "can_call": self.check()[0],
        }
    
    def update_limits(self, max_per_minute: int = None, max_per_session: int = None):
        """Update rate limits."""
        if max_per_minute is not None:
            self.max_per_minute = max_per_minute
        if max_per_session is not None:
            self.max_per_session = max_per_session


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

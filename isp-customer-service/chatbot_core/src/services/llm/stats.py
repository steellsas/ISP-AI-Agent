"""
LLM Statistics

Track token usage, costs, and performance metrics.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CallStats:
    """Statistics for a single LLM call."""
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    timestamp: datetime
    cached: bool = False
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp.isoformat(),
            "cached": self.cached,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class SessionStats:
    """Aggregated statistics for a session."""
    calls: list[CallStats] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    
    # Computed properties
    @property
    def total_calls(self) -> int:
        return len(self.calls)
    
    @property
    def successful_calls(self) -> int:
        return sum(1 for c in self.calls if c.success)
    
    @property
    def failed_calls(self) -> int:
        return sum(1 for c in self.calls if not c.success)
    
    @property
    def cached_calls(self) -> int:
        return sum(1 for c in self.calls if c.cached)
    
    @property
    def total_tokens(self) -> int:
        return sum(c.total_tokens for c in self.calls)
    
    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)
    
    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)
    
    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)
    
    @property
    def average_latency_ms(self) -> float:
        non_cached = [c for c in self.calls if not c.cached and c.success]
        if not non_cached:
            return 0.0
        return sum(c.latency_ms for c in non_cached) / len(non_cached)
    
    @property
    def calls_per_model(self) -> dict[str, int]:
        counts = {}
        for c in self.calls:
            counts[c.model] = counts.get(c.model, 0) + 1
        return counts
    
    @property
    def tokens_per_model(self) -> dict[str, int]:
        tokens = {}
        for c in self.calls:
            tokens[c.model] = tokens.get(c.model, 0) + c.total_tokens
        return tokens
    
    @property
    def cost_per_model(self) -> dict[str, float]:
        costs = {}
        for c in self.calls:
            costs[c.model] = costs.get(c.model, 0) + c.cost_usd
        return costs
    
    @property
    def session_duration_seconds(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()
    
    def get_recent_calls(self, n: int = 10) -> list[CallStats]:
        """Get n most recent calls."""
        return self.calls[-n:]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for UI display."""
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "cached_calls": self.cached_calls,
            "total_tokens": self.total_tokens,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_cost_display": f"${self.total_cost_usd:.4f}",
            "average_latency_ms": round(self.average_latency_ms, 2),
            "calls_per_model": self.calls_per_model,
            "tokens_per_model": self.tokens_per_model,
            "cost_per_model": {k: round(v, 6) for k, v in self.cost_per_model.items()},
            "session_duration_seconds": round(self.session_duration_seconds, 1),
        }
    
    def get_summary_text(self) -> str:
        """Get human-readable summary."""
        stats = self.to_dict()
        return f"""
📊 LLM Usage Summary
───────────────────
Calls: {stats['total_calls']} ({stats['successful_calls']} success, {stats['cached_calls']} cached)
Tokens: {stats['input_tokens']:,} in + {stats['output_tokens']:,} out = {stats['total_tokens']:,} total
Cost: {stats['total_cost_display']}
Avg Latency: {stats['average_latency_ms']:.0f}ms
Session: {stats['session_duration_seconds']:.0f}s
"""


# =============================================================================
# Global Session Stats Instance
# =============================================================================

_session_stats: SessionStats = None


def get_session_stats() -> SessionStats:
    """Get current session statistics."""
    global _session_stats
    if _session_stats is None:
        _session_stats = SessionStats()
    return _session_stats


def reset_session_stats():
    """Reset session statistics."""
    global _session_stats
    _session_stats = SessionStats()
    logger.info("Session stats reset")


def record_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: float,
    cached: bool = False,
    success: bool = True,
    error: str = None,
):
    """Record a call in session stats."""
    stats = CallStats(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        timestamp=datetime.now(),
        cached=cached,
        success=success,
        error=error,
    )
    get_session_stats().calls.append(stats)
    
    if not cached:
        logger.debug(
            f"LLM call recorded: {model}, tokens={input_tokens}+{output_tokens}, "
            f"cost=${cost_usd:.6f}, latency={latency_ms:.0f}ms"
        )

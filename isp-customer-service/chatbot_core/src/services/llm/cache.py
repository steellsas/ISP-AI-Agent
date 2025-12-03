"""
LLM Response Cache

In-memory cache for LLM responses to reduce costs.
"""

import json
import time
import hashlib
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class ResponseCache:
    """In-memory cache for LLM responses."""
    
    def __init__(self, ttl_seconds: int = 300, max_temp_for_cache: float = 0.2):
        """
        Initialize cache.
        
        Args:
            ttl_seconds: Time-to-live for cached responses
            max_temp_for_cache: Only cache responses for temperature <= this value
        """
        self.ttl = ttl_seconds
        self.max_temp = max_temp_for_cache
        self.cache: dict[str, tuple[str, float]] = {}  # key -> (response, timestamp)
        self.hits = 0
        self.misses = 0
    
    def _make_key(self, messages: list[dict], model: str, temperature: float) -> str:
        """
        Create cache key from request parameters.
        
        Returns empty string if request shouldn't be cached (high temperature).
        """
        # Only cache deterministic requests
        if temperature > self.max_temp:
            return ""
        
        content = json.dumps({
            "messages": messages,
            "model": model
        }, sort_keys=True)
        
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, messages: list[dict], model: str, temperature: float) -> Optional[str]:
        """
        Get cached response if available.
        
        Args:
            messages: Request messages
            model: Model ID
            temperature: Temperature used
            
        Returns:
            Cached response or None
        """
        key = self._make_key(messages, model, temperature)
        if not key:
            return None
        
        if key in self.cache:
            response, timestamp = self.cache[key]
            
            # Check if still valid
            if time.time() - timestamp < self.ttl:
                self.hits += 1
                logger.debug(f"Cache hit (key={key[:8]}...)")
                return response
            else:
                # Expired
                del self.cache[key]
        
        self.misses += 1
        return None
    
    def set(self, messages: list[dict], model: str, temperature: float, response: str):
        """
        Cache a response.
        
        Args:
            messages: Request messages
            model: Model ID
            temperature: Temperature used
            response: Response to cache
        """
        key = self._make_key(messages, model, temperature)
        if key:
            self.cache[key] = (response, time.time())
            logger.debug(f"Cached response (key={key[:8]}...)")
    
    def clear(self):
        """Clear all cached responses."""
        count = len(self.cache)
        self.cache = {}
        self.hits = 0
        self.misses = 0
        logger.info(f"Cache cleared ({count} entries)")
    
    def cleanup_expired(self):
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, (_, ts) in self.cache.items() if now - ts >= self.ttl]
        for k in expired:
            del self.cache[k]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired cache entries")
    
    def get_stats(self) -> dict:
        """Get cache statistics for UI."""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 1),
            "ttl_seconds": self.ttl,
            "max_temp_for_cache": self.max_temp,
        }


# =============================================================================
# Global Cache Instance
# =============================================================================

_response_cache: ResponseCache = None


def get_cache() -> ResponseCache:
    """Get cache instance."""
    global _response_cache
    if _response_cache is None:
        _response_cache = ResponseCache()
    return _response_cache


def clear_cache():
    """Clear response cache."""
    get_cache().clear()

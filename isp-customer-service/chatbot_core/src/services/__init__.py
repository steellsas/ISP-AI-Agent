"""
Services module - LLM and external integrations
"""

from .llm import llm_completion, llm_json_completion

__all__ = [
    "llm_completion",
    "llm_json_completion",
]
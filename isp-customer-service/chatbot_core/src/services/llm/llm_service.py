"""LiteLLM wrapper for multiple LLM providers"""


class LLMService:
    """LLM service using LiteLLM"""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model

    def generate(self, messages: list, temperature: float = 0.7):
        """Generate response using LLM"""
        # This will call LiteLLM
        return ""

    def stream(self, messages: list):
        """Stream response from LLM"""
        # This will stream response from LiteLLM
        return None

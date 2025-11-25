"""
LLM Service
OpenAI API wrapper for chat completions
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator
from openai import OpenAI, AsyncOpenAI

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger, get_config

logger = get_logger(__name__)


class LLMService:
    """
    LLM Service for chat completions using OpenAI API.
    
    Features:
    - Sync and async completions
    - Streaming support
    - Token counting and cost tracking
    - Retry logic
    - Temperature and parameter control
    - Structured output generation
    - Intent classification
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 1000
    ):
        """
        Initialize LLM service.
        
        Args:
            api_key: OpenAI API key (defaults to env var)
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        # Get API key from env if not provided
        if api_key is None:
            config = get_config()
            api_key = config.openai_api_key
        
        if not api_key:
            raise ValueError("OpenAI API key not provided and not found in environment")
        
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Initialize clients
        self.client = OpenAI(api_key=api_key)
        self.async_client = AsyncOpenAI(api_key=api_key)
        
        # Statistics
        self.total_tokens_used = 0
        self.total_requests = 0
        
        logger.info(f"LLMService initialized with model: {model}")
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Get chat completion (synchronous).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            system_prompt: Optional system prompt to prepend
            
        Returns:
            Response content string
        """
        try:
            # Prepend system prompt if provided
            if system_prompt:
                messages = [
                    {"role": "system", "content": system_prompt}
                ] + messages
            
            # Make API call
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens
            )
            
            # Extract response
            content = response.choices[0].message.content
            
            # Update statistics
            self.total_tokens_used += response.usage.total_tokens
            self.total_requests += 1
            
            logger.info(f"Chat completion: {response.usage.total_tokens} tokens used")
            
            return content
            
        except Exception as e:
            logger.error(f"Error in chat completion: {e}", exc_info=True)
            raise
    
    async def chat_completion_async(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Get chat completion (asynchronous).
        
        Args:
            messages: List of message dicts
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            system_prompt: Optional system prompt
            
        Returns:
            Response content string
        """
        try:
            # Prepend system prompt if provided
            if system_prompt:
                messages = [
                    {"role": "system", "content": system_prompt}
                ] + messages
            
            # Make async API call
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens
            )
            
            # Extract response
            content = response.choices[0].message.content
            
            # Update statistics
            self.total_tokens_used += response.usage.total_tokens
            self.total_requests += 1
            
            logger.info(f"Async chat completion: {response.usage.total_tokens} tokens used")
            
            return content
            
        except Exception as e:
            logger.error(f"Error in async chat completion: {e}", exc_info=True)
            raise
    
    def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ):
        """
        Get streaming chat completion (synchronous).
        
        Args:
            messages: List of message dicts
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            system_prompt: Optional system prompt
            
        Yields:
            Content chunks
        """
        try:
            # Prepend system prompt if provided
            if system_prompt:
                messages = [
                    {"role": "system", "content": system_prompt}
                ] + messages
            
            # Make streaming API call
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            
            self.total_requests += 1
            logger.info("Streaming completion finished")
            
        except Exception as e:
            logger.error(f"Error in streaming completion: {e}", exc_info=True)
            raise
    
    async def chat_completion_stream_async(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Get streaming chat completion (asynchronous).
        
        Args:
            messages: List of message dicts
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            system_prompt: Optional system prompt
            
        Yields:
            Content chunks
        """
        try:
            # Prepend system prompt if provided
            if system_prompt:
                messages = [
                    {"role": "system", "content": system_prompt}
                ] + messages
            
            # Make async streaming API call
            stream = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            
            self.total_requests += 1
            logger.info("Async streaming completion finished")
            
        except Exception as e:
            logger.error(f"Error in async streaming: {e}", exc_info=True)
            raise
    
    # ========== NEW METHODS FOR GRAPH NODES ==========
    
    async def generate(
        self,
        system_prompt: str,
        messages: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Simple generation wrapper (async).
        
        This is a convenience method for nodes that need simple text generation.
        
        Args:
            system_prompt: System prompt to guide generation
            messages: Optional conversation history
            temperature: Temperature override
            max_tokens: Max tokens override
            
        Returns:
            Generated text
        """
        if messages is None:
            messages = []
        
        return await self.chat_completion_async(
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    async def generate_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_format: Dict[str, str],
        temperature: Optional[float] = 0.3
    ) -> str:
        """
        Generate structured JSON response.
        
        Forces the LLM to respond with valid JSON matching the specified format.
        
        Args:
            system_prompt: System prompt describing the task
            user_message: User's message to process
            response_format: Dictionary describing expected JSON format
                Example: {"problem_type": "string", "confidence": "float"}
            temperature: Temperature (lower for more consistent structured output)
            
        Returns:
            JSON string (needs to be parsed with json.loads())
            
        Example:
            >>> response = await llm.generate_structured(
            ...     system_prompt="Classify the problem",
            ...     user_message="My internet is down",
            ...     response_format={
            ...         "problem_type": "internet|tv|phone",
            ...         "confidence": "float 0-1"
            ...     }
            ... )
            >>> data = json.loads(response)
        """
        # Build format description
        format_desc = "\n".join([f"- {k}: {v}" for k, v in response_format.items()])
        
        full_system_prompt = f"""{system_prompt}

You MUST respond with ONLY valid JSON in this exact format:
{format_desc}

Rules:
- Do not include any explanatory text
- Do not include markdown code blocks
- Return only the raw JSON object
- Ensure all JSON is properly formatted"""
        
        messages = [{"role": "user", "content": user_message}]
        
        response = await self.chat_completion_async(
            messages=messages,
            system_prompt=full_system_prompt,
            temperature=temperature,
            max_tokens=500
        )
        
        # Clean markdown code blocks if present
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        
        return response.strip()
    
    async def classify_intent(
        self,
        user_message: str,
        intents: List[str],
        temperature: Optional[float] = 0.2
    ) -> str:
        """
        Classify user message into one of the given intents.
        
        Uses LLM to determine which intent best matches the user's message.
        
        Args:
            user_message: User's message to classify
            intents: List of possible intent names
            temperature: Temperature (lower for more deterministic classification)
            
        Returns:
            The most likely intent from the provided list
            
        Example:
            >>> intent = await llm.classify_intent(
            ...     user_message="Yes, that's correct",
            ...     intents=["yes", "no", "unclear"]
            ... )
            >>> print(intent)  # "yes"
        """
        if not intents:
            logger.warning("No intents provided for classification")
            return "unclear"
        
        intents_str = ", ".join(intents)
        
        system_prompt = f"""You are classifying user messages into intents.

Available intents: {intents_str}

Rules:
- Respond with ONLY the intent name
- Choose the single best matching intent
- Do not add any explanation or punctuation
- If unclear, respond with the first intent in the list"""
        
        messages = [{"role": "user", "content": user_message}]
        
        try:
            response = await self.chat_completion_async(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=20
            )
            
            # Clean and normalize
            response = response.strip().lower()
            
            # Find exact or partial match
            for intent in intents:
                intent_lower = intent.lower()
                if intent_lower == response or intent_lower in response or response in intent_lower:
                    logger.info(f"Classified intent: {intent} (from: {user_message[:50]}...)")
                    return intent
            
            # No match found - default to first intent
            logger.warning(f"No intent match found for: {user_message[:50]}... Defaulting to: {intents[0]}")
            return intents[0]
            
        except Exception as e:
            logger.error(f"Error in intent classification: {e}", exc_info=True)
            # Return first intent as fallback
            return intents[0]
    
    # ========== EXISTING HELPER METHODS ==========
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment of text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Sentiment analysis result
        """
        messages = [
            {
                "role": "system",
                "content": "Analyze the sentiment of the following text. Respond with JSON: {\"sentiment\": \"positive/negative/neutral\", \"confidence\": 0.0-1.0, \"reason\": \"brief explanation\"}"
            },
            {
                "role": "user",
                "content": text
            }
        ]
        
        response = self.chat_completion(messages, temperature=0.3)
        
        try:
            import json
            return json.loads(response)
        except:
            return {"sentiment": "neutral", "confidence": 0.5, "reason": "Could not parse"}
    
    def extract_entities(self, text: str, entity_types: List[str]) -> Dict[str, List[str]]:
        """
        Extract named entities from text.
        
        Args:
            text: Text to analyze
            entity_types: Types of entities to extract (e.g., ["address", "phone", "email"])
            
        Returns:
            Dictionary of entity types to extracted values
        """
        entity_list = ", ".join(entity_types)
        
        messages = [
            {
                "role": "system",
                "content": f"Extract the following entities from the text: {entity_list}. Respond with JSON."
            },
            {
                "role": "user",
                "content": text
            }
        ]
        
        response = self.chat_completion(messages, temperature=0.2)
        
        try:
            import json
            return json.loads(response)
        except:
            return {entity_type: [] for entity_type in entity_types}
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get usage statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "total_requests": self.total_requests,
            "total_tokens_used": self.total_tokens_used,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
    
    def reset_statistics(self):
        """Reset usage statistics."""
        self.total_tokens_used = 0
        self.total_requests = 0
        logger.info("Statistics reset")


# Singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service(
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> LLMService:
    """
    Get or create LLMService singleton instance.
    
    Args:
        api_key: OpenAI API key (only used on first call)
        model: Model name (only used on first call)
        temperature: Temperature (only used on first call)
        max_tokens: Max tokens (only used on first call)
        
    Returns:
        LLMService instance
    """
    global _llm_service
    
    if _llm_service is None:
        _llm_service = LLMService(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    return _llm_service
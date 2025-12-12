"""
Session State Management for Streamlit UI
Simplified for ReAct Agent
"""

import streamlit as st
import uuid
from datetime import datetime


def init_session():
    """Initialize all session state variables."""
    
    # Conversation state
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None
    
    if "phone_number" not in st.session_state:
        st.session_state.phone_number = "+37060012345"
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "agent" not in st.session_state:
        st.session_state.agent = None
    
    # Call state
    if "call_active" not in st.session_state:
        st.session_state.call_active = False
    
    if "call_start_time" not in st.session_state:
        st.session_state.call_start_time = None
    
    if "call_ended" not in st.session_state:
        st.session_state.call_ended = False
    
    # Monitoring data
    if "llm_calls" not in st.session_state:
        st.session_state.llm_calls = []
    
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []
    
    if "total_tokens" not in st.session_state:
        st.session_state.total_tokens = 0
    
    if "total_cost" not in st.session_state:
        st.session_state.total_cost = 0.0
    
    # LLM call tracking (updated via callbacks)
    if "llm_call_count" not in st.session_state:
        st.session_state.llm_call_count = 0
    
    if "average_latency" not in st.session_state:
        st.session_state.average_latency = 0.0
    
    if "cached_count" not in st.session_state:
        st.session_state.cached_count = 0
    
    # RAG retrievals tracking
    if "rag_retrievals" not in st.session_state:
        st.session_state.rag_retrievals = []
    
    # Chatbot state for monitoring
    if "chatbot_state" not in st.session_state:
        st.session_state.chatbot_state = {}
    
    # RAG ready flag
    if "rag_ready" not in st.session_state:
        st.session_state.rag_ready = False
    
    # Settings with defaults
    if "settings" not in st.session_state:
        st.session_state.settings = {
            # Language - default English
            "language": "en",
            
            # LLM Model settings
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            
            # UI settings
            "debug_mode": False,
            "show_agent_thoughts": True,
        }


def get_current_language() -> str:
    """Get current language from settings."""
    return st.session_state.settings.get("language", "en")


def get_current_model() -> str:
    """Get current model from settings."""
    return st.session_state.settings.get("model", "gpt-4o-mini")


def get_current_provider() -> str:
    """Get current provider from settings."""
    return st.session_state.settings.get("provider", "openai")


def get_current_temperature() -> float:
    """Get current temperature from settings."""
    return st.session_state.settings.get("temperature", 0.3)


def update_settings(**kwargs):
    """Update settings."""
    for key, value in kwargs.items():
        st.session_state.settings[key] = value


def start_new_call():
    """Start a new call/conversation."""
    st.session_state.conversation_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.agent = None
    st.session_state.call_active = True
    st.session_state.call_start_time = datetime.now()
    st.session_state.call_ended = False
    
    # Reset monitoring
    st.session_state.llm_calls = []
    st.session_state.tool_calls = []
    st.session_state.total_tokens = 0
    st.session_state.total_cost = 0.0
    st.session_state.llm_call_count = 0
    st.session_state.average_latency = 0.0
    st.session_state.cached_count = 0
    st.session_state.rag_retrievals = []
    st.session_state.chatbot_state = {}


def end_call():
    """End current call."""
    st.session_state.call_active = False
    st.session_state.call_ended = True


def reset_session():
    """Full session reset."""
    st.session_state.conversation_id = None
    st.session_state.messages = []
    st.session_state.agent = None
    st.session_state.call_active = False
    st.session_state.call_start_time = None
    st.session_state.call_ended = False
    st.session_state.llm_calls = []
    st.session_state.tool_calls = []
    st.session_state.total_tokens = 0
    st.session_state.total_cost = 0.0
    st.session_state.llm_call_count = 0
    st.session_state.average_latency = 0.0
    st.session_state.cached_count = 0
    st.session_state.rag_retrievals = []
    st.session_state.chatbot_state = {}


def add_message(role: str, content: str, metadata: dict = None):
    """Add message to conversation history."""
    msg = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata or {},
    }
    st.session_state.messages.append(msg)
    return msg


def get_call_duration() -> str:
    """Get formatted call duration."""
    if not st.session_state.call_start_time:
        return "00:00"
    
    duration = datetime.now() - st.session_state.call_start_time
    minutes = int(duration.total_seconds() // 60)
    seconds = int(duration.total_seconds() % 60)
    return f"{minutes:02d}:{seconds:02d}"


def get_state_summary() -> dict:
    """Get summary of current agent state for display."""
    agent = st.session_state.get("agent")
    if not agent:
        return {}
    
    state = agent.state
    
    return {
        "customer_id": state.customer_id,
        "customer_name": state.customer_name,
        "customer_address": state.customer_address,
        "turn_count": state.turn_count,
        "is_complete": state.is_complete,
    }


def log_rag_retrieval(query: str, results: list):
    """Log RAG retrieval for monitoring."""
    st.session_state.rag_retrievals.append({
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "results_count": len(results),
        "results": results[:5],  # Keep top 5
    })
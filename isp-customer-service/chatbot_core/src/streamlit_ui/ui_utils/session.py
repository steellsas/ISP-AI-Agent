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
    
    # Settings
    if "settings" not in st.session_state:
        st.session_state.settings = {
            "language": "lt",
            "debug_mode": False,
            "show_agent_thoughts": True,
        }


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

"""
Session State Management for Streamlit UI
"""

import streamlit as st
import uuid
from datetime import datetime
from typing import Any


def init_session():
    """Initialize all session state variables."""

    # Conversation state
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None

    if "phone_number" not in st.session_state:
        st.session_state.phone_number = "+37061234567"

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "chatbot_state" not in st.session_state:
        st.session_state.chatbot_state = None

    if "config" not in st.session_state:
        st.session_state.config = None

    # Call state
    if "call_active" not in st.session_state:
        st.session_state.call_active = False

    if "call_start_time" not in st.session_state:
        st.session_state.call_start_time = None

    if "call_ended" not in st.session_state:
        st.session_state.call_ended = False

    # Monitoring data
    if "token_usage" not in st.session_state:
        st.session_state.token_usage = {"input": 0, "output": 0, "total": 0}

    if "llm_calls" not in st.session_state:
        st.session_state.llm_calls = []

    if "rag_documents" not in st.session_state:
        st.session_state.rag_documents = []

    if "node_history" not in st.session_state:
        st.session_state.node_history = []

    # Settings
    if "settings" not in st.session_state:
        st.session_state.settings = {
            "model": "gpt-4o-mini",
            "language": "lt",
            "debug_mode": False,
            "show_agent_thoughts": True,
        }


def start_new_call():
    """Start a new call/conversation."""
    st.session_state.conversation_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.chatbot_state = None
    st.session_state.call_active = True
    st.session_state.call_start_time = datetime.now()
    st.session_state.call_ended = False

    # Reset monitoring
    st.session_state.token_usage = {"input": 0, "output": 0, "total": 0}
    st.session_state.llm_calls = []
    st.session_state.rag_documents = []
    st.session_state.node_history = []


def end_call():
    """End current call."""
    st.session_state.call_active = False
    st.session_state.call_ended = True


def reset_session():
    """Full session reset."""
    st.session_state.conversation_id = None
    st.session_state.messages = []
    st.session_state.chatbot_state = None
    st.session_state.config = None
    st.session_state.call_active = False
    st.session_state.call_start_time = None
    st.session_state.call_ended = False
    st.session_state.token_usage = {"input": 0, "output": 0, "total": 0}
    st.session_state.llm_calls = []
    st.session_state.rag_documents = []
    st.session_state.node_history = []


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


def update_token_usage(input_tokens: int, output_tokens: int):
    """Update token usage counters."""
    st.session_state.token_usage["input"] += input_tokens
    st.session_state.token_usage["output"] += output_tokens
    st.session_state.token_usage["total"] = (
        st.session_state.token_usage["input"] + st.session_state.token_usage["output"]
    )


def add_llm_call(node: str, model: str, tokens: int, duration_ms: int):
    """Log an LLM call for monitoring."""
    st.session_state.llm_calls.append(
        {
            "timestamp": datetime.now().isoformat(),
            "node": node,
            "model": model,
            "tokens": tokens,
            "duration_ms": duration_ms,
        }
    )


def add_rag_document(doc_id: str, title: str, score: float):
    """Log a RAG document retrieval."""
    st.session_state.rag_documents.append(
        {"timestamp": datetime.now().isoformat(), "doc_id": doc_id, "title": title, "score": score}
    )


def add_node_transition(from_node: str, to_node: str, reason: str = None):
    """Log node transition for graph visualization."""
    st.session_state.node_history.append(
        {
            "timestamp": datetime.now().isoformat(),
            "from": from_node,
            "to": to_node,
            "reason": reason,
        }
    )


def get_state_summary() -> dict:
    """Get summary of current chatbot state for display."""
    state = st.session_state.chatbot_state
    if not state:
        return {}

    return {
        "current_node": state.get("current_node", "-"),
        "customer_id": state.get("customer_id"),
        "customer_name": state.get("customer_name"),
        "problem_type": state.get("problem_type"),
        "problem_description": state.get("problem_description"),
        "problem_context": state.get("problem_context", {}),
        "address_confirmed": state.get("address_confirmed", False),
        "diagnostics_completed": state.get("diagnostics_completed", False),
        "problem_resolved": state.get("problem_resolved", False),
        "troubleshooting_needs_escalation": state.get("troubleshooting_needs_escalation", False),
        "ticket_id": state.get("ticket_id"),
        "ticket_type": state.get("ticket_type"),
        "conversation_ended": state.get("conversation_ended", False),
        "provider_issue_informed": state.get("provider_issue_informed", False),
    }

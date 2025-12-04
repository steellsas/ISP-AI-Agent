"""
Bridge between Streamlit UI and Chatbot Core
Handles all communication with the LangGraph workflow
"""

import streamlit as st
from typing import Tuple, Optional
import time
from datetime import datetime

# These imports will work when file is in chatbot_core/src/ui/streamlit_ui/
# and src is in sys.path
try:
    from graph.graph import get_app
    from graph.state import create_initial_state, add_message

    CHATBOT_AVAILABLE = True
except ImportError as e:
    CHATBOT_AVAILABLE = False
    IMPORT_ERROR = str(e)


def _on_llm_call(data: dict):
    """Callback for LLM calls - store in session state."""
    if "llm_calls" not in st.session_state:
        st.session_state.llm_calls = []

    st.session_state.llm_calls.append(
        {
            **data,
            "timestamp": datetime.now().isoformat(),
        }
    )

    # Update totals
    if "total_tokens" not in st.session_state:
        st.session_state.total_tokens = 0
    if "total_cost" not in st.session_state:
        st.session_state.total_cost = 0.0

    st.session_state.total_tokens += data.get("input_tokens", 0) + data.get("output_tokens", 0)
    st.session_state.total_cost += data.get("cost", 0)


def _on_rag_retrieval(data: dict):
    """Callback for RAG retrievals - store in session state."""
    if "rag_retrievals" not in st.session_state:
        st.session_state.rag_retrievals = []

    st.session_state.rag_retrievals.append(
        {
            **data,
            "timestamp": datetime.now().isoformat(),
        }
    )


def check_chatbot_available() -> Tuple[bool, str]:
    """Check if chatbot core is available."""
    if CHATBOT_AVAILABLE:
        return True, "Chatbot connected"
    return False, f"Import error: {IMPORT_ERROR}"


@st.cache_resource
def get_cached_app():
    """Get cached LangGraph app instance."""
    if not CHATBOT_AVAILABLE:
        return None
    return get_app()


def start_conversation(phone_number: str) -> dict:
    """
    Start a new conversation and get initial greeting.

    Returns:
        Result state from graph invocation

    """
    # Reset stats for new conversation
    st.session_state.llm_calls = []
    st.session_state.rag_retrievals = []
    st.session_state.total_tokens = 0
    st.session_state.total_cost = 0.0

    # Register callbacks
    try:
        from src.services.llm.client import register_stats_callback
        from src.rag.retriever import register_rag_callback

        register_stats_callback(_on_llm_call)
        register_rag_callback(_on_rag_retrieval)
    except ImportError as e:
        print(f"Warning: Could not register callbacks: {e}")

    app = get_cached_app()
    if not app:
        return {"error": "Chatbot not available"}

    conversation_id = st.session_state.conversation_id
    config = {"configurable": {"thread_id": conversation_id}}

    # Store config in session
    st.session_state.config = config

    try:
        from src.locales import get_language as get_ui_language

        ui_language = get_ui_language()
    except ImportError:
        ui_language = "lt"

    # Create initial state
    initial_state = create_initial_state(
        conversation_id=conversation_id, phone_number=phone_number, language=ui_language
    )

    # Invoke graph
    start_time = time.time()
    result = app.invoke(initial_state, config)
    duration_ms = int((time.time() - start_time) * 1000)

    # Store in session
    st.session_state.chatbot_state = result

    # Log node transition
    if "current_node" in result:
        from ui_utils.session import add_node_transition

        add_node_transition("START", result.get("current_node", "unknown"))

    return result


def send_message(user_input: str) -> dict:
    """
    Send user message and get response.

    Args:
        user_input: User's message text

    Returns:
        Updated state from graph invocation
    """
    app = get_cached_app()
    if not app:
        return {"error": "Chatbot not available"}

    config = st.session_state.config
    if not config:
        return {"error": "No active conversation"}

    # Track previous node for transition logging
    prev_node = (
        st.session_state.chatbot_state.get("current_node")
        if st.session_state.chatbot_state
        else None
    )

    # Create user message
    user_message = add_message(role="user", content=user_input, node="user_input")

    # Invoke with new message
    start_time = time.time()
    result = app.invoke({"messages": [user_message]}, config)
    duration_ms = int((time.time() - start_time) * 1000)

    # Update session state
    st.session_state.chatbot_state = result

    # Log node transition if changed
    current_node = result.get("current_node")
    if current_node and current_node != prev_node:
        from ui_utils.session import add_node_transition

        add_node_transition(prev_node or "unknown", current_node)

    return result


def get_new_assistant_messages(result: dict, last_count: int) -> list:
    """
    Extract new assistant messages from result.

    Args:
        result: Graph invocation result
        last_count: Previous message count

    Returns:
        List of new assistant message contents
    """
    all_messages = result.get("messages", [])
    new_messages = all_messages[last_count:]

    assistant_messages = []
    for msg in new_messages:
        if msg.get("role") == "assistant":
            assistant_messages.append(msg.get("content", ""))

    return assistant_messages


def is_conversation_ended(result: dict) -> Tuple[bool, Optional[str]]:
    """
    Check if conversation has ended and why.

    Returns:
        Tuple of (ended: bool, reason: str or None)
    """
    if result.get("conversation_ended"):
        return True, "conversation_ended"

    if result.get("provider_issue_informed"):
        return True, "provider_issue"

    if result.get("problem_resolved"):
        return True, "resolved"

    if result.get("troubleshooting_needs_escalation"):
        return True, "escalated"

    if result.get("address_search_successful") is False:
        return True, "customer_not_found"

    return False, None


def get_agent_decision_info(result: dict) -> dict:
    """
    Extract information about agent's decision making for display.

    Returns:
        Dict with decision-related info
    """
    return {
        "current_node": result.get("current_node", "-"),
        "problem_type": result.get("problem_type"),
        "problem_context": result.get("problem_context", {}),
        "context_score": result.get("problem_context", {}).get("context_score", 0),
        "troubleshooting_scenario": result.get("troubleshooting_scenario_id"),
        "troubleshooting_step": result.get("troubleshooting_current_step"),
        "diagnostic_results": result.get("diagnostic_results", {}),
    }


def get_graph_image() -> bytes | None:
    """Get graph visualization as PNG bytes."""
    try:
        app = get_cached_app()
        if not app:
            return None
        return app.get_graph().draw_mermaid_png()
    except Exception as e:
        print(f"Error generating graph: {e}")
        return None

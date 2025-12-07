"""
Bridge between Streamlit UI and ReAct Agent
Handles all communication with the agent
"""

import streamlit as st
from typing import Tuple, Optional, List
import time
from datetime import datetime
import sys
from pathlib import Path

# Add paths for imports
_ui_dir = Path(__file__).resolve().parent.parent  # streamlit_ui
_src_dir = _ui_dir.parent  # src
_chatbot_core = _src_dir.parent  # chatbot_core

if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# Try to import ReactAgent
try:
    from agent.react_agent import ReactAgent
    AGENT_AVAILABLE = True
    IMPORT_ERROR = None
except ImportError as e:
    AGENT_AVAILABLE = False
    IMPORT_ERROR = str(e)

# Try to import LLM stats
try:
    from services.llm.stats import get_session_stats, reset_session_stats
    from services.llm.client import register_stats_callback, unregister_stats_callback
    LLM_STATS_AVAILABLE = True
except ImportError:
    LLM_STATS_AVAILABLE = False


def _llm_stats_callback(data: dict):
    """Callback to update session_state with LLM call data."""
    if "total_tokens" not in st.session_state:
        st.session_state.total_tokens = 0
    if "total_cost" not in st.session_state:
        st.session_state.total_cost = 0.0
    if "llm_call_count" not in st.session_state:
        st.session_state.llm_call_count = 0
    if "average_latency" not in st.session_state:
        st.session_state.average_latency = 0.0
    if "cached_count" not in st.session_state:
        st.session_state.cached_count = 0
    
    # Update stats from callback data
    if data.get("success", True):
        input_tokens = data.get("input_tokens", 0)
        output_tokens = data.get("output_tokens", 0)
        cost = data.get("cost", 0)
        latency = data.get("latency_ms", 0)
        cached = data.get("cached", False)
        
        st.session_state.total_tokens += (input_tokens + output_tokens)
        st.session_state.total_cost += cost
        st.session_state.llm_call_count += 1
        st.session_state.average_latency += latency
        if cached:
            st.session_state.cached_count += 1


def _register_llm_callback():
    """Register the LLM stats callback."""
    if LLM_STATS_AVAILABLE:
        try:
            register_stats_callback(_llm_stats_callback)
        except Exception as e:
            print(f"Failed to register LLM callback: {e}")


def check_chatbot_available() -> Tuple[bool, str]:
    """Check if chatbot/agent is available."""
    if AGENT_AVAILABLE:
        return True, "Agent connected"
    return False, f"Import error: {IMPORT_ERROR}"


def start_conversation(phone_number: str, language: str = "en") -> dict:
    """
    Start a new conversation with the agent.
    
    Args:
        phone_number: Customer's phone number
        language: Language code ("lt" or "en")
    
    Returns:
        Result dict with initial greeting
    """
    if not AGENT_AVAILABLE:
        return {"error": "Agent not available", "messages": []}
    
    # Reset stats for new conversation
    st.session_state.llm_calls = []
    st.session_state.tool_calls = []
    st.session_state.total_tokens = 0
    st.session_state.total_cost = 0.0
    st.session_state.llm_call_count = 0
    st.session_state.average_latency = 0.0
    st.session_state.cached_count = 0
    st.session_state.rag_retrievals = []
    
    # Reset LLM session stats
    if LLM_STATS_AVAILABLE:
        reset_session_stats()
        _register_llm_callback()
    
    try:
        # Get model settings from session_state
        settings = st.session_state.get("settings", {})
        model = settings.get("model", "gpt-4o-mini")
        temperature = settings.get("temperature", 0.3)
        
        # Create config with all settings
        from agent.config import create_config
        config = create_config(
            language=language,
            model=model,
            temperature=temperature,
        )
        
        # Create new agent instance with config
        agent = ReactAgent(
            caller_phone=phone_number,
            language=language,
            config=config,
        )
        
        # Store agent in session
        st.session_state.agent = agent
        
        # Run agent to get initial greeting
        start_time = time.time()
        
        # First turn - agent should greet (no user input)
        response = agent.run_until_response()
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Extract response
        messages = []
        if response:
            messages.append({
                "role": "assistant",
                "content": response
            })
        
        # Build state info
        state_info = _extract_state_info(agent)
        
        # Log the call
        _log_agent_turn(agent, duration_ms)
        
        # Update token stats from LLM service
        _update_token_stats()
        
        return {
            "success": True,
            "messages": messages,
            "state": state_info,
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "messages": [],
        }


def send_message(user_input: str) -> dict:
    """
    Send user message to agent and get response.
    
    Args:
        user_input: User's message text
    
    Returns:
        Result dict with agent response
    """
    if not AGENT_AVAILABLE:
        return {"error": "Agent not available"}
    
    agent = st.session_state.get("agent")
    if not agent:
        return {"error": "No active conversation"}
    
    try:
        start_time = time.time()
        
        # Run agent with user input
        response = agent.run_until_response(user_input)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Extract response
        messages = []
        if response:
            messages.append({
                "role": "assistant",
                "content": response
            })
        
        # Build state info
        state_info = _extract_state_info(agent)
        
        # Log the call
        _log_agent_turn(agent, duration_ms)
        
        # Update token stats from LLM service
        _update_token_stats()
        
        return {
            "success": True,
            "messages": messages,
            "state": state_info,
            "is_complete": agent.state.is_complete,
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def _extract_state_info(agent: "ReactAgent") -> dict:
    """Extract state information from agent for display."""
    state = agent.state
    
    return {
        "customer_id": state.customer_id,
        "customer_name": state.customer_name,
        "customer_address": state.customer_address,
        "is_complete": state.is_complete,
        "turn_count": state.turn_count,
    }


def _update_token_stats():
    """Update session token stats from agent."""
    agent = st.session_state.get("agent")
    if not agent:
        return
    
    try:
        # Get stats from agent
        stats = agent.get_stats()
        st.session_state.llm_call_count = stats.get("total_calls", 0)
        st.session_state.total_tokens = stats.get("total_tokens", 0)
        st.session_state.total_cost = stats.get("total_cost", 0.0)
        st.session_state.average_latency = stats.get("average_latency_ms", 0.0)
        st.session_state.cached_count = stats.get("cached_calls", 0)
    except Exception as e:
        print(f"Error updating token stats: {e}")


def get_llm_stats() -> dict:
    """Get current LLM statistics from session_state."""
    return {
        "total_calls": st.session_state.get("llm_call_count", 0),
        "total_tokens": st.session_state.get("total_tokens", 0),
        "total_cost": st.session_state.get("total_cost", 0.0),
        "average_latency_ms": st.session_state.get("average_latency", 0.0),
        "cached_calls": st.session_state.get("cached_count", 0),
    }


def _log_agent_turn(agent: "ReactAgent", duration_ms: int):
    """Log agent turn for monitoring - extract ALL tool calls from messages."""
    import re
    import json as json_module
    
    # Initialize if needed
    if "llm_calls" not in st.session_state:
        st.session_state.llm_calls = []
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []
    
    # Get all messages and find tool calls
    messages = agent.state.messages
    
    # Track which tools we've already logged (by content hash)
    logged_tools = set()
    if st.session_state.tool_calls:
        for tc in st.session_state.tool_calls:
            logged_tools.add(f"{tc.get('tool')}_{tc.get('timestamp', '')[:16]}")
    
    # Parse all assistant messages for tool calls
    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            
            # Extract Action
            action_match = re.search(r"Action:\s*(\w+)", content)
            if action_match:
                action = action_match.group(1).strip()
                
                # Skip respond/finish - not tools
                if action in ["respond", "finish"]:
                    continue
                
                # Extract Action Input
                action_input = {}
                input_match = re.search(r"Action Input:\s*(\{.+?\})", content, re.DOTALL)
                if input_match:
                    try:
                        action_input = json_module.loads(input_match.group(1))
                    except:
                        pass
                
                # Create unique key to avoid duplicates
                tool_key = f"{action}_{datetime.now().isoformat()[:16]}"
                
                if tool_key not in logged_tools:
                    st.session_state.tool_calls.append({
                        "timestamp": datetime.now().isoformat(),
                        "tool": action,
                        "input": action_input,
                        "duration_ms": duration_ms,
                    })
                    logged_tools.add(tool_key)
    
    # Log LLM call summary
    last_thought = ""
    last_action = ""
    
    # Get last assistant message
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            thought_match = re.search(r"Thought:\s*(.+?)(?=\nAction:|\Z)", content, re.DOTALL)
            if thought_match:
                last_thought = thought_match.group(1).strip()
            action_match = re.search(r"Action:\s*(\w+)", content)
            if action_match:
                last_action = action_match.group(1).strip()
            break
    
    # Get model from agent config
    model = "unknown"
    try:
        model = agent.config.model
    except:
        pass
    
    st.session_state.llm_calls.append({
        "timestamp": datetime.now().isoformat(),
        "thought": last_thought[:200] if last_thought else "",
        "action": last_action,
        "duration_ms": duration_ms,
        "model": model,
    })


def get_new_assistant_messages(result: dict, last_count: int = 0) -> List[str]:
    """
    Extract new assistant messages from result.
    
    Args:
        result: Agent result dict
        last_count: Previous message count (unused, for compatibility)
    
    Returns:
        List of new assistant message contents
    """
    messages = result.get("messages", [])
    return [msg["content"] for msg in messages if msg.get("role") == "assistant"]


def is_conversation_ended(result: dict) -> Tuple[bool, Optional[str]]:
    """
    Check if conversation has ended.
    
    Returns:
        Tuple of (ended: bool, reason: str or None)
    """
    if result.get("is_complete"):
        return True, "conversation_ended"
    
    state = result.get("state", {})
    if state.get("is_complete"):
        return True, "agent_finished"
    
    return False, None


def get_agent_decision_info(result: dict = None) -> dict:
    """
    Get information about agent's decision making for display.
    
    Returns:
        Dict with decision-related info
    """
    agent = st.session_state.get("agent")
    if not agent:
        return {}
    
    state = agent.state
    
    # Get last few observations
    recent_observations = state.observations[-3:] if state.observations else []
    
    return {
        "customer_id": state.customer_id,
        "customer_name": state.customer_name,
        "customer_address": state.customer_address,
        "turn_count": state.turn_count,
        "max_turns": state.max_turns,
        "is_complete": state.is_complete,
        "recent_observations": recent_observations,
    }


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
        "observations_count": len(state.observations),
    }
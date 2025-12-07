"""
Monitoring Tab Component
Real-time statistics, token usage, costs, and debugging
"""

import streamlit as st
import sys
from pathlib import Path

# Fix imports
_ui_dir = Path(__file__).resolve().parent.parent  # components -> streamlit_ui
_src_dir = _ui_dir.parent  # src

if str(_ui_dir) not in sys.path:
    sys.path.insert(0, str(_ui_dir))
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from ui_utils.session import get_state_summary


def render_monitor_tab():
    """Render the monitoring tab with real-time stats."""
    
    st.markdown("## 📊 Monitoring")
    
    # Top metrics row - real-time from LLM service
    render_metrics_row()
    
    st.markdown("---")
    
    # Two columns: LLM Calls + Tool Calls
    col_llm, col_tools = st.columns([1, 1])
    
    with col_llm:
        render_llm_calls_section()
    
    with col_tools:
        render_tool_calls_section()
    
    st.markdown("---")
    
    # Bottom section: Debug only
    render_debug_section()


def render_metrics_row():
    """Render top metrics from session_state (real-time via callbacks)."""
    
    # Get stats from session_state (updated by agent.get_stats())
    total_calls = st.session_state.get("llm_call_count", 0)
    total_tokens = st.session_state.get("total_tokens", 0)
    total_cost = st.session_state.get("total_cost", 0.0)
    avg_latency = st.session_state.get("average_latency", 0.0)
    cached_calls = st.session_state.get("cached_count", 0)
    
    # Display metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("🧠 LLM Calls", total_calls)
    
    with col2:
        st.metric("📝 Tokens", f"{total_tokens:,}")
    
    with col3:
        st.metric("💰 Cost", f"${total_cost:.4f}")
    
    with col4:
        st.metric("⚡ Avg Latency", f"{avg_latency:.0f}ms")
    
    with col5:
        st.metric("📦 Cached", cached_calls)


def render_llm_calls_section():
    """Render LLM calls log with model and cost info."""
    
    st.markdown("### 🧠 LLM Calls")
    
    # Summary stats
    total_calls = st.session_state.get("llm_call_count", 0)
    total_tokens = st.session_state.get("total_tokens", 0)
    total_cost = st.session_state.get("total_cost", 0.0)
    
    if total_calls > 0:
        st.markdown(f"**Summary:** {total_calls} calls, {total_tokens:,} tokens, ${total_cost:.4f}")
        st.markdown("---")
    
    # Recent calls from session state
    llm_calls = st.session_state.get("llm_calls", [])
    
    if not llm_calls:
        st.info("No LLM calls yet. Start a conversation!")
        return
    
    st.markdown("**Recent Calls:**")
    
    for call in reversed(llm_calls[-10:]):
        model = call.get("model", "unknown")
        action = call.get("action", "-")
        duration = call.get("duration_ms", 0)
        thought = call.get("thought", "")[:80]
        
        # Icon based on action
        icon = "💬" if action == "respond" else "🔧" if action not in ["respond", "finish"] else "✅"
        
        with st.expander(f"{icon} `{action}` - {model} ({duration}ms)"):
            if thought:
                st.markdown(f"**Thought:** {thought}...")
            st.caption(f"Time: {call.get('timestamp', '')[:19]}")


def render_tool_calls_section():
    """Render tool calls log."""
    
    st.markdown("### 🔧 Tool Calls")
    
    tool_calls = st.session_state.get("tool_calls", [])
    
    if not tool_calls:
        st.info("No tool calls yet.")
        return
    
    # Tool call icons
    tool_icons = {
        "find_customer": "🔍",
        "check_network_status": "📡",
        "check_outages": "⚠️",
        "run_ping_test": "📶",
        "search_knowledge": "📚",
        "create_ticket": "🎫",
    }
    
    # Summary
    tool_counts = {}
    for call in tool_calls:
        tool = call.get("tool", "unknown")
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
    
    st.markdown("**Summary:**")
    for tool, count in tool_counts.items():
        icon = tool_icons.get(tool, "🔧")
        st.markdown(f"• {icon} `{tool}`: {count}")
    
    st.markdown("---")
    st.markdown("**Recent Calls:**")
    
    for call in reversed(tool_calls[-8:]):
        tool_name = call.get("tool", "unknown")
        tool_input = call.get("input", {})
        duration = call.get("duration_ms", 0)
        icon = tool_icons.get(tool_name, "🔧")
        
        # Format input summary
        input_summary = ""
        if tool_input:
            if "phone" in tool_input:
                input_summary = f"phone={tool_input['phone']}"
            elif "query" in tool_input:
                input_summary = f"query=\"{tool_input['query'][:25]}...\""
            elif "customer_id" in tool_input:
                input_summary = f"id={tool_input['customer_id']}"
        
        with st.expander(f"{icon} `{tool_name}` {input_summary}"):
            st.json(tool_input)
            st.caption(f"Duration: {duration}ms")


def render_debug_section():
    """Render debug information."""
    
    st.markdown("### 🐛 Debug")
    
    # Current settings
    with st.expander("Current Settings"):
        st.json(st.session_state.settings)
    
    # Agent state
    state = get_state_summary()
    if state:
        with st.expander("Agent State"):
            st.json(state)
    
    # LLM Stats from session_state
    with st.expander("LLM Stats"):
        stats = {
            "total_calls": st.session_state.get("llm_call_count", 0),
            "total_tokens": st.session_state.get("total_tokens", 0),
            "total_cost": st.session_state.get("total_cost", 0.0),
            "average_latency_ms": st.session_state.get("average_latency", 0.0),
            "cached_calls": st.session_state.get("cached_count", 0),
        }
        st.json(stats)
    
    # Message count
    msg_count = len(st.session_state.get("messages", []))
    st.metric("Messages in conversation", msg_count)
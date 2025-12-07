"""
Call Interface Component
Phone call simulation UI with agent status panel
"""

import sys
from pathlib import Path

_streamlit_ui = Path(__file__).resolve().parent.parent  # components -> streamlit_ui
_src_dir = _streamlit_ui.parent  # src

if str(_streamlit_ui) not in sys.path:
    sys.path.insert(0, str(_streamlit_ui))
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import streamlit as st
from datetime import datetime

from ui_utils.session import (
    start_new_call,
    end_call,
    get_call_duration,
    get_state_summary,
    add_message as session_add_message,
    reset_session,
    get_current_language,
)
from ui_utils.chatbot_bridge import (
    check_chatbot_available,
    start_conversation,
    send_message,
    get_new_assistant_messages,
    is_conversation_ended,
    get_agent_decision_info,
    get_llm_stats,
)


def render_call_tab():
    """Render the main call interface tab."""
    
    available, message = check_chatbot_available()
    if not available:
        st.error(f"❌ Agent unavailable: {message}")
        st.info("Check that all dependencies are installed correctly.")
        return
    
    col_phone, col_agent = st.columns([1, 1])
    
    with col_phone:
        render_phone_ui()
    
    with col_agent:
        render_agent_panel()


def render_phone_ui():
    """Render the phone call interface."""
    
    st.markdown("### 📞 Phone Simulation")
    
    with st.container():
        # If no active call - show dial screen
        if not st.session_state.call_active and not st.session_state.call_ended:
            render_dial_screen()
        
        # Active call
        elif st.session_state.call_active:
            render_active_call()
        
        # Call ended
        else:
            render_call_ended()


def render_dial_screen():
    """Render the initial dial screen."""
    
    # Get current language for display
    lang = st.session_state.settings.get("language", "en")
    lang_display = "🇬🇧 English" if lang == "en" else "🇱🇹 Lietuvių"
    
    st.markdown(
        f"""
        <div style="text-align: center; padding: 40px 20px;">
            <div style="font-size: 48px; margin-bottom: 20px;">📞</div>
            <div style="font-size: 18px; color: #666; margin-bottom: 10px;">
                ISP Customer Service
            </div>
            <div style="font-size: 14px; color: #999; margin-bottom: 30px;">
                Language: {lang_display}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # Phone number input
    phone = st.text_input(
        "Phone Number",
        value=st.session_state.phone_number,
        placeholder="+37060012345",
        key="phone_input",
    )
    st.session_state.phone_number = phone
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("📞 Start Call", type="primary", use_container_width=True):
            start_new_call()
            
            # Get language from settings
            language = get_current_language()
            
            with st.spinner("Connecting..."):
                result = start_conversation(
                    st.session_state.phone_number,
                    language=language,
                )
                
                if "error" in result:
                    st.error(f"Error: {result['error']}")
                    end_call()
                else:
                    # Add greeting messages to display
                    for msg in result.get("messages", []):
                        if msg["role"] == "assistant":
                            session_add_message("assistant", msg["content"])
            
            st.rerun()


def render_active_call():
    """Render active call interface."""
    
    # Call header
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            f"""
            <div style="text-align: center; padding: 10px; background: #e8f5e9; border-radius: 10px; margin-bottom: 15px;">
                <div style="color: #2e7d32; font-weight: bold;">🟢 Active Call</div>
                <div style="font-size: 24px; font-weight: bold;">{get_call_duration()}</div>
                <div style="color: #666;">{st.session_state.phone_number}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    # Messages container
    messages_container = st.container(height=400)
    
    with messages_container:
        for msg in st.session_state.messages:
            render_message(msg)
    
    # Input area
    st.markdown("---")
    
    col_input, col_end = st.columns([4, 1])
    
    with col_input:
        user_input = st.chat_input("Type your message...", key="chat_input")
    
    with col_end:
        if st.button("🔴 End", help="End call", type="secondary"):
            end_call()
            st.rerun()
    
    # Process user input
    if user_input:
        # Add user message to display
        session_add_message("user", user_input)
        
        # Send to agent
        with st.spinner(""):
            result = send_message(user_input)
        
        if "error" in result:
            st.error(f"Error: {result['error']}")
        else:
            # Get assistant response
            for msg in result.get("messages", []):
                if msg["role"] == "assistant":
                    session_add_message("assistant", msg["content"])
            
            # Check if conversation ended
            ended, reason = is_conversation_ended(result)
            if ended:
                end_call()
        
        st.rerun()


def render_call_ended():
    """Render call ended screen."""
    
    state = get_state_summary()
    llm_stats = get_llm_stats()
    
    st.markdown(
        f"""
        <div style="text-align: center; padding: 40px 20px;">
            <div style="font-size: 48px; margin-bottom: 20px;">📴</div>
            <div style="font-size: 18px; color: #666; margin-bottom: 10px;">
                Call Ended
            </div>
            <div style="font-size: 14px; color: #999;">
                Duration: {get_call_duration()}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("🧠 LLM Calls", llm_stats.get("total_calls", 0))
    
    with col2:
        st.metric("📝 Tokens", f"{llm_stats.get('total_tokens', 0):,}")
    
    with col3:
        st.metric("💰 Cost", f"${llm_stats.get('total_cost', 0):.4f}")
    
    # Customer info
    if state.get("customer_name"):
        st.info(f"👤 Customer: {state['customer_name']}")
    
    if state.get("is_complete"):
        st.success("✅ Conversation completed successfully")
    
    # New call button
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("📞 New Call", type="primary", use_container_width=True):
            reset_session()
            st.rerun()
    
    # Show conversation log
    with st.expander("💬 Conversation History"):
        for msg in st.session_state.messages:
            role_icon = "🤖" if msg["role"] == "assistant" else "👤"
            st.markdown(f"**{role_icon}** {msg['content']}")


def render_message(msg: dict):
    """Render a single chat message."""
    
    if msg["role"] == "assistant":
        with st.chat_message("assistant", avatar="🤖"):
            st.write(msg["content"])
    else:
        with st.chat_message("user", avatar="👤"):
            st.write(msg["content"])


def render_agent_panel():
    """Render the agent status/decision panel."""
    
    st.markdown("### 🤖 Agent Status")
    
    if not st.session_state.get("agent"):
        st.info("Start a call to see agent status")
        return
    
    decision_info = get_agent_decision_info()
    state = get_state_summary()
    llm_stats = get_llm_stats()
    
    # Turn counter
    turn_count = decision_info.get("turn_count", 0)
    max_turns = decision_info.get("max_turns", 20)
    
    st.progress(turn_count / max_turns, text=f"Turn: {turn_count}/{max_turns}")
    
    # Quick stats
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Tokens", f"{llm_stats.get('total_tokens', 0):,}")
    with col2:
        st.metric("Cost", f"${llm_stats.get('total_cost', 0):.4f}")
    
    # Customer info
    st.markdown("#### 👤 Customer")
    
    customer_id = state.get("customer_id")
    customer_name = state.get("customer_name")
    customer_address = state.get("customer_address")
    
    if customer_id and customer_address:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Name", customer_name or "Unknown")
        with col2:
            st.metric("ID", customer_id)
        
        st.markdown(f"📍 **Address:** {customer_address}")
    else:
        st.caption("Waiting for customer identification...")
    
    # Tool calls
    st.markdown("#### 🔧 Tool Calls")
    
    tool_calls = st.session_state.get("tool_calls", [])
    
    if tool_calls:
        tool_icons = {
            "find_customer": "🔍",
            "check_network_status": "📡",
            "check_outages": "⚠️",
            "run_ping_test": "📶",
            "search_knowledge": "📚",
            "create_ticket": "🎫",
        }
        
        for call in tool_calls[-5:]:  # Last 5 calls
            tool_name = call.get("tool", "unknown")
            icon = tool_icons.get(tool_name, "🔧")
            
            # Input summary
            tool_input = call.get("input", {})
            input_summary = ""
            if tool_input:
                if "phone" in tool_input:
                    input_summary = f" ({tool_input['phone']})"
                elif "query" in tool_input:
                    input_summary = f" ({tool_input['query'][:25]}...)"
            
            st.markdown(f"{icon} `{tool_name}`{input_summary}")
    else:
        st.caption("No tool calls yet")
    
    # Recent thoughts (debug mode)
    if st.session_state.settings.get("show_agent_thoughts"):
        with st.expander("💭 Agent Thoughts"):
            llm_calls = st.session_state.get("llm_calls", [])
            
            if llm_calls:
                for call in llm_calls[-5:]:
                    thought = call.get("thought", "")
                    action = call.get("action", "")
                    
                    if thought:
                        st.markdown(f"**Thought:** {thought[:120]}...")
                    if action:
                        st.markdown(f"**Action:** `{action}`")
                    st.markdown("---")
            else:
                st.caption("No thoughts yet")

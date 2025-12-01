"""
Call Interface Component
Phone call simulation UI with agent status panel
"""
import sys
from pathlib import Path

# Add streamlit_ui to path for utils imports
_streamlit_ui = Path(__file__).resolve().parent.parent  # components -> streamlit_ui
print(f"DEBUG call_interface: _streamlit_ui = {_streamlit_ui}")
print(f"DEBUG call_interface: sys.path[:3] = {sys.path[:3]}")
if str(_streamlit_ui) not in sys.path:
    sys.path.insert(0, str(_streamlit_ui))

print(f"DEBUG call_interface: after insert sys.path[:3] = {sys.path[:3]}")

# Check if utils exists
import os
utils_path = _streamlit_ui / "ui_utils"
print(f"DEBUG: utils folder exists: {utils_path.exists()}")
print(f"DEBUG: utils contents: {list(utils_path.iterdir()) if utils_path.exists() else 'N/A'}")


import streamlit as st
from datetime import datetime

from ui_utils.session import (
    start_new_call, 
    end_call, 
    get_call_duration,
    get_state_summary,
    add_message as session_add_message
)
from ui_utils.chatbot_bridge import (
    check_chatbot_available,
    start_conversation,
    send_message,
    get_new_assistant_messages,
    is_conversation_ended,
    get_agent_decision_info
)

# Localization
try:
    from src.locales import t
    LOCALES_AVAILABLE = True
except ImportError:
    LOCALES_AVAILABLE = False
    def t(key, **kwargs):
        return key

def render_call_tab():
    """Render the main call interface tab."""
    
    available, message = check_chatbot_available()
    if not available:
        st.error(t("errors.chatbot_unavailable", message=message))
        st.info(t("errors.check_config"))
        return
    
    col_phone, col_agent = st.columns([1, 1])
    
    with col_phone:
        render_phone_ui()
    
    with col_agent:
        render_agent_panel()


def render_phone_ui():
    """Render the phone call interface."""
    
    st.markdown(f"### {t('call.phone_title')}")
    
    # Phone frame container
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
    
    st.markdown(f"""
    <div style="text-align: center; padding: 40px 20px;">
        <div style="font-size: 48px; margin-bottom: 20px;">📞</div>
        <div style="font-size: 18px; color: #666; margin-bottom: 30px;">
          {t('call.support_title')}
        </div
    </div>
    """, unsafe_allow_html=True)
    
    # Phone number input
    phone = st.text_input(
        t("call.phone_label"),
        value=st.session_state.phone_number,
        placeholder="+37061234567",
        key="phone_input"
    )
    st.session_state.phone_number = phone
    
    # Call button
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(t("call.call_button"), type="primary", use_container_width=True):
            start_new_call()
            
            with st.spinner(t("call.connecting")):
                result = start_conversation(st.session_state.phone_number)
                
                if "error" in result:
                    st.error(f"ERROR: {result['error']}")
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
        st.markdown(f"""
        <div style="text-align: center; padding: 10px; background: #e8f5e9; border-radius: 10px; margin-bottom: 15px;">
            <div style="color: #2e7d32; font-weight: bold;">{t('call.active_call')}</div>
            <div style="font-size: 24px; font-weight: bold;">{get_call_duration()}</div>
            <div style="color: #666;">{st.session_state.phone_number}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Messages container
    messages_container = st.container(height=350)
    
    with messages_container:
        for msg in st.session_state.messages:
            render_message(msg)
    
    # Check if ended by bot
    if st.session_state.chatbot_state:
        ended, reason = is_conversation_ended(st.session_state.chatbot_state)
        if ended:
            end_call()
            st.rerun()
    
    # Input area
    st.markdown("---")
    
    col_input, col_end = st.columns([4, 1])
    
    with col_input:
        user_input = st.chat_input(t("call.type_message"), key="chat_input")
    
    with col_end:
        if st.button("🔴", help=t("call.end_call_tooltip"), type="secondary"):
            end_call()
            st.rerun()
    
    # Process user input
    if user_input:
        # Add to display
        session_add_message("user", user_input)
        
        # Get message count before invocation
        prev_count = len(st.session_state.chatbot_state.get("messages", []))
        
        # Send to chatbot
        with st.spinner(""):
            result = send_message(user_input)
        
        if "error" in result:
            st.error(f"Error: {result['error']}")
        else:
            # Get new assistant messages
            new_messages = get_new_assistant_messages(result, prev_count)
            
            for content in new_messages:
                session_add_message("assistant", content)
        
        st.rerun()


def render_call_ended():
    """Render call ended screen."""
    
    # Get final state info
    state = get_state_summary()
    
    st.markdown(f"""
    <div style="text-align: center; padding: 40px 20px;">
        <div style="font-size: 48px; margin-bottom: 20px;">📴</div>
        <div style="font-size: 18px; color: #666; margin-bottom: 10px;">
           {t('call.call_ended')}
        </div>
        <div style="font-size: 14px; color: #999;">
           {t('call.call_duration')}: {get_call_duration()}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Summary
    if state.get("problem_resolved"):
        st.success(t("call.problem_resolved"))
    elif state.get("troubleshooting_needs_escalation"):
        st.warning(t("call.escalated"))
    elif state.get("ticket_id"):
        st.info(t("call.ticket_created", ticket_id=state.get('ticket_id')))
    elif state.get("provider_issue_informed"):
        st.info(t("call.provider_issue"))
        
    # New call button
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(t("call.new_call_button"), type="primary", use_container_width=True):
            from ui_utils.session import reset_session
            reset_session()
            st.rerun()
    
    # Show conversation log
    with st.expander(t("call.chat_history")):
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
    
    st.markdown(f"### {t('agent.title')}")
    # Show current model
    try:
        from src.services.llm.settings import get_settings
        current_model = get_settings().model
        st.caption(f"🤖 {t('agent.model')}: `{current_model}`")
    except:
        pass
    
    if not st.session_state.chatbot_state:
        st.info(t("agent.start_hint"))
        return
    
    decision_info = get_agent_decision_info(st.session_state.chatbot_state)
    state = get_state_summary()
    
    # Current node
    current_node = decision_info.get("current_node", "-")
    node_colors = {
        "greeting": "🟢",
        "identify_customer": "🔵",
        "problem_capture": "🟡",
        "diagnostics": "🟠",
        "troubleshooting": "🔧",
        "ticket_creation": "🎫",
        "closing": "✅",
        "end": "⬛"
    }
    node_icon = node_colors.get(current_node, "⚪")
    
    st.markdown(f"""
    <div style="background: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 15px;">
        <div style="font-size: 12px; color: #666; text-transform: uppercase;">Current Node</div>
        <div style="font-size: 20px; font-weight: bold;">{node_icon} {current_node}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Customer info
    st.markdown(f"#### {t('agent.customer')}")
    col1, col2 = st.columns(2)
    with col1:
        st.metric(t("agent.name"), state.get("customer_name") or "-")
    with col2:
        st.metric("ID", state.get("customer_id") or "-")
    
    # Problem info
    st.markdown(f"#### {t('agent.problem')}")
    
    problem_type = state.get("problem_type") or "-"
    problem_icons = {
        "internet": "🌐",
        "tv": "📺",
        "phone": "📱",
        "billing": "💳",
        "other": "❓"
    }
    problem_icon = problem_icons.get(problem_type, "")
    
    st.markdown(f"**{t('agent.type_label')}:** {problem_icon} {problem_type}")
    
    if state.get("problem_description"):
        st.markdown(f"**Problem Description:** {state['problem_description'][:100]}...")
    
    # Context score
    context = state.get("problem_context", {})
    score = context.get("context_score", 0)
    
    st.progress(score / 100, text=f"{t('agent.context_collected')}: {score}%")
    
    # Context details
    if context and any(v for k, v in context.items() if k != "context_score"):
        with st.expander(t("agent.extracted_info")):
            for key, value in context.items():
                if key != "context_score" and value is not None:
                    st.markdown(f"• **{key}:** {value}")
    
    # Troubleshooting info
    if decision_info.get("troubleshooting_scenario"):
        st.markdown(f"#### {t('agent.troubleshooting')}")
        st.markdown(f"**{t('agent.scenario')}:** {decision_info['troubleshooting_scenario']}")
        st.markdown(f"**{t('agent.step')}:** {decision_info['troubleshooting_step']}")
    
    # Status flags
    st.markdown(f"#### {t('agent.status')}")
    
    flags_col1, flags_col2 = st.columns(2)
    
    with flags_col1:
        if state.get("address_confirmed"):
            st.success(t("agent.address_confirmed"), icon="📍")
        if state.get("diagnostics_completed"):
            st.success(t("agent.diagnostics_done"), icon="🔍")
    
    with flags_col2:
        if state.get("problem_resolved"):
            st.success(t("agent.resolved"), icon="✅")
        if state.get("ticket_id"):
            st.info(f"Ticket: {state['ticket_id']}", icon="🎫")
    
    # Node history
    if st.session_state.node_history:
        with st.expander(t("agent.node_history")):
            for transition in reversed(st.session_state.node_history[-10:]):
                st.markdown(f"`{transition['from']}` → `{transition['to']}`")

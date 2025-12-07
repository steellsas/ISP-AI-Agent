"""
ISP Customer Service Chatbot - Streamlit UI
ReAct Agent Demo
"""

import streamlit as st
import sys
from pathlib import Path

# =============================================================================
# PATH SETUP
# =============================================================================

current_dir = Path(__file__).resolve().parent  # streamlit_ui/
src_dir = current_dir.parent  # src/
chatbot_core = src_dir.parent  # chatbot_core/

# Add paths for imports
sys.path.insert(0, str(current_dir))  # ui_utils, components
sys.path.insert(0, str(src_dir))  # agent, rag, services

from ui_utils.session import init_session

# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title="ISP Customer Service Demo",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# RAG PRELOAD (Background initialization)
# =============================================================================

@st.cache_resource
def init_rag_system():
    """Initialize RAG system once (cached)."""
    try:
        from rag import get_retriever
        
        retriever = get_retriever()
        success = retriever.load("production")
        
        if success:
            stats = retriever.get_statistics()
            print(f"✅ RAG loaded: {stats['total_documents']} documents")
            return True
        else:
            print("⚠️ RAG: Knowledge base not found")
            return False
            
    except ImportError as e:
        print(f"⚠️ RAG not available: {e}")
        return False
    except Exception as e:
        print(f"❌ RAG init error: {e}")
        return False


# =============================================================================
# CUSTOM CSS
# =============================================================================

st.markdown("""
<style>
    /* Chat container */
    .stChatMessage {
        padding: 10px 15px;
    }
    
    /* Phone simulation */
    .phone-header {
        text-align: center;
        padding: 10px;
        background: #e8f5e9;
        border-radius: 10px;
        margin-bottom: 15px;
    }
    
    /* Agent panel */
    .agent-panel {
        background: #f5f5f5;
        padding: 15px;
        border-radius: 10px;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# MAIN APP
# =============================================================================

def main():
    """Main app entry point."""
    
    # Initialize session state
    init_session()
    
    # Initialize RAG in background (cached - runs only once)
    rag_ready = init_rag_system()
    st.session_state.rag_ready = rag_ready
    
    # Header
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("📞 ISP Klientų Aptarnavimas")
        st.caption("ReAct Agent Demo")
    
    # Main tabs
    tab_call, tab_monitor, tab_settings = st.tabs([
        "📞 Skambutis",
        "📊 Monitoringas", 
        "⚙️ Nustatymai"
    ])
    
    with tab_call:
        render_call_tab()
    
    with tab_monitor:
        render_monitor_tab()
    
    with tab_settings:
        render_settings_tab()


def render_call_tab():
    """Render main call interface."""
    try:
        from components.call_interface import render_call_tab as _render_call
        _render_call()
    except ImportError as e:
        st.error(f"Failed to load call interface: {e}")


def render_monitor_tab():
    """Render monitoring dashboard."""
    st.markdown("### 📊 Sesijos statistika")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        llm_count = len(st.session_state.get("llm_calls", []))
        st.metric("LLM iškvietimai", llm_count)
    
    with col2:
        tool_count = len(st.session_state.get("tool_calls", []))
        st.metric("Įrankių iškvietimai", tool_count)
    
    with col3:
        msg_count = len(st.session_state.get("messages", []))
        st.metric("Žinutės", msg_count)
    
    # Tool calls log
    st.markdown("#### 🔧 Įrankių istorija")
    
    tool_calls = st.session_state.get("tool_calls", [])
    if tool_calls:
        for call in reversed(tool_calls):
            with st.expander(f"`{call['tool']}` - {call['timestamp'][:19]}"):
                st.json(call.get("input", {}))
    else:
        st.info("Dar nebuvo įrankių iškvietimų")
    
    # LLM calls log
    st.markdown("#### 🧠 LLM istorija")
    
    llm_calls = st.session_state.get("llm_calls", [])
    if llm_calls:
        for call in reversed(llm_calls[-10:]):
            thought = call.get("thought", "")[:100]
            action = call.get("action", "-")
            st.markdown(f"**{action}**: {thought}...")
    else:
        st.info("Dar nebuvo LLM iškvietimų")


def render_settings_tab():
    """Render settings panel."""
    st.markdown("### ⚙️ Nustatymai")
    
    # Debug mode
    debug = st.checkbox(
        "Rodyti agento mintis",
        value=st.session_state.settings.get("show_agent_thoughts", True),
        help="Rodyti agento 'Thought' žingsnius"
    )
    st.session_state.settings["show_agent_thoughts"] = debug
    
    # RAG status
    st.markdown("---")
    st.markdown("#### 📚 RAG Sistema")
    
    if st.session_state.get("rag_ready"):
        st.success("✅ Knowledge base užkrauta")
    else:
        st.warning("⚠️ Knowledge base nepasiekiama")
    
    # Reset button
    st.markdown("---")
    if st.button("🔄 Reset sesija", type="secondary"):
        from ui_utils.session import reset_session
        reset_session()
        st.rerun()


if __name__ == "__main__":
    main()

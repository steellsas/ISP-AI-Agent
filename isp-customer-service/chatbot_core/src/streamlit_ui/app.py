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
    
    /* Metrics styling */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
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
    
    # Header with current settings info
    render_header()
    
    # Main tabs
    tab_call, tab_monitor, tab_settings = st.tabs([
        "📞 Call",
        "📊 Monitoring", 
        "⚙️ Settings"
    ])
    
    with tab_call:
        render_call_tab()
    
    with tab_monitor:
        render_monitor_tab()
    
    with tab_settings:
        render_settings_tab()


def render_header():
    """Render header with title and current settings."""
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("📞 ISP Customer Service")
        st.caption("ReAct Agent Demo")
    
    # Show current settings in small text
    with col3:
        lang = st.session_state.settings.get("language", "en").upper()
        model = st.session_state.settings.get("model", "gpt-4o-mini")
        # Shorten model name for display
        model_short = model.split("/")[-1] if "/" in model else model
        
        st.markdown(
            f"""
            <div style="text-align: right; font-size: 12px; color: #666;">
                🌍 {lang} | 🤖 {model_short}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_call_tab():
    """Render main call interface."""
    try:
        from components.call_interface import render_call_tab as _render_call
        _render_call()
    except ImportError as e:
        st.error(f"Failed to load call interface: {e}")
        
        # Fallback simple interface
        st.markdown("### Phone Interface")
        st.text_input("Phone number", value=st.session_state.phone_number)
        if st.button("📞 Start Call"):
            st.info("Call interface not available")


def render_monitor_tab():
    """Render monitoring dashboard."""
    try:
        from components.monitoring import render_monitor_tab as _render_monitor
        _render_monitor()
    except ImportError as e:
        st.error(f"Failed to load monitoring: {e}")
        
        # Fallback simple metrics
        st.markdown("### Session Statistics")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            llm_count = len(st.session_state.get("llm_calls", []))
            st.metric("LLM Calls", llm_count)
        
        with col2:
            tool_count = len(st.session_state.get("tool_calls", []))
            st.metric("Tool Calls", tool_count)
        
        with col3:
            tokens = st.session_state.get("total_tokens", 0)
            st.metric("Tokens", f"{tokens:,}")


def render_settings_tab():
    """Render settings panel."""
    try:
        from components.settings import render_settings_tab as _render_settings
        _render_settings()
    except ImportError as e:
        st.error(f"Failed to load settings: {e}")
        
        # Fallback simple settings
        st.markdown("### Settings")
        
        # Language
        lang = st.selectbox(
            "Language",
            ["en", "lt"],
            index=0 if st.session_state.settings.get("language") == "en" else 1,
        )
        st.session_state.settings["language"] = lang
        
        # Debug mode
        debug = st.checkbox(
            "Show agent thoughts",
            value=st.session_state.settings.get("show_agent_thoughts", True),
        )
        st.session_state.settings["show_agent_thoughts"] = debug
        
        # Reset button
        st.markdown("---")
        if st.button("🔄 Reset Session"):
            from ui_utils.session import reset_session
            reset_session()
            st.rerun()


if __name__ == "__main__":
    main()
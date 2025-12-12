"""
ISP Customer Service Chatbot - Streamlit UI
ReAct Agent Demo with Protected Settings
"""

import sys
from pathlib import Path

# Add shared path
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
sys.path.insert(0, str(shared_path))

import os
os.environ["LITELLM_LOG"] = "ERROR"

# Initialize logging FIRST
from utils import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

import streamlit as st

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
            logger.info(f"RAG loaded: {stats['total_documents']} documents")
            print(f"✅ RAG loaded: {stats['total_documents']} documents")
            return True
        else:
            logger.warning("RAG: Knowledge base not found")
            print("⚠️ RAG: Knowledge base not found")
            return False
            
    except ImportError as e:
        logger.warning(f"RAG not available: {e}")
        print(f"⚠️ RAG not available: {e}")
        return False
    except Exception as e:
        logger.error(f"RAG init error: {e}")
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
    
    /* Demo banner */
    .demo-banner {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 10px 20px;
        border-radius: 8px;
        text-align: center;
        margin-bottom: 20px;
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
    
    # Demo banner
    render_demo_banner()
    
    # Header with current settings info
    render_header()
    
    # Main tabs - now with Demo Guide!
    tab_call, tab_guide, tab_monitor, tab_settings = st.tabs([
        "📞 Call",
        "📋 Demo Guide",
        "📊 Monitoring", 
        "⚙️ Settings"
    ])
    
    with tab_call:
        render_call_tab()
    
    with tab_guide:
        render_demo_guide_tab()
    
    with tab_monitor:
        render_monitor_tab()
    
    with tab_settings:
        render_settings_tab()


def render_demo_banner():
    """Render demo mode banner."""
    st.markdown("""
    <div class="demo-banner">
        <strong>🎮 DEMO MODE</strong> — 
        This is a demonstration of the ISP Customer Service AI Agent. 
        Use the phone numbers from Demo Guide to test different scenarios.
    </div>
    """, unsafe_allow_html=True)


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
        
        # Show lock status
        lock_icon = "🔓" if st.session_state.get("admin_authenticated") else "🔒"
        
        st.markdown(
            f"""
            <div style="text-align: right; font-size: 12px; color: #666;">
                🌍 {lang} | 🤖 {model_short} | {lock_icon}
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
        logger.error(f"Failed to load call interface: {e}")
        st.error(f"Failed to load call interface: {e}")
        
        # Fallback simple interface
        st.markdown("### Phone Interface")
        st.text_input("Phone number", value=st.session_state.get("phone_number", ""))
        if st.button("📞 Start Call"):
            st.info("Call interface not available")


def render_demo_guide_tab():
    """Render demo guide with scenarios."""
    try:
        from components.demo_guide import render_demo_guide
        render_demo_guide()
    except ImportError as e:
        logger.error(f"Failed to load demo guide: {e}")
        st.error(f"Failed to load demo guide: {e}")
        
        # Fallback - show basic info
        st.markdown("### 📋 Demo Scenarios")
        st.markdown("""
Use these phone numbers to test different scenarios:

| # | Phone | Scenario | Expected Result |
|---|-------|----------|-----------------|
| 1 | `+37060012345` | ✅ Happy Path | Troubleshooting → Resolved |
| 2 | `+37060012346` | ⚠️ Area Outage | Inform & wait |
| 3 | `+37060012347` | 📶 Slow WiFi | WiFi troubleshooting |
| 4 | `+37060012348` | 🔴 Port Down | Technician ticket |
| 5 | `+37060012349` | 📺 TV No Signal | TV troubleshooting |
| 6 | `+37060012350` | 🌐 No IP | Router restart |
| 7 | `+37060012351` | ⏸️ Suspended | Redirect to billing |
| 8 | `+37060012352` | 📉 Packet Loss | Line check ticket |
        """)


def render_monitor_tab():
    """Render monitoring dashboard."""
    try:
        from components.monitoring import render_monitor_tab as _render_monitor
        _render_monitor()
    except ImportError as e:
        logger.error(f"Failed to load monitoring: {e}")
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
        logger.error(f"Failed to load settings: {e}")
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

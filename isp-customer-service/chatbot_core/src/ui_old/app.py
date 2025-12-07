"""
ISP Customer Service Chatbot - Streamlit UI
Phone Call Simulation Demo
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent paths for imports
current_dir = Path(__file__).resolve().parent  # streamlit_ui/
src_dir = current_dir.parent  # src/

sys.path.insert(0, str(current_dir))  # utils, components
sys.path.insert(0, str(src_dir))  # graph, services

from components.call_interface import render_call_tab
from components.monitor import render_monitor_tab
from components.settings import render_settings_tab
from components.docs import render_docs_tab
from ui_utils.session import init_session

# =============================================================================
# RAG PRELOAD (Background initialization)
# =============================================================================


@st.cache_resource
def init_rag_system():
    """
    Initialize RAG system once (cached).
    Runs in background on first app load.
    """
    try:
        from rag import init_rag, preload_embedding_model

        # Start embedding model preload in background thread
        preload_embedding_model()

        # Load knowledge base
        success = init_rag(
            kb_name="production", preload_model=False, use_hybrid=True  # Already started above
        )

        if success:
            print("✅ RAG system initialized successfully")
        else:
            print("⚠️ RAG: Knowledge base not found, will work without it")

        return success

    except ImportError as e:
        print(f"⚠️ RAG not available: {e}")
        return False
    except Exception as e:
        print(f"❌ RAG init error: {e}")
        return False


# Localization
try:
    from src.locales import t, set_language

    LOCALES_AVAILABLE = True
except ImportError:
    LOCALES_AVAILABLE = False

    def t(key, **kwargs):
        return key


# Page config
st.set_page_config(
    page_title="ISP Customer Service Demo",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS (your existing CSS here...)
st.markdown(
    """
<style>
    /* ... your existing styles ... */
</style>
""",
    unsafe_allow_html=True,
)


def main():
    """Main app entry point."""

    # Initialize session state
    init_session()

    # Initialize RAG in background (cached - runs only once)
    rag_ready = init_rag_system()

    # Store RAG status in session
    if "rag_ready" not in st.session_state:
        st.session_state.rag_ready = rag_ready

    # Set language
    try:
        from src.locales import set_language

        saved_lang = st.session_state.settings.get("language", "lt")
        set_language(saved_lang)
    except ImportError:
        pass

    # Header
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title(t("app.title"))

        # Optional: Show RAG status indicator
        # if rag_ready:
        #     st.caption("🟢 RAG Ready")
        # else:
        #     st.caption("🟡 RAG Unavailable")

    # Main tabs
    tab_call, tab_monitor, tab_settings, tab_docs = st.tabs(
        [t("tabs.call"), t("tabs.monitor"), t("tabs.settings"), t("tabs.docs")]
    )

    with tab_call:
        render_call_tab()

    with tab_monitor:
        render_monitor_tab()

    with tab_settings:
        render_settings_tab()

    with tab_docs:
        render_docs_tab()


if __name__ == "__main__":
    main()

"""
ISP Customer Service Chatbot - Streamlit UI
Phone Call Simulation Demo
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent paths for imports
# Kai app.py yra chatbot_core/src/ui/streamlit_ui/
# reikia pridėti chatbot_core/src/ į path
current_dir = Path(__file__).resolve().parent  # streamlit_ui/
src_dir = current_dir.parent  # src/  (tik 1 lygis aukštyn!)

sys.path.insert(0, str(current_dir))  # utils, components
sys.path.insert(0, str(src_dir))       # graph, services

from components.call_interface import render_call_tab
from components.monitor import render_monitor_tab
from components.settings import render_settings_tab
from components.docs import render_docs_tab
from ui_utils.session import init_session

# Page config
st.set_page_config(
    page_title="ISP Customer Service Demo",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
<style>
    /* Main container */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        font-size: 16px;
    }
    
    /* Chat message styling */
    .chat-message {
        padding: 12px 16px;
        border-radius: 12px;
        margin: 8px 0;
        max-width: 80%;
    }
    
    .chat-message.user {
        background-color: #007AFF;
        color: white;
        margin-left: auto;
    }
    
    .chat-message.assistant {
        background-color: #E9ECEF;
        color: #1a1a1a;
    }
    
    /* Phone frame styling */
    .phone-frame {
        background: linear-gradient(145deg, #1a1a2e, #16213e);
        border-radius: 30px;
        padding: 20px;
        max-width: 400px;
        margin: 0 auto;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3);
    }
    
    .phone-screen {
        background: #ffffff;
        border-radius: 20px;
        min-height: 500px;
        padding: 15px;
    }
    
    /* Call button */
    .call-button {
        background: linear-gradient(145deg, #00c853, #00a844);
        color: white;
        border: none;
        padding: 15px 40px;
        border-radius: 30px;
        font-size: 18px;
        cursor: pointer;
    }
    
    /* End call button */
    .end-call-button {
        background: #ff3b30;
    }
    
    /* Status indicators */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
    }
    
    .status-active { background: #d4edda; color: #155724; }
    .status-pending { background: #fff3cd; color: #856404; }
    .status-error { background: #f8d7da; color: #721c24; }
    
    /* Agent info panel */
    .agent-info-panel {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


def main():
    """Main app entry point."""
    
    # Initialize session state
    init_session()
    
    # Header
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("📞 ISP Customer Service Demo")
    
    # Main tabs
    tab_call, tab_monitor, tab_settings, tab_docs = st.tabs([
        "📞 Call",
        "📊 Monitor", 
        "⚙️ Settings",
        "📖 Docs"
    ])
    
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

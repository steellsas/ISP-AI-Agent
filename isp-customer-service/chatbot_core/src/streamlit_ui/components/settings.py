"""
Settings Tab Component
Configuration for models, language, and other options
"""

import streamlit as st


def render_settings_tab():
    """Render the settings tab."""
    
    st.markdown("## ⚙️ Nustatymai")
    
    # Two columns layout
    col1, col2 = st.columns(2)
    
    with col1:
        render_model_settings()
    
    with col2:
        render_general_settings()
    
    st.markdown("---")
    
    render_advanced_settings()


def render_model_settings():
    """Render model selection settings."""
    
    st.markdown("### 🤖 AI Modeliai")
    
    st.info("⚠️ Modelių keitimas bus implementuotas vėliau")
    
    # Main model selection
    main_model = st.selectbox(
        "Pagrindinis modelis",
        options=[
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4-turbo",
            "claude-3-5-sonnet",
            "claude-3-haiku",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ],
        index=0,
        help="Modelis naudojamas pagrindinėms užduotims",
        disabled=True  # TODO: Enable when implemented
    )
    
    st.markdown("#### Modeliai pagal node'ą")
    st.markdown("*Galimybė naudoti skirtingus modelius skirtingiems workflow žingsniams*")
    
    # Per-node model selection (future feature)
    with st.expander("📊 Node-specific models", expanded=False):
        nodes = [
            ("greeting", "Pasisveikinimas"),
            ("identify_customer", "Kliento identifikavimas"),
            ("problem_capture", "Problemos surinkimas"),
            ("diagnostics", "Diagnostika"),
            ("troubleshooting", "Troubleshooting"),
            ("ticket_creation", "Ticket kūrimas"),
            ("closing", "Pokalbio užbaigimas")
        ]
        
        for node_id, node_name in nodes:
            st.selectbox(
                f"{node_name}",
                options=["Default (gpt-4o-mini)", "gpt-4o", "claude-3-haiku"],
                key=f"model_{node_id}",
                disabled=True
            )


def render_general_settings():
    """Render general settings."""
    
    st.markdown("### 🌍 Bendri nustatymai")
    
    # Language selection
    language = st.selectbox(
        "Kalba / Language",
        options=["Lietuvių", "English"],
        index=0,
        key="language_select"
    )
    
    if language == "Lietuvių":
        st.session_state.settings["language"] = "lt"
    else:
        st.session_state.settings["language"] = "en"
    
    st.markdown("---")
    
    # UI preferences
    st.markdown("#### 🎨 UI nustatymai")
    
    show_agent_thoughts = st.checkbox(
        "Rodyti agento 'mintis'",
        value=st.session_state.settings.get("show_agent_thoughts", True),
        help="Rodyti agento sprendimų informaciją Call tab'e"
    )
    st.session_state.settings["show_agent_thoughts"] = show_agent_thoughts
    
    debug_mode = st.checkbox(
        "Debug režimas",
        value=st.session_state.settings.get("debug_mode", False),
        help="Rodyti papildomą techninę informaciją"
    )
    st.session_state.settings["debug_mode"] = debug_mode


def render_advanced_settings():
    """Render advanced settings."""
    
    with st.expander("🔧 Advanced Settings"):
        st.markdown("### API Configuration")
        
        st.text_input(
            "OpenAI API Key",
            type="password",
            placeholder="sk-...",
            help="Jūsų OpenAI API raktas",
            disabled=True
        )
        
        st.text_input(
            "Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            help="Jūsų Anthropic API raktas",
            disabled=True
        )
        
        st.text_input(
            "Google AI API Key",
            type="password",
            placeholder="...",
            help="Jūsų Google AI API raktas",
            disabled=True
        )
        
        st.info("API raktai kol kas konfigūruojami per environment variables")
        
        st.markdown("---")
        
        st.markdown("### Database")
        
        db_path = st.text_input(
            "Database path",
            value="database/isp_database.db",
            disabled=True
        )
        
        st.markdown("---")
        
        st.markdown("### Troubleshooting")
        
        if st.button("🔄 Clear Cache", help="Išvalyti LangGraph cache"):
            st.cache_resource.clear()
            st.success("Cache išvalytas!")
        
        if st.button("📊 Show System Info"):
            import sys
            st.code(f"""
Python version: {sys.version}
Platform: {sys.platform}
            """)

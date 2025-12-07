"""
Settings Tab Component
Configuration for language, models, and other options
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

from ui_utils.session import update_settings, get_current_language


# =============================================================================
# MODEL REGISTRY (fallback if import fails)
# =============================================================================

DEFAULT_MODELS = {
    "openai": [
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "cost": "$0.15/1M"},
        {"id": "gpt-4o", "name": "GPT-4o", "cost": "$5.00/1M"},
    ],
    "google": [
        {"id": "gemini/gemini-2.0-flash", "name": "Gemini 2.0 Flash", "cost": "$0.075/1M"},
        {"id": "gemini/gemini-2.5-pro", "name": "Gemini 2.5 Pro", "cost": "$1.25/1M"},
    ],
}

# Try to import actual model registry
try:
    from services.llm.models import MODEL_REGISTRY, get_model_info
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    MODEL_REGISTRY = {}


def render_settings_tab():
    """Render the settings tab."""
    
    st.markdown("## ⚙️ Settings")
    
    # Two columns layout
    col1, col2 = st.columns(2)
    
    with col1:
        render_language_settings()
        st.markdown("---")
        render_model_settings()
    
    with col2:
        render_ui_settings()
        st.markdown("---")
        render_system_info()


def render_language_settings():
    """Render language selection."""
    
    st.markdown("### 🌍 Language")
    
    languages = [
        {"code": "en", "name": "English", "flag": "🇬🇧"},
        {"code": "lt", "name": "Lietuvių", "flag": "🇱🇹"},
    ]
    
    current_lang = st.session_state.settings.get("language", "en")
    
    # Find current index
    lang_codes = [l["code"] for l in languages]
    current_index = lang_codes.index(current_lang) if current_lang in lang_codes else 0
    
    selected_lang = st.selectbox(
        "Agent response language",
        lang_codes,
        index=current_index,
        format_func=lambda x: next(
            (f"{l['flag']} {l['name']}" for l in languages if l["code"] == x), x
        ),
        help="Language for agent responses. Changes take effect on next call.",
    )
    
    if selected_lang != current_lang:
        update_settings(language=selected_lang)
        st.success(f"Language set to: {selected_lang.upper()}")
        st.info("💡 Start a new call for language change to take effect.")


def render_model_settings():
    """Render model selection settings."""
    
    st.markdown("### 🤖 LLM Model")
    
    current_provider = st.session_state.settings.get("provider", "openai")
    current_model = st.session_state.settings.get("model", "gpt-4o-mini")
    current_temp = st.session_state.settings.get("temperature", 0.3)
    
    # Provider selection
    providers = ["openai", "google"]
    provider_labels = {
        "openai": "🟢 OpenAI",
        "google": "🔵 Google",
    }
    
    selected_provider = st.selectbox(
        "Provider",
        providers,
        index=providers.index(current_provider) if current_provider in providers else 0,
        format_func=lambda x: provider_labels.get(x, x),
    )
    
    # Get models for selected provider
    if MODELS_AVAILABLE:
        provider_models = [
            (model_id, info)
            for model_id, info in MODEL_REGISTRY.items()
            if info.provider == selected_provider
        ]
        model_options = [m[0] for m in provider_models]
        
        def format_model(model_id):
            info = MODEL_REGISTRY.get(model_id)
            if info:
                return f"{info.name} - ${info.input_cost_per_1k * 1000:.2f}/1M"
            return model_id
    else:
        # Use default models
        provider_models = DEFAULT_MODELS.get(selected_provider, [])
        model_options = [m["id"] for m in provider_models]
        
        def format_model(model_id):
            for m in provider_models:
                if m["id"] == model_id:
                    return f"{m['name']} - {m['cost']}"
            return model_id
    
    # Find current model index
    current_index = 0
    if current_model in model_options:
        current_index = model_options.index(current_model)
    
    selected_model = st.selectbox(
        "Model",
        model_options,
        index=current_index,
        format_func=format_model,
    )
    
    # Show model info
    if MODELS_AVAILABLE and selected_model in MODEL_REGISTRY:
        info = MODEL_REGISTRY[selected_model]
        st.info(
            f"""
**{info.name}**
- Input: ${info.input_cost_per_1k * 1000:.2f} / 1M tokens
- Output: ${info.output_cost_per_1k * 1000:.2f} / 1M tokens
- Max context: {info.max_tokens:,} tokens
- JSON mode: {"✅" if info.supports_json_mode else "❌"}
            """
        )
    
    # Temperature slider
    st.markdown("#### Parameters")
    
    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=current_temp,
        step=0.1,
        help="Lower = more focused, Higher = more creative",
    )
    
    # Check if settings changed
    settings_changed = (
        selected_provider != current_provider or
        selected_model != current_model or
        temperature != current_temp
    )
    
    # Apply button
    if settings_changed:
        st.warning("⚠️ Settings changed - click Save to apply")
    
    if st.button("💾 Save Model Settings", type="primary", disabled=not settings_changed):
        update_settings(
            provider=selected_provider,
            model=selected_model,
            temperature=temperature,
        )
        
        # Also update AgentConfig if available
        try:
            from agent.config import update_config
            update_config(
                model=selected_model,
                temperature=temperature,
            )
        except ImportError:
            pass
        
        # Update LLM settings if available
        try:
            from services.llm.settings import update_settings as update_llm_settings
            update_llm_settings(
                model=selected_model,
                temperature=temperature,
            )
        except ImportError:
            pass
        
        st.success(f"✅ Saved: {selected_model}, temp={temperature}")
        st.info("💡 Changes take effect on next LLM call.")


def render_ui_settings():
    """Render UI settings."""
    
    st.markdown("### 🎨 UI Settings")
    
    # Show agent thoughts
    show_thoughts = st.checkbox(
        "Show agent thoughts",
        value=st.session_state.settings.get("show_agent_thoughts", True),
        help="Display agent's reasoning in the UI",
    )
    st.session_state.settings["show_agent_thoughts"] = show_thoughts
    
    # Debug mode
    debug_mode = st.checkbox(
        "Debug mode",
        value=st.session_state.settings.get("debug_mode", False),
        help="Show additional technical information",
    )
    st.session_state.settings["debug_mode"] = debug_mode


def render_system_info():
    """Render system information."""
    
    st.markdown("### 📋 System Info")
    
    # RAG status
    if st.session_state.get("rag_ready"):
        st.success("✅ RAG Knowledge base loaded")
    else:
        st.warning("⚠️ RAG Knowledge base not available")
    
    # API keys status
    st.markdown("#### API Keys")
    
    try:
        from services.llm.utils import check_api_keys
        keys = check_api_keys()
        
        for provider, available in keys.items():
            if available:
                st.markdown(f"✅ {provider.upper()}")
            else:
                st.markdown(f"❌ {provider.upper()} - not configured")
    except ImportError:
        st.info("API key status not available")
    
    # Actions
    st.markdown("---")
    st.markdown("#### Actions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Clear Cache"):
            st.cache_resource.clear()
            st.success("Cache cleared!")
    
    with col2:
        if st.button("📊 System Info"):
            import sys
            st.code(f"Python: {sys.version[:10]}\nPlatform: {sys.platform}")
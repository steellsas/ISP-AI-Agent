"""
Settings Tab Component
Configuration for models, language, and other options
"""

import streamlit as st

# Localization
try:
    from src.locales import t

    LOCALES_AVAILABLE = True
except ImportError:
    LOCALES_AVAILABLE = False

    def t(key, **kwargs):
        return key


def render_settings_tab():
    """Render the settings tab."""

    st.markdown(f"## {t('settings.title')}")

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

    st.markdown(f"### {t('settings.models_title')}")

    # Import model registry
    try:
        from src.services.llm.models import MODEL_REGISTRY
        from src.services.llm.settings import get_settings, update_settings

        MODELS_AVAILABLE = True
    except ImportError as e:
        MODELS_AVAILABLE = False
        st.error(f"Model settings not available: {e}")
        return

    current_settings = get_settings()
    current_model = current_settings.model

    # Detect current provider
    current_provider = "openai"
    for model_id, info in MODEL_REGISTRY.items():
        if model_id == current_model:
            current_provider = info.provider
            break

    # Provider selection
    providers = ["openai", "google"]
    provider_labels = {"openai": "🟢 OpenAI", "google": "🔵 Google"}

    selected_provider = st.selectbox(
        t("settings.provider"),
        providers,
        index=providers.index(current_provider),
        format_func=lambda x: provider_labels.get(x, x),
    )

    # Filter models by provider
    provider_models = [
        (model_id, info)
        for model_id, info in MODEL_REGISTRY.items()
        if info.provider == selected_provider
    ]

    # Model selection
    model_options = [m[0] for m in provider_models]

    # Find current index
    current_index = 0
    if current_model in model_options:
        current_index = model_options.index(current_model)

    def format_model_option(model_id):
        info = MODEL_REGISTRY.get(model_id)
        if info:
            return f"{info.name} - ${info.input_cost_per_1k * 1000:.2f}/1M tokens"
        return model_id

    selected_model = st.selectbox(
        t("settings.model"), model_options, index=current_index, format_func=format_model_option
    )

    # Show model info
    if selected_model in MODEL_REGISTRY:
        info = MODEL_REGISTRY[selected_model]
        st.info(
            f"""
**{info.name}**
- Input: ${info.input_cost_per_1k * 1000:.2f} / 1M tokens
- Output: ${info.output_cost_per_1k * 1000:.2f} / 1M tokens  
- Max context: {info.max_tokens:,} tokens
- JSON mode: {"✅" if info.supports_json_mode else "❌"}
- Vision: {"✅" if info.supports_vision else "❌"}
        """
        )

    # Temperature slider
    st.markdown(f"#### {t('settings.parameters')}")

    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=current_settings.temperature,
        step=0.1,
        help=t("settings.temperature_help"),
    )

    # Check if settings changed
    settings_changed = (
        selected_model != current_model or temperature != current_settings.temperature
    )

    # Apply button
    if settings_changed:
        st.warning(t("settings.settings_changed"))

    if st.button(t("settings.save_button"), type="primary", disabled=not settings_changed):
        update_settings(model=selected_model, temperature=temperature)
        st.success(t("settings.saved_message", model=selected_model, temperature=temperature))
        st.rerun()


def render_general_settings():
    """Render general settings."""

    # Import localization
    try:
        from src.locales import t, get_language, set_language, get_available_languages

        LOCALES_AVAILABLE = True
    except ImportError:
        LOCALES_AVAILABLE = False

    st.markdown(f"### {t('settings.language_title') if LOCALES_AVAILABLE else '🌍 Language'}")

    if LOCALES_AVAILABLE:
        languages = get_available_languages()
        current_lang = get_language()

        # Find current index
        lang_codes = [l["code"] for l in languages]
        current_index = lang_codes.index(current_lang) if current_lang in lang_codes else 0

        selected_lang = st.selectbox(
            t("settings.language_title"),
            lang_codes,
            index=current_index,
            format_func=lambda x: next(
                (f"{l['flag']} {l['name']}" for l in languages if l["code"] == x), x
            ),
            label_visibility="collapsed",
        )

        if selected_lang != current_lang:
            set_language(selected_lang)
            st.session_state.settings["language"] = selected_lang
            st.rerun()
    else:
        st.warning("Localization not available")

    st.markdown("---")

    # UI preferences
    st.markdown(f"#### {t('settings.ui_settings') if LOCALES_AVAILABLE else '🎨 UI settings'}")

    show_agent_thoughts = st.checkbox(
        t("settings.show_agent_thoughts") if LOCALES_AVAILABLE else "Show agent thoughts",
        value=st.session_state.settings.get("show_agent_thoughts", True),
        help=(
            t("settings.show_agent_thoughts_help")
            if LOCALES_AVAILABLE
            else "Show agent decision info"
        ),
    )
    st.session_state.settings["show_agent_thoughts"] = show_agent_thoughts

    debug_mode = st.checkbox(
        t("settings.debug_mode") if LOCALES_AVAILABLE else "Debug mode",
        value=st.session_state.settings.get("debug_mode", False),
        help=t("settings.debug_mode_help") if LOCALES_AVAILABLE else "Show technical info",
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
            disabled=True,
        )

        st.text_input(
            "Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            help="Jūsų Anthropic API raktas",
            disabled=True,
        )

        st.text_input(
            "Google AI API Key",
            type="password",
            placeholder="...",
            help="Jūsų Google AI API raktas",
            disabled=True,
        )

        st.info("API raktai kol kas konfigūruojami per environment variables")

        st.markdown("---")

        st.markdown("### Database")

        db_path = st.text_input("Database path", value="database/isp_database.db", disabled=True)

        st.markdown("---")

        st.markdown("### Troubleshooting")

        if st.button("🔄 Clear Cache", help="Išvalyti LangGraph cache"):
            st.cache_resource.clear()
            st.success("Cache išvalytas!")

        if st.button("📊 Show System Info"):
            import sys

            st.code(
                f"""
Python version: {sys.version}
Platform: {sys.platform}
            """
            )

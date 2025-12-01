"""
Monitor Tab Component
Detailed monitoring, debugging, and graph visualization
"""

import streamlit as st
import json
import sys
from pathlib import Path

# Fix imports
_current = Path(__file__).resolve().parent.parent
if str(_current) not in sys.path:
    sys.path.insert(0, str(_current))

from ui_utils.session import get_state_summary

# Localization
try:
    from src.locales import t
    LOCALES_AVAILABLE = True
except ImportError:
    LOCALES_AVAILABLE = False
    def t(key, **kwargs):
        return key

# Import LLM stats
try:
    from services.llm import get_session_stats
    LLM_STATS_AVAILABLE = True
except ImportError:
    LLM_STATS_AVAILABLE = False


def render_monitor_tab():
    """Render the monitoring tab."""
    
    st.markdown(f"## {t('monitor.title')}")
    
    # Top metrics row
    render_metrics_row()
    
    st.markdown("---")
    
    # Two columns: Graph + Details
    col_graph, col_details = st.columns([1, 1])
    
    with col_graph:
        render_graph_section()
    
    with col_details:
        render_details_section()
    
    st.markdown("---")
    
    # Bottom section: LLM calls and RAG
    col_llm, col_rag = st.columns([1, 1])
    
    with col_llm:
        render_llm_calls_section()
    
    with col_rag:
        render_rag_section()
    
    # Debug section
    st.markdown("---")
    render_debug_section()


def render_metrics_row():
    """Render top metrics from session_state."""
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
       st.metric(t("monitor.messages"), len(st.session_state.get("messages", [])))

    with col2:
        tokens = st.session_state.get("total_tokens", 0)
        st.metric(t("monitor.tokens"), f"{tokens:,}")
    
    with col3:
        cost = st.session_state.get("total_cost", 0)
        st.metric("💰 Cost", f"${cost:.4f}")
    
    with col4:
        calls = len(st.session_state.get("llm_calls", []))
        st.metric(t("monitor.llm_calls"), calls)


def render_llm_calls_section():
    """Render LLM calls from session_state."""
    
    st.markdown(f"### {t('monitor.llm_title')}")
    
    llm_calls = st.session_state.get("llm_calls", [])
    
    if not llm_calls:
        st.info(t("monitor.no_llm_calls"))
        return
    
    # Summary by model
    models = {}
    for call in llm_calls:
        model = call.get("model", "unknown")
        if model not in models:
            models[model] = {"count": 0, "tokens": 0, "cost": 0}
        models[model]["count"] += 1
        models[model]["tokens"] += call.get("input_tokens", 0) + call.get("output_tokens", 0)
        models[model]["cost"] += call.get("cost", 0)
    
    st.markdown(f"**{t('monitor.by_model')}:**")
    for model, stats in models.items():
        st.markdown(f"• `{model}`: {stats['count']} calls, {stats['tokens']:,} tokens, ${stats['cost']:.4f}")
    
    st.markdown("---")
    
    # Recent calls
    st.markdown(f"**{t('monitor.recent_calls')}:**")
    for call in reversed(llm_calls[-10:]):
        cached = "📦" if call.get("cached") else ""
        total_tok = call.get("input_tokens", 0) + call.get("output_tokens", 0)
        st.markdown(
            f"✓ {cached} `{call.get('model')}` | "
            f"{total_tok} tok | "
            f"${call.get('cost', 0):.5f} | "
            f"{call.get('latency_ms', 0):.0f}ms"
        )

def render_graph_section():
    """Render graph visualization section."""
    
    st.markdown(f"### {t('monitor.graph_title')}")
    
    from ui_utils.chatbot_bridge import get_graph_image
    
    graph_png = get_graph_image()
    if graph_png:
        st.image(graph_png, caption="LangGraph Workflow", width="stretch")
    else:
        st.warning("Can generate graph image yet.")
    
    state = get_state_summary()
    current_node = state.get("current_node", "unknown")
    st.markdown(f"**{t('monitor.current_node_label')}:** `{current_node}`")


def render_details_section():
    """Render state details section."""
    
    st.markdown(f"### {t('monitor.state_title')}")
    
    state = get_state_summary()
    
    if not st.session_state.chatbot_state:
        st.info("Pradėkite pokalbį, kad matytumėte state")
        return
    
    tab1, tab2, tab3 = st.tabs(["Customer", "Problem", "Workflow"])
    
    with tab1:
        st.json({
            "customer_id": state.get("customer_id"),
            "customer_name": state.get("customer_name"),
            "address_confirmed": state.get("address_confirmed")
        })
    
    with tab2:
        st.json({
            "problem_type": state.get("problem_type"),
            "problem_description": state.get("problem_description"),
            "problem_context": state.get("problem_context")
        })
    
    with tab3:
        st.json({
            "current_node": state.get("current_node"),
            "diagnostics_completed": state.get("diagnostics_completed"),
            "problem_resolved": state.get("problem_resolved"),
            "troubleshooting_needs_escalation": state.get("troubleshooting_needs_escalation"),
            "ticket_id": state.get("ticket_id"),
            "conversation_ended": state.get("conversation_ended")
        })


def render_rag_section():
    """Render RAG documents from session_state."""
    
    st.markdown(f"### {t('monitor.rag_title')}")
    
    rag_retrievals = st.session_state.get("rag_retrievals", [])
    
    if not rag_retrievals:
        st.info(t("monitor.no_rag"))
        return
    
    for retrieval in reversed(rag_retrievals[-5:]):
        query = retrieval.get("query", "")[:50]
        with st.expander(f"🔍 Query: {query}..."):
            st.markdown(f"**Results:** {retrieval.get('results_count', 0)}")
            
            for result in retrieval.get("results", []):
                meta = result.get("metadata", {})
                score = result.get("score", 0)
                scenario_id = meta.get("scenario_id", "doc")
                title = meta.get("title", "")
                st.markdown(f"• **{scenario_id}** (score: {score:.2f}) - {title}")

def render_debug_section():
    """Render debug section with full state."""

    with st.expander(t("monitor.debug_title")):
        if st.session_state.chatbot_state:
            st.code(json.dumps(st.session_state.chatbot_state, indent=2, default=str), language="json")
        else:
            st.info(t("monitor.no_state"))
    
    if LLM_STATS_AVAILABLE:
        with st.expander("📊 LLM Stats Raw"):
            stats = get_session_stats()
            st.code(stats.get_summary_text())

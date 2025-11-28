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

# Import LLM stats
try:
    from services.llm.stats import get_session_stats
    LLM_STATS_AVAILABLE = True
except ImportError:
    LLM_STATS_AVAILABLE = False


def render_monitor_tab():
    """Render the monitoring tab."""
    
    st.markdown("## 📊 Monitoring Dashboard")
    
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
    """Render top metrics row."""
    
    col1, col2, col3, col4 = st.columns(4)
    
    if LLM_STATS_AVAILABLE:
        stats = get_session_stats()
        
        with col1:
            st.metric("💬 Žinutės", len(st.session_state.messages))
        
        with col2:
            st.metric(
                "🎫 Tokens",
                f"{stats.total_tokens:,}",
                help=f"Input: {stats.total_input_tokens:,} | Output: {stats.total_output_tokens:,}"
            )
        
        with col3:
            st.metric(
                "💰 Cost",
                f"${stats.total_cost_usd:.4f}",
            )
        
        with col4:
            st.metric(
                "🔄 LLM Calls",
                stats.total_calls,
                help=f"✓ {stats.successful_calls} | ✗ {stats.failed_calls} | 📦 {stats.cached_calls} cached"
            )
    else:
        with col1:
            st.metric("💬 Žinutės", len(st.session_state.messages))
        with col2:
            st.metric("🎫 Tokens", "N/A")
        with col3:
            st.metric("💰 Cost", "N/A")
        with col4:
            st.metric("🔄 LLM Calls", "N/A")
        st.warning("LLM stats not available")


def render_llm_calls_section():
    """Render LLM calls history section."""
    
    st.markdown("### 🤖 LLM Calls")
    
    if not LLM_STATS_AVAILABLE:
        st.warning("LLM stats not available")
        return
    
    stats = get_session_stats()
    recent_calls = stats.get_recent_calls(10)
    
    if not recent_calls:
        st.info("Kol kas LLM iškvietimų nebuvo")
        return
    
    # Summary by model
    if stats.calls_per_model:
        st.markdown("**Pagal modelį:**")
        for model, count in stats.calls_per_model.items():
            tokens = stats.tokens_per_model.get(model, 0)
            cost = stats.cost_per_model.get(model, 0)
            st.markdown(f"• `{model}`: {count} calls, {tokens:,} tokens, ${cost:.4f}")
    
    st.markdown("---")
    
    # Recent calls
    st.markdown("**Paskutiniai iškvietimai:**")
    for call in reversed(recent_calls):
        status = "✓" if call.success else "✗"
        cached = "📦" if call.cached else ""
        st.markdown(
            f"{status} {cached} `{call.model}` | "
            f"{call.total_tokens} tok | "
            f"${call.cost_usd:.5f} | "
            f"{call.latency_ms:.0f}ms"
        )


def render_graph_section():
    """Render graph visualization section."""
    
    st.markdown("### 🗺️ Workflow Graph")
    
    from ui_utils.chatbot_bridge import get_graph_image
    
    graph_png = get_graph_image()
    if graph_png:
        st.image(graph_png, caption="LangGraph Workflow", width="stretch")
    else:
        st.warning("Nepavyko sugeneruoti graph vizualizacijos")
    
    state = get_state_summary()
    current_node = state.get("current_node", "unknown")
    st.markdown(f"**Dabartinis node:** `{current_node}`")


def render_details_section():
    """Render state details section."""
    
    st.markdown("### 📋 State Details")
    
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
    """Render RAG documents section."""
    
    st.markdown("### 📚 RAG Documents")
    
    rag_docs = st.session_state.rag_documents
    
    if not rag_docs:
        st.info("Kol kas RAG dokumentų nepanaudota")
    else:
        for doc in rag_docs:
            with st.expander(f"📄 {doc.get('title', 'Document')} (score: {doc.get('score', 0):.2f})"):
                st.markdown(f"**ID:** {doc.get('doc_id')}")
                st.markdown(f"**Retrieved:** {doc.get('timestamp')}")


def render_debug_section():
    """Render debug section with full state."""
    
    with st.expander("🐛 Debug: Full State"):
        if st.session_state.chatbot_state:
            st.code(json.dumps(st.session_state.chatbot_state, indent=2, default=str), language="json")
        else:
            st.info("No state available")
    
    if LLM_STATS_AVAILABLE:
        with st.expander("📊 LLM Stats Raw"):
            stats = get_session_stats()
            st.code(stats.get_summary_text())

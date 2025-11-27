"""
Monitor Tab Component
Detailed monitoring, debugging, and graph visualization
"""

import streamlit as st
import json

from ui_utils.session import get_state_summary


def render_monitor_tab():
    """Render the monitoring tab."""
    
    st.markdown("## 📊 Monitoring Dashboard")
    
    if not st.session_state.chatbot_state:
        st.info("Pradėkite pokalbį 📞 Call tab'e, kad matytumėte monitoring duomenis")
        return
    
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
    
    # Bottom section: RAG docs and LLM calls
    col_rag, col_llm = st.columns([1, 1])
    
    with col_rag:
        render_rag_section()
    
    with col_llm:
        render_llm_calls_section()
    
    # Debug section
    st.markdown("---")
    render_debug_section()


def render_metrics_row():
    """Render top metrics row."""
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "💬 Žinutės",
            len(st.session_state.messages)
        )
    
    with col2:
        token_usage = st.session_state.token_usage
        st.metric(
            "🎫 Tokens",
            f"{token_usage['total']:,}",
            help=f"Input: {token_usage['input']:,} | Output: {token_usage['output']:,}"
        )
    
    with col3:
        # Estimate cost (GPT-4o-mini pricing)
        # Input: $0.15/1M, Output: $0.60/1M
        input_cost = token_usage['input'] * 0.00000015
        output_cost = token_usage['output'] * 0.0000006
        total_cost = input_cost + output_cost
        st.metric(
            "💰 Cost",
            f"${total_cost:.4f}",
            help="Estimated cost based on GPT-4o-mini pricing"
        )
    
    with col4:
        st.metric(
            "🔄 LLM Calls",
            len(st.session_state.llm_calls)
        )


def render_graph_section():
    """Render graph visualization section."""
    
    st.markdown("### 🗺️ Workflow Graph")
    
    # Get current node
    state = get_state_summary()
    current_node = state.get("current_node", "unknown")
    
    # Mermaid graph
    # Highlight current node
    node_styles = {
        "greeting": "",
        "identify_customer": "",
        "problem_capture": "",
        "diagnostics": "",
        "troubleshooting": "",
        "ticket_creation": "",
        "closing": "",
        "end": ""
    }
    
    # Set current node style
    if current_node in node_styles:
        node_styles[current_node] = ":::active"
    
    mermaid_code = f"""
    graph TD
        A[Start] --> B[greeting{node_styles.get('greeting', '')}]
        B --> C[identify_customer{node_styles.get('identify_customer', '')}]
        C --> D[problem_capture{node_styles.get('problem_capture', '')}]
        D --> E[diagnostics{node_styles.get('diagnostics', '')}]
        E --> F{{Router}}
        F -->|provider issue| G[inform_provider_issue]
        F -->|customer issue| H[troubleshooting{node_styles.get('troubleshooting', '')}]
        H --> I{{Resolved?}}
        I -->|yes| J[closing{node_styles.get('closing', '')}]
        I -->|no| K[ticket_creation{node_styles.get('ticket_creation', '')}]
        K --> J
        G --> J
        J --> L[end{node_styles.get('end', '')}]
        
        classDef active fill:#4CAF50,stroke:#2E7D32,color:white
    """
    
    st.markdown(f"""
    ```mermaid
    {mermaid_code}
    ```
    """)
    
    # Note: Streamlit doesn't render mermaid natively, 
    # but we can show it as code or use streamlit-mermaid component
    
    # Alternative: simple text representation
    st.markdown("#### Node Flow:")
    
    nodes = [
        ("greeting", "🟢"),
        ("identify_customer", "🔵"),
        ("problem_capture", "🟡"),
        ("diagnostics", "🟠"),
        ("troubleshooting", "🔧"),
        ("ticket_creation", "🎫"),
        ("closing", "✅"),
        ("end", "⬛")
    ]
    
    flow_text = ""
    for node, icon in nodes:
        if node == current_node:
            flow_text += f"**→ {icon} {node} ←**  "
        else:
            flow_text += f"{icon} {node}  →  "
    
    st.markdown(flow_text.rstrip(" → "))


def render_details_section():
    """Render state details section."""
    
    st.markdown("### 📋 State Details")
    
    state = get_state_summary()
    
    # Organized state display
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
        
        # Placeholder for demonstration
        st.markdown("""
        *Čia bus rodomi dokumentai, kuriuos agentas panaudojo atsakymui:*
        - Troubleshooting guides
        - FAQ entries
        - Technical documentation
        """)
    else:
        for doc in rag_docs:
            with st.expander(f"📄 {doc.get('title', 'Document')} (score: {doc.get('score', 0):.2f})"):
                st.markdown(f"**ID:** {doc.get('doc_id')}")
                st.markdown(f"**Retrieved:** {doc.get('timestamp')}")


def render_llm_calls_section():
    """Render LLM calls history section."""
    
    st.markdown("### 🤖 LLM Calls")
    
    llm_calls = st.session_state.llm_calls
    
    if not llm_calls:
        st.info("Kol kas LLM iškvietimų nebuvo užregistruota")
        
        # Placeholder
        st.markdown("""
        *Čia bus rodoma LLM iškvietimų istorija:*
        - Node kuris iškvietė
        - Modelis
        - Token count
        - Response time
        """)
    else:
        for i, call in enumerate(reversed(llm_calls[-10:])):
            st.markdown(f"""
            **#{len(llm_calls) - i}** `{call.get('node')}` 
            | Model: {call.get('model')} 
            | Tokens: {call.get('tokens')} 
            | Time: {call.get('duration_ms')}ms
            """)


def render_debug_section():
    """Render debug section with full state."""
    
    with st.expander("🐛 Debug: Full State"):
        if st.session_state.chatbot_state:
            # Make it copy-able
            st.code(json.dumps(st.session_state.chatbot_state, indent=2, default=str), language="json")
        else:
            st.info("No state available")
    
    with st.expander("📜 Message History (Raw)"):
        for i, msg in enumerate(st.session_state.messages):
            st.markdown(f"**[{i}]** `{msg.get('role')}`: {msg.get('content')[:100]}...")

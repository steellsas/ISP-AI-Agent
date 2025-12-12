"""
Demo Guide Component - Shows available test scenarios with phone numbers

Displays the 8 demo scenarios that users can test.
"""

import streamlit as st


# =============================================================================
# DEMO SCENARIOS DATA
# =============================================================================

DEMO_SCENARIOS = [
    {
        "id": 1,
        "phone": "+37060012345",
        "name": "Jonas Jonaitis",
        "title": "Happy Path",
        "icon": "✅",
        "description": "Everything works fine. Router restart resolves issue.",
        "expected": "Troubleshooting → Resolved",
        "color": "#4CAF50",
    },
    {
        "id": 2,
        "phone": "+37060012346",
        "name": "Marija Kazlauskienė",
        "title": "Area Outage",
        "icon": "⚠️",
        "description": "Active outage in customer's area.",
        "expected": "Inform about outage → Wait for fix",
        "color": "#FF9800",
    },
    {
        "id": 3,
        "phone": "+37060012347",
        "name": "Petras Petraitis",
        "title": "Slow WiFi",
        "icon": "📶",
        "description": "Slow internet on phone only. Network is healthy.",
        "expected": "WiFi troubleshooting guide",
        "color": "#2196F3",
    },
    {
        "id": 4,
        "phone": "+37060012348",
        "name": "Andrius Andriuška",
        "title": "Port Down",
        "icon": "🔴",
        "description": "Network port is DOWN. Requires technician.",
        "expected": "Create high-priority ticket",
        "color": "#f44336",
    },
    {
        "id": 5,
        "phone": "+37060012349",
        "name": "Ona Onaitė",
        "title": "TV No Signal",
        "icon": "📺",
        "description": "TV shows 'No Signal'. Has TV Premium service.",
        "expected": "TV-specific troubleshooting",
        "color": "#9C27B0",
    },
    {
        "id": 6,
        "phone": "+37060012350",
        "name": "Laima Laimutė",
        "title": "No IP (DHCP)",
        "icon": "🌐",
        "description": "No IP address assigned. DHCP issue.",
        "expected": "Router restart → Maybe ticket",
        "color": "#00BCD4",
    },
    {
        "id": 7,
        "phone": "+37060012351",
        "name": "Tomas Tomauskas",
        "title": "Account Suspended",
        "icon": "⏸️",
        "description": "Account is suspended (billing issue).",
        "expected": "Redirect to billing department",
        "color": "#607D8B",
    },
    {
        "id": 8,
        "phone": "+37060012352",
        "name": "Rūta Rūtaitė",
        "title": "Packet Loss",
        "icon": "📉",
        "description": "Intermittent connection. ~30% packet loss.",
        "expected": "Create ticket for line check",
        "color": "#795548",
    },
]


# =============================================================================
# RENDER FUNCTIONS
# =============================================================================

def render_demo_guide():
    """Render the demo guide with all scenarios."""
    
    st.markdown("## 📋 Demo Scenarios")
    st.markdown(
        "Use these phone numbers to test different customer scenarios. "
        "Each scenario demonstrates a different agent behavior."
    )
    
    # Quick reference - all numbers
    with st.expander("📞 Quick Reference - All Phone Numbers", expanded=False):
        render_quick_reference()
    
    st.markdown("---")
    
    # Detailed scenarios in 2 columns
    col1, col2 = st.columns(2)
    
    for i, scenario in enumerate(DEMO_SCENARIOS):
        with col1 if i % 2 == 0 else col2:
            render_scenario_card(scenario)


def render_quick_reference():
    """Render quick reference table with all phone numbers."""
    
    st.markdown("""
| # | Phone | Scenario | Result |
|---|-------|----------|--------|
| 1 | `+37060012345` | ✅ Happy Path | Resolved |
| 2 | `+37060012346` | ⚠️ Area Outage | Inform & wait |
| 3 | `+37060012347` | 📶 Slow WiFi | WiFi guide |
| 4 | `+37060012348` | 🔴 Port Down | Technician ticket |
| 5 | `+37060012349` | 📺 TV No Signal | TV guide |
| 6 | `+37060012350` | 🌐 No IP | Restart/ticket |
| 7 | `+37060012351` | ⏸️ Suspended | Billing redirect |
| 8 | `+37060012352` | 📉 Packet Loss | Line check ticket |
    """)


def render_scenario_card(scenario: dict):
    """Render a single scenario card."""
    
    st.markdown(
        f"""
        <div style="
            border: 1px solid {scenario['color']}40;
            border-left: 4px solid {scenario['color']};
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            background: {scenario['color']}10;
        ">
            <div style="font-size: 1.2em; font-weight: bold; margin-bottom: 8px;">
                {scenario['icon']} Scenario {scenario['id']}: {scenario['title']}
            </div>
            <div style="font-family: monospace; background: #f5f5f5; padding: 5px 10px; border-radius: 4px; margin-bottom: 8px;">
                📞 {scenario['phone']}
            </div>
            <div style="font-size: 0.9em; color: #666; margin-bottom: 5px;">
                👤 {scenario['name']}
            </div>
            <div style="margin-bottom: 8px;">
                {scenario['description']}
            </div>
            <div style="font-size: 0.85em; color: {scenario['color']};">
                → {scenario['expected']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_demo_sidebar():
    """Render a compact demo guide in sidebar."""
    
    st.sidebar.markdown("### 📞 Demo Numbers")
    
    for scenario in DEMO_SCENARIOS:
        st.sidebar.markdown(
            f"{scenario['icon']} `{scenario['phone']}`  \n"
            f"<small style='color: #666;'>{scenario['title']}</small>",
            unsafe_allow_html=True,
        )


def render_phone_selector():
    """Render phone number selector dropdown."""
    
    options = [""] + [f"{s['phone']} - {s['icon']} {s['title']}" for s in DEMO_SCENARIOS]
    
    selected = st.selectbox(
        "Select demo scenario",
        options,
        index=0,
        help="Choose a scenario or enter custom phone number",
    )
    
    if selected:
        # Extract phone from selection
        phone = selected.split(" - ")[0]
        return phone
    
    return None


def get_scenario_by_phone(phone: str) -> dict | None:
    """Get scenario details by phone number."""
    
    for scenario in DEMO_SCENARIOS:
        if scenario["phone"] == phone:
            return scenario
    
    return None


def render_current_scenario_info(phone: str):
    """Show info about currently selected scenario."""
    
    scenario = get_scenario_by_phone(phone)
    
    if scenario:
        st.info(
            f"**{scenario['icon']} Scenario {scenario['id']}: {scenario['title']}**\n\n"
            f"👤 {scenario['name']}\n\n"
            f"{scenario['description']}\n\n"
            f"*Expected: {scenario['expected']}*"
        )

"""
Documentation Tab Component
Documentation in LT and EN
"""

import streamlit as st


def render_docs_tab():
    """Render the documentation tab."""

    st.markdown("## 📖 Dokumentacija")

    # Language toggle
    doc_lang = st.radio("Kalba / Language", options=["🇱🇹 Lietuvių", "🇬🇧 English"], horizontal=True)

    is_lt = "Lietuvių" in doc_lang

    st.markdown("---")

    # Docs sections
    if is_lt:
        render_docs_lt()
    else:
        render_docs_en()


def render_docs_lt():
    """Render Lithuanian documentation."""

    st.markdown(
        """
    ## ISP Klientų Aptarnavimo Chatbot
    
    ### 📋 Apžvalga
    
    Šis chatbotas skirtas automatizuoti ISP (interneto paslaugų tiekėjo) klientų 
    aptarnavimo telefono skambučius. Sistema gali:
    
    - ✅ Identifikuoti klientą pagal telefono numerį arba adresą
    - ✅ Surinkti informaciją apie problemą
    - ✅ Atlikti tinklo diagnostiką
    - ✅ Vesti per troubleshooting žingsnius
    - ✅ Sukurti ticket'ą jei problema neišsprendžiama
    
    ---
    
    ### 🔄 Workflow Žingsniai
    
    1. **Greeting** - Pasisveikinimas su klientu
    2. **Identify Customer** - Kliento identifikavimas (telefonu/adresu)
    3. **Problem Capture** - Problemos aprašymo surinkimas
    4. **Diagnostics** - Automatinė tinklo diagnostika
    5. **Troubleshooting** - Problemos sprendimas pagal scenarijų
    6. **Ticket Creation** - Ticket kūrimas jei reikia
    7. **Closing** - Pokalbio užbaigimas
    
    ---
    
    ### 🛠️ Techninė Informacija
    
    **Naudojamos technologijos:**
    - LangGraph - workflow valdymas
    - LiteLLM - multi-provider LLM access
    - RAG - troubleshooting scenarijų paieška
    - MCP - CRM ir diagnostikos servisų integracija
    
    **Palaikomi modeliai:**
    - OpenAI GPT-4o, GPT-4o-mini
    - Anthropic Claude 3.5 Sonnet, Claude 3 Haiku
    - Google Gemini 1.5 Pro, Flash
    
    ---
    
    ### 📞 Testavimas
    
    **Testiniai telefono numeriai:**
    - `+37061234567` - Standartinis testas
    - `+37060012345` - Klientas su aktyviu internet planu
    
    **Testinės problemos:**
    - "Neveikia internetas" - Internet troubleshooting flow
    - "Neveikia televizija" - TV troubleshooting flow
    - "Per lėtas internetas" - Speed issues flow
    
    ---
    
    ### ❓ DUK
    
    **K: Kaip pakeisti AI modelį?**
    A: Šiuo metu modelis konfigūruojamas per Settings tab (coming soon).
    
    **K: Ar duomenys saugomi?**
    A: Demo versijoje pokalbiai nesaugomi. Production versijoje būtų 
    integruota su CRM.
    
    **K: Kaip pridėti naujus troubleshooting scenarijus?**
    A: Scenarijai aprašomi YAML failuose `chatbot_core/src/config/` folderyje.
    """
    )


def render_docs_en():
    """Render English documentation."""

    st.markdown(
        """
    ## ISP Customer Service Chatbot
    
    ### 📋 Overview
    
    This chatbot is designed to automate ISP (Internet Service Provider) customer 
    service phone calls. The system can:
    
    - ✅ Identify customers by phone number or address
    - ✅ Collect problem information
    - ✅ Perform network diagnostics
    - ✅ Guide through troubleshooting steps
    - ✅ Create tickets if the problem cannot be resolved
    
    ---
    
    ### 🔄 Workflow Steps
    
    1. **Greeting** - Initial customer greeting
    2. **Identify Customer** - Customer identification (by phone/address)
    3. **Problem Capture** - Collecting problem description
    4. **Diagnostics** - Automatic network diagnostics
    5. **Troubleshooting** - Problem resolution following scenarios
    6. **Ticket Creation** - Creating ticket if needed
    7. **Closing** - Conversation closing
    
    ---
    
    ### 🛠️ Technical Information
    
    **Technologies used:**
    - LangGraph - workflow management
    - LiteLLM - multi-provider LLM access
    - RAG - troubleshooting scenario search
    - MCP - CRM and diagnostics services integration
    
    **Supported models:**
    - OpenAI GPT-4o, GPT-4o-mini
    - Anthropic Claude 3.5 Sonnet, Claude 3 Haiku
    - Google Gemini 1.5 Pro, Flash
    
    ---
    
    ### 📞 Testing
    
    **Test phone numbers:**
    - `+37061234567` - Standard test
    - `+37060012345` - Customer with active internet plan
    
    **Test problems:**
    - "Internet not working" - Internet troubleshooting flow
    - "TV not working" - TV troubleshooting flow
    - "Slow internet" - Speed issues flow
    
    ---
    
    ### ❓ FAQ
    
    **Q: How to change the AI model?**
    A: Currently, the model is configured via Settings tab (coming soon).
    
    **Q: Is data stored?**
    A: In the demo version, conversations are not stored. Production version 
    would integrate with CRM.
    
    **Q: How to add new troubleshooting scenarios?**
    A: Scenarios are defined in YAML files in `chatbot_core/src/config/` folder.
    """
    )

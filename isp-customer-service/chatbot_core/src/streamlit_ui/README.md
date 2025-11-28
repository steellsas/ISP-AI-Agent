# ISP Customer Service - Streamlit UI

📞 Phone Call Simulation Demo for ISP Customer Service Chatbot

## 📁 Struktūra

```
streamlit_ui/
├── app.py                    # Main Streamlit app
├── components/
│   ├── __init__.py
│   ├── call_interface.py     # 📞 Call tab - phone simulation
│   ├── monitor.py            # 📊 Monitor tab - debugging
│   ├── settings.py           # ⚙️ Settings tab
│   └── docs.py               # 📖 Docs tab
├── utils/
│   ├── __init__.py
│   ├── session.py            # Session state management
│   └── chatbot_bridge.py     # Connection to chatbot_core
├── requirements.txt
└── README.md
```

## 🚀 Paleidimas

### 1. Įdėti į projektą

Nukopijuok `streamlit_ui` folderį į:
```
chatbot_core/src/ui/streamlit_ui/
```

### 2. Instaliuoti dependencies

```bash
pip install streamlit>=1.28.0
```

### 3. Paleisti

```bash
# Iš chatbot_core/src/ui/streamlit_ui/ folderio:
cd chatbot_core/src/ui/streamlit_ui
streamlit run app.py

# Arba su custom port:
streamlit run app.py --server.port 8501
```

### 4. Atidaryti naršyklėje

```
http://localhost:8501
```

## 📞 Naudojimas

1. **Call Tab** - Pagrindinė sąsaja
   - Įveskite telefono numerį
   - Spauskite "📞 Skambinti"
   - Kalbėkitės su agentu
   - Dešinėje matykite agento būseną

2. **Monitor Tab** - Monitoring
   - Token usage ir cost
   - Workflow graph
   - RAG dokumentai
   - LLM calls istorija
   - Full state debug

3. **Settings Tab** - Nustatymai
   - Modelių pasirinkimas (coming soon)
   - Kalbos pasirinkimas
   - Debug režimas

4. **Docs Tab** - Dokumentacija
   - LT ir EN versijos
   - API info
   - FAQ

## 🔧 Troubleshooting

### Import Error: No module named 'graph'

Patikrinkite ar `app.py` teisingai prideda path:
```python
current_dir = Path(__file__).parent
src_dir = current_dir.parent.parent  # Turi rodyti į chatbot_core/src/
sys.path.insert(0, str(src_dir))
```

### Chatbot nepasiekiamas

1. Patikrinkite ar `chatbot_core` veikia (paleiskite `cli_chat1.py`)
2. Patikrinkite ar database egzistuoja
3. Patikrinkite environment variables (API keys)

## 📋 TODO

- [ ] Token tracking integration
- [ ] RAG document logging
- [ ] LLM calls logging
- [ ] Model switching
- [ ] Mermaid graph rendering
- [ ] Export conversation
- [ ] Multiple sessions

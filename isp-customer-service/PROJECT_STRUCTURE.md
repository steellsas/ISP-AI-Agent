"""
ISP CUSTOMER SERVICE PROJECT STRUCTURE - COMPLETE SETUP
========================================================

Project: isp-customer-service
Location: c:\Users\steel\turing_projects\support_bot_V2\anplien-AE.3.5\isp-customer-service

Full Directory Tree:
"""

isp-customer-service/
│
├── 📄 Root Configuration Files
│   ├── pyproject.toml              # Project dependencies and metadata
│   ├── uv.lock                     # UV lock file
│   ├── .env                        # Environment variables (local)
│   ├── .env.exemple                # Example environment file
│   ├── .python-version             # Python version specification
│   ├── .gitignore                  # Git ignore rules
│   └── README.md                   # Project documentation
│
├── 📂 chatbot_core/                # Main Chatbot Application
│   ├── cli_chat.py                 # CLI interface for testing
│   ├── pyproject.toml              # Core package dependencies
│   │
│   ├── src/                        # Source code
│   │   ├── __init__.py
│   │   │
│   │   ├── config/                 # Configuration Module
│   │   │   ├── __init__.py
│   │   │   ├── config.py           # Configuration loader
│   │   │   ├── config.yaml         # Main config file
│   │   │   ├── messages.yaml       # Message templates
│   │   │   ├── problem_types.yaml  # Problem type definitions
│   │   │   ├── troubleshooting_mappings.yaml  # Scenario mappings
│   │   │   └── old/                # Legacy configs
│   │   │
│   │   ├── graph/                  # LangGraph Workflow
│   │   │   ├── __init__.py
│   │   │   ├── state.py            # Pydantic State schema
│   │   │   ├── graph.py            # LangGraph workflow definition
│   │   │   ├── structure_flow.md   # Flow documentation
│   │   │   │
│   │   │   ├── nodes/              # Workflow Nodes
│   │   │   │   ├── __init__.py
│   │   │   │   ├── greeting.py     # Static greeting node
│   │   │   │   ├── problem_capture.py  # LLM loop for problem
│   │   │   │   ├── phone_lookup.py # CRM customer lookup
│   │   │   │   ├── address_confirmation.py  # Address confirmation
│   │   │   │   ├── address_search.py  # Address search
│   │   │   │   ├── diagnostics.py  # Network diagnostics
│   │   │   │   ├── inform_provider_issue.py  # Provider issue message
│   │   │   │   ├── troubleshooting.py  # RAG + LLM troubleshooting
│   │   │   │   ├── create_ticket.py  # Ticket creation
│   │   │   │   └── closing.py      # Farewell message
│   │   │   │
│   │   │   └── edges/              # Node connections
│   │   │
│   │   ├── services/               # External Service Wrappers
│   │   │   ├── __init__.py
│   │   │   ├── config_loader.py    # Configuration loading
│   │   │   ├── crm.py              # CRM service wrapper
│   │   │   ├── network.py          # Network diagnostics wrapper
│   │   │   ├── prompt_loader.py    # Prompt loading
│   │   │   ├── custom_mcp_client.py # MCP client
│   │   │   ├── mcp_service.py      # MCP service integration
│   │   │   │
│   │   │   └── llm/                # LLM Service
│   │   │       ├── __init__.py
│   │   │       ├── llm_service.py  # LiteLLM wrapper
│   │   │       └── ...
│   │   │
│   │   ├── rag/                    # RAG Implementation
│   │   │   ├── __init__.py
│   │   │   ├── embeddings.py       # Sentence transformers
│   │   │   ├── vector_store.py     # FAISS vector store
│   │   │   ├── retriever.py        # RAG retriever
│   │   │   ├── scenario_loader.py  # YAML scenario loading
│   │   │   │
│   │   │   ├── knowledge_base/     # Knowledge Base Content
│   │   │   │   ├── troubleshooting/
│   │   │   │   │   ├── *.md files  # Markdown documentation
│   │   │   │   │   └── scenarios/  # YAML troubleshooting scenarios
│   │   │   │   │       ├── internet_no_connection.yaml
│   │   │   │   │       ├── internet_slow.yaml
│   │   │   │   │       └── tv_no_signal.yaml
│   │   │   │   ├── procedures/     # Procedure documentation
│   │   │   │   └── faq/            # FAQ content
│   │   │   │
│   │   │   ├── vector_store_data/  # FAISS index files
│   │   │   └── scripts/
│   │   │       └── build_kb.py     # Knowledge base builder
│   │   │
│   │   ├── locales/                # Localization Module
│   │   │   ├── __init__.py
│   │   │   ├── loader.py           # Locale loader
│   │   │   └── translations/       # Translation files
│   │   │
│   │   └── prompts/                # LLM Prompt Templates
│   │       ├── problem_capture/    # Problem capture prompts
│   │       ├── shared/             # Shared prompt templates
│   │       └── troubleshooting/    # Troubleshooting prompts
│   │
│   ├── streamlit_ui/               # Web UI (Streamlit)
│   │   ├── app.py                  # Main Streamlit app
│   │   ├── README.md               # UI documentation
│   │   ├── requirements.txt        # UI specific requirements
│   │   │
│   │   ├── components/             # UI Components
│   │   └── ui_utils/               # UI Utilities
│   │
│   ├── tests/                      # Unit Tests
│   │   ├── __init__.py
│   │   ├── run_tests.py            # Test runner
│   │   ├── test_routers.py         # Router tests
│   │   ├── test_workflow_integration.py  # Integration tests
│   │   ├── test_config_loaders.py  # Config loader tests
│   │   ├── test_direct_subprocess.py
│   │   ├── test_env.py             # Environment tests
│   │   ├── test_mcp_simple.py      # MCP tests
│   │   └── test_mcp_tools.py       # MCP tool tests
│   │
│   ├── RAG_TESTING.md              # RAG testing documentation
│   └── cli_chat1.py                # Alternative CLI
│
├── 📂 crm_service/                 # CRM MCP Server
│   ├── pyproject.toml              # CRM service dependencies
│   ├── logs/                       # Service logs
│   │
│   ├── src/
│   │   ├── __init__.py
│   │   │
│   │   ├── crm_mcp/                # MCP Server Implementation
│   │   │   ├── __init__.py
│   │   │   ├── server.py           # MCP server
│   │   │   └── tools/              # MCP tools
│   │   │       ├── customer_lookup.py
│   │   │       └── tickets.py
│   │   │
│   │   └── repository/             # Data Access Layer
│   │       ├── __init__.py
│   │       ├── customer_repo.py    # Customer repository
│   │       └── ticket_repo.py      # Ticket repository
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_crm_standalone.py
│   │   ├── test_mcp_protocol.py
│   │   └── test_phone_lookup.py
│   │
│   └── README.md                   # CRM service documentation
│
├── 📂 network_diagnostic_service/  # Network Diagnostics MCP Server
│   ├── pyproject.toml              # Network service dependencies
│   ├── logs/                       # Service logs
│   │
│   ├── src/
│   │   ├── __init__.py
│   │   │
│   │   ├── network_diagnostic_mcp/ # MCP Server Implementation
│   │   │   ├── __init__.py
│   │   │   └── tools/
│   │   │       ├── connectivity_tests.py
│   │   │       ├── outage_checks.py
│   │   │       └── port_diagnostics.py
│   │   │
│   │   └── repository/             # Data Access Layer
│   │       ├── __init__.py
│   │       └── ...
│   │
│   ├── tests/
│   │   └── __init__.py
│   │
│   └── README.md                   # Network service documentation
│
├── 📂 shared/                      # Shared Module
│   ├── main.py                     # Shared main module
│   ├── pyproject.toml              # Shared dependencies
│   ├── README.md                   # Shared documentation
│   │
│   └── src/
│       ├── __init__.py
│       │
│       ├── database/               # Database utilities
│       │   └── __init__.py
│       │
│       ├── isp_types/              # ISP data types
│       │   └── __init__.py
│       │
│       └── utils/                  # Utilities
│           └── __init__.py
│
├── 📂 database/                    # Database Management
│   ├── isp_database.db             # SQLite database (runtime)
│   │
│   ├── schema/                     # Database Schemas
│   │   ├── crm_schema.sql          # CRM tables schema
│   │   └── network_schema.sql      # Network tables schema
│   │
│   ├── seeds/                      # Sample Data
│   │   ├── customers.sql           # Sample customers
│   │   ├── addresses.sql           # Sample addresses
│   │   ├── service_plans.sql       # Sample plans
│   │   ├── equipment.sql           # Sample equipment
│   │   └── network.sql             # Sample network data
│   │
│   └── migrations/                 # Database migrations
│
├── 📂 scripts/                     # Utility Scripts
│   ├── setup_db.py                 # Database setup script
│   ├── seed_data.py                # Data seeding
│   ├── test_crm_service.py         # CRM service testing
│   └── test_network_service.py     # Network service testing
│
├── 📂 docs/                        # Documentation
│   ├── Architecture.md             # Architecture documentation
│   └── ...
│
└── 📄 Other
    ├── main.py                     # Project main entry
    ├── cli_chat.py                 # CLI chat interface
    ├── dabartine_SChema.md         # Current schema documentation
    └── .pytest_cache/              # Pytest cache

═════════════════════════════════════════════════════════════════

KEY COMPONENTS SUMMARY:

1. WORKFLOW (LangGraph):
   ✓ greeting → problem_capture → phone_lookup → address_confirmation/search
   → diagnostics → inform_provider_issue/troubleshooting → create_ticket → closing

2. STATE MANAGEMENT (Pydantic):
   ✓ Conversation state (messages, node tracking)
   ✓ Customer state (phone, ID, addresses)
   ✓ Problem state (type, description)
   ✓ Workflow control flags
   ✓ Diagnostics results
   ✓ Troubleshooting progress
   ✓ Ticket management

3. LLM INTEGRATION (LiteLLM):
   ✓ Multi-provider support
   ✓ Lithuanian language support
   ✓ Context-aware responses

4. RAG SYSTEM (FAISS + Sentence Transformers):
   ✓ Multilingual embeddings
   ✓ Vector store for scenarios
   ✓ Scenario retrieval
   ✓ Knowledge base management

5. DATABASE (SQLite):
   ✓ Customers table
   ✓ Addresses table
   ✓ Service plans
   ✓ Equipment inventory
   ✓ Network infrastructure
   ✓ Tickets and activities
   ✓ Outages and events

6. MCP SERVERS:
   ✓ CRM MCP Server (port 8001)
   ✓ Network Diagnostic MCP Server (port 8002)

7. INTERFACES:
   ✓ CLI chat interface
   ✓ Streamlit web UI

═════════════════════════════════════════════════════════════════

SETUP STATUS:
✅ Directory structure created
✅ Core node implementations created
✅ Configuration files created
✅ Database schema created
✅ Sample data files created
✅ MCP servers set up
✅ Documentation created

READY FOR:
• Database initialization: python scripts/setup_db.py
• CLI testing: cd chatbot_core && uv run python cli_chat.py --phone "+37060012345"
• Web UI: cd chatbot_core/streamlit_ui && streamlit run app.py
• Unit tests: cd chatbot_core && uv run pytest tests/

═════════════════════════════════════════════════════════════════
"""

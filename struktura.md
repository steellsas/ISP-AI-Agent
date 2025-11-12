isp-customer-service/
│
├── chatbot-core/
│   ├── src/
│   │   ├── graph/              # LangGraph nodes & edges
│   │   │   ├── __init__.py
│   │   │   ├── state.py        # ConversationState schema
│   │   │   ├── nodes/
│   │   │   │   ├── greeting.py
│   │   │   │   ├── customer_identification.py
│   │   │   │   ├── check_history.py
│   │   │   │   ├── problem_identification.py
│   │   │   │   ├── diagnostics.py
│   │   │   │   ├── troubleshooting.py
│   │   │   │   ├── ticket_registration.py
│   │   │   │   └── resolution.py
│   │   │   └── graph.py        # Main graph definition
│   │   │
│   │   ├── rag/                # RAG system
│   │   │   ├── knowledge_base/ # Markdown docs
│   │   │   │   ├── internet_no_connection.md
│   │   │   │   ├── internet_slow.md
│   │   │   │   └── ...
│   │   │   ├── embeddings.py
│   │   │   ├── vector_store.py # FAISS
│   │   │   └── retriever.py
│   │   │
│   │   ├── mcp_client/         # MCP client connections
│   │   │   ├── __init__.py
│   │   │   ├── client.py
│   │   │   └── registry.py     # Tool registry
│   │   │
│   │   ├── ui/                 # Streamlit interface
│   │   │   ├── app.py
│   │   │   ├── components/
│   │   │   └── styles.py
│   │   │
│   │   ├── config/             # Configuration
│   │   │   ├── problems.yaml
│   │   │   ├── prompts_lt.yaml
│   │   │   ├── prompts_en.yaml
│   │   │   └── settings.yaml
│   │   │
│   │   └── utils/
│   │       ├── logging.py
│   │       └── helpers.py
│   │
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
│
├── crm-service/
│   ├── src/
│   │   ├── mcp_server/         # MCP Server
│   │   │   ├── __init__.py
│   │   │   ├── server.py       # Main MCP server
│   │   │   └── tools/          # MCP tools
│   │   │       ├── customer_lookup.py
│   │   │       ├── fuzzy_search.py
│   │   │       ├── history.py
│   │   │       ├── equipment.py
│   │   │       └── tickets.py
│   │   │
│   │   ├── models/             # Database models
│   │   │   ├── __init__.py
│   │   │   ├── customer.py
│   │   │   ├── address.py
│   │   │   ├── service_plan.py
│   │   │   ├── equipment.py
│   │   │   ├── ticket.py
│   │   │   ├── history.py
│   │   │   └── memory.py
│   │   │
│   │   ├── repository/         # Data access layer
│   │   │   ├── __init__.py
│   │   │   ├── customer_repo.py
│   │   │   └── ticket_repo.py
│   │   │
│   │   └── utils/
│   │       ├── fuzzy_match.py  # Levenshtein, etc.
│   │       └── validators.py
│   │
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
│
├── network-diagnostic-service/
│   ├── src/
│   │   ├── mcp_server/         # MCP Server
│   │   │   ├── __init__.py
│   │   │   ├── server.py
│   │   │   └── tools/          # MCP tools
│   │   │       ├── port_check.py
│   │   │       ├── ip_assignment.py
│   │   │       ├── bandwidth.py
│   │   │       ├── area_issues.py
│   │   │       └── signal_quality.py
│   │   │
│   │   ├── models/             # Database models
│   │   │   ├── __init__.py
│   │   │   ├── switch.py
│   │   │   ├── port.py
│   │   │   ├── ip_pool.py
│   │   │   ├── bandwidth_log.py
│   │   │   └── area_outage.py
│   │   │
│   │   ├── diagnostics/        # Diagnostic logic (mock)
│   │   │   ├── __init__.py
│   │   │   ├── mock_responses.py
│   │   │   └── checks.py
│   │   │
│   │   └── repository/
│   │       └── network_repo.py
│   │
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
│
├── shared/
│   ├── src/
│   │   ├── types/              # Shared types
│   │   │   ├── __init__.py
│   │   │   ├── customer.py
│   │   │   ├── ticket.py
│   │   │   └── network.py
│   │   │
│   │   ├── database/           # Database connection
│   │   │   ├── __init__.py
│   │   │   ├── connection.py
│   │   │   └── base.py
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── logger.py
│   │       └── config.py
│   │
│   ├── pyproject.toml
│   └── README.md
│
├── database/
│   ├── migrations/             # Database migrations
│   │   ├── 001_initial_schema.sql
│   │   ├── 002_add_equipment.sql
│   │   └── ...
│   │
│   ├── seeds/                  # Mock data
│   │   ├── customers.sql
│   │   ├── addresses.sql
│   │   ├── network.sql
│   │   └── seed.py
│   │
│   ├── schema/                 # Schema definitions
│   │   ├── crm_schema.sql
│   │   └── network_schema.sql
│   │
│   └── isp_database.db         # SQLite file (gitignored)
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DATABASE_SCHEMA.md
│   └── SETUP.md
│
├── scripts/
│   ├── setup_db.py             # Initialize database
│   ├── seed_data.py            # Load mock data
│   └── run_all.sh              # Start all services
│
├── docker-compose.yml          # Run all services
├── pyproject.toml              # Workspace config
├── .env.example
├── .gitignore
└── README.md


isp-customer-service/  (monorepo)
├── chatbot-core/              # Main conversational bot
├── crm-service/               # CRM + Tickets (combined)
├── network-diagnostic-service/ # Network monitoring
├── shared/                    # Shared utilities, types
├── database/                  # Shared SQLite with schemas
├── docker-compose.yml
└── README.md


┌─────────────────────────────────┐
│   Chatbot Core                  │
│   - LangGraph workflow          │
│   - RAG knowledge base          │
│   - UI (Streamlit)              │
│   - MCP Client                  │
└────────────┬────────────────────┘
             │ MCP Protocol (local/stdio)
    ┌────────┴────────┐
    │                 │
┌───▼──────────┐ ┌───▼────────────────┐
│ CRM Service  │ │ Network Diagnostic │
│ MCP Server   │ │ MCP Server         │
│              │ │                    │
│ - Customers  │ │ - Switch ports     │
│ - Addresses  │ │ - IP assignments   │
│ - Services   │ │ - Bandwidth        │
│ - Equipment  │ │ - Area outages     │
│ - Tickets    │ │ - Signal quality   │
│ - History    │ │                    │
└───┬──────────┘ └───┬────────────────┘
    │                │
    └────────┬───────┘
             │
    ┌────────▼────────┐
    │  SQLite Database│
    │                 │
    │ Schema: crm     │
    │ Schema: network │
    └─────────────────┘
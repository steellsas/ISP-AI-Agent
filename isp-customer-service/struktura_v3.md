# ISP Customer Service Chatbot - Project Structure v3

## Overview
Complete ISP customer service chatbot project built with LangGraph, LiteLLM, and Retrieval-Augmented Generation (RAG).

```
isp-customer-service/
├── chatbot_core/                           # Main chatbot application
│   ├── cli_chat.py                         # CLI interface for testing
│   ├── cli_chat1.py                        # Alternative CLI version
│   ├── pyproject.toml                      # Python dependencies for chatbot_core
│   ├── run_rag_test.py                     # RAG testing script
│   ├── test_config_loaders.py              # Config loader tests
│   ├── test_direct_subprocess.py           # Subprocess tests
│   ├── test_env.py                         # Environment tests
│   ├── test_mcp_simple.py                  # MCP protocol tests
│   ├── test_mcp_tools.py                   # MCP tools tests
│   ├── RAG_TESTING.md                      # RAG testing documentation
│   │
│   ├── src/
│   │   ├── __init__.py
│   │   │
│   │   ├── config/                         # Configuration management
│   │   │   ├── __init__.py
│   │   │   ├── config.py                   # Config loader
│   │   │   ├── config.yaml                 # Main configuration
│   │   │   ├── messages.yaml               # UI messages (multilingual)
│   │   │   ├── problem_types.yaml          # Problem type definitions
│   │   │   ├── troubleshooting_mappings.yaml  # Troubleshooting scenario mappings
│   │   │   └── old/                        # Legacy configurations
│   │   │
│   │   ├── graph/                          # LangGraph workflow
│   │   │   ├── __init__.py
│   │   │   ├── state.py                    # Pydantic State schema
│   │   │   ├── graph.py                    # Workflow definition
│   │   │   ├── structure_flow.md           # Flow documentation
│   │   │   ├
│   │   │   └── nodes/                      # Workflow nodes
│   │   │       ├── __init__.py
│   │   │       ├── greeting.py             # Static greeting node
│   │   │       ├── problem_capture.py      # LLM loop - capture problem
│   │   │       ├── phone_lookup.py         # CRM phone lookup
│   │   │       ├── address_confirmation.py # LLM address confirmation
│   │   │       ├── address_search.py       # LLM address extraction
│   │   │       ├── diagnostics.py          # Network diagnostics
│   │   │       ├── inform_provider_issue.py# Provider issue notification
│   │   │       ├── troubleshooting.py      # RAG + LLM troubleshooting
│   │   │       ├── create_ticket.py        # Ticket creation
│   │   │       └── closing.py              # Closing node
│   │   │
│   │   ├── services/                       # External service wrappers
│   │   │   ├── __init__.py
│   │   │   ├── config_loader.py            # Configuration service
│   │   │   ├── crm.py                      # CRM service wrapper
│   │   │   ├── custom_mcp_client.py        # Custom MCP client
│   │   │   ├── mcp_service.py              # MCP service integration
│   │   │   ├── network.py                  # Network diagnostics wrapper
│   │   │   ├── prompt_loader.py            # Prompt loading service
│   │   │   └── llm/                        # LLM-related services
│   │   │
│   │   ├── rag/                            # Retrieval-Augmented Generation
│   │   │   ├── __init__.py
│   │   │   ├── embeddings.py               # Sentence transformers
│   │   │   ├── retriever.py                # RAG retriever logic
│   │   │   ├── scenario_loader.py          # YAML scenario loader
│   │   │   ├── vector_store.py             # FAISS vector store
│   │   │   ├── knowledge_base/             # Knowledge base documents
│   │   │   │   ├── troubleshooting/        # Troubleshooting guides
│   │   │   │   │   ├── *.md                # Markdown documentation
│   │   │   │   │   └── scenarios/          # YAML scenarios
│   │   │   │   │       ├── internet_no_connection.yaml
│   │   │   │   │       ├── internet_slow.yaml
│   │   │   │   │       └── tv_no_signal.yaml
│   │   │   │   ├── procedures/             # General procedures
│   │   │   │   └── faq/                    # FAQ documents
│   │   │   ├── vector_store_data/          # FAISS index files
│   │   │   └── scripts/
│   │   │       └── build_kb.py             # Knowledge base builder
│   │   │
│   │   └── locales/                        # Internationalization
│   │       ├── __init__.py
│   │       ├── loader.py                   # Translation loader
│   │       └── translations/               # Translation files
│   │
│   ├── streamlit_ui/                       # Web UI (alternative to CLI)
│   │   ├── app.py                          # Main Streamlit app
│   │   ├── README.md                       # UI documentation
│   │   ├── requirements.txt                # UI dependencies
│   │   ├── components/                     # Reusable components
│   │   └── ui_utils/                       # UI utilities
│   │
│   └── tests/                              # Chatbot tests
│       ├── __init__.py
│       ├── run_tests.py                    # Test runner
│       ├── test_routers.py                 # Router tests
│       ├── test_workflow_integration.py    # Integration tests
│       └── __pycache__/
│
├── crm_service/                            # CRM MCP Server
│   ├── pyproject.toml                      # Dependencies
│   ├── test_crm_standalone.py              # Standalone tests
│   ├── test_mcp_protocol.py                # MCP protocol tests
│   ├── test_phone_lookup.py                # Phone lookup tests
│   │
│   ├── src/
│   │   ├── __init__.py
│   │   ├── crm_mcp/
│   │   │   ├── __init__.py
│   │   │   ├── server.py                   # MCP server implementation
│   │   │   └── ...
│   │   ├── repository/
│   │   │   └── ...
│   │   └── __pycache__/
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   └── ...
│   │
│   └── logs/                               # CRM service logs
│
├── network_diagnostic_service/             # Network Diagnostics MCP Server
│   ├── pyproject.toml                      # Dependencies
│   │
│   ├── src/
│   │   ├── __init__.py
│   │   ├── network_diagnostic_mcp/         # MCP server
│   │   ├── repository/                     # Data layer
│   │   └── __pycache__/
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   └── ...
│   │
│   └── logs/                               # Service logs
│
├── shared/                                 # Shared utilities
│   ├── main.py                             # Entry point
│   ├── pyproject.toml                      # Dependencies
│   ├── README.md                           # Documentation
│   │
│   └── src/
│       ├── __init__.py
│       ├── database/                       # Database utilities
│       ├── isp_types/                      # Shared type definitions
│       └── utils/                          # Utility functions
│
├── database/                               # Database schema and seeds
│   ├── migrations/                         # Database migrations
│   ├── schema/
│   │   ├── crm_schema.sql                  # CRM tables
│   │   └── network_schema.sql              # Network tables
│   └── seeds/
│       ├── addresses.sql                   # Sample addresses
│       ├── customers.sql                   # Sample customers
│       ├── equipment.sql                   # Sample equipment
│       ├── network.sql                     # Sample network data
│       └── service_plans.sql               # Service plans
│
├── scripts/                                # Utility scripts
│   ├── seed_data.py                        # Database seeding
│   ├── setup_db.py                         # Database setup
│   ├── test_crm_service.py                 # CRM service testing
│   ├── test_network_service.py             # Network service testing
│   └── test_shared.py                      # Shared utilities testing
│
├── docs/                                   # Documentation
│   └── Architecture.md                     # Architecture documentation
│


├── verify_structure.py                     # Structure verification script
├── pyproject.toml                          # Root dependencies
├── README.md                               # Project documentation
├── PROJECT_STRUCTURE.md                    # Project structure doc
└── dabartine_SChema.md                     # Current schema documentation
```

---

## Core Workflow Architecture

```
┌─────────┐    ┌─────────────────┐    ┌──────────────┐    ┌───────────────────┐
│  START  │───▶│    greeting     │───▶│problem_capture│───▶│   phone_lookup    │
└─────────┘    └─────────────────┘    └──────────────┘    └───────────────────┘
                                              │                     │
                                              │ (loop until         │
                                              │  problem clear)     ▼
                                              │              ┌──────────────┐
                                              │              │ Customer     │
                                              │              │ found?       │
                                              │              └──────────────┘
                                              │                 │       │
                                              │            YES  │       │ NO
                                              │                 ▼       ▼
                                      ┌───────────────────┐  ┌─────────────────┐
                                      │address_confirmation│  │  address_search │
                                      └───────────────────┘  └─────────────────┘
                                              │                      │
                                              │ (confirmed)          │ (found)
                                              ▼                      ▼
                                      ┌───────────────────────────────┐
                                      │         diagnostics           │
                                      │  (check provider issues)      │
                                      └───────────────────────────────┘
                                              │
                              ┌───────────────┴───────────────┐
                              │                               │
                       provider_issue=True            provider_issue=False
                              │                               │
                              ▼                               ▼
                 ┌─────────────────────┐          ┌─────────────────────┐
                 │inform_provider_issue│          │   troubleshooting   │
                 │  (region outage)    │          │ (step-by-step LLM)  │
                 └─────────────────────┘          └─────────────────────┘
                              │                               │
                              │                   ┌───────────┴───────────┐
                              │                   │                       │
                              │           problem_resolved=True   needs_escalation=True
                              │                   │                       │
                              │                   ▼                       ▼
                              │           ┌─────────────────────────────────┐
                              │           │        create_ticket            │
                              │           │  (resolved=silent, escalate=msg)│
                              │           └─────────────────────────────────┘
                              │                           │
                              │                           ▼
                              │                   ┌───────────────┐
                              │                   │    closing    │
                              │                   │ (farewell)    │
                              │                   └───────────────┘
                              │                           │
                              ▼                           ▼
                           ┌─────────────────────────────────┐
                           │              END                │
                           └─────────────────────────────────┘
```

---

## Node Specifications

| Node | Type | Description | Key Features |
|------|------|-------------|--------------|
| **greeting** | Static | Initial greeting | Introduces agent, sets conversational tone |
| **problem_capture** | LLM Loop | Problem definition | Loops until problem type & description clear |
| **phone_lookup** | Deterministic | CRM customer lookup | Finds customer by phone number |
| **address_confirmation** | LLM | Address verification | LLM confirms address with customer |
| **address_search** | LLM + CRM | Address extraction & lookup | Extracts address from text, searches CRM |
| **diagnostics** | Deterministic | Network checks | Tests outages, port status, IP assignment |
| **inform_provider_issue** | Static | Issue notification | Informs about regional outage |
| **troubleshooting** | RAG + LLM | Step-by-step guidance | Uses RAG for scenarios, LLM for instruction |
| **create_ticket** | Deterministic | Ticket registration | Creates ticket (silent or with notification) |
| **closing** | Static | Farewell | Goodbye message based on resolution |

---

## State Schema

```python
class State(BaseModel):
    # Conversation
    conversation_id: str
    messages: Annotated[list[dict], operator.add]
    current_node: str
    
    # Customer
    phone_number: str
    customer_id: str | None
    customer_name: str | None
    customer_addresses: list[dict]
    confirmed_address: str | None
    
    # Problem
    problem_type: Literal["internet", "tv", "phone", "other"] | None
    problem_description: str | None
    
    # Workflow control
    address_confirmed: bool | None
    address_search_successful: bool | None
    
    # Diagnostics
    diagnostics_completed: bool
    provider_issue_detected: bool
    diagnostic_results: dict
    
    # Troubleshooting
    troubleshooting_scenario_id: str | None
    troubleshooting_current_step: int
    troubleshooting_completed_steps: list
    troubleshooting_needs_escalation: bool
    problem_resolved: bool
    
    # Ticket
    ticket_created: bool
    ticket_id: str | None
    ticket_type: str | None
    
    # End
    conversation_ended: bool
```

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Workflow** | LangGraph | State machine orchestration |
| **State** | Pydantic | Type-safe state management |
| **LLM** | LiteLLM + GPT-4o-mini | Language understanding & generation |
| **Embeddings** | Sentence-Transformers (multilingual) | Vector embeddings for RAG |
| **Vector Store** | FAISS | Efficient similarity search |
| **Knowledge Base** | YAML + Markdown | Structured troubleshooting scenarios |
| **Database** | SQLite | Customer & equipment data |
| **Web UI** | Streamlit | Alternative interface |
| **CLI** | Python Click/Typer | Testing interface |
| **Internationalization** | Custom YAML loader | Multilingual support |

---

## Troubleshooting Flow (Detailed)

```
┌─────────────────────────────────────────────────────────────────┐
│                    TROUBLESHOOTING NODE                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  First time?      │
                    └─────────┬─────────┘
                         YES  │  NO
                              │   │
              ┌───────────────┘   └───────────────┐
              ▼                                   ▼
    ┌─────────────────┐                 ┌─────────────────┐
    │ RAG: Select     │                 │ Get user        │
    │ scenario        │                 │ response        │
    └─────────────────┘                 └─────────────────┘
              │                                   │
              ▼                                   ▼
    ┌─────────────────┐                 ┌─────────────────┐
    │ Load YAML       │                 │ Check goodbye   │
    │ scenario        │                 │ phrases         │
    └─────────────────┘                 └─────────────────┘
              │                                   │
              ▼                                   ▼
    ┌─────────────────┐                 ┌─────────────────┐
    │ Format first    │                 │ LLM: Analyze    │
    │ step (LLM)      │                 │ with context    │
    └─────────────────┘                 └─────────────────┘
              │                                   │
              ▼                           ┌───────┴───────┐
    ┌─────────────────┐                   │               │
    │ Return step     │           needs_substep    branch_selected
    │ instruction     │                   │               │
    └─────────────────┘                   ▼               ▼
                                  ┌───────────┐   ┌───────────────┐
                                  │ Ask next  │   │ action=       │
                                  │ substep   │   │ resolved/     │
                                  └───────────┘   │ escalate/     │
                                                  │ next_step     │
                                                  └───────────────┘
```

**Key Features:**
- Phone-friendly: One action at a time
- Context-aware: LLM sees full conversation history
- Goodbye detection: Recognizes farewell phrases
- Flexible branching: YAML scenarios with multiple branches

---

## Ticket Logic

| Scenario | Ticket Type | Actions |
|----------|------------|---------|
| Problem resolved | `resolved` | Silent ticket creation, farewell |
| Needs technician | `technician_visit` | Notify customer, create ticket |
| Scenario not found | `escalation` | Notify customer, create ticket |

---

## Setup & Usage

### Installation
```bash
cd chatbot_core
uv pip install -e .
```

### Testing with Known Number
```bash
cd chatbot_core
uv run python cli_chat.py --phone "+37060012345"
```

### Rebuild RAG Knowledge Base
```bash
cd chatbot_core
uv run python src/rag/scripts/build_kb.py
```

### Database Setup
```bash
cd scripts
python setup_db.py
python seed_data.py
```

---

## Configuration Files

### `config.yaml` - Main Configuration
Contains LLM settings, service endpoints, debug flags.

### `messages.yaml` - UI Messages
Multilingual messages for greeting, prompts, errors.

### `problem_types.yaml` - Problem Types
Supported problem categories: internet, tv, phone, other.

### `troubleshooting_mappings.yaml` - RAG Mappings
Maps problem types to YAML scenario files.

---

## Service Architecture

### MCP Servers
- **CRM Service**: Customer lookups, ticket creation
- **Network Service**: Diagnostics, outage checks

### Integration Points
- **LLM Service**: LiteLLM for model calls
- **RAG Service**: Vector search for troubleshooting
- **Config Service**: Centralized configuration management

---

## File Naming Conventions

- **Nodes**: `{node_name}.py` (e.g., `greeting.py`)
- **Edges**: `edge_{from}_{to}.py` or logic in `graph.py`
- **Tests**: `test_{module}.py`
- **Scenarios**: `{problem_type}.yaml`
- **Knowledge Base**: Structured by category (troubleshooting, procedures, faq)

---

## Environment Variables

```
LITELLM_API_KEY=...
LITELLM_API_BASE=...
DATABASE_URL=...
DEBUG=false
```

---

## Development Workflow

1. **Modify node logic** → Update corresponding file in `nodes/`
2. **Update RAG** → Modify YAML scenarios in `knowledge_base/`
3. **Rebuild index** → Run `build_kb.py`
4. **Test flow** → Use CLI or Streamlit UI
5. **Verify state** → Check `verify_structure.py` output

---

## Project Statistics

- **Total Nodes**: 10
- **Service Integrations**: 2 (CRM, Network)
- **Knowledge Base Categories**: 3+ (troubleshooting, procedures, FAQ)
- **Supported Languages**: 1+ (Lithuanian + expandable)
- **Database Tables**: 5+ (customers, equipment, network, tickets, service_plans)


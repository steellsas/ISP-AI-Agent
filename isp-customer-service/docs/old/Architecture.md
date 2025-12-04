# System Architecture

## Overview

ISP Customer Service Chatbot is built using a microservices architecture with MCP (Model Context Protocol) for inter-service communication.

## Architecture Diagram

```
┌─────────────────────────────────┐
│   Chatbot Core                  │
│   - LangGraph workflow          │
│   - RAG knowledge base          │
│   - Streamlit UI                │
│   - MCP Client                  │
└────────────┬────────────────────┘
             │ MCP Protocol (stdio)
    ┌────────┴────────┐
    │                 │
┌───▼──────────┐ ┌───▼────────────────┐
│ CRM Service  │ │ Network Diagnostic │
│ MCP Server   │ │ MCP Server         │
└───┬──────────┘ └───┬────────────────┘
    │                │
    └────────┬───────┘
             │
    ┌────────▼────────┐
    │  SQLite Database│
    │  - crm schema   │
    │  - network schema│
    └─────────────────┘
```

## Services

### 1. Chatbot Core
**Responsibility**: Conversational flow and user interaction

**Technology**:
- LangGraph for state machine
- LangChain for LLM interactions
- FAISS for RAG vector store
- Streamlit for UI

**Key Components**:
- 8-node workflow graph
- Config-driven problem types
- RAG knowledge base
- MCP client for tool calling

### 2. CRM Service
**Responsibility**: Customer data management

**Technology**:
- MCP Server
- SQLAlchemy ORM
- Levenshtein for fuzzy matching

**Key Components**:
- Customer lookup tools
- Fuzzy search algorithms
- Ticket management
- History tracking

### 3. Network Diagnostic Service
**Responsibility**: Network monitoring and diagnostics

**Technology**:
- MCP Server
- Mock diagnostic logic (Phase 1)
- Real API integration (Future)

**Key Components**:
- Port status checks
- IP/MAC validation
- Bandwidth measurement
- Area outage detection

### 4. Shared Package
**Responsibility**: Common utilities

**Components**:
- Database connection manager
- Shared type definitions
- Common utilities
- Logger configuration

## Data Flow

### Typical Conversation Flow

1. **User initiates** → Chatbot UI
2. **Greeting** → Check for caller ID
3. **Customer ID** → Call CRM lookup tools via MCP
4. **Check History** → Load previous issues via CRM
5. **Problem ID** → User describes issue
6. **Diagnostics** → Call Network diagnostic tools via MCP
7. **Decision**: Provider issue OR Customer issue
8. **If Customer issue** → Troubleshooting with RAG
9. **Ticket Registration** → Create via CRM tools
10. **Resolution** → Final message, save conversation

## Communication Protocol

### MCP (Model Context Protocol)

**Why MCP?**
- Standardized tool calling
- Auto-discovery of tools
- Easy to add new services
- Local or remote connections

**Connection Type**: stdio (local processes)

**Tool Discovery**: Automatic on startup

## Database Design

### Schemas

**CRM Schema**:
- customers
- addresses
- service_plans
- customer_equipment
- tickets
- customer_history
- customer_memory
- conversations

**Network Schema**:
- switches
- ports
- ip_assignments
- bandwidth_logs
- area_outages
- signal_quality

**Relationships**:
- `crm.customer_equipment.mac_address` ↔ `network.ports.equipment_mac`
- `crm.customers.customer_id` ↔ `network.ports.customer_id`

## Scalability

### Current (Phase 1)
- All services run locally
- Single SQLite database
- stdio MCP connections

### Future
- Services can be deployed separately
- Switch to PostgreSQL for production
- Remote MCP connections (WebSocket/SSE)
- Independent scaling per service

## Security

### Current
- Local-only access
- No authentication needed

### Future (Production)
- JWT authentication for MCP
- API keys for external services
- Encrypted database
- Rate limiting

## Extensibility

### Adding New Problem Types
1. Add entry to `problems.yaml`
2. Create RAG document
3. Add tools if needed (via new MCP server)
4. No code changes required!

### Adding New Services
1. Create new MCP server
2. Register tools
3. Chatbot auto-discovers
4. Ready to use!

## Technology Choices

| Component | Technology | Why? |
|-----------|-----------|------|
| Workflow | LangGraph | State machine, conditional edges, great for complex flows |
| LLM | Anthropic Claude | Best reasoning, Lithuanian support |
| RAG | FAISS | Fast, local, no external dependencies |
| MCP | stdio | Simple, local, perfect for development |
| Database | SQLite | Easy setup, sufficient for mock data |
| UI | Streamlit | Rapid prototyping, easy to use |
| Package Manager | UV | Fast, modern, workspace support |

## Monitoring

### LangSmith Integration
- Trace all LLM calls
- Monitor latency
- Debug flows
- Track costs

### Logging
- Structured logging
- Session logs
- Error tracking
- Performance metrics
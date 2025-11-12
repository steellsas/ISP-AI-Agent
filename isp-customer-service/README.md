# ISP Customer Service Chatbot

Intelligent customer service chatbot for ISP (Internet Service Provider) using LangGraph, MCP servers, and Agentic RAG.

## 🏗️ Architecture

This is a **microservices-based** monorepo with the following components:

### Services

- **chatbot-core**: Main conversational bot with LangGraph workflow orchestration
- **crm-service**: Customer data, equipment, tickets, and history management (MCP Server)
- **network-diagnostic-service**: Network monitoring and diagnostics (MCP Server)
- **shared**: Shared utilities, types, and database connection

### Communication

All services communicate via **MCP (Model Context Protocol)** with local stdio connections.

## 📋 Features

### Core Capabilities
- ✅ **Multi-step customer identification** with fuzzy matching
- ✅ **Customer history check** for recurring issues
- ✅ **Automated network diagnostics** (provider-side checks)
- ✅ **Interactive troubleshooting** with RAG-powered solutions
- ✅ **Intelligent ticket creation** (network issues, resolved, technician visits)
- ✅ **Lithuanian language support**

### Technical Features
- ✅ **Config-driven problem types** (easy to extend)
- ✅ **Agentic RAG** for troubleshooting knowledge
- ✅ **Multi-model support** (Claude, GPT-4, Gemini)
- ✅ **Memory system** (short-term and long-term)
- ✅ **Learning from patterns** (auto-update RAG)
- ✅ **LangSmith observability**
- ✅ **Token tracking and cost calculation**

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [UV package manager](https://github.com/astral-sh/uv)
- Anthropic API key (for Claude)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd isp-customer-service
```

2. **Install dependencies with UV**
```bash
# Install UV if you haven't
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all workspace dependencies
uv sync
```

3. **Setup environment variables**
```bash
cp .env.example .env
# Edit .env and add your API keys
```

4. **Initialize database**
```bash
uv run python scripts/setup_db.py
uv run python scripts/seed_data.py
```

5. **Start the chatbot**
```bash
uv run streamlit run chatbot-core/src/ui/app.py
```

## 📁 Project Structure

```
isp-customer-service/
├── chatbot-core/              # Main bot
│   ├── src/
│   │   ├── graph/             # LangGraph nodes & workflow
│   │   ├── rag/               # RAG knowledge base
│   │   ├── mcp_client/        # MCP client connections
│   │   ├── ui/                # Streamlit interface
│   │   └── config/            # YAML configs
│   └── tests/
│
├── crm-service/               # CRM MCP Server
│   ├── src/
│   │   ├── mcp_server/        # MCP server & tools
│   │   ├── models/            # Database models
│   │   └── repository/        # Data access layer
│   └── tests/
│
├── network-diagnostic-service/ # Network MCP Server
│   ├── src/
│   │   ├── mcp_server/        # MCP server & tools
│   │   ├── models/            # Database models
│   │   └── diagnostics/       # Mock diagnostic logic
│   └── tests/
│
├── shared/                    # Shared utilities
│   └── src/
│       ├── types/             # Shared types
│       ├── database/          # DB connection
│       └── utils/             # Common utilities
│
├── database/                  # Database files
│   ├── schema/                # SQL schemas
│   ├── migrations/            # Migrations
│   └── seeds/                 # Mock data
│
├── docs/                      # Documentation
└── scripts/                   # Utility scripts
```

## 🔧 Development

### Running Tests
```bash
# Run all tests
uv run pytest

# Run tests for specific service
uv run pytest chatbot-core/tests/
uv run pytest crm-service/tests/
```

### Code Formatting
```bash
# Format code with black
uv run black .

# Lint with ruff
uv run ruff check .
```

### Type Checking
```bash
uv run mypy chatbot-core/src/
```

## 📚 Documentation

- [Architecture](docs/ARCHITECTURE.md) - Detailed system architecture
- [Database Schema](docs/DATABASE_SCHEMA.md) - Database structure
- [API Documentation](docs/API.md) - MCP tools documentation
- [Configuration Guide](docs/CONFIGURATION.md) - How to add problem types, prompts, etc.

## 🎯 Roadmap

### Phase 1 (Current): MVP
- [x] Project setup
- [ ] Database schema
- [ ] CRM MCP Server
- [ ] Network Diagnostic MCP Server
- [ ] Basic LangGraph flow
- [ ] RAG knowledge base
- [ ] Streamlit UI

### Phase 2: Full Features
- [ ] Multi-model support
- [ ] Memory & learning
- [ ] Feedback system
- [ ] Advanced analytics

### Phase 3: Production
- [ ] Voice integration prep
- [ ] Cloud deployment
- [ ] Scaling & optimization

## 📝 License

MIT

## 🤝 Contributing

Contributions welcome! Please read CONTRIBUTING.md for guidelines.

## 📧 Contact

For questions or support, contact: andrius@example.com
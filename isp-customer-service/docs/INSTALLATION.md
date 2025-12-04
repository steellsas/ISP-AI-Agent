# Installation Guide

Setup and deployment instructions.

## Table of Contents

- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Detailed Installation](#detailed-installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Development Setup](#development-setup)
- [Troubleshooting](#troubleshooting)

---

## Requirements

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.10 | 3.11+ |
| RAM | 4 GB | 8 GB |
| Disk | 2 GB | 5 GB |
| OS | Linux, macOS, Windows | Linux/macOS |

### API Keys (at least one required)

| Provider | Environment Variable | Get Key |
|----------|---------------------|---------|
| Anthropic | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| OpenAI | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |
| Google | `GOOGLE_API_KEY` | [makersuite.google.com](https://makersuite.google.com) |

---

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/your-org/isp-chatbot.git
cd isp-chatbot

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -e .

# 4. Set up environment
cp .env.example .env
# Edit .env and add your API key(s)

# 5. Initialize database
python scripts/init_database.py

# 6. Run the demo
streamlit run streamlit_ui/app.py
```

---

## Detailed Installation

### Step 1: Clone Repository

```bash
git clone https://github.com/your-org/isp-chatbot.git
cd isp-chatbot
```

### Step 2: Python Environment

**Using venv (recommended):**
```bash
python -m venv venv
source venv/bin/activate
```

**Using conda:**
```bash
conda create -n isp-chatbot python=3.11
conda activate isp-chatbot
```

**Using poetry:**
```bash
poetry install
poetry shell
```

### Step 3: Install Dependencies

**Standard installation:**
```bash
pip install -e .
```

**With development dependencies:**
```bash
pip install -e ".[dev]"
```

**Manual installation:**
```bash
pip install -r requirements.txt
```

### Step 4: Environment Configuration

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Required: At least one LLM API key
ANTHROPIC_API_KEY=sk-ant-api03-...
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...

# Optional: Database path
DATABASE_PATH=./database/isp_database.db

# Optional: Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/chatbot.log

# Optional: RAG settings
RAG_KNOWLEDGE_BASE_PATH=./knowledge_base
```

### Step 5: Initialize Database

```bash
# Create demo database with sample data
python scripts/init_database.py

# Or with custom path
python scripts/init_database.py --db-path ./my_database.db
```

**Sample data includes:**
- 5 demo customers
- Service records
- Equipment records
- Sample tickets

### Step 6: Build RAG Index

```bash
# Index knowledge base documents
python scripts/build_rag_index.py

# With custom settings
python scripts/build_rag_index.py \
    --kb-path ./knowledge_base \
    --output ./data/faiss_index
```

---

## Configuration

### Directory Structure

```
isp-chatbot/
├── .env                    # Environment variables
├── pyproject.toml          # Project configuration
├── src/
│   ├── config/
│   │   ├── config.yaml     # General settings
│   │   ├── messages.yaml   # Response templates
│   │   └── locales/        # Translations
│   ├── graph/              # LangGraph workflow
│   ├── services/           # LLM, MCP, RAG services
│   └── rag/                # RAG components
├── crm_service/            # CRM MCP server
├── knowledge_base/         # Troubleshooting docs
├── streamlit_ui/           # Demo interface
├── database/               # SQLite database
├── logs/                   # Log files
└── data/                   # FAISS index
```

### Config Files

**config.yaml** — Main settings:
```yaml
app:
  default_language: "lt"

llm:
  default_provider: "anthropic"
  default_model: "claude-3-5-sonnet-20241022"
  temperature: 0.3

rag:
  enabled: true
  top_k: 5
  similarity_threshold: 0.5
```

**messages.yaml** — Response templates (see [CONFIGURATION.md](CONFIGURATION.md))

---

## Running the Application

### Demo UI (Streamlit)

```bash
# Standard run
streamlit run streamlit_ui/app.py

# Custom port
streamlit run streamlit_ui/app.py --server.port 8080

# With auto-reload
streamlit run streamlit_ui/app.py --server.runOnSave true
```

Access at: `http://localhost:8501`

### CLI Interface

```bash
# Interactive chat
python cli_chat.py

# With phone number
python cli_chat.py --phone "+37060000000"

# With specific language
python cli_chat.py --language en
```

### MCP Servers

```bash
# Start CRM service (in separate terminal)
python -m crm_service.src.crm_mcp.server

# With custom database
DB_PATH=./custom.db python -m crm_service.src.crm_mcp.server
```

---

## Development Setup

### Install Dev Dependencies

```bash
pip install -e ".[dev]"
```

### Pre-commit Hooks

```bash
pre-commit install
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src

# Specific test file
pytest tests/test_graph.py

# Verbose
pytest -v
```

### Code Formatting

```bash
# Format with black
black src/ tests/

# Sort imports
isort src/ tests/

# Lint with ruff
ruff check src/
```

### Type Checking

```bash
mypy src/
```

---

## Troubleshooting

### Common Issues

#### API Key Not Found

```
Error: ANTHROPIC_API_KEY not set
```

**Solution:**
1. Check `.env` file exists
2. Verify key format: `ANTHROPIC_API_KEY=sk-ant-...`
3. Restart application after changing `.env`

#### Database Not Found

```
Error: Database file not found
```

**Solution:**
```bash
python scripts/init_database.py
```

#### RAG Index Missing

```
Error: FAISS index not found
```

**Solution:**
```bash
python scripts/build_rag_index.py
```

#### Import Errors

```
ModuleNotFoundError: No module named 'src'
```

**Solution:**
```bash
pip install -e .
```

#### Streamlit Port in Use

```
Error: Port 8501 already in use
```

**Solution:**
```bash
streamlit run streamlit_ui/app.py --server.port 8502
```

### Logs

Check logs for detailed errors:

```bash
# View recent logs
tail -f logs/chatbot.log

# Search for errors
grep -i error logs/chatbot.log
```

### Debug Mode

Enable debug logging:

```bash
# In .env
LOG_LEVEL=DEBUG
```

Or in code:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Dependencies

### Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | ≥0.2.0 | Workflow orchestration |
| litellm | ≥1.0.0 | Multi-LLM gateway |
| pydantic | ≥2.0.0 | Data validation |
| faiss-cpu | ≥1.7.0 | Vector search |
| sentence-transformers | ≥2.0.0 | Text embeddings |
| streamlit | ≥1.40.0 | Demo UI |
| pyyaml | ≥6.0 | Configuration |

### Dev Dependencies

| Package | Purpose |
|---------|---------|
| pytest | Testing |
| black | Code formatting |
| ruff | Linting |
| mypy | Type checking |
| pre-commit | Git hooks |

### Full Requirements

See `pyproject.toml` or `requirements.txt` for complete list.

---

## Upgrading

### Update Dependencies

```bash
pip install -e . --upgrade
```

### Rebuild RAG Index

After updating knowledge base:

```bash
python scripts/build_rag_index.py --force
```

### Database Migration

```bash
python scripts/migrate_database.py
```

---

## Uninstalling

```bash
# Deactivate virtual environment
deactivate

# Remove directory
cd ..
rm -rf isp-chatbot

# Or just remove venv
rm -rf venv
```

---

*Next: [API_REFERENCE.md](API_REFERENCE.md) — API and function reference*

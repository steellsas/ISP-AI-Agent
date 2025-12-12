# Installation Guide

Detailed setup and deployment instructions.

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.11+ | 3.12 |
| RAM | 4 GB | 8 GB |
| Disk | 2 GB | 5 GB |
| OS | Linux, macOS, Windows | Linux/macOS |

### Required Tools

- **Python 3.11+**
- **[UV](https://github.com/astral-sh/uv)** — Fast Python package manager

### API Keys

At least one LLM provider API key is required:

| Provider | Environment Variable | Get Key |
|----------|---------------------|---------|
| OpenAI | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |
| Google | `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com) |

---

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/TuringCollegeSubmissions/anplien-AE.3.5.git
cd isp-customer-service

# 2. Install UV (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install dependencies
uv sync

# 4. Setup environment
cp .env.example .env
# Edit .env with your API keys

# 5. Initialize database
uv run python scripts/setup_db.py
uv run python scripts/seed_data.py

# 6. Build knowledge base
uv run python -m src.rag.scripts.build_kb

# 7. Run the bot
uv run streamlit run chatbot_core/src/streamlit_ui/app.py
```

---

## Step-by-Step Installation

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd isp-customer-service
```

### Step 2: Install UV Package Manager

**Linux/macOS:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**With pip (alternative):**
```bash
pip install uv
```

**Verify installation:**
```bash
uv --version
```

### Step 3: Install Dependencies

```bash
uv sync
```

UV will automatically:
- Create virtual environment in `.venv/`
- Install all dependencies from `pyproject.toml`
- Lock versions in `uv.lock`

### Step 4: Environment Configuration

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Required: At least one LLM API key
OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...

# Database path (optional)
DATABASE_PATH=./database/isp_database.db

# Logging (optional)
LOG_LEVEL=INFO
LOG_FILE=./logs/chatbot.log

# RAG settings (optional)
RAG_KNOWLEDGE_BASE_PATH=./knowledge_base
```

### Step 5: Initialize Database

```bash
# Create database schema
uv run python scripts/setup_db.py

# Seed with demo data
uv run python scripts/seed_data.py
```

### Step 6: Build Knowledge Base

```bash
uv run python -m src.rag.scripts.build_kb
```

This creates the FAISS index for troubleshooting document search.

---

## Running the Application

### Web UI (Streamlit)

```bash
uv run streamlit run chatbot_core/src/streamlit_ui/app.py
```

Access at: `http://localhost:8501`

### CLI Interface

```bash
# Interactive chat
uv run python -m src.agent.react_agent

# With specific phone number
uv run python -m src.agent.react_agent --phone "+37060012345"
```

## Dependencies

### Core Dependencies

| Package | Purpose |
|---------|---------|
| litellm | Multi-LLM gateway (OpenAI, Anthropic, Google) |
| pydantic | Data validation |
| faiss-cpu | Vector similarity search |
| sentence-transformers | Text embeddings |
| streamlit | Web UI |
| pyyaml | Configuration files |

### Development Dependencies

| Package | Purpose |
|---------|---------|
| pytest | Testing framework |
| ruff | Linting and formatting |

### View All Dependencies

```bash
# List installed packages
uv pip list

# Show dependency tree
uv pip tree
```

---

## Common Commands

### Development

```bash
# Run tests
uv run pytest tests/ -v

# Run specific test
uv run pytest tests/test_scenarios.py::TestScenario01 -v

# Format code
uv run ruff format .

# Lint code
uv run ruff check .
```

### Database

```bash
# Reset database
uv run python scripts/setup_db.py --reset

# View database
uv run python -c "
import sqlite3
conn = sqlite3.connect('database/isp_database.db')
print(conn.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall())
"
```

### Knowledge Base

```bash
# Rebuild index
uv run python -m src.rag.scripts.build_kb --force

# Test search
uv run python -c "
from rag import get_retriever
r = get_retriever()
print(r.retrieve('internetas neveikia'))
"
```

---

## Configuration Options

### LLM Settings

Edit `src/config/config.yaml`:

```yaml
llm:
  default_model: "gpt-4o-mini"
  temperature: 0.3
  max_tokens: 1000
```

### Agent Settings

```yaml
agent:
  max_turns: 20
  language: "lt"  # lt or en
```

### RAG Settings

```yaml
rag:
  top_k: 5
  similarity_threshold: 0.4
  keyword_weight: 0.3
```

---

## Troubleshooting

### UV Not Found

```bash
# Add UV to PATH
export PATH="$HOME/.cargo/bin:$PATH"

# Or reinstall
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Import Errors

```bash
# Ensure virtual environment is active
source .venv/bin/activate

# Or use uv run
uv run python -c "import litellm; print('OK')"
```

### Database Errors

```bash
# Reset database
rm database/isp_database.db
uv run python scripts/setup_db.py
uv run python scripts/seed_data.py
```

### API Key Issues

```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Test API connection
uv run python -c "
import litellm
response = litellm.completion(
    model='gpt-4o-mini',
    messages=[{'role': 'user', 'content': 'Hello'}]
)
print(response.choices[0].message.content)
"
```

### RAG Index Missing

```bash
# Rebuild knowledge base
uv run python -m src.rag.scripts.build_kb --force
```

---

## Updating

### Update Dependencies

```bash
# Update all packages
uv sync --upgrade

# Update specific package
uv add litellm@latest
```

### Update UV

```bash
# Self-update UV
uv self update
```

---


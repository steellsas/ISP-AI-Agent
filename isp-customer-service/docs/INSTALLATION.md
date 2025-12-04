# Installation Guide

Setup and deployment instructions.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Installation](#detailed-installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Development Setup](#development-setup)
- [Troubleshooting](#troubleshooting)

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
- **[UV package manager](https://github.com/astral-sh/uv)** — Fast Python package installer

### API Keys (at least one required)

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

# 3. Install all dependencies
uv sync

# 4. Setup environment variables
cp .env.example .env
# Edit .env and add your API keys

# 5. Initialize database
uv run python scripts/setup_db.py
uv run python scripts/seed_data.py

# 6. Start the chatbot
uv run streamlit run chatbot_core/src/streamlit_ui/app.py
```


---

## Detailed Installation

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

**With pip:**
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
- Create a virtual environment
- Install all dependencies from `pyproject.toml`
- Lock versions in `uv.lock`

### Step 4: Environment Configuration

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Required: At least one LLM API key

 OPENAI_API_KEY=sk-...
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
# Create database schema
uv run python scripts/setup_db.py

# Seed with demo data
uv run python scripts/seed_data.py
```




---

```

### Config Files






Access at: `http://localhost:8501`

### CLI Interface

```bash
# Interactive chat
uv run python chatbot_core/src/cli_chat.py

# With phone number
uv run python chatbot_core/src/cli_chat.py --phone "+37060000000"


```


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
| ruff | Linting & formatting |
| mypy | Type checking |
| pre-commit | Git hooks |

### Full Requirements

See `pyproject.toml` for complete dependency list.

---
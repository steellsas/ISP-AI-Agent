# ISP AI Agent — after-hours voice support

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)
![LangGraph](https://img.shields.io/badge/LangGraph-single_engine-green)
![FastAPI](https://img.shields.io/badge/FastAPI-voice_dashboard-teal)
![License](https://img.shields.io/badge/License-MIT-yellow)

A voice agent for an Internet Service Provider's customers outside business hours. It
answers the call in Lithuanian, identifies the caller, checks the line and the account,
guides the customer through the fix step by step, and — when the problem cannot be solved
by phone or is outside its knowledge — registers the right ticket for the right people.
Every call leaves a contact record.

**Live demo:** [isp-ai-agent-production.up.railway.app](https://isp-ai-agent-production.up.railway.app)

## What it does

- **Identifies the caller** from the phone number or a dictated address, always checking
  the address back before anything about the account is said.
- **Checks level-1 facts** after identification: debt, a mass outage (held until the address
  is confirmed), a node or switch fault, open tickets, the service profile (e.g. IPTV
  runs over the internet).
- **Solves** faults with fault packs — hung router, dead router (with a temporary cable
  bridge to the PC), line down to the flat, CRC errors, a changed router (foreign MAC), a
  customer-side problem (one device, Wi-Fi), an unclear fault — reading telemetry between
  the steps.
- **Registers** what it does not solve: a technician or unclear-fault ticket, or a request
  for the responsible person (billing, disconnection, relocation, a wish); a repeat call
  is a note on the open ticket, not a duplicate.
- **Records** every call: outcome (`resolved`, `ticket`, `ticket_appended`,
  `informed_outage`, `informed_debt`, `abandoned`, …) and whether a person should review it.

## How it works

One conversation engine — a LangGraph of four nodes over one typed, checkpointed state.
LLMs understand the caller, propose next steps and word the replies; the engine plans
every turn, validates every action and runs the tools; the knowledge lives in files.

```
caller ─► ASR ─► perceive ─► decide ─► execute ─► narrate ─► TTS ─► caller
                 understand   policy     tools via   context card → LLM,
                 facts, intent rules →   one gateway  or a locale phrase
                              TurnPlan
knowledge/*.yaml  (intents · fault packs · verdicts · inform · services · ticket types · limits)
locales/lt/       (phrases · vocabulary · examples)   — validated at startup
```

The architecture, decisions and the refactor that produced it:
[`isp-customer-service/docs/refactoring/RESULT.md`](isp-customer-service/docs/refactoring/RESULT.md).

## Repository

| Path | What |
|---|---|
| `isp-customer-service/chatbot_core/src/agent/` | The engine: `perceive/`, `decide/`, `execute/`, `speak/`, `analyst/`, `contract/`, `knowledge/`, `locales/`, `tooling/`, `call_record/`, `graph_v2/` |
| `isp-customer-service/chatbot_core/src/app/` | FastAPI service: sessions, voice WebSocket, archive, the dashboard (`static/`) and demo scenarios (`scenarios.yaml`) |
| `isp-customer-service/crm_service/`, `network_diagnostic_service/` | Demo CRM and network telemetry (tools and MCP servers) |
| `isp-customer-service/database/` | SQLite schema and seeds of the Šiauliai demo world |
| `isp-customer-service/docs/` | Documentation index: [`docs/README.md`](isp-customer-service/docs/README.md) |

## Quick start

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), an OpenAI API key (the
default model is `gpt-4o-mini`); for voice, a Groq key (`ASR_BACKEND=groq`) or local
faster-whisper; TTS is edge-tts by default.

```bash
git clone https://github.com/steellsas/ISP-AI-Agent.git
cd ISP-AI-Agent/isp-customer-service
uv sync
cp .env.exemple .env        # fill OPENAI_API_KEY (and GROQ_API_KEY for voice)
uv run python scripts/setup_db.py && uv run python scripts/seed_data.py
uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080
```

Open http://localhost:8080 — the dashboard:

- **Testavimas** — make a call (voice or text) and watch the agent: the conversation line,
  the path of each turn through the graph with durations, the turn plan, the call state
  and the event timeline.
- **Scenarijai** — the demo calls (who calls, what to say, what to expect); ▶ starts one and
  checks the verdict and the outcome afterwards.
- **Archyvas** — past calls and their contact records, replayed turn by turn; filter the
  ones that need review.

Before a demo, press **♻ DB** (the outage ETA is relative to the reset time).

## Tests

```bash
uv run pytest                                              # unit and integration tests
uv run python chatbot_core/src/agent/eval/run_eval.py      # scripted calls, scored
uv run python scripts/refactor_acceptance.py               # architecture acceptance checks
```

## Documentation

| Document | For |
|---|---|
| [docs/README.md](isp-customer-service/docs/README.md) | Index of all documents |
| [docs/DEMO_SCENARIJAI.md](isp-customer-service/docs/DEMO_SCENARIJAI.md) | Demo calls (Lithuanian) |
| [docs/FAULT_PACKS.md](isp-customer-service/docs/FAULT_PACKS.md) | Writing fault packs and knowledge files (Lithuanian) |
| [docs/refactoring/RESULT.md](isp-customer-service/docs/refactoring/RESULT.md) | Architecture after the refactor, verification, latency |
| [docs/refactoring/ROADMAP.md](isp-customer-service/docs/refactoring/ROADMAP.md) | What is left to fix and build |

## License

MIT. **Andrius** — [GitHub](https://github.com/steellsas)

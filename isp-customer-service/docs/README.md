# Documentation index

> Updated 2026-09-17, after the single-engine refactor (M0–M7). New documents are written in
> English; the Lithuanian working documents below stay Lithuanian.

## Start here

| Document | Purpose |
|---|---|
| [refactoring/RESULT.md](refactoring/RESULT.md) | **The system as it is now**: architecture diagram, what each milestone changed, verification, latency, known limitations |
| [refactoring/ROADMAP.md](refactoring/ROADMAP.md) | What is left to fix and build after the refactor, with evidence and where to start |
| [refactoring/DECISIONS.md](refactoring/DECISIONS.md) | Architecture decisions D-01…D-22 (the "why") |
| [refactoring/REFACTORING_PLAN.md](refactoring/REFACTORING_PLAN.md) | The refactor itself: milestones, status log with every deviation, findings F-1…F-31, owner questions |
| `refactoring/M0_…` … `M7_…` | Step-by-step instructions per milestone (historical: line numbers refer to `develop` @ `c7be3ba`) |
| [refactoring/OWNER_NOTES_dialogue.md](refactoring/OWNER_NOTES_dialogue.md) | How the owner wants the dialogue to behave — input for ROADMAP R-6…R-10 |
| [refactoring/baseline/](refactoring/baseline/) | Eval and latency baseline before the refactor (M0) and the final runs (`final/`) |

## Working documents (Lithuanian)

| Document | Purpose |
|---|---|
| [DEMO_SCENARIJAI.md](DEMO_SCENARIJAI.md) | The demo calls: numbers, what to say, what to expect — also in the dashboard's **Scenarijai** tab (`chatbot_core/src/app/scenarios.yaml`) |
| [FAULT_PACKS.md](FAULT_PACKS.md) | Writing fault packs and the knowledge files (English schema, step roles, locale keys, intents, ticket types, services) |
| [AGENT_ONBOARDING.md](AGENT_ONBOARDING.md) | Customer onboarding questionnaire for a deployment — what goes into which knowledge file |
| [DIALOGO_ETALONAS.md](DIALOGO_ETALONAS.md) | Reference dialogue quality rules |
| [IDENT_TESTAI.md](IDENT_TESTAI.md) | Identification live test scripts |
| [BARGE_IN_TESTAI.md](BARGE_IN_TESTAI.md) | Barge-in live test scripts |
| [TESTU_ZEMELAPIS.md](TESTU_ZEMELAPIS.md) | Map of the test suite by layer |
| [../chatbot_core/src/agent/eval/README.md](../chatbot_core/src/agent/eval/README.md) | The eval harness: scenarios, checks, how to run |

## Tools

| Command (from `isp-customer-service/`) | What |
|---|---|
| `uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080` | The service and the dashboard |
| `uv run pytest` | Unit and integration tests |
| `uv run python chatbot_core/src/agent/eval/run_eval.py [--only ID] [--json out.json]` | Scripted calls, scored |
| `uv run python scripts/refactor_acceptance.py` | Architecture acceptance checks from every milestone's Definition of Done |

## Planned

Programmer guide (engine, modules, file map — start from RESULT.md) · presentation
(Lithuanian) · instructor guide (knowledge files, phrases, policies — start from
FAULT_PACKS.md) · integration and production guide (ticket types → departments, MCP, admin
login, audio retention).

## Archive

[archive/](archive/) — superseded documents describing the pre-refactor engine
(`ReactAgent`, legacy graph, walker/solver, Streamlit UI, old roadmaps, Dec 2025
installation/RAG/tools docs), the old voice plan (`VOICE_PLAN.md`, whose V1/L3a labels
still appear in code comments), the pre-dashboard voice test script
(`TESTAVIMO_SCENARIJUS.md`) and the early prototype demo scenarios
(`archive/chatbot_core/demo_scenarios.md`). Kept for history only.

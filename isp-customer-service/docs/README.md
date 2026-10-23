# Documentation index

> Reorganised 2026-10-15. Documentation is written in English; Lithuanian working documents
> (demo, tests, instructor drafts, live review) stay Lithuanian until they are rewritten.

## Start here

| Document | For | What |
|---|---|---|
| [STATUS.md](STATUS.md) | everyone | **What the agent can do, how far from demo and production, risks, proposed order** |
| [ARCHITECTURE.md](ARCHITECTURE.md) | programmers | **How it works**: call, turn graph, decide and the Case, perceive, speak, every LLM call, models, knowledge files, tools, voice, latency, technical debt |
| [DECISIONS.md](DECISIONS.md) | programmers | Architecture decisions D-01…D-22 — the *why* |
| [ROADMAP.md](ROADMAP.md) | everyone | **What we do next**: demo track (latency, turn detection, engine quality) and production track |

## By folder

| Folder | Documents |
|---|---|
| [demo/](demo/) | `DEMO_PRISTATYMAS.md` — the demo run · `DEMO_SCENARIJAI.md` — the demo calls (also in the dashboard's Scenarijai tab) |
| [instructor/](instructor/) | Drafts for the instructor guide: `ZINIU_BAZE.md` (knowledge-base documents, v2), `AGENT_ONBOARDING.md` (customer questionnaire), `FAULT_PACKS.md` (**outdated: v1 packs**, see STATUS §7) |
| [testing/](testing/) | **How to check and fix (start here): `KAIP_TIKRINTI_IR_TAISYTI.md`** · tests by function: `TESTAI_PAGAL_FUNKCIJAS.md` · live test scripts: `BALSO_TESTAVIMAS.md` (voice), `IDENT_TESTAI.md`, `BARGE_IN_TESTAI.md`; `TESTU_ZEMELAPIS.md` (test map) · eval harness: [../chatbot_core/src/agent/eval/README.md](../chatbot_core/src/agent/eval/README.md) |
| [review/](review/) | The live review: `PERZIURA.md` (findings and principles), `STRUKTURA_V3.md` (phases design), `PROMPTAI.md` (prompt and LLM-parameter change log), `DELSA.md` (latency measurements and levers) |
| [archive/](archive/) | History only: pre-refactor engine docs, the M0–M7 refactor (`archive/refactoring/`), fix waves and RAG planning (`archive/review/`), `AGENTO_VEIKIMAS.md` and `MODELIAI.md` (folded into ARCHITECTURE/STATUS) |

## Planned

1. **Presentation** (Lithuanian) — built from STATUS §2–3.
2. **Instructor guide** — adding a new fault: card → modules → equipment → phrases → tests → eval
   (replaces `instructor/FAULT_PACKS.md`; after the v3 phases settle).
3. **Maintenance guide** — running, tests, eval, logs, knowledge reload, live test rounds
   (merges `testing/`).
4. **Integration and production guide** — adapters, telephony, on-prem models, security, operations.

## Tools

| Command (from `isp-customer-service/`) | What |
|---|---|
| `uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080` | The service and the dashboard |
| `uv run pytest` | Unit and integration tests |
| `uv run python chatbot_core/src/agent/eval/run_eval.py [--only ID] [--runs N] [--voice] [--json out.json]` | Scripted calls with the real LLM, scored |
| `uv run python chatbot_core/src/agent/eval/metrics.py base.json --compare new.json` | LLM calls, tokens, latency and stability between two eval runs |
| `uv run python scripts/latency_report.py [--last N] [--days N] [--turns]` | Where each voice turn's time went, by layer (endpoint, ASR, read, engine, speak, TTS) |
| `uv run python scripts/reader_silent.py [--days N] [--module M]` | What no reader understood, from call traces |
| `uv run python scripts/prune_logs.py [--days N] [--keep N] [--apply]` | Delete old traces and audio past retention (dry run without `--apply`) |

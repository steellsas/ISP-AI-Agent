# ISP customer-service agent

> Location: `isp-customer-service/CLAUDE.md`. Git root is the parent `ISP-AI-Agent/`
> (remote `steellsas/ISP-AI-Agent`, base branch `develop`).

A Lithuanian voice agent for an ISP helpdesk: identifies the caller, reads telemetry, diagnoses
with fault cards, guides fixes, registers tickets. Simulated CRM and network; Pipecat voice.

## Read first
| File | When |
|---|---|
| `docs/STATUS.md` | what works, what does not, risks |
| `docs/ROADMAP.md` | current stage and what is next |
| `docs/ARCHITECTURE.md` | before touching the engine, perceive, speak or tools |
| `docs/DECISIONS.md` | D-xx decisions; if a change contradicts one, stop and ask |
| `docs/tasks/` | the task this session was started for |
| `docs/review/PROMPTAI.md` | prompt and LLM-parameter change log |

## Commands (from `isp-customer-service/`)
- Service + dashboard: `uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080`
- Voice bot: `.venv/Scripts/python.exe chatbot_core/src/app/pipecat_bot.py -t webrtc` (port 7860)
- Tests: `uv run pytest` · lint: `uv run ruff check . && uv run ruff format --check .`
- Eval (real LLM, costs ~0.10 USD per run): `uv run python chatbot_core/src/agent/eval/run_eval.py [--only ID] [--runs N] [--voice]`
  Ask before running the full eval.
- How to check and fix: `docs/testing/KAIP_TIKRINTI_IR_TAISYTI.md`

## Tests in a git worktree
The venv's editable `.pth` files point at the main checkout. In a worktree:
1. Copy gitignored files from the main checkout: `database/*.db`, `database/eval.sqlite`,
   `chatbot_core/.api_config.json`. Never print `.env`.
2. Use the main venv python with PYTHONPATH in Windows form:
   `W=$(cygpath -w "$PWD")`;
   `PYTHONPATH="$W\chatbot_core;$W\crm_service\src;$W\shared\src;$W\network_diagnostic_service\src"`.
   Without it the two copies mix (`No module named repository.customer_repo`).
3. The eval needs `.env` (API keys), which a worktree does not have; never copy or print it.
   To measure `develop`, run the eval from the main checkout while it is on `develop` and clean.
   To measure a branch's own code, ask Andrius how to run it.

## Design rules
- **The engine decides, the LLM only speaks.** Every action (register, inform, close) is an engine
  rule with a named reason (`knowledge/registracija.yaml`). A model suggestion returns to the engine
  as an analyst signal; it never becomes an action.
- **Confirm, do not guess.** An unclear caller answer gets a clarifying question
  („… — ar teisingai?“), read through `case.confirm`.
- **A new engine question lists its answers.** Before building it, list every answer kind the
  dialogue already handles (yes, no, new value, question, refusal, farewell, hang-up) and test
  each one plus the turn after it.
- **Code = mechanics, files = behaviour.** Cards, modules, equipment and phrases are YAML.
- **Prompt changes** are proposed with what and why, agreed with the owner, then logged in
  `docs/review/PROMPTAI.md`.
- People are reached only through tickets. No live/warm transfer.
- „maršrutizatorius“ is correct Lithuanian; do not replace it.

## Conventions
- Docs: English; Lithuanian working documents (demo/, testing/, instructor/) stay Lithuanian.
- Historical comments in code (dates, “fixed after…”) are being removed on purpose; do not add new ones.

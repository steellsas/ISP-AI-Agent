# M0 — Safety net and dead code removal

> Part of [REFACTORING_PLAN.md](REFACTORING_PLAN.md). Read its "Rules for the executor" first.
> Decisions: D-20. Prerequisites: branch `refactor/single-engine` created from `develop`.

Paths are relative to the repo root `isp-customer-service/`. `A/` = `chatbot_core/src/agent/`.
Line numbers from `develop` @ `c7be3ba`; re-locate with grep.

---

## 1. Why

- The old safety net was **parity against the legacy engine** (`run_eval.py --compare
  graph,v2`). M1 deletes the legacy engine, so parity disappears. Before that, the current
  v2 behaviour must be pinned by **eval scenarios + a recorded baseline**.
- Eval has **no scenario** for `crc_errors`, `link_down_local`, `node_fault_unregistered`,
  `dhcp_silent`, `no_port_data`, and `active_outage` is only covered indirectly.
- There are no golden traces in the repo (`logs/` is gitignored).
- A lot of code is **dead** (verified by importer search on 2026-09-14). Deleting it first
  shrinks every later milestone.

## 2. Before → After

| Before | After |
|---|---|
| 18 eval scenarios, 6 verdicts uncovered | ≥ 24 scenarios: every verdict produced by `A/verdict.py` + the 9 demo calls |
| No recorded baseline | `docs/refactoring/baseline/eval_baseline.json` (+ a short `README.md` with date, model, pass counts) |
| Stale eval docs/options | `run_eval.py` docstrings correct |
| Dead modules, stale scripts/tests | Deleted |

## 3. Affected files

**Modify**
- `A/eval/scenarios.json` — add scenarios (§4 step 1).
- `A/eval/run_eval.py` — fix stale docstrings (L18 `reply_any` = any substring; `--engine`
  help says default "graph" but default is `v2`). Do **not** remove `--engine/--compare` yet
  (M1 does).
- `A/eval/README.md` — list all 7 check types.

**Create**
- `docs/refactoring/baseline/eval_baseline.json`, `docs/refactoring/baseline/README.md`.

**Delete** (each verified dead; re-run the importer grep before deleting)

| Path | Evidence |
|---|---|
| `A/graph_v2/nodes/perception.py` | only `raise NotImplementedError`, zero importers |
| `A/graph_v2/nodes/diagnosis/evidence_drive.py` | same (the live module is `A/evidence_drive.py`) |
| `chatbot_core/src/services/mcp_service.py`, `services/custom_mcp_client.py` | only importer is `chatbot_core/test_mcp_simple.py` |
| `chatbot_core/src/services/crm.py`, `services/network.py` | zero importers |
| `chatbot_core/src/services/llm/cache.py` | zero importers |
| `chatbot_core/src/services/llm/utils.py` | zero importers (client has its own helpers) |
| `chatbot_core/test_mcp_simple.py` | manual script for dead MCP client |
| `chatbot_core/voice_demo.py` | superseded FastRTC demo; app host is `app/main.py` |
| `chatbot_core/src/adapters/transport/fastrtc_stream.py` (+ `adapters/transport/__init__.py` export) | only used by `voice_demo.py` and tests |
| `chatbot_core/src/ports/transport.py` (+ `ports/__init__.py` export) | only fastrtc + tests; the real transport is inline in `app/main.py` |
| `chatbot_core/src/streamlit_ui/` (whole dir) + `streamlit` dependency in `chatbot_core/pyproject.toml` | no importer; drives `ReactAgent` directly; broken stats import |
| `chatbot_core/src/config/__init__.py` | imports non-existent `config.py`; nobody imports the package. **Keep `config/i18n/`** (M3 moves it) |
| `A/prompts/greeting.txt`, `get_prompt_path` in `A/prompts/__init__.py` | no readers/callers |
| `A/prompts/partials/consultation.md`, `A/prompts/partials/understanding.md` | never included |
| `crm_service/test_mcp_protocol.py`, `crm_service/test_crm_standalone.py` | import renamed `mcp_server.*` modules |
| `scripts/test_crm_service.py`, `scripts/test_network_service.py` | import renamed `mcp_server.*` modules |
| `A/resolution.py` `LINEAR_DOCS`, `build_linear_strategy`; `react_agent.py` `_register_linear_strategies` (~L88-106) | `LINEAR_DOCS = {}`; no-op |
| `ReactAgent.run_turn_scoped` (~L468) and dead delegates `_revalidate_accumulated_address`, `_maybe_facts_recap`, `_maybe_refute_confirm`, `_refuting_client_fact`, `_revive_gave_up_key` | zero callers |
| `_spell_done` attribute (`react_agent.py` ~L273, `identification_flow.py` ~L771) | set, never read |

**Keep — do NOT delete (owner decision Q-1, plan §8):** the MCP servers
`crm_service/src/crm_mcp/server.py`, `network_diagnostic_service/src/network_diagnostic_mcp/server.py`,
their `[project.scripts]` entries, `shared/src/utils/logger.py` `setup_mcp_server_logger`,
`CustomerRepository` / `TicketRepository` / `NetworkRepository`, and tool functions reachable only
through the servers (`get_customer_equipment`, `get_customer_tickets`, `get_switch_info`). MCP may
become the integration transport. They are unused and untested today — do not refactor them in
this plan beyond keeping imports working.

**Tests to delete together with the code above**
- `chatbot_core/tests/test_voice_adapters.py`: `TestFastRTCTransport` (6 tests),
  `test_decode_gtts_mp3_to_fastrtc_frame` (~L425), module imports at ~L17/L21.
- `chatbot_core/tests/test_resolution.py`: `TestLinearStrategy` (~L160).
- Any test importing a deleted module (grep the module name in `chatbot_core/tests`).

## 4. Step-by-step

1. **Add eval scenarios** to `A/eval/scenarios.json` (same schema as existing entries:
   `{id, phone, desc, turns[], expect{}}`, checks `verdict_in`, `disposition`, `identified`,
   `reply_any`, `reply_none`, `tool_used`). Use the seeded customers:

   | New id | Phone | Verdict | Expected disposition | Source for turns |
   |---|---|---|---|---|
   | `D5_link_down` | +37060020104 | `link_down_local` | `ticket` (or `resolved` if the reseat path succeeds in seed) — run once, record what current v2 does, confirm with `docs/DEMO_SCENARIJAI.md` #5 | DEMO_SCENARIJAI #5 |
   | `D6_crc` | +37060030305 | `crc_errors` | per DEMO_SCENARIJAI #6 | #6 |
   | `D3_node_fault` | +37060030306 | `node_fault_unregistered` | `inform` (+ auto ticket) | #3 |
   | `D2_outage` | +37060020102 | `active_outage` (explicit `verdict_in`) | `inform` | #2 |
   | `D4_switch` | +37060020103 | `switch_unreachable` | `ticket` | #4 |
   | `D8_router_hung` | +37060020112 | `router_hung` | `resolved` | #8 |
   | `X_dhcp_silent` | seeded CUST106 (check `database/seeds/demo_internet.sql`) | `dhcp_silent` | record current behaviour; mark `known_bug: true` if it is the free-LLM path (Findings F-8) | — |

   For each: write turns from the demo script, run
   `cd chatbot_core && uv run python src/agent/eval/run_eval.py --only <id>` three times;
   the scenario must pass 3/3 before it is committed (LLM variance). If a verdict's current
   behaviour is wrong, keep the scenario with `known_bug: true` and add a line to the plan's
   Findings log.
2. **Record the baseline.** Run the full eval twice with `--json`:
   `uv run python src/agent/eval/run_eval.py --json ../docs/refactoring/baseline/eval_run1.json`
   (and `run2`). Merge into `eval_baseline.json` (per scenario: pass/fail per check, verdicts
   seen, disposition, tools used). Write `baseline/README.md`: date, git commit, models from
   `chatbot_core/.api_config.json`/env (`PERCEPTION_MODEL`, agent model), total checks passed
   per run. Commit.
   **Voice latency baseline (for plan §9 P-1):** ask the owner to run the 9 demo calls by voice
   on the current code (speculation on). From each session trace
   `logs/sessions/<session_id>.jsonl` extract `voice_turn_done.ttfa_ms`, `total_ms` and
   `voice_latency` events; write per-call median/p90 into `baseline/voice_latency.md`. Commit.
3. **Delete dead code** from §3 in small commits (services; voice demo + transport + port;
   streamlit; prompts; stale scripts/tests; no-op strategies and dead ReactAgent delegates).
   After each commit: `uv run pytest` green, and `uv run uvicorn --app-dir chatbot_core
   src.app.main:app --port 8080` starts (then stop it).
4. **Fix eval docs** (docstrings, README).
5. **Update the plan**: tick M0, status log, note scenario ids added.

## 5. Tests

- `uv run pytest` green after every commit.
- Eval: all pre-existing scenarios still pass; new scenarios pass or are `known_bug`.

## 6. Definition of Done

- Every verdict in `A/verdict.py decide()` appears in at least one scenario `verdict_in`.
- `docs/refactoring/baseline/` committed with two runs and README.
- All paths in §3 "Delete" are gone (the "Keep" list stays); importer grep for each
  deleted module name returns nothing.
- App starts; `uv run pytest` green.

## 7. Risks & rollback

- LLM variance makes new scenarios flaky → assert on state outcomes (verdict, disposition,
  tools) rather than exact wording; keep `reply_any` lists broad.
- Eval costs real API tokens (≈ 24 scenarios × several turns × 2 runs) — acceptable; do not
  loop runs.
- Rollback: revert the commit.

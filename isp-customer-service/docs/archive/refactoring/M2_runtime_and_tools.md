# M2 — Runtime context and one tool gateway

> Part of [REFACTORING_PLAN.md](REFACTORING_PLAN.md). Read its "Rules for the executor" first.
> Decisions: D-01 (no live objects in state), D-08 (telemetry as one tool), D-04 (prepares the
> closed action set), D-09 (prepares the identification gate).
> Prerequisites: M1 done (GraphState is the only state).

Legend as in M1 (`A/`, `RA`, `ID`, `PF`, `NF`, `SF`, `ED`, `WF`, `WG`, `TF`, `EF`, `CF`, `SE`, `v2/`).
Line numbers from `develop` @ `c7be3ba`; re-locate with grep.

---

## 1. Why

- Every node closes over `engine` (a `ReactAgent`) and every flow function takes `engine`
  as its first argument, then calls back into other flow modules through `engine._x()`
  delegates. Nodes cannot be tested without building the whole engine.
- Tools run in **14 different places** outside the LLM tool loop (table §5), plus the LLM
  tool loop itself; the gate, tracing and state updates are applied inconsistently.
  `verdict.gather_signals` imports CRM/NMS functions directly.
- LangGraph 1.x (installed 1.2.4) provides `context_schema` / `Runtime` for exactly this:
  dependencies injected per invocation, not stored in state.

## 2. Before → After

```
BEFORE                                          AFTER
node(state) ─► engine.method() ─► flow(engine)  node(state, runtime: Runtime[AgentRuntime])
flow(engine) ─► engine._other() ─► other(engine)   ─► flow(state, rt) ─► other(state, rt)   (direct calls)
execute_tool(...) called from 14 places         rt.tools.run(state, name, args, reason)  (one gateway)
verdict.gather_signals imports crm/nms          telemetry tool: snapshot | recheck, via ToolProvider
engine.tracer / engine.config / llm imports      rt.tracer / rt.config / rt.llm
```

`AgentRuntime` (frozen dataclass, `A/runtime.py`):

| Field | What |
|---|---|
| `session_id` | call id |
| `config` | `AgentConfig` |
| `tracer` | `ConversationTracer` |
| `llm` | thin facade over `services/llm/client.py` (`complete`, `json_complete`, `stream`) |
| `tools` | `ToolGateway` (§4 step 3) wrapping a `ToolProvider` |
| `knowledge` | access to packs/prompts loaders (M3 replaces with the contract loader) |
| `cancel` | `threading.Event` |
| `clock` | `now()` (testable time for ETA, flap windows) |

## 3. Affected files

**Create** (note: `A/tools.py` stays a module, so the new package is `A/tooling/`)
- `A/runtime.py` (`AgentRuntime`, builder used by `SE`).
- `A/tooling/gateway.py` (`ToolGateway.run(state, name, args, *, reason) -> ToolResult`:
  gate → provider call → trace `tool_call`/`tool_result` → state update → result).
- `A/tooling/local_provider.py` implementing `chatbot_core/src/ports/tools.py ToolProvider`
  with the current in-process functions from `A/tools.py`.
- `A/tooling/telemetry.py` (`telemetry(state, rt, mode="snapshot"|"recheck", level=1|2)`),
  wrapping `verdict.gather_signals` + `verdict.decide`.
- `A/trace.py` (helpers moved from RA: `trace_note`, `trace_tool_result`, `emit_decision`,
  `emit_case`).
- `A/dialog_utils.py` (helpers moved from RA: `last_agent_question`, `asked_recently`,
  `is_question`, `sanitize_question`, `similar`, `progress_key`).

**Modify**
- All nodes in `v2/nodes/**`: signature `(state, runtime)`; no `engine` closure.
- `v2/graph.py`: `StateGraph(GraphState, context_schema=AgentRuntime)`; `build_graph()` no longer
  takes an engine.
- `SE`: builds `AgentRuntime` once per call; passes `context=` on every `invoke`/`stream`.
- Every flow module: first parameters become `(state, rt)`; internal `engine._x()` round trips
  become direct imports (list in §6 below).
- `A/tools.py`: keeps the tool **implementations + schemas** only; `execute_tool` becomes the
  provider's dispatch; `REAL_TOOLS` stays the LLM-facing catalog until M5.
- `A/verdict.py`: `gather_signals` receives a provider (no direct `crm_mcp`/`network_diagnostic_mcp`
  imports).
- `A/ticket_flow.py` `amend_ticket_note` (~L184-212, raw SQL) → a provider tool
  `append_ticket_note` (M6 extends it).
- `A/perception_flow.py` ~L382 raw `SELECT street_name FROM streets` and
  `A/identification_flow.py` ~L244, 653, 674 `get_db` usage → provider `address_registry()`.

**Delete**
- RA delegates and helpers once all callers use modules (the whole list in §6). After M2,
  `RA` contains only: the streaming LLM loop (`run_turn_scoped_stream`,
  `_run_until_response_stream`), `_finalize_reply`, `_track_stuck`, `_stuck_backstop`,
  `_apply_backstop`, `_commit_driven_reply`, `_emit_scripted_reply`, `on_turn_cancelled`,
  `_record_llm_stats`, `get_stats`, `end_session` helpers. M4/M5 remove the rest.
- RA class constants → module constants (`_GATED_TOOLS` → `A/tooling/gateway.py`,
  `_UNRESOLVED_LINE_FAULTS` → `A/verdict.py` (M3 turns it into a verdict flag),
  `_STRATEGY_DIAG_TOOLS`/`_STRATEGY_ACTION_TOOLS` → `v2/tool_scopes.py`,
  `_SOLVER_DRIVE_VERDICTS`, `_DRIVE_MAX_TURNS` → `A/solver_flow.py`).
- `v2/runtime.py` `run_on_state` wrapper from M1 (nodes now return updates directly).

## 4. Step-by-step

1. **Introduce `AgentRuntime` and context schema** without changing flows: nodes receive
   `runtime` and still pass `engine` built from it (temporary adapter in `SE`). Commit.
2. **Move RA helpers** (`A/trace.py`, `A/dialog_utils.py`) and update all callers
   (17 `_trace_note` sites, 11 `_last_agent_question`, 4 `_asked_recently`, …). Commit.
3. **ToolGateway + LocalToolProvider.** Implement the gateway with the existing gate logic
   from `EF.gate_tool` (~L22-129) and state update logic from `NF.update_state_from_observation`
   (~L1418-1434 and neighbours), tracing from RA `_trace_tool_result`. Route the LLM tool loop
   (`EF.execute_tool_calls` ~L132-175) through it. Commit.
4. **Route the 14 direct call sites through the gateway** (table §5), one flow module per
   commit. Each call passes a `reason` string (e.g. `"preflight_phone"`, `"verify_restored"`)
   that ends up in the trace.
5. **Telemetry tool.** `telemetry(mode, level)`:
   - `snapshot` = today's `diagnose_connection` (sets verdict/hypothesis/strategy through the
     same code as `WF.ensure_diagnosed` ~L55-99).
   - `recheck` = today's read-only `fresh_diagnose` (`WF` ~L41) — never changes verdict or
     hypothesis; returns signals for the caller to evaluate.
   - `level=1` = billing + outage + switch/node; `level=2` = port/line/MAC/CRC/DHCP/traffic.
     In M2 both levels are computed together (behaviour unchanged); M6 uses level 1 alone for the
     identification gate and adds open tickets.
   Replace `diagnose_connection` call sites (`WF` ~41, 92; `SF` ~546; `SE` ~211 background;
   RA ~1246 hang-up net; `EF` gate ~73; `NF` ~1333) with `telemetry(...)`. The LLM-facing tool
   name `diagnose_connection` may stay in `REAL_TOOLS` until M5 removes narrator tools.
6. **Flows take `(state, rt)`.** Convert module by module (suggested order: CF → TF → ED → WG →
   WF → SF → PF → ID → NF → EF). Replace every `engine._x(...)` delegate call with a direct
   import. Nodes call flows directly. Delete the corresponding RA delegates in the same commit.
7. **Remove the temporary engine adapter** from step 1. `ReactAgent` is constructed only for
   the narrator loop (nodes that narrate get it from a small factory in `v2/runtime.py`).
8. **Tests.** Replace engine-building fixtures with `make_state()` + `make_runtime(fake_tools,
   fake_llm)` in `conftest.py`. Node-level tests now call `node(state, runtime)` directly.

## 5. Direct tool call sites to route through the gateway

| # | Site | Tool | Purpose |
|---|---|---|---|
| 1 | `ID` ~36 | `find_customer(phone)` | preflight → `phone_candidate` |
| 2 | `ID` ~66 | `check_outages(candidate)` | preflight outage (**M6 makes it silent**, D-09) |
| 3 | `ID` ~350 | `resolve_address` (read-only) | revalidate accumulated address |
| 4 | `ID` ~694 | `find_customer(account_code)` | account-code rung |
| 5 | `PF` ~1337 | `resolve_address` | commit identity from slots |
| 6 | `WF` ~41 | `diagnose_connection` read-only | `fresh_diagnose` → `telemetry(recheck)` |
| 7 | `WF` ~92 | `diagnose_connection` | `ensure_diagnosed` → `telemetry(snapshot)` |
| 8 | `WF` ~176 | `step.tool_actions` (`update_mac`) | ACTION step |
| 9 | `NF` ~1328 | `reset_port` | chained after `update_mac` |
| 10 | `SF` ~546 | `diagnose_connection` | device visible? → `telemetry(recheck)` |
| 11 | `SF` ~613 | `update_mac` (+ reset) | bridge bind |
| 12 | `EF` ~264 | `create_ticket` | register from state |
| 13 | `SE` ~211 | `diagnose_connection` | background diagnosis → `telemetry(snapshot)` into inbox |
| 14 | RA ~1246 | `diagnose_connection` | hang-up net → `telemetry(recheck)` |

Plus: `A/verdict.py` ~66-71 imports; `TF` ~184-212 raw SQL; `PF` ~382 raw SQL; `ID` ~244, 653, 674
`get_db`; demo simulations `EF` ~283, 305 and `app/main.py` ~169, 202 (`simulate_*`) → provider
methods behind `SIMULATE_*` flags.

## 6. RA helpers and delegates to remove in this milestone

Delegates (callers switch to the flow module): `anchor_text`, `classify_side_topic`,
`ensure_diagnosed`, `ensure_action_done`, `solver_drive_turn`, `_advance_resolution`,
`_shadow_solve`, `_ingest_client_evidence`, `_prefill_slots_from_text`, `_pre_turn_guards`,
`_mark_step_presented`, `_maybe_close_inform`, `_maybe_finish`, `_drive_escalate`, and all
WF/SF/TF/ED/PF/ID/NF/EF round-trip delegates (`_advance_*`, `_goto_step`, `_route_to`,
`_classify_*`, `_fresh_diagnose_reason`, `_note_evidence`, `_settle_hypothesis`,
`_open_hypothesis`, `_bridge_fail_step`, `_build_solver_context`, `_drive`,
`_drive_propose_fix`, `_refresh_diagnosis`, `_plug_report`, `_begin_ticket_dialogue`,
`_abort_ticket_to_solving`, `_wants_to_keep_solving`, `_finish_ticket_dialogue`,
`_ticket_stage_reply`, `_ticket_need`, `_fmt_phone`, `_evidence_drive`,
`_evidence_question_open`, `_negation_clarify_reply`, `_engine_resolve_from_slots`,
`_on_task_question`, `_reopen_identification`, `_augment_tool_result`,
`_augment_resolve_result`, `_update_state_from_observation`, `_result_narration_tail`,
`_emit_rag_injection`, `_prune_history`, `_state_facts_block`, `_scoped_tools_schema`,
`_register_ticket_from_state`, `_simulate_bridge_connection`, `_simulate_router_reboot`).

Helpers moved to modules (step 2): `_trace_note`, `_trace_tool_result`, `_emit_decision`,
`_emit_case`, `_last_agent_question`, `_asked_recently`, `_is_question`, `_sanitize_question`,
`_similar`, `_progress_key`, `_tools_called_this_session`, `_assistant_tool_message`,
`_apply_bg_diagnosis` (→ inbox merge in `SE`), `_consume_injected_reply` (→ narrator input).

## 7. Tests

- Adapt fixtures (step 8). Tests that monkeypatch `ra.execute_tool` or
  `ReactAgent._fresh_diagnose_reason` (e.g. `test_graph.py` successors, `test_line_faults.py` ~L18)
  inject a fake `ToolProvider` instead.
- New `test_tool_gateway.py`: every tool call is traced once; gate refusals; state updates for
  `find_customer`/`resolve_address`/`telemetry`; `recheck` never changes verdict/hypothesis.
- New: a grep-style test that fails if `execute_tool(` or `crm_mcp`/`network_diagnostic_mcp`
  imports appear outside `A/tooling/`.
- Eval full run ≥ baseline.

## 8. Definition of Done

- `grep -rn "engine\b" chatbot_core/src/agent/graph_v2 chatbot_core/src/agent/*_flow.py` →
  no flow/node takes or closes over `engine` (the narrator factory is the only exception).
- `grep -rn "execute_tool(\|from crm_mcp\|from network_diagnostic_mcp" chatbot_core/src` →
  only inside `A/tooling/` (and `A/tools.py` implementations).
- Every tool call in a trace has a `reason`.
- RA contains only the members listed in §3 "Delete" as remaining.
- `uv run pytest` green; eval ≥ baseline; live call works (owner check).

## 9. Risks & rollback

- Huge mechanical diff → strictly one module per commit, tests green each time.
- Tool call ordering changes can alter behaviour (e.g. `reset_port` chained after
  `update_mac`). Keep the existing order; the gateway only wraps.
- Rollback: revert the commit of the failing module.

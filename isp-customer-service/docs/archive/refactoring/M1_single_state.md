# M1 — Single state: GraphState only, legacy engines removed

> Part of [REFACTORING_PLAN.md](REFACTORING_PLAN.md). Read its "Rules for the executor" first.
> Decisions: D-01, D-20, D-21. Prerequisites: M0 done (baseline recorded).

Legend: `A/` = `chatbot_core/src/agent/`, `RA` = `A/react_agent.py`, `ID` = `A/identification_flow.py`,
`PF` = `A/perception_flow.py`, `NF` = `A/narrator_flow.py`, `SF` = `A/solver_flow.py`,
`ED` = `A/evidence_drive.py`, `WF` = `A/walker_flow.py`, `WG` = `A/walker_guards.py`,
`TF` = `A/ticket_flow.py`, `EF` = `A/executor_flow.py`, `CF` = `A/closing_flow.py`,
`SE` = `A/session.py`, `G1` = `A/graph.py`, `v2/` = `A/graph_v2/`.
Line numbers from `develop` @ `c7be3ba`; re-locate with grep.

---

## 1. Why

Today there are two state holders:

```
 ReactAgent (RA)                                GraphState (v2/state.py)
 ├─ self.state: AgentState (48 fields)   ──copy──►  same 48 fields + turn: TurnScratch
 └─ ~99 private attributes (_flags)       (sync_updates, v2/runtime.py:75-83,
    68 in __init__, 31 created lazily      after SOME nodes; walker/executor return {})
                         ▲
        nothing ever reads the checkpoint back into the engine
```

Consequences: the checkpoint is incomplete (no flags, stale between turns); nodes cannot be
tested without a full `ReactAgent`; `route_entry` routes on a mirror; three engines
(`v2`, `graph`, `legacy`) must be kept alive. D-01 makes `GraphState` the only state.

## 2. Before → After

| Before | After |
|---|---|
| `AGENT_ENGINE=v2\|graph\|legacy`, `A/graph.py`, non-streaming loop | only v2; no switch |
| `AgentState` dataclass + `GraphState` mirror + `_LEGACY_FIELDS` + `sync_updates` | `GraphState` only, grouped sub-models |
| ~99 `engine._x` flags | named fields in `GraphState` groups, `TurnScratch`, or runtime objects |
| Engine keeps state between turns | Checkpointer keeps state; each node receives state and returns updates |
| Between-turn writes mutate the engine (`apply_delivery`, overlay, background inbox, hang-up net) | `graph.update_state(config, patch)` or the next turn's input |
| Relative SQLite path, one connection per session, never closed | absolute path from config, one saver per process, closed on shutdown; tests use `InMemorySaver` |

`ReactAgent` still exists after M1 (it holds the LLM loop and helpers) but **owns no state**:
its `state` attribute is only the `GraphState` handed in by the running node. M2 removes its
helpers, M5 deletes the class.

### Target `GraphState` shape

```python
class GraphState(BaseModel):
    messages: list[dict[str, Any]]
    identity: IdentityState      # who is calling, identification ladder
    intake: IntakeState          # problem, anamnesis, symptoms, secondary problems
    diagnosis: DiagnosisState    # verdict/diagnosis, hypothesis, evidence ledger + evidence dialogue
    resolution: ResolutionState  # active strategy/procedure position + solver/drive/bridge counters
    ticket: TicketState          # stage, context, contact, ticket_id
    dialog: DialogState          # last question, stuck, awaiting, active question, holds
    closing: ClosingState        # case_closed, closed_reason, is_complete, wrap-up
    voice: VoiceState            # delivery/overlay/analyst inbox results
    turn: TurnScratch            # reset every invocation (never history)
```

Existing flat fields → groups:

| Group | Existing fields |
|---|---|
| `identity` | caller_phone, profile, customer_id, customer_name, customer_address, caller_name, caller_relation, phone_candidate, preflight_done, preflight_outage, address_confirmed |
| `intake` | problem_type, secondary_problems, problem_description, anamnesis_asked, anamnesis_raw, anamnesis_when, anamnesis_trigger, symptoms, heard_utterances, observations |
| `diagnosis` | diagnosis, hypothesis, evidence, failed_hypotheses, rejected_hypotheses, pivoted_from, outage_reported |
| `resolution` | resolution (rename inner access only if needed; keep dict shape in M1) |
| `ticket` | ticket_id, ticket_stage → `stage`, contact_phone, contact_hours |
| `dialog` | last_question, stuck_count, last_heard, clarity_level, awaiting, awaiting_turns, step_confusions, last_intent, turn_count, max_turns |
| `closing` | case_closed, closed_reason, is_complete, closing_turns |

## 3. Affected files

**Delete**
- `A/graph.py` (move `LOOKUP_TOOLS`, `TICKET_TOOLS`, `CLOSING_TOOLS` → `v2/tool_scopes.py`;
  node prompt constants already exist in `v2/runtime.py:29-33`).
- `A/state.py` (`AgentState`; move `set_customer_info`, `add_observation` to `GraphState`
  methods or `A/state_ops.py` functions; delete `confirm_address`, `to_dict`).
- `v2/state.py`: `_LEGACY_FIELDS`, `from_legacy`, `to_legacy`, `begin_turn` (unused).
- `v2/runtime.py`: `sync_updates`.
- `RA`: `step()` (~L1649), `run_until_response` (~L1772), `run_cli` (~L2056), `llm_tool_completion`
  non-streaming path, `_use_graph` logic; `A/__init__.py` exports of `ReactAgent`, `run_cli`,
  `AgentState`, `run_agent`.
- `SE`: `_use_graph`, `_engine_mode`, legacy branches (~L51-77, 82, 95, 250, 269, 284).
- `chatbot_core/src/app/runtime_config.py` ~L69-79 `AGENT_ENGINE` option (and the key in any
  local `chatbot_core/.api_config.json`).
- `A/eval/run_eval.py`: `--engine`, `--compare`, `_run_compare`, `_PARITY_FIELDS` (~L28-31,
  154-160, 332-377, 385-417).

**Modify**
- `v2/state.py` (grouped models + all promoted fields), `v2/checkpoint.py` (factory, allowlist
  for new models, absolute path), `v2/graph.py`, every node in `v2/nodes/**`, `v2/runtime.py`
  (`narrate`, `speak_scripted` return updates), `SE`, `RA`, and every flow module that reads or
  writes `engine.state.*` or `engine._*` (ID, PF, NF, SF, ED, WF, WG, TF, EF, CF,
  `A/dialog_registry.py`, `A/speculation.py`, `A/analyst.py`, `A/endpoint.py`,
  `A/voice_pipeline.py`), `chatbot_core/src/app/voice.py` (~L162 reaches into `session._agent`),
  `chatbot_core/src/app/main.py`, `chatbot_core/src/app/sessions.py`, `A/eval/run_eval.py`,
  `A/eval/fuzz.py`.

**Tests** — see §6.

## 4. Step-by-step

Each numbered step is one commit (or one commit per group where stated); `uv run pytest`
green after each.

1. **Remove legacy engines.** Delete everything in §3 "Delete" that concerns `graph`/`legacy`,
   the non-streaming loop, `run_cli`, eval parity. Move tool scopes to `v2/tool_scopes.py`.
   Tests: delete `tests/test_graph.py::TestGreetingParity`, `tests/test_graph_v2.py::TestRuntimeConfigSwitch`
   and `test_greeting_matches_legacy_and_graph`, `tests/test_agent.py::TestAgentStep`,
   `tests/test_tool_gate.py::TestGateInStep`, `tests/test_graph_v2_state.py::TestFieldParity`
   and `::TestRoundTrip`. Rewrite tests that pass `engine="graph"`/`"legacy"`
   (`test_agent.py` ~L1282/1302/1348, `test_graph.py`, `test_graph_v2.py` `_v2_session` hack
   ~L42-45) to use the default engine; rewrite tests using `run_until_response` /
   `llm_tool_completion` patches (`test_nlu.py::TestPrefillWiring`, `test_repeat_guard.py`
   TestBackstop/TestProgressReset) onto the streaming path. Move the surviving tests of
   `test_graph.py` (walker/closing logic) into `test_walker_flow.py` / `test_closing.py` and delete
   `test_graph.py`.
2. **Make state types serializable.** Replace: `dialog_registry.ActiveQuestion` dataclass →
   pydantic model; `_ticket_ctx["step"]` live `Step` object → `step_id: str` plus a lookup
   helper `faults.step_by_id(verdict, step_id)`; `_revived_keys` set → `list[str]`;
   `_evidence_conflict` / `_fact_confirm` tuples → small pydantic models. Register every new
   model in `v2/checkpoint.py` serializer allowlist. Add a test that a `GraphState` with all
   groups populated round-trips through the checkpointer.
3. **GraphState replaces AgentState.** Build the grouped models (§2) with the existing fields.
   Make `engine.state` a `GraphState`. Replace every `engine.state.<field>` access with the
   grouped path (`engine.state.identity.customer_id`, …). Seed `dialog.max_turns` from
   `AgentConfig.max_turns` (today config says 50, state says 20 — use the config value and
   delete the state default). Delete `A/state.py`, `_LEGACY_FIELDS`, legacy bridges.
   Commit per group if the diff is large.
4. **Promote private flags** following Appendix A, **one commit per group**
   (identity → intake → diagnosis → resolution → ticket → dialog/closing → voice/runtime).
   Rules:
   - `CALL` lifetime → field in the group model (English snake_case name from Appendix A).
   - `PER_TURN` → field in `TurnScratch`.
   - `PER_TURN*` (one-shot flag consumed by its reader, may survive a turn if the reader did
     not run) → keep as a **group field**, unless a test proves setter and reader always run in
     the same turn.
   - `RUNTIME` → stays off-state (engine attribute until M2 moves it to runtime context).
   - `UNUSED` → delete.
   - Delete dead state: `TurnScratch.cancel_requested` (use a runtime `threading.Event`),
     duplicated `_side_topic_this_turn` (use `turn.side_topic_active`).
   Acceptance grep after this step (only runtime attributes may remain):
   `grep -rnE "engine\._[a-z_]+|agent\._[a-z_]+" chatbot_core/src` → only
   `_registry`, `_spec_cache`, `_bg_diagnosis` (inbox), `_cancel_requested` (→ Event),
   `_session_ended`, and method calls (`engine._walk_resolution(...)` etc.; M2 removes those).
5. **Node contract: state in, updates out.** Replace `sync_updates` with one wrapper in
   `v2/runtime.py`:
   ```text
   def run_on_state(engine, state, fn):
       engine.state = state.model_copy(deep=True)   # the node's working copy
       result = fn()                                # existing engine/flow calls
       return engine.state.model_dump(exclude_unset=False)  # full update incl. turn
   ```
   Every node (identification, ticket, closing, side_topic, diagnose, solver_gate, walker,
   executor, narrator) uses it — walker/executor must no longer return `{}`.
   `SE` stops relying on engine memory between turns: the turn input is
   `{"turn": TurnScratch(user_input=...), **inbox_updates}` and the graph loads everything else
   from the checkpoint.
6. **Between-turn writes through the graph.**
   - `SE.apply_delivery` / `SE.apply_overlay`: read `graph.get_state(config).values`, compute the
     patch with the existing logic on a copy, write with `graph.update_state(config, patch)`.
   - Background results (`analyst_notes`, `bg_diagnosis`, `injected_reply`): session keeps a
     thread-safe inbox; its contents are merged into the **next turn input**
     (`voice.analyst_notes`, `turn.injected_reply`, `voice.bg_diagnosis`). No thread touches
     `engine.state`.
   - `SE.end_session` (hang-up net + call record): load state with `graph.get_state`, run the
     existing logic on it, `update_state`, then persist. (M6 redesigns this as the finalizer.)
   - `app/voice.py` ~L162 must use a public `AgentSession` method instead of `session._agent`.
   - Cancel: `SE.request_cancel` sets a runtime `threading.Event` checked between tokens.
7. **Checkpointer.** `v2/checkpoint.py`: `make_checkpointer(path: Path | None)`; path from
   config (`API_CHECKPOINT_PATH`, default `<repo>/logs/graph_checkpoints.sqlite`, absolute);
   one saver shared by all sessions in the process (created in `app/sessions.py`
   `SessionManager`), closed on shutdown. Tests and eval use `InMemorySaver`.
8. **Proof test.** `tests/test_single_state.py`: run 3 turns of a scripted call; build a
   **new** `AgentSession` object with the same `thread_id` and checkpointer; continue the call;
   assert identity, evidence, resolution step and ticket stage survived and the next reply is
   consistent. Also assert that `ReactAgent` has no attribute starting with `_` holding call data
   (inspect `vars(engine)` against an allowlist of runtime names).

## 5. Appendix A — flag → target mapping (authoritative)

Lifetime: `CALL` survives turns · `PER_TURN` one turn · `*` one-shot (see step 4) ·
`RUNTIME` live object · `UNUSED`.

### identity
| Flag | Lifetime | Target |
|---|---|---|
| `_registry` | RUNTIME | runtime cache (module-level) |
| `_awaiting_account_code` | CALL | `identity.account_code_mode` |
| `_code_grace` | CALL | `identity.account_code_grace_turns` |
| `_addr_empty_turns` | CALL | `identity.address_empty_turns` |
| `_addr_unrecognized` | CALL | `identity.address_unrecognized_turns` |
| `_addr_warned` | CALL | `identity.address_warned` |
| `_addr_encouraged` | CALL | `identity.address_encouraged` |
| `_addr_resolve_fails` | CALL | `identity.address_resolve_failures` |
| `_addr_city_suggestion` | CALL | `identity.suggested_city` |
| `_addr_diag_note` | PER_TURN | `turn.address_lookup_note` |
| `_addr_confirm_note` | PER_TURN | `turn.address_confirm_note` |
| `_db_address_note` | PER_TURN | `turn.db_address_note` |
| `_denied_street` | PER_TURN | local variable in `prefill_slots_from_text` |
| `_street_attempts` | CALL | `identity.street_attempts: list[str]` |
| `_street_not_exists_due` / `_said` | CALL | `identity.street_not_exists_due` / `identity.street_not_exists_said` |
| `_city_not_served_said` | CALL | `identity.city_not_served_said` |
| `_spell_mode` | CALL | `identity.spell_mode` |
| `_spell_done` | UNUSED | delete (M0) |
| `_just_identified` | PER_TURN* | `identity.just_identified` |
| `_result_pending` | CALL | `identity.result_pending` |
| `_reopen_note` | PER_TURN | `turn.reopen_note` |
| `_reopen_confirm_pending` / `_asked` / `_asks` / `_reask` | CALL | `identity.reopen_confirm_utterance` / `reopen_confirm_asked` / `reopen_confirm_asks` / `reopen_reask_due` |
| `_holder_clarify_open` / `_asked` | CALL | `identity.holder_clarify_open` / `holder_clarify_asked` |
| `_name_heard` | PER_TURN* | `identity.caller_name_heard` |

### intake
| Flag | Lifetime | Target |
|---|---|---|
| `_boundary_problem` | PER_TURN* | `intake.boundary_problem` |
| `_problem_guess` | CALL | `intake.problem_guess` |
| `_ask_problem_count` | CALL | `intake.ask_problem_count` |
| `_opening_heard_note` | PER_TURN* | `intake.opening_heard_note` |

### diagnosis (evidence dialogue)
| Flag | Lifetime | Target |
|---|---|---|
| `_news_told` | CALL | `diagnosis.news_delivered` |
| `_last_understanding` | PER_TURN | `turn.understanding` |
| `_perception_step` | PER_TURN | `turn.perception_step` |
| `_evidence_asks` | CALL | `diagnosis.evidence_ask_counts: dict[str,int]` |
| `_evidence_last_ask_key` | CALL | `diagnosis.pending_evidence_key` |
| `_evidence_conflict` / `_asked` | CALL | `diagnosis.evidence_conflict` (model) / `diagnosis.evidence_conflict_asked_key` |
| `_fact_confirm` / `_asked` | CALL | `diagnosis.fact_confirm_pending` (model) / `diagnosis.fact_confirm_asked` |
| `_fact_meaning` | PER_TURN* | `diagnosis.fact_meaning` |
| `_done_report_key` | PER_TURN | `turn.done_report_key` |
| `_revived_keys` | CALL | `diagnosis.revived_evidence_keys: list[str]` |
| `_recap_state` | CALL | `diagnosis.facts_recap_state` |
| `_refute_state` | CALL | `diagnosis.refute_confirm_state` |
| `_findings_announced` | CALL | `diagnosis.findings_announced` |
| `_pending_announce` | CALL | `diagnosis.pending_announcement` |
| `_evidence_directive` / `_findings_directive` / `_recap_directive` / `_ident_directive` / `_ticket_directive` | PER_TURN | `turn.directives.{evidence,findings,recap,ident,ticket}` (fixes F-10: reset every turn) |
| `_side_topic_this_turn` | PER_TURN | `turn.side_topic_active` (exists; delete the duplicate) |
| `_side_topic_turns` | CALL | `dialog.side_topic_streak` |

### resolution (solver / drive / bridge)
| Flag | Lifetime | Target |
|---|---|---|
| `_solver_prev_step`, `_solver_cycles`, `_solver_low_conf`, `_solver_internal_hops` | CALL | `resolution.solver_prev_step`, `solver_cycles`, `solver_low_conf_streak`, `solver_internal_hops` |
| `_drive_turns`, `_drive_repeats`, `_drive_last_reply`, `_drive_last_action`, `_drive_disabled` | CALL | `resolution.drive_turns`, `drive_repeats`, `drive_last_reply`, `drive_last_action`, `drive_disabled` |
| `_drive_bridge_offered` | CALL | `resolution.bridge_offered` |
| `_bridge_plug_reported` | CALL | `resolution.bridge_plug_reported` |
| `_bridge_bound` | CALL | `resolution.bridge_bound` |
| `_bridge_fail_stage` | CALL | `resolution.bridge_fail_stage` |
| `_escalate_clarify_asked` | CALL | `resolution.escalate_clarify_asked` |
| `_escalate_clarify_pending` | PER_TURN* | `resolution.escalate_clarify_due` |

### ticket
| Flag | Lifetime | Target |
|---|---|---|
| `_ticket_stage` (property over `state.ticket_stage`) | CALL | `ticket.stage` (delete the property) |
| `_ticket_ctx` | CALL | `ticket.context: TicketContext` (`step_id`, `note`, `last_kind`, `intro_done`, `hours_asked`, `cancel_confirm_out`, `ask_cancel_confirm`) |
| `_ticket_offscript` | PER_TURN | `turn.ticket_offscript_question` |
| `_bridge_fail_note` | CALL | `ticket.bridge_fail_note` |
| `_resume_fix_note` | PER_TURN* | `ticket.resume_fix_note` |

### dialog / closing
| Flag | Lifetime | Target |
|---|---|---|
| `_active_question` | CALL | `dialog.active_question: ActiveQuestion \| None` |
| `_end_confirm_pending` | CALL | `dialog.end_confirm_pending` |
| `_resume_hold` | PER_TURN* | `dialog.resume_hold_due` |
| `_resync_note` | PER_TURN* | `dialog.resync_note` |
| `_cannot_now_state` / `_done` | CALL | `dialog.cannot_now_state` / `dialog.cannot_now_done` |
| `_repeated_verbatim` | CALL (1 turn later) | `dialog.last_reply_repeated` |
| `_turn_start_key` | PER_TURN | `turn.progress_key_at_start` |
| `_pre_turn_head_done` | PER_TURN | delete in M4 (node order replaces it); in M1 → `turn.pre_turn_head_done` |
| `_last_rag_key` | CALL | `dialog.last_rag_injection_key` |
| `_wrap_content_turns` | CALL | `closing.wrap_content_turns` |
| `_wrap_react_note` | PER_TURN* | `closing.wrap_react_note` |
| `_callback_goodbye_due` | PER_TURN* | `closing.callback_goodbye_due` |
| `_secondary_asked` | CALL | `closing.secondary_problems_asked` |

### voice / runtime
| Flag | Lifetime | Target |
|---|---|---|
| `_cancel_requested` | RUNTIME | runtime `threading.Event` |
| `_injected_reply` | PER_TURN (set before turn) | `turn.injected_reply` via turn input |
| `_spec_cache` | RUNTIME | runtime (session-level) |
| `_bg_diagnosis` | RUNTIME inbox | `voice.bg_diagnosis` via turn input |
| `_analyst_notes` | CALL inbox | `voice.analyst_notes` via turn input |
| `_overlay_heard` | CALL one-shot | `voice.overlay_heard` (written by `update_state`) |
| `_undelivered_tail` | CALL one-shot | `voice.undelivered_tail` |
| `_unheard_question` | CALL one-shot | `voice.unheard_question` |
| `_active_tool_names`, `_node_prompt` | PER_TURN | node arguments (not state) |
| `_active_node` | PER_TURN | `turn.active_node` |
| `_session_ended` | RUNTIME | session attribute |

Class constants used by flow modules become module constants in M2:
`_GATED_TOOLS`, `_UNRESOLVED_LINE_FAULTS`, `_STRATEGY_DIAG_TOOLS`, `_STRATEGY_ACTION_TOOLS`,
`_SOLVER_DRIVE_VERDICTS`, `_DRIVE_MAX_TURNS`.

## 6. Tests

- **Delete** (legacy/parity only): listed in step 1.
- **Adapt:** ~950 private-attribute accesses in 23 test files (largest: `test_agent.py`,
  `test_identification_rules.py`, `test_fault_packs.py`). Mechanical rule: `agent._x` →
  `agent.state.<group>.<name>` per Appendix A; `agent.state.<flat>` → grouped path. Add a
  helper in `conftest.py` (`make_engine(state=...)`) so tests build an engine around a
  `GraphState`.
- **Adapt** `test_graph_v2.py::TestCheckpointedState` (inject `InMemorySaver`),
  `test_graph_v2_state.py` remaining tests (build `GraphState` directly).
- **New:** checkpoint round-trip with all groups (step 2); `test_single_state.py` (step 8).
- **Eval:** full run; pass count ≥ M0 baseline.

## 7. Definition of Done

- `grep -rn "AGENT_ENGINE\|AgentState\|_LEGACY_FIELDS\|sync_updates\|to_legacy\|from_legacy\|run_until_response\|agent\.graph\b" chatbot_core` → nothing (docs/archive excluded).
- `A/graph.py`, `A/state.py` do not exist.
- Step 4 acceptance grep passes.
- `test_single_state.py` passes: a call continues correctly on a fresh session object.
- `uv run pytest` green; eval ≥ baseline; app starts and a live voice call works (owner check:
  greeting, identification, one diagnosis turn, barge-in cancel).

## 8. Risks & rollback

- **Deep copy cost per node** (messages grow). Measure `turn_summary` latency before/after on
  one eval run; if a node copy costs > 20 ms, copy once per turn in `SE` and pass by reference
  inside one invocation.
- **One-shot flags** (`*`) behaving differently now that `turn` resets every invocation: keep
  them as group fields as specified; if an eval scenario regresses, compare traces.
- **Checkpoint serde failures** hide as silent turn deaths (seen 2026-08-13). The round-trip
  test in step 2 must include real tool-call message shapes (`tool_calls` lists).
- Rollback: revert the step's commit.

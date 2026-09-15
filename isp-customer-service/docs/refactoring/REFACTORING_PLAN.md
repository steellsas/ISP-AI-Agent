# Refactoring plan — single LangGraph engine

> Status: **ready to execute** · Written 2026-09-14 · Owner: Andrius
> Why: [DECISIONS.md](DECISIONS.md) (D-01 … D-22). This file is the short overview;
> every milestone has its own instruction file (links below).

## 1. Goal (one paragraph)

Turn the ISP support agent into **one LangGraph engine** whose `GraphState` is the only
state, where every turn is **perceive → decide → execute → speak**, **one driver**
(solver + procedures) makes exactly **one `TurnPlan` per turn**, all behaviour
(knowledge, phrases, vocabulary, limits, policies) lives in **English-schema files with
Lithuanian locale content**, and every call leaves a **contact record**. `ReactAgent`,
the legacy engines and all dead code are deleted along the way.

```
 AgentSession (thin: invoke per turn, stream, cancel, finalizer → contact record)
      │ graph.stream(TurnInput, config={thread_id}, context=Runtime)
      ▼
 perceive ──► decide ──► execute ──► speak ──► END
 (facts,       (TurnPlan:  (the ONLY   (phrase key
  intent,       owner,      place tools  or LLM
  step answer,  action,     run;         directive;
  analyst       say,        telemetry    no tools,
  signals)      hypothesis) snapshot/    no decisions)
                            recheck)
 GraphState = identity · intake · diagnosis · resolution · ticket · dialog · closing · voice · turn
 Runtime (not state) = llm · tools · tracer · knowledge · locale · limits · config · cancel
```

## 2. Milestones

Do them **in order**. Each milestone ends with green tests, green eval and its dead code
deleted. Tick the box and add the merge commit hash when done.

| # | Milestone | Instruction file | Decisions | Done |
|---|---|---|---|---|
| M0 | Safety net + dead code removal | [M0_safety_net.md](M0_safety_net.md) | D-20 | [x] `0126841` |
| M1 | Single state (GraphState only, legacy engines removed) | [M1_single_state.md](M1_single_state.md) | D-01, D-21 | [x] `1f3a64f` |
| M2 | Runtime context + one tool gateway | [M2_runtime_and_tools.md](M2_runtime_and_tools.md) | D-01, D-08 | [x] `ed8494d` |
| M3 | Knowledge contract (EN schema, locales, roles, limits, validation) | [M3_knowledge_contract.md](M3_knowledge_contract.md) | D-15…D-19 | [x] `e12c73b` |
| M4 | `decide` + `TurnPlan` + single driver + hypothesis stability | [M4_decide.md](M4_decide.md) | D-02…D-05 | [x] `a774e1e` |
| M5 | `speak` node + analyst signals; `ReactAgent` deleted | [M5_speak_and_analyst.md](M5_speak_and_analyst.md) | D-02, D-06, D-15 | [ ] |
| M6 | Call intents, identification gate, tickets, contact records | [M6_calls_and_records.md](M6_calls_and_records.md) | D-09…D-14 | [ ] |
| M7 | Dashboard `TurnPlan` panel + final verification | [M7_dashboard_and_finish.md](M7_dashboard_and_finish.md) | D-21 | [ ] |

```
M0 ─► M1 ─► M2 ─► M3 ─► M4 ─► M5 ─► M6 ─► M7
       state   deps    files   brain   voice   calls   demo
```

Why this order: state first (everything else writes to it), then dependencies/tools
(nodes become testable), then the file contract (so the new brain is written once against
final English keys and step roles), then the brain, then the mouth, then call-level
policies, then the demo surface.

## 3. Rules for the executor (another agent / another session)

1. **Read first:** this file → [DECISIONS.md](DECISIONS.md) → the milestone file you work on.
   Do not rely on older docs; they are in `docs/archive/` and describe the pre-refactor code.
2. **Branch:** all work happens on `refactor/single-engine` (created from `develop` after
   the docs PR is merged). One PR to `develop` at the end, or one PR per milestone if the
   owner asks. Never commit to `develop`/`main` directly.
3. **Commits:** English messages, one logical step = one commit, each commit leaves
   `uv run pytest` green. End commit messages with the attribution line required by the
   session environment, if any.
4. **Delete as you go:** code, tests, prompts, config options and docs that a step makes
   obsolete are deleted in that same step. No compatibility shims, no "kept for rollback".
   Obsolete tests are deleted, not skipped.
5. **Behaviour is the contract, not the old code.** When moving logic, keep observable
   behaviour (eval scenarios, demo scenarios in `docs/DEMO_SCENARIJAI.md`, dialogue
   reference in `docs/DIALOGO_ETALONAS.md`) unless a decision in DECISIONS.md changes it.
6. **Line numbers drift.** Milestone files cite `file:line` from `develop` @ `c7be3ba`
   (2026-09-14). Always re-locate with grep before editing.
7. **Stop and ask the owner** when: a decision seems contradicted, eval pass count drops and
   the cause is not obvious, a step needs a product choice not covered by DECISIONS.md,
   or something must be deleted that is not listed and is not clearly dead.
8. **Report, don't silently fix** unrelated bugs you find: add them to §6 "Findings log"
   of this file and continue.
9. **Update this file** at the end of every milestone: tick §2, fill §5 status log.

## 4. Commands

Run from the repository root `isp-customer-service/` unless stated.

| Purpose | Command |
|---|---|
| Install | `uv sync` (voice extras: `uv sync --package chatbot-core --extra voice`) |
| Full test suite (CI) | `uv run pytest` |
| One file / one test | `uv run pytest chatbot_core/tests/test_x.py` · `uv run pytest "chatbot_core/tests/test_x.py::TestY::test_z"` |
| Eval (real LLM, needs `.env` keys, rebuilds DB per scenario) | `cd chatbot_core && uv run python src/agent/eval/run_eval.py` (`--only ID`, `--json out.json`) |
| Reset demo DB | `uv run python scripts/setup_db.py && uv run python scripts/seed_data.py` |
| Run app (owner runs live voice tests) | `uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080` |

Test DB note: the pytest session rebuilds `database/isp_database.db` — do not run tests
while the app is serving a live call.

## 5. Status log

| Date | Milestone | Commit | Notes |
|---|---|---|---|
| 2026-09-14 | plan | — | Plan, decisions and milestone files written; old docs archived |
| 2026-09-14 | M0 done | `089c915` … `0126841` | Scenarios added: `D2_outage`, `D3_node_fault`, `D4_switch`, `D5_link_down`, `D6_crc`, `D8_router_hung` (3/3 each), `X_dhcp_silent` (`known_bug`). Baseline on `089c915`: 105/108 checks ×2, 0 unexpected failures. Dead code from M0 §3 deleted (+ `fastrtc` voice extra); pytest 1094 → 1086 (obsolete tests removed), app starts. Q-3 answered (unit test). Voice latency: one billing call recorded instead of 9 (`baseline/voice_latency.md`); owner decision — enough, latency is reviewed separately after the refactor |
| 2026-09-14 | M1 done (owner accepted; live voice check deferred to the owner's later test round) | `1baa7d1` … `74e2766` | Legacy `graph`/`legacy` engines, `AgentState`, `sync_updates` and the non-streaming loop deleted. `GraphState` groups: identity · intake · diagnosis · resolution · ticket · dialog · closing · voice + `turn` (field renames: `diagnosis`→`diagnosis.verdicts`, `resolution`→`resolution.procedure`, `ticket_stage`→`ticket.stage`). All Appendix A flags promoted (one commit per group); only runtime attributes stay on the engine. Nodes run through `runtime.run_on_state` (state in, full state out); between-turn writes via `update_state` / a session inbox; one SqliteSaver per API process. pytest 1079 green (legacy/parity tests removed, new: checkpoint serde, between-turn writes, shared saver, `test_single_state`). Eval 105/108, every scenario identical to the M0 baseline. Deep copy per node ≈0.9 ms at 360 messages. Deviations: ticket context model carries all 12 keys the dialogue uses (plan listed 7); `faults.step_by_id` not added (only the step id is ever read); background telemetry rides `turn.bg_diagnosis` (per-turn inbox) instead of `voice.bg_diagnosis`; eval/fuzz read `session.state` after `end_session` (the hang-up net now runs on the checkpoint) |
| 2026-09-14 | M2 done (live voice check deferred to the owner's test round) | `981e9d9` … `ed8494d` | `AgentRuntime` (`agent/runtime.py`, built by `new_call()`) is the graph `context_schema`; nodes are `(state, runtime)`, work on a copy and return `node_update()`; `run_on_state` and the engine adapter deleted — the session holds no `ReactAgent`, nodes narrate through the `graph_v2.runtime.narrator()` factory. `ToolGateway` + `LocalToolProvider` (`agent/tooling/`): all 14 direct call sites and the LLM tool loop go through it, each `tool_call` traced with a `reason`; `telemetry(mode=snapshot|recheck)`; `append_ticket_note` and `address_registry()` replace raw SQL. Helpers moved to `trace.py`, `dialog_utils.py`, `delivery.py`, `speculation.py`; all flows take `(state, rt)`; RA delegates deleted — RA keeps only the §3 members (+ `_persist_call_record`/`_build_call_summary` as `end_session` helpers). Test fixtures `make_state()`/`make_runtime(fake_tools)` + `FakeToolProvider`. pytest 1086 green, app starts. Eval 105/108, every scenario identical to the M0 baseline. Deviations: `telemetry` has no `level` parameter yet (both levels always computed; M6 adds level 1); step 6 (flows take `(state, rt)`) landed as one commit instead of one per module; no `fake_llm` fixture (no LLM port before M5); flow tests still use `make_agent()` as a `(state, runtime)` holder; `_apply_bg_diagnosis` became `speculation.apply_bg_diagnosis` called at the same point of the turn, not an inbox merge in the session (keeps the timing); `app/main.py` `simulate_plug`/`simulate_reboot` dashboard endpoints still call `agent.tools` directly (outside a turn, no state/runtime); the ticket's executed-tools list now also shows gateway-internal calls (e.g. telemetry rechecks, `append_ticket_note`) since every call is traced |
| 2026-09-15 | M3 done (owner voice check 2026-09-15 on `router_hung`, CUST112: resolved without a ticket; findings F-18, F-19) | `4999f66` … `e12c73b` | Knowledge contract: pydantic schema with cross-reference validation (`agent/contract/schema.py`); locale layer `locales/lt/` (`phrases.yaml`, `vocabulary.yaml`, `examples/*.md`, `lang.py`) with `phrase`/`vocab`/`examples` accessors — no customer sentence or reader vocabulary left in Python outside the M5 directive code; step roles + `knowledge/verdicts.yaml` flags replace every hardcoded step id / verdict set; unclear fault is a pack, in-code `STRATEGIES` deleted (F-1 fixed, gate test added); all schema keys, evidence codes and LLM JSON contracts English; prompts English with `<<examples:…>>` + `<<language>>`, inline prompts moved to `prompts/sensors/`; `knowledge/limits.yaml` (61 limits, env override wins) + `knowledge/policies.yaml` (tools needing an identified caller); `contract/loader.py` validates knowledge + locale + prompts at startup (a broken pack stops the app with file/key; verified with uvicorn), `loader.reload()` + `POST /admin/knowledge/reload` (validates first); code comments English. pytest 1120 green, app starts. Eval 105/108, every scenario identical to the M0 baseline. Deviations: **`prompts/sensors/perception.md` + `perception_step.md` stay Lithuanian** — the English version made gpt-4o-mini read „Perkišau“ as still in progress (D5 0/4; isolated A/B on the captured context: LT 12/12 done, EN 12/12 waiting; several English variants did not recover it) → revisit when perception is reworked (M4); two verdict flags beyond `line_fault` (`unresolved_after_fix`, `device_visible`, `healthy_up_to_router`) and an `inform` enum flag; LT wording referenced inline as `<<examples:file/section>>` instead of `examples_key`; playbooks stay in `rag/knowledge_base` (heading marker read from vocabulary); `adapters/asr/lt_text.py` stays in adapters (`lang.normalize_numbers` re-exports it); no `service_area.yaml` (served city stems are vocabulary); detector glosses and step answer meanings are locale phrases; active language is process-wide; step `consent` is still a bool (M4 adds required|not_required); `bridge_phase` condition still never set automatically; LT directive strings and payload keys in `narrator_flow`, `perception_flow`/`identification_flow` address directives and `speculation` stay until M5; limits in code M5 deletes (`narrator_flow`, `react_agent`, `speculation`), text-length caps, slot confidences and `AgentConfig`/LLM settings are not in `limits.yaml`; `app/runtime_config.py` dashboard labels/comments still Lithuanian (UI, outside `src/agent`) |
| 2026-09-15 | M4 done (owner live test 2026-09-15: full dead-router call works; polishing of nuances deferred until after M7; the other demo calls and the contradiction call were not run) | `02ac9ef` … `a774e1e` | Graph is `perceive → decide → execute → narrate` (router, stage nodes and the diagnosis subgraph deleted). `agent/perceive/` holds all reading (slots, NLU, evidence ingest, side topic, caller intro, classifier); `agent/decide/` holds `TurnPlan` (`plan.py`), the ordered `policy.py` chain pinned by `test_policy_order.py`, `rules/` (dialog, closing, ticket, head, hypothesis_confirm, stage, reply, diagnosis, evidence, identification), the procedure runner (`procedure.py` + `procedure_guards.py`, `advance` → `StepOutcome`), the hypothesis state machine with one `Contradiction` record (D-05; a telemetry recheck or client conflict asks the confirm question before switching, max 2 asks), the active question (`question.py`, replaces `dialog_registry`) and the plan gate (`gate.py`: closed action set, `policies.forbidden_actions`, `steps[].consent: required|not_required` checked against `dialog.consents`). `agent/execute/` runs actions and speaks (`actions.py`, `diagnosis.py`, `ticket.py`, `identification.py`, `say.py` with the scripted exits). Every turn emits one `turn_plan`. One driver: `meta.driver`, `SOLVER_DRIVE`/`SOLVER_SHADOW`, shadow solver, `solver_flow`, `evidence_drive`, `ticket_flow`, `closing_flow`, `perception_flow`, `identification_flow`, `dialog_registry`, `RA._stuck_backstop/_apply_backstop/_commit_driven_reply` deleted; DoD grep empty. Fixed: F-5 (stuck close registers the promised ticket / closes unidentified with reason), F-7 (no silent hypothesis replacement), F-8 (`dhcp_silent`/`no_port_data` → unclear-fault ticket, no jargon). pytest 1149 green, app starts. Eval 107/108 (baseline 105): `X_dhcp_silent` now passes (F-8); `S1v_side_topic_deviation` `reply_len` max 289 > 280 (LLM length, flaky near the cap). `turn_plan` vs the step-2 shadow baseline: 78/190 turns identical on (owner, action, say kind); the rest are labelling (the shadow recorded stage-node owners and step roles, plans now name the rule family, `run_due_action`, `preflight_phone`, `register_ticket:auto`), the F-8 path in `X_dhcp_silent`, and LLM-path noise (`I4`, one `S4` turn); step 10 changed no plan vs step 8. Deviations: rows 11-12, 14-15 and 18-19 run in the narrator's reply layer (`rules/reply.py`, called by `execute/say.py` after the procedure moves) instead of standalone entries in `policy.py` — their precedence is kept exactly, `policy.py` lists rows 1-10, 13 and the stage entry (20); no separate `rules/inform.py`/`rules/side_topic.py` (inform and side topic live in `stage`/`reply`); no `execute → decide` re-decide edge and no `max_redecide_per_turn` (no scenario needed it); rules are not pure yet — several still write state or start the ticket dialogue while deciding, and the problem gate / ticket reader / solver LLM calls stay in decide (M5 sensors); `advance` takes `(state, rt, user_input)`; the speculative injected reply stays in the narrator's LLM loop (it replaces the LLM call, no decision); `narrator_flow` keeps directives, tool results and `activate_hypothesis` on the first verdict until M5; the sensor prompts `perception.md` and the ticket reader stay Lithuanian (English regressed D5 and T1); the checkpoint type of the active question moved (`agent.graph_v2.state.ActiveQuestion`) — checkpoints written before `97c24d2` do not restore that field; F-11, F-12, F-15, F-17, F-19, F-20 (planned for M4) are not fixed — the port kept today's behaviour — owner moved F-11/12/15/17/19 to M5 and F-20 to M6 |

## 6. Findings log (bugs/risks found during the refactor, not fixed in scope)

Pre-filled from the 2026-09-14 code research:

| # | Finding | Where | Handled in |
|---|---|---|---|
| F-1 | Solver gate knows only 4 in-code verdicts → `propose_fix` downgraded for `router_hung`, `link_down_local`, `crc_errors` | `agent/solver_flow.py` `known_hypotheses=set(STRATEGIES)` | M3 step 6 |
| F-2 | Process-global LLM rate limiter: 100 calls/"session" counter never reset in the API | `services/llm/rate_limiter.py` | out of scope (integration) — note only |
| F-3 | A WebSocket disconnect does not end the session; call record written only on DELETE/TTL/shutdown | `app/main.py` WS `finally`, `app/sessions.py` | M6 (finalizer) |
| F-4 | `outcome` column overwritten by transport strings (`client_closed`, `expired`) | `react_agent.end_session` → `save_call_record` | M6 |
| F-5 | Stuck backstop says "I will register" but creates no ticket | `react_agent._stuck_backstop` (~L1958-1974) | M4 — fixed (`8d6944f`: identified → `register_ticket` reason `stuck`; unidentified → close with `closing.unidentified_reason="stuck"`) |
| F-6 | Identity can be committed by an LLM tool call or a dictated address without explicit confirmation; `address_confirmed` never set | `narrator_flow.update_state_from_observation`, `perception_flow` guards | M6 |
| F-7 | Hypothesis silently replaced on every diagnose observation (no confirmation) | `walker_flow.open_hypothesis` via `narrator_flow` | M4 — fixed (`127d5a9`: a new verdict under an active procedure is a `Contradiction`; the belief changes only after the caller confirms) |
| F-8 | `dhcp_silent`, `no_port_data` have no pack and no inform template → free LLM with all tools | `verdict.py`, `narrator_flow.scoped_tools_schema` | M4 — fixed (`b85cf96`: plan gate + unclear-fault ticket, verdict kept as telemetry only) |
| F-9 | SQLite checkpointer connection opened per session, never closed; relative path depends on CWD | `graph_v2/checkpoint.py` | M1 — fixed (`e98329f`: one saver per process, absolute path, closed on shutdown) |
| F-10 | `_ticket_directive` not reset on ticket/identification/closing routes (can linger) | `perception_flow.py` ~L82 | M1 — fixed (`061913b`: directives live in `turn.directives`, reset every turn) |
| F-11 | "Neveikia internetas visuose įrenginiuose" in the first turn is not captured: after `router_hung` the agent still asks "visuose ar tik viename?" (eval probe, CUST112) | understand / facts intake | M5 (moved from M4 by the owner 2026-09-15; the M4 precedence port left it unchanged) |
| F-12 | `router_hung`: caller says "perkroviau, internetas atsirado" before the reboot instruction → agent ignores it and asks to reach the router; "Ne, ačiū, viso gero" then creates a ticket on a line the caller called working (eval probe, CUST112) | procedure walker / closing | M5 (moved from M4 by the owner 2026-09-15; the M4 precedence port left it unchanged) |
| F-13 | Link-down/CRC ticket offer: caller answers the phone-number question with "Ačiū, viso gero" → agent re-asks "Registruoti, ar tikrai nereikia?" yet `create_ticket` still runs (eval probe, CUST104) | ticket flow / closing | M6 |
| F-15 | `router_hung` at `rh_check`: "Perkroviau, internetas atsirado" is read as intent `done` but the walker holds and the narrator asks to check the lights again; the case closes as resolved only through the hang-up net (same in the M0 baseline) | walker `rh_check` / restored detection | M5 (moved from M4 by the owner 2026-09-15; the M4 precedence port left it unchanged) |
| F-16 | `resolution.py` defined `_ONE_MARK` twice; the first tuple (with `"tik "`, `"vien "`) was dead, only the second was used | `agent/resolution.py` scope detector | M3 step 4 — dead copy dropped (`0b616f3`), behaviour unchanged |
| F-17 | Perception anchor goes stale: when the agent's reply has no question (an instruction ending "Pasakykite, kai padarysite."), `AGENT'S LAST QUESTION` still shows the previous question ("Ar ji dega ar mirksi?"), so a done-report is judged against the wrong question (seen in the D5 prompt-language regression; with a correct anchor the English prompt still misread it 10/12, so it is one factor, not the whole cause) | `perception_flow.anchor_text` | M5 (moved from M4 by the owner 2026-09-15; the M4 precedence port left it unchanged) |
| F-18 | Analyst notes after the English `sensors/analyst.md`: every turn (10/10 in the voice check) says the caller "neatsako į aktyvų klausimą… — pokalbis nukrypo" even when they answered, and fires the deviation flag (the pre-M3 Lithuanian prompt: 1/3). The notes reach the narrator context as noise; eval does not cover it (analyst runs in voice only). Owner decision: do not patch now — the analyst is rebuilt as signals in M5 | `prompts/sensors/analyst.md`, `agent/analyst.py` | M5 |
| F-19 | Voice check `router_hung`: (a) "Mirksi… veikia, ačiū, viskas gerai" at the reboot check triggers the farewell confirm ("Ar tikrai norite baigti? galiu užregistruoti gedimą") twice instead of closing as restored — resolved only by the hang-up net (same class as F-12/F-15); (b) "Galo?" (ASR for "Galiu") gets the reboot instruction, then "Ištraukiau" is read as the yes to the ability step and the instruction is repeated | walker guards (farewell before restored), `rh_ability`/`rh_reboot` | M5 (moved from M4 by the owner 2026-09-15; the M4 precedence port left it unchanged) |
| F-20 | After a resolved close, "Ne, ačiū, viskas" (no more questions) is read by the closing node's still-down check as "not working" → the case reopens and the ticket dialogue starts ("Telefonu neišspręsim… Registruoju meistrą"); present in the M4 shadow baseline (`S1v_side_topic_deviation` last turn) | `graph_v2/nodes/closing.py` still-down reopen (`detect_restored` on a bare "ne") | M6 (moved from M4 by the owner 2026-09-15; the M4 precedence port left it unchanged) |
| F-21 | Ticket dialogue started from the no-path (TV) case: the caller's NAME answer ("Andrius, taip, mano sutartis") is captured as phone consent (`phone_captured`), so the next answer ("Taip, tinka šis numeris") lands on the hours question; the ticket reader then may read it as a refusal and the ticket is cancelled (`T1_tv_unclear_fault_ticket` flaky). The English ticket reader made it 5/10 → kept Lithuanian (`e7ce73d`, 1/10) | `perception_flow.pre_turn_guards` ticket capture, `identification_flow` caller-name vs ticket intro | M6 (tickets) |
| F-14 | `no_port_data` cannot be reached in eval: every seeded customer has a port row (covered only by `tests/test_verdict.py::test_no_port_data`) | `database/seeds/` | Q-3: unit test accepted |

## 7. Out of scope (do not do in this refactor)

Other languages' content (only the mechanism), Postgres checkpointer, telephony/SIP,
call resume after crash, authentication/HTTPS hardening, real CRM/NMS adapters, TTS vendor
change, new fault packs (TV, slow internet), presentation material, end-user documentation.
Those come after the refactor (see DECISIONS.md D-22).

## 8. Open questions (answer before the milestone that needs them)

| # | Question | Needed by | Answer |
|---|---|---|---|
| Q-1 | Delete the unused MCP servers (`crm_service/src/crm_mcp/server.py`, `network_diagnostic_service/src/network_diagnostic_mcp/server.py`) and their repository classes, or keep MCP as the future integration transport? | M0 | **Keep** (2026-09-14). MCP may be the transport to the customer's DB/tools — decided during integration. Do not delete servers, repository classes or server-only tool functions. |
| Q-2 | Keep the voice speculation feature (`agent/speculation.py`, pre-computed replies) and adapt it to `TurnPlan`, or delete it? | M5 | **Remove in M5, re-evaluate after M7** (2026-09-14). It exists only to cut latency and depends on the old directive mechanism. After the refactor, measure latency (see §9); rebuild on `TurnPlan` only if it is still needed. |
| Q-3 | M0 DoD needs every `decide()` verdict in an eval scenario, but no seeded customer lacks a port, so `no_port_data` is unreachable (F-14). Add a seed customer without a port row (e.g. `CUST113`, additive, visible in the demo DB), or accept the unit test as coverage? | M0 | **Unit test is enough** (2026-09-14). Not every verdict needs an eval scenario; `no_port_data` stays covered by `tests/test_verdict.py::test_no_port_data`. |

## 9. Post-refactor checks (owner decides after M7)

| # | Check | How | Decision it feeds |
|---|---|---|---|
| P-1 | Is pre-computed reply speculation still needed? | Repeat the calls in `baseline/voice_latency.md` and compare `voice_latency` (`total_ms` = server-side time to first audio; `ttfa_ms` is not traced): M0 baseline (speculation on) vs after M7 (no speculation). Record numbers in `docs/refactoring/RESULT.md`. Owner (2026-09-14): one baseline call is enough; a dedicated latency review (causes + improvements) follows the refactor. | Rebuild speculation on `TurnPlan` (predict plans for the top answers of `awaiting`, pre-render `phrase` plans) or drop it for good |

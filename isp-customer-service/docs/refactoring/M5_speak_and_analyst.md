# M5 — `speak` node and analyst signals; `ReactAgent` deleted

> Part of [REFACTORING_PLAN.md](REFACTORING_PLAN.md). Read its "Rules for the executor" first.
> Decisions: D-02 (speaker never decides), D-06 (analyst = signals), D-15 (phrase | directive),
> D-19 (English prompts). Prerequisites: M4 done. Q-2 answered: speculation is removed here and
> re-evaluated after M7 (plan §9).

Legend as in M1. Line numbers from `develop` @ `c7be3ba`; re-locate with grep.

---

## 1. Why

- After M4 the narrator (`RA._run_until_response_stream` + `NF.build_messages` +
  `NF.state_facts_block`) still: calls tools (identification lookups), builds a 49-section
  Lithuanian "KNOWN FACTS" block (`NF` ~L284-1163) full of one-shot directives, and lives inside
  the last big class, `ReactAgent`.
- The analyst (`A/analyst.py`) only shapes wording, runs only in the voice path, writes an engine
  attribute from a background thread (`AN` ~L150) and is consumed as free text (`NF` ~L1151-1158).

## 2. Before → After

| Before | After |
|---|---|
| `narrate` node → `ReactAgent` LLM loop with tools | `speak` node: renders `plan.say`, **no tools** |
| 49 LT facts sections, one-shot flags consumed while rendering | one English **context card** built from state + `TurnPlan` |
| Stage prompts `P/stages/*.md` per node | one `P/speak/system.md` + `P/speak/owners/<owner>.md` goal snippets |
| Identification lookups by LLM tool calls | `identification.*` rules plan `resolve_address` / `find_customer` actions (executed by `execute`) |
| Analyst: free-text notes to narrator, voice only, thread writes engine | `analyst` step: typed `signals` → state (via turn input / `update_state`) → consumed by `decide` |
| `ReactAgent`, `A/react_agent.py`, `A/narrator_flow.py` | deleted |

### `speak` contract

```
speak(state, rt):
  plan = state.turn.plan
  if plan.say.kind == "phrase":    text = rt.locale.phrase(plan.say.key, **plan.say.vars)   # stream as one chunk
  if plan.say.kind == "directive": text = LLM(system=P/speak/system.md + owners/<owner>.md,
                                              context_card(state, plan), history_window, goal=plan.say.goal)
  post-process (safety only, never decisions):
     - registration claim guard (no "I registered" unless ticket.ticket_id)
     - repeat guard → dialog.stuck_count / dialog.last_reply_repeated
     - length cap from K/limits.yaml
  return {messages: +assistant, dialog.last_question, turn.reply}
```

### Context card (English, compact, deterministic order)

`Caller & identity` · `Service profile` (M6) · `Problem & anamnesis` · `Hypothesis (cause, status,
contradiction quote)` · `Awaiting (what we asked, what answer we need)` · `Procedure step
(goal, hint, playbook section text)` · `What the client just said (understanding)` ·
`Delivery notes (unheard question, overlay, undelivered tail)` · `Allowed content for side topic
(FAQ answer)` · `Plan goal` · `Must not` (from `K/policies.yaml`).

Every section is generated from typed state; no section may carry an instruction that changes
**what** to do — only **how** to say what `decide` chose.

## 3. Affected files

**Create**
- `A/speak/node.py`, `A/speak/context_card.py`, `A/speak/postprocess.py`, `A/speak/history.py`
  (moved `history_summary`, `prune_history`, `recall_lines` from `NF` ~L188-281).
- `A/analyst/node.py` (analyst step), `A/analyst/signals.py` (typed model).
- `P/speak/system.md`, `P/speak/owners/{intake,identification,inform,side_topic,diagnosis,procedure,ticket,closing}.md`.
- `A/session_record.py` — temporary home for `_build_call_summary` / `_persist_call_record` moved
  from RA (M6 replaces it with the finalizer).

**Delete**
- `A/react_agent.py` (whole file), `A/narrator_flow.py` (whole file), `v2/runtime.py` narrate/speak
  helpers, `P/stages/` (replaced), `P/partials/directives.md` (directive markers are gone), the
  `NARRATOR_QUESTIONS` flag (goal vs scripted wording is now `say.kind`), `v2/tool_scopes.py`,
  `REAL_TOOLS` LLM schemas that are no longer offered to any LLM (keep the tool implementations),
  `A/analyst.py` (moved), `ANALYST` free-text note plumbing.
- Tests of deleted internals (`test_history_v2.py` moves to `A/speak/history` tests;
  `test_streaming_agent.py` stays if it tests `services.llm.client`).

**Modify**
- `SE` (no `_agent`; stats from `rt.llm`; cancel through `rt.cancel`), `A/voice_pipeline.py`,
  `chatbot_core/src/app/voice.py` (~L353-372 background thread triggers; ~L162 private access),
  `chatbot_core/src/app/main.py`, `chatbot_core/src/app/sessions.py` (`build_turn_summary` reads
  `turn_plan` + `llm` events), `A/eval/run_eval.py` (reads `session.state` via the graph),
  `A/eval/fuzz.py`.

## 4. Step-by-step

1. **Identification without LLM tools.** Add rules/actions so that address and phone lookups
   are planned by `decide` (`resolve_address`, `find_customer`) and executed by `execute`, with
   the result folded back by the gateway state update. Remove `LOOKUP_TOOLS` from the narrator;
   update `P/partials/identification.md` which today tells the LLM to call `check_outages` /
   `close_case` (~L28-30). Eval identification scenarios I1–I6, T2, G2 must pass. Commit.
2. **Context card + speak node (directive path).** Implement `context_card.py` from typed state;
   port only the information content of the 49 facts sections (list them in the PR description
   with "kept as card field X" / "removed: was a decision, now rule Y"). Write
   `P/speak/system.md` + owner snippets in English (persona from `P/partials/identity.md`,
   style rules, `{output_language}`; Lithuanian examples via `<<examples:…>>` from M3).
   Commit.
3. **Phrase path + post-processing.** `say.kind == "phrase"` renders locale text; post-processors:
   registration claim guard (from `TF.registration_claim_guard` ~L241-274), repeat guard
   (RA `_track_stuck` ~L1914-1934, `_similar` ~L1891-1901), length cap. Commit.
4. **Streaming and cancel.** Stream tokens with `get_stream_writer`; check `rt.cancel` between
   tokens; on cancel append the partial reply with "—", roll back the ask counter for the awaited
   evidence key (logic of RA `on_turn_cancelled` ~L663-678). `SE.handle_turn_stream` keeps the
   same public behaviour for `app/`. Commit.
5. **Analyst signals.**
   - Model: `Signal(type: contradiction|already_answered|secondary_problem|off_topic|frustration,
     fact_key: str|None, quote: str|None, confidence: float)`; max signals per turn from limits.
   - Prompt `P/sensors/analyst.md` (English, JSON output; created in M3) — reads the full
     conversation, ledger summary, hypothesis, awaited answer.
   - Execution: `ANALYST_MODE=async|sync|off` in config. `async` (voice default): after the turn,
     a background task computes signals and puts them into the session inbox → next turn input
     `voice.analyst_signals`. `sync` (text/eval default): runs as the last step of the turn.
   - Consumption in `decide` (M4 rules): `contradiction` → `hypothesis.py` entry (doubt);
     `already_answered` → confirm with the quote instead of asking again; `secondary_problem` →
     candidate in `intake.secondary_problems` with `source="analyst"` (closing asks);
     `off_topic` → return-to-anchor phrase; `frustration` → tone hint added to `say.goal`.
   - The analyst never writes facts, never changes the hypothesis, never speaks (D-06).
   Commit.
6. **Remove speculation (owner decision Q-2).** Delete `A/speculation.py`, the `SPECULATION`
   flag and dashboard option, `session.speculate_next`, `speculation_match`,
   `turn.injected_reply`, the `voice_pipeline` hooks (~L419-436) and the background trigger in
   `app/voice.py` (~L353-372; keep the background **analyst** trigger), tests in
   `test_voice_v1.py` Speculation class. Keep the background telemetry snapshot only if M6 still
   needs it for the held outage check; otherwise delete it too. Latency is re-evaluated after M7
   (plan §9, P-1) — if needed, speculation is rebuilt on `TurnPlan` then. Commit.
7. **Delete `ReactAgent`.** Move remaining helpers (`_build_call_summary`, `_persist_call_record`,
   `_tools_called_this_session`, `_record_llm_stats`) to `A/session_record.py` / `rt.llm`; delete
   `A/react_agent.py`, `A/narrator_flow.py` and everything in §3 "Delete". Commit.

## 5. Tests

- New: `test_speak_phrase.py`, `test_context_card.py` (card fields for each owner; no
  decision words like "ask now"/"register" originate from the card unless `plan.say.goal` says so),
  `test_speak_postprocess.py`, `test_speak_cancel.py`, `test_analyst_signals.py` (schema, async
  inbox delivery, decide consumption).
- Adapt `test_api.py` (patches of `agent.react_agent.stream_tool_completion` ~L71 → patch the
  LLM facade), `test_voice_v1.py`, `test_overlay_stage2.py`, `test_tracing.py`
  (`TestReactAgentEmits` → speak/decide emits), `test_understand.py` (~L491
  `run_turn_scoped_stream`).
- Eval full run ≥ baseline (reply length check: max 280 / avg 160 chars).

## 6. Definition of Done

- `grep -rn "ReactAgent\|react_agent\|narrator_flow\|state_facts_block\|LOOKUP_TOOLS\|NARRATOR_QUESTIONS" chatbot_core` → nothing.
- The speak LLM call has `tools=None` in every trace (`llm` events).
- Every analyst output in traces is a typed `analyst_signals` event; no free-text notes reach the
  speaker.
- `P/` contains no Lithuanian (examples live in `locales/lt/examples/`).
- `uv run pytest` green; eval ≥ baseline; owner live voice test (barge-in, overlay, unheard
  question, contradiction call).

## 7. Risks & rollback

- **Tone/quality drop** after replacing hand-tuned LT directives with an English card: compare
  eval transcripts side by side for the 9 demo scenarios; the owner judges wording on the demo
  calls before the milestone is closed.
- **Latency:** the card must be shorter than today's facts block; measure `llm` input tokens and
  `ttfa_ms` on voice before/after.
- **Async analyst race:** signals for turn N arriving after turn N+1 started are dropped if their
  `turn_index` is stale (store the index in the signal).
- Rollback: revert per step.

# M7 — Dashboard TurnPlan panel and final verification

> Part of [REFACTORING_PLAN.md](REFACTORING_PLAN.md). Read its "Rules for the executor" first.
> Decisions: D-21, D-02, D-05. Prerequisites: M6 done.

Paths relative to `chatbot_core/src/`. Line numbers from `develop` @ `c7be3ba`; re-locate with grep.

---

## 1. Why

- The owner wants the demo audience (and himself when debugging) to **see the engineer think**:
  who owns the turn, which rule fired, the hypothesis and its status (active → doubt →
  confirming → changed), the action and what the agent waits for.
- The refactor must end with an explicit, repeatable verification and a clean handover.

## 2. Before → After

| Before | After |
|---|---|
| Brain panel renders `node`, `decision`, `verdict`, `tool_*`, … (`app/static/index.html` `onEvent` ~L278-314); `turn_plan`, `analyst_signals` not rendered | A **Turn plan card** per turn: owner · rule · hypothesis chip with status colour · action · awaiting · say kind; analyst signals as small tags |
| Archive formatter `fmtEvent` (~L708-724) lacks new events | Archive shows the same card |
| `export_txt` (`adapters/tracing/jsonl_tracer.py` ~L166-292) skips new events | Transcript export includes one line per `turn_plan` |

## 3. Affected files

- `app/static/index.html` (`onEvent` case `turn_plan`, `analyst_signals`; `fmtEvent`; `renderTurn`
  chips ~L316-334; CSS for hypothesis status colours — follow existing styles).
- `app/sessions.py` `build_turn_summary` (~L67-113): include `rule`, `owner`, `hypothesis.status`.
- `adapters/tracing/jsonl_tracer.py` `export_txt`.
- Remove rendering branches for events that no longer exist after M4/M5 (`drive_decision`,
  `shadow_decision`, `decision` if replaced, `scripted` if replaced by `turn_plan`) — grep the
  emitters first.

## 4. Step-by-step

1. **Event payloads final.** `turn_plan` event = `TurnPlan.model_dump()` + `turn_index`;
   `analyst_signals` = list of signals + `turn_index`. Pin with `test_turn_plan_trace.py`. Commit.
2. **Live panel.** Render the card; hypothesis status colours: active (neutral), doubt (amber),
   confirming (blue), changed (green with "from → to"). Keep it readable at phone width.
   Commit.
3. **Archive + export.** Same card in archive; `export_txt` line format:
   `[plan] owner=procedure rule=procedure.verify_reboot hyp=router_hung(doubt) action=tool:telemetry.recheck say=directive`.
   Commit.
4. **Final verification (no code changes unless a check fails):**
   - `uv run pytest` — green.
   - Eval twice — pass count ≥ M0 baseline plus new scenarios; store both JSON runs in
     `docs/refactoring/baseline/final/` with a README (date, commit, models).
   - Acceptance greps from every milestone DoD re-run in one script
     `scripts/refactor_acceptance.py` (commit it; it is useful for future regressions).
   - App starts; owner live voice session on the 9 demo scenarios (`docs/DEMO_SCENARIJAI.md`)
     + contradiction call + repeat call with open ticket + unidentified hang-up.
   - Latency check P-1 (plan §9): collect `ttfa_ms` / `voice_latency` from those voice sessions
     and compare with the M0 baseline; write the numbers into `RESULT.md` for the owner's
     speculation decision.
5. **Handover.** Update `REFACTORING_PLAN.md` (all ticks, status log, findings), write
   `docs/refactoring/RESULT.md` (1 page: what changed, final architecture diagram, known
   limitations, follow-ups for documentation/presentation), update `docs/DEMO_SCENARIJAI.md`
   where behaviour changed (M6 outage announcement timing). Open the PR
   `refactor/single-engine → develop` with an English description; the owner merges.

## 5. Definition of Done

- Every turn of a live call shows a Turn plan card; hypothesis transitions are visible on the
  contradiction call.
- Final verification items all pass; `RESULT.md` written; PR opened.

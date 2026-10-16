# Eval after the refactor (M7 final verification)

The same harness as the M0 baseline ([../README.md](../README.md)), run twice at the end of
M7 in an isolated worktree (own SQLite DB) so a live demo server was not disturbed.

| Field | Value |
|---|---|
| Date | 2026-09-17 |
| Git commit | `9a5454c` (`refactor/single-engine`, code identical to the PR head; later commits change docs and comments only) |
| Engine | single engine: `perceive → decide → execute → narrate` |
| Agent model | `gpt-4o-mini` |
| Perception / analyst model | `PERCEPTION_MODEL=default` → the agent model; `ANALYST_MODE` default |
| Eval env | `SIMULATE_BRIDGE=on`, `SIMULATE_REBOOT=on`, LangSmith tracing off (set by `run_eval.py`) |
| Scenarios | 33 (the 25 from M0, minus `G2_boundary_saskaitos`, plus 9 added in M5–M7: A1, D2b, R1, R1b, R2, R3, R4, S10, U1) |

## Results

| Run | Checks passed | Unexpected scenario failures | Expected failures (`known_bug`) |
|---|---|---|---|
| M0 baseline run1 / run2 | 105 / 108 · 105 / 108 | 0 · 0 | `X_dhcp_silent` (fixed in M4, F-8) |
| **final run1** | **178 / 178** | 0 | none |
| **final run2** | **177 / 178** | 1 | none |

The check count grew from 108 to 178 because of the new scenarios and the per-scenario
`contact_record` check (exactly one conversations row per call, M6).

**The one failure (run2):** `A1_repeat_and_frustration` — `reply_len` max 325 characters
(cap 280): one narrator reply was long (LLM variance; the same scenario passed in run1).
Its transcript also shows a real open behaviour: after „Gerai, perkroviau — atsirado“ the
agent said the callback goodbye instead of confirming the fix — the F-12 / F-15 class,
ROADMAP R-7.

## Files

| File | Content |
|---|---|
| `eval_run1.json`, `eval_run2.json` | `run_eval.py --json` output; `trace` is the file name only (traces are not committed) |

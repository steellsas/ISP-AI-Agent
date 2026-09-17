# Conversation eval harness — Golden Dataset

The safety net **required before any reasoning change** (introduced in Phase 3.8 step 0;
the original spec is archived at `docs/archive/MASTANTIS_AGENTAS_SPEC.md`; the refactor
that keeps it green is `docs/refactoring/REFACTORING_PLAN.md`). Drives `AgentSession`
text-to-text through scripted CLIENT turns and hard-scores the resulting conversation
**state + replies + contact record**.

The LLM only phrases; the engine decides. Each turn runs the graph
`perceive → decide → execute → narrate`, and `decide` (the rules, the procedure runner
`decide/procedure.py` and its guards, the solver and the plan gate) produces one `TurnPlan`
from state and the scripted turn, so the **state trajectory** (verdict, disposition,
identification, contact-record outcome) is stable enough to assert on — unlike free-form
reply text, which is only checked for required / forbidden substrings.

## Run
```bash
cd chatbot_core
uv run python src/agent/eval/run_eval.py                          # all scenarios
uv run python src/agent/eval/run_eval.py --only S8_billing_inform  # one scenario by id
uv run python src/agent/eval/run_eval.py --no-db                   # skip DB rebuild (faster reruns)
uv run python src/agent/eval/run_eval.py --json report.json        # also write the raw report
```
Needs LLM API keys in `.env` (drives the REAL model, like a live call). The harness
validates the knowledge files at startup (`contract.loader.startup()`), sets
`SIMULATE_BRIDGE=on` and `SIMULATE_REBOOT=on`, and turns LangSmith tracing off. The DB is
rebuilt from the versioned seed (`scripts/setup_db.py` + `scripts/seed_data.py`) **before
each scenario** (bind/reset stubs mutate it — scenarios must not leak state; sub-second).
`--only` with an unknown id exits with code `2`. `--json` writes, per scenario: `id`,
`known_bug`, every check (`name`, `pass`, `detail`), `verdicts_seen`, `disposition` and the
trace path.

The recorded pre-refactor results live in
[`docs/refactoring/baseline/`](../../../../docs/refactoring/baseline/README.md).

## Scenarios (`scenarios.json`)
33 scenarios (2026-09-17). Each scenario = `{id, phone, desc, turns[], expect{}, known_bug?}`.
The scorer (`_score` in `run_eval.py`) runs these checks:
- `verdict_in` — the expected verdict reason appears at some point (hypothesis cause,
  procedure verdict or the network verdict, across turns).
- `disposition` — `resolved | ticket | outage | inform | declined | open | any`
  (`ticket` = a `create_ticket` tool call ran; `inform` also accepts `open`/`outage`;
  `any` is not scored).
- `identified` — `true`/`false`: whether the call ended with a committed customer id.
- `reply_any` — at least ONE of the listed substrings appears (synonyms / OR-group).
- `reply_none` — NO reply contains ANY listed substring (regression guard for a bug).
- `tool_used` — each listed tool call actually ran (read from the session trace); one
  check per listed tool (`tool_used:<name>`).
- `contact_record` — **always on**: exactly one row for the call in the `conversations`
  table (D-14).
- `record_outcome` — the contact record's `outcome`, compared together with
  `unidentified_reason` against `expect.record_reason` (`null` when not given); scored only
  when present in `expect` and a record exists.
- `reply_len` — **always on**: voice-length guard, longest reply ≤ 280 chars, average ≤ 160.

The first six and `record_outcome` run only when present in `expect`. A full run scores
~178 checks (2026-09-17); every new scenario adds 2 (`contact_record`, `reply_len`) plus one
per `expect` key and one per `tool_used` entry.

## `known_bug` scenarios
Flagged `known_bug: true` encode a fault found in voice testing. They are **expected to
fail now** (shown as `xfail`, exit code stays 0) and turn **green** once the fix lands —
so the bug can never silently return. Once a known bug is fixed and stably green, PROMOTE
it (drop the flag or set it to `false`) so a future regression fails the suite instead of
hiding as `xfail`.

No scenario is flagged `known_bug: true` at the moment. `X_dhcp_silent` was the last one
(the `dhcp_silent` verdict had no pack, so the free LLM improvised jargon and a
factory-reset suggestion with no ticket); refactor M4 fixed it (F-8: an unclear-fault
ticket without telemetry jargon) and it is now `known_bug: false`, a must-pass guard.
`S4_dead_router_bridge` was the first known bug — the agent blamed the router's power
after the PC was plugged in — and the Phase 3.8 dr_intro desync fix closed it.

## Exit code
`0` = no UNEXPECTED failures (known_bug scenarios may fail). `1` = a scenario that
should pass failed — a real regression. `2` = `--only` named no scenario.

## Extending
Add a scenario to `scenarios.json`. New bugs found in testing → add a `known_bug`
scenario reproducing it; fixing it flips it green. This is the second level's feed:
LLM-actor fuzzing (`fuzz.py`, personas in `fuzz_personas.json`) surfaces new phrasings
that become new fixed scenarios here.

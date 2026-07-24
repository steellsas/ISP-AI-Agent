# Conversation eval harness — Golden Dataset

Phase 3.8 step 0. The safety net **required before any reasoning change** (see
`docs/MASTANTIS_AGENTAS_SPEC.md`). Drives `AgentSession` text-to-text through scripted
CLIENT turns and hard-scores the resulting conversation **state + replies**.

The LLM only phrases; the verdict tree and step walker are deterministic given the
scripted turns, so the **state trajectory** (verdict, disposition, steps) is stable
enough to assert on — unlike free-form reply text, which is only checked for
required / forbidden substrings.

## Run
```bash
cd chatbot_core
uv run python src/agent/eval/run_eval.py                 # all scenarios
uv run python src/agent/eval/run_eval.py --only S8_billing_inform
uv run python src/agent/eval/run_eval.py --no-db          # skip DB rebuild (faster reruns)
uv run python src/agent/eval/run_eval.py --json report.json
```
Needs LLM API keys in `.env` (drives the REAL model, like `voice_demo.py`). The DB is
rebuilt from the versioned seed **before each scenario** (bind/reset stubs mutate it —
scenarios must not leak state; sub-second).

## Scenarios (`scenarios.json`)
Each scenario = `{id, phone, desc, turns[], expect{}}`. Checks (only those present run):
- `verdict_in` — the expected verdict reason appears at some point.
- `disposition` — `resolved | ticket | outage | inform | open | any`.
- `reply_any` — at least ONE of the listed substrings appears (synonyms / OR-group).
- `reply_none` — NO reply contains ANY listed substring (regression guard for a bug).

## `known_bug` scenarios
Flagged `known_bug: true` encode a fault found in voice testing. They are **expected to
fail now** (shown as `xfail`, exit code stays 0) and turn **green** once the fix lands —
so the bug can never silently return. Once a known bug is fixed and stably green, PROMOTE
it (drop the flag) so a future regression fails the suite instead of hiding as `xfail`.

There are currently no open known bugs. `S4_dead_router_bridge` was the first — the
agent blamed the router's power after the PC was plugged in — and the Phase 3.8 dr_intro
desync fix (the walker/narration were desynced; a later "ne" misrouted to escalate)
closed it. It is now a must-pass regression guard.

## Exit code
`0` = no UNEXPECTED failures (known_bug scenarios may fail). `1` = a scenario that
should pass failed — a real regression.

## Extending
Add a scenario to `scenarios.json`. New bugs found in testing → add a `known_bug`
scenario reproducing it; fixing it flips it green. This is the second level's feed:
LLM-actor fuzzing (persona-driven) surfaces new phrasings that become new fixed
scenarios here.
```

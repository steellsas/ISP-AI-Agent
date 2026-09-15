# Eval baseline — before the single-engine refactor

Recorded in M0 (plan §2, D-20). This is the behaviour M1…M7 must keep, unless a decision
in [DECISIONS.md](../DECISIONS.md) changes it.

| Field | Value |
|---|---|
| Date | 2026-09-14 |
| Git commit | `089c915` (`refactor/single-engine`: `develop` @ `f541144` + the new eval scenarios) |
| Engine | `v2` (`AGENT_ENGINE=v2`, the `run_eval.py` default) |
| Agent model | `gpt-4o-mini` (confirmed from the trace `llm` events) |
| Perception model | `PERCEPTION_MODEL=default` → same as the agent model |
| Solver model | not set → same as the agent model |
| Eval env | `SIMULATE_BRIDGE=on`, `SIMULATE_REBOOT=on`, LangSmith tracing off (set by `run_eval.py`) |
| Scenarios | 25 (18 existing + 7 added in M0) |

## Results

| Run | Checks passed | Unexpected scenario failures | Expected failures (`known_bug`) |
|---|---|---|---|
| run1 | 105 / 108 | 0 | `X_dhcp_silent` (2/5) |
| run2 | 105 / 108 | 0 | `X_dhcp_silent` (2/5) |

The two runs agree on every scenario's checks, verdicts and disposition. The only
difference is `I3_ident_no_address_recorded`: run1 called `check_outages` once, run2 did
not (LLM variance on an unidentified caller; all checks pass in both).

## Files

| File | Content |
|---|---|
| `eval_run1.json`, `eval_run2.json` | `run_eval.py --json` output + `tools_used` read from each trace; `trace` is the file name only (traces are gitignored) |
| `eval_baseline.json` | Per scenario, both runs: pass/fail per check, verdicts seen, disposition, tools used, `stable` flag |
| `voice_latency.md` | Voice latency baseline for plan §9 P-1 (speculation on): one billing call, median 2217 ms to first audio |

## Scenarios added in M0

| Id | Verdict | Disposition | Note |
|---|---|---|---|
| `D2_outage` | `active_outage` | inform | demo #2 |
| `D3_node_fault` | `node_fault_unregistered` | ticket (automatic) | demo #3 |
| `D4_switch` | `switch_unreachable` | ticket (automatic) | demo #4 (short flow) |
| `D5_link_down` | `link_down_local` | ticket | demo #5, full ladder |
| `D6_crc` | `crc_errors` | ticket | demo #6 |
| `D8_router_hung` | `router_hung` | resolved | demo #8 (demo flow) |
| `X_dhcp_silent` | `dhcp_silent` | — | `known_bug`: free-LLM path (Findings F-8); target after M4 is an unclear-fault ticket |

Demo calls #1, #7, #9 were already covered by `S8_billing_inform`, `S4_dead_router_bridge`
and `S9_client_side_phone_wifi`.

## Re-run

```bash
cd chatbot_core
uv run python src/agent/eval/run_eval.py --json report.json
```

Compare `report.json` against `eval_run1.json` per scenario (checks, `verdicts_seen`,
`disposition`). Reply text is not compared — the LLM rephrases between runs.

## Shadow turn plans (M4 step 2)

`plans/<scenario>.jsonl` — one line per turn with the `turn_plan` the pre-M4 engine
effectively executed (owner, rule id, action, say kind, hypothesis, awaited answer,
plus the raw `shadow` path/decisions/tools). Recorded on `89a5e3d` from a full eval run
(105/108, identical to the M0 baseline). M4 step 10 compares the policy chain's plans
with these. Regenerate: run the eval with `--json report.json`, then
`python docs/refactoring/baseline/extract_plans.py report.json docs/refactoring/baseline/plans`.

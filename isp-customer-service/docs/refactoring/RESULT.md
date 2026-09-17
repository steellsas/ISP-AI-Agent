# Result of the single-engine refactor

Branch `refactor/single-engine` (from `develop` @ `f541144`), M0 → M7, 2026-09-14 … 2026-09-17.
Plan and per-milestone log: [REFACTORING_PLAN.md](REFACTORING_PLAN.md) · decisions:
[DECISIONS.md](DECISIONS.md) · what is left: [ROADMAP.md](ROADMAP.md).

## What changed

Before: two engines and a `ReactAgent` sharing a legacy state, an LLM that called tools and
decided steps through a walker, a solver and directive strings, Lithuanian schema keys and
hardcoded step ids, a call record written only on some end paths.

After: **one conversation engine** — a LangGraph of four nodes over one typed state — and
**knowledge in files** the instructor fills. LLMs read the caller (perception, analyst),
propose the next step for evidence-led packs (`decide/solver.py`) and word the replies; the
engine plans every turn, the gate validates every action, and only the engine runs tools.

```
 caller audio ─► ASR ─► perceive ──► decide ──► execute ──► narrate ─► TTS ─► caller
                       understand    policy       tools       speak
                       (facts,       chain →      (gateway)   (context card
                        intent)      TurnPlan     actions      → LLM, or a
                          │          + gate        ticket      locale phrase)
                          ▼             │            │             │
                      analyst ────► typed signals    ▼             ▼
                                   GraphState (identity · intake · diagnosis · resolution ·
                                   ticket · closing · dialog · voice) — checkpointed per turn
                                                          │
                            session end (hang-up, disconnect, TTL, eval) ─► call_record finalizer
                                                          ─► contact record (outcome, review)
 knowledge/*.yaml (intents, packs, verdicts, inform, services, ticket_types, limits, policies)
 locales/lt/ (phrases, vocabulary, examples)  ─ validated at startup by agent/contract/
```

| Area | Now | Milestone |
|---|---|---|
| State | One `GraphState` (typed groups), one SqliteSaver per process; legacy engines and `AgentState` deleted | M1 |
| Dependencies | `AgentRuntime` as the graph context; every tool call through one `ToolGateway` (traced, gated) | M2 |
| Knowledge | Pydantic schema with cross-checks, English keys, step roles, `verdicts.yaml` flags, `limits.yaml`, locale layer; a broken pack stops startup; `POST /admin/knowledge/reload` | M3 |
| Decisions | `decide/`: policy chain of rule families → one `TurnPlan` per turn (owner, rule, action, say, awaiting, hypothesis), consent gate, one procedure runner; one driver — the driver switch, the shadow solver and the old `*_flow` modules deleted (the solver proposes, the gate decides) | M4 |
| Speech | `speak/`: English context card from state, byte-stable prompt per owner, reply guards; the speaking LLM has no tools; analyst emits typed signals only; speculation removed | M5 |
| Calls | Intents catalog with policies (solve / register / answer / not_ours / chat); identification gate (outage held until the address is confirmed, dictated address checked back); service profile and dependencies (IPTV over internet); 7 ticket types; repeat call appends to the open ticket; contact record for every call with a derived outcome and review flag; WS disconnect ends the call | M6 |
| Dashboard | Tabs Testavimas / Scenarijai / Archyvas; the turn path with durations, turn plan and state cards, event timeline, live conversation line; demo scenarios as data (`app/scenarios.yaml`) with ✓/✗ checks; archived calls replayed turn by turn; resizable, foldable panels | M7 |

## Verification (2026-09-17)

| Check | Result |
|---|---|
| `uv run pytest` | 1221 passed, 21 skipped (the RAG-index tests; the index is not built in the isolated worktree) |
| Eval, two full runs | **178/178** and **177/178** on 33 scenarios (M0 baseline: 105/108 on 25); the one miss is a reply-length variance in `A1` — [baseline/final/README.md](baseline/final/README.md) |
| `scripts/refactor_acceptance.py` | 9 PASS, 1 DEVIATION (`NARRATOR_QUESTIONS`, owner-kept), 1 OPEN (66 Lithuanian string literals in code → ROADMAP R-3) |
| Owner voice tests | M4 dead router; M6 calls on 2026-09-17 (outage, repeat call, billing request, disputed debt, router hung, unidentified hang-up) — failures found there fixed in `ea9680e` |

## Latency (plan §9 P-1)

Server-side time to first audio (`voice_latency.total_ms`: ASR + agent + first TTS chunk):

| Run | Calls / turns | median | p90 | mean |
|---|---|---|---|---|
| M0 baseline (speculation on) — one billing call, 2026-09-14 | 1 / 5 | 2217 ms | 3687 ms | 2263 ms |
| After M6/M7 (no speculation) — owner voice calls, 2026-09-17 | 9 / 61 | 3345 ms | 6840 ms | 3827 ms |

Breakdown of the 22 turns traced with node timings (2026-09-17 afternoon): ASR median 536 ms;
perceive median 10 ms but up to 1.7 s when the perception LLM runs; decide and execute
~0 ms; narrate median 856 ms (LLM median 913 ms on the turns that use it); **first TTS
chunk median 1418 ms, mean 2422 ms, max 8936 ms**. The first TTS chunk (edge-tts, cold
connections, F-25) is the largest and least stable part. The baseline is a single short
call, so the comparison is indicative, not conclusive. Decision on speculation and the
latency work: ROADMAP R-4.

## Known limitations

- `NARRATOR_QUESTIONS` still on (the prompt/wording pass removes it with ~25 tests).
- Lithuanian directive strings remain in `speak/context_card.py` and
  `execute/identification.py` (R-3); sensor prompts `perception*`, `ticket_reader*` stay
  Lithuanian on purpose (M3 finding: the English version broke D5).
- Open findings F-12, F-13, F-15, F-17, F-19, F-22, F-23, F-25, F-26, F-28, F-30, F-31 — each
  mapped to a ROADMAP item.
- No DB migrations: the demo DB is rebuilt from `database/schema` + seeds (owner decision);
  archived calls from before M6 do not have the contact-record columns.
- `audio_retention_until` is recorded but no job deletes the audio yet (R-12).

## Follow-ups for documentation and presentation

Programmer guide (engine, modules, file map — this file's diagram is the starting point),
instructor guide (`docs/FAULT_PACKS.md`, `docs/AGENT_ONBOARDING.md` updated for the English
schema), demo script (`docs/DEMO_SCENARIJAI.md` + the Scenarijai tab), integration guide
(ticket types → departments, MCP transport — Q-1).

# Status and road ahead

> 2026-10-15, `develop` @ `6623c53`. What the agent can do today, how far it is from a demo and
> from production, and what stands in the way. Architecture: [ARCHITECTURE.md](ARCHITECTURE.md).
> The owner sets the order; everything below is a proposal.

---

## 1. Where we are — one picture

```
 prototype ──► single engine ──► reviewed & fixed ──► v3 structure ──► DEMO ──► PILOT ──► PRODUCTION
 (2025-12)     (M0–M7, 09-17)    (waves 0–9, 10-05)   (stages 0–6,         ▲
                                                       10-15)        we are here:
                                                                     demo-capable for internet
                                                                     faults in a browser call
```

**In one sentence:** a working voice agent for **internet** faults, in Lithuanian, that identifies
the caller, reads live (demo) telemetry, diagnoses with cards, leads the caller through fixes,
informs about outages and debt, and registers tickets — running against a **simulated** CRM and
network, in the browser, with cloud LLM and ASR.

---

## 2. What it can do

| Area | Can do today | Not yet |
|---|---|---|
| **Call flow** | greeting as an AI, reason for the call, identification, diagnosis, fix, ticket, conclusion, goodbye; hang-up handled at any point | phases owned by one place (still derived, §4) |
| **Identification** | caller-ID candidate, address by parts, village search, two contracts at one address, tenant vs owner, wrong-house correction; tools locked until confirmed | — |
| **Internet faults** | 7 fault cards: hung router, CRC/cable, DHCP silent, changed router (MAC), problem behind a healthy router, local link down, dead router (+ bridge offer) | slow internet (no card → “unclear” ticket) |
| **News** | area outage, debt suspension, node fault, switch unreachable, no port data, open ticket status | — |
| **TV / phone** | IPTV that depends on broken internet: fix internet, then re-check TV | TV and phone faults of their own (no cards) |
| **Requests** | billing, disconnection, relocation, wishes → a typed ticket for the right department; repeat call → note on the open ticket | a request mentioned mid-fault is only listed, not registered (R-2) |
| **Several problems** | second problem noted and written into the ticket | not diagnosed (review stage 7a) |
| **Dialogue quality** | one question at a time, clarifies contradictions quoting the caller, re-explains when confused, honest about unknowns, no unbacked promises, barge-in | latency (§5) |
| **Records** | contact record for every call, outcome, unidentified reasons, review filter, audio retention | review queue as its own screen |
| **Knowledge** | equipment-aware wording (router → TP-Link), knowledge-base answers, startup validation, hot reload | per-model equipment files; instructor guide (§6) |
| **Languages** | Lithuanian | EN/PL/RU (architecture is locale-ready) |

## 3. Strengths — what to tell people

1. **It does not invent.** Every fact has a source — telemetry, CRM or the caller's quoted words —
   and the code checks the quote. The model never decides and never calls a tool.
2. **Telemetry over words.** Callers often describe the wrong problem; the agent trusts the network
   and asks only where the network cannot see (lights, cables, TV).
3. **A new fault is data.** Cards, modules and equipment are YAML, validated at startup, reloadable
   without a restart.
4. **Explainable.** Every turn has one plan with the rule that produced it; the dashboard shows it
   live and the archive replays it.
5. **Safe by construction.** Identity gate before account data, closed list of ticket reasons, a
   guard that drops promises nothing backs, a record for every call.
6. **Model-independent.** Providers switch by configuration; already runs on an open EU-hosted
   model (Gemma 4) with an automatic fallback.
7. **Tested.** ~1 390 tests without an LLM and 48 scored end-to-end calls.

---

## 4. What a demo still needs

“Demo” = a convincing live voice call in front of a customer, on demo data.

| # | Item | Why | Size |
|---|---|---|---|
| D1 | **Latency ≤ 1.5 s** to first audio (now ~3 s median, p90 4.5 s) | the first thing a listener notices | M — more engine-read turns, more written phrases, measure again after 6b |
| D2 | **Review stage 7a — several problems** in one call (one at a time, second after the conclusion, one ticket) | real callers do it | M |
| D3 | **TV cards** (most frequent TV faults) | “internet only” narrows the story | M — needs the owner's list of TV faults |
| D4 | **Gemma Lithuanian quality** — grammar and word errors | a native listener hears them | S–M — prompts, examples, `kalba.yaml`; fine-tuning only after eval |
| D5 | **Phases owned in one place** (v3) | the remaining live-call bugs come from scattered ownership | M |
| D6 | Demo script refresh | [demo/DEMO_PRISTATYMAS.md](demo/DEMO_PRISTATYMAS.md) dates from 2026-09-28 | S |
| D7 | Stable eval: `X_dhcp_silent`, `I2` flaky | confidence before a show | S |

## 5. What production needs

| # | Item | Today | Needed |
|---|---|---|---|
| P1 | **Real CRM and network** | all 14 tools use the `demo_db` adapter on SQLite | `mcp:` / `http:` adapters (the manifest seam exists), mapping to the customer's systems |
| P2 | **Telephony** | browser WebSocket | SIP / PBX or a telephony provider; the voice pipeline is transport-agnostic |
| P3 | **On-premise models** | LLM on Scaleway, ASR on Groq (cloud) | GPU server (min. L40S/A40 48 GB), Gemma 4 26B-A4B (+ Qwen fallback), local ASR |
| P4 | **Security** | no authentication; `/admin/*` open; CORS `*` | login, roles, TLS, secrets management |
| P5 | **Deployment** | run by hand with `uv`; only Qdrant in Docker | containers, service management, backups, migrations (DB is rebuilt, never migrated) |
| P6 | **Operations** | log/audio pruning is manual; `ops.log` | scheduled retention (GDPR), monitoring, alerts, review queue for unidentified calls |
| P7 | **Ticket routing** | 8 types with departments in YAML | connected to the customer's ticketing system |
| P8 | **Scale** | one process, one SQLite checkpointer | concurrent calls, checkpointer per deployment, load test |
| P9 | **Customer onboarding** | questionnaire draft [instructor/AGENT_ONBOARDING.md](instructor/AGENT_ONBOARDING.md) | instructor guide + process to fill cards, equipment, phrases per customer |

## 6. Challenges and risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Small-model Lithuanian** | Gemma makes grammar errors even via API; gpt-4o-mini is better but not on-prem | fixed phrases where possible, examples, word fixes; A/B on eval; fine-tune later |
| **Latency** | two serial LLM calls + ASR + TTS | engine readers first (6b), written phrases, local GPU, streaming ASR |
| **Knowledge per customer** | every ISP has its own equipment, faults, words | data-driven cards; needs a clear instructor process and tooling |
| **Real telemetry differs from demo** | the demo world is clean | design the adapters early with one real system; keep `on_failure` fallbacks |
| **Architecture still moving** | v3 phases half done; docs go stale | finish v3 before writing the instructor guide; keep ARCHITECTURE.md checked against code |
| **Single developer + AI** | knowledge in one head and in session logs | this documentation; decisions written down (DECISIONS.md, review/) |

## 7. Code and documentation hygiene

- **Structural debt** — listed in [ARCHITECTURE.md §14](ARCHITECTURE.md#14-known-technical-debt-in-the-structure)
  (two ledgers, legacy state fields, dead modules, Lithuanian strings in Python).
- **Docs out of date with code:**
  - [instructor/FAULT_PACKS.md](instructor/FAULT_PACKS.md) describes the old v1 packs
    (`faults/*.yaml`, step roles, `verdict.py decide()`) — all removed. To be replaced by the
    instructor guide.
  - [instructor/ZINIU_BAZE.md](instructor/ZINIU_BAZE.md) mentions an `ont` equipment level that
    does not exist.
  - `agent/eval/README.md` says 33 scenarios (48 now); `scenarios.json` `_doc` mentions the
    removed verdict tree.
- **Repo**: `.env.exemple` (typo; mentions MCP stdio); manual tools at package root
  (`chatbot_core/replay_stt.py`, `smoke_voice.py`); ad-hoc tests outside pytest
  (`crm_service/test_phone_lookup.py`, `scripts/test_shared.py`); `scripts/refactor_acceptance.py`
  checks rules from the old refactor.

## 8. Proposed order

```
 now ─► 7a several problems ─► TV cards ─► latency pass ─► v3 phase owners ─► DEMO
                                                                              │
       instructor guide + maintenance guide (after v3 settles) ◄──────────────┤
                                                                              ▼
           integration (P1, P7) ─► telephony (P2) ─► on-prem models (P3) ─► security/deploy/ops ─► PILOT
```

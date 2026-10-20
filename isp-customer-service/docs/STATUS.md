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

## 8. Framework and platform decisions (proposals, 2026-10-15)

The engine/LLM split matches what regulated customer-service agents converged on in 2025–26
(Rasa CALM, Parlant, Pipecat Flows, Agentforce topics): the engine decides, the model reads and
speaks. Rated against that practice:

| Practice | Here | Rating |
|---|---|---|
| Model calls no tools; code decides | yes | ★★★ |
| Facts grounded by a verified quote | yes | ★★★ rare in the market |
| Telemetry over the caller's words | yes | ★★★ |
| Knowledge as validated data | yes | ★★★ |
| Explainability (one plan per turn, traces) | yes | ★★★ |
| Tests without LLM + eval with LLM | 1 390 + 48 | ★★☆ no voice/noise eval |
| Latency | ~3 s | ★☆☆ industry < 1 s |
| Turn-taking, barge-in | own code | ★★☆ works, but reinvented |
| Production infrastructure | almost none | ☆☆☆ |

| Layer | Today | Proposal | Why |
|---|---|---|---|
| **Voice transport** | **Pipecat** over WebRTC in the dashboard (`app/pipecat_call.py`); the own WebSocket voice was deleted (A5, 2026-10-20) | **Pipecat** (cloud telephony: Twilio/Telnyx) or **LiveKit Agents** (customer's own PBX / on-prem SIP); the engine becomes one processor in the pipeline | telephony, streaming STT, turn-detection model, interruption handling, per-service TTFB metrics, maintained by others. Does **not** reduce LLM latency by itself |
| **Engine** | LangGraph (4 nodes + checkpoints) + plain Python | **keep**, do not deepen the dependency; Case and decide stay plain Python | little of LangGraph is used; a plain state machine would do the same, so switching gains nothing |
| **LangChain** | not used (litellm) | **do not add** | its strengths (chains, tool agents) are what the design deliberately avoids |
| **Model serving (on-prem)** | Scaleway API | **vLLM or SGLang** with prefix caching | many concurrent calls; the speak prompt is already cache-shaped |
| **Structured output** | JSON mode + one retry | **guided decoding** (vLLM / Outlines / XGrammar) for perception | valid JSON every time, fewer small-model errors, no retries |
| **Production observability** | JSONL traces + dashboard | **Langfuse** (self-hosted) | cost/latency per call, datasets from real calls, LLM-as-judge |
| **Prompt tuning** | by hand, logged in `review/PROMPTAI.md` | **DSPy** against the eval, for the perception prompt on a local model | small models are sensitive to wording and examples |
| Rasa CALM, Parlant, Pipecat Flows | — | **no** | same idea as the engine, weaker domain fit |

**First step:** a Pipecat spike on a separate branch — `AgentSession` inside a pipeline with Piper
TTS. Measure: Lithuanian turn detection (Smart Turn language support is unverified), latency, how
much of `app/` falls away. Ask the customer which telephony they have (add to
[instructor/AGENT_ONBOARDING.md](instructor/AGENT_ONBOARDING.md)).

## 9. Production questions not yet designed

| Area | Gap |
|---|---|
| **Scale** | the LLM limiter allows 30 calls/min per process — about 3–4 concurrent calls; one process, SQLite; no load test; no fallback path when the service itself is down (route to a human queue) |
| **Privacy (EU)** | recording consent at call start; retention only defined for unidentified calls; caller voice goes to Groq (US) — DPA/DPIA or local ASR |
| **Identity strength** | address + name is weak: the debt amount is told to anyone who knows the address; disconnection requests are registered without a stronger check |
| **Human handover** | a human is reached only through a ticket; production ISPs usually need a live (warm) transfer for urgent or angry callers |
| **Knowledge governance** | cards reload live but have no versions, review, staging or rollback; the call record does not store which knowledge version served it; no multi-tenant setup |
| **Quality loop** | no business metrics (containment, repeat call within 48 h, escalation rate, handle time, CSAT); **no feedback from technicians' ticket closure codes to measure diagnosis accuracy**; no post-call review sampling |
| **Real callers** | narrowband phone audio, noise, elderly callers, dialects; **Russian** speakers are a real share of Lithuanian ISP customers; eval is text-only (no ASR-error or synthetic voice caller) |
| **Promises** | “we will call you back” — nothing schedules or performs the callback |
| **Slow telemetry** | real probes may take 3–10 s; the `tool_slow` filler is untested against real delays |

**Safest road to production:** a **shadow run** — the agent listens to real operator calls and
diagnoses silently; its diagnosis is compared with the operator's and the technician's.

## 10. Latency plan

Working document with the measurements and the decisions: [review/DELSA.md](review/DELSA.md)
(`scripts/latency_report.py`). **Update 2026-10-15** from 3 calls of 2026-10-14 (before 6b): first
audio median 1.7 s after the cut, ~2.7 s with the endpoint wait; the LLM read (~0.7 s) and the
endpoint window (~0.9 s) are now the biggest layers, the speak TTFT is only ~0.26 s.

Older picture (2026-10-05, before Piper and 6b):

```
caller stops ─► endpoint wait ─► ASR ─► LLM read ─► engine ─► LLM speak ─► 1st sentence ─► TTS ─► audio
                 350–1 800 ms    ~550    0 / ~550    ~2 ms     TTFT ~1 150   complete        ~270
```

| # | Lever | Layer | Gain | Cost |
|---|---|---|---|---|
| L1 | **Measure** the current pipeline per layer on 3–5 live calls (incl. endpoint wait) | all | the right target | S |
| L2 | **Short first sentence** — the speaker opens with a brief reaction; the guard releases it immediately | speak | 300–600 ms | S |
| L3 | **More written phrases** instead of directives where the wording is fixed | speak | whole LLM call (~1.1 s) on those turns | S–M |
| L4 | **Status phrase before a known wait** (pre-rendered, about the real action: “tikrinu liniją”) — not a generic “mhm” (rejected 2026-08-31) | masking | perceived 1–2 s | S |
| L5 | **Endpoint tuning** — shorter waits when the answer is complete; turn-detection model (Pipecat/LiveKit) | endpoint | 200–1 000 ms | S–M |
| L6 | **Smaller speak input** (prompt ~4k tokens) and a provider with prompt caching | speak | 100–400 ms | M |
| L7 | **Start reading on a stable partial transcript** while the caller finishes | read | ~500 ms on read turns | M |
| L8 | **Streaming ASR** (local on GPU) | ASR | 300–400 ms | M, needs GPU |
| L9 | **Local GPU models** — small model for reading, larger for speaking, vLLM prefix cache | read + speak | TTFT ~1.1 s → 0.2–0.3 s | L, the main step |

Target budget: endpoint 300 + ASR 200 + read 0–300 + speak TTFT 300 + first sentence 200 +
TTS 150 ≈ **1.2–1.5 s**, perceived lower with L4.

## 11. Proposed order

```
 now ─► latency L1–L4 ─► 7a several problems ─► TV cards ─► v3 phase owners ─► DEMO
         └─► Pipecat / LiveKit spike (parallel, own branch)
                                                                              │
       instructor guide + maintenance guide (after v3 settles) ◄──────────────┤
                                                                              ▼
           integration (P1, P7) ─► telephony (P2) ─► on-prem models (P3) ─► security/deploy/ops ─► PILOT
```

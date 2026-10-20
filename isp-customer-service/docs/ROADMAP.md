# Roadmap

> Agreed with the owner 2026-10-15/16, rewritten 2026-10-20. Goal: a **demo** that is a working
> agent — ready to be shown, and run like it already were in production (monitoring, tests, a
> change process) — and a clear, tested picture of what **production** integration takes.
> Details: [STATUS.md](STATUS.md), latency [review/DELSA.md](review/DELSA.md), live review and
> agreed principles [review/PERZIURA.md](review/PERZIURA.md).

## The idea

```
DEMO = a working agent; to integrate a customer, only these change:
   ┌─ the customer's systems: CRM, telemetry, tickets   → tool adapters (manifests)
   ├─ knowledge: cards, modules, equipment, phrases     → instructor files
   ├─ settings: policies, limits, language              → YAML / config
   └─ infrastructure: local models, telephony, GPU      → configuration, not code
 + monitoring, tests and a change process, as if the agent already ran in production
```

Every production part we cannot have yet is **tried in the demo with a stand-in**, as the GPU
was: the open model runs through an EU API now, so we know what to expect on a local GPU.

| Production part | Stand-in in the demo | State |
|---|---|---|
| Local models on a GPU | Gemma 4 26B through Scaleway (EU API) | ✅ tried |
| Customer CRM and telemetry | our demo CRM reached **as an external system** through an `http:` adapter | planned (stage 3) |
| Telephony | Pipecat with a test telephony account or a local SIP softphone — real 8 kHz phone audio | planned (stage 3) |
| Several calls at once | 3–5 eval calls in parallel (LLM limiter, Piper pool, SQLite) | planned (stage 3) |
| A new customer's knowledge | a “profile” folder: cards, equipment, phrases, tools | planned (stage 3) |

## Targets

| | Demo | Production |
|---|---|---|
| Caller stops talking → agent's first audio | **~1.5 s** (now ~1.4 s median with Pipecat) | **~0.6 s** |
| Models | Scaleway Gemma 4 26B, Groq ASR, Piper TTS (worker pool) | local on GPU (vLLM), local streaming ASR, Piper |
| Voice | Pipecat in the browser (WebRTC) | the same Pipecat bot over telephony |

## Stage 1 — Voice finished (Pipecat the only voice)

Done: WebRTC in the dashboard (`app/pipecat_call.py`), Smart Turn (endpoint 900 → 200 ms),
Piper in worker processes, PCM cache for scripted lines, “what the caller heard” after a
barge-in (D1). **2026-10-20: V1–V6 done** (`56b1de5`, `23271ba`, `902fda1`, `78a12fa`,
`0aba9d0`, `eb58bb6`) — waiting for live calls, then A5. The steps:

| # | Step | Why | Done when |
|---|---|---|---|
| V1 | **Record the call audio** (caller and agent per turn into `logs/sessions/<id>/`) | the archive and every review need to hear the call | archive plays a Pipecat call |
| V2 | **I-3 “finish the phrase, then decide”** + short phrases never lost (G17-1): the agent finishes its current phrase (≤ ~1.5 s), holds, and on the caller's words either goes on from where it stopped (backchannel, echo, nothing heard) or yields (an answer, a question, „palaukit") | the “≥ 3 words” rule is interim and drops real answers | „Gerai, ačiū" over the question is read as an answer; „aha" does not cut |
| V3 | **I-1 required information** instead of the unbreakable greeting | agreed principle (PERZIURA §6) | an interrupted greeting is still heard later (the AI disclosure) |
| V4 | **Check-in when the caller is silent** („Ar jūs dar ten?") | the old voice had it | silence → one check-in, then the agreed ending |
| V5 | **Dashboard parts tied to the old voice**: partial transcript, voice meter, time-to-first-audio in the brain panel; `latency_report` reads Pipecat timings (G19) | visible in the demo | brain panel and report show Pipecat calls fully |
| V6 | Pipecat the default; Smart Turn and interruption settings on the config page | convenience | — |
| A5 | **Delete the old voice path** (`audio_front.py`, WS audio in `main.py`, parts of `voice_pipeline`) | one voice path to maintain, the one production uses | after V1–V6 and a few live calls |

Deferred until after the live trials (2026-10-20): **background noise, music and other voices**
(noise filter, loudness, the caller's voice print — PERZIURA §6 I-4, I-5) — not now, so that
background sound is never taken for the caller.

## Stage 2 — Engine quality for the demo

| # | Step | Why |
|---|---|---|
| E1 | I-1 required information, I-2 partial answers (PERZIURA §6) | nothing the agent must say is lost; ask for what is missing |
| E2 | Live-call findings: G2–G4 (address and name readers), G7 (clarify an unclear „ne"), G8 (hours), G11 (non-Latin letters from Gemma), G12–G13, G15 (paid-but-suspended is a dispute), G18 (double reply), G6 (stale „Malonu") | what a listener notices |
| E3 | Review stage 7a — several problems in one call (one at a time, one ticket) | real callers do it |
| E4 | TV cards, if the demo shows TV | „internet only" narrows the story |
| E5 | v3: phases owned in one place | the remaining live-call bugs come from scattered ownership |

## Stage 3 — Run it like production

| # | Step | What | Have now |
|---|---|---|---|
| P1 | **Debug view** | per call and turn: why the agent said it (rule, readers, LLM input), errors, timings | traces, brain panel, archive, `ops.log` |
| P2 | **Monitoring** | a daily summary: outcomes, solved without a human, what no reader understood, promises the guard stopped, interruptions, latency, errors; a review queue | parts (`reader_silent`, `latency_report`) |
| P3 | **Test loop** | a live call with a fault → an eval scenario (repeatable) → fix → tests → eval → live call | eval 48 scenarios, 1 793 tests; moving a call into eval is manual |
| P4 | **Change process** | instructor edits a card → validation → tests → the related eval → reload; versions and rollback | validation and reload; no versions |
| P5 | **Learning loop** | not understood → vocabulary; „unclear fault" tickets → candidate cards; in production, technicians' closure codes → card accuracy | `reader_silent` |
| P6 | **Integration seam** | `http:` adapter to our demo CRM as an external system | manifests accept `http:`/`mcp:`, no adapter yet |
| P7 | **Load test** | 3–5 calls at once | none |
| P8 | **Customer profile** | one folder per customer: knowledge, tools, settings | knowledge files exist, not grouped as a profile |
| P9 | **Telephony trial** | Pipecat over a test phone line | none |

## Stage 4 — Presentation

| # | Document | For |
|---|---|---|
| D1 | How the agent works (Lithuanian) — from STATUS §2–3 and ARCHITECTURE | the customer |
| D2 | Instructor guide: cards (symptoms), how a fault is classified, modules, equipment, policies, adding a new fault, tests and eval for it | whoever teaches the agent |
| D3 | Integration and production guide: what changes for a customer (adapters, profile, models, telephony, security, operations) and what stays | integrators |
| D4 | What is thought through and what is still open (from STATUS, PERZIURA, this roadmap) | the owner, the customer |

## Stage 5 — Demo rehearsal

Scenarios, live calls, a fallback plan ([demo/](demo/)).

## Production track (after a GPU server and a customer)

| # | Step |
|---|---|
| B1 | GPU server (min. L40S / A40 48 GB); vLLM or SGLang with prefix caching; guided decoding for the read |
| B2 | Local models: Gemma 4 26B-A4B (Qwen3.6 fallback); small model for reading, larger for speaking |
| B3 | Local streaming ASR; start reading on stable partials |
| B4 | Telephony: Pipecat (cloud telephony) or LiveKit (own PBX / SIP) — the customer's answer decides |
| B5 | Real CRM / network adapters behind the tool manifests |
| B6 | Security (login, TLS), deployment (containers), operations (retention, monitoring, Langfuse) |
| B7 | Scale (LLM limiter, concurrency), privacy (consent, DPA, retention), identity strength |
| B8 | Shadow run beside human operators → pilot |

## Decisions behind this roadmap

| Date | Decision |
|---|---|
| 2026-10-15 | Keep LangGraph and the plain-Python engine; no LangChain |
| 2026-10-16 | Latency metric = caller's silence → agent's first audio; demo ~1.5 s, production ~0.6 s |
| 2026-10-16 | Until the GPU: only cheap latency levers; model/ASR/serving tuning waits |
| 2026-10-16 | Smart Turn alone does not stop cut-offs (callers finish a sentence and go on) — measured offline |
| 2026-10-19 | Pipecat in the dashboard, in the server process; Piper in worker processes (GIL) |
| 2026-10-19 | Interruptions anywhere, required information never lost (PERZIURA §6, I-1…I-5) |
| 2026-10-20 | The demo runs like production: monitoring, test loop, change process; production parts tried with stand-ins |
| 2026-10-20 | Finish the voice first (stage 1), then the debug view and monitoring (stage 3 P1–P2) |

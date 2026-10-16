# Roadmap

> Agreed with the owner 2026-10-15/16. Two tracks: **demo** (now — the engine must work well,
> ~1.5 s response) and **production** (after a GPU server — local models, ~0.6 s). Details and
> measurements: [STATUS.md](STATUS.md), latency working notes [review/DELSA.md](review/DELSA.md).

## Targets

| | Demo | Production |
|---|---|---|
| Gap: caller stops talking → agent's first audio | **~1.5 s** | **~0.6 s** |
| Models | Scaleway Gemma 4 26B (EU API), Groq ASR, Piper TTS | local on GPU (vLLM), local streaming ASR, Piper |
| Telephony | browser | SIP / provider (Pipecat or LiveKit, decided by the customer's telephony) |
| Rule | only cheap latency work that stays useful in production | model/ASR/serving tuning |

## Track A — Demo (now)

### A1. Faster turn-taking (latency)

| # | Step | What | Done when |
|---|---|---|---|
| A1.0 | **Measure** | owner's 3–5 live calls → `scripts/latency_report.py --days 1 --turns` | per-layer picture after 6b in DELSA.md |
| A1.1 | **Smart Turn offline test** | run Pipecat's Smart Turn v3 model (audio, BSD-2, 8 MB, CPU) on the recorded caller turns `logs/sessions/*/turn_NN_user.wav`, without the Pipecat framework | accuracy on Lithuanian known: complete vs cut-mid-thought, inference time |
| A1.2 | **Endpoint trace** | `app/audio_front.py` records the real wait (speech end → cut, mode) | `latency_report.py` shows measured endpoint, not an estimate |
| A1.3 | **Smart Turn in the endpoint** | if A1.1 is good: Smart Turn as a second signal beside `agent/endpoint.py`; both agree → cut after ~200–300 ms instead of 900 | live calls: endpoint median ≤ 400 ms, no rise in cut-offs |
| A1.4 | **Fine-tune for Lithuanian** | only if A1.1 is mediocre: open `train.py` + our recorded turns, labelled complete / incomplete | accuracy close to supported languages |
| A1.5 | **Short first sentence** (L2) | the speaker opens with a short reaction (≤ ~40 chars) | first-sentence TTS ≤ 300 ms p90 |
| A1.6 | **More turns without the LLM read** (R1) | extend the engine readers where traces show the read LLM still runs on simple answers | read LLM on ≤ 30 % of turns |
| A1.7 | **Pre-answer closed questions** (idea, to discuss) | while the agent asks a closed question, the engine plans every expected answer and Piper pre-renders the phrases | “taip / ne” answered within endpoint + ASR |

Expected: first audio ~1.0–1.3 s after the cut, **~1.5 s** from the caller's silence.

### A2. Engine quality (the review continues)

| # | Step |
|---|---|
| A2.1 | Review stage 7a — several problems in one call (one at a time, the second after the conclusion, one ticket) |
| A2.2 | TV fault cards (owner lists the most frequent TV faults) |
| A2.3 | v3 — phases owned in one place |
| A2.4 | Stable eval (`X_dhcp_silent`, `I2`) |
| A2.5 | Demo script refresh ([demo/](demo/)) |

### A3. Documentation

Presentation (LT) from STATUS §2–3 · instructor guide (after v3) · maintenance guide.

## Track B — Production (after the GPU server)

| # | Step |
|---|---|
| B1 | GPU server (min. L40S / A40 48 GB); vLLM or SGLang with prefix caching; guided decoding for the read |
| B2 | Local models: Gemma 4 26B-A4B (Qwen3.6 fallback); small model for reading, larger for speaking |
| B3 | Local streaming ASR; start reading on stable partials (L7) |
| B4 | Telephony: Pipecat (cloud telephony) or LiveKit (own PBX / SIP) — the customer's answer decides |
| B5 | Real CRM / network adapters (`mcp:` / `http:` behind the tool manifests) |
| B6 | Security (login, TLS), deployment (containers), operations (retention, monitoring, Langfuse) |
| B7 | Scale (LLM limiter, concurrency, load test), privacy (consent, DPA, retention), identity strength |
| B8 | Shadow run beside human operators → pilot |

## Decisions behind this roadmap

| Date | Decision |
|---|---|
| 2026-10-15 | Keep LangGraph and plain-Python engine; no LangChain |
| 2026-10-16 | Latency metric = caller's silence → agent's first audio; demo ~1.5 s, production ~0.6 s |
| 2026-10-16 | Until the GPU: only cheap latency levers; model/ASR/serving tuning waits |
| 2026-10-16 | Turn detection for the demo: **Pipecat Smart Turn model only, without the framework**; LiveKit's detector rejected (no LT, cloud-hosted full model, licence). Framework choice stays a telephony question (B4) |

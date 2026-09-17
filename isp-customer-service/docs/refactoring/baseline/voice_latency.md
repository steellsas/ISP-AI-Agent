# Voice latency baseline (plan §9 P-1)

Recorded in M0 on the pre-refactor code (speculation **on**), to compare against the same
call after M7 (speculation removed).

## What is measured

The session trace does **not** contain `voice_turn_done.ttfa_ms` — that event goes only to
the browser over the WebSocket (`app/voice.py`). The traced equivalent is the
`voice_latency` event from `agent/voice_pipeline.py` `stream_turn`:

| Field | Meaning |
|---|---|
| `asr_ms` | speech-to-text of the finished utterance |
| `tts_ms` | ASR done → first reply audio chunk ready (agent + first-sentence TTS; they overlap when streaming) |
| `total_ms` | `asr_ms + tts_ms` = server-side time to first audio |

Not included: the VAD end-of-speech wait before the utterance is closed, network and
browser playback start. Both runs are measured the same way, so the comparison holds.

## Call 1 — demo #1 (billing), 2026-09-14 16:25

Session `20260914-162524-833002-0001`, phone `***0101`, `gpt-4o-mini`, edge-tts, 3-turn
call by voice (5 measured turns; one noise segment dropped by ASR).

| # | Caller (ASR) | Engine | asr_ms | tts_ms (to first audio) | total_ms |
|---|---|---|---|---|---|
| 1 | „Labai dienaliniu tikiuose neturiu." | scripted | 658 | 480 | 1138 |
| 2 | „Nevyk į internetus." | LLM (1253 ms) | 577 | 1639 | 2217 |
| 3 | „Taip." (address + diagnose) | scripted + tools | 592 | 758 | 1349 |
| 4 | „Paulius, mano vardas." (verdict inform) | scripted, `bg_diagnosis_applied` | 565 | 2361 | 2926 |
| 5 | „Ne, ačiū, visą gerą." | LLM (978 ms) | 681 | 3007 | 3687 |

| Metric | asr_ms | tts_ms | total_ms |
|---|---|---|---|
| median | 592 | 1639 | 2217 |
| p90 (nearest rank, n=5) | 681 | 3007 | 3687 |
| mean | 615 | 1649 | 2263 |

## Limits of this baseline

- One call, one scenario (billing inform). It has no procedure-step turns, so the
  speculation branch cache (pre-rendered replies to awaited step answers) was never hit —
  only `bg_diagnosis_applied`. The part of latency speculation targets is not in it.
- For P-1 repeat **this same call** after M7 and compare per turn.

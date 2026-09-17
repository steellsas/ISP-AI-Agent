# Roadmap after the single-engine refactor

What is left to fix or build once `refactor/single-engine` is merged into `develop`. Every
item points to its evidence (a finding in [REFACTORING_PLAN.md](REFACTORING_PLAN.md) §6, a
live call, an owner note). Order is a proposal — the owner sets it.

Status on 2026-09-17: M0–M7 done; eval and pytest green; owner voice tests of the M6 calls
done and their failures fixed (`ea9680e`).

## Priority 1 — behaviour the caller notices

| # | What | Evidence | Where to start |
|---|---|---|---|
| R-1 | A call that drops while the end-of-call „Ar užregistruoti gedimą?“ is unanswered still registers the fault ticket at session end. Decide: a ticket, or only a contact record for review. | F-31 (eval I2) | `call_record/finalizer.py` hang-up net, `decide/rules/head.end_confirm_answer` |
| R-2 | A request mentioned in the middle of a fault call („o dar dėl sąskaitos“) is dropped. It should become a second ticket (its own type) at the closing. | F-28 | `perceive/slots.py` secondary problems, `decide/rules/closing.py`, `decide/rules/requests.py` |
| R-3 | 66 Lithuanian string literals are still in Python code — mostly the context card's directive sentences (`speak/context_card.py` 38, `execute/identification.py` 13). They belong in `locales/lt/` (M3 goal). `scripts/refactor_acceptance.py` reports them as OPEN. | acceptance check M3 | `speak/context_card.py`, `execute/identification.py` |
| R-4 | Voice latency is higher than the M0 baseline: server time to first audio median **3.3 s** (p90 6.8 s) on 9 calls / 61 turns on 2026-09-17, vs **2.2 s** (p90 3.7 s) on the single M0 billing call. The first TTS chunk dominates (median 1.4 s, max 8.9 s); the perception pass adds up to 1.7 s on some turns. Decide P-1 (speculation) with these numbers; warm the TTS connection before the greeting (F-25); a faster perception model or partial-ASR start. | [RESULT.md](RESULT.md) §Latency, F-24, F-25 | `adapters/tts/edge_tts`, `app/voice.py`, `perceive/understand.py` |
| R-5 | Prompts and wording pass: remove `NARRATOR_QUESTIONS` (and rewrite the ~25 tests that assert scripted sentences), polish the wording of F-26, use the stale „Malonu, {vardas}!“ one-shot on the scripted turn (F-30), vocative names („Malonu, Anatolijau“), no invented causes in the closing („jis nebuvo prijungtas“). | F-26, F-30, live calls 2026-09-17 | `prompts/speak/`, `speak/context_card.py`, `locales/lt/` |

## Priority 2 — the dialogue the owner described

| # | What | Evidence | Where to start |
|---|---|---|---|
| R-6 | The analyst's clarify loop: a contradiction or an unexpected answer reopens the hypothesis; clarify only when the step's result is missing, not on every step. | `OWNER_NOTES_dialogue.md` §1–2 | `analyst/`, `decide/hypothesis.py` |
| R-7 | „Perkroviau, internetas atsirado“ before or at the reboot step: the walker holds or asks for the lights again, and the case closes only through the hang-up net; a „Mirksi… veikia“ at the reboot check triggers the farewell confirm. | F-12, F-15, F-19, F-17 (stale perception anchor); final eval run2 `A1`: „Gerai, perkroviau — atsirado“ got the callback goodbye | `decide/procedure.py` restored detection, `perceive/understand.py` anchor |
| R-8 | Verify F-13 (a farewell at the contact question): the 2026-09-17 call re-asked and registered only after a yes — confirm with an eval scenario, then close it. | F-13 | eval `scenarios.json`, `decide/rules/ticket.py` |
| R-9 | A garbled opening („nevyk internetas visose renginiuose“) lands later through the normal ingest, but the check-back only covers facts from the activation seed, so the agent re-asks. | F-22 | `execute/diagnosis._seed_evidence_from_call` |
| R-10 | Lead the physical work in small steps with telemetry between them, say why and what happens next; the `router_hung` pack has no LIGHTS evidence (which light, where, what blinking means). | `OWNER_NOTES_dialogue.md` §3–4, F-23 | `knowledge/faults/internet_pakibes_routeris.yaml` |
| R-11 | `answer` intents cover only the ticket status; outage ETA and debt questions still go through the inform verdicts. Decide whether they become `answer` intents. | M6 deviation | `knowledge/intents.yaml`, `decide/rules/requests.py` |

## Priority 3 — product and operations

| # | What | Evidence | Where to start |
|---|---|---|---|
| R-12 | `audio_retention_until` is written for unidentified calls, but nothing deletes the audio after that date — a cleanup job is needed (privacy, D-14). | M6 step 5 | `app/archive.py`, a scheduled task |
| R-13 | Admin login before any public hosting: the config page, DB reset and archive are open. | dashboard note | `app/main.py` |
| R-14 | Dashboard: a detailed decision graph (which rule, which step, branches) on top of the four-node strip; run a scenario's lines automatically as a text call. | owner review 2026-09-17 | `app/static/js/brain.js`, `app/scenarios.yaml` |
| R-15 | Remove the dead LLM tool-round path: `executor_flow.execute_tool_calls` has no caller in `src` (tests only) since the speaker has no tools (M5). | M5 deviation | `agent/executor_flow.py`, `tests/test_procedure.py`, `tests/engine_fakes.py` |
| R-16 | The LLM rate limiter counts 100 calls per process and never resets in the API. | F-2 (integration) | `services/llm` |
| R-18 | Comment hygiene: ~96 "walker" mentions in `.py` comments (the queue owner key `walker` is still live), old Lithuanian key names in fault-pack comments (`kada`, `klausimas`, `patvirtinta_kai`, …), the unused phrase `identification.anamnesis_question`, and two example files with no reader (`locales/lt/examples/prompt_directives.md`, `prompt_analyst.md`; `problems.md` is read through `intents.yaml` `examples_key`). | comment review 2026-09-17 | `chatbot_core/src/agent/`, `knowledge/faults/`, `locales/lt/examples/` |
| R-19 | `POST /admin/knowledge/reload` may refuse a pack that uses a phrase key just added to `phrases.yaml` (validation reads the locale through the startup cache, cleared only after a successful reload) until the server restarts — found by reading the code, verify first. | docs review 2026-09-17 | `agent/contract/loader.py`, `contract/locale.py` |
| R-20 | Knowledge contract gaps: `policies.yaml` `forbidden_topics` is in the schema but nothing reads it (D-17); a verdict missing from `verdicts.yaml` is caught only by a test, not at startup; stale comments in `faults._expanded_steps`, `contract/schema.py` (`resolution.DETECTORS`), the `verdicts.yaml` header (`inform` also allows `service`, `ticket`). | docs review 2026-09-17 | `agent/contract/`, `knowledge/` |
| R-21 | Debt wording conflict: `faq.debt_amount` says „Tikslios sumos aš nematau…“, but the debt news (`inform.billing_suspended`) states the amount — a „kiek skolingas?“ side question can contradict the agent's own words. | test docs review 2026-09-17 | `locales/lt/phrases.yaml` `faq.debt_amount`, `knowledge/faq.yaml` |
| R-17 | Integration with a real CRM and network: ticket types map to departments (`knowledge/ticket_types.yaml`), MCP stays the likely transport (Q-1). | D-11, Q-1 | `agent/tooling/`, `crm_service/` |

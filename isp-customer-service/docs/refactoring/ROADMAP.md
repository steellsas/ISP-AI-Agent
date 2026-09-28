# Roadmap after the single-engine refactor

What is left to fix or build once `refactor/single-engine` is merged into `develop`. Every
item points to its evidence (a finding in [REFACTORING_PLAN.md](REFACTORING_PLAN.md) §6, a
live call, an owner note). Order is a proposal — the owner sets it.

Status on 2026-09-17: M0–M7 done; eval and pytest green; owner voice tests of the M6 calls
done and their failures fixed (`ea9680e`).

**Status on 2026-09-28 (wave 5).** These rows carried no marks at all, because waves 1–4b
tracked their own `F-` findings and never met the `R-` numbers. Each row was checked against
the code, not guessed; five of them were the explicit subject of wave 5 step 5-4
([FIX_PLAN.md](../review/FIX_PLAN.md)). What the column says:

| | |
|---|---|
| ✅ | done — where it happened |
| 🔁 | solved differently; the row's own plan is obsolete |
| ◐ | partly done, the rest named |
| ⏳ | open, verified open |

Ten done, two solved differently, three partly, six open. The open ones are mostly
production and integration work, not behaviour the caller notices.

## Priority 1 — behaviour the caller notices

| # | Būsena | What | Evidence | Where to start |
|---|---|---|---|---|
| R-1 | ✅ | A call that drops while the end-of-call „Ar užregistruoti gedimą?“ is unanswered still registers the fault ticket at session end. Decide: a ticket, or only a contact record for review. — **`call_record/finalizer.py` has the hang-up net with its own decisions (`hangup_net` → `callback_close` / `skip_solved`); a hang-up on the homework step closes as a callback instead of a ticket (F3, live 2026-09-09).** | F-31 (eval I2) | `call_record/finalizer.py` hang-up net, `decide/rules/head.end_confirm_answer` |
| R-2 | ⏳ | A request mentioned in the middle of a fault call („o dar dėl sąskaitos“) is dropped. It should become a second ticket (its own type) at the closing. — **verified open 2026-09-28: `intake.py::_is_secondary` records only a `solve` fault, and the closing asks about it but creates no ticket; a `register` intent (billing, disconnection) is still dropped.** | F-28 | `perceive/slots.py` secondary problems, `decide/rules/closing.py`, `decide/rules/requests.py` |
| R-3 | ⏳ | 66 Lithuanian string literals are still in Python code — mostly the context card's directive sentences (`speak/context_card.py` 38, `execute/identification.py` 13). They belong in `locales/lt/` (M3 goal). — **2026-09-28 the count GREW: 46 in `context_card.py`, 14 in `execute/identification.py`, and `scripts/refactor_acceptance.py` no longer exists, so nothing reports it.** | acceptance check M3 | `speak/context_card.py`, `execute/identification.py` |
| R-4 | ⏳ | Voice latency is higher than the M0 baseline: server time to first audio median **3.3 s** (p90 6.8 s) on 9 calls / 61 turns on 2026-09-17, vs **2.2 s** (p90 3.7 s) on the single M0 billing call. The first TTS chunk dominates (median 1.4 s, max 8.9 s); the perception pass adds up to 1.7 s on some turns. Decide P-1 (speculation) with these numbers; warm the TTS connection before the greeting (F-25); a faster perception model or partial-ASR start. — **not measured again since; the knowledge layer added a search of p95 45 ms, which is inside the budget but not free.** | [RESULT.md](RESULT.md) §Latency, F-24, F-25 | `adapters/tts/edge_tts`, `app/voice.py`, `perceive/understand.py` |
| R-5 | ◐ | Prompts and wording pass: remove `NARRATOR_QUESTIONS` (and rewrite the ~25 tests that assert scripted sentences), polish the wording of F-26, use the stale „Malonu, {vardas}!“ one-shot on the scripted turn (F-30), vocative names („Malonu, Anatolijau“), no invented causes in the closing („jis nebuvo prijungtas“). — **the vocative and the spoken address landed 2026-09-23; the `NARRATOR_QUESTIONS` flag is still read in three places (`decide/rules/identification.py` ×2, `decide/rules/ticket.py`).** | F-26, F-30, live calls 2026-09-17 | `prompts/speak/`, `speak/context_card.py`, `locales/lt/` |

## Priority 2 — the dialogue the owner described

| # | Būsena | What | Evidence | Where to start |
|---|---|---|---|---|
| R-6 | ✅ | The analyst's clarify loop: a contradiction or an unexpected answer reopens the hypothesis; clarify only when the step's result is missing, not on every step. — **`decide/hypothesis.py` holds one doubt at a time (`doubt` → `due` → `ask` → `answered`), the analyst raises `contradiction` / `already_answered` / `secondary_problem`, and „ask only where the answer changes something“ is wave 4a's third cut (`17cbeab`).** | `OWNER_NOTES_dialogue.md` §1–2 | `analyst/`, `decide/hypothesis.py` |
| R-7 | 🔁 | „Perkroviau, internetas atsirado“ before or at the reboot step: the walker holds or asks for the lights again, and the case closes only through the hang-up net. — **the walker is gone; a card's `done_when` plus the telemetry re-read decide this now (wave 3/4a), and the live scenarios C1/D in [BALSO_TESTAVIMAS.md](../BALSO_TESTAVIMAS.md) check exactly this turn.** | F-12, F-15, F-19, F-17; final eval run2 `A1` | `decide/procedure.py` restored detection, `perceive/understand.py` anchor |
| R-8 | ✅ | Verify F-13 (a farewell at the contact question): the 2026-09-17 call re-asked and registered only after a yes — confirm with an eval scenario, then close it. — **`R1b_billing_request_farewell_midway` is that call, in the eval.** | F-13 | eval `scenarios.json`, `decide/rules/ticket.py` |
| R-9 | ⏳ | A garbled opening („nevyk internetas visose renginiuose“) lands later through the normal ingest, but the check-back only covers facts from the activation seed, so the agent re-asks. — **`execute/diagnosis.py::_seed_evidence_from_call` is unchanged.** | F-22 | `execute/diagnosis._seed_evidence_from_call` |
| R-10 | ✅ | Lead the physical work in small steps with telemetry between them, say why and what happens next; the `router_hung` pack has no LIGHTS evidence (which light, where, what blinking means). — **wave 4b: a light has a colour, and the lights live in the equipment documents the card can reach (`knowledge/v2/cards/router_hung.yaml`).** | `OWNER_NOTES_dialogue.md` §3–4, F-23 | `knowledge/faults/internet_pakibes_routeris.yaml` |
| R-11 | ✅ | `answer` intents cover only the ticket status; outage ETA and debt questions still go through the inform verdicts. Decide whether they become `answer` intents. — **decided by the informing cards (wave 4a): the news is a card, and a repeat question is answered from the same facts (`answer_from_news`).** | M6 deviation | `knowledge/intents.yaml`, `decide/rules/requests.py` |

## Priority 3 — product and operations

| # | Būsena | What | Evidence | Where to start |
|---|---|---|---|---|
| R-12 | ✅ | `audio_retention_until` is written for unidentified calls, but nothing deletes the audio after that date — a cleanup job is needed (privacy, D-14). — **wave 5: `scripts/prune_logs.py` deletes audio past its retention date (and old traces), dry run by default.** | M6 step 5 | `app/archive.py`, a scheduled task |
| R-13 | ⏳ | Admin login before any public hosting: the config page, DB reset and archive are open. — **still open; `app/main.py` says so itself in a comment above `/admin/config`.** | dashboard note | `app/main.py` |
| R-14 | ◐ | Dashboard: a detailed decision graph (which rule, which step, branches) on top of the four-node strip; run a scenario's lines automatically as a text call. — **`static/js/brain.js` shows the rule and the step; the automatic scenario run does not exist.** | owner review 2026-09-17 | `app/static/js/brain.js`, `app/scenarios.yaml` |
| R-15 | ✅ | Remove the dead LLM tool-round path: `executor_flow.execute_tool_calls` has no caller in `src` (tests only) since the speaker has no tools (M5). — **gone; `executor_flow.py` keeps only the ticket registration and the demo simulations, which are called.** | M5 deviation | `agent/executor_flow.py`, `tests/test_procedure.py`, `tests/engine_fakes.py` |
| R-16 | ✅ | The LLM rate limiter counts 100 calls per process and never resets in the API. — **wave 5: the budget is per conversation (a ContextVar set around every turn), the minute window stays per process, and the finalizer forgets a finished call. Six tests.** | F-2 (integration) | `services/llm` |
| R-18 | ◐ | Comment hygiene: ~96 "walker" mentions in `.py` comments (the queue owner key `walker` is still live), old Lithuanian key names in fault-pack comments, the unused phrase `identification.anamnesis_question`, and two example files with no reader. — **53 „walker“ mentions left of ~96; the rest of the list is unchecked.** | comment review 2026-09-17 | `chatbot_core/src/agent/`, `knowledge/faults/`, `locales/lt/examples/` |
| R-19 | ✅ | `POST /admin/knowledge/reload` may refuse a pack that uses a phrase key just added to `phrases.yaml` (validation reads the locale through the startup cache, cleared only after a successful reload) until the server restarts — found by reading the code, verify first. — **verified 2026-09-28, and worse: validation read the whole knowledge from the startup cache, so an edited card was not seen at all and the endpoint answered `reloaded` after validating the OLD files. Fixed by `loader.revalidate()` — caches first, validation second.** | docs review 2026-09-17 | `agent/contract/loader.py`, `contract/locale.py` |
| R-20 | 🔁 | Knowledge contract gaps: `policies.yaml` `forbidden_topics` is in the schema but nothing reads it (D-17); a verdict missing from `verdicts.yaml` is caught only by a test, not at startup; stale comments in `faults._expanded_steps`, `contract/schema.py`, the `verdicts.yaml` header. — **what `forbidden_topics` was meant to do is done by the boundary gate (`agent/knowledge_need.py`, RAG E3b), which decides from the documents' own keywords and a tunable vocabulary. The dead field and the smaller comment gaps remain.** | docs review 2026-09-17 | `agent/contract/`, `knowledge/` |
| R-21 | ✅ | Debt wording conflict: `faq.debt_amount` says „Tikslios sumos aš nematau…“, but the debt news (`inform.billing_suspended`) states the amount — a „kiek skolingas?“ side question can contradict the agent's own words. — **closed in wave 4a (2026-09-23, after the live call): `faq.yaml: answer_from_news: billing_suspended` answers from the same facts whenever the debt verdict exists; the phrase is only used when there are no debt facts, where it is true.** | test docs review 2026-09-17 | `locales/lt/phrases.yaml` `faq.debt_amount`, `knowledge/faq.yaml` |
| R-17 | ⏳ | Integration with a real CRM and network: ticket types map to departments (`knowledge/ticket_types.yaml`), MCP stays the likely transport (Q-1). | D-11, Q-1 | `agent/tooling/`, `crm_service/` |

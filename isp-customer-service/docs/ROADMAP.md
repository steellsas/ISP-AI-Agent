# 🛠️ ISP-AI-Agent — Modernization & Voice Roadmap

> Reference document for the step-by-step rework of the ISP after-hours support bot
> into a modular, provider-agnostic **voice-to-voice** consulting agent.
>
> **Golden rule:** every layer sits behind a stable interface, so any later decision
> (cloud ↔ local, which STT/TTS/LLM, web ↔ telephony, which frontend) can be swapped
> **without redoing earlier steps**.

---

## 1. Design tenets

- **Ports & Adapters (hexagonal).** Anything that can change (LLM, ASR, TTS, Transport, DB)
  lives behind a `Protocol` interface; concrete implementations are pluggable adapters.
- **Framework-free core.** Dialog logic + RAG + tools never depend on Streamlit / FastRTC / Ollama.
- **`main` is the live demo.** The Railway deployment must never break — all work happens on branches.
- **Safety net first.** A scenario-based regression/eval harness is established *before* refactoring,
  so "how well it consults" is measurable and protected.
- **Small, traceable steps.** Each phase has an explicit *Definition of Done*.

---

## 2. Git & branching strategy

```
main                      ← stable, == Railway demo. PR-only.
develop                   ← daily integration branch
  ├─ chore/foundation       (Phase 0)
  ├─ fix/rag-retrieval      (Phase 1)
  ├─ refactor/tool-calling  (Phase 2)
  └─ feat/voice-fastrtc     (Phase 3)
```

- Each phase = a feature branch off `develop`; finished → PR into `develop`; when stable → `develop` → `main`.
- Small commits with conventional prefixes: `fix:`, `refactor:`, `feat:`, `chore:`, `test:`, `docs:`.
- Tag `v1-demo` marks the pre-rework restore point.

---

## 3. Tooling & quality gates (part of the foundation)

- **ruff** (lint + format), **mypy** (types), **pytest + coverage**, **pre-commit** hooks.
- **GitHub Actions CI:** lint → typecheck → tests on every PR.
- **pydantic-settings** as the single config source; PII redaction in logs.
- Repo hygiene: remove `.mypy_cache` from VCS, fix `.gitignore`, rename `.env.exemple` → `.env.example`.

---

## 4. Target structure

```
chatbot_core/src/
  ports/          # ASRProvider, TTSProvider, LLMProvider, Transport, ToolProvider (Protocol)
  core/           # AgentSession, dialog logic, RAG orchestration (framework-free)
  adapters/
    llm/          # OpenAI / Claude / Ollama (via LiteLLM)
    asr/          # faster-whisper, whisper-api
    tts/          # gTTS, Azure, Piper
    transport/    # fastrtc_ws, twilio
  rag/            # retriever, vector_store, processor (cleaned up)
  services/       # MCP clients (CRM, Network)
  app/            # FastAPI entrypoint, mount(stream)
  debug_ui/       # Streamlit — monitoring only
```

---

## Phase 0 — Foundation hardening · `chore/foundation`

**Goal:** clean, tested, secure base. No new features.

- [x] Tooling + CI + pre-commit (see §3) — *merged via PR #1*
- [x] **Regression safety net:** self-contained scenario/tool suite (rebuilds the
      SQLite DB from versioned SQL; RAG tests skip offline); `pytest` enabled in CI
      — *merged via PR #2; 66 passed / 22 skipped, hermetic*
- [x] Ports skeleton (`ports/`) — `Protocol` interfaces only, no behavior change
      (LLMProvider, ToolProvider, ASRProvider, TTSProvider, Transport) — *merged via PR #3*
- [ ] **Critical fixes (small, high impact):**
  - [x] Wire rate-limiter (`check_or_raise`) + `record_call` / session stats into
        `llm_completion` (was dead code) — *merged via PR #6*
  - [x] Single cost source: dropped `client.py` local `_calculate_cost` →
        `models.calculate_cost` — *merged via PR #6*
  - [ ] **LLM response cache — deliberately deferred.** `ResponseCache` is
        exact-match (`md5(messages+model)`); in a ReAct dialog every turn sends a
        *growing* history, so identical requests almost never recur and the real
        hit-rate ≈ 0. The actual cost/quality lever is history management (see
        Phase 2). Decide cache's fate there — likely delete, or replace with a
        semantic cache — rather than wiring low-ROI infra now.
  - [x] Empty `respond` message handling: model could pick `action: respond`
        with an empty `message`; the falsy check in `run_until_response` treated
        `""` as "no response" and silently fell through to `timeout_message`
        (wasting an LLM call). `step()` now detects an empty respond, injects a
        corrective observation and retries (bounded by `max_tool_calls_per_response`
        → no loop / cost blowup); `run_until_response` distinguishes `None` from a
        real reply via `is not None`. Empty *user* input (silent caller) left as a
        boundary concern for the voice phase. — *merged via PR #9*
  - [x] DB singleton fix (`shared/src/database/connection.py`): removed the broken
        `__new__` singleton. `__init__` re-ran on every `DatabaseConnection(...)`
        call (Python always calls it after `__new__`), replacing `self._local` →
        leaking open thread-local connections, and mutating `db_path` to the last
        caller's path while keeping the first instance — two conflicting sources of
        truth (`cls._instance` vs module `_db_connection`) and cross-test pollution.
        Now a plain class; lifecycle is owned solely by `init_database` /
        `get_db_connection` (which everyone already uses); `init_database` closes the
        previous connection before replacing. — *via `fix/db-singleton`*
  - [x] Transaction atomicity (`crm_mcp/tools/tickets.py`): `create_ticket` wrote
        the ticket row and its history entry in **two separate** `db.cursor()`
        blocks — each its own commit — so a failure on the second left an orphan
        ticket with no history (unrecoverable, already on disk). Both writes now
        share a single `db.transaction()` (commit-or-rollback together). Same fix
        applied to `update_ticket_status` (status update + resolution history),
        which had the identical two-commit pattern. — *via `fix/ticket-atomicity`*
  - Lock down SQL f-strings: `shared/.../database/base.py:157`
  - Error / PII sanitization at tool boundary; redact phone numbers in logs
  - `Optional[...]` type-hint sweep
  - **Pydantic v1→v2:** migrate class-based `Config` → `ConfigDict` across
    `shared/src/isp_types/*` (Customer, Address, Port, Ticket, …); clears 13
    `PydanticDeprecatedSince20` warnings. Also drop the `UP042` ratchet by moving
    enums to `enum.StrEnum`. *(Dedicated pass — touches all shared models.)*
  - **Windows UTF-8:** `scripts/setup_db.py` & `scripts/seed_data.py` crash with
    `UnicodeEncodeError` printing emoji to a cp1252 console — add a stdout UTF-8
    reconfigure (or drop the emoji).

- **Found & fixed by the regression net:** `run_ping_test` queried a non-existent
  `ping_logs` table (schema has `ping_tests`) — fixed in PR #2.

**Done:** CI green · scenario eval green · demo behaves as before (no regression).
**Stable from here:** the port interfaces — every later phase plugs into them.

---

## Phase 1 — RAG correctness · `fix/rag-retrieval`

**Goal:** reliable ranking and measurable retrieval quality.

- [ ] `IndexFlatIP` + use cosine score directly; retune thresholds — `rag/vector_store.py:75,192`
- [ ] Single `DocumentProcessor`, token-based chunking (merge `document_processor.py` vs `scripts/build_kb.py`)
- [ ] Real hybrid retrieval: BM25 (`rank_bm25`) or RRF normalization — `rag/hybrid_retriever.py:262`
- [ ] Implement `_rebuild_index` (currently `pass`) or persist embeddings — `vector_store.py:289`
- [ ] Embedding dim from the model; include `normalize` flag in cache key — `rag/embeddings.py`
- [ ] LT↔EN cross-lingual retrieval tests (small eval set with expected docs)

**Done:** eval set returns correct docs in top-k; thresholds are principled, not arbitrary.

---

## Phase 2 — Agent core · `refactor/tool-calling`

**Goal:** robust, latency-friendly agent; prep for voice and Ollama.

- [ ] **ReAct regex → native tool / function calling** via LiteLLM (removes the fragile parser)
- [ ] Tool-argument validation against the schema (replaces the `tools.py` `**kwargs` risk)
- [ ] History management: truncate / summarize observations — `react_agent.py:159`
- [ ] Route DB access through repositories / MCP consistently (no raw SQL in tools)
- [ ] Normalize tool response schema (`find_customer` addresses)
- [ ] `AgentSession` stable interface (`handle_turn(text) -> reply`) — base for voice and web

**Done:** scenario eval green with native tool-calling; switching model (OpenAI/Claude/Ollama) is config-only.

---

## Phase 3 — Voice vertical slice · `feat/voice-fastrtc`

- [ ] `ASRProvider` (faster-whisper, LT) + `TTSProvider` (gTTS, LT) adapters
- [ ] FastRTC `Stream` + `ReplyOnPause` handler → ASR → `AgentSession` → TTS
- [ ] `.ui.launch()` for instant testing

**Done:** speak Lithuanian, agent replies by voice, consultation quality testable end-to-end.

---

## Phase 4 — Service & frontend

- [ ] FastAPI app + `stream.mount(app)`; thin custom client
- [ ] Streamlit → debug / monitoring only

**Done:** voice served through your own FastAPI; Streamlit latency gone.

---

## Phase 5 — Realtime & telephony

- [ ] Barge-in / streaming polish
- [ ] `fastphone()` real-call test → later Twilio / PBX `transport` adapter

**Done:** call the agent from a real phone; core untouched.

---

## Phase 6 — Local models

- [ ] Ollama llama3 + HF models = adapter swap; (later) finetuning prep

**Done:** local mode works via config; hybrid if LT quality requires it.

---

## Phase 7 — Production hardening

- [ ] Observability (structured logs, traces, cost guards), deploy, secrets, `security-review`

---

## Cross-cutting — regression / eval safety net

The scenario eval (Phase 0) is kept **green across all phases**. It guarantees that refactoring
never degrades consultation quality — the core "pro" safety net.

## Risk register

| Risk | Mitigation |
|------|------------|
| LT TTS/STT quality | "Understandable" is enough early; swap voices later behind the TTS port |
| llama3 LT + tool-calling weaker than GPT-4o/Claude | Hybrid routing (cloud for LT reasoning, local for cheap tasks) |
| FastRTC dependency weight | Isolated inside the `transport` adapter |
| Breaking the live demo | `main` is PR-only; `v1-demo` tag is the restore point |

---

## Current next action

- [x] Tag `v1-demo` on `main`; create `develop` and `chore/foundation`.
- [x] Commit this `docs/ROADMAP.md` as the reference document.
- [x] Phase 0 · Tooling + CI + pre-commit (PR #1).
- [x] Phase 0 · Regression safety net + `pytest` in CI (PR #2).
- [x] Phase 0 · Ports skeleton (`ports/` Protocol interfaces) (PR #3).
- [x] Phase 0 · Critical-fix #1 — LLM rate-limiter + session stats + single cost
      source wired into `llm_completion`; cache deferred (PR #6).
- [x] Phase 0 · Critical-fix #2 — empty `respond` message handling (PR #9).
- [x] Phase 0 · Critical-fix #3 — DB singleton (`__new__`) removed; lifecycle via
      `init_database` only (`fix/db-singleton`).
- [x] Phase 0 · Critical-fix #4 — transaction atomicity for `create_ticket` +
      `update_ticket_status` (single `db.transaction()`) (`fix/ticket-atomicity`).
- [ ] **Next:** Phase 0 · Critical-fix pass continues — SQL f-string lockdown
      (`database/base.py`), then PII sanitization at the tool boundary — all
      protected by the green scenario eval.

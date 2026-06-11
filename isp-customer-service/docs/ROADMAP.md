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
  - [x] Lock down SQL f-strings (`shared/src/database/base.py`): `count()` and
        `exists()` interpolated `{table}` and `{where}` directly into the SQL
        string (no parameterisation) — a SQL-injection vector. A codebase scan
        showed both methods were **unused** (every other `.exists()` was
        `pathlib.Path.exists()`), so they were deleted outright (0 code = 0 risk)
        rather than hardened. The remaining `execute_*` helpers already use `?`
        placeholders. — *via `fix/sql-injection`*
  - [x] PII sanitization at the tool boundary (redact phone numbers in logs):
        customer phone numbers (GDPR identifiers) were logged in plain text at
        `find_customer`, CRM lookups and agent init. Added central redaction in
        `shared/src/utils/logger.py` — `redact_phone()` masks LT numbers to the
        last 4 digits (`***2345`) via an anchored regex that leaves IPs, MACs
        and CUST/ticket IDs untouched; a `LogRecord` factory + handler filter
        mask **every** logger process-wide (covers module loggers that only
        propagate to a Streamlit/basicConfig root), installed via
        `install_pii_redaction()` at the app/CLI entry points. Traceability is
        preserved: `REDACT_PII` flag (default on) lets local testing keep full
        numbers; deployed stays masked. Names/addresses (not regex-catchable)
        dropped from the relevant call-sites. Tool return payloads unchanged —
        the agent still gets the real number. 19 unit tests added. — *PR #14*
  - [x] **Regression-net hardening (during #5):** the session DB fixture only
        built the SQLite DB when missing, so a cached DB from a prior day let
        `datetime('now')`-relative seed rows (CUST008 packet-loss / bandwidth in
        a `-24h` window) age out → non-deterministic `TestScenario08` failures.
        `conftest.py` now rebuilds the DB every session (sub-second, pure
        sqlite3). — *PR #13*
  - [x] **Pydantic v1→v2:** migrated class-based `Config` → `ConfigDict` across
    `shared/src/isp_types/*` (Customer, Address, Port, Ticket, …); cleared 13
    `PydanticDeprecatedSince20` warnings. Also dropped the `UP042` ratchet by moving
    enums to `enum.StrEnum`. Behaviour-neutral (verified `-W error::DeprecationWarning`
    + full suite green). — *PR #15*
  - [x] `Optional[...]` type-hint sweep — **moot:** the only `Optional[...]` in
    tracked code lived in a ~400-line commented-out *old* version of
    `mcp_service.py`; the live rewrite already uses `X | None` / `from typing import
    Any`. Rather than rename hints inside dead comments, deleted the stale block
    outright (891 → 490 lines; old version preserved in git history). No live
    behaviour change.
  - [x] **Windows UTF-8:** `scripts/setup_db.py` & `seed_data.py` (plus the three
    `scripts/test_*.py` smoke tests) crashed with `UnicodeEncodeError` printing emoji
    to a cp1252 console. Dropped the decorative emoji outright (the `€` currency sign
    in `test_shared.py` kept) — output is now pure ASCII, no reconfigure needed. — *this PR*

- **Found & fixed by the regression net:** `run_ping_test` queried a non-existent
  `ping_logs` table (schema has `ping_tests`) — fixed in PR #2.

**Done:** CI green · scenario eval green · demo behaves as before (no regression).
**Stable from here:** the port interfaces — every later phase plugs into them.

---

## Phase 1 — RAG correctness · `fix/rag-retrieval`

**Goal:** reliable ranking and measurable retrieval quality.

*Measure-first:* the eval harness + RetrieverPort seam were built **before** the
retrieval changes, so every change below is verified against numbers, not eyeballed.

- [x] **`RetrieverPort` seam + centralized RAG config** — retrieval sits behind a
      `Protocol` (`ports/retrieval.py`); tuning knobs (`rag_index_type`, `rag_top_k`,
      `rag_threshold`, `rag_keyword_weight`, `rag_default_lang`) moved to
      `Config`/env, out of scattered call-sites. — *PR #17 (`feat/rag-retriever-port`)*
- [x] **Eval harness (recall@k + MRR)** — fixed 18-query LT set (`rag/eval/queries.json`)
      + `run_eval.py` measuring recall@k (lenient/strict) and MRR for BASE vs HYBRID
      via `RetrieverPort.retrieve()` only. Baseline: recall@3=1.0, MRR base 0.917 /
      hybrid 0.972 (hybrid measurably ranks better → reason to wire it into prod).
      — *PR #18 (`feat/rag-eval-harness`)*
- [x] **`lang` metadata (multilingual foundation)** — every chunk stamped with a
      `lang` from a `knowledge_base/<lang>/<category>/` folder convention (flat LT →
      `lt`; dropping an `en/` tree later is auto-picked with zero code change).
      Groundwork for the LT↔EN cross-lingual eval below. — *PR #18*
- [x] **`IndexFlatIP` + cosine score directly** — FAISS flipped flatl2 → flatip;
      score is now raw interpretable cosine in [-1, 1]. Ranking unchanged (as
      expected — cosine changes values, not order); hit-score floors readable:
      BASE min=0.501, HYBRID min=0.381. **Also fixed a silent `isp_shared`/`shared`
      import bug** that made every RAG module hit its except-fallback (so config
      never reached the index — the flip looked dead until repointed to `utils`).
      — *PR #18*
- [x] **Production retrieval wired to HYBRID + config** — `tools.py:search_knowledge`
      switched from BASE to `get_hybrid_retriever()` (eval: MRR 0.972 vs 0.917) and
      now reads `config.rag_top_k/rag_threshold`; `get_hybrid_retriever` resolves its
      knobs from config too. Key insight: the threshold gates the *semantic cosine*
      pre-filter inside the hybrid (before the keyword blend), so the existing 0.4 is
      already a valid floor — correct-doc cosine ≥0.5. Verified recall@3=18/18 holds
      at threshold=0.4. — *`feat/rag-prod-hybrid-wiring`*
- [x] **Single `DocumentProcessor`** — merged the dead `document_processor.py` with the
      inline copy in `build_kb.py`; the canonical lang-aware class now lives in
      `rag/document_processor.py` and `build_kb.py` imports it. Behaviour-preserving
      (recall@3 = 18/18). — *`refactor/rag-single-document-processor`*
- [ ] Token-based chunking (current `_chunk_text` splits on whitespace words) — `rag/document_processor.py`
- [x] **Real hybrid retrieval: BM25 + RRF** — replaced the weighted keyword-overlap
      re-ranker with `rank_bm25.BM25Okapi` over the FULL corpus (catches exact
      technical matches semantic misses) fused with Reciprocal Rank Fusion (k=60,
      ranks not raw scores). `keyword_weight` is now the RRF weight on the BM25 arm;
      `threshold` still gates the semantic arm only. Eval: recall@3=18/18, MRR 0.972
      (no regression; this LT set lacks the model-number cases where BM25 wins, so
      the gain is architectural — proven by design + smoke test). — *`feat/rag-bm25-rrf-hybrid`*
- [ ] Implement `_rebuild_index` (currently `pass`) or persist embeddings — `vector_store.py:296`.
      **Verified not on the demo path:** `_rebuild_index`'s only caller is
      `delete_document`, which is **unused anywhere in `src/`**. `build_kb.py` always
      rebuilds the KB from scratch (fresh retriever → `add_documents` → `save`), never
      deletes — so adding S4/S5 content (Phase 2.5 step 6) does **not** trigger the
      stale-index bug. Stays deferred / low-priority; fix only if incremental
      delete is ever needed.
- [ ] Embedding dim from the model; include `normalize` flag in cache key — `rag/embeddings.py`
- [ ] LT↔EN cross-lingual retrieval tests (small eval set with expected docs) — `lang` metadata foundation already in place
- [ ] _(later stage)_ RAG content governance: structure the knowledge base to the
      company's processes, de-duplicate / strip noise, and a workflow for
      updating & extending docs — eventually automate the add/fix pipeline. Deferred
      until there is more real content and settled internal conventions; re-run the
      eval harness after each content change to catch retrieval regressions.

**Done:** eval set returns correct docs in top-k; thresholds are principled, not arbitrary.

---

## Phase 2 — Agent core · `refactor/tool-calling`

**Goal:** robust, latency-friendly agent; prep for voice and Ollama.

- [x] **ReAct regex → native tool / function calling** via LiteLLM (removes the fragile
      parser): `Tool.to_openai_schema()` + `llm_tool_completion` + `step()` rewrite
      (assistant `tool_calls` → `role:"tool"` results, no regex). — *PR #22*
- [x] Tool-argument validation against the schema (replaces the `tools.py` `**kwargs`
      risk): `Tool.validate_arguments()` guards `execute_tool` — missing required →
      structured error observation (model self-corrects, no call); unknown args dropped
      + warned; scalar→string coercion. — *PR #23*
- [x] **Normalize tool response schema** — same logical field has the same shape across
      every return path. Resolved the `find_customer` `addresses` vs `address` split via
      an **enrichment-by-id** pattern: any search key (phone/address) only resolves a
      `customer_id`, then `get_customer_details(customer_id)` → `_format_customer_profile`
      yields one identical envelope (`{"success": True, ...}` / `{"success": False,
      "error", "message"}`) with `addresses`/`status`/`email`/`active_services` on every
      path. `check_outages` gained `affected`/`outage_count`; `create_ticket` /
      `run_ping_test` else-branches stop leaking raw passthrough. — *PR #24*
- [x] **`AgentSession` stable interface** (`handle_turn(text) -> reply` + `greeting()`) —
      composition wrapper over `ReactAgent`; the single seam every transport (CLI,
      Streamlit, voice) calls, so history/memory/model/prompt internals evolve behind it.
      `run_cli` migrated to it; fixed a latent `full_address` state bug. — *PR #25*
- [x] **History management** — windowed LLM payload behind `AgentSession`:
      `_prune_history` (tool-pairing-safe sliding window, `config.history_window_messages`)
      keeps the payload bounded while `AgentState.messages` stays the full transcript;
      `_state_facts_block` re-injects resolved customer/problem/ticket facts (no extra
      LLM call) so pruning never loses context. Static system prompt stays cache-friendly;
      the fact addendum is the seam where identity-gate/policy plugs in. — *PR #26*
- [x] **Route DB access through MCP consistently (no raw SQL in tools)** — the agent
      tool layer no longer calls `db.cursor()`. The three raw-SQL helpers in `tools.py`
      (ports/ip/ping_tests/bandwidth_logs) were removed; that SQL moved into the
      network-diagnostic adapter as `get_packet_loss_summary` / `get_bandwidth_summary`
      (24h aggregation the service lacked), returning the exact shapes the agent already
      consumed. `ImportError` → clean `service_unavailable` envelope (no silent DB
      fallback). MCP service = the DB adapter; agent depends only on it. — *PR #27*
- [ ] **Identity gate + `policy.yaml` (core vision — deferred to voice/live testing)** —
      plugs into the `AgentSession` / `_state_facts_block` seam. Intentionally built
      *after* the voice slice (Phase 3) so it's tuned against real call transcripts, not
      imagined scenarios. The lookup
    finds an *account*, not necessarily the *caller*. Real-world variants to handle
    (captured now, designed/tuned during live testing):
    - Caller's phone resolves to an account, but the **address is someone else's** —
      caller is helping parents / a neighbour, or lives elsewhere. Address match ≠ caller
      identity.
    - Contract under a **spouse's / family member's name**; caller may not know whose
      name it's registered under.
    - **Partial name match** (surname matches, given name differs, e.g. "Romutė" vs the
      registered "Roma") → ask a clarifying question rather than accept/reject outright.
    - Possible **extra verification tools**: is this phone number seen in the outage /
      support history for that address? does the surname match? ask who signed the
      contract, DOB, etc.
    - **PII-disclosure guardrails (two-way):** don't over-reveal ("there's a contract at
      this address, but not under Andrius's name"), yet sometimes a name/surname/DOB
      *must* be revealed/confirmed to disambiguate. Where to relax vs. tighten is a
      `policy.yaml` decision, validated by where lookups string/fail in testing.

**Done:** scenario eval green with native tool-calling; switching model (OpenAI/Claude/Ollama) is config-only.

---

## Phase 2.5 — "Neveikia internetas" demo slice · `feat/no-internet-demo`

**Goal:** prove ONE repeatable pattern end-to-end on a single fault family —
**identify the fault → reach a verdict → instruct the customer step-by-step →
close (inform / escalate / resolve remotely)** — text-to-text first. Every other
fault (incl. TV) reuses the same template; only knowledge-base / seed content
changes.

> **Design docs (the "why" + domain logic) live in `chatbot_core/docs/`:**
> - `scenarijus_neveikia_internetas.md` — domain reference/TEMPLATE: causes →
>   detection → action, provider side (B1–B3) + customer side (B4–B7), diagnostic
>   pipeline Steps 1–4 (BŪSENA A/B/C).
> - `demo_plan_neveikia_internetas.md` — demo scope, scenarios S1–S5, two-speed
>   latency, locked decisions.
> - `kliento_identifikacijos_dizainas.md` — hierarchical voice-robust customer lookup.
> - `pokalbio_valdymas.md` — turn-taking / barge-in / state-aware timeouts (voice runtime).

**Scope:** only "no internet / nėra interneto." Demonstration of capability, not a
full product. Locked decisions: verdict = ONE deterministic composite tool (A
variant); SMS dropped entirely; MAC-change + reboot/port-reset = simulated (stub)
tools; two-speed latency flow; "fill-the-wait-with-symptoms + parallel diagnostics"
is MANDATORY agent behaviour (into the system prompt).

**Build order (text-to-text):**

- [x] **1. Seed customers S1–S5 (mock telemetry via seed DB).** — *done: additive
      `database/seeds/demo_internet.sql` (CUST101–111, SW101–103, streets+district);
      schema: `ports` +`observed_mac`/`crc_error_rate`/`dhcp_status`, `area_outages`
      +`switch_id` (OUT001 linked to SW001), `customers` +`account_code`, `streets`
      +`district`; wired into `conftest.py` + `seed_data.py`; suite 135/135 green.* Each scenario
      customer carries a known telemetry state (billing / incident / switch / port
      / MAC / CRC / DHCP) so `diagnose_connection` returns a deterministic verdict.
      Mechanism approved: per-scenario seed rows feed the mock telemetry (extends the
      existing versioned-SQL seed the regression net already rebuilds).
      **APPROVED — where telemetry lives (data-sourcing architecture):**
      - **Telemetry belongs to the NETWORK domain, not CRM.** Customer/billing/contract
        = CRM (`crm_mcp`); switch / port / `observed_mac` / `crc_error_rate` /
        `dhcp_status` / vlan / outage = network (`network_mcp`). The 3 missing fields
        go into `network_schema.sql` (on `ports` or a `port_telemetry` snapshot table);
        `area_outages` gets a `switch_id` FK. **Decision: seed rows in the schema, NOT a
        separate Python mock layer** — one coherent seed world (customer Sxx → its ports
        → telemetry state), and the tool's "fetch" path is identical to real integration
        (call tool → adapter queries source → returns signals).
      - **The agent never touches the DB** — it calls a tool (port); the adapter reads
        the seed now, real OSS/network systems (SNMP, RADIUS, DHCP, switch CLI/TR-069,
        NMS) later. Swap = adapter-only; agent + verdict logic unchanged. The stable seam
        is the **tool contract** (`signalai{...}` shape), designed to match what real
        systems can return.
      - **Shared vs separate DB:** keep the **logical** separation strong (separate
        schemas + separate MCP services — already in place). Physically one SQLite file
        for the demo is fine because access is service-only (Phase 2: "no raw SQL in
        tools"). When network becomes a real separate system, swap only the network
        adapter's backing — CRM + agent untouched. **Do NOT JOIN across the CRM/network
        schemas** — `diagnose_connection` orchestrates by calling both services
        separately (see step 2), so the future split stays an adapter swap, not a rewrite.
      - **APPROVED — seed locations** (full scheme in
        `kliento_identifikacijos_dizainas.md` §8.1): Šiauliai (main stage) +
        **Šiaulių r. with THREE villages** (Ginkūnų / Bubių / Vinkšnėnų k. — forces
        the "which village?" question). Streets: Dainų g. / Dailės g. (fuzzy pair) /
        Tilžės g. (apartment block, full 5-level flow) / **Žemaitės g.** (street
        named after a surname — must not be confused with the customer's surname) /
        **S. Dariaus ir S. Girėno g.** (long compound name with initials — spoken
        many ways → normalization/fuzzy challenge) in Šiauliai; Žeimių g. (Ginkūnai),
        Aušros g. (Bubiai), Sodo g. (Vinkšnėnai). Key addresses: Tilžės g. 60
        (flats 1–12), Dainų g. 5 (the §7.2 example verbatim), Dainų g. 7 (two
        contracts, no flats → surname disambiguation), **S. Dariaus ir S. Girėno g.
        25-45** (flat in a big block + compound-name recognition), **Žeimių g. 12-6,
        Ginkūnų k.** (street-level recovery: "Šiauliai, Žeimių g." → not in Šiauliai
        → suggest Šiaulių r.), **Aušros g. 8, Bubių k.** (village-level
        disambiguation), **Sodo g. 122F, Vinkšnėnų k.** (house number with a letter —
        voice/STT robustness). ~11 customers: S1–S5 + the Dainų g. 7 pair + the
        recovery/edge customers; one found by phone, one carries an account code.
- [ ] **2. `diagnose_connection` verdict tool (A variant, "thick"/deterministic) —
      ORCHESTRATOR above both services.** It belongs to neither DB: it calls CRM
      (billing/suspension → B1) **and** network (outage/switch/port/MAC/CRC/DHCP →
      B2–B7), then applies the decision tree. One call gathers signals →
      `{pusė: tiekėjas|klientas|neaišku, grupė: B1..B7, veiksmas:
      informuoti|kurti_tiketą|instruktuoti, priežastis, signalai{...}, žinutė_agentui}`.
      The decision tree (Steps 1–4, BŪSENA A/B/C) lives in code; on `klientas`/`neaišku`
      it hands off to the conversation (does NOT decide the final cause). Fast for voice.
- [ ] **3. System-prompt rewrite.** Bakes in: hierarchical identification, two-speed
      latency flow (fast path = incident/billing → inform & terminate instantly; slow
      path = full diagnostics with announced delay), MANDATORY fill-wait-with-symptoms
      + parallel diagnostics, and A/B/C branch routing after the verdict.
- [ ] **4. Identification lookup improvements.** Wire the existing
      `normalize_street_name` + `fuzzy_match_street` into the voice/dialog path;
      per-level lookup (city → street → house → apartment); account-code lookup;
      surname-for-confirmation-only (PII: agent never states the surname first).
      **Connects to the deferred Phase 2 "Identity gate + `policy.yaml`" item** — this
      is the concrete first cut of that lookup, to be tuned later against real
      transcripts.
- [ ] **5. Simulated tools `update_mac` / `reset_port` (stubs).** Log + "success"
      message, no real infrastructure — demonstrate the B6/B4 action flow. Detail
      level of the simulated responses still open (so the dialog feels real).
- [ ] **6. RAG knowledge-base entries for S4/S5 instruction steps.** Step-by-step
      customer-side guidance (power/cable check; Factory Reset → DHCP; Wi-Fi module),
      delivered one step at a time. Re-run the eval harness after content changes.
- [ ] **7. CLI text-to-text test.** Validates LOGIC/dialog flow (identification,
      verdict → A/B/C routing, instruction steps, ticket creation, filtering zone).
      Voice runtime (barge-in, real latency, state-aware timeouts) is documented in
      `pokalbio_valdymas.md` but deferred to the voice phase — non-blocking here.

**Scenarios (S1–S5):** S1 Apmokėjimas (B1) inform, no ticket · S2 Masinė avarija
(B2) inform + ETA, **no ticket** (already-registered incident) · S3 Tinklo gedimas
individualus (B3) → ticket · S4 Kabelis/maitinimas (B4/B5) instruct → resolve or
ticket · S5 Routerio suderinimas (B6/B7) instruct/simulate → resolve or ticket.

**Resolved mini-decisions:** telemetry lives in the network schema as seed rows
(step 1); seed locations approved (step 1 / design doc §8.1); disambiguation depth =
city + village level (seed supports it); **ticket = fault registration with NO time
promise** — the agent creates the ticket and says a worker will call (next business
morning) to arrange the visit; the agent never promises a time and knows nothing of
technician schedules → **no working-hours logic in the demo** (no after-18:00
branching in branch C).

**Done:** the five scenarios run end-to-end in CLI text-to-text — correct
identification, correct verdict→branch, correct close (inform / ticket / resolve) —
proving the template generalises to other faults by content alone.

> **Feedback loop (applies from here on):** improvements surfaced during testing
> (text-to-text first, then voice) are folded **back into this roadmap and the
> `chatbot_core/docs/` design docs** as we go — the docs stay the living source of
> truth, roadmap tracks the work. Voice-only refinements (real latency,
> barge-in, state-aware timeouts — see `pokalbio_valdymas.md`) are captured but
> only acted on in the voice phase below.

---

## Phase 3 — Voice vertical slice · `feat/voice-fastrtc`

> **Sequencing:** starts **after** the Phase 2.5 text-to-text slice validates the
> dialog logic. Voice testing then checks how the agent actually *converses* by
> voice — and any improvements it surfaces feed back into the roadmap + docs
> (see the Phase 2.5 feedback-loop note). The runtime behaviours in
> `pokalbio_valdymas.md` (barge-in, endpointing, waits during reboot, state-aware
> timeouts) are realised here, not in text-to-text.

- [x] `ASRProvider` (faster-whisper, LT) + `TTSProvider` (gTTS, LT) adapters,
      plus framework-free `VoicePipeline` (ASR → `AgentSession` → TTS) behind
      the ports. Engine imports deferred so adapters construct without the
      `voice` extra; offline tests cover protocol conformance, empty inputs,
      WAV/PCM decoding and pipeline orchestration. — *PR #28*
- [ ] FastRTC `Stream` + `ReplyOnPause` handler → `VoicePipeline` (transport adapter)
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
- [x] Phase 0 · Critical-fix #5 — SQL f-string lockdown: deleted unused
      `count()`/`exists()` (injection vector) from `base.py` (PR #13).
- [x] Phase 0 · Regression-net hardening — `conftest.py` rebuilds the test DB
      every session so time-windowed seed data never goes stale (PR #13).
- [x] Phase 0 · Critical-fix #6 — PII sanitization: central phone-number
      redaction in logs (`redact_phone` + LogRecord factory + `REDACT_PII`
      flag); 19 unit tests (PR #14).
- [x] Phase 0 · Pydantic v1→v2 migration (`ConfigDict` + `StrEnum`) across the
      shared models (PR #15).
- [x] Phase 0 · final cleanup — dropped decorative emoji from `scripts/*.py`
      (fixes the cp1252 `UnicodeEncodeError`) and deleted the ~400-line
      commented-out old `mcp_service.py` (the only `Optional[...]` site, hence the
      sweep was moot) (`chore/strip-script-emoji`).
- [x] Phase 1 · RetrieverPort seam + centralized RAG config (PR #17,
      `feat/rag-retriever-port`).
- [x] Phase 1 · Eval harness (recall@k + MRR, 18-query LT set) + `lang` metadata
      foundation + `IndexFlatIP` cosine flip (with the silent `isp_shared` import-bug
      fix that had kept the flip dead) (PR #18, `feat/rag-eval-harness`).
- [x] Phase 1 · production retrieval wired to HYBRID + config thresholds
      (`tools.py:search_knowledge` → `get_hybrid_retriever()`, knobs from
      `config.rag_*`); recall@3=18/18 verified at threshold=0.4
      (`feat/rag-prod-hybrid-wiring`).
- [x] Phase 1 · single `DocumentProcessor` — merged the dead `document_processor.py`
      with the inline copy in `build_kb.py`; canonical class now in
      `rag/document_processor.py`, behaviour-preserving (recall@3=18/18)
      (`refactor/rag-single-document-processor`).
- [x] Phase 1 · real hybrid retrieval — BM25 (full corpus) + RRF fusion replacing
      the weighted-overlap re-ranker; recall@3=18/18, MRR 0.972 (no regression)
      (`feat/rag-bm25-rrf-hybrid`).
- [x] Phase 2 · ReAct regex → native tool/function calling (LiteLLM): schema export +
      `llm_tool_completion` + `step()` rewrite (PR #22).
- [x] Phase 2 · tool-argument validation against the schema (`Tool.validate_arguments`
      guarding `execute_tool`) (PR #23).
- [x] Phase 2 · normalize tool response schema across all 6 tools (one envelope +
      enrichment-by-id; fixes `find_customer` `addresses` vs `address`) (PR #24).
- [x] Phase 2 · `AgentSession` stable interface (`handle_turn`/`greeting`) over
      `ReactAgent`; `run_cli` migrated; latent `full_address` bug fixed (PR #25).
- [x] Phase 2 · history management — windowed payload behind `AgentSession`
      (`_prune_history` tool-pairing-safe + `_state_facts_block` durable-fact
      re-injection; `config.history_window_messages`) (PR #26).
- [x] Phase 2 · route DB access through MCP — removed all raw SQL from the agent
      tool layer; SQL moved into the network-diagnostic adapter
      (`get_packet_loss_summary` / `get_bandwidth_summary`); `ImportError` → clean
      `service_unavailable` envelope (PR #27).
- [x] Phase 3 · voice adapters slice — `FasterWhisperASR` + `GTTSProvider` behind
      the ASR/TTS ports, plus framework-free `VoicePipeline` (ASR → `AgentSession`
      → TTS). Engine imports deferred; `voice` optional extra; offline tests green
      (PR #28).
- [ ] **Next:** Phase 2.5 · "Neveikia internetas" demo slice (text-to-text) —
      build order: (1) seed S1–S5 + mock telemetry, (2) `diagnose_connection`
      verdict (A variant), (3) system-prompt rewrite (hierarchical ID + two-speed
      latency + mandatory fill-wait + A/B/C routing), (4) identification lookup
      (wire normalizer/fuzzy, per-level, account-code, surname-confirm — first cut
      of the deferred Identity-gate item), (5) simulated `update_mac`/`reset_port`,
      (6) RAG KB for S4/S5, (7) CLI text-to-text test. Design docs in
      `chatbot_core/docs/` (`scenarijus_`, `demo_plan_`, `kliento_identifikacijos_`,
      `pokalbio_valdymas`).
- [ ] Phase 3 · FastRTC transport adapter — `Stream` + `ReplyOnPause` →
      `VoicePipeline`, `.ui.launch()` for live Lithuanian voice testing; add
      `fastrtc` to the `voice` extra. Identity-gate / `policy.yaml` follows, tuned
      against real call transcripts.
- [ ] _(deferred)_ Phase 1 · token-based chunking (replace whitespace-word `_chunk_text`)
      and the LT↔EN cross-lingual eval (lang metadata already in place). The
      cross-lingual / harder eval set is also what would finally show BM25's upside
      numerically. Each measured against the eval harness.

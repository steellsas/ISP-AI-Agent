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
- **Frameworks where they earn it (revised 2026-06-18).** The earlier hard
  "framework-free core" rule is relaxed: proven libraries/frameworks (e.g.
  LangGraph for orchestration) are adopted when they make the app more
  professional and faster to build — *behind the Ports*, so they stay swappable.
  The non-negotiable that remains: **decision logic stays pure and unit-testable**
  (slot policy, verdict tree) — the framework wires and runs the decisions, it
  does not own them.
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
- [x] **2. `diagnose_connection` verdict tool (A variant, "thick"/deterministic) —
      ORCHESTRATOR above both services.** — *done: `agent/verdict.py`
      (`gather_signals` I/O + pure `decide` tree, unit-testable without DB);
      `get_billing_status` added to the CRM adapter (get_customer_details filters
      to active plans, so suspension_reason was invisible); network adapter:
      `check_port_status` SELECT +telemetry fields +switch_status,
      new `get_switch_neighbor_summary` (assigned-port neighbour correlation);
      thin tool wrapper + registration (English keys: side/group/action/reason/
      agent_message, LT text in agent_message); 23 verdict tests (every tree
      branch + S1-S5 integration over seed); suite 158/158 green.* It belongs to neither DB: it calls CRM
      (billing/suspension → B1) **and** network (outage/switch/port/MAC/CRC/DHCP →
      B2–B7), then applies the decision tree. One call gathers signals →
      `{pusė: tiekėjas|klientas|neaišku, grupė: B1..B7, veiksmas:
      informuoti|kurti_tiketą|instruktuoti, priežastis, signalai{...}, žinutė_agentui}`.
      The decision tree (Steps 1–4, BŪSENA A/B/C) lives in code; on `klientas`/`neaišku`
      it hands off to the conversation (does NOT decide the final cause). Fast for voice.
- [x] **3. System-prompt rewrite.** — *done + CLI-tested (3 scripted scenarios).*
      Identification is **address-first** (changed during testing: the phone is a
      HELPER only — mandatory fallback when the address lookup fails, anchored to
      the customer-stated address); full-sentence address capture (no forced
      level-by-level), echo+confirm, re-ask only the failing level, never re-ask
      given info; hard anti-hallucination rules (never invent customer_id/address;
      no diagnostics before identification — both observed in CLI and fixed);
      verdict routing (inform = fast path, create_ticket = no-time-promise wording,
      instruct = announce + fill-wait-with-symptoms + one-step-at-a-time);
      waiting behaviour; filtering zone; formal "Jūs"; vocabulary ("gedimo
      registracija", never "bilietas"). Known CLI-verified limits left for step 4:
      apartment never reaches the lookup (naive parse), district/village strings
      mangle the city field. Prompt polish backlog: B1 reason wording, surname
      offered as search in one turn, double address confirm.
- [x] **4. Identification lookup improvements — `resolve_address` rich-result tool.**
      — *done (contract: design doc §8.2).* New CRM adapter `address_resolver.py`:
      per-level diagnosis (city/street/house/apartment status + alternatives +
      LT `hint` telling the agent the exact next question); token-set street
      matching (compound names with initials, any word order — "Girėno Dariaus"
      → S. Dariaus ir S. Girėno g.); district+village in one phrase ("Šiaulių
      rajonas, Bubių kaimas" → Bubiai, genitive-tolerant); strong
      street-elsewhere beats weak in-city fuzzy (Žeimių → Ginkūnai recovery, not
      "gal Žemaitės?"); apartment finally reaches the DB (separate param);
      contracts_count → ask flat or surname; surname confirm-only, no PII leak
      in hints. `find_customer` gained `account_code`; agent state now tracks
      the customer from resolve_address too. 26 resolver tests; scripted
      AgentSession smoke: all 4 previously-failing scenarios pass (flat found
      first try, village extracted, Žeimių recovery dialog, account-code → B3
      ticket). Suite 184/184. **First concrete cut of the deferred Phase 2
      "Identity gate + policy.yaml" item** — tune against real transcripts later.
      Manual test script: `chatbot_core/docs/cli_testavimo_scenarijai.md`.
- [x] **4b. Prompt polish (CLI-testing findings — own commit).** — *done
      (prompt-only; per user decision validated within the step-6 RAG testing
      round rather than its own smoke).* Agreed after the step-4 manual CLI round:
      - **Phone↔address cross-check:** as soon as the customer names a street, peek
        at the caller's phone account; if its address matches the spoken street/house,
        offer the full address for confirmation in ONE turn ("Ar skambinate dėl
        Tilžės g. 60-7?") instead of asking city/flat separately.
      - **Early outage fast-path (mass-fault shortcut):** once the STREET is
        confirmed (no apartment needed!), call check_outages(city+street); active
        outage → inform + ETA and FINISH — no full identification, no flat question
        (everyone at that address is down anyway).
      - Convert spoken Lithuanian numerals to digits before tool calls ("dvylika"
        → 12; observed: house='dvulika' passed verbatim).
      - **Harden the phone-fallback anchor rule** — observed violation: address
        lookup failed, fallback found a DIFFERENT street's account and the agent
        created a ticket for the wrong address. The found account's street MUST
        match the spoken one, otherwise say "not found", never adopt the account.
      - Never print bracketed placeholders (observed verbatim output: "Priežastis:
        [priežastis iš agento žinutės]"); B1 must quote the exact verdict reason.
      - Surname is never offered as a search key; avoid double address confirmation;
        after account-code identification still confirm the address briefly.
- [x] **5. Simulated tools `update_mac` / `reset_port` (DB-effect stubs).** — *done.*
      Approved variant (b): the stubs MUTATE the mock DB so the flow is believable
      end-to-end — after update_mac a repeated diagnose_connection shows the problem
      GONE (observed==registered, DHCP ok, lease refreshed). Orchestration mirrors
      diagnose_connection: network adapter `bind_port_mac`/`reset_customer_port`
      (port_actions.py, new) + CRM adapter `update_equipment_mac`; agent-level
      update_mac calls both (no cross-schema writes in adapters). Clean
      `no_observed_mac` error when nothing is connected. Registry 8 -> 10;
      6 tests incl. end-to-end foreign_mac -> healthy + snapshot/restore fixture
      (session-scoped DB + mutating stubs = later test files must see seed state).
      Also needed by the B-Plan bridge content in step 6 (MAC binding is its core
      action). Observed in CLI: without the tool the model SAID "Dabar atnaujinsiu
      MAC adresą" and faked it via check_network_status — the stub closes this hole.
- [ ] **6. RAG knowledge-base entries for S4/S5 instruction steps.** Step-by-step
      customer-side guidance (power/cable check; Factory Reset → DHCP; Wi-Fi module),
      delivered one step at a time. Re-run the eval harness after content changes.
      **EXPANDED (approved 2026-06-12): "bridge until the technician" content —
      the B-Plan moves INTO scope** on the knowledge side. Dead router with a live
      line (internet reaches the home; router shows no life, TV dead too):
      - (a) connect the WAN cable DIRECTLY to one device (PC/laptop) + bind its MAC
        (`update_mac`) → temporary internet on one device;
      - (b) the customer uses/buys their OWN router → bind its MAC → full service.
      Goal: keep the customer online while waiting for the technician / router
      replacement. KB must teach the agent WHEN to offer it (router dead, line OK)
      and the exact steps + that MAC binding is required. Depends on step 5's
      `update_mac` stub.
- [ ] **6b. Proactive outage awareness (designed 2026-06-12, details TBD).**
      Motivated by a CLI bug: the model called check_outages city-only and
      attributed ANOTHER street's outage to the caller (sent away with the wrong
      answer while his real fault — foreign MAC — stayed unsolved). Patched at
      prompt+tool level (shortcut only pre-identification; street required;
      street-match mandatory; city-only tool warning), but the better design
      moves the decision out of the LLM entirely:
      - **`get_active_outages()` tool** — list of streets with active mass
        outages `{city, street, description, ETA}`; no customer needed.
      - **Pre-flight injection** — at session start (caller phone known),
        deterministically look up the phone account's street, match against
        active outages, and inject a fact via the `_state_facts_block` seam:
        the agent's FIRST reply to "neveikia internetas" can then be
        "Ar skambinate dėl Dainų g.? Ten avarija, visame kvartale nėra
        interneto, atstatymas ~17 val." — two-phrase handling during call
        storms. PII note: reveals only the street tied to the caller's number.
- [ ] **7. CLI text-to-text test.** Validates LOGIC/dialog flow (identification,
      verdict → A/B/C routing, instruction steps, ticket creation, filtering zone).
      Voice runtime (barge-in, real latency, state-aware timeouts) is documented in
      `pokalbio_valdymas.md` but deferred to the voice phase — non-blocking here.

- [x] **8. Observability — conversation trace (BEFORE the voice phase).** — *done.*
      Design: `stebejimo_dizainas.md`. One unified trace, hooked at the single `AgentSession`
      seam, so it is identical across CLI / voice / future UI. Per-session JSONL
      (`logs/sessions/<id>.jsonl`), one event per line: session_start / user_turn /
      tool_call / tool_result / **verdict (own type)** / agent_reply / session_end;
      every event carries `session_id` + `ts` (+ schema `v`). Thin
      `ConversationTracer` port → swappable sink (file now → UI reads the same →
      prod aggregator later). Trace ≠ error logs (errors appear in both). Reuses
      `REDACT_PII`; non-blocking append for voice. Debug verbosity now; tokens/cost,
      human-readable UI view, dashboards, and **conversation-history persistence**
      (session_end → existing `conversations` table, like a ticket) are deferred.
      Rationale: voice is far harder to debug than CLI (no live text stream), and
      this same trace is the foundation for the demo UI and Phase 7 observability.

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
- [x] FastRTC `Stream` + `ReplyOnPause` handler → `VoicePipeline` (transport
      adapter) + `.ui.launch()` for instant testing — *PR #32 (`feat/voice-real-agent`)*
- [x] **Hosted LT STT + observability + reliability fixes** — Groq Whisper
      (CPU has no GPU) for fast/accurate Lithuanian; richer trace (raw STT,
      per-tool/LLM timing, `.txt` export, per-turn audio recording); STT
      noise/hallucination filter + calmer VAD; phone pre-flight + echo-confirm
      address; LT number normalizer; `can_interrupt=False` (agent no longer cuts
      itself off); `resolve_address` city-recovery; fuzzy-"yes"; `.env` auto-load.
      — *PR #33 (`feat/voice-instrumentation`)*

**Done:** speak Lithuanian, agent replies by voice, consultation quality testable
end-to-end. **Voice testing surfaced structural faults → Phase 3.5 below.**

---

## Phase 3.5 — Conversation engine: dialog state + nodes · `feat/conversation-engine`

**Goal:** replace the single free-form ReAct loop with a structured dialog engine
— explicit typed slots, deterministic policy, focused nodes — so the agent stops
losing/overwriting facts, deciding wrongly, and is ready for many fault types and
(later) async voice.

> **Why now:** live voice traces (`logs/sessions/20260618-*`) exposed structural
> faults a prompt cannot fix: a garbled turn OVERWRITES a resolved address; the
> LLM HALLUCINATES a customer_id; it DIAGNOSES before identification; the address
> SPIRALS because there is no durable slot to protect. Root cause = the engine,
> not the prompt. Full design discussion → `chatbot_core/docs/pokalbio_variklis.md`.

### Architecture (target)
- **Per turn: NLU → DialogState (slots) → Policy → NLG.** The LLM only *understands*
  and *phrases*; the **decisions are made by code** (deterministic policy + verdict
  tree) — so it cannot re-open a resolved address, hallucinate an id, or rush.
- **Slots** (typed, Pydantic): `problem_type, city, street, house, apartment,
  address_verified, customer_id` — each with confidence; durable, never lost to a
  single garbled turn.
- **Nodes (one LangGraph):** Router (classify `problem_type`) → AddressValidation
  (Režimas A: slot-filling + tool-access gate, **problem-agnostic**) → Diagnosis
  (Režimas B: a **per-problem-type strategy registry** sharing "gather signals →
  verdict → act"; `diagnose_connection` is the first strategy).
- **Shared skeleton for EVERY fault** (no internet / slow / TV / billing …):
  identify → retrieve (RAG) → diagnose → resolve. A new fault = a new diagnosis
  strategy + KB content; identification and core stay untouched.

### Forward-compat principles (baked in from the start)
1. **Tools may be slow** — SQLite is a test stand-in; a real DB/OSS may be slower.
   Tool calls are timeout- and filler-ready; true async impl in Phase 5.
2. **Streaming TTS by design** — the TTS port is a streaming interface now; gTTS is
   a non-streaming adapter behind it; swap the engine without touching the core.
3. **State will grow** — dynamic state in a TRAILING message (not the system
   prompt), plus a state-summarization step when slots/history grow.
4. **Concurrency-ready (far future)** — no global mutable state; nodes are pure
   `(state) -> state`; checkpointer keyed by `thread_id` (one state per call).

### Corrections folded in (from trace evidence)
- Latency is **LLM + audio**, not the DB (tools run in 1–13 ms) — the gate is for
  CORRECTNESS, the filler masks the LLM (not the DB). Do **not** optimize DB I/O.
- Focused nodes buy **accuracy/control**, not dramatic speed (the LLM round-trip
  floor dominates; a shorter prompt is cheaper, not "lightning fast").
- Token-streaming into TTS needs a streaming engine (gTTS blocks it); the interim
  filler does not and lands first.
- Re-injecting facts into the **system prompt busts the prompt cache** — the real
  cost (not token count); fix by a stable system prompt + dynamic state in a
  trailing message.

### Build order
- [x] **0. Design doc `pokalbio_variklis.md`** — slot schema, policy state machine
      (a table, like the verdict tree), node graph, principles + corrections,
      target diagram next to the current architecture. *(No code.)*
- [x] **1.1 Prompt-cache fix** — stable system prompt; durable facts move from the
      system message to a trailing message (cache-friendly → lower latency/cost).
- [x] **1.2 Explicit slots in state** — typed `ClientProfileState`
      (city/street/house/apartment/`address_verified`/customer_id/problem_type);
      `resolve_address` writes into slots with confidence.
- [x] **1.3 Tool-access gate** — block technical tools until `address_verified`;
      deterministic guard in the dispatcher (kills diagnose-too-early + id
      hallucination). *Framework-independent — value even without LangGraph.*
- [x] **1.4 NLU extraction (Dual-Track)** — deterministic owns the *values* (street
      via the registry fuzzy, numbers via the normalizer); the LLM only *segments*
      the utterance into slot fields, and only when the deterministic track is
      ambiguous / the sentence is complex. A clean address skips the LLM entirely
      (faster + no hallucination). LLM never passes a street value directly —
      `resolve_address` validates it.
- [ ] **2. Latency masking** — TTS streaming port (gTTS adapter behind it) + instant
      filler ("sekundėlę, tikrinu…") at the `AgentSession` seam + **audio cache**:
      pre-render the fixed/static phrases (greeting, fillers, common instructions)
      as WAV/MP3 → 0 ms for those (the filler is a cache client). Caching adapter
      behind the TTS port; only FIXED phrases cache — LLM-varied replies still synth.
- **3. LangGraph migration** — done BEFORE step 2 (decision 2026-06-19: get the
  structure right, then mask latency on top of the working graph). Split:
  - [x] **3.1 graph plumbing** — one-node `StateGraph` + `MemorySaver` behind the
        `AgentSession` seam, delegating each turn to the existing ReactAgent
        (behaviour-preserving; `AGENT_ENGINE=legacy` bypass). `agent/graph.py`.
  - [x] **3.2 node split** — deterministic router (on `customer_id`) → two focused
        nodes: `address_validation` (lookup tools only — structural gate) and
        `diagnosis` (full toolset), each with a short stage prompt, both delegating
        the tool-loop to the ReactAgent (`run_turn_scoped`). Reuses gate /
        resolve_address / verdict tree / NLU. Conversation state still in the
        engine; migrating it into the typed graph state + LangSmith debug are later
        refinements.

**Kept unchanged:** the verdict tree, `resolve_address` (now a slot validator), the
10-tool registry (becomes the Diagnosis node's tools), the Tracer (extended per
node), the seed world, the 259-test suite.

**Deferred to Phase 5 (realtime/telephony):** async generator + token streaming,
fast-path / slow-path split (real-time media vs async brain), AEC + barge-in, real
slow-DB async.

**Done:** identification runs as deterministic slot-filling behind a tool-access
gate; LangGraph orchestrates the nodes over typed state; the trace bugs (overwritten
address, hallucinated id, premature diagnosis) are gone; a new fault type is content
+ a diagnosis strategy, not a core change.

---

## Phase 3.6 — Resolution engine: step-by-step fault solving · *(done, PRs #44–#45 + `feat/thinking-engine`)*

Voice testing after 3.5 showed the agent could identify but not *solve* well: it
dumped whole playbooks, looped tool calls, closed on the caller's word, and never
hung up. Built a universal **step walker** — the engine owns the procedure, the LLM
only understands and phrases.

- [x] **Strategy registry + step walker** — a verdict maps to an ordered `Step` list
      (CONFIRM / INSTRUCT / ACTION / VERIFY / ESCALATE). Per-step tool scoping (a
      CONFIRM exposes NO tools), per-step RAG section injection (one `### Žingsnis`
      at a time), deterministic advancement. Adding a fault = registry entry + RAG doc
      (`docs/PLETIMAS_GEDIMAI.md` is the recipe); a purely linear fault needs only the
      doc (`build_linear_strategy`).
- [x] **Engine-driven actions + telemetry verify** — `ensure_diagnosed`,
      `ensure_action_done` (bind/reset run by the engine, never the model → no
      single-tool loops), verdict re-read after every action. Truth comes from
      telemetry, not the caller's word.
- [x] **Declarative branching** — `Step.detector` + `on` routing keys with a
      `DETECTORS` registry (yes_no / restored / scope / conn / port / lights /
      have_device); `goto` for converging instruct chains.
- [x] **Three fault directions on the walker** — `foreign_mac` (cable by port
      FUNCTION → bind → verify), `healthy_to_router` (client side: all/phone/computer,
      device-aware so a phone is never asked about cables, caller-verified since
      telemetry is blind), `no_mac_observed` (dead router → power/cable → **B-Plan
      bridge**: wall cable into a PC + bind = temporary internet; closes Phase 2.5
      step 6).
- [x] **Hypothesis rejection + rethink** — a fix that does not restore the line
      records the cause in `failed_hypotheses`, re-diagnoses, and switches strategy if
      the telemetry now points elsewhere; the agent says the rethink out loud instead
      of silently restarting. Only escalates when there is no Plan B.
- [x] **Clean call ending** — offer "ar dar kuo nors padėti?", end on a farewell (or
      any agent goodbye, on every path), then `CloseStream` actually drops the WebRTC
      connection (a real hang-up).
- [x] **Identification polish** — the phone's registered address offered up front,
      ONE confirm then straight to diagnosis, and the apartment is never filled in
      from the DB (enforced in `resolve_address`, not the prompt).
- [x] **Dialogue quality** — "neišgirdau" only for real silence, otherwise reflect
      what was heard and name what was unclear; `clarity_level` switches to plain,
      visual wording once the caller says they do not follow the jargon.

---

## Phase 3.7 — Conversational contract: listen, wait, think aloud · `feat/thinking-engine`

**Goal:** the same helpful, unhurried consultation in EVERY fault. Voice testing
showed the walker is correct but the *conversation* is not: the agent runs ahead of
the caller, repeats itself when a turn is not a plain answer, and jumps to a verdict
without saying what it sees or what a result means.

> **Why structurally:** a caller's turn currently has only two fates — recognised
> (advance) or not (repeat). "Einu prie routerio", "nesuprantu", "o kiek kainuos?"
> and silence all collapse into "repeat the question". Two layers are missing between
> "the caller spoke" and "the step moves": what KIND of turn this was, and what the
> engine is WAITING for. Everything below falls out of those two.

- [x] **1. `awaiting` state + turn-intent classifier** *(the foundation)* —
      `state.awaiting` = `None | client_answer | client_action | system_check` (+ since
      when); `detect_turn_intent` → `answer · in_progress · done · question · confused
      · silence · new_info`. Only `answer`/`done` advance the walker; the rest hold.
      Classification stays deterministic (like the detectors), phrasing stays with the
      LLM; the safe default on "unknown" is WAIT and ask, never run ahead.
      *(Built during 3.8: `state.awaiting`, `detect_turn_intent`, `_turn_may_advance`
      + the LLM step-classifier on top.)*
- [x] **2. "darysiu" ≠ "padariau"** — "einu / atsinešiu / tuoj" is work in progress,
      not completion: acknowledge and wait, and do NOT read telemetry yet (observed:
      the bridge checked the line before the caller had plugged anything in).
      *(Built: INTENT_IN_PROGRESS holds; INSTRUCT classifier separates done/waiting.)*
- [x] **3. Hypothesis object** — `state.hypothesis {cause, because[], status,
      settled_by}` + `rejected[]`, filled at the three points that already compute it
      (diagnose → step outcome → telemetry after an action). The verdict tree stays
      the SOURCE; the object mirrors it so the agent can narrate the whole arc,
      including **confirmation** ("taigi dėl routerio ir nebuvo interneto") — today we
      track only rejection. No candidate queue: ordering stays with the tree, not the
      model. *(Built during 3.8: `hypothesis` + `failed_hypotheses` + `pivoted_from`.)*
- [x] **4. Narration contract in ONE place** — always-rules in
      `prompts/partials/solving.md` (explain before asking · say what each result
      MEANS · share what you checked/did and where you see the problem · voice
      hypothesis changes aloud · ask ONE thing then STOP and wait · reflect the
      caller's answer before moving on). Step hints keep only CONTENT; tone comes
      from the contract. *(feat/turn-taking-rail.)*
- [x] **5. Progressive disclosure** — `intent = confused` drops to a FINER breakdown
      of the same step (distinct from `clarity_level`, which changes the wording, not
      the number of steps). *(Built: `step_confusions` + clarity_level.)*
- [x] **6. Turn-taking rail (2026-07-28, from live calls)** — the step advances ONLY
      after ITS question was actually posed and answered: stale "patvirtink adresą"
      hint neutralized on identification (the activation reply states the FINDING +
      the first step's question, never re-asks the address); deterministic INFORM
      close (`_maybe_close_inform`) — outage/billing calls end on the caller's
      farewell instead of looping goodbyes / re-narrating the outage.

**Falls out for free:** silence handling and "kur jūs dabar?" come from 1; the
`system_check` wait is the socket Phase 5's async telemetry polling plugs into.

**Done:** the agent explains what it sees before asking, waits for the caller to
actually act, says what every result means, and consults the same way in every fault.

---

## Phase 3.8 — Thinking agent on rails: perceive → solve → act · `feat/thinking-agent`

**Goal:** move the diagnostic *reasoning* out of hardcoded Python (verdict tree +
`Step` walker + keyword detectors) into an editable knowledge layer driven by ONE
decision-maker, WITHOUT losing determinism/safety. The engine constrains the ACTION
space (allowed actions + guardrails); it no longer dictates HOW the agent thinks.

> **Why:** voice traces showed the walker is a decision-tree executor with narration,
> not a thinking agent. Two independent readers (keyword detector + narrating LLM)
> DESYNC — an undetected "yes" freezes the step while the model drifts ahead, then a
> later "no" misroutes to escalate (trace `20260721-142904`). The hypothesis is a
> *mirror* of the verdict, so the agent cannot revise its belief from dialogue or
> catch a telemetry↔client contradiction (the "no lights / wrong device" bug,
> `20260721-143433`). Root cause = architecture, not prompt.

> **Design docs (the full spec):**
> - `docs/ARCHITEKTUROS_LINIJA.md` — the frozen / policy / knowledge line (every
>   element sorted).
> - `docs/ARCHITEKTUROS_SCHEMA.md` — current (decision-tree executor) vs. proposed
>   (perceive → solve → act loop) flow.
> - `docs/MASTANTIS_AGENTAS_SPEC.md` — full contract: classifier output, solver JSON
>   schema, allowed `next_action` enum, gate validation + bailout, conflict matrix,
>   transparency/bridging rules, migration + eval.

**Principles (locked):**
- **Determinism bounds ACTIONS, not THINKING.** 🔒 mechanism (tools, telemetry read,
  guardrail enforcement, safety-action execution) · ⚙️ policy (`policy.yaml`: auth,
  tool-scoping, thresholds) · 📚 knowledge (RAG/prompts: interpretation, playbooks,
  conflict matrix).
- **Cognitive divergence, action convergence.** `current_hypothesis` = free string
  (may exceed the verdict-tree vocabulary — e.g. "looking at the ONT, not the router");
  `next_action` = strict enum. The gate validates only the action; an unknown
  hypothesis reaching a safety tool is REJECTED without a mapping.
- **Single decision-maker.** Classifier = sensor (returns a `Candidate Observation`,
  never writes state); solver = the only decider (structured output); narrator =
  executor (phrases the decided step, prompt-isolated). No two readers → no desync.
- **Verdict tree stays 🔒 as a *candidate cause + confidence* provider (a strong
  prior), NOT the final word.** The solver may confirm / refine / override it from
  dialogue. Interpretation-as-final-decision moves to 📚.
- **Safety unchanged.** MAC bind / ticket / close are executed by code; the LLM only
  proposes. Auth gate + apartment-never-from-DB enforced in code.

**Build order:**  *(steps 0–4 done on `feat/thinking-engine`; 476 unit + eval 16/16)*
- [x] **0. Eval harness (PREREQUISITE — no reasoning change lands before this).**
  Two levels: (a) **Golden Dataset** — the 9 scripted scenarios (`docs/TESTAVIMO_SCENARIJUS.md`)
  + the found bugs as fixed regression scenarios, driven text-to-text through
  `AgentSession`, hard-scored (verdict / action / step reached). Runs in seconds,
  deterministic, on every `.md`/code change. (b) **LLM-actor (fuzzing)** — an LLM plays
  a persona ("irate senior, non-standard Lithuanian, mislabels the lights") to surface
  new phrasings; findings become new Golden scenarios; LLM-as-judge for contract
  adherence.
- [x] **1. Classifier node (perceive)** — client text → `Candidate Observation`
  `{candidate_observation, intent, internally_inconsistent, confidence}`; contextual
  (told the expected answer space); does NOT write state. Same Claude (variant A;
  Haiku classifier possible later). Keyword detectors kept as a fallback on classifier
  failure.
- [x] **2. Solver node (decide)** — reads knowledge (interpretation + playbooks +
  conflict matrix) + hypothesis + observation + telemetry/prior; emits the strict JSON
  (`current_hypothesis`, `confidence`, `conflict_detected`, `hypothesis_changed`,
  `reason_for_change`, `next_action`, `playbook_step`, `narrator_instruction`).
- [x] **3. Gate (validate + safeguard)** — Pydantic schema validation; action-enum
  check; unknown-hypothesis-to-safety-tool rejection; safety actions executed by code;
  **bailout counter** (`confidence < 0.4` ×3 OR `cycles_in_same_step > 3` → generic
  ticket). Thresholds in ⚙️ `policy.yaml`.
- [x] **4. Narrator transparency/bridging (📚, buildable now)** — `hypothesis_changed`
  → mandatory one-sentence explanation; explicit transition (never ask B without
  resolving A); direction-NEUTRAL fillers only before the decision. Conflict matrix
  with **fact authority** (telemetry wins for line/session facts; client wins for
  physical-room facts).
- [~] **5. Shadow mode on ONE direction (dead router / bridge)** — shadow BUILT (solver+gate log alongside the walker via SOLVER_SHADOW); cut-over in progress. — splitter: walker
  (master) answers the caller; solver (shadow) decides in parallel, logged as a
  `shadow_decision` event in the existing `JsonlFileTracer` (not BigQuery). Cut-over
  when 100 real calls show 0 safety violations + auto agreement measured, with
  human/judge review of the disagreements (the valuable signal).
  - [x] **5a. Solver DRIVES one direction** (behind `SOLVER_DRIVE`, dead-router first):
        the solver reads the playbook + dialogue + telemetry, decides next_action, the gate
        validates + executes safety actions by code, the narrator speaks
        `narrator_instruction`. Walker stays default + for all other directions.
        *Mechanism done + measured (eval `tool_used`); decision-quality tuning (reliably
        reach propose_fix, less disambiguate) is ongoing — see Phase 3.9.*
  - [x] **5b. Detection semantics INTO the knowledge** — each step's `answers` in
        `knowledge/faults.yaml` give the classifier what to detect; `DETECTOR_GLOSSES`
        is the fallback. Equivalence-guarded.
  - [~] **5c. Purpose + procedure + signals per fault** — PURPOSE (`problems.triggers`)
        and the full PROCEDURE (`faults.<v>.steps`) now come from the manifest
        (`get_strategy` / `classify_problem` read it, code is fallback). **Still code:**
        WHICH signals to gather (`verdict.gather_signals`) and the telemetry→cause
        interpretation (`verdict.decide`) — needed only when a NEW fault needs new signals,
        so deferred behind Phase 3.9.
  - [~] **5d. Identification as knowledge** — the procedure wording is already a file
        (`prompts/partials/identification.md`); the DIRECTION knobs now live in
        `agent/knowledge/identification.yaml` (`identification.py` loader, fail-soft):
        `offer_phone_address`, `require_apartment`, and `extra_questions` — so adding an
        extra verification question (e.g. the caller's name) is a file edit (it injects a
        guidance line). Defaults = today's behaviour (eval 16/16, no regression). GUARDS
        stay code: identity gate, "apartment never from the DB", street-must-match.
        **Decision (2026-07): the caller's name is NOT verified.** We serve the contract
        holder AND family / tenants / a neighbour or friend helping out, and we make no
        contract changes, so a name mismatch is expected and fine — no name-match guard
        (that would wrongly reject legitimate callers). The name is captured into
        `state.caller_name` (distinct from the account `customer_name`) purely for the call
        record / history — wired in Phase 3.10, never compared. (Optional later: move the
        procedure prose into structured steps for per-step editing.)
  - [ ] **5e. Call-flow policy — separate conversation ORDER from action gating.** Today
        `graph.route()` hard-codes identify-first because diagnosis needs identity. Split
        the two: the router reads a declarative flow (`policy.yaml` / per-problem) —
        `identify: before_diagnosis | at_action | none` — so the agent can go PROBLEM-FIRST
        (understand + classify, discuss causes) and ask for identity only WHEN a technical
        action needs it. The safety FLOOR is unchanged and stays code: the gate still blocks
        every diagnostic/mutation tool until identity is verified, and "apartment never from
        the DB" holds — the policy only reorders the CONVERSATION, never relaxes a guard.
        Enables: problem-first flow, per-problem identity depth (billing vs a technical
        fault), extra verification questions (name) declared alongside 5d.

  **Target artefacts (the "no code for a new fault" contract):**
  - `agent/faults/faults.yaml` — per fault: `id`, `purpose_triggers`, `playbook` (the RAG
    doc), `steps` (each with its routing keys + plain-language MEANING = what to detect),
    `signals` to gather, `allowed_actions`.
  - `rag/knowledge_base/troubleshooting/<fault>.md` — the WORDING (`### Žingsnis N`).
  - `policy.yaml` — who may be served, thresholds, per-stage tools.
  - **Stays code:** tool implementations, telemetry reads, the gate//guard ENFORCEMENT,
    executing bind/ticket/close. Knowledge says WHAT to do; code guarantees what CANNOT be
    done. A new fault = a manifest entry + a playbook + seed + an eval scenario; a new
    physical capability (e.g. a speed test) still adds a tool once.
- [ ] **6. Widen** — cut over the remaining directions one fault at a time; retire the
  walker steps for each as it goes. **North star: a UNIVERSAL solver that resolves any
  fault exactly as the RAG domain knowledge instructs — the algorithm and the checks live
  in the playbook, the engine only enforces safety + executes.**

---

## Phase 3.9 — Perfect ONE fault as the universal template ("nėra interneto")

**Decision (2026-07):** do NOT add new faults yet. Make the single "no internet" fault
resolve *flawlessly and entirely from the engine* first, so a new fault is genuinely just
"plug new files onto a proven engine". Widening (step 6, slow-internet, TV…) comes after.

**What "perfect" means (acceptance):**
- Every no-internet direction resolves correctly: `foreign_mac`, `healthy_to_router`,
  `no_mac_observed` (+ bridge), and the inform paths (billing, outage, link-down).
- Robust to REAL messy speech, not just clean scripted turns (STT noise, mixed intent,
  the caller jumping ahead).
- Actions actually RUN (bind / reset / ticket / close), measured by `tool_used` — no
  "said it, didn't do it".
- The same unhurried, human consultation in every direction (contract + bridging).

**Plan (ordered):**
- [x] **A. Fuzzing eval (LLM-actor).** `agent/eval/fuzz.py` — an LLM plays personas from
      `fuzz_personas.json` over each no-internet direction. **Findings:** client-side and
      foreign_mac are ROBUST under messy speech; only **dead-router / bridge is fragile** —
      two paths to the same failure (the bridge never binds, `update_mac` never runs):
      (1) an INSTRUCT step freezes on a messy done-signal ("Gerai, jau įkišau" read as
      in_progress by the keyword turn-intent — the classifier fix covered CONFIRM only);
      (2) on digression / a half-said "registruokit" the agent ESCALATES to a ticket
      without offering the bridge though the caller has a computer. Positive: the
      telemetry↔caller re-confirm (#8) works and self-correction works. Infra: 30/min rate
      limit corrupts multi-persona runs — actor retries, but proper fuzzing needs a higher
      limit or pacing.
- [x] **B. Fix what fuzzing found** — dead-router/bridge, both root causes:
      (1) INSTRUCT-step advancement is now classifier-aware, so a messy "jau įkišau"
      advances instead of freezing dr_plug_pc (`_classify_instruct_and_advance`); (2) the
      real #2 was dr_intro escalating on a messy/engaged reply misread as `no` — sharpened
      its answer meanings in faults.yaml so engagement → hold/proceed and only a CLEAR
      decline → escalate (a FILE edit). Eval 16/16, S4 binds reliably. Contract #9/#10
      (refocus, temporal contradiction) still open — fold into C as fuzzing surfaces them.
- [ ] **C. Solver-drive to reliable** — reach `propose_fix` reliably, stop lingering on
      `disambiguate`; extend the pilot to the other no-internet directions once each passes
      the fuzzing eval in shadow. Decide walker-retirement per direction on the numbers.
- [ ] **D. (Enables widening) interpretation + signals → knowledge** — move
      `verdict.gather_signals` (which signals) and `verdict.decide` (telemetry→cause) behind
      the manifest, so the LAST code-bound pieces of a fault definition become files. Only
      needed to make step 6 "files only"; do it once no-internet is solid.

**Done:** the no-internet fault is reliable end-to-end from files on the engine; adding the
next fault touches only `faults.yaml` + a playbook + seed + an eval scenario.

---

## Phase 3.10 — Call outcomes: structured ticket + call record from STATE

**Why now (structural):** as the engine matures, capture the OUTCOME of every call so we can
build client history, reports, improve the agent, and diagnose faults faster. The key
insight: the outcome is already in STATE — `problem_type` (why they called), `resolution`
/ `hypothesis` (the cause determined + which side, provider/client), the trace's tool_calls
(what was done), `closed_reason` (resolved / ticket / inform / declined). So both artefacts
below are built DETERMINISTICALLY from state, not from LLM free text.

- [x] **Ticket from state, not free text.** `_register_ticket_from_state` (Phase 3.11 B):
      cause from hypothesis/verdict, actions from this call's trace, type technician_visit
      — never the model's wording. The engine registers it at the ESCALATE outcome.
- [x] **Persist a call record at session_end.** The `conversations` table already exists
      (`session_id, customer_id, messages, outcome, summary, ticket_id, duration_seconds`) —
      write a structured summary there when the call ends: {purpose, cause + side,
      actions taken, resolved? / why not, ticket_id, **caller_name** if asked}. Emit a
      `call_summary` trace event too. The caller's name (state.caller_name — who was on the
      phone, not the account holder) is recorded here, never used to gate identity.
      - [x] **Slice 1a — structured `call_summary` trace event.** `end_session` now builds
            the summary DETERMINISTICALLY from state (`_build_call_summary`) and emits it
            before `session_end`: purpose, cause, side, outcome, resolved?, ticket_id,
            caller_name, and `actions` (tool names harvested from this call's own trace via
            `_tools_called_this_session`). Rendered in the .txt export; tested (test_tracing).
      - [x] **Slice 1b — persist to the `conversations` table.** CRM adapter
            `crm_mcp.tools.conversations.save_conversation` + `tools.save_call_record` wrapper;
            `end_session._persist_call_record` writes one row (summary JSON + transcript +
            outcome + ticket_id), keyed by session. Dangling customer/ticket FKs are stored
            NULL rather than dropping the record; best-effort so a DB failure never breaks
            teardown. Tested (row written end-to-end + FK-drop; test_tracing).
- [ ] **(Later) reporting / history surface** — per-customer call history and aggregate
      reports off the call records; feeds agent improvement and faster repeat-fault diagnosis.

**Ticketing is a CALL-ENDING outcome, in ONE node (design decision 2026-07).** A ticket is
never created mid-troubleshooting — it is always part of wrapping up: either "couldn't
solve → ticket + close" or "solved temporarily → follow-up ticket + close" (the bridge).
So:
- Strategies/diagnosis only DECIDE the outcome into state (`resolved` / `cant_solve` +
  reason / `provider_fault` / `inform`); they do NOT create the ticket.
- A single OUTCOME/closing node reads the outcome and, when needed, registers the ticket
  DETERMINISTICALLY from state, then closes. `create_ticket` stops being an LLM-callable
  tool mid-strategy — which also removes the premature/freelance-ticket failure (3.9 B #2).
- A provider-side fault diagnosed with no resolution to attempt goes straight to this node
  (ticket or inform, then close).
- **(Later) ticket-confirmation dialogue:** collecting/confirming details with the caller
  before filing is its own small dialogue, added when we refine ticket registration;
  keep the outcome node ready for it. MUST collect (2026-07-29): **contact phone to
  reach the person** — the caller may be on a company phone, a private number, or the
  DB number may be outdated, so always ASK, never assume caller-ID/DB; **contact
  person** (who to talk to — may differ from the account holder); **what the problem
  is** (short, from state); and a **comment** with when they can be called (hours) and
  any extra notes.

**Boundary:** the summary/ticket builder is deterministic 🔒 (reads state); the summary
WORDING template is 📚. No new call reasoning — it only RECORDS what the engine already
knows. Infra mostly exists (table + state fields); this wires it at the session seam.

**Design note for the ongoing migration:** keep `problem_type`, `hypothesis`/`resolution`
and `closed_reason` clean and complete in STATE — they are the single source for both the
ticket and the call record. Anything moved to knowledge must still leave the OUTCOME
legible in state.

**Deferred dependencies (follow-up, not blocking):** async telemetry (<150 ms) +
mid-turn TTS filler for the "speak-then-fetch" latency mask; `TRANSFER_TO_HUMAN`
(only `create_ticket` exists now); variant B (merge solver+narrator) only if latency
demands it.

**Done:** the diagnostic reasoning is editable knowledge behind one decision-maker;
desync is structurally impossible; the agent revises its hypothesis from dialogue and
catches telemetry↔client contradictions; safety and testability are preserved via the
gate + eval harness.

---

## Phase 3.11 — Pre-Phase-5 readiness: natural dialogue (kelias į Phase 5)

**Goal (2026-07-28, from live testing):** the agent should work like a human
consultant — listen first, understand the problem, solve step by step (already in
place after the turn-taking rail), AND: speak short, stop when interrupted, fill
waiting time with useful questions. This is the list to finish "daugmaž viską"
before Phase 5 (async + telephony).

- [x] **A. Short voice replies.** reply_len auto-check in the Golden eval (max ≤ 280
      chars, avg ≤ 160 per scenario) + dr_intro trimmed to two sentences (no cause
      enumeration). Long replies were also the main TTS latency cost (5–8 s per turn
      observed) — shorter replies cut latency for free.
- [x] **B. 3.10 outcome node.** ESCALATE is a deterministic OUTCOME: the ENGINE
      registers the ticket from STATE on the caller's consent (consent → registered,
      decline → closed without a ticket, unclear → re-ask); create_ticket removed from
      the model's tools mid-strategy. PLUS scope split for any answer order (cs_scope →
      all / one→cs_which / named device→cs_cross_* cross-check) — the classifier never
      guesses a device again.
- [x] **C. Anamnesis during waits.** The bind announce (foreign_mac bind_mac +
      dead-router dr_bind) carries ONE history question in the same utterance ("O kol
      laukiam — kada pastebėjote, kad dingo internetas?"). Full version rides Phase 5
      async telemetry.
- [ ] **D. 3.8 leftovers on the universal-agent track** *(parallel, not blocking)* —
      solver cut-over on dead-router (5/6), signals→knowledge (D). Phase 5 does not
      depend on these, but they continue the "universal thinking agent" line.

### Operating philosophy (2026-08-03, Andrius): after-hours helper, humans take over via tickets

The agent SOLVES only what the knowledge describes; everything else ends HONESTLY:
- provider-side fault -> ticket immediately;
- described fault, attempt failed -> ticket with WHAT was tried + the hypotheses
  (Bandyta/atmesta on the ticket details);
- UNDESCRIBED fault -> no invented procedures: tell the caller this is beyond what
  can be solved right now, register a ticket marked as an unknown fault. (Routing for
  unknown faults to be added when the first such flows are defined.)
A farewell mid-process is a signal to CLARIFY ("ar tikrai norite baigti? galiu
užregistruoti"), never a hang-up trigger; deterministic closes only after the
business is done (news delivered / resolved / registered).

### Block architecture (agreed 2026-07-31): identifikavimas | supratimas | sprendimas + mąstytojas

The agent is three BLOCKS joined by the THINKER (solver): IDENTIFIKAVIMAS returns an
identified customer; PROBLEMOS SUPRATIMAS builds the ANALYSIS (telemetry + what the
CALLER said — anamnesis); PROBLEMOS SPRENDIMAS walks the strategy to a fix or a
registration. The mąstytojas decides the transitions and owns the hypothesis.

- [x] **Step 1 — separate identification from diagnosis (arc v3).** The engine
      diagnoses silently right after the identity commits (state-only); the same reply
      narrates "Patikrinsiu būseną šiuo adresu… Patikrinau: [rezultatas]" — one reply,
      no dead-air ack turn, no deferred-finding vacuum (a hidden finding made the model
      hallucinate a router story for a debtor). Dictated correction addresses are
      accepted directly (echo + resolve, no extra confirm round). When Phase 5 async
      telemetry lands, announce and result naturally split into two real turns.
- [x] **Step 2 — the ANALYSIS object.** nlu.extract_anamnesis reads the intake
      answer into {when, trigger, "nežino"}; state carries anamnesis_raw/when/trigger;
      the hypothesis `because` cites BOTH sides ("telemetrija rodo X; klientas sako
      dingo šiandien, po: audra"); the call summary and the ticket carry the
      anamnesis ("Klientas: dingo vakar, po: audra").
- [x] **Step 3 — the mąstytojas joins the blocks (first direction live).**
      SOLVER_DRIVE is ON by default: the solver drives the dead-router direction
      (S4 eval: 8/9 diagnosis turns solver-driven, gate-bounded), reasoning over the
      FULL ANALYSIS (hypothesis + anamnesis + symptoms + caller + telemetry). It
      NEVER overrides the deterministic mechanics — the identification ladder, the
      clarify contract and the wrap-up stay engine-owned; the graph router remains
      the backstop (SOLVER_DRIVE=off reverts). Next: widen direction by direction
      (3.8 #6).

**Done:** short, natural turns; every call ends deterministically; waiting time is
used for anamnesis; ready to lift the engine onto Phase 4/5 async infrastructure.

---

## Phase 4 — Service & frontend · `feat/api-service` (agreed 2026-08-04)

The FastAPI host is the foundation Phase 5 builds on: the engine goes behind an
HTTP/WS boundary now, so async/telephony later change the INTERNALS, not the
contract. Testing scope for now: ONE call at a time (multi-call is structural —
the session registry isolates sessions — but scale, hosting and shared-resource
limits are deliberately re-thought later; see notes below).

**PR1 — foundation (text vertical):**
- [ ] `chatbot_core/src/app/` skeleton (per Target structure §4): FastAPI app
      factory, pydantic-settings config
      (model keys, DB paths, feature flags like SOLVER_DRIVE — today scattered
      through env), `/health`, uvicorn entry, launch.json config.
- [ ] Session manager: `session_id → AgentSession` (graph engine) registry —
      create / get / end, TTL cleanup for forgotten sessions, a per-session lock
      so concurrent turns on one session cannot interleave. API async from day
      one; the engine stays sync inside (Phase 5 swaps the inside only).
- [ ] Tracer event-bus: every event the engine already emits (`node`,
      `tool_call/result` + ms, `rag`, `decision`, `scripted`, `llm`
      tokens/latency, `voice_latency`) is ALSO broadcast live to WS subscribers,
      plus a per-turn `turn_summary` JSON (node, tools, tokens, cost, latency).
      The jsonl trace file stays the archive format — one source of truth.
- [ ] Text dialogue API: `POST /sessions` → `{session_id, greeting}`;
      `POST /sessions/{id}/turns {text}` → `{reply, state}` (+ SSE token
      stream); `DELETE /sessions/{id}` → end + call record.
- [ ] `/ws/call/{session_id}`: typed messages — JSON = events, binary = audio
      (audio lands in PR2); events channel live from PR1.
- [ ] Tests: httpx lifecycle, turns, event stream, N concurrent sessions
      (structural check only).

**PR2 — voice + demo dashboard v1:**
- [ ] Audio over the same WS: browser mic → VAD/STT → turn → TTS → audio back,
      reusing `voice_pipeline` adapters; the local voice demo becomes an API
      client instead of in-process.
- [ ] Call audio recording (WAV per call next to the trace jsonl) — needed for
      the archive zone.
- [ ] `index.html` dashboard (single page, Tailwind + Web Audio API, served by
      FastAPI — no build step): left = live transcript (STT/TTS), right = agent
      "brain" (active LangGraph node, tool calls with ms, active RAG section,
      tokens + call cost USD, latency incl. TTFT, ENGINE-vs-LLM indicator per
      turn from `scripted`/`decision` events).
- [ ] Honest latency: half-duplex until Phase 5 (no barge-in/AEC yet); the
      dashboard SHOWS the real STT→LLM→TTS numbers — that is the Phase 5 pitch.

**PR3 — archive & analytics:**
- [ ] Past-call list (conversations table), full trace viewer, audio playback,
      cost summary per call, JSON export (PDF later, cosmetics).

**Vision (target demo, build incrementally — not all at once):** three-zone
screen — live conversation | agent internals | history/analytics; single
bidirectional WS carrying audio + events; business pitch = no hallucinations
(deterministic-engine indicator), transparent cost, latency clock, full audit
trail.

**Deferred within Phase 4 (agreed):**
- Config-page ADMIN AUTH (Andrius 2026-08-06): model switching and setting
  changes are a sensitive surface — before the demo is HOSTED anywhere
  public, /admin/* and the config page must sit behind authorized-admin
  login. Decide together with the hosting setup (Phase 5/7 boundary).
- Auth, DB-backed session persistence, horizontal scaling — Phase 7.
- Multi-call SCALE: sync engine threads, shared Groq classifier rate limit
  (30/min across all calls), SQLite write contention (WAL), local STT/TTS
  CPU/GPU sharing (~2–3 voice calls realistically) + WHERE to host — re-think
  as its own step alongside Phase 5 async.

**Done when:** a call runs end-to-end through FastAPI (browser client), the
brain panel streams live events, Streamlit demoted to debug-only.

---

## Phase 4.5 — Analizės variklis: evidence ledger (spec agreed 2026-08-05)

The agent's core skill: extract the SAME required information while ADAPTING
the conversation to the caller's level. Position in the flow = what is KNOWN,
not which step number — a benched solver can then never rewind a call
(observed live: bailout at dr_offer_bridge rewound the walker to dr_intro and
re-asked lights/power/cable the caller had already done).

**Design (three layers):**
- **Evidence ledger (`state.evidence`)** — facts with SOURCE and history.
  Telemetry facts (from tools: line_to_flat, mac_observed, port…) are ground
  truth — words never overwrite them; client facts cover only what telemetry
  cannot see (lights, cables, devices at home). Conflicting client answers
  append + flag (never silently overwrite) → deterministic clarify quoting
  both ("sakėte X, dabar Y — kaip yra iš tiesų?"). Client-vs-telemetry
  conflict: telemetry wins, said politely.
- **Fault description in faults.yaml** = diagnosis criteria (telemetry +
  client evidence needed, per-line "what must be established"), confirm rule,
  and solution paths. One file block per fault — adding a fault is a file
  edit. Unclear-cause faults (no clear evidence either way) — separate branch
  later; honest ticket with everything collected.
- **Extraction pass** — one small-prompt LLM call per caller turn (diagnosis
  stage only, v1): input = ledger + missing evidence + utterance; output =
  extracted facts + contradictions. Sees the whole conversation, so info
  offered out-of-order still lands. CONSOLIDATES the per-detector classifiers
  (yes_no, lights, instruct_done…) — net LLM-call count stays ~flat.

**Invariant vs adaptation:** WHAT to establish is fixed (file); HOW to ask
adapts to the caller (LLM narrator + clarity levels per evidence item:
"patikrinkite maitinimą" → "juodas laidas apvaliu antgaliu į rozetę…").
Conversations differ; the ledger does not.

**findings node:** when the ledger confirms/refutes the hypothesis, the graph
enters a findings node — engine decides WHEN and supplies WHAT (checked facts,
assumption, solution options, what we cannot do now); the LLM words it (small
prompt, no scripted sentence). Guards keep it honest ("užregistravau" without
ticket_id is impossible; nothing outside FINDINGS can be said). Scripted
replies remain ONLY for mechanical commits (address confirm, ticket contact
questions).

**One-way doors:** hypothesis confirmed → solutions only (bridge if a device
exists, else ticket). Questions are generated from MISSING evidence, so
"going back" has nothing to go back to.

**Quick fixes shipped ahead of the ledger (2026-08-05):**
- [x] "No device" after the bridge offer → deterministic escalate (engine
      rule; the thinker is not consulted)
- [x] Registration-claim guard: a narrated "užregistravau" with no ticket
      starts the REAL contact dialogue on the same reply
- [x] Hang-up safety net: session end mid-strategy with no ticket registers
      one from state ("Pokalbis nutrūko" on the record, caller-ID contact)

**Steps:**
- [ ] Ledger v1 on no_mac_observed: state.evidence + extraction call +
      conflict clarify + questions from missing evidence (rewind class dies)
- [ ] findings node + guards
- [ ] Generalize: evidence blocks for all faults.yaml faults; retire
      per-detector classifiers where extraction covers them
- [ ] Clarity levels per evidence item (adaptation ladder in the file)

---

## Phase 4.6 — Skriptas → mąstymas: naratoriaus laisvinimo pakopos (aptarta 2026-08-12)

Po 7 „hearing agent" ratų mechanika stabili, bet Andriaus diagnozė taikli:
„agentas kalba tai, kas jam buvo nurodyta, bet negali pats išanalizuoti, ką
žmogus pasakė". Beveik kiekvienas scripted gabalas — randas po konkrečios
gyvos avarijos (haliucinuoti tiketai, per ankstyvas bind), tad determinizmas
buvo sąmoninga kaina. Grąžinam LLM'ui vairo palaipsniui, kiekvieną pakopą
tikrinant balsu + eval'u:

- [ ] **A. Naratoriaus formuluojami klausimai** — variklis sprendžia KĄ
      klausti (ledger'io raktas — šventa), LLM formuluoja KAIP pagal kontekstą
      ir kliento kalbėseną; yaml tekstas lieka atsarga (LLM klaidos atveju) ir
      prasmės inkaras. Taikoma ir suvestinei („Pasitikslinu…") bei išvados
      paskelbimui. Tikslas: dingsta „to paties teksto kas skambutį" pojūtis.
- [ ] **B. Garsus mąstymas (išvados, ne tik faktai)** — po kiekvieno ledger'io
      įrašo naratorius įpareigojamas vienu sakiniu pasakyti IŠVADĄ: „kadangi
      kiti įrenginiai veikia, rozetė gera — lieka pats routeris". Apibendrina
      esamą kodel/isvada mechaniką iš faults.yaml.
- [ ] **C. Solver'io išlaisvinimas** *(diskusijai po A+B)* — platesnė veiksmų
      erdvė (gate'ai lieka: vienpusės durys, įrankiai, tiketai tik per variklį),
      „patikrinkime dar kartą" ramentas apribojamas biudžetu.
- [ ] **D. Mąstymo ciklas** *(diskusijai; už vėliavos, lyginamas eval'u)* —
      supratimo pass'as + solver'is sulydomi į vieną apmąstymo žingsnį kas
      ėjimą: „ką pasakė → kas iš to seka → ko trūksta → ką sakau" su
      struktūruotu išėjimu; deterministinis sluoksnis lieka grynai saugos
      tinklas. Kaina: +latencija, +tokenai — derinti su latencijos paketu.

Eiga: A+B po `feat/hearing-agent` merge → balso patikra, ar „skripto jausmas"
keičiasi → Andriaus klausimai apie agento struktūrą → sprendimas dėl C/D.

---

## Phase 5 — Realtime & telephony

- [ ] **Async conversation engine** — `run_until_response` → async generator;
      token streaming into the streaming TTS port (deferred here from Phase 3.5).
- [ ] **Fast-path / slow-path split** — real-time media loop (WebSocket STT/TTS)
      decoupled from the async LangGraph "brain" (event-driven). Needed for
      telephony; enables true overlap.
- [ ] **AEC + asymmetric barge-in filter** — acoustic echo cancellation so
      `can_interrupt` can be re-enabled without the agent cutting itself off
      (browser AEC alone proved insufficient — trace `20260618-092029`). On top of
      AEC, an **asymmetric barge-in filter**: a small local (ms) check classifies a
      detected interruption as a backchannel ("aha"/"taip"/"gerai" — short duration
      + LT affirmation list → keep talking) vs real new speech ("ne, ne tas
      adresas" → stop + full LangGraph switch). Start heuristic (duration +
      wordlist), not an ML classifier. Prereq: AEC.
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
- [ ] **Next:** Phase 3.5 · Conversation engine (`feat/conversation-engine`) —
      build order: (0) design doc `pokalbio_variklis.md`, (1.1) prompt-cache fix,
      (1.2) typed slots, (1.3) tool-access gate, (1.4) NLU extraction, (2) latency
      masking (filler + streaming TTS port), (3) LangGraph migration (nodes +
      MemorySaver). Async / fast-slow split / AEC deferred to Phase 5.
- [ ] **Next:** Phase 3.8 · Thinking agent on rails (`feat/thinking-agent`) —
      START with step 0, the **eval harness** (Golden Dataset from the 9 voice
      scenarios + found bugs, driven text-to-text through `AgentSession`, hard-scored),
      the prerequisite before any reasoning change. Design: `docs/MASTANTIS_AGENTAS_SPEC.md`
      (+ `ARCHITEKTUROS_LINIJA.md`, `ARCHITEKTUROS_SCHEMA.md`). Then classifier →
      solver → gate → narrator bridging → shadow mode on the dead-router direction.

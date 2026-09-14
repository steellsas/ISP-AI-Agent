# Architecture Decisions — single-engine refactor

> Agreed 2026-09-14 by the project owner (Andrius) in a design discussion.
> This file is the **"why"** behind [REFACTORING_PLAN.md](REFACTORING_PLAN.md).
> Every milestone file references decisions by id (`D-xx`). If a milestone
> seems to contradict a decision here, the decision wins — stop and ask the owner.

Format per decision: **Context** (the problem) → **Decision** → **Rejected** (alternatives
considered) → **Consequences** (what it forces in code).

---

## Part A — Engine architecture

### D-01 · LangGraph is the only engine; `ReactAgent` is removed

- **Context.** Two state holders exist: `ReactAgent` (`agent/react_agent.py`) owns the real
  state (`AgentState` + ~60 private `_flags`) and the LLM loop; the LangGraph v2 graph
  (`agent/graph_v2/`) is an orchestration shell whose `GraphState` is a copy refreshed by
  `runtime.sync_updates` after each node. Nothing reads state back from the checkpoint.
  Nodes call `engine.*` and touch private attributes, so nodes cannot be tested alone and
  "why did the agent do X" has no single answer.
- **Decision.** `GraphState` is the single source of truth. Nodes are functions
  `(state, runtime) -> partial update`. `ReactAgent`, `agent/graph.py`, `agent/state.py`
  and the `AGENT_ENGINE=graph|legacy` rollback paths are deleted.
- **Rejected.** Keeping `ReactAgent` as a facade (keeps dual state); keeping legacy engines
  for parity comparison (owner: delete).
- **Consequences.** Persistent flags become named `GraphState` fields, per-turn flags go to
  `TurnScratch`, live objects (LLM client, tools, tracer, config) go to runtime context —
  never into state. Parity testing against the old engine disappears → a replay/eval safety
  net must exist first (D-20).

### D-02 · One decision per turn: `TurnPlan` ("decide → act → speak")

- **Context.** Today decisions are scattered: pre-turn guards, solver, walker guard chain,
  and even the narrator (stuck backstop, scripted identification, wait-ack, speculation).
- **Decision.** Each turn runs `perceive → decide → execute → speak`. `decide` emits one
  `TurnPlan` object: **who owns the turn**, **which action** (tool / procedure step / none),
  **what to say** (see D-15), plus hypothesis status and the awaited answer.
  The narrator/speaker never decides.
- **Rejected.** Turning each of the ~15 guards into a graph edge (unreadable graph).
- **Consequences.** The guard chain becomes an ordered, pure `plan_turn` policy inside
  `decide`; `TurnPlan` is traced and shown in the dashboard (D-21). `decide` is unit-tested
  without LLM wording: "these facts in → this plan out".

### D-03 · One driver: solver + procedures

- **Context.** Packs choose a driver (`vairuotojas: solveris|walker`): 4 packs solver,
  2 packs walker. Two mental models, hard to explain and document.
- **Decision.** `decide` (the solver) is the only driver. The former walker becomes a
  **procedure runner**: when `decide` selects a phone-solvable solution, the procedure walks
  its steps deterministically; new evidence hands control back to `decide`, which may stop
  the procedure and change the hypothesis (under D-05).
- **Rejected.** Walker everywhere (an executor, not an engineer; needs a tree per branch);
  keeping both drivers.
- **Consequences.** `meta.vairuotojas` disappears from packs. Walker-only packs
  (`crc_errors`, `link_down_local`) get `evidence`/`decisions` blocks so `decide` can drive them.

### D-04 · Closed action set — no improvisation

- **Context.** The old roadmap described the LLM solver as "filling gaps". Owner: the agent
  solves only what it knows.
- **Decision.** `decide` may choose only: actions/solutions/procedures declared in knowledge
  files, plus the standard set `ask`, `inform`, `register_ticket`, `append_ticket`, `close`.
  The gate rejects anything else. No knowledge for a fault → ticket "unclear fault".
- **Consequences.** Solver output schema is an enum of known action ids; gate validates
  membership, consent (D-16) and policies (D-17).

### D-05 · Hypothesis stability

- **Context.** An engineer does not jump between hypotheses on one ambiguous remark.
- **Decision.** Explicit state machine per hypothesis:
  `ACTIVE → DOUBT → CONFIRMING → CHANGED | ACTIVE`.
  A contradiction (telemetry recheck, client statement, analyst signal) only moves to
  `DOUBT`. The agent then asks a confirmation question **quoting what the client said
  earlier** ("You said the WAN light was on — is it off now?"). Only a confirmed
  contradiction changes the hypothesis. Only `decide` changes it.
- **Consequences.** State keeps: active hypothesis + reason, status, the contradiction,
  what the client said before (quote), awaited answer, current procedure step. When the
  client drifts, the agent answers briefly and **returns to the point** (anchor).

### D-06 · Quiet context analyst = signals for `decide`

- **Context.** `agent/analyst.py` reads the whole conversation in a background thread
  (voice path only) and only shapes the narrator's wording.
- **Decision.** The analyst becomes part of the graph flow (text and voice), reads the full
  conversation and emits **signals**: contradiction with earlier statement, question already
  answered earlier, secondary problem mentioned, drifting off-topic, frustration.
  It never writes facts, never changes the hypothesis, never talks to the client. A signal
  can at most move the hypothesis to `DOUBT` (D-05).
- **Rejected.** Advisory-to-narrator only (too little); analyst writes facts (a background
  LLM error would become a "fact").
- **Consequences.** It may still run asynchronously for latency, but its output is a typed
  `signals` list in state consumed by the next `decide`.

---

## Part B — Facts, telemetry, identification

### D-07 · Telemetry beats client words — within its visible segment

- **Context.** Clients describe symptoms imprecisely; telemetry shows facts about the line.
- **Decision.** Telemetry is authoritative for what it sees (provider side → switch → port →
  line → router presence/traffic). The client is authoritative beyond the router
  (Wi-Fi, devices, cabling in the flat) and in time (intermittent problems, "yesterday
  evening"). Conflicts in telemetry's segment → telemetry wins, the agent clarifies gently.
- **Consequences.** Ledger rules keep "telemetry beats words"; docs state the boundary.

### D-08 · Telemetry early, in two levels, as one tool

- **Decision.** Right after confirmed identification:
  **level 1** (any intent): billing suspension, area outage, node/switch state, **open tickets**;
  **level 2** (per stated service problem): port/line/MAC/CRC/traffic.
  Missing information is asked afterwards — only what telemetry cannot know.
  Telemetry is one tool with modes `snapshot` (first picture) and `recheck` (verify a
  procedure step). Only `execute` calls it; results land in state as timestamped facts.
- **Consequences.** Today's scattered calls (`preflight_phone`, background diagnosis in
  `session.py`, `ensure_diagnosed`, walker rechecks) converge into this tool.

### D-09 · Identification gate

- **Context.** A phone number maps to an address, but the caller may call about another
  address; revealing account data to an unverified caller is a data leak.
- **Decision.** Before confirmed identification: listen to the problem and store it
  (intake), phone lookup yields only a **candidate**; **no telemetry, billing or account
  statements**. After confirmation: level-1 checks immediately, and do not re-ask what the
  client already said.
- **Exception handling for mass outages (option 2).** With a phone candidate the outage check
  may run **silently in the background**; nothing is said until identity is confirmed; then it
  is announced immediately. If the candidate is not confirmed, the result is discarded.
- **Consequences.** Current `PROACTIVE OUTAGE` behaviour
  (`narrator_flow.py` ~L517, `identification_flow.preflight_phone`) violates the gate and is
  changed. The outage contact is recorded against the confirmed customer/address.

### D-10 · Service profile comes from the customer's CRM plans

- **Decision.** After identification the agent loads a **service profile** (internet / TV /
  phone, and technology) from CRM plans. `decide` uses it: complaint about a service the
  client does not have → inform; dependency between problems; which telemetry to check.
  Dependency rules (e.g. IPTV depends on internet) are **knowledge in a file**, not code.
- **Consequences / data gap.** Demo DB `service_plans.service_type` has only
  `internet|tv|phone|bundle` — no technology (IPTV vs cable) and `bundle` hides its parts.
  A technology field is required (demo schema now; mandatory CRM field in integration docs).

---

## Part C — Call handling policies

### D-11 · Call intents catalog with policies

- **Decision.** Every call is classified into an intent from a catalog file (moved out of
  `faults.yaml`). Policies:

  | Policy | Behaviour |
  |---|---|
  | `solve` | identify → telemetry → decide → procedures (only if knowledge exists) |
  | `register` | identify → collect info → ticket with a **type** routed to the right department → "I registered your request, they will contact you" (billing, disconnection, service transfer/relocation, wishes) |
  | `answer` | identify → answer from data (ticket status, outage ETA, debt) |
  | `not_ours` | say we do not handle it (PC, other company) — no identification |
  | `chat` | warm reply + "how can I help?" |

  Known fault without knowledge → ticket "unclear fault". An identified customer can always
  get a ticket with a message.
- **Consequences / data gap.** Demo `tickets.ticket_type` lacks non-technical types; a
  ticket-type → department mapping belongs to integration docs.

### D-12 · Multiple problems in one call

- **Decision.** Dependent problems (IPTV over internet): fix the primary, then verify the
  dependent one recovered. Independent problems (TV on a separate cable): solve one after
  another. If a ticket is registered, **all** problems go into that one ticket.
  Repeat call with an **open ticket** → append to it (repeat call, what the client said:
  just checking / nobody came / new info) and tell the client its status. No duplicates.
- **Consequences.** New tool: append note to ticket. Open-ticket check is part of level-1.

### D-13 · Human handoff = ticket only

- **Decision.** No live transfer to an operator. Anything the agent cannot solve becomes a
  ticket and the client is told so.

### D-14 · Contact record for every call

- **Decision.** Every call produces a contact record via a **guaranteed finalizer at
  `AgentSession` level** (runs on hang-up, disconnect, error, TTL — not only on graph
  END). Fields: `customer_id` (nullable), `address_confirmed`, `intent`, `verdict`,
  `outage_id`, `outcome` (`resolved | informed_outage | informed_debt | ticket |
  ticket_appended | unidentified | abandoned | error`), `unidentified_reason`
  (`address_not_found | not_a_customer | caller_refused | hung_up | stuck |
  technical_error`), `needs_review` + `review_reason`, links to trace/audio.
  Outcome and reasons are derived deterministically from state, not by an LLM.
  Mass outage → contact record linked to the outage (complaint counter), **no ticket**.
  Unidentified calls → **no tickets**, only contact records for review.
  Review UI: an archive filter now; a dedicated queue later.
- **Consequences.** Audio retention for unidentified calls must be configurable (privacy).

---

## Part D — Behaviour mechanisms (content is written later, the mechanism now)

### D-15 · `say` = phrase key or directive

`TurnPlan.say` is either `phrase: <key>` (mandatory wording from the locale file — debt,
outage ETA, ticket registration, AI disclosure) or `directive: <goal>` (the LLM formulates
as an IT engineer). The speaker node renders; it never decides.

### D-16 · Consent per system action

Each system action in knowledge declares `consent: required | not_required`
(e.g. MAC bind, port reset). The gate refuses a `required` action without recorded consent.

### D-17 · Policies and limits in files

Forbidden actions/topics live in `policies.yaml` (gate + speak directives). Numeric limits
(procedure retries, re-ask count, when to ticket, gate thresholds now in
`gate.py DEFAULT_POLICY`, turn caps) live in a config file, not Python.

### D-18 · Step roles, not step ids

Pack steps declare `role:` (e.g. `recheck`, `verify_restored`, `bind_device`). The engine
matches roles; no pack step id (`rh_check`, `crc_recheck`, `dr_pick_cable`, …) may appear
in Python. Goal: **a new fault = YAML + Markdown, zero Python.**

---

## Part E — Language, process, scope

### D-19 · English code, prompts, schema and docs; customer language via locales

- **Decision.** All code, identifiers, YAML schema keys, prompts and documentation are
  English. Everything the customer hears (phrases, question texts, few-shot examples) and
  language-specific vocabulary (triggers, answer synonyms like "jo"/"nepadėjo",
  end-of-speech words) lives in `locales/<lang>/`. The agent speaks Lithuanian now;
  EN/PL/RU are a later stage that must require **no engine change**.
- **Consequences.** Pack keys are renamed (e.g. `vairuotojas`, `patvirtinta_kai`,
  `sprendimai`), customer text moves to `locales/lt/`, prompts are rewritten in English with
  `{output_language}`. Docs are English now; the presentation is translated to Lithuanian later.

### D-20 · Safety net before deletion; delete as you go

- **Decision.** Work on branch `refactor/single-engine`. Before removing the old engine:
  eval scenarios for uncovered verdicts (`crc_errors`, `link_down_local`) and a recorded
  baseline of current v2 outcomes. After that, **unused code and obsolete tests are deleted
  immediately in the milestone that makes them obsolete** — no separate cleanup phase.
- **Consequences.** Each milestone ends green (pytest + eval) and with its dead code removed.

### D-21 · Checkpoints and dashboard

- Checkpoints are used for debugging, replay and the dashboard for now; resuming a call
  after a server crash is out of scope.
- `TurnPlan` and hypothesis status are emitted as trace events and rendered in the
  dashboard "brain" panel (useful for the demo).

### D-22 · Order of work

Refactor first, presentation preparation afterwards.

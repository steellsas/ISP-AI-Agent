# M6 — Call intents, identification gate, service profile, tickets, contact records

> Part of [REFACTORING_PLAN.md](REFACTORING_PLAN.md). Read its "Rules for the executor" first.
> Decisions: D-08, D-09, D-10, D-11, D-12, D-13, D-14. Prerequisites: M5 done.

Legend: `A/` = `chatbot_core/src/agent/`, `K/` = `A/knowledge/`, `DB` = `database/schema/`.
Line numbers from `develop` @ `c7be3ba`; re-locate with grep.

---

## 1. Why (current gaps against the decisions)

| Decision | Gap in code today |
|---|---|
| D-09 identification gate | Preflight checks outages for an **unconfirmed** phone candidate (`identification_flow.preflight_phone` ~L61-78) and the narrator announces it before identification (`narrator_flow.py` ~L517-529 "PROACTIVE OUTAGE"). Identity can be committed without explicit confirmation (dictated address, LLM lookup); `address_confirmed` is never set (F-6). |
| D-08 level-1 checks | One composite diagnose; no open-ticket check; `outage_id` not kept in state. |
| D-10 service profile | The agent keeps only plan names (`tools._format_customer_profile` ~L256-292) and uses none of them; DB has no service technology (`DB/crm_schema.sql` ~L59 `service_type IN ('internet','tv','phone','bundle')`). |
| D-11 intents | Catalog lives in `faults.yaml problems`; policy `registruoja` has no own path; no `answer` policy; billing is `nelieciam`. |
| D-12 multiple problems / open ticket | `secondary_problems` exist; no dependency model; no "append to open ticket"; only raw-SQL `amend_ticket_note` for the call's own ticket. |
| D-11 ticket types | Engine always registers `technician_visit`/`high` (`executor_flow.py` ~L178-268); DB CHECK allows only 5 technical types (`DB/crm_schema.sql` ~L121). |
| D-14 contact record | `end_session` runs only on DELETE/TTL/shutdown — not on WebSocket disconnect (F-3); `outcome` column overwritten by transport strings (F-4); no `unidentified_reason`, `needs_review`, `outage_id`, `intent`, `duration_seconds`. |

## 2. Before → After

```
 call start ─► phone lookup → identity.candidate
           └─► background: level-1 telemetry for candidate (outage only)  ── held, not spoken
 intake     ─► intent (catalog K/intents.yaml) + problem text stored
 identify   ─► explicit confirmation → identity.confirmed = true (address_confirmed)
           └─► level-1: billing · outage · node/switch · OPEN TICKETS  (+ held outage result released)
 by intent policy:
   solve     → level-2 telemetry → decide/procedures (M4)
   register  → collect info → ticket(type) → "registered, they will contact you"
   answer    → answer from data (ticket status, outage ETA, debt)
   not_ours  → boundary phrase (no identification)
   chat      → warm reply
 open ticket for same problem → append note + tell status (no new ticket)
 session end (hang-up, disconnect, error, TTL, shutdown) ─► FINALIZER ─► contact record
```

## 3. Affected files

**Create**
- `K/intents.yaml` (moved from `K/faults.yaml problems`, EN keys from M3) with policies
  `solve | register | answer | not_ours | chat` and, for `register`, a `ticket_type`.
- `K/services.yaml` — service catalog and dependencies, e.g.:
  ```yaml
  services:
    internet: {technologies: [ftth, ethernet]}
    tv:       {technologies: [iptv, dvbc]}
    phone:    {technologies: [voip]}
  dependencies:
    - {service: tv, technology: iptv, depends_on: internet}
    - {service: phone, technology: voip, depends_on: internet}
  ```
- `K/ticket_types.yaml` — agent ticket types → department (integration maps them to the real CRM):
  `fault_technician`, `fault_unclear`, `billing_request`, `disconnection_request`,
  `service_transfer`, `customer_wish`, `repeat_contact` (append only).
- `A/decide/rules/intents.py`, `A/decide/rules/open_ticket.py`, `A/decide/rules/services.py`.
- `A/call_record/finalizer.py`, `A/call_record/outcome.py` (deterministic derivation).
- DB migrations as SQL files `database/schema/migrations/2026_09_m6_*.sql` + apply them in
  `scripts/setup_db.py`, `app/admin.py reset_db`, `tests/conftest.py`.
- Tests listed in §5.

**Modify**
- `DB/crm_schema.sql`: `service_plans.technology TEXT` (nullable) + seed values in
  `database/seeds/service_plans.sql`, `demo_internet.sql`, `network_faults.sql`; replace
  `bundle` rows by explicit service rows (or add `bundle_id` grouping) so the profile lists real
  services; `tickets.ticket_type` CHECK → the new types (keep existing technical ones used by seeds);
  `conversations` new columns: `intent TEXT`, `verdict TEXT`, `outage_id TEXT`,
  `address_confirmed INTEGER`, `unidentified_reason TEXT`, `needs_review INTEGER DEFAULT 0`,
  `review_reason TEXT`, `closed_reason TEXT`, `transport_end TEXT` (hang-up/disconnect/ttl/…),
  `audio_retention_until TIMESTAMP`; `area_outages` complaint counter via a view
  `outage_contacts` (count of `conversations` by `outage_id`) — no counter column.
- CRM tools (`crm_service/src/crm_mcp/tools/`): `get_customer_details` already returns plans,
  equipment, `recent_tickets` (`customer_lookup.py` ~L407-491) — expose `services` (type +
  technology + status) and `open_tickets`; new `append_ticket_note(ticket_id, note, kind)`
  (replaces `ticket_flow.amend_ticket_note` raw SQL from M2); `create_ticket` accepts the new
  `ticket_type` values; `save_conversation` writes the new columns.
- `A/tooling/telemetry.py`: `level=1` alone (billing, outage incl. `outage_id`, node/switch,
  open tickets); `level=2` alone (port/line/…); outage check allowed with `candidate=True` flag
  that marks the result **held**.
- `A/decide/rules/identification.py`: explicit confirmation rule; no commit on dictated address
  without a confirmation turn ("Ar skambinate dėl adreso X?" → yes); LLM/lookup results create
  a candidate, never a commit (F-6).
- `A/speak/context_card.py`: remove any pre-identification account/outage content.
- `A/session.py` + `chatbot_core/src/app/sessions.py` + `chatbot_core/src/app/main.py`: finalizer on
  every end path (WebSocket `finally` ~L800-818 must call it once the call is over or the socket
  is gone for > configurable grace seconds; DELETE; TTL sweep; shutdown); remove
  `outcome` override (F-4).
- `chatbot_core/src/app/archive.py` + `app/static/index.html`: archive filter "needs review" and
  columns intent / outcome / unidentified reason.
- Config: `CALL_AUDIO_RETENTION_DAYS_UNIDENTIFIED` (default 30), `WS_DISCONNECT_GRACE_S`.

**Delete**
- `problems:` section and loader code in `K/faults.yaml` / `A/faults.py` (file `K/faults.yaml`
  deleted if empty).
- `preflight_outage` announcement path, the `PROACTIVE OUTAGE` card content, related ladder skips
  (`identification_flow` ~L1301, 1465 equivalents in M4 rules).
- `amend_ticket_note` raw SQL.
- `A/session_record.py` (temporary from M5) once the finalizer replaces it.

## 4. Step-by-step

1. **Intents catalog.** Move `problems` → `K/intents.yaml`; policies `solve/register/answer/
   not_ours/chat`; rules in `A/decide/rules/intents.py` route by policy (billing, disconnection,
   service transfer/relocation, wishes → `register` with ticket type; ticket status / outage ETA /
   debt questions → `answer`). Multiple intents in one call are handled one after another
   (primary first, others kept in `intake.secondary_problems`). Commit.
2. **Identification gate.** (a) Candidate vs confirmed identity in state
   (`identity.candidate`, `identity.confirmed`, `identity.address_confirmed`); (b) explicit
   confirmation rule; (c) level-1 telemetry only after confirmation; (d) background outage check
   for the candidate stored as `identity.held_outage` and released as an `inform` plan in the
   first turn after confirmation, discarded if the candidate is rejected; (e) remove
   pre-identification outage talk. Tests: nothing about account, debt or outage is said before
   confirmation (scan replies and `turn_plan` events in eval scenarios I1–I6, D2). Commit.
3. **Service profile.** DB `technology` column + seeds; profile model in
   `identity.service_profile`; `rules/services.py`: complaint about a service the customer does
   not have → inform; dependency from `K/services.yaml` — dependent problem is re-checked after the
   primary is fixed; independent problems solved one after another; telemetry choice by service.
   Commit.
4. **Tickets.** New ticket types + `K/ticket_types.yaml`; `create_ticket` with type and all
   problems of the call in the details (D-12); open-ticket check in level-1 →
   `rules/open_ticket.py`: same problem → `append_ticket` (note: repeat call, what the client said,
   `kind: just_checking | nobody_came | new_info`) + `answer` status; different problem → normal
   path; identified customer can always register a ticket with a message. Commit.
5. **Contact record finalizer.** `finalizer.finalize(thread_id, transport_end)` loads final state
   from the checkpointer, derives `outcome` / `unidentified_reason` / `needs_review` /
   `review_reason` deterministically (`outcome.py`, table below), writes `conversations`, sets
   `audio_retention_until` for unidentified calls, exports the transcript. Idempotent. Wire it into
   every end path; WebSocket disconnect triggers it after `WS_DISCONNECT_GRACE_S` unless the call
   reconnects. Outage calls record `outage_id` (no ticket). Unidentified calls never create
   tickets. Commit.

   | Condition (checked in order) | outcome | unidentified_reason | needs_review |
   |---|---|---|---|
   | technical error event in the turn log | `error` | `technical_error` (if unidentified) | yes |
   | not confirmed + stuck backstop fired | `unidentified` | `stuck` | yes |
   | not confirmed + intent `not_ours`/new customer | `unidentified` | `not_a_customer` | yes |
   | not confirmed + caller refused address | `unidentified` | `caller_refused` | no |
   | not confirmed + address lookups failed | `unidentified` | `address_not_found` | yes |
   | not confirmed + hang-up/disconnect | `abandoned` | `hung_up` | yes |
   | confirmed + outage informed | `informed_outage` | — | no |
   | confirmed + debt informed | `informed_debt` | — | no |
   | confirmed + ticket appended | `ticket_appended` | — | no |
   | confirmed + ticket created | `ticket` | — | no |
   | confirmed + resolved | `resolved` | — | no |
   | confirmed + hang-up before close | `abandoned` | — | yes |
6. **Archive filter.** `/calls?needs_review=1`, columns and a filter toggle in the dashboard
   archive. Commit.

## 5. Tests

- `test_intents.py` (policy routing per intent; register → ticket type; answer → data reply).
- `test_identification_gate.py` (no account/outage/debt content before confirmation; held outage
  released after confirmation, discarded on rejection; dictated address requires confirmation).
- `test_service_profile.py` (no-service inform; IPTV dependency re-check; independent sequence).
- `test_open_ticket.py` (append vs new; status answer; no duplicates).
- `test_call_record.py` (every row of the outcome table; finalizer idempotent; WS disconnect path;
  outcome not overwritten by transport).
- DB tests: migrations apply on a fresh DB and on `reset_db`.
- Eval: add scenarios `R1_billing_request` (register), `R2_repeat_call_open_ticket` (append),
  `R3_iptv_depends_on_internet`, `U1_unidentified_hangup` (contact record only).

## 6. Definition of Done

- Every call in eval and in a manual hang-up test produces exactly one `conversations` row with the
  new columns filled per the table.
- No reply before confirmation contains account, debt or outage information (automated check).
- `grep -rn "PROACTIVE OUTAGE\|preflight_outage\|amend_ticket_note\|technician_visit\" *, *\"high\"" chatbot_core/src` → nothing.
- `uv run pytest` green; eval ≥ baseline + new scenarios; owner live test: outage call (announce
  after confirmation), repeat call with an open ticket, billing request.

## 7. Risks & rollback

- **Demo flow change** for outage calls (announcement moves after confirmation): update
  `docs/DEMO_SCENARIJAI.md` #2 wording in the same commit; tell the owner.
- **DB migration on the live demo DB**: demo DB is rebuilt by `reset_db`, but archived calls in
  `conversations` would be lost — export before applying if the owner wants to keep them.
- Rollback: revert per step; migrations are additive except the `ticket_type` CHECK (revert =
  restore the old schema file and reset DB).

# M4 — `decide`: TurnPlan, single driver, hypothesis stability, closed action set

> Part of [REFACTORING_PLAN.md](REFACTORING_PLAN.md). Read its "Rules for the executor" first.
> Decisions: D-02, D-03, D-04, D-05, D-07, D-16, D-17. Prerequisites: M1, M2, M3 done
> (single state, runtime context + tool gateway, English knowledge contract with step roles).

Legend as in M1/M2. Line numbers from `develop` @ `c7be3ba` (pre-M1..M3 names; after M2 the
functions take `(state, rt)`); re-locate with grep.

---

## 1. Why

Decisions are spread over five places and ~60 ordered checks:

| Today | Where | What it decides |
|---|---|---|
| Pre-turn guards (8 groups) | `PF.pre_turn_guards` ~L687-1320 | ticket capture, end/reopen confirm, cannot-now shield, farewell, caller intro, identity commit |
| Identification scripted ladder (16 rules) | `ID.identification_scripted_reply` ~L1001-1450 | problem gate, account code, address, inform delivery, wrap-up |
| Solver drive (8 bail-outs + actions) | `SF.solver_drive_turn` ~L197-383, `SF.drive` ~L386-491 | evidence questions, recap, findings, bridge, escalate, close |
| Walker + guard chain (3 prelude + 8 step guards + dispatch) | `WF.walk_resolution` ~L233-337, `WG` | step advancement, holds, classifier routing |
| Scripted exits inside the narrator | RA `_run_until_response_stream` ~L1422-1590 | greeting, stuck backstop, identification reply, wait-ack, speculation injection |

Plus routers (`v2/router.py`) and the closing node (`v2/nodes/closing.py` ~L22-114).
Nobody can answer "why did the agent do that" from one place. Two drivers exist
(`meta.driver: solver|walker`). The hypothesis is silently replaced on every diagnose
observation (`WF.open_hypothesis` via `NF` ~L1473-1488, Findings F-7). Verdicts without a pack
(`dhcp_silent`, `no_port_data`) fall through to a free LLM with all tools (F-8). The stuck
backstop promises a registration and creates no ticket (F-5).

## 2. Before → After

```
BEFORE (v2)                                         AFTER
route_entry ─► identification | ticket |            perceive ─► decide ─► execute ─► narrate* ─► END
               closing | diagnosis subgraph                        ▲         │
diagnosis: diagnose ─► side_topic | solver_gate                    └─(max 1 re-decide after a recheck)
           ─► walker ─► executor ─► narrator
                                                    * narrate = existing LLM loop, now fed by TurnPlan;
                                                      M5 replaces it with `speak`.
```

- **perceive** (no decisions): understanding pass (facts + intent + step answer), side-topic
  classification, slot prefill, caller-intro extraction, detector reads, analyst signals merge.
  Output: `turn.perception` (typed).
- **decide** (pure policy + optional LLM solver): produces exactly one `TurnPlan`, traced as
  `turn_plan`.
- **execute**: runs `plan.action` through the tool gateway (M2); procedure step effects; ticket
  registration; may request one re-decide (e.g. a `recheck` produced a contradiction).
- **narrate**: renders `plan.say` (phrase → scripted text; directive → LLM wording).

### `TurnPlan` model (`A/decide/plan.py`)

```python
class Say(BaseModel):
    kind: Literal["phrase", "directive", "none"]
    key: str | None = None            # locale phrase key (kind=phrase)
    goal: str | None = None           # English goal for the LLM (kind=directive)
    vars: dict[str, Any] = {}

class Action(BaseModel):
    type: Literal["tool", "procedure_step", "register_ticket", "append_ticket", "close", "none"]
    name: str | None = None           # tool name / step role / close reason
    args: dict[str, Any] = {}
    consent: Literal["required", "not_required"] = "not_required"

class Contradiction(BaseModel):
    source: Literal["telemetry", "client", "analyst"]
    fact_key: str
    before_value: str | None
    before_quote: str | None          # what the client said earlier (for the confirm question)
    now_value: str | None

class HypothesisView(BaseModel):
    cause: str                        # verdict / pack id
    status: Literal["active", "doubt", "confirming", "changed"]
    contradiction: Contradiction | None = None

class TurnPlan(BaseModel):
    owner: Literal["intake", "identification", "inform", "side_topic",
                   "diagnosis", "procedure", "ticket", "closing"]
    rule: str                         # id of the policy rule that fired, e.g. "ticket.capture_phone"
    action: Action = Action(type="none")
    say: Say
    hypothesis: HypothesisView | None = None
    awaiting: str | None = None       # evidence key / step role / question key we wait for
    redecide_after_action: bool = False
```

Closed action set (D-04): `action.name` must be a tool in the allowed catalog, a step role of the
active pack/module, a solution of the active pack, or one of the standard actions
(`ask`, `inform`, `register_ticket`, `append_ticket`, `close`). The gate rejects anything else.

## 3. Affected files

**Create**
- `A/perceive/` package: `node.py` (perceive node), moves extraction-only code from
  `PF` (ingest, side-topic classification, overlay ingest), `A/understand.py`, `A/nlu.py`,
  detector functions from `A/resolution.py`, caller-intro/slot extraction from `ID`/`PF`.
- `A/decide/` package:
  `plan.py` (models above), `node.py`, `policy.py` (ordered rule chain, §4 step 4),
  `rules/identification.py`, `rules/ticket.py`, `rules/closing.py`, `rules/inform.py`,
  `rules/side_topic.py`, `rules/dialog.py` (end-confirm, reopen, cannot-now, farewell, backstop,
  wait-ack), `rules/diagnosis.py` (solver driver), `procedure.py` (procedure runner),
  `hypothesis.py` (state machine), `gate.py` (moved from `A/gate.py`, extended), `solver.py`
  (moved from `A/solver.py`; output schema = closed enum).
- `A/execute/node.py` (plan executor; uses `rt.tools`).
- Tests: `test_policy_order.py`, `test_rules_*.py`, `test_procedure.py`, `test_hypothesis.py`,
  `test_gate_closed_set.py`, `test_turn_plan_trace.py`.

**Delete (when emptied — each rule family's commit deletes what it replaced)**
- `v2/router.py`, `v2/nodes/identification.py`, `v2/nodes/ticket.py`, `v2/nodes/closing.py`,
  `v2/nodes/side_topic.py`, `v2/nodes/diagnosis/` (whole subgraph), `v2/tool_scopes.py`
  (except LOOKUP scope, kept until M6).
- `A/walker_flow.py`, `A/walker_guards.py`, `A/solver_flow.py`, `A/evidence_drive.py`,
  `A/ticket_flow.py`, `A/closing_flow.py`, decision parts of `A/perception_flow.py` and
  `A/identification_flow.py` (both files deleted once only extraction remains in `A/perceive/`),
  `A/dialog_registry.py` (replaced by `plan.owner` + `dialog.active_question` precedence in policy),
  `A/gate.py`, `A/solver.py` (moved), `A/classifier.py` if the perception step answer fully
  covers it (keep only if eval shows the fallback is still needed — then move it to `A/perceive/`).
- RA scripted exits: `_stuck_backstop`, `_apply_backstop`, `_consume_injected_reply` call sites,
  identification scripted reply and wait-ack hooks in `_run_until_response_stream`,
  `_commit_driven_reply`, `turn.pre_turn_head_done` latch.
- `meta.driver` in packs and every reader; `SOLVER_DRIVE`, `SOLVER_SHADOW` env flags,
  `shadow_solve`; `_SOLVER_DRIVE_VERDICTS`.
- Tests of deleted modules are rewritten as policy/procedure tests (not kept in parallel).

## 4. Step-by-step

1. **One driver in the packs.** Delete `meta.driver`. Give `internet_crc_kabelis.yaml`
   (`crc_errors`) and `internet_linija_nutrukusi.yaml` (`link_down_local`) the `evidence`
   (`confirmed_when`, `refuted_when`) and `solutions` blocks that `rules/diagnosis.py` needs to
   start their procedure (today they rely on the walker from the first turn). Until step 6 lands,
   make the existing solver drive treat every pack as solver-driven. Eval: D5/D6 scenarios (M0)
   must pass. Commit.
2. **TurnPlan in shadow.** Add `A/decide/plan.py`; make the existing nodes *record* the plan they
   effectively executed (owner, rule id, action, say kind) and emit `turn_plan` trace events.
   No behaviour change. This gives a reference trace for every eval scenario before the rewrite:
   store one JSONL per scenario in `docs/refactoring/baseline/plans/` (commit).
3. **perceive node.** Move extraction-only logic into `A/perceive/` and a `perceive` node that
   runs first. Rule: perceive may write facts/slots/understanding/signals, never
   `closing`, `ticket.stage`, `resolution` position, `identity.customer_id` commit, or say
   anything. Decisions found inside extraction code (e.g. identity commit inside
   `PF.pre_turn_guards` group 7) move to decide rules in step 4. Commit.
4. **Policy chain.** Implement `policy.plan_turn(state, perception, rt) -> TurnPlan` as an
   ordered list of rules. Port **today's precedence exactly** (§5 table). One rule family per
   commit; in each commit the old code path for that family is deleted and the node calls the
   rule. Each rule is a pure function `(state, perception, rt.readonly) -> TurnPlan | None`
   (no tool calls; tools are actions).
5. **New graph.** `perceive → decide → execute → narrate → END`, with `execute → decide`
   allowed once per turn when `plan.redecide_after_action` and the result changed facts
   (cap in `K/limits.yaml: max_redecide_per_turn: 1`). Delete router, stage nodes, subgraph.
   Commit.
6. **Procedure runner.** Extract `WF.advance_*` (instruct, restored, line check, reboot check,
   see device, escalate, route_to, goto_step) and the step guards into `procedure.py`:
   `advance(state, step, perception, telemetry_result) -> StepOutcome(next_role | exit(success|failure) | hold | need_recheck)`.
   Ownership rule (replaces `walker_owns_turn`): while a procedure is active, the client's answer to
   the procedure's awaited step belongs to the procedure; `rules/diagnosis.py` regains control on
   (a) procedure exit, (b) a contradiction (step 7), (c) refusal/ticket demand, (d) a new problem or
   side topic. Commit.
7. **Hypothesis state machine** (`hypothesis.py`, D-05):
   ```
   active ──contradiction(telemetry|client|analyst)──► doubt
   doubt ──decide asks confirm question (quote before_quote)──► confirming
   confirming ──client confirms contradiction──► changed ─► new hypothesis active (old → failed_hypotheses)
   confirming ──client denies / unclear──► active (contradiction dropped, note in ledger)
   ```
   - A telemetry `recheck` that yields a different verdict **never** switches directly; it
     creates a `Contradiction(source="telemetry")`. The confirm question is about the symptom the
     client can observe (e.g. WAN light) — phrase key from the pack
     (`evidence.client.<key>.confirm_key`, added in this step to the packs that need it).
   - Replace `WF.open_hypothesis` silent replacement (F-7), `ED.maybe_refute_confirm` single-flag
     `_refute_state`, story-flip gate (`PF._story_flip_gate`), client-vs-client conflict clarify
     (`PF._conflict_to_clarify`, `ID` ~L1221-1232) with this one mechanism.
   - Analyst signals of type `contradiction` (M5) plug into the same entry point; in M4 accept the
     type but nothing emits it yet.
   - Limits: max confirm attempts per contradiction in `K/limits.yaml`.
   Commit.
8. **Closed action set + consent.** `decide/gate.py`: validate `plan.action` against the allowed
   set (§2), consent (`steps[].consent: required` needs `dialog.consents[role] == true`, recorded
   when the client agreed), and `K/policies.yaml` forbidden actions. Solver LLM output schema
   (`decide/solver.py`) becomes an enum built at runtime from the active pack's solutions/step
   roles + standard actions; free-text hypotheses are rejected. Verdicts without a pack and
   without `inform: true` (e.g. `dhcp_silent`, `no_port_data`) route to the `unclear_fault` pack
   (register ticket) — fixes F-8. Commit.
9. **Stuck backstop fix** (F-5): the backstop rule (today RA ~L1903-1974: stuck 3 → offer account
   code, stuck 4 → "Užregistruosiu…" + `closed_reason="declined"` without a ticket) must, when the
   customer is identified, plan `register_ticket` (reason `stuck`); when unidentified, plan
   `close` with `closing.unidentified_reason="stuck"` (M6 turns it into a contact record with
   `needs_review`). Commit.
10. **Remove scripted exits from the narrator loop** (they are plans now) and delete everything in
    §3 "Delete". Compare `turn_plan` traces with the step-2 shadow baseline for every eval
    scenario: differences must be explained by F-5/F-7/F-8 fixes or D-05. Commit.

## 5. Policy precedence to port (today's order, highest first)

| # | Rule family → rule ids | Today's code (re-grep) |
|---|---|---|
| 1 | `dialog.greeting` (turn 0) | RA ~1426-1433 |
| 2 | `closing.*` when `closing.case_closed`: ticket demand at goodbye → reopen+escalate; "still not working" after resolved → reopen+escalate; finish; amend ticket contact; secondary problems ask once; scripted goodbye | `v2/nodes/closing.py` ~31-113, `CF.maybe_finish` |
| 3 | `ticket.*` when `ticket.stage` set: cancel-confirm answer; first-person callback → close callback; ticket reader (question/refusal/value); keyword question divert; "don't register" → cancel-confirm; farewell → done; phone/hours capture with one retry each; finish → register | `PF.pre_turn_guards` group -2 ~708-984, `TF`, `ID` ~1179-1206 |
| 4 | `dialog.end_confirm_answer` | `PF` ~991-1015 |
| 5 | `identification.reopen_confirm_answer` | `PF` ~1022-1073, `ID` ~1069-1085 |
| 6 | `dialog.cannot_now` shield + ladder | `PF` ~1080-1097, `ID` ~1090-1174 |
| 7 | `dialog.farewell_mid_process` → end-confirm | `PF` ~1098-1115 |
| 8 | `identification.caller_intro` / holder mismatch clarify | `PF` ~1120-1177, `ID` ~1030 |
| 9 | `identification.*` when not identified: offer-reply commit, corrected address commit, "which address?", problem gate (L1 triggers, L2 LLM, confirm, boundary reply, gate max turns), account-code rung, address ladder, spelling round, street-not-exists, city-not-served | `PF` ~1178-1308, `ID` ~1270-1329, 448-546, 735-998 |
| 10 | `identification.address_correction` when identified | `PF` ~1309-1320 |
| 11 | `dialog.callback_goodbye_due` | `ID` ~1012 |
| 12 | `side_topic.*` (FAQ answer + return to anchor; 3rd deviation frame) | `PF.classify_side_topic` ~534-628, `ID` ~1211-1218 |
| 13 | `diagnosis.hypothesis_confirm` (new, step 7) — replaces evidence conflict clarify `ID` ~1221-1232, fact confirm `ED` ~206-218, refute confirm `ED` ~223-237 | — |
| 14 | `dialog.confirm_end` / `diagnosis.escalate_clarify` / bare "no" to open evidence key | `ID` ~1234-1251, `WF` ~340-370 |
| 15 | `inform.*` when identified and result pending: caller-name question; inform template (+ auto ticket for node/switch faults); wrap-up close | `ID` ~1335-1450, `CF.maybe_close_inform` |
| 16 | `procedure.*` when a procedure is active and owns the awaited answer (prelude holds: question priority, resume hold, end-confirm pending; step guards: device-change pre-answer, homework consent, backchannel hold, restored pre-answer, refuse/ticket redirect, evidence question hold, classifier confirm/instruct routing; dispatch by step role) | `WG` PRELUDE ~71, STEP ~247, `WF.walk_resolution` ~233-337 |
| 17 | `diagnosis.*` solver driver: plug report → bridge fix; "no computer" → escalate; next missing evidence (first ask = directive, retries = phrases, give-up after limit); recap; findings; solution → start procedure / bridge / ticket; LLM solver for remaining gaps (closed set); distrust bailout | `SF.solver_drive_turn` ~197-383, `SF.drive` ~386-491, `ED.evidence_drive` ~182-476 |
| 18 | `dialog.stuck_backstop` (fixed, step 9) | RA ~1903-1974 |
| 19 | `dialog.wait_ack` | `WF.scripted_wait_ack` ~607-637, RA ~1492-1495 |
| 20 | `dialog.free_reply` — directive "answer in role" (fallback) | narrator |

Keep this order in `policy.py` as a literal list and pin it with `test_policy_order.py`.

## 6. Tests

- `test_policy_order.py`: the rule list order equals §5.
- Rule tests: table-driven "state + perception → plan" for every rule id (port assertions from
  `test_walker_guards.py`, `test_identification_rules.py`, `test_fault_packs.py`,
  `test_router_hung.py`, `test_line_faults.py`, `test_repeat_guard.py`, `test_tool_gate.py`,
  `test_dialogue_quality.py`, then delete the old tests of deleted modules).
- `test_procedure.py`: every step role outcome (success/failure/hold/recheck) for the 6 packs.
- `test_hypothesis.py`: all transitions; a telemetry recheck with a new verdict does not switch
  without confirmation; the confirm question quotes the earlier client statement.
- `test_gate_closed_set.py`: unknown action rejected; consent required; forbidden action;
  `propose_fix` accepted for every pack verdict; `dhcp_silent` → unclear-fault ticket.
- Eval: full run ≥ baseline; `turn_plan` diff vs shadow baseline explained.

## 7. Definition of Done

- Graph is `perceive → decide → execute → narrate`; `v2/router.py` and stage nodes gone.
- Every turn emits exactly one `turn_plan` event with a `rule` id.
- `grep -rn "driver\|vairuotojas\|SOLVER_DRIVE\|SOLVER_SHADOW\|walker_owns_turn\|open_hypothesis\|_refute_state\|dialog_registry" chatbot_core/src` → nothing.
- Files listed in §3 "Delete" are gone.
- `uv run pytest` green; eval ≥ baseline; owner live test of the 4 demo calls (debt → outage →
  CRC → hung router) plus one call where the client contradicts an earlier statement.

## 8. Risks & rollback

- **Precedence regressions** are the main risk (the guard chain holds hard-won behaviour —
  repeat guard, question ownership, backchannel). Port one family per commit, run eval after each,
  compare `turn_plan` traces with the shadow baseline.
- **Procedure ownership** edge cases (client answers a different question than the one awaited):
  covered by rules 13 and 16 order; add a test per case found.
- **LLM solver enum** may reduce flexibility → if eval regresses on a scenario, add the missing
  solution to the pack (knowledge), never widen the enum with free text.
- Rollback: revert the rule family's commit.

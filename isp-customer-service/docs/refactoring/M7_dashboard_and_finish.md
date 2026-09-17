# M7 — Dashboard TurnPlan panel and final verification

> Part of [REFACTORING_PLAN.md](REFACTORING_PLAN.md). Read its "Rules for the executor" first.
> Decisions: D-21, D-02, D-05. Prerequisites: M6 done.

Paths relative to `chatbot_core/src/`. Line numbers from `develop` @ `c7be3ba`; re-locate with grep.

---

## 1. Why

- The owner wants the demo audience (and himself when debugging) to **see the engineer think**:
  who owns the turn, which rule fired, the hypothesis and its status (active → doubt →
  confirming → changed), the action and what the agent waits for.
- The refactor must end with an explicit, repeatable verification and a clean handover.

## 2. Before → After (owner layout review, 2026-09-17)

The owner tested the M6 calls and asked for a dashboard built around the agent, not the
transcript: fixed panel sizes and a wide chat made the state hard to follow while testing.
Approved layout (mockup in the session, light and dark by the system theme):

```
┌ header: ISP agentas · [Testavimas] [Scenarijai] [Archyvas] [⚙] · scenario ▾ · phone · Call · voice ┐
├──────────── ~30% ─────────────┬┬──────────────────────── ~70% ──────────────────────────────┤
│ Scenario card: what to say     ││ Graph strip: perceive → decide → execute → narrate (+ ms)   │
│ (said lines ticked, expected)  ││ Turn plan card │ State card (customer, address ✓, verdict)   │
│ Conversation (compact)         ││ Event timeline with filters (LLM · tools · decisions · ASR/TTS) │
│ text input · mic               ││   and duration bars                                         │
└────────────────────────────────┴┴────────────────────────────────────────────────────────────┘
 drag splitters between columns and blocks · every block collapses · sizes remembered
```

- **Scenarijai**: the demo scenarios as data (number, phone, client and address, what to say
  step by step, expected verdict and outcome); ▶ fills the phone, opens Testavimas with the
  scenario card, and after the call the expected verdict/outcome are ticked ✓/✗.
- **Archyvas**: the review filter, and a call opens in the same components as Testavimas
  (transcript, turn cards, timeline, audio), stepping turn by turn.
- The graph is the four-node strip with durations; a detailed rule/step graph is later work.

## 3. Affected files

- `app/static/index.html` split into `index.html` + `app.css` + `js/*.js` (no build step),
  served under `/static`.
- `app/scenarios.yaml` + `GET /demo/scenarios`.
- `agent/graph_v2/runtime.py`: a `graph_node` trace event with the node's duration.
- `adapters/tracing/jsonl_tracer.py` `export_txt`: one `[plan]` line per turn.

## 4. Step-by-step

1. **Events.** `graph_node` {node, ms} per graph node; `turn_plan` carries `turn_index`; pinned
   by `test_turn_plan_trace.py`. Commit.
2. **Split the page** into files served under `/static` with no visible change (voice, mic,
   barge-in and config keep working). Commit.
3. **Testavimas layout**: tabs, splitters, collapsible blocks, remembered sizes, light/dark
   theme; graph strip, turn plan card (hypothesis status colours: active neutral, doubt amber,
   confirming blue, changed green), state card, event timeline with filters and duration
   bars. Readable at phone width. Commit.
4. **Scenarijai**: `scenarios.yaml` (the 9 demo scenarios + the M6 ones), endpoint, tab,
   scenario card in Testavimas, expected-result check. Commit.
5. **Archyvas** in the same components, turn stepping. Commit.
6. **Export**: `export_txt` line
   `[plan] owner=procedure rule=procedure.verify_reboot hyp=router_hung(doubt) say=directive`. Commit.
7. **Final verification (no code changes unless a check fails):**
   - `uv run pytest` — green.
   - Eval twice — pass count ≥ M0 baseline plus new scenarios; store both JSON runs in
     `docs/refactoring/baseline/final/` with a README (date, commit, models).
   - Acceptance greps from every milestone DoD re-run in one script
     `scripts/refactor_acceptance.py` (commit it; it is useful for future regressions).
   - App starts; owner live voice session on the demo scenarios + contradiction call + repeat
     call with open ticket + unidentified hang-up.
   - Latency check P-1 (plan §9): `ttfa_ms` / `voice_latency` from those sessions vs the M0
     baseline, written into `RESULT.md`.
8. **Handover.** Update `REFACTORING_PLAN.md` (all ticks, status log, findings), write
   `docs/refactoring/RESULT.md` (1 page: what changed, final architecture diagram, known
   limitations, follow-ups), update `docs/DEMO_SCENARIJAI.md`. Push the branch and give the
   owner the compare URL and an English PR description — the owner opens and merges the PR.

## 5. Definition of Done

- Every turn of a live call shows a Turn plan card; hypothesis transitions are visible on the
  contradiction call.
- The dashboard layout above works in a live call and in the archive; scenarios run from the Scenarijai tab.
- Final verification items all pass; `RESULT.md` written; branch pushed with the PR description.

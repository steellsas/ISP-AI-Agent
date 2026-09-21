# Perception eval — is the READING right?

The conversation eval (`agent/eval/`) scores whole calls. This one scores the single
thing every call depends on: **what the agent understood from one utterance** — the turn
type and the canonical facts. It is how a model swap, a prompt change or a prompt
LANGUAGE change becomes measurable (P-5, review finding AR).

```bash
cd chatbot_core
uv run python src/agent/eval/perception/run.py                  # both case files
uv run python src/agent/eval/perception/run.py --only reviewed   # the curated set
uv run python src/agent/eval/perception/run.py --limit 20 --json report.json
```

## The two case files

| File | What it is | How to read a failure |
|---|---|---|
| `cases_reviewed.json` | **Curated**: expectations a human confirmed. | A failure is a real defect — the run exits non-zero. |
| `cases.json` | **Baseline**: what the system read on recorded calls (auto-collected from traces, unreviewed). | A drop is a regression signal; a difference may be an improvement. Review the case, then move it to the curated file with the right expectation. |

## A case

```json
{
 "utterance": "Visuose įrenginiuose",
 "context": {"verdict": "router_hung", "pending": "fail_scope",
             "question": "Ar internetas neveikia visuose įrenginiuose, ar tik viename?"},
 "expect": {"turn_type": "answer", "facts": {"fail_scope": "all"}}
}
```

`context` puts the call in position: `verdict` activates that fault's evidence spec,
`pending` is the evidence question that is out, `question` is what the agent just asked.
`expect.facts` are canonical values (the pack's own), so a case survives re-wording.

## Growing the set

1. A misread in a live call → add the utterance with the RIGHT expectation to
   `cases_reviewed.json` (this is the wave-0/9 data flywheel: `needs_review` calls are
   the queue).
2. Re-collect the baseline from fresh traces when the reading changes on purpose.
3. Keep cases short and about ONE thing: they are a table, not a conversation.

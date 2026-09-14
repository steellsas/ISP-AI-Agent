# Documentation index

> Updated 2026-09-14. Documentation language is English from now on; existing Lithuanian
> working documents stay as they are until they are rewritten.

## Start here

| Document | Purpose |
|---|---|
| [refactoring/REFACTORING_PLAN.md](refactoring/REFACTORING_PLAN.md) | **Current work.** Single-engine refactor: goal, milestones M0–M7, rules for the executor, commands, findings |
| [refactoring/DECISIONS.md](refactoring/DECISIONS.md) | Architecture decisions D-01…D-22 (the "why") agreed with the owner on 2026-09-14 |
| `refactoring/M0_…` … `M7_…` | Step-by-step instructions per milestone |

## Active working documents (describe current behaviour; Lithuanian)

| Document | Purpose | Note |
|---|---|---|
| [DEMO_SCENARIJAI.md](DEMO_SCENARIJAI.md) | 9 demo calls: phone numbers, flows, branches | behaviour reference for the refactor |
| [DIALOGO_ETALONAS.md](DIALOGO_ETALONAS.md) | Reference dialogue quality rules | behaviour reference |
| [IDENT_TESTAI.md](IDENT_TESTAI.md) | Identification live test scripts | |
| [BARGE_IN_TESTAI.md](BARGE_IN_TESTAI.md) | Barge-in live test scripts | |
| [TESTAVIMO_SCENARIJUS.md](TESTAVIMO_SCENARIJUS.md) | Voice test scenarios with dialogue | mentions `voice_demo.py`, deleted in M0 |
| [TESTU_ZEMELAPIS.md](TESTU_ZEMELAPIS.md) | Map of the unit test suite | outdated after M1 |
| [FAULT_PACKS.md](FAULT_PACKS.md) | Fault pack author guide | outdated after M3 (English schema, roles) |
| [VOICE_PLAN.md](VOICE_PLAN.md) | Voice naturalness plan and backlog | |
| [AGENT_ONBOARDING.md](AGENT_ONBOARDING.md) | Customer onboarding questionnaire (for deployment) | input for integration docs |

## Planned (after the refactor)

Programmer documentation (engine, modules, file map) · presentation (Lithuanian) ·
instructor guide (knowledge files, phrases, policies) · integration & production guide.

## Archive

[archive/](archive/) — superseded documents describing the pre-refactor engine
(`ReactAgent`, legacy graph, old roadmaps, Dec 2025 installation/RAG/tools docs) and the old
`chatbot_core/docs/` design notes. Kept for history only; code comments that still point to
`docs/ROADMAP_REFACTORING.md`, `docs/MASTANTIS_AGENTAS_SPEC.md` etc. now refer to
`docs/archive/…` and are removed as the refactor rewrites those files.

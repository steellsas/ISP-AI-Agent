# M3 — Knowledge contract (English schema, locales, roles, policies, validation)

> Part of [REFACTORING_PLAN.md](REFACTORING_PLAN.md). Read the plan's "Rules for the executor"
> first. Decisions: D-15, D-16, D-17, D-18, D-19, D-03 (driver key disappears), D-04.
> Prerequisites: M0, M1, M2 done (GraphState is the only state; tools run through `execute`).

Path legend used below: `A/` = `chatbot_core/src/agent/`, `K/` = `chatbot_core/src/agent/knowledge/`,
`P/` = `chatbot_core/src/agent/prompts/`. Line numbers were taken on 2026-09-14 from
`develop` (commit `c7be3ba`); they drift — always re-locate with grep before editing.

---

## 1. Why

1. **"A new fault = YAML + Markdown, zero Python" is false today.** Python matches pack
   step ids (`rh_check`, `crc_recheck`, `dr_pick_cable`, …) and id suffixes
   (`_ability`, `_locate`, `_homework`), and keeps duplicate in-code strategies
   (`A/resolution.py STRATEGIES`). See D-18.
2. **Mixed languages confuse the model and block other languages.** Schema keys are
   Lithuanian (`vairuotojas`, `patvirtinta_kai`, `sprendimai`…), prompts are EN+LT mixed,
   ~1 000 Lithuanian literals live in Python (phrases, directives, keyword regexes).
   See D-19.
3. **Behaviour limits are hidden in code** (`A/gate.py DEFAULT_POLICY`, retry caps in
   `walker_flow.py`, `identification_flow.py`…). See D-17.
4. **No validation.** A broken pack is silently skipped; `crc_errors`, `link_down_local`,
   `router_hung` have no fallback at all; bad `on:`/`goto:` targets are only found at runtime.
5. **Latent bug:** the solver gate's known hypotheses come from in-code `STRATEGIES`
   (`A/solver_flow.py` ~L146, ~L425, `known_hypotheses=set(STRATEGIES)`), so for
   `router_hung`, `link_down_local`, `crc_errors` a `propose_fix` is downgraded to `verify`.

## 2. Before → After

```
BEFORE                                        AFTER
K/faults.yaml   problems (LT keys)            K/intents.yaml        (moved in M6; keys EN now)
K/faults/*.yaml LT keys + LT customer text    K/faults/*.yaml       EN keys, text by phrase key, step roles
K/modules/*.yaml modulis/isejimai             K/modules/*.yaml      module/exits
K/identification.yaml  phrases LT             K/identification.yaml EN policy knobs only
K/informavimas.yaml sakoma                    K/inform.yaml         EN keys, template = phrase key
K/faq.yaml tema/raktazodziai/atsakymas        K/faq.yaml            topic, keywords/answer = locale keys
K/endpoint.yaml tesiniai                      (vocabulary → locale)
K/detectors.yaml LT glosses                   K/detectors.yaml      EN structure, glosses → locale
(none)                                        K/policies.yaml       forbidden actions/topics, consent defaults
(Python constants)                            K/limits.yaml         all numeric thresholds (§3.6)
(none)                                        K/verdicts.yaml       verdict flags (line_fault, healthy, device_visible…)
config/i18n/{lt,en}/messages.yaml             locales/lt/phrases.yaml     every customer-facing sentence
Python LT literals / regexes                  locales/lt/vocabulary.yaml  triggers, answer markers, farewells…
P/*.md mixed EN/LT                            locales/lt/examples/*.md    few-shot dialogues, style examples
                                              P/*.md                EN only, {output_language}, <<examples:…>>
(no validation)                               A/contract/schema.py pydantic models + cross-ref checks at load
```

Location of `locales/`: `chatbot_core/src/agent/locales/<lang>/`.
Language selection: `AgentConfig.language` (default `lt`), passed via runtime context (M2).

## 3. Affected files

**Create**
- `A/contract/` package (code; `K/` stays data-only): `schema.py` (pydantic models for pack, module, intents, inform,
  faq, detectors, policies, limits, verdicts), `loader.py` (single loader + validation +
  `reload()`), `locale.py` (`phrase(key, **vars)`, `vocab(name)`, `examples(name)` for the
  active language; missing key → hard error at load, not at runtime).
- `A/locales/lt/phrases.yaml`, `A/locales/lt/vocabulary.yaml`, `A/locales/lt/examples/`.
- `K/policies.yaml`, `K/limits.yaml`, `K/verdicts.yaml`.
- Tests: `chatbot_core/tests/test_knowledge_schema.py` (every file validates; cross-refs;
  every phrase key referenced by packs/code exists in `locales/lt`), `test_locale.py`.

**Rewrite (keys to EN, text to locale keys)**
- `K/faults/*.yaml` (6 packs), `K/modules/*.yaml` (2), `K/identification.yaml`,
  `K/informavimas.yaml` → rename `K/inform.yaml`, `K/faq.yaml`, `K/detectors.yaml`,
  `K/endpoint.yaml` (content → `vocabulary.yaml`, file deleted).
- All prompt files in `P/` → English; LT examples to `locales/lt/examples/`.
- Inline prompts moved to files `P/sensors/`: `classifier.md`, `solver.md`, `analyst.md`,
  `ticket_reader.md` (from `A/classifier.py:45-63,85-86`, `A/solver.py:70-107`,
  `A/analyst.py:27-43,104-127`, `A/understand.py:198-228`), `problem_classifier.md`
  (`A/nlu.py:255-256`).

**Modify (consumers)** — every reader listed in §4 tables; main ones:
`A/faults.py`, `A/evidence.py`, `A/evidence_drive.py`, `A/perception_flow.py`,
`A/walker_flow.py`, `A/walker_guards.py`, `A/solver_flow.py`, `A/executor_flow.py`,
`A/identification.py`, `A/identification_flow.py`, `A/informavimas.py`, `A/faq.py`,
`A/detectors.py`, `A/endpoint.py`, `A/understand.py`, `A/nlu.py`, `A/resolution.py`,
`A/glossary.py`, `A/closing_flow.py`, `A/barge_in.py`, `A/ticket_flow.py`,
`A/dialog_registry.py`, `A/speculation.py`, `A/analyst.py`, `A/narrator_flow.py`,
`A/voice_pipeline.py`, `A/playbook.py`, `app/voice.py`, `app/main.py`,
`adapters/asr/lt_text.py` (stays LT-specific but reads number words / hallucination
markers / domain prompt from `locales/lt/`).

**Delete (in this milestone)**
- `A/resolution.py` in-code `STRATEGIES` (`_FOREIGN_MAC`, `_CLIENT_SIDE`, `_DEAD_ROUTER`,
  `_UNCLEAR_FAULT`) → `unclear_fault` becomes a built-in pack file `K/faults/unclear_fault.yaml`.
- `tests/data/strategies_snapshot.json` and the snapshot tests in `tests/test_fault_packs.py`
  that compare against it (replace with schema tests).
- Duplicate defaults: `identification._PHRASES_DEFAULTS`, `_CALLER_QUESTION_DEFAULT`,
  `resolution.DETECTOR_GLOSSES`, `detectors._EXTRA_DEFAULTS`, `endpoint._DEFAULT_TRAILING`,
  `nlu._PROBLEM_KEYWORDS`, `glossary.py` (whole file → locale), `evidence.LABELS`/`VALUE_LT`.
- `config/i18n/` and `services/language_service.py` (replaced by `A/contract/locale.py`).
- `faults.yaml` `faults: {}` monolith merge in `A/faults.py`.
- `meta.tags`, `meta.domenas`, `meta.pavadinimas` readers/tests if still unused
  (`find_by_tag`, `depends_on` are replaced by the service dependency file in M6).

## 4. Rename tables (authoritative)

### 4.1 Pack keys (`K/faults/*.yaml`)

| Old | New | Notes |
|---|---|---|
| `meta.vairuotojas` | `meta.driver` (temporary) | deleted in M4 step 1 (D-03, single driver) |
| `meta.pavadinimas` | `meta.title` | |
| `meta.domenas` | `meta.domain` | |
| `meta.priklauso_nuo` | — | delete; dependencies move to M6 service catalog |
| `evidence.client.<key>` | `evidence.client.<key>` | evidence keys themselves → EN (table 4.3) |
| `.label`, `.reiksmes` | `.label_key`, `.value_label_keys` | values are locale keys |
| `.reikia` | `.goal` | EN LLM directive (not spoken) |
| `.klausimas` / `.paprasciau` / `.patikslinimas` / `.ka_radote` / `.kodel` | `.question_key` / `.simpler_key` / `.clarify_key` / `.ask_result_key` / `.why_key` | locale keys |
| `.reiskia` | `.meaning` | EN, for the LLM |
| `.atsakymai` | `.answers` | value → vocabulary list name in `locales/<lang>/vocabulary.yaml` |
| `.zingsnis` | `.step_role` | points to a step **role**, not id |
| `.kada` | `.when` | |
| `.patikslinti` | `.confirm_values` | |
| `.formuluote: skriptas` | `.wording: scripted` | |
| `evidence.patvirtinta_kai` | `evidence.confirmed_when` | `[]` keeps meaning "confirmed by telemetry" |
| `evidence.paneigta_kai` | `evidence.refuted_when` | |
| `evidence.paneigta_veda` | `evidence.on_refuted` | target = step role |
| `reikalinga` | `ticket_need_key` | spoken + ticket text |
| `isvada` | `conclusion_key` | |
| `pasiulymas` | `offer_goal` | EN directive |
| `tiltas_nepavyko.pastaba` / `.prierasas` | `bridge_failed.notice_key` / `.ticket_note_key` | |
| `sprendimai[]` → `jei` / `tada` / `zingsnis` / `aprasymas` | `solutions[]` → `when` / `action` / `step_role` / `description_key` | `action ∈ procedure, bridge, ticket` (`walker` → `procedure`) |
| `steps[].tikslas` | `steps[].goal` | EN |
| `steps[].kaip` | `steps[].as` | |
| `steps[].hint` | `steps[].hint` | EN only; LT examples → `locales/lt/examples/<pack>.md` referenced by `examples_key` |
| (new) `steps[].role` | required | table 4.4 |
| (new) `steps[].consent` | `required \| not_required` | D-16, for `kind: action` |
| condition token `patvirtinta` | `confirmed` | |
| condition token `tilto_fazeje` | `bridge_phase` | implement a real handler (today `_cond_holds` returns False) |

### 4.2 Modules, catalog, other files

| File | Old → New |
|---|---|
| modules | `modulis`→`module`, `isejimai`→`exits`, values `pavyko`/`nepavyko`→`success`/`failure`, ids `patikrinti_ar_atsirado`→`verify_restored`, `priristi_mac`→`bind_mac` |
| `faults.yaml problems` (renamed in M6 to `intents.yaml`) | `aprasymas`→`description` (EN), `pavyzdziai`→`examples_key`, `politika`→`policy` with values `sprendzia`→`solve`, `registruoja`→`register`, `nelieciam`→`not_ours`, `pokalbis`→`chat` (D-11; `answer` added in M6), `patvirtinimas`→`confirm_question_key`, `atsakymas`→`boundary_reply_key`, `triggers`→`triggers_vocab` (vocabulary name); ids `saskaitos`→`billing`, `pokalbis`→`chat`, `kita_ne_musu`→`not_ours` |
| `informavimas.yaml` → `inform.yaml` | `sakoma`→`template_key`, `aiskumo_salyga`→`clarity_requirements` (values `what_is_wrong`, `what_to_do`, `what_is_being_done`, `when_restored`, `how_notified`); placeholders `{suma}{menesiai}{pask_mokejimas}{vieta}{eta}`→`{amount}{months}{last_payment}{location}{eta}` |
| `faq.yaml` | `tema`→`topic` (`kaina`→`price`, `skolos_suma`→`debt_amount`, `kiek_uztruks`→`duration`, `meistras`→`technician`, `darbo_laikas`→`working_hours`), `raktazodziai`→`keywords_vocab`, `atsakymas`→`answer_key` |
| `endpoint.yaml` | `tesiniai` → `vocabulary.yaml: continuation_words`; delete file |
| `identification.yaml` | keys already EN; `phrases:` block moves to `locales/lt/phrases.yaml` under `identification.*`; placeholders → `{address}{news}{reason}{phone}{hours}{topic}{a}{b}{anchor}{facts}{solutions}{question}{value}{letters}{street}{code}` |
| LLM JSON contracts | perception: `faktai`→`facts`, `tipas`→`type` (`atsakymas|klausimas|nukrypimas|nesupratimas|prieštaravimas` → `answer|question|deviation|confusion|contradiction`), `supratau`→`understood`, `neaiskumas`→`confusion`, `pasitikejimas`→`confidence`, `zingsnis`→`step`; ticket reader: `reiksme`→`value`, `tipas`→`type` (`answer|question|refusal|other`), `tas_pats`→`same_number` |
| Playbooks `rag/knowledge_base/troubleshooting/*.md` | stay Lithuanian content for now (they are locale content) → move to `locales/lt/playbooks/`; heading marker `### Žingsnis N` becomes `### Step N` **or** steps reference `playbook_section: <anchor>` instead of a positional index. Update `A/playbook.py:22` and `rag/document_processor.py:154-179` together. |

### 4.3 Evidence keys and value enums (compared in Python)

| Key | Old values → New |
|---|---|
| `ivykiai` → `recent_events` | `buvo/nebuvo` → `yes/no` |
| `device_present` | `rado/nerado` → `found/not_found` |
| `lights` | `dega/nedega/mirksi` → `on/off/blinking` |
| `power_cable` | `įkištas/atjungtas` → `plugged/unplugged` |
| `outlet_works` | `bandyta/neveikia` → `tried/not_working` |
| `lan_active` | `aktyvus/neaktyvus` → `active/inactive` |
| `fail_scope` | `visuose/viename` → `all/one` |
| `fail_device` | `telefonas/kompiuteris` → `phone/computer` |
| `connection_type` | `laidas/wifi` → `wired/wifi` |
| `rebooted` | `perkrautas/neperkrautas` → `yes/no` |
| `changed_device` | `keite/nekeite` → `yes/no` |
| give-up marker | `neaišku` → `unknown` |
| LAN fallback | `nepatikrinta` → `not_checked` |

Python readers to update: `A/evidence.py` (~L30-53, 76, 141, 175-229, 321, 433-484, 514-516),
`A/understand.py` (~L31-44), `A/evidence_drive.py` (~L34, 137, 372), `A/perception_flow.py`
(~L212, 246, 309), `A/solver_flow.py` (~L274, 553-573, 668-690), `A/speculation.py` (~L94).
Evidence-key vocabulary that is pack-specific (`has_computer`, `lan_active`, `power_cable`,
`outlet_works`, `device_present`) must come from pack `evidence` definitions; the built-in
extraction regexes in `A/evidence.py` move to `locales/lt/vocabulary.yaml` keyed by evidence key.

### 4.4 Step roles (replace hardcoded ids — D-18)

| Hardcoded today | Where (re-grep) | Role |
|---|---|---|
| `confirm_restored` | `A/walker_flow.py` ~230, 301; `A/walker_guards.py` ~223; `A/perception_flow.py` ~48 | `verify_restored` |
| `client_side` | `A/walker_flow.py` ~783 | `client_side_check` |
| `rh_check` | `A/walker_flow.py` ~306, 477, 807 | `verify_reboot` |
| `rh_reboot_retry` | `A/walker_flow.py` ~943 | `reboot_retry` |
| `rh_device` | `A/walker_flow.py` ~931 | `device_path` |
| `ll_recheck`, `crc_recheck` | `A/walker_flow.py` ~311, 485 | `verify_line` |
| `dr_see_device` | `A/walker_flow.py` ~230, 315, 467 | `verify_device_visible` |
| `dr_bind` | `A/walker_flow.py` ~695; `A/solver_flow.py` ~628 | `bind_device` |
| `dr_pick_cable` | `A/walker_flow.py` ~701 | `locate_cable` |
| `dr_register_router` | `A/executor_flow.py` ~219; `A/solver_flow.py` ~712 | `register_after_bridge` |
| `confirm_change` | `A/walker_guards.py` ~84 | `confirm_device_change` |
| step id `escalate` | many (grep `"escalate"`) | lookup by `kind: escalate` |
| suffix `_ability` / `_locate` / `_homework` | `A/dialog_registry.py` ~70-80; `A/walker_guards.py` ~98, 168; `A/walker_flow.py` ~752; `A/perception_flow.py` ~1091, 1112; `A/react_agent.py` ~1229 (gone after M1/M5) | `ability_check` / `locate_device` / `homework` |

Terminals `resolve`, `callback`, `end` stay as reserved EN goto targets.

Verdict-specific checks move to `K/verdicts.yaml` flags:

| Hardcoded | Where | Flag |
|---|---|---|
| `_UNRESOLVED_LINE_FAULTS` | `A/react_agent.py` ~534 → used in `walker_flow`, `executor_flow` | `line_fault: true` |
| `line_bad` set | `A/walker_flow.py` ~836-842 | `line_fault: true` |
| `healthy_to_router` check | hang-up net | `healthy_up_to_router: true` |
| `no_mac_observed` checks | `A/walker_flow.py` ~689; `A/solver_flow.py` ~547 | `device_visible: false` |
| inform verdicts (`billing_suspended`, `active_outage`, `node_fault_unregistered`, `switch_unreachable`) | `A/informavimas.py`, `A/identification_flow.py` ~1431-1445, `A/closing_flow.py` ~80, `A/narrator_flow.py` ~472 | `inform: true`, `auto_ticket: true/false`, `close_reason: outage/inform` |
| gate `known_hypotheses=set(STRATEGIES)` | `A/solver_flow.py` ~146, 414, 425 | derive from loaded packs (fixes the latent bug) |

## 5. Step-by-step

Each step = one commit (English message), full test suite green before committing.
Run `uv run pytest` from the repo root after every step.

1. **Schema models, no behaviour change.** Create `A/contract/schema.py` with pydantic
   models for the *current* (LT) keys and a test that all existing files validate. Add
   cross-reference checks: `on`/`goto`/`paneigta_veda`/`zingsnis` targets exist, `answers`
   keys ⊆ `on` keys, detector names exist, `use:` modules exist, `rag_section` < number of
   playbook sections. Fix any file that fails (report fixes in the commit message).
2. **Locale layer.** Create `A/contract/locale.py` and `A/locales/lt/phrases.yaml`.
   Move `identification.yaml phrases`, `config/i18n/lt/messages.yaml`, `informavimas.yaml
   sakoma/fallback`, `faq.yaml atsakymas`, pack spoken fields (§2 of research: `klausimas`,
   `paprasciau`, `patikslinimas`, `ka_radote`, `kodel`, `reikalinga`, `isvada`,
   `tiltas_nepavyko.pastaba`, `patvirtinimas`, `atsakymas`, labels/value labels) into it with
   namespaced keys (`identification.*`, `system.*`, `inform.*`, `faq.*`,
   `pack.<verdict>.<evidence_key>.question`, …). Replace readers with `phrase(key)`.
   Delete `identification._PHRASES_DEFAULTS`, `language_service.py`, `config/i18n/`.
3. **Customer-facing Python literals → phrases.** Move the literals listed in §6.1 into
   `phrases.yaml`. Grep check at the end: no Lithuanian customer sentence remains in
   `A/` except in `locales/`.
4. **Vocabulary → locale.** Move keyword/regex vocabularies (§6.2) to
   `locales/lt/vocabulary.yaml` as named lists; `A/resolution.py` detectors,
   `A/nlu.py`, `A/evidence.py`, `A/closing_flow.py`, `A/barge_in.py`, `A/endpoint.py`,
   `A/ticket_flow.py`, `A/identification.py`, `A/identification_flow.py`,
   `A/perception_flow.py`, `A/walker_guards.py`, `A/solver_flow.py`, `A/speculation.py`,
   `A/analyst.py`, `rag/hybrid_retriever.py` stopwords read lists via `vocab(name)`.
   Lithuanian-specific *algorithms* (diacritic folding `_FOLD`, number words, ASR
   hallucination markers) stay in a `A/locales/lt/lang.py` module exposing a small
   interface (`fold`, `normalize_numbers`, `asr_domain_prompt`) selected by language.
   Fix `A/ticket_flow.py` ~L68 logic that compares Lithuanian reason text — use a reason enum.
5. **Step roles + verdict flags.** Add `role:` to every step of the 6 packs and 2 modules;
   add `K/verdicts.yaml`; replace every hardcoded id/suffix/verdict set from §4.4 with role /
   flag lookups (`faults.step_by_role(verdict, role)`, `verdicts.flag(verdict, name)`).
   Acceptance grep (must return nothing outside `K/` and tests):
   `rh_check|rh_device|rh_reboot_retry|ll_recheck|crc_recheck|dr_see_device|dr_bind|dr_pick_cable|dr_register_router|confirm_restored|confirm_change|client_side|_ability|_locate|_homework`.
6. **Unclear fault as a pack; delete in-code STRATEGIES.** Create
   `K/faults/unclear_fault.yaml`; make `get_strategy` use packs only; derive the solver's
   known hypotheses from loaded packs (fixes §1.5); delete `STRATEGIES`, `_FOREIGN_MAC`,
   `_CLIENT_SIDE`, `_DEAD_ROUTER`, `_UNCLEAR_FAULT`, `strategies_snapshot.json` and snapshot
   tests. Add a test: `router_hung` `propose_fix` is accepted by the gate.
7. **Rename schema keys to English.** Apply tables 4.1–4.3 to all YAML files, schema
   models and readers in one commit per file family (packs+modules; catalog; inform/faq/
   detectors; evidence enums; LLM JSON contracts). `meta.vairuotojas` is renamed to a
   temporary `meta.driver` (`solver|walker`) because the walker still drives two packs
   until M4; M4 step 1 deletes it.
8. **Prompts in English.** Rewrite every file in `P/` in English. Output language comes
   from `{output_language}`; LT few-shots (`stages/diagnosis.md <expert_voice>`,
   `partials/identity.md` reactions/vocatives, `sensors/perception*.md` examples, style
   examples) move to `locales/lt/examples/*.md` and are included with
   `<<examples:name>>` resolved by the prompt loader for the active language.
   Move inline prompts (§3 Rewrite list) to `P/sensors/*.md`. Delete orphaned
   `P/partials/consultation.md`, `P/partials/understanding.md`, `P/greeting.txt`,
   `get_prompt_path`. Make the prompt loader fail at startup on a missing include.
   Note: the ~124 Lithuanian directive strings in `A/narrator_flow.py state_facts_block`
   are rewritten in **M5** (speak node) — do not translate them twice; only move
   customer-facing sentences found there to phrases in step 3.
9. **Policies and limits.** Create `K/limits.yaml` with every constant from §6.3 and
   `K/policies.yaml` (forbidden actions/topics, per-action consent defaults — content is
   filled later with the owner; start with what code enforces today). Replace constants
   with `limits.get("name")`. `consent` for actions is read by the gate in M4.
10. **Single loader + reload.** All knowledge files load through `A/contract/loader.py`
    at startup (fail fast with a readable error listing file/key), cached, with one
    `reload()` used by tests and the admin config endpoint.

## 6. Inventories to work from (re-verify with grep)

### 6.1 Customer-facing Lithuanian in Python
- `A/identification.py` ~35, 75-158 (defaults duplicating YAML)
- `A/react_agent.py` ~125-128 (`_STUCK_OFFER_CODE`, `_STUCK_REGISTER`) — if still present
- `A/solver_flow.py` ~467-470, 491, 513, 539, 584-587, 599-604, 662-664, 675-677, 684, 692, 723-725
- `A/identification_flow.py` ~1206; `A/perception_flow.py` ~528 (default anchor)
- `A/voice_pipeline.py` ~214 (`_FILLER_TEXT`), ~68-75 (TTS address normalisation → `lang.py`)
- `A/informavimas.py` ~23-32, 49-64, 75 (month names, euro plural grammar → `lang.py`)
- `A/glossary.py` ~11-45 (`DIAGNOSIS_LT`, `PROBLEM_LT`, `TICKET_NEED_LT`)
- `A/evidence.py` ~30-53, 141 (`LABELS`, `VALUE_LT`, "KONFLIKTAS")
- `A/evidence_drive.py` ~283, 293; `A/speculation.py` ~122 (" ARBA " joiner)
- `A/nlu.py` ~275-295, 333-350, 369 (symptom/anamnesis labels stored in state → store enum, render via phrases)
- `A/executor_flow.py` ~191-260, `A/ticket_flow.py` ~79, 205, 225 (ticket text — operator-facing; use `locales/lt/phrases.yaml ticket.*`)
- escalate reasons: `A/walker_flow.py` ~753, 845-858; `A/walker_guards.py` ~171-178 → reason enum + phrase

### 6.2 Vocabularies (regex/keyword lists)
`A/resolution.py` ~683-1725 (all detector regexes: `_NEG`, `_POS`, `_DEVICE_CHANGE`,
`_RESTORED_*`, `_REBOOT_*`, scope/conn/port/lights/device, `_FAREWELL`, `_CONFUSED`,
`_IN_PROGRESS`/`_DONE`/`_QUESTION`, `_CONSENT_*`, address confirm, `_CANNOT_NOW`,
`_TICKET_*`, `_NO_DEVICE`, `_GREETING`, `_PLUGGED`, farewell tokens, `_BACKCHANNEL`,
`_NEGATION_TOKENS`, `_DONE_STEMS`/`_ACKS`, `_QUESTION_TOKENS`); `A/evidence.py` ~152-221,
433-484, 514; `A/nlu.py` ~30, 141, 159, 187-192, 222-234, 272-296, 307, 333-350;
`A/identification.py` ~171-270; `A/identification_flow.py` ~175-295, 554, 574, 583,
595-615, 764, 825-840, 886, 912-938, 1100-1143, 1346-1355; `A/perception_flow.py` ~267,
631-659, 728, 748, 863-875, 888, 945-970, 1140, 1180; `A/ticket_flow.py` ~22-37, 250-255;
`A/walker_guards.py` ~104-108; `A/solver_flow.py` ~182-193, 273-275; `A/closing_flow.py`
~18-26; `A/barge_in.py` ~23-53, 91; `A/endpoint.py` ~35-39; `A/understand.py` ~31-44;
`A/speculation.py` ~262-264; `A/analyst.py` ~52-75, 158; `A/react_agent.py` ~113-121;
`A/playbook.py` ~22; `adapters/asr/lt_text.py` ~28-39, 96-105, 109-257;
`A/session.py` ~130, 145; `rag/hybrid_retriever.py` ~92-114; `rag/document_processor.py` ~154-179.
Service-area constants (Šiauliai): `A/identification_flow.py` ~574, 886, `P/partials/region.md`,
`lt_text.py` ~96-105 → `K/service_area.yaml` (business config, not language).

### 6.3 Numeric limits → `K/limits.yaml`
`A/gate.py` ~37-42 (`DEFAULT_POLICY`); `A/react_agent.py` ~619 (`_DRIVE_MAX_TURNS`),
~1901, 1908-1911 (similarity, stuck backstop); `A/solver_flow.py` ~38, 98, 322, 397;
`A/identification_flow.py` ~495 (`GATE_MAX_TURNS`), 511-535, 565-568, 638, 664, 852, 899,
930, 942, 966, 982, 1211; `A/nlu.py` ~25-26; `A/evidence_drive.py` ~151, 358, 369;
`A/walker_flow.py` ~124, 358, 421, 520, 698, 786, 814, 940, 982, 1013; `A/understand.py`
~136-141, 160, 178, 230; `A/narrator_flow.py` ~255, 384, 393, 407, 456, 629-641, 778, 792,
1102, 1157; `A/closing_flow.py` ~40; `A/graph_v2/nodes/closing.py` ~109; `A/config.py`
~49-92 (`max_turns` 50 vs state 20 — unify); `A/analyst.py` ~106, 121, 137, 144;
`A/speculation.py` ~100, 182, 262; `A/classifier.py` ~91; `A/solver.py` ~125;
`A/endpoint.py` ~67-75; `A/barge_in.py` ~55-56; `A/resolution.py` ~1507, 1615, 1673, 1689;
`A/perception_flow.py` ~682, 788, 829, 855, 918; `A/verdict.py` ~29, 35;
`app/voice.py` ~182, 252, 283; `app/main.py` ~395, 450; `A/voice_pipeline.py` ~63;
`A/session.py` ~146; `lt_text.py` ~42. Env-var overrides (`GATE_MAX_TURNS`,
`IDENT_MAX_TURNS`, `ENDPOINT_*_MS`, …) keep working: env wins over the file.

## 7. Tests

- New: `test_knowledge_schema.py` (all files valid, cross-refs, every referenced phrase/vocab
  key exists for `lt`, no LT schema keys remain), `test_locale.py` (missing key fails at load;
  placeholder rendering; language switch loads a stub `locales/xx/` fixture without code change).
- New: gate accepts `propose_fix` for every pack verdict (latent bug regression).
- Update: tests asserting Lithuanian keys, step ids or phrases (`test_fault_packs.py`,
  `test_line_faults.py`, `test_resolution.py`, `test_router_hung.py`,
  `test_identification_rules.py`, `test_informavimas.py`, `test_detectors.py`,
  `test_classification.py`, `test_understand.py`) — assert on roles/keys/enums, and on
  phrases via `phrase(key)` rather than literal copies.
- Delete: strategy snapshot tests; tests for deleted defaults/duplicates.
- Eval: `cd chatbot_core && uv run python src/agent/eval/run_eval.py` — all scenarios pass
  (reply substrings in `scenarios.json` stay Lithuanian — that is customer output).

## 8. Definition of Done

- `uv run pytest` green; eval green (same pass count as the M0 baseline or better).
- Acceptance greps return nothing outside `K/`, `locales/` and tests:
  - step ids/suffixes (step 5 list);
  - Lithuanian schema keys: `vairuotojas|patvirtinta_kai|paneigta_kai|paneigta_veda|sprendimai|reikalinga|pasiulymas|tiltas_nepavyko|isejimai|modulis|politika|aprasymas|sakoma|raktazodziai|tesiniai`;
  - `STRATEGIES =`, `DETECTOR_GLOSSES`, `_PHRASES_DEFAULTS`, `_PROBLEM_KEYWORDS`.
- `grep -rP "[ąčęėįšųūž]" chatbot_core/src/agent --include=*.py` returns only
  `locales/lt/lang.py` (and comments explicitly marked as examples, if any).
- All prompts in `P/` are English.
- Starting the app with a deliberately broken pack fails at startup with a clear message.
- A live voice call on scenario "pakibęs routeris" behaves as before (owner check).

## 9. Risks & rollback

- **Behaviour drift from vocabulary moves** (regex order/anchors matter, e.g. `\bjo\b`).
  Move lists verbatim; keep the exact regex strings; tests on detectors must stay green
  before any cleanup.
- **Prompt translation changes model behaviour.** Translate one prompt family per commit
  and run eval after each; if a scenario regresses, compare `llm_input` traces
  (`DEBUG_LLM=on`) before/after.
- **Big-bang rename.** Do renames per file family with the schema model updated in the
  same commit; the load-time validator catches missed keys.
- Rollback = revert the milestone's commits (each step is one commit).

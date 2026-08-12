# LangGraph v2 refaktoringo planas — „super agento" kelias

> Šaka: `refactor/langgraph-v2` · Sudaryta: 2026-08-12 (Andrius + Claude)
> Papildo bendrą [ROADMAP.md](ROADMAP.md) (šis dokumentas = atskiras refaktoringo takelis,
> vykdomas lygiagrečiai su Phase 4.6+ darbais).
>
> **Tikslas:** perstatyti agento griaučius taip, kad (1) mąstymas ir užduočių vykdymas
> būtų kuo geresni, (2) naujas gedimas / nauja užduotis pridedama be variklio perrašymo,
> (3) agentas bendrautų kaip IT specialistas, (4) delsa balso kanale kristų.
> Struktūrą keičiame PIRMIAUSIA, kad visi tolesni patobulinimai būtų lipdomi
> ant naujų griaučių ir nereikėtų perdarinėti.

---

## 1. Dabartinė padėtis (2026-08-12 auditas)

- LangGraph sluoksnis **plonas ir dekoratyvinis**: 4 mazgai (`address_validation`,
  `diagnosis`, `ticket_registration`, `closing`) + `side_topic` sub-mazgas, visi eina
  tiesiai į `END`; vienintelis šakojimasis — `route()` įėjime (`agent/graph.py`).
  Grafo `TurnState` laiko tik `user_input`/`reply`.
- **Tikroji būsenų mašina — `ReactAgent` monolite** (`agent/react_agent.py`,
  ~5500 eil., ~130 metodų): walker (`_walk_resolution` + 15 guard'ų), evidence drive,
  solver+gate, tiketo dialogas, identifikacijos skriptas, naratoriaus streaming.
- `AgentState` (dataclass, `agent/state.py`) gyvena variklyje, ne grafe;
  checkpointer `MemorySaver` nieko vertingo nesaugo.
- Solveris („mąstymas") įjungtas tik verdiktui `no_mac_observed`; strategijos
  kietai užkoduotos `resolution.py` (58 KB Python).
- Delsa: per vieną balso turn'ą 2–4 **nuoseklūs** LLM kvietimai
  (understand → solver → classifier → naratorius), visi tuo pačiu `gpt-4o-mini`.

## 2. Tikslinė architektūra

```
                        ┌────────────────────┐
  srautinis STT ──────► │  perception mazgas │  1 greitas LLM: faktai+intentas+žingsnio klasė
                        └─────────┬──────────┘
                                  ▼
                        ┌────────────────────┐
                        │       router       │  conditional edges (buv. route())
                        └─┬────┬────┬────┬───┘
              ┌───────────┘    │    │    └──────────────┐
              ▼                ▼    ▼                    ▼
      identification    side_topic  ticket           closing
              │           (tikras mazgas)
              ▼
      ┌──────────────────── diagnosis SUBGRAFAS ────────────────────┐
      │  diagnose ──► solver+gate ──► walker ──► executor ──► narrator │
      │  (telemetrija)  (hipotezė,     (žingsnio   (tools,     (stream │
      │                  veiksmas)      HOLD/adv)   ticket)     į TTS) │
      └───────────────────────────────────────────────────────────────┘
                                  │
                        SqliteSaver checkpointeris
                        (time-travel, būsena tarp skambučių)
```

Principai:

- **Grafo state = vienintelis tiesos šaltinis.** `GraphState` (Pydantic) perima visą
  `AgentState`; efemeriniai vieno turn'o flag'ai — atskirame `turn:` sub-modelyje,
  kuris resetinamas kas invokaciją ir NEskaitomas kaip istorija.
- **Vienas turn'as = viena grafo invokacija** (kaip dabar). LangGraph `interrupt()`
  HOLD semantikai — atidėta v2.1 (komplikuoja barge-in/cancel kelią).
- **Sprendimų logika lieka gryna ir unit-testuojama** (ROADMAP.md „Design tenets"):
  mazgai plonai apvynioja grynas funkcijas.
- Senasis variklis lieka veikti per `AGENT_ENGINE` jungiklį, kol v2 pasiveja
  (strangler pattern) — demo niekada nelūžta.

## 2.1 Failų struktūra (sutarta 2026-08-12: vienas mazgas = vienas failas)

```
src/agent/graph_v2/
  __init__.py          # vieši eksportai
  state.py             # GraphState, TurnScratch
  router.py            # route_entry() + VISOS maršrutizavimo funkcijos (guard'ai → edges)
  graph.py             # TIK surinkimas: add_node / add_edge / compile
  checkpoint.py        # SqliteSaver gamykla (storage keitimas = vienas failas)
  nodes/
    perception.py      # supratimas + faktai + side-topic klasifikacija
    identification.py  # adreso slot'ai, lookup
    side_topic.py      # tikras mazgas (buvęs sub-kvietimas)
    ticket.py          # 2 klausimų kontaktų dialogas
    closing.py         # atsisveikinimas, call record
    diagnosis/         # subgrafas
      diagnose.py      # telemetrija, verdiktas
      solver_gate.py   # hipotezė + gate
      walker.py        # žingsnių HOLD/advance
      evidence_drive.py# faults.yaml klausinėjimas
      executor.py      # VIENINTELĖ vieta tools + ticket registracijai
      narrator.py      # LLM atsakymas, stream į TTS
```

Taisyklės (kad nereikėtų perdaryti):
- Vienas mazgas = vienas failas su viena viešąja `*_node(state)` funkcija;
  failo docstring'e — kas į jį migruoja iš `react_agent.py`.
- Mazgai tarpusavyje NEsiimportuoja — bendrauja tik per `GraphState`.
- `graph.py` — be jokios logikos; `router.py` — tik grynos funkcijos
  (skaito state, grąžina mazgo vardą; jokių LLM/tool kvietimų, jokių mutacijų).
- Priklausomybės (variklis, tracer, config) įšvirkščiamos per `build_graph()`
  factory/closure — mazgai nesiekia globalių.
- Gryna sprendimų logika lieka `agent/` moduliuose (slots, verdict, resolution,
  evidence, gate) — mazgai ploni.

## 3. Etapai

### R0 — Saugiklis (prieš bet kokį logikos keitimą)

- [x] Šaka `refactor/langgraph-v2` nuo `develop`
- [ ] „Auksiniai" scenarijai: ~10–15 pilnų pokalbių transkriptų kaip regresijos
      etalonai (po kelis kiekvienam verdiktui: `foreign_mac`, `healthy_to_router`,
      `no_mac_observed`, + outage, billing, stuck→eskalacija, side-topic, barge-in).
      Šaltiniai: `demo_scenarios.md`, `agent/eval/`, esami `tests/test_agent.py` atvejai.
- [x] `AGENT_ENGINE=v2` reikšmė `session.py` (šalia esamų `graph`/`legacy`)
- **DoD:** auksiniai testai žali su senuoju varikliu; jungiklis veikia.

### R1 — State migracija  ← **DABARTINIS ETAPAS**

- [x] `agent/graph_v2/state.py`: `GraphState` (Pydantic) — visi `AgentState` laukai
      + `TurnScratch` efemeriniams; `from_legacy()` / `to_legacy()` tilteliai,
      kad abu varikliai migracijos metu dalintųsi ta pačia būsena
- [x] Testai `tests/test_graph_v2_state.py`: pilnas legacy↔v2 round-trip,
      JSON serializacija (checkpointer'io parengtis), slot guard'ų išlikimas
- [x] `SqliteSaver` vietoj `MemorySaver` (`graph_v2/checkpoint.py`,
      `logs/graph_checkpoints.sqlite`; `thread_id=session_id`)
- [x] Time-travel smoke testas: `graph.get_state_history()` grąžina turn'ų seką;
      būsena išgyvena grafo perkūrimą virš to paties db failo
- **DoD:** GraphState serializuojasi be nuostolių; checkpointai rašomi į SQLite. ✔

### R2 — Ploni wrapper'iai (elgesys IDENTIŠKAS)

- [x] `graph_v2/graph.py`: 4 stadijos mazgai atskiruose failuose, kiekvienas kol kas
      kviečia esamus `ReactAgent` metodus (paritetas su `agent/graph.py` — testuota:
      greeting, reply, lookup-only tool gate); `route_entry` — gryna funkcija virš
      GraphState (`ticket_stage` promotintas į state, sinchronizuojamas kas turn'ą)
- [ ] `side_topic` — tikras mazgas (dabar sub-kvietimas `diagnosis` viduje)
- [ ] Diagnozės subgrafo griaučiai: 9 žingsnių seka iš `nodes/diagnosis/__init__.py`
      tampa mazgais su paprastomis briaunomis (dar be guard'ų perkėlimo)
- [ ] Token streaming per `get_stream_writer()` patikrintas gyvu balso skambučiu
- [ ] `request_cancel` (barge-in) kelias patikrintas gyvu balso skambučiu
- **DoD:** auksiniai testai žali su `AGENT_ENGINE=v2`; trace'ai rodo tuos pačius
  `node` įvykius; elgesio skirtumų nėra.

### R3 — Logikos perkėlimas (po vieną metodą, po vieną guard'ą)

- [ ] Metodai iš `react_agent.py` keliauja į mazgų modulius pagal žemėlapį §4;
      kiekvienas perkėlimas — atskiras commit'as su žaliais testais
- [ ] 15 walker guard'ų (§5) virsta conditional edges / routing funkcijomis —
      perkeliame po 2–3, ne visus iš karto
- [ ] Efemeriniai `_flag'ai` (§6) → `TurnScratch` arba lieka mazgo lokalūs
- [ ] `react_agent.py` traukiasi iki LLM kvietimo + naratoriaus pagalbininkų
- **DoD:** `react_agent.py` < ~1500 eil.; visa maršrutizacija matoma grafe;
  auksiniai testai žali.

### R4 — Smegenys ant naujų griaučių

- [ ] **Percepcijos suliejimas:** understand + intent + step-classifier → VIENAS
      greito modelio kvietimas su structured output (delsa −0,5–1,5 s/turn)
- [ ] **Solveris — centrinis:** įjungiamas visiems verdiktams (ne tik
      `no_mac_observed`); walker tampa solverio įrankiu „vykdyk procedūrą";
      gate.py lieka saugikliu be pakeitimų
- [ ] Modelių tiering: percepcija — greitas modelis, solveris — stipresnis
- **DoD:** eval rinkinio baigtys ne blogesnės; vidutinė turn delsa išmatuojamai krito.

### R5 — Plečiamumas ir persona

- [ ] **Gedimų paketai (fault packs):** deklaratyvus formatas — YAML
      (simptomai → reikalingi įrodymai → hipotezės sąlygos → testai → fix'ai →
      eskalacija) + KB markdown žingsniai. `resolution.py` strategijos GENERUOJAMOS
      iš paketų. Migruojame 3 esamas; įrodymas — naujas gedimas pridėtas VIEN failais.
- [ ] **IT specialisto persona:** paketuose „eksperto paaiškinimo" laukas
      (kodėl taip nutinka — naratorius jį gauna), few-shot eksperto dialogai stage
      promptuose, pasitikėjimo kalba („beveik tikrai X", „dar negaliu atmesti Y")
- [ ] Balso delsa: srautinis STT (daliniai transkriptai), filler įjungimas,
      retry/rate-limit streaming kelyje
- **DoD:** naujas gedimas = YAML + MD, nulis Python; klausytojo testas
  „skamba kaip technikas, ne skriptas".

## 4. Metodų migracijos žemėlapis (`react_agent.py` → mazgai)

| Naujas mazgas / modulis | Kas persikelia |
|---|---|
| `perception` | `_ingest_client_evidence`, `understand.understand`, `classify_side_topic`, `_prefill_slots_from_text` |
| `router` | `route()` (graph.py) + `_pre_turn_guards` maršrutinė dalis |
| `identification` | `_identification_scripted_reply`, `_reopen_identification`, `_preflight_phone`, `_revalidate_accumulated_address` |
| `diagnose` | `ensure_diagnosed`, `_refresh_diagnosis`, `_fresh_diagnose_reason` (verdict.py jau atskiras) |
| `solver_gate` | `solver_drive_turn`, `_drive`, `_shadow_solve`, `_build_solver_context` (+ gate.py be pakeitimų) |
| `walker` | `_walk_resolution`, visi `_advance_*`, `_detect_confirm`, `_route_to`, `_goto_step`, `_turn_may_advance` |
| `evidence_drive` | `_evidence_drive`, `_maybe_facts_recap`, `_maybe_refute_confirm`, `_revive_gave_up_key`, `_negation_clarify_reply` |
| `executor` | `ensure_action_done`, `_gate_tool`, `_execute_tool_calls`, `_register_ticket_from_state`, `_simulate_bridge_connection` |
| `ticket` | `_begin/_finish_ticket_dialogue`, `_ticket_stage_reply`, `_ticket_need`, `_abort_ticket_to_solving`, `_wants_to_keep_solving` |
| `narrator` | `_build_messages`, `_state_facts_block`, `_run_until_response_stream`, `_scoped_tools_schema`, repeat guard (`_track_stuck`, `_stuck_backstop`) |
| `closing` | `_maybe_finish`, `_maybe_close_inform`, `_maybe_end_on_goodbye`, `end_session` |

## 5. Walker guard'ų grandinė (perkėlimo tvarka — atsargiai, čia elgesio auksas)

Iš `_walk_resolution` (react_agent.py:2509–2699), perkeliame grupelėmis po 2–3:

1. `_resume_hold` (klientas atsisakė baigti)
2. `_end_confirm_pending`
3. device-change pre-answer ant `confirm_change`
4. `is_backchannel` ant CONFIRM/INSTRUCT
5. `detect_restored==YES` pre-answer
6. `detect_refuse_or_ticket` → escalate/dialogas
7. `_evidence_question_open` (klausimo nuosavybė)
8. classifier CONFIRM routing
9. classifier INSTRUCT routing
10. ESCALATE → `_advance_escalate`
11. `_turn_may_advance` intent gate
12. `confirm_restored` → `_advance_restored`
13. `dr_see_device` → `_advance_see_device`
14. INSTRUCT/ACTION su `asked` → `_advance_instruct`
15. `asked` + freshness → `_detect_confirm` → `_route_to`

## 6. State laukų klasifikacija

**Į `GraphState` (checkpointinama):** visas dabartinis `AgentState` — profilis su
slot'ais, evidence ledger, hypothesis/failed_hypotheses, resolution pozicija,
stuck/awaiting/clarity, tiketo laukai, skaitliukai.

**Į `TurnScratch` (resetinama kas turn'ą, NEcheckpointinama kaip istorija):**
`user_input`, `reply`, `_cancel_requested`, `_side_topic_this_turn`,
`_pending_announce`, `_active_node`, `_active_tool_names`, `_node_prompt`,
`_turn_start_key`, `_repeated_verbatim`.

**Sprendžiama R3 metu (kandidatai į GraphState, nes gyvena ilgiau nei turn'ą):**
`_ticket_stage`, `_ticket_ctx`, `_bridge_bound`, `_bridge_fail_stage`,
`_evidence_asks`, `_revived_keys`, `_recap_state`, `_refute_state`,
`_drive_turns/_drive_disabled`, solver skaitliukai, `_end_confirm_pending`,
`_resume_hold`, `_news_told`, `_done_report_key`, `_findings_announced`.
Taisyklė: jei flag'as turi išgyventi tarp turn'ų — jis eina į GraphState su
normaliu vardu (be `_`); jei ne — į TurnScratch.

## 7. Rizikos ir taisyklės

- **Mažais žingsniais:** vienas metodas / 2–3 guard'ai per commit'ą, visada žali
  auksiniai testai. Jokių „big bang" perkėlimų.
- **Guard'ų grandinė** — didžiausia rizika: joje sukaupta sunkiai uždirbta elgesio
  logika (repeat guard, question ownership, backchannel). Perkeliant tikrinti
  trace'us, ne tik unit testus.
- **Streaming ir cancel:** `get_stream_writer()` iš subgrafo + `request_cancel`
  kelias — patikrinti R2 pabaigoje su tikru balso skambučiu.
- **Checkpointinama tik tai, kas serializuojasi:** jokių gyvų objektų (tracer,
  LLM klientai) GraphState viduje — jie lieka mazgų closure'uose.
- **`main` = gyvas demo** (ROADMAP.md taisyklė): viskas per PR į `develop`,
  demo niekada nelūžta.

## 8. Testavimo strategija

- Unit: esami `tests/test_*` lieka žali (arba adaptuojami su aiškiu commit'u „kodėl").
- Regresija: auksiniai transkriptai leidžiami per ABU variklius
  (`AGENT_ENGINE=graph` vs `v2`) ir lyginamos baigtys + žingsnių sekos.
- Eval: `agent/eval/fuzz.py` skambintojo simuliatorius — plėsti iki ~20–30
  scenarijų su automatiniu „ar pasiekė teisingą baigtį per N turn'ų".
- Delsa: `voice_latency` / `ttfa_ms` trace metrikos prieš/po R4.

## 9. Statuso žurnalas

- **2026-08-12** — planas sudarytas (architektūros auditas: grafas/state, voice/latency,
  RAG, promptai/tools). Sukurta šaka `refactor/langgraph-v2`. R1 pradžia:
  `graph_v2/state.py` (`GraphState` + `TurnScratch` + legacy tilteliai) ir testai.
- **2026-08-12 (2)** — R1 užbaigta + R2 branduolys: `SqliteSaver` checkpointeris,
  grynas `route_entry`, `runtime.py` (narrate + sync_updates strangler siūlė),
  4 ploni mazgai atskiruose failuose, `AGENT_ENGINE=v2` jungiklis.
  Pariteto/checkpointo/time-travel testai (18) žali. Liko R2: gyvo balso
  patikra (streaming + barge-in), auksiniai scenarijai (R0 skola).

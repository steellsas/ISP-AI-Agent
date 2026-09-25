# Testų žemėlapis (sutarta 2026-08-31, peržiūra vyksta pažingsniui; atnaujinta 2026-09-17 po refaktoringo M0–M6)

Tikslas (Andrius): žinoti, kas KĄ tikrina; nebe kurti besidubliuojančių
testų; stambūs pokalbio lygio patikrinimai („supratimas veikia,
identifikacija veikia, tiketas veikia, užbaigimas veikia") + smulkūs vieno
funkcionalumo testai — kiekvienam faktui VIENA vieta.

Būsena 2026-09-17 (`refactor/single-engine`): **65 testų failai**
(`chatbot_core/tests/test_*.py`; atskiro šakninio `tests/` katalogo nėra),
**1242 testai** (`uv run pytest --collect-only -q`); eval **33 scenarijai**
(`chatbot_core/src/agent/eval/scenarios.json`), pilnas paleidimas — **~178
čekiai**. Čekių skaičius auga su kiekvienu scenarijumi: +2 visada
(`contact_record` ir `reply_len`) + po vieną už kiekvieną `expect` raktą
(`verdict_in`, `disposition` ≠ `any`, `identified`, `reply_any`, `reply_none`,
`record_outcome`) + po vieną už kiekvieną `tool_used` įrašą. (Peržiūros
pradžioje 2026-08-31 buvo 37 failai, 933 testai, 11 scenarijų / 44 čekiai.)

Variklis vienas: LangGraph grafas `perceive → decide → execute → narrate`
(`agent/graph_v2/graph.py`; `narrate` kalba per `agent/speak/`), viena būsena
`GraphState`, kiekvienas ėjimas — vienas `TurnPlan`, kiekvienas skambutis
palieka kontakto įrašą (`agent/call_record/`).

## Piramidė ir sluoksnių nuosavybė

| Sluoksnis | Kas garantuojama | Kur gyvena |
|---|---|---|
| EVAL (pokalbio lygis) | pilni pokalbiai su tikru LLM: supratimas, identifikacija, sprendimas, tiketas, užbaigimas, kontakto įrašas | `eval/scenarios.json` (S/I/D/R/T/U/G/A/X serijos) |
| Grafas ir būsena | grafo mazgų tvarka, checkpoint'as = visas skambutis, tarp-ėjimų įrašai | test_graph_v2, test_graph_v2_state, test_single_state |
| `perceive` (skaitymas) | adresų NLU, slotai, supratimo pass'as, klasifikacijos kaskada, evidence įrašymas, šalutinė tema | test_nlu, test_nlu_wave, test_slots, test_understand, test_perception_merge, test_classification, test_evidence |
| `decide` (planas) | politikų grandinės tvarka, taisyklės (identifikacija, tiketas, uždarymas, prašymai, atviri tiketai), procedūros vykdytojas + jo sargai, hipotezės būsena, solverio ir plano vartai | test_policy_order, test_identification_rules, test_identification_gate, test_rules_ticket, test_rules_closing, test_closing, test_requests, test_open_ticket, test_service_profile, test_procedure, test_procedure_guards, test_resolution, test_hypothesis, test_gate, test_gate_closed_set, test_repeat_guard, test_dialogue_quality, test_live_calls_m6 |
| Gedimų žinios (pack'ai) | pack'ų struktūra ir eiga, verdiktų medis, informavimo šablonai, playbook | test_fault_packs, test_faults, test_router_hung, test_line_faults, test_verdict, test_inform, test_playbook |
| `execute` / įrankiai | įrankiai (CRM, tinklas, žinių bazė), ToolGateway, įrankių vartai iki identifikacijos, nuotoliniai veiksmai, DB, RAG | test_tools, test_tool_gateway, test_tool_gate, test_port_actions, test_address_resolver, test_db, test_rag |
| `speak` (balsas LLM) | frazių kelias, konteksto kortelė, atsakymo sargai, istorijos langas, promptų kompozicija, srautinis LLM klientas | test_speak, test_history_v2, test_prompts, test_streaming_agent |
| `analyst` | tipizuoti signalai ir jų ribos | test_analyst_signals |
| `contract` (failų kontraktas) | žinių schema, limitai/politikos, loader + reload, locale frazės, detektorių glosos, identifikacijos politika | test_knowledge_schema, test_limits, test_loader, test_locale, test_detectors, test_identification_policy |
| `call_record` + stebėjimas | kontakto įrašo baigtis, trace JSONL, PII maskavimas, `turn_plan` įvykiai | test_call_record, test_tracing, test_pii_redaction, test_turn_plan_trace |
| `app` (FastAPI host) | sesijų gyvavimas, ėjimai, įvykių srautas, WS, admin | test_api, test_interrupt_ack, test_overlay_stage2 |
| Balsas (transportas) | audio front (VAD, segmentai), STT biasing, adapteriai, LT skaičių normalizacija | test_audio_front, test_voice_v1, test_voice_adapters, test_lt_text |
| Mišrus (istorinis) | žr. „Dubliavimosi kandidatai" | test_agent |

## Taisyklės

1. **Vienas faktas — vienas sluoksnis.** Pvz., identifikacijos atradimo
   variantai (dalimis diktuotas adresas, klaidingas namas, recovery) —
   TIK identifikacijos sluoksnyje (eval I1–I6 + test_address_resolver +
   test_slots + test_identification_rules). Visuose KITUOSE
   scenarijuose/testuose identifikacija = paruošta būsena (fixture
   `make_state()` / `make_runtime()`), nebetestuojama pakeliui.
2. **Naujas testas — tik su vieta žemėlapyje.** Jei sluoksnis faktą jau
   dengia — keičiamas esamas testas, ne kuriamas naujas.
3. **Peržiūra vyksta KARTU su pažingsniniu testavimu** (ne atskira
   „didžioji revizija"): testuojame identifikaciją → sutvarkome jos
   sluoksnį; tada analizę/supratimą; tada sprendimo vedimą; tada tiketą ir
   užbaigimą. Kiekvieno etapo išvestis — sluoksnio failų sąrašas šiame
   dokumente + išvalyti dubliai.

## Pažingsninio testavimo eiga (pagal DIALOGO_ETALONAS.md srautą)

| Etapas | Kas tikrinama | Testų sluoksnio failai (pildoma peržiūros metu) |
|---|---|---|
| 1. Prisistatymas + problemos supratimas | greeting (DI atskleidimas), problemos vartai (L1/L2 kaskada), capture-first | test_classification, test_nlu, test_understand, test_perception_merge, test_dialogue_quality (W1), eval G1, T1, T2, S10 |
| 2. Identifikacija | adreso laiptai, resolve, diktuoto adreso patvirtinimas, abonento kodas, savininko vardas, identifikacijos vartai (D-09) | test_address_resolver, test_slots, test_nlu_wave, test_identification_rules, test_identification_gate, test_identification_policy, eval I1–I6, U1, D2b |
| 3. Analizė (telemetrija + hipotezė) | verdiktai, paslaugų profilis, hipotezės stabilumas, analitiko signalai, fast-path | test_verdict, test_service_profile, test_hypothesis, test_analyst_signals, eval S8 pora, S3, D2–D4, R3 |
| 4. Sprendimo vedimas | pack'ai, procedūros vykdytojas + sargai, solverio ir plano vartai, evidence žurnalas, kartojimo sargas, verifikacija dviem šaltiniais | test_fault_packs, test_procedure, test_procedure_guards, test_resolution, test_router_hung, test_line_faults, test_evidence, test_gate, test_gate_closed_set, test_repeat_guard, test_dialogue_quality, eval S1, S1v, S4, S6, S9, D5, D6, D8, A1 |
| 5. Tiketas + užbaigimas | kontaktai, registracija, prašymai (D-11), atviri tiketai (D-12), informavimo šablonai, goodbye, kontakto įrašas (D-14) | test_rules_ticket, test_rules_closing, test_closing, test_requests, test_open_ticket, test_inform, test_call_record, test_api (dalis), eval R1, R1b, R2, R4, X_dhcp_silent |
| 6. Balso transportas | duplex, delivery, overlay, endpointing, pertraukimo ack | test_audio_front, test_voice_v1, test_voice_adapters, test_overlay_stage2, test_interrupt_ack, test_lt_text, test_api ws |

## Dubliavimosi kandidatai (tikrinti peržiūros metu)

- `test_agent.py` (128) — istorinis katilas be modulio docstring'o, 27 klasės,
  jau importuoja naujus sluoksnius (`perceive`, `decide`, `execute`, `speak`,
  `call_record`). Skaidyti pagal sluoksnius: `TestSpeakPrompt`,
  `TestHistoryWindow`, `TestPromptLoader`, `TestPromptPrefixHygiene` → speak;
  `TestIdentificationLadder`, `TestAddressGuards`, `TestAddressSpeech` →
  identifikacija; `TestTicketDialogue`, `TestAutoRegisterEscalate`,
  `TestRefuseOrTicket` → tiketas; `TestBargeInCancel`, `TestVoiceGuardsRound5`
  → balsas; dublius su test_fault_packs / test_dialogue_quality naikinti.
- `test_graph_v2.py` (15) — v1 variklio (`test_graph.py`) nebėra, variklis
  vienas. Bet šio failo docstring'as ir dalis pavadinimų dar kalba senais
  terminais („diagnosis subgraph", „per-stage tool scopes", „walker",
  „ticket node"), nors grafas dabar `perceive → decide → execute → narrate`
  ir kalbantis LLM įrankių neturi. Perrašyti pavadinimus pagal dabartinį grafą.
- `test_procedure_guards.py`, `test_procedure.py`, `test_perception_merge.py`
  — docstring'ai dar mini „walker"; kodas dabar `decide/procedure.py`
  (procedūros vykdytojas) + `decide/procedure_guards.py`.
- `test_voice_adapters.py` / `test_voice_v1.py` — dalis dengia legacy PART
  kelią; peržiūrėti, kai duplex taps vieninteliu keliu.

## Žinių sluoksnis (RAG, E1–E4)

| Failas | Ką įrodo |
|---|---|
| `test_knowledge_base.py` | dokumento sutartis: rūšis, raktai, filtras, skyriai, žingsniai |
| `test_knowledge_recall.py` | **arbitras**: 68 klausimai kliento žodžiais, `hit@1`/`hit@2` ribos, kiekvienas dokumentas turi klausimų |
| `test_knowledge_need.py` | agento **ribos**: ką atsisako ieškoti (tema, paskirtis, prietaisas, ne klausimas), konkretus įrenginys prieš bendrą, kortelės `knowledge_need` |
| `test_retrieval_port.py` | saugyklos keitimo siūlė: per portą grąžinami TIE PATYS dokumentai |
| `test_qdrant_index.py` | indeksas: *sparse* sandauga = leksinis balas, hibridas, filtrai, versijos, aliasai, modelio saugiklis, sveikata |

Klausimų rinkinys gyvena **prie žinių** (`src/rag/knowledge_base/_questions.yaml`), ne testuose —
tą patį failą skaito ir ingestijos kanarėlė, tad CI ir gamyba negali nesutarti, kas yra
„pakankamai gerai".

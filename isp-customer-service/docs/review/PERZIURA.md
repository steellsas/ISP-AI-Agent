# Agento peržiūra — radiniai ir sprendimai (gyvas dokumentas)

Pradėta 2026-09-17. Peržiūra etapais (0–10); čia fiksuojama, kas APTARTA ir
NUSPRĘSTA. Kodas peržiūros metu nekeičiamas — taisymai planuojami po peržiūros.

| # | Etapas | Būsena |
|---|---|---|
| 0 | Žemėlapis | ✅ |
| 1 | Vieno ėjimo kelias | ✅ |
| 2 | Perceive | ✅ (radiniai G–M) |
| 3 | Decide | ✅ (radiniai N–R) |
| 4 | Execute ir įrankiai | ✅ (radiniai S–X) |
| 5 | Narrate/Speak ir promptai | ✅ (radiniai Y–AC) |
| 6 | Analyst ir call record | ✅ (C patvirtinta; AD–AF) |
| 7 | Žinios: YAML, fault packs, RAG | ✅ (radiniai AG–AK, P-8 aptarimui) |
| 8 | Greitis | ✅ (radiniai AL–AO) |
| 9 | Kokybė: eval, testai | ✅ (radiniai AP–AU) |
| 10 | Suvestinė ir taisymų planas | ✅ (§4) |
| 11 | Lokalūs modeliai (atskiras etapas): open-source modelių parinkimas, min. resursai (GPU/VRAM), matavimas per eval | vėliau |
| 12 | Integracija (atskiras etapas): tikros įmonės sistemos (CRM, tinklo stebėsena, tiketai) per MCP / mikroservisus; esamų integravimas arba naujų kūrimas | vėliau |

---

## 1. Principai (sutarta 2026-09-18)

**P-1 · Diagnozė = informacijos rinkimas, ne kliento žodžių priėmimas.**
Klientas pasako problemą taip, kaip JIS ją supranta — dažnai tai ne tikra
priežastis. Agentas renka faktus iš dviejų šaltinių ir pagal aprašytas
situacijas parenka gedimą bei sprendimą:

```
kliento pasakymas ──► kandidatai (kortelės pagal paslaugą + simptomą)
                          │
        ┌─────────────────┴─────────────────┐
  telemetrija (kur yra)              kliento klausimai (kur nėra)
  = arbitras (D-07)                  LLM ištraukia reikiamą faktą
        └─────────────────┬─────────────────┘
                          ▼
           atitiktis aprašytai situacijai ──► gedimas + sprendimas
                          │
           faktai prieštarauja? ──► „gedimas ne ten" → kita hipotezė
```

**P-2 · Kortelė aprašo gedimą IR patikros būdus.** Kiekvienam faktui kortelė
nurodo, kaip jį gauti: telemetrijos zondas (jei yra) ir/arba kliento klausimas
(„ką rodo ekranas?", „ar dega lemputė?"). Variklis pats renkasi: jei zondas
yra — tikrina, jei ne — klausia.

**P-3 · LLM pildo spragas, nesugalvoja sprendimų.** LLM supranta klientą,
klausinėja ir ištraukia informaciją, formuluoja kalbą; gedimą ir sprendimą
renkasi variklis pagal korteles (uždaras veiksmų sąrašas, gate).

**P-4 · Naujas gedimas = failai, ne kodas.** Kortelė + frazės + testiniai
scenarijai.

**P-5 · Modeliai keičiami, principas lieka.** Produkcija — įmonės lokalus
serveris; demo naudoja debesies modelius, kurie vėliau keičiami lokaliais.
Dabar tobulinamas veikimo principas (algoritmas), modelių nauda ir greitis
tikrinami juos pakeitus (per eval). Todėl variklis:
- kalba su modeliais tik per portus (`src/ports/*`), jokių tiekėjo-specifinių funkcijų varikly;
- JSON išvestis per schemą, kurią palaiko ir lokalūs serveriai (constrained decoding);
- trumpi promptai (mažas kontekstas), užduotis padalinta taip, kad tiktų ir mažam modeliui;
- kiekvienas modelio vaidmuo (ASR, supratimas, solver, naratorius, analyst, TTS) konfigūruojamas atskirai.

**P-6 · Skambučio fazės (sutarta 2026-09-18).** Vienas sprendėjas (Case);
keli numanomi gedimai vienu metu, klausimai juos atskiria; LLM solver — tik
spragoms, grąžina tikslą naratoriui.

```
1 ATSILIEPIA + IDENTIFIKUOJA
2 SUPRANTA PROBLEMĄ (paslauga + simptomas, kliento žodžiais)
      └─ trumpi keliai: avarija · skola · atviras tiketas · paslauga neužsakyta → INFORMUOJA
3 ANALIZĖ: kandidatai iš žinių → telemetrija + klausimai → atskiria, kuris gedimas
      └─ „gedimas ne ten" → kitas kandidatas
4 IŠVADA: gedimas žinomas → paaiškina klientui → pasirenka kelią
      ├─ sprendžiama telefonu (žinomas sprendimo būdas)
      └─ tiketas (meistras / kitas skyrius)
5 SPRENDIMAS PO ŽINGSNĮ: instrukcija → laukia → patikrina (kliento žodis + zondas)
      └─ nepadėjo → atgal į 3 (kitas kandidatas) arba tiketas
6 UŽDARYMAS: rezultatas, antrinės problemos, atsisveikinimas
Bet kurioje fazėje: klientas nori tiketo / negali dabar / atsisveikina → bendros politikos.
```
Riba tarp 3 ir 4 („gedimas nustatytas") — aiški: analizė renka faktus, sprendimo
žingsniai tik vykdo (tai išsprendžia radinį N).

**P-7 · Įrankiai pasiruošę integracijai (sutarta 2026-09-18).** Tikros
sistemos dar nežinomos (12 etapas), todėl demo kuriamas taip, kad integruoti
būtų paprasta: demo — tiesiogiai DB, produkcija — MCP / mikroservisai; variklis
skirtumo nemato. Agentas turi įrankius ir moka juos naudoti, įskaitant veiksmus
tinkle (skaityti, perkrauti, pririšti MAC, aktyvuoti portą). Kiekvienas
įrankis — atskiras kontraktas su savo saugikliais; naujas įrankis = aprašas +
adapteris. Neveikiantis įrankis ar pasiektas limitas → aiškus pranešimas
(klientui, trace, operatoriams) ir numatytas atsarginis kelias.

Įrankio aprašas (manifestas, pvz. `knowledge/tools/*.yaml`):
```yaml
tool: reboot_cpe
capability: action            # probe (read-only) | action (mutacija) | crm | ticketing | outages
adapter: demo_db              # demo_db | mcp:network | http:nms  — keičiasi integracijos metu
args:    { customer_id: str }
returns: { facts: [cpe_rebooted, port_flap] }   # kas patenka į ledger
requires: [identified, consent]                 # prieigos sąlygos
guards:                                          # saugikliai — pagal įrankį
  max_per_call: 1
  cooldown_s: 600
  allowed_hours: "08-22"                         # pvz. įrangos perkrovimas ribotas
timeout_s: 8
retries: 1
rate_limit: { per_minute: 30 }                   # visai sistemai
filler_key: tools.checking                       # „patikrinsiu…" kol laukiam
on_failure:                                      # neveikia / timeout / limitas
  say_key: tools.unavailable
  fallback: ask_client | ticket | skip           # zondo vietoj — kliento klausimas
  alert: ops                                     # pranešimas operatoriams
audit: true                                      # kiekvienas veiksmas įrašomas
```
Pvz.: `port_activate` — be ribojimų (bet kada); `reboot_cpe` — su cooldown ir
valandų ribojimu; `update_mac` — tik su kliento sutikimu, 1 kartą per skambutį.

**P-9 · Testų strategija: gebėjimai be LLM, pokalbiai su LLM (Andrius, 2026-09-18).**
```
1 GEBĖJIMŲ TESTAI (be LLM, greiti, daug)   įvestis → laukiamas rezultatas, po vieną gebėjimą
   adresas iš transkripcijos (su STT darkymais) · gatvės atitikimas · abonento kodas ·
   RAG paieška (klausimas → laukiamas gabalas top-k) · kiekvienas įrankis per kontraktą
   (args → rezultatas; timeout / limitas / neveikia per fake adapterį) · MAC pririšimo
   grandinė · gate ir saugikliai (sutikimas, cooldown) · greitkelio skaitytuvai ·
   faktų priėmimo politika · decide lentelės (būsena + perception → planas) ·
   kortelių validacija · frazių atvaizdavimas · sakinių skaidymas TTS
2 KOMPONENTŲ EVAL (su LLM, be pokalbio)     perception rinkinys · įgūdžio atsakymai
3 POKALBIŲ EVAL (su LLM, pilni pokalbiai)   tik tai, kas atsiranda iš DERINIO:
   supratimas kontekste · fazių perėjimai · hipotezės keitimas · „gedimas ne ten" ·
   vienas klausimas / tonas · voice režimas · stabilumas (k paleidimų)
```
- Gebėjimų testai rašomi prieš **kontraktą / portą, ne vidinę struktūrą** → išgyvena refaktoringą (AU).
- Atvejai — **duomenų lentelėse** (YAML/JSON): naujas atvejis = nauja eilutė, ne naujas testas.
  ```yaml
  - heard: "Tilžės gatvė šešiasdešimt, butas penki"
    expect: { street: "Tilžės g.", house: "60", apartment: "5" }
  ```
- Kiekviena gyvo skambučio klaida → pirmiausia eilutė žemiausiame sluoksnyje, kuris ją pagauna;
  į pokalbių eval — tik jei klaida atsiranda iš derinio.
- Eval **nebetikrina to, ką jau garantuoja 1 sluoksnis** (pvz. identifikacija = paruošta
  būsena, kaip `TESTU_ZEMELAPIS.md` taisyklė 1).
- Pilnas 1 sluoksnio paleidimas (sekundės–minutė) atsako „ar nieko nesugadinom";
  eval atsako „ar agentas su LLM elgiasi gerai".

### Domenų pastabos
- **Lėtas internetas** — telemetrija panaši į „veikia"; reikės skiriančių
  faktų (Wi-Fi vs kabelis, vienas/visi įrenginiai, paros laikas, greičio
  testas) → kortelėse daugiau kliento klausimų, telemetrija kaip patvirtinimas.
- **TV** — įrenginių telemetrijos nebus; remiamasi kliento pasakymais
  (ekrano pranešimas, lemputės, kanalai) → kortelės daugiausia klausimų tipo.

---

## 2. Radiniai

| ID | Radinys | Būsena |
|---|---|---|
| **A** | Sprendimai vyksta ne tik decide: `decide/rules/stage.py` vykdo įrankius, LLM solver, `procedure.advance`; `narrate` per `scripted_exit`/`plan_reply` antrą kartą planuoja, uždaro skambutį, registruoja tiketus; `maybe_end_on_goodbye` baigia skambutį pagal LLM tekstą. Pasekmės: gate (forbidden/consent) nemato dalies veiksmų, `turn_plan` trace netikslus, decide netestuojamas izoliuotai. `TurnPlan.redecide_after_action` nenaudojamas. | Sprendimas: 3 variantas (tikslinė architektūra, §3), pradedant F1 |
| **B** | `llm` trace įvykis rašomas tik speak mazge — understand/classifier/solver/analyst kvietimai neskaičiuojami (`turn_summary.llm_calls`, kaina per mažos). | Taisyti F0 |
| **C** | PATVIRTINTA (6 etapas): `AgentSession.analyst_next` taiko signalus `self._state` snapshot'ui, ne checkpoint'ui → voice (async) režime sprendžiantys signalai (contradiction, already_answered, secondary_problem) gali dingti; galimas race. | Taisyti F0 |
| **D** | Pirmas garsas p50 2,9 s / p90 6,8 s (8 skambučiai); scripted ėjimas be LLM — 5,7 s → dominuoja TTS/transportas. `model_copy(deep=True)` — ne problema. | Detaliau 8 etape |
| **E** | Smulkmenos: pasenęs „SUBGRAPH" komentaras `session.handle_turn_stream`; `tools.py` kviečia `crm_mcp` in-process (ne per MCP); dubliuoti moduliai (`agent/evidence.py` ↔ `perceive/evidence.py` ir kt.). | 2 ir 4 etapuose |

### 2 etapas — Perceive (2026-09-18)

| ID | Radinys |
|---|---|
| **G** | Skaitymas išbarstytas: perceive skaito tik dalį; ~50 detektorių kvietimų decide/narrate failuose (head 9, procedure 9, reply 5, closing 5, ticket 4…) ir 3 LLM skaitytuvai už perceive ribų (`classify_problem_llm`, `classify_step`, `understand_ticket`). |
| **H** | Tas pats sakinys skaitomas 3–4 keliais (LLM understand + keyword `extract_client_facts` + pending-key skaitytuvas + žingsnio detektorius) ir ~8 arbitražo sargai (reader_disagreement, done_report_dropped, uncorroborated_flip, story_flip_gate, conflict_silent…) — kiekvienas gyvo skambučio lopas. |
| **I** | Domenas kode: `understand._ALLOWED` (device_present, lights, power_cable…) ir `evidence.extract_client_facts` raktai — interneto faktai įrašyti Python'e (prieštarauja P-4). |
| **J** | Perceive rašo ir sprendimus: `problem_type` įsipareigojimas, antrinės problemos, `hypothesis.doubt` (contradiction), holder relation. |
| **K** | LLM understand veikia tik identifikuotam klientui diagnozės etape; `PERCEPTION_MODEL=default` (gpt-4o-mini) — greitesnis modelis neįjungtas. |
| **L** | Realių voice duomenų apie understand trace'uose nėra: `logs/sessions` ~121 tūkst. failų, dauguma — testų/eval paleidimai (TRACE_DIR nenukreiptas). |
| **M** | Sensorių promptai lietuviški (`sensors/perception.md`), o D-19 sako „English prompts" — neatitikimas (sprendimas neaptartas). |
| E↺ | Patikslinta: `agent/detectors.py` (YAML glosos), `agent/evidence.py` (ledger modelis), `agent/slots.py` (modeliai) — NE dublikatai `perceive/*`, tik painūs pavadinimai. |

Kryptis (F2): vienas `Perception` objektas per ėjimą — greitkelis (regex trumpiems
uždariems atsakymams, 0 LLM) → vienas LLM kvietimas visam kitam; faktų schema
generuojama iš kandidatų kortelių (ne kode); kiekvienas faktas su CITATA iš
sakinio (deterministinė haliucinacijų patikra vietoj sargų rinkinio); faktų
priėmimo politika vienoje vietoje decide'e; perceive tik skaito.

#### Atsakymai (2026-09-18)
- K: Groq veikė gerai, grįžta į gpt-4o-mini dėl nemokamo rate limit. Ilgalaikis tikslas — **visi modeliai lokalūs**, nepriklausomi nuo trečiųjų šalių.
- M: LT promptai palikti testams; keisti į EN, jei nenukris kokybė ir greitis (spręs perception eval).

### Supratimo tobulinimo strategija (aptarta 2026-09-18)

Principas: **pirma matuoti, tada keisti modelį / promptą / kalbą.**

1. **Perception eval rinkinys** (~200–300 pavyzdžių: sakinys + kontekstas →
   laukiamas Perception). Šaltiniai: realūs skambučiai, eval scenarijai,
   sintetika (didelis modelis generuoja, Andrius tikrina). Metrikos: faktų
   tikslumas, turn_type tikslumas, haliucinacijos (faktas be citatos), p50/p90 ms.
2. **Greitis:** greitkelis be LLM uždariems atsakymams; vienas kvietimas su
   JSON schema / constrained decoding; trumpas dinaminis promptas (tik aktyvaus
   klausimo raktai); **perception paleidžiama ant stabilaus ASR partial** dar
   prieš sakinio pabaigą; modelių kaskada (regex → mažas modelis → didelis tik
   kai mažas nepasitiki).
3. **Kokybė:** citata prie fakto; dinaminiai few-shot pavyzdžiai iš pavyzdžių
   banko pagal aktyvų klausimą; normalizacijos sluoksnis (STT klaidos, slengas)
   failuose; „klausk, nespėliok" esant mažam pasitikėjimui.
4. **Plėtra negadinant supratimo:** perception kontraktas stabilus ir
   versijuotas; promptas mato tik aktyvių kandidatų raktus (dydis neauga su
   gedimų skaičiumi); problemų katalogui — retrieval top-k → LLM renkasi;
   kiekviena nauja kortelė + scenarijai → CI regresijos vartai.
5. **Kalbos ir slengas** (dabar tik LT; kitos kalbos — perspektyva, svarbu, kad naują kalbą būtų lengva įvesti lokalės failais): perception grąžina kalbai neutralius raktus; kalba
   iš ASR; slengo/tarmių žodynas ir pavyzdžiai per lokalę; EN promptas + LT/RU/EN pavyzdžiai.
6. **Lokalūs modeliai:** ASR — faster-whisper (jau yra); perception —
   mažas modelis (LoRA fine-tune, mokytojas = didelis modelis, distiliacija)
   arba encoder klasifikatorius turn_type/taip-ne; narator — vidutinis
   instrukcinis modelis, stiprus LT; TTS LT lokaliai — silpniausia vieta,
   reikia tyrimo. Portai (`src/ports/*`) jau leidžia keisti tiekėjus.
7. **Duomenų ratas:** klaidingi skaitymai (dashboard/analyst) → žymėjimas →
   eval rinkinys + pavyzdžių bankas → fine-tune duomenys.

### 3 etapas — Decide (2026-09-18)

Palikti (gera): aiški policy chain eilė; D-05 hipotezės stabilumas (doubt →
confirm); visos ribos `limits.yaml`; uždaras veiksmų sąrašas; bailout'ai prieš
kilpas; ledger su šaltinio autoritetu (telemetrija > žodis).

| ID | Radinys |
|---|---|
| **N** | **Trys vairuotojai vienam gedimui**: `evidence_drive` (ledger), LLM solver, walker (`procedure`) + perdavimo taisyklės (`owns_answer`, `solution_synced`, `drive_disabled` bailout, „walker = rodyklė, sinchronizuojama iš ledger"). D-03 „vienas vairuotojas" realiai neįgyvendintas; daug gyvų klaidų kilo būtent iš perdavimų (lenktynės, pasenęs žingsnis, „rewind"). |
| **O** | **LLM solver kalba tiesiogiai**: `narrator_instruction` ištariamas pažodžiui (`committed=True`) — apeina naratoriaus promptą/stilių; solver varo pokalbį, kai ledger neturi ko klausti (P-3: LLM tik spragoms). Laisva hipotezė normalizuojama į aktyvų verdiktą, `pivot` = tik telemetrijos perskaitymas. |
| **P** | **Hipotezė trijose vietose**: `diagnosis.hypothesis` (cause/because/status), `evidence.hypothesis_status(spec)` (confirmed/refuted iš ledger), `contradiction` (doubt/confirming) + `failed_hypotheses` ir `rejected_hypotheses`. Vienu metu tik VIENAS kandidatas — nėra diferencinės diagnozės (P-1). |
| **Q** | **Aktyvus klausimas ~10 formų**: registras (`question.py`, pusiau „shadow") + vėliavos `end_confirm_pending`, `cannot_now_state`, `ticket.stage/last_kind`, `pending_evidence_key`, `procedure.asked/asked_at`, `reopen_confirm_asked`, `holder_clarify_asked`, `contradiction.asked`, `debt_offer`… Du pirmumo mechanizmai: RULES eilė ir `OWNER_PRIORITY`. |
| **R** | **Du gate'ai** su skirtingomis taisyklėmis: solver `gate()` ir plano `check_plan()`. |

**Sprendimai (Andrius, 2026-09-18):**
- ✅ **Vienas sprendėjas** — Case; evidence_drive / solver / walker trijulė nebelieka (N).
- ✅ **Keli numanomi gedimai vienu metu**; klausimai parenkami taip, kad atskirtų, kuris tai gedimas (P).
- ✅ **LLM solver = spragų pildytojas**: siūlo iš uždaro sąrašo, grąžina tikslą naratoriui, pažodžiui nekalba (O).
- ✅ Skambučio fazių modelis — P-6 (§1).

Trace'ų skaičiai (dauguma testų/eval, ne gyvi skambučiai — L): `drive_decision`
ask_evidence 3042 · fix_deferred 2384 · escalate 527 · bailout_to_walker 263 ·
bridge_fail_* 527 · LLM solver veiksmai (disambiguate/propose_fix/instruct) tik ~50.
→ Solver realiai vairuoja retai; perdavimas į walker'į — dažnas.

Kryptis (F1 + F3): decide(state, perception) → TurnPlan, grynas:
1) vienas klausimų registras (owner, key, ko laukia) → jo savininko tvarkyklė;
2) bendros dialogo politikos (atsisveikinimas, negaliu dabar, atsisakymas, tiketas);
3) Case: kandidatai iš kortelių → įrodymai keičia jų svorį → prieštaravimas =
patvirtinimo klausimas (D-05) → vienas patvirtintas → jo sprendimo žingsniai
(procedūra tik VYKDYMUI) → kitaip kitas skiriantis faktas (zondas, jei yra,
kitaip klausimas) → kortelė nieko nesako → LLM solver siūlo iš uždaro sąrašo,
jo tekstas = tikslas naratoriui, ne pažodinė kalba;
4) ribos/bailout → registracija. Vienas gate.

### 4 etapas — Execute ir įrankiai (2026-09-18)

Palikti (gera): `ToolGateway` — viena vieta įrankio kvietimui (trace + prieigos
gate + observation); `ToolProvider` portas; customer_id sargas (tik
identifikuotas, tik savas id); telemetrija `snapshot` vs `recheck` (read-only);
`verdict.py` padalintas į `gather_signals` (I/O) ir `decide` (grynas medis);
preflight telefono paieška pasisveikinimo metu; foninis telemetrijos atnaujinimas.

| ID | Radinys |
|---|---|
| **S** | **ReAct laikų palikimas**: `REAL_TOOLS` katalogas LLM'ui (close_case, create_ticket, search_knowledge, check_network_status, run_ping_test), gateway'aus „corrective" pranešimai angliškai modeliui, `executor_flow.execute_tool_calls` (niekur nekviečiamas) — LLM įrankių nebekviečia (speak `tools=None`). Negyvas kodas + klaidinantys sargai. |
| **T** | **Paslėpta grandinė stebėjimo apdorojime**: `observe.augment_*` po `resolve_address` paleidžia `ensure_diagnosed`, po `update_mac` — `reset_port` + telemetrijos perskaitymą. Sprendimai/veiksmai vyksta observation handleryje (dar viena vieta, žr. A). |
| **U** | **Diagnostika = interneto sprendimų medis kode** (`verdict.py`): gera greičiui, bet domenas kode; Case architektūrai reikia žalių signalų → faktų (telemetry.port_up, mac_seen, crc_rate…), o sąlygas deklaruoja kortelės. |
| **V** | **Integracijos tik demo**: įrankiai importuoja `crm_mcp` / `network_diagnostic_mcp` funkcijas tiesiogiai (MCP serveriai runtime nenaudojami), viena SQLite. Produkcijai (lokalus įmonės serveris) reikės tikrų adapterių: CRM, tinklo stebėsena (SNMP/ACS/NMS), tiketų sistema. `simulate_*` įrankiai gyvena tame pačiame provider'yje (tik env sargas). |
| **W** | **Latencija ir klaidos nerepetuotos**: dabar įrankiai ~1 ms (in-process). Tikri sistemų kvietimai — sekundės; nėra timeout'ų / pakartojimų / „patikrinsiu" užpildo politikos kiekvienam įrankiui; neaišku, ką agentas daro, kai telemetrija nepasiekiama. |
| **X** | **Uždarymo sargas `close_case` gateway'uje** — perteklinis (uždarymą daro variklis, ne LLM įrankis). |

Kryptis:
- Įrankiai skirstomi pagal **galimybes** (capabilities): `probes` (telemetrija,
  read-only), `actions` (bind, reset — mutacijos, reikalauja sutikimo/gate),
  `crm` (klientas, paslaugos, skolos), `ticketing`, `outages`. Kiekviena —
  atskiras portas; demo adapteris (SQLite) ir produkcijos adapteriai keičiami.
- Kortelės nurodo zondą pagal vardą (`probe: iptv_status`); zondas grąžina
  faktus į ledger. `verdict.py` medis tampa „telemetrijos kortele" / taisyklėmis failuose.
- Kiekvienam įrankiui deklaruojama: timeout, pakartojimai, ar reikia užpildo
  frazės, ką daryti nepavykus (klausti kliento vietoj zondo / tiketas).
- Grandinės (bind → reset → recheck) — modulio žingsniai kortelėje, ne kodas observe'e.
- Ištrinti LLM įrankių katalogą, corrective pranešimus, `execute_tool_calls`, `close_case`.

### 5 etapas — Narrate ir promptai (2026-09-18)

Palikti (gera): promptai failuose su `<<include>>` (taisyklė vienoje vietoje);
EN taisyklės + LT pavyzdžiai per lokalę (`<<examples:…>>`); pastovus prefiksas
atskirai nuo kintamos kortelės (cache); deterministinė istorijos santrauka;
startup patikra (`check_prompts`); streaming.

Išmatuota (tiktoken o200k, be kortelės ir istorijos):

| Owner | Sistemos promptas |
|---|---|
| diagnosis | ~3500 tok |
| intake | ~2800 |
| side_topic | ~2500 |
| ticket | ~2460 |
| closing | ~2300 |
| kitas | ~2160 |
Sensoriai: perception ~660, solver ~630, analyst ~400, classifier ~260.

| ID | Radinys |
|---|---|
| **Y** | **Per ilgas bendras branduolys**: `partials/identity.md` vienas ~1500 tok (~20 stiliaus taisyklių) siunčiamas KIEKVIENAM owner'iui, net closing/ticket, kur atsakymas — vienas sakinys. |
| **Z** | **Taisyklės kartojasi**: „one question" 6 vietose (system, identity, style_core, solving…), „neužregistravau" — 3; dalis taisyklių su „live 2026-…" lopų pastabomis. Mažam/lokaliam modeliui ilgas „NEVER" sąrašas mažina instrukcijų laikymąsi. |
| **AA** | **Kortelė = 12 sekcijų** (`context_card.py` 1047 eil.): PLAN GOAL + daug kitų eilučių (telemetrija, simptomai, hipotezė, evidence, žingsnis, stuck, awaiting…) nepriklausomai nuo tikslo. Dydis nematuotas (įjungti `DEBUG_LLM`). |
| **AB** | **Ilgio riba neveikia balse**: `trim_to_cap` (280 simb.) taikomas PO streamingo — klientas jau išgirdo visą tekstą, apkarpoma tik istorija. „Vienas klausimas" niekur netikrinamas kode. |
| **AC** | **Parametrai**: speak `temperature 0.3`, `max_tokens 500` (atsakymas ~90 tok) — perteklinis; nėra `stop` sekų; `top_p 1`, penalties 0 (gerai — frequency/presence penalty LT kalbai kenktų galūnėms). Istorijos langas 20 žinučių + santrauka + kortelė — dubliuojasi. |

**Sprendimas (Andrius, 2026-09-18):** ✅ promptai pagal SITUACIJĄ (įgūdį, kurį
parenka decide pagal plano tikslą), ne pagal owner'į; trumpas branduolys + įgūdis
+ pavyzdžiai + ribota kortelė.

Kryptis (promptai pagal situaciją):
```
[1] BRANDUOLYS ~400–600 tok   kas esi · telefonas · 5 kietos taisyklės · kalba   ← pastovus (cache)
[2] ĮGŪDIS ~100–300 tok       pagal plano tikslo tipą: ask_fact · instruct_step ·
                              explain_finding · reexplain_confused · answer_side ·
                              ticket_offscript · goodbye
[3] 2–3 PAVYZDŽIAI            to įgūdžio, iš lokalės banko
[4] KORTELĖ                   tik tikslui reikalingos eilutės, su dydžio riba
[5] ISTORIJA                  4–6 paskutinės žinutės + santrauka
tikslas: ~1000–1500 tok vietoj ~3500 + kortelė
```
- Parametrai: `max_tokens ~150`; `stop` (pvz. naujos eilutės); temperatūra
  0.3–0.5 naratoriui, 0 sensoriams; be frequency/presence penalty; kartojimąsi
  tarp ėjimų spręsti kortele („paskutinė pradžia: X — pradėk kitaip").
- Deterministiniai validatoriai prieš TTS (sakinių buferis): ≤1 „?", ilgis,
  draudžiamos frazės iš lokalės → nukirpti / pakeisti atsarginiu tekstu.
- Lopų pastabos („live 2026-…") iš promptų → į regresijos testus / changelog.
- Kiekvienas įgūdis turi eval scenarijų; promptų pakeitimai matuojami (P-5).

### 6 etapas — Analyst ir call record (2026-09-18)

**C PATVIRTINTA** (atkūrimas: sesija atmintyje, `use_background_analyst()`,
imituoti signalai secondary_problem + frustration, `analyst_next()`):
snapshot'e antrinė problema atsiranda, checkpoint'e — ne; po kito ėjimo
`_refresh_state()` ji dingsta. Per inbox keliauja tik tono signalai. Taigi
voice režime contradiction / already_answered / secondary_problem signalai
**prarandami visada**; tekstiniame (sync) režime veikia.

Palikti (gera): analyst tik signalizuoja, sprendžia variklis (D-06); uždaras
signalų tipų sąrašas; pasenusių signalų atmetimas pagal turn_index. Call record:
outcome išvedamas deterministiškai iš būsenos; `needs_review` + priežastis;
hang-up saugiklis (pažadėtas tiketas neprarandamas); privatumo terminas
neidentifikuotiems; transport_end atskirtas nuo outcome.

| ID | Radinys |
|---|---|
| **C** | ✅ Patvirtinta klaida (žr. aukščiau). |
| **AD** | **Analyst dubliuoja perception**: contradiction (perception type + ledger conflict), already_answered (pending skaitytuvas, F-11 seeded confirm), secondary_problem (slots classify_problem). Unikalu tik: viso pokalbio vaizdas ir tonas (frustration, off_topic). |
| **AE** | **Brangiausias kvietimas**: kiekvieną ėjimą, 60 žinučių, `max_tokens 700`; sync režime (tekstas/eval) prideda latenciją narrate viduje. |
| **AF** | Call record: `finalize` registruoja tiketą pakabinus (apeina gate — A); `_technical_error` skaito trace failą (priklauso nuo JSONL sink'o); santraukos raktai maišyti LT/EN (`identifikacija_nepavyko`, `girdeta`). |

Kryptis:
- Analyst = foninė „antra nuomonė" tik tam, ko perception nemato: prieštaravimai
  per kelis ėjimus, pamirštos antrinės problemos, nuotaikos tendencija.
- Signalai keliauja per inbox → kito ėjimo Perception → decide (taisymas C).
- Paleidžiamas ne kiekvieną ėjimą, o pagal trigerius: kas N ėjimų, stuck,
  prieš išvadą / tiketą / uždarymą.
- Call record: hang-up tiketas — per tą patį gate/Action; techninės klaidos
  žymė būsenoje, ne trace faile; raktai EN. `needs_review` skambučiai →
  žymėjimo eilė → perception eval / pavyzdžių bankas (duomenų ratas).

### 7 etapas — Žinios, instrukcijos, RAG (2026-09-18)

Dabar: fault pack YAML (evidence + steps + EN hint'ai) · playbook MD (LT, žingsnių
sekcijos, jungiamos numeriu `rag_section`) · `phrases.yaml` · `examples/*.md` ·
`vocabulary.yaml` · `faq.yaml` (5 temos, raktažodžiai) · `rag/knowledge_base`
(~72 KB MD) + FAISS hybrid (multilingual mpnet).

Palikti (gera): schemos validacija paleidžiant (sugadinta žinia sustabdo
programą, ne skambutį); reload be perkrovimo; playbook tiekiamas po VIENĄ
žingsnį (modelis nebėga į priekį); moduliai kaip mechanizmas.

| ID | Radinys |
|---|---|
| **AG** | **Tos pačios žinios 4 vietose**: pack hint (EN), playbook žingsnis (LT), frazės, pavyzdžiai; komentarai „hint'as turi SUTAPTI su evidence klausimu". Perkrovimo instrukcija aprašyta kiekviename playbook'e atskirai. |
| **AH** | **Tik 2 moduliai** (`bind_mac`, `verify_restored`); procedūros neparametrizuotos pagal įrangą. |
| **AI** | **Įrangos žinios nepasiekiamos**: `equipment/router_tplink.md`, `tv_box.md`, `procedures/*`, `faq/common_questions.md` runtime niekur nenaudojami; CRM turi kliento įrangą su modeliu (`customer_equipment`), bet agentas jos neskaito. |
| **AJ** | **Embedding RAG realiai nenaudojamas**: pasiekiamas tik per `search_knowledge` LLM įrankį, kurio niekas nekviečia (S). Playbook „RAG" = deterministinis sekcijos numeris (trapu: 57 `rag_section` nuorodos). |
| **AK** | FAQ — 5 temos raktažodžiais; atviras klausimas už jų → „ne mano sritis". |

**Principas P-8: „Struktūra sprendžia, paieška randa."**

| Žinių rūšis | Pvz. | Forma | Kaip pasiekiama |
|---|---|---|---|
| 1. Sprendimų žinios | gedimo kortelės, sąlygos, sprendimai, politikos, įrankiai | YAML | tiesiogiai pagal raktą — NIEKADA per paiešką |
| 2. Įrangos katalogas | modeliai, lemputės → reikšmė → faktas, kur yra, kaip perkrauti, portai, tipinės klaidos | YAML (`equipment/*.yaml`) | pagal kliento įrangą iš CRM |
| 3. Moduliai-instrukcijos | reboot(device), reseat_cable(port), wifi_reconnect(os), factory_reset, check_lights(device) | YAML + trumpas tekstas pagal įrangos modelį | pagal id iš kortelės |
| 4. Aiškinamasis tekstas | kaip paaiškinti, tipinės klaidos, „kodėl" | MD gabalai su id | pagal žingsnio/modulio id (ne numeriu) |
| 5. Atviri klausimai | „kaip pakeisti Wi-Fi slaptažodį?", „ką reiškia oranžinė lemputė?", instrukcijos, FAQ | MD gabalai su metaduomenimis | **paieška** (hybrid BM25 + embeddings, filtras pagal įrangos modelį/paslaugą) → atsakymas tik iš rasto, su pasitikėjimo slenksčiu |
| 6. Pavyzdžių bankas | dialogų pavyzdžiai pagal situaciją | MD | **paieška** (dinaminiai few-shot, 5 etapas) |
| 7. Problemų katalogas | simptomų aprašai kortelėse | kortelių laukai | **paieška** top-k → LLM renkasi (kai kortelių daug) |
| 8. Gyvi duomenys | avarijos, skolos, planai, tiketai | sistemos | tik per įrankius, niekada failuose |

Gerosios praktikos: vienas gabalas = viena tema (100–300 tok) su pavadinimu ir
metaduomenimis (tipas, įrangos modelis, paslauga, gedimai, kalba); hybrid
paieška (BM25 gerai randa modelių pavadinimus/kodus, embeddings — prasmę) +
metaduomenų filtras + (pasirinktinai) reranker; atsakymas tik iš rastų gabalų
su nuoroda (grounding), nerasta → sąžiningai „perduosiu"; paieškos eval
(recall@k) klausimų rinkiniu — jau yra `rag/eval/run_eval.py`; embeddings
modelis lokalus, daugiakalbis (P-5, 11 etapas); kiekviena žinia turi savininką ir datą.

**Įrangos instrukcijų hierarchija (Andrius, 2026-09-18) — agentas niekada
nepasiduoda:** CRM gali nežinoti įrangos, klientas gali turėti savo nupirktą
įrenginį. Todėl instrukcija parenkama nuo tiksliausios iki bazinės:
```
1 tikslus modelis   equipment/tplink/archer_c6.yaml        (jei žinomas)
2 gamintojo šeima   equipment/tplink/_family.yaml          (klientas pasako „TP-Link")
3 įrenginio tipas   equipment/_generic/router.yaml         (BAZINĖ — visada yra)
                    _generic/modem · ont · tv_box · smart_tv · wifi_extender …
```
- Įrangos šaltinis: CRM → jei nėra, fakto klausimas klientui („kokios firmos
  routeris?" / aprašymas „balta dėžutė su antenomis") → jei nežino, bazinė.
- Gamintojo klausiama TIK tada, kai instrukcija skiriasi nuo bazinės (pvz.
  reset mygtuko vieta, web sąsaja); maitinimo perkrovimas universalus — neklausiama.
- Bazinė instrukcija tik saugūs, universalūs veiksmai (be gamyklinio reset'o ir pan.).
- Kiekvienas lygis paveldi žemesnį ir perrašo tik tai, kas skiriasi (validatorius
  tikrina, kad kiekvienas tipas turi bazinę).
- Kliento įranga, įrašyta pokalbio metu, patenka į call record → CRM papildymas.

Įrangos lemputės → faktai: kortelės neturi žinoti modelio; „INTERNET raudona"
(TP-Link) ir „LOS mirksi raudonai" (ONT) abi virsta `wan_link=down` — faktų
raktus perception gauna iš įrangos katalogo.

### 8 etapas — Greitis (2026-09-18)

Išmatuota (2026-09-15…17 voice skambučiai, maža imtis):

| Dalis | p50 | p90 | max |
|---|---|---|---|
| TTS vienam sakiniui (edge-tts, debesis) | 1,27 s | 4,26 s | 8,9 s |
| LLM (speak) | 0,95 s | 1,36 s | 1,85 s |
| LLM įvestis (promptas + kortelė + istorija) | 4,1k tok | 4,6k tok | — |
| narrate mazgas | 0,79 s | 2,1 s | 4,2 s |
| ASR (galutinis) | 0,54 s | 0,75 s | 1,2 s |
| ASR pabaiga → pirmas garsas | 2,9 s | 6,8 s | 10,6 s |
+ endpoint tylos laukimas prieš ASR: 350 ms (greitas) / 1400 (lėtas) / 1800 (problema nežinoma).

Pavyzdys (20260917-130120): scripted atsakymas „Klausau! Kuo galiu padėti?" —
LLM trace'e 0, bet narrate 4,1 s (paslėpti LLM kvietimai, B); kitame ėjime TTS
7,4 s 52 simboliams.

| ID | Radinys |
|---|---|
| **AL** | **TTS — didžiausias ir nestabiliausias vėlinimas** (edge-tts neoficialus debesies endpoint'as): p90 4,3 s vienam sakiniui. Scripted frazės kešuojamos tik dalinai (53 hit'ai iš 204). |
| **AM** | **Nėra pilno ėjimo laiko skaidymo**: `voice_latency` sujungia agentą ir TTS; paslėpti LLM kvietimai (B) — neįmanoma pasakyti, kur dingo 4,1 s. |
| **AN** | Kiekvieno ėjimo LLM įvestis ~4,1k tok (5 etapas) — ilgina TTFT; lokaliai (prefill) dar labiau. |
| **AO** | Endpoint laukimas iki 1,8 s prieš ASR — didelė, nematuojama dalis. |

Laiko biudžetas (tikslas: kalbos pabaiga → pirmas garsas ≤ ~1,5 s):
```
endpoint (semantinis)   350–700 ms   ← perception ant partial pasako „atsakymas pilnas"
ASR                       0–300 ms   ← partial pakartotinis naudojimas (D4 jau yra)
perception                0–150 ms   ← greitkelis / mažas lokalus modelis (F2)
decide                      ~0 ms   ← grynas (F1)
LLM iki 1-o sakinio      ~300 ms   ← trumpas promptas (5 etapas), mechaniniai ėjimai be LLM
TTS pirmi baitai      200–300 ms   ← srautinis / lokalus TTS, iš anksto sugeneruotos frazės
```

Kryptis:
- **Matavimas pirmiausia**: vienas `turn_timing` įvykis su laiko žymomis
  (kalbos pabaiga, endpoint, ASR, perceive, decide, LLM pirmas tokenas, pirmas
  sakinys, TTS pirmi baitai, garsas išsiųstas) + visi LLM kvietimai trace'e (B).
- **TTS**: visos scripted frazės ir užpildai sugeneruojami iš anksto (paleidžiant)
  → mechaniniai ėjimai be TTS laukimo; srautinis TTS (garsas groja nuo pirmų
  baitų); kito sakinio sintezė lygiagrečiai su grojimu; trumpas pirmas sakinys
  (reakcija) išsiunčiamas iškart; timeout → atsarginis balsas; lokalus TTS (11 etapas).
- **Agentas**: jau sutarti pakeitimai (F1 grynas decide, F2 vienas perception +
  greitkelis, 5 etapo trumpi promptai, analyst ne kritiniame kelyje, mechaniniai
  ėjimai be LLM) — sumažina LLM kvietimus ir įvestį.
- **Endpoint**: semantinis (perception ant partial) — pilnas atsakymas → 350 ms.
- **Užpildas** („Tuoj patikrinsiu…") tik kai žinoma, kad bus lėta (įrankis / LLM),
  iš anksto sugeneruotas.

**Sprendimas (Andrius, 2026-09-18):** TTS vėliau keičiamas lokaliu (kandidatas —
Piper; LT balso pasirinkimas — 11 etape). Dabar svarbiau, kad greitis ir kokybė
veiktų esamoje sistemoje; TTS pusėje dabar — tik iš anksto sugeneruotos frazės ir matavimas.

### 9 etapas — Kokybė: eval ir testai (2026-09-18)

Palikti (gera, stiprus pagrindas): 65 testų failai / 1242 testai; testų
žemėlapis su sluoksnių nuosavybe (`docs/TESTU_ZEMELAPIS.md`); eval 33
scenarijai / ~178 čekiai su tikru LLM, vertina BŪSENĄ (verdiktas, baigtis,
identifikacija, kontakto įrašas) + frazių sargus; `known_bug` mechanizmas
(klaida užfiksuojama scenarijumi, pataisius tampa privaloma); fuzz su LLM
„klientu" pagal personas; baseline prieš refaktoringą (105/108, 2 paleidimai).

| ID | Radinys |
|---|---|
| — | Patikrinta 2026-09-18 (`develop`): **1242 passed per 68 s** (TRACE_DIR nukreiptas į temp). |
| **AP** | **Vienetų testai išjungia LLM kelius**: `CLASSIFIER=off`, `ANALYST_MODE=off`, `NARRATOR_QUESTIONS=off` — supratimas, analyst ir naratoriaus direktyvos tikrinami tik eval'e. |
| **AQ** | **Eval tik tekstinis (sync)**: voice elgsena (async analyst, barge-in, partial ASR, STT darkymas) netikrinama — todėl C klaida praslydo. Atsakymų kokybė (vienas klausimas, tonas, ar remiasi kortele) nevertinama — tik frazės. |
| **AR** | **Nėra komponentų eval'ų**: supratimo (2 etapas), prompto/įgūdžio, latencijos regresijos; yra tik RAG eval. |
| **AS** | **Nestabilumas nematuojamas**: eval su tikru LLM paleidžiamas kartą (baseline — 2 kartus); nėra pass@k / stabilumo rodiklio. |
| **AT** | **Nėra grįžtamojo ryšio iš gyvų skambučių**: `needs_review` → žymėjimas → eval nesujungta; trace'ai užteršti testų (L). |
| **AU** | **Refaktoringo rizika**: dauguma 1242 testų pririšti prie dabartinės vidinės struktūros; F1–F3 daug jų sulaužys → elgsenos apsauga turi būti eval + auksiniai dialogai, o vienetų testai perrašomi naujiems sluoksniams. |

Kryptis — kokybės sistema sluoksniais:
```
1 KOMPONENTAI   perception eval (~200–300) · paieškos recall@k · įgūdžių validatoriai
                · decide lentelių testai (grynas → be LLM, iš kortelių)
2 KORTELĖS      kiekviena kortelė turi savo scenarijus (P-4) → auto paleidžiami
3 POKALBIAI     esamas eval + VOICE režimas (async analyst, STT triukšmo injekcija)
                + k paleidimų → stabilumas (pvz. 3/3 privaloma, 2/3 — įspėjimas)
                + atsakymo kokybės rubrika (deterministinė + LLM-teisėjas imtimi)
4 LATENCIJA     turn_timing biudžetai voice replay'uje (`replay_stt.py` jau yra)
5 PRODUKCIJA    needs_review → žymėjimo eilė → 1–3 papildymas (duomenų ratas)
CI: vienetai + schema + eval pogrupis kiekvienam pakeitimui; pilnas eval + fuzz — naktį / prieš merge
```

### Kliūtys plėtrai (iš A diskusijos)
1. Paketas = vienas telemetrijos verdiktas; diagnozė startuoja nuo interneto telemetrijos.
2. Tos pačios žinios aprašytos dukart: `evidence` (ledger + solver) ir `steps` (on/goto medis).
3. Variklio rolės kode (`verify_reboot`, `verify_line`, bridge…) — naujas įrenginys = programavimas.
4. GraphState pilna vienkartinių vėliavų, hint'uose „live 2026-…" lopai — trūksta bendrų sąvokų.
5. Vieno atsakymo skaitymas keliais keliais (keli LLM + regex).

---

## 3. Tikslinė architektūra (3 variantas)

```
 ėjimas ─► PERCEIVE ─► DECIDE ─────────► EXECUTE ─────────► NARRATE
          1 LLM        grynas (be I/O)    visi efektai        tik kalba
          + regex      1 dialogo mech.    per GATE            (phrase / LLM)
          greitkelis   2 byla (Case)      │
                       3 solver spragoms  │
                            ▲             │
                            └─ redecide ──┘  (reikia duomenų → įrankis → decide vėl)
```

- **Perceive:** vienas struktūrinis kvietimas (greitas modelis) vietoj
  understand / classify_step / classify_problem / ticket_reader.
- **Byla (Case):** problema (paslauga + simptomas), kandidatų sąrašas iš
  kortelių, įrodymai (telemetrija = vienas iš jų), aktyvus sprendimas.
- **Decide:** grynas; dialogo mechanika → bylos logika → LLM solver tik spragoms.
- **Execute:** close / register / bind / įrankiai — visi `Action` per gate.
- **Narrate:** jokių būsenos sprendimų.
- **Žinios:** kortelė v2 (vienas aprašymas: kada tinka · ką/kaip tikrinti ·
  reikšmė · sprendimai iš modulių · verify = kliento žodis + zondas),
  `equipment.yaml` (įrenginiai, lemputės, perkrovimas, zondai),
  parametrizuojami moduliai, `scenarios/` testai kortelei.

### Migracija

| Etapas | Turinys |
|---|---|
| F0 | Auksiniai dialogai 7 pack'ams; B, C taisymai |
| F1 | Išgryninti decide: close/register/bind → `Action` per gate; reply layer + backstop į decide per redecide ciklą; narrate be sprendimų |
| F2 | Vienas perception kontraktas |
| F3 | Case + kortelė v2 + bendras verify; konverteris esamiems pack'ams; rolės → moduliai |
| F4 | `equipment.yaml` + lėtas internetas ir TV — tik failais |
| F5 | Išvalyti vėliavas, ištrinti senus kelius |

---

## 4. Taisymų planas (10 etapas, 2026-09-18)

Sprendimas (Andrius): atskiro vertinimo rinkinio PRIEŠ keitimus nekuriame —
keičiame iš karto ir kiekvienoje bangoje rašome gebėjimų testus (P-9).
Apsauga: esami 1242 testai + esamas eval (33 scen.) paleidžiamas bangos
pradžioje ir pabaigoje (nieko naujo kurti nereikia; baseline 2026-09-14 jau yra).
Senieji testai, tikrinantys pakeičiamą vidų, trinami / perrašomi TAME PAČIAME pakeitime.

```
BANGA 0  greiti taisymai ─ lygiagrečiai, maži atskiri pakeitimai
   │
BANGA 1  F1 grynas decide ─ nuosekliai, pamatas visam kitam
   │
   ├──► BANGA 2a  F2 Perception (+ analyst per inbox, semantinis endpoint)
   ├──► BANGA 2b  Promptai pagal įgūdį + validatoriai          ← lygiagrečiai
   └──► BANGA 2c  Įrankių manifestai + gateway (P-7)
            │
BANGA 3  F3 Case + kortelė v2 + moduliai + įrangos katalogas (P-6, P-8)
   │
BANGA 4  F4 nauji domenai tik failais (lėtas internetas, TV) + RAG atviriems klausimams
   │
BANGA 5  F5 valymas
            … vėliau: 11 lokalūs modeliai (Piper, LLM, embeddings) · 12 integracija
```

| Banga | Turinys (radiniai) | Testai (P-9) | Priklauso nuo |
|---|---|---|---|
| **0** | C analyst per inbox · B visi LLM kvietimai trace'e · L testų TRACE_DIR · AM `turn_timing` įvykis · AC `max_tokens≈150` + stop · AB sakinio validatorius prieš TTS (≤1 „?", ilgis, draudžiamos frazės) · AL iš anksto sugeneruotos scripted frazės · S/X ReAct palikimo trynimas · E komentarai · AQ/AS eval: voice (async analyst) režimas + k paleidimų | C atkūrimo testas; validatoriaus lentelė; trace įvykių testai | — |
| **1** | F1: close / register / bind / hang-up → `Action` per VIENĄ gate (A, R, AF) · `plan_reply` + backstop → decide per redecide ciklą · narrate tik kalba · `maybe_end_on_goodbye` pašalinamas · observe grandinės → veiksmai (T) · perceive tik skaito (J) · vienas klausimų registras (Q) | decide lentelės: būsena → planas; gate lentelės | 0 |
| **2a** | F2: vienas `Perception` (G, H, K) · greitkelis be LLM · citatos prie faktų · faktų priėmimo politika decide'e · analyst → inbox → Perception, paleidžiamas pagal trigerius (AD, AE) · semantinis endpoint (AO) · perception eval rinkinys (~200–300) | greitkelio lentelės; faktų politikos lentelės; komponentų eval | 1 |
| **2b** | Promptai pagal įgūdį (Y, Z, AA, AN): branduolys + įgūdis + pavyzdžiai + ribota kortelė; istorija 4–6; lopų pastabos → testai | įgūdžio validatoriai; komponentų eval | 1 |
| **2c** | Įrankių manifestai (P-7, V, W): capability portai, saugikliai, timeout / limitai / on_failure, demo adapteris, fake adapteris gedimams | kiekvieno įrankio kontrakto lentelės (ok / timeout / limitas / neveikia) | 1 |
| **3** | F3: Case, keli kandidatai, skiriantys klausimai, vienas sprendėjas (N, O, P, P-6) · kortelė v2 + konverteris 7 pack'ams (AG) · moduliai parametrizuoti (AH) · įrangos katalogas modelis → šeima → bazinė (AI, P-8) · verdict medis → faktai + taisyklės failuose (U) · solver = spragų pildytojas | kortelių scenarijai; Case lentelės; hierarchijos lentelės | 2a, 2c |
| **4** | F4: lėtas internetas + TV tik failais (įrodymas P-4) · RAG atviriems klausimams su įrangos filtru (AJ, AK) · pavyzdžių bankas (dinaminiai few-shot) · paieškos recall@k | paieškos lentelės; naujų kortelių scenarijai | 3, 2b |
| **5** | F5: vienkartinės vėliavos, seni keliai, pavadinimai, LT/EN raktai, testų žemėlapio atnaujinimas | pilnas paleidimas | 4 |

Taisyklės darbui:
- Kiekviena banga — atskira šaka nuo `develop`; commit'ai EN; push + compare URL,
  PR kuria Andrius.
- Banga baigiama pilnai (kodas + testai + eval), tik tada testuojama gyvai.
- Kiekvienos bangos pabaigoje — įrašas čia: kas padaryta, eval rezultatas, kas liko.

# Kaip tikrinti ir taisyti agentą — darbo instrukcija (2026-10-23)

Kam: kai taisai vieną sritį (identifikaciją, problemą, tyrimą, tiketą, pabaigą, kortelę, promptą)
ir nori patikrinti būtent ją, nepaleisdamas visų testų. Ir kai neveikia demo scenarijus —
kur žiūrėti, kaip rasti priežastį, ką keisti.

## 1. Trys tikrinimo lygiai

```
  greitai, be LLM, nemokamai                                  lėčiau, su LLM, kainuoja
  ┌────────────────────┐   ┌──────────────────────┐   ┌──────────────────────────┐
  │ 1. TESTAI (pytest) │ → │ 2. EVAL (scenarijai)  │ → │ 3. GYVAS SKAMBUTIS       │
  │ sritis: sekundės   │   │ vienas: ~10–30 s      │   │ dashboard'e, „Scenarijai“│
  │ visi: ~5 min       │   │ ~0,005 USD/scenarijus │   │ balsu arba tekstu        │
  │ LLM pakeistas      │   │ tikras LLM            │   │ tikras LLM + balsas      │
  │ tikrina VARIKLĮ    │   │ tikrina visą pokalbį  │   │ tikrina, kaip skamba     │
  └────────────────────┘   └──────────────────────┘   └──────────────────────────┘
```

- **Testai** tikrina, ką nusprendė variklis: taisyklę, būseną, įrankius, kortelę, varikliui
  priklausančias frazes žodis į žodį. Modelio žodžiai pakeisti `‹LLM›`.
- **Eval** paleidžia scenarijų su tikru modeliu ir tikrina rezultatą: kortelę (verdict),
  baigtį, kontakto įrašą, ar atsakymuose yra (nėra) tam tikrų žodžių.
- **Gyvas skambutis** parodo, kaip tai skamba ir atrodo.

Taisant eini iš kairės į dešinę: pirma testai (greitai), tada eval, tada gyvas skambutis.

## 2. Kur kas gyvena — sritis → failai → testai

| Sritis | Kodas (`chatbot_core/src/agent/`) | Žinios (keičiama dažniausiai) | Testai (`chatbot_core/tests/`) | Žymė |
|---|---|---|---|---|
| Identifikacija | `decide/rules/identification.py`, `perceive/nlu.py` | `knowledge/identification.yaml` | `identification/` | `identification` |
| Problema | `perceive/nlu.py`, `perceive/classifier.py`, `decide/rules/intake.py` | `knowledge/intents.yaml` | `problem/` | `problem` |
| Supratimas (kliento atsakymų skaitymas) | `perceive/detectors.py`, `perceive/understand.py` | `locales/lt/vocabulary.yaml`, `knowledge/detectors.yaml` | `understanding/` | `understanding` |
| Tyrimas (kortelės, žingsniai) | `case.py`, `facts.py`, `decide/rules/case_rule.py` | `knowledge/v2/cards/*.yaml`, `knowledge/v2/modules/*.yaml`, `knowledge/signals.yaml`, `knowledge/verdicts.yaml` | `diagnosis/` | `diagnosis` |
| Tiketas | `decide/rules/ticket.py`, `execute/ticket.py`, `executor_flow.py` | `knowledge/registracija.yaml`, `knowledge/ticket_types.yaml` | `ticket/` | `ticket` |
| Pabaiga | `closing.py`, `decide/rules/closing.py`, `call_record/` | — | `closing/` | `closing` |
| Kalba (ką ir kaip sako) | `speak/context_card.py`, `speak/node.py` | `locales/lt/phrases.yaml`, `prompts/speak/system.md`, `prompts/skills/*.md`, `prompts/phases/*.md` | `speaking/` | `speaking` |
| Žinių failų taisyklingumas | `contract/` | visi `knowledge/` ir `locales/` failai | `contract/` | `contract` |
| Variklis (fazės, taisyklių tvarka) | `decide/policy.py`, `graph_v2/` | `knowledge/policies.yaml` | `engine/` | `engine` |

Kitos sritys: `knowledge` (žinių bazė, RAG), `tools`, `llm`, `voice`, `observe` (stebėsena).
Visų testų žemėlapis: [TESTU_ZEMELAPIS.md](TESTU_ZEMELAPIS.md). Kaip testai sudaryti:
[TESTAI_PAGAL_FUNKCIJAS.md](TESTAI_PAGAL_FUNKCIJAS.md).

## 3. Testų paleidimas pagal sritį

Visos komandos — iš aplanko `chatbot_core`. PowerShell'e, kad lietuviškos raidės ataskaitoje
būtų teisingos, vieną kartą lange:

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

| Ką tikrini | Komanda | Laikas |
|---|---|---|
| Vieną sritį | `uv run pytest -m identification -q` | ~10 s |
| Kelias sritis | `uv run pytest -m "diagnosis or ticket" -q` | ~1 min |
| Vieną funkciją (failas = funkcija) | `uv run pytest tests/diagnosis/test_steps.py -q` | ~15 s |
| Vieną variantą (pagal pavadinimą) | `uv run pytest tests/diagnosis/test_steps.py -q -k "patikra"` | ~10 s |
| Ar žinių failai taisyklingi (po kortelės, frazės keitimo) | `uv run pytest -m contract -q` | ~10 s |
| Viską (prieš commit) | `uv run pytest -q` | ~5 min |

Pabaigoje — **funkcijų ataskaita**:

```
Tyrimas
  ✓ Atsakymai žingsniuose.. 41/41   (5 žinomos spragos)
      · spraga: perkrovimas: dar ne — „dar ne“ laikomas atliktu …
  ✗ Visa fazė.............. 13/14
      ✗ sveika iki routerio — AssertionError: …
```

- `✓` — funkcija veikia; `✗` — sugedo, po ja parašyta, kuris variantas ir kodėl.
- `spraga` — žinoma, dar netaisyta (`xfail`). Ji testo nesugadina.
- Kai spragą pataisai, testas **krenta** su „XPASS(strict)“. Tai gera žinia: nuimk tą
  `xfail` žymę, ir testas tampa tikru testu.

## 4. Eval — scenarijus su tikru LLM

```powershell
uv run python src/agent/eval/run_eval.py --only S9_client_side_phone_wifi
uv run python src/agent/eval/run_eval.py --only D8_router_hung --runs 3      # ar stabilu: 3 kartus
uv run python src/agent/eval/run_eval.py                                     # visi 48 (~0,2 USD)
```

Kiekvieno scenarijaus išvestyje yra `trace:` kelias. Tą skambutį galima atsidaryti
dashboard'e („Stebėsena“ → eval paleidimai) arba skaityti failą `logs/eval/*.jsonl`.

**Kurie eval scenarijai tikrina kurią kortelę** (kai pakeiti kortelę, paleisk šiuos):

| Kortelė | Eval scenarijai |
|---|---|
| `router_hung` | S6, D8, D8b, D8c, D8d, D8e, A1, R3, C1 |
| `no_mac_observed` | S4, S4b, S4c, S4d, S4e, S4f |
| `foreign_mac` | S1, S1v, K1 |
| `healthy_to_router` | S9, C2 |
| `dhcp_silent` | X_dhcp_silent |
| `link_down_local` | D5_link_down |
| `crc_errors` | D6_crc |
| `switch_unreachable` | S3, D4_switch |
| `node_fault_unregistered` | D3_node_fault |
| `billing_suspended` | S8_billing_inform, S8b, R4, G1 |
| `active_outage` | D2_outage, D2b |
| `open_ticket_exists` | R2 |
| `service_not_subscribed` | S10 |
| `unclear_fault` | T1 |
| identifikacija, prašymai | I1–I8, T2, U1, R1, R1b, S8_outage_inform |

Pilni id ir kiekvieno scenarijaus aprašymas: `src/agent/eval/scenarios.json`,
[eval/README.md](../../chatbot_core/src/agent/eval/README.md).

## 5. Neveikia scenarijus — darbo eiga

```
 1. ATKURTI      dashboard „Scenarijai“ → skambutis   arba   eval --only <id>
        │
 2. PAŽIŪRĖTI    „Archyvas“ → skambutis → ėjimas, kuriame suklydo:
        │        ką išgirdo · kaip perskaitė · kuri taisyklė · kuri kortelė ·
        │        ką gavo LLM (tikslas, įvestis) · ką pasakė
        │
 3. KUR KLAIDA?  ──► žr. medį žemiau
        │
 4. TESTAS       parašyk variantą, kuris dabar krenta (to kreipimosi žodžiai)
        │        tame srities faile → pamatai ✗
        │
 5. TAISYTI      vieną vietą: žodyną / kortelę / frazę / promptą / taisyklę
        │
 6. TIKRINTI     sritis (-m <sritis>) → contract → susiję eval → gyvas skambutis
        │
 7. VISKAS       uv run pytest -q → commit
```

**3 žingsnis — kur ieškoti klaidos:**

```
Ar agentas TEISINGAI SUPRATO, ką pasakė klientas?   (Archyvas: „perskaitė“)
 ├─ NE  → Supratimas: žodynas `locales/lt/vocabulary.yaml` arba skaitytuvas
 │        testai: tests/understanding/, tests/diagnosis/test_steps.py
 │        pagalba: `uv run python ../scripts/reader_silent.py --days 1`  (ko nesuprato)
 │
 └─ TAIP → Ar pasirinko TEISINGĄ KORTELĘ?           (Archyvas: „kortelė“, „galimi gedimai“)
     ├─ NE  → kortelės `when` / `rules_out`, `knowledge/signals.yaml` (telemetrija → faktai)
     │        testai: tests/diagnosis/test_phase.py, test_case_candidates.py
     │
     └─ TAIP → Ar padarė TEISINGĄ ŽINGSNĮ?           (Archyvas: „taisyklė“, „žingsnis“)
         ├─ NE  → kortelės `needs` / `solution`, modulis `knowledge/v2/modules/`,
         │        arba variklio taisyklė `decide/rules/*.py` (čia — aptarti prieš keičiant)
         │        testai: tests/diagnosis/test_steps.py, tests/engine/
         │
         └─ TAIP → Ar GERAI PASAKĖ?                  (Archyvas: LLM tikslas ir atsakymas)
             ├─ variklio frazė blogai → `locales/lt/phrases.yaml`
             └─ modelis pasakė blogai → `prompts/skills/*.md`, `prompts/speak/system.md`,
                 tikslas iš `speak/context_card.py`; testai: tests/speaking/;
                 eval `reply_any` / `reply_none`
```

Taisyklė: **variklis sprendžia, LLM tik sako.** Jei agentas *padarė* ne tai — klaida yra
variklyje arba žiniose (kortelėje, žodyne), ne prompte. Promptą keisk tik tada, kai
sprendimas teisingas, o žodžiai — ne.

## 6. Kortelių tikrinimas

**Kortelė** (`knowledge/v2/cards/<gedimas>.yaml`) — vienas gedimas:

```yaml
fault: healthy_to_router          # gedimo vardas
when:     {all: [node_reachable=yes, line_link=up, traffic=flowing]}   # kada tinka (telemetrijos faktai)
rules_out: [area_outage=yes, device_seen=no, …]                        # kas ją atmeta
needs:                            # ką paklausti kliento (faktai, kurių telemetrija nežino)
  fail_scope: {ask: "pack.healthy_to_router.fail_scope.question", values: {all: …, one: …}}
solution:                         # ką daryti, pagal atsakymus
  - when: [fail_scope=all, rebooted=no]
    steps: [{module: reach}, {module: reboot}, {module: verify}]
escalate: {note: "…"}             # ką parašyti tikete, kai telefonu neišsprendžiama
```

Sakiniai, kuriuos girdi klientas, — `locales/lt/phrases.yaml` (raktai `pack.<gedimas>.…`).
Kaip kortelė tampa tiketu — `knowledge/ticket_types.yaml` (`by_verdict`).

**Pakeitei kortelę — tikrink taip:**

```powershell
uv run pytest -m contract -q                               # ar failas taisyklingas
uv run pytest tests/diagnosis -q                            # ar demo linijos vis dar pasiekia savo korteles
uv run python src/agent/eval/run_eval.py --only <id>       # susiję eval (lentelė 4 skyriuje)
```

Veikiančiam serveriui naujos žinios įkeliamos be perkrovimo (klaidingas failas grąžina
klaidų sąrašą, o senos žinios lieka):

```powershell
Invoke-RestMethod -Method Post http://localhost:8080/admin/knowledge/reload
```

**Demo klientas kiekvienai kortelei** (jo linija rodo tą gedimą; naudojama ir testuose,
`tests/phases.py`):

| Kortelė | Klientas | Telefonas |
|---|---|---|
| `router_hung` | CUST112 | +37060020112 |
| `no_mac_observed` | CUST009 (demo) / CUST001 (testai) | +37060012353 / +37060012345 |
| `foreign_mac` | CUST105 | +37060020105 |
| `link_down_local` | CUST104 | +37060020104 |
| `dhcp_silent` | CUST106 | +37060020106 |
| `crc_errors` | CUST305 | +37060030305 |
| `healthy_to_router` | CUST109 | +37060020109 |
| `billing_suspended` | CUST101 | +37060020101 |
| `active_outage` | CUST102 | +37060020102 |
| `switch_unreachable` | CUST103 | +37060020103 |
| `node_fault_unregistered` | CUST306 | +37060030306 |

## 7. Promptų ir fazių tikrinimas

| Kas | Kur | Testai |
|---|---|---|
| Bendras kalbėtojo promptas | `prompts/speak/system.md` | `tests/speaking/test_prompts.py` |
| Kiekvieno ėjimo užduotis („skill“) | `prompts/skills/*.md` (ask_fact, instruct_step, sum_up, goodbye …) | `tests/speaking/` |
| Promptas pagal fazę | `prompts/phases/*.md` | `tests/speaking/test_prompt_by_phase.py` |
| Skaitytuvų promptai (supratimas) | `prompts/sensors/*.md` | `tests/understanding/`, `tests/llm/` |
| Fazės ir perėjimai | `graph_v2/`, `decide/policy.py` | `tests/engine/test_phases.py` |

- **Kokį promptą modelis gavo konkrečiame ėjime**: Archyvas → ėjimas → LLM įvestis. Pilna
  įvestis rašoma kūrimo režime (`DEBUG_LLM=full`, numatyta).
- **Ar fazė prasideda teisingai**: testų fiksatoriai pradeda pokalbį nuo fazės
  (`identified` — po identifikacijos, `diagnosing` — tyrimo pradžia). Taip tyrimo testas
  nesugenda dėl identifikacijos klaidos. Žr. [TESTAI_PAGAL_FUNKCIJAS.md](TESTAI_PAGAL_FUNKCIJAS.md).
- **Ar fazė neperšoka**: „Stebėsena“ žymi „neleistinas fazės perėjimas“.

## 8. Kur stebėti elgesį dashboard'e

Paleidimas: `uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080` (iš projekto
šaknies), tada http://localhost:8080.

| Skirtukas | Kam |
|---|---|
| **Testavimas** | gyvas skambutis; eiga ėjimais pagal variklio dalis (išgirdo → perskaitė → nusprendė → įrankiai → pasakė) |
| **Scenarijai** | demo scenarijai su laukiama kortele ir baigtimi; po skambučio ✓/✗ |
| **Archyvas** | baigtas skambutis ėjimas po ėjimo; LLM pagal tikslą: tikslas → įvestis → išvestis |
| **Stebėsena** | baigtys, kur nutrūksta pagal fazę, naudotos kortelės, ko nesuprato, delsa, kaina, peržiūros eilė; gyvi skambučiai arba eval paleidimai, pagal versiją |

## 9. Prieš commit

```
[ ] srities testai žali (uv run pytest -m <sritis> -q)
[ ] uv run pytest -m contract -q
[ ] susiję eval scenarijai PASS
[ ] visi testai: uv run pytest -q
[ ] radinys / pataisymas įrašytas TESTAI_PAGAL_FUNKCIJAS.md
[ ] šaka patikrinta (git branch --show-current), commit angliškai
```

## 10. Toliau

1. **Demo peržiūra**: kiekvienas „Scenarijų“ skirtuko scenarijus — gyvas skambutis →
   Archyvas → kortelė (`when`, `needs`, `solution`) → ar elgesys toks, kokio nori. Radiniai —
   į testus (`xfail`), tada taisymas pagal 5 skyrių.
2. **Naujas gedimas žingsnis po žingsnio**: kortelė → frazės → demo klientas (seed) →
   testai → eval scenarijus → gyvas skambutis. Pastaba: [instructor/FAULT_PACKS.md](../instructor/FAULT_PACKS.md)
   aprašo seną (v1, `faults/*.yaml`) formatą; v2 kortelių gidas bus parašytas einant per
   naują gedimą (ROADMAP D2).

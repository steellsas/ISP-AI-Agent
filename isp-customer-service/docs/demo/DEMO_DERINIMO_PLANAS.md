# Demo derinimo planas (sudarytas 2026-10-23, pradžia pirmadienį)

**Tikslas.** Pereiti demo scenarijus vieną po kito ir išmokti savarankiškai tikrinti agentą:
kaip jis identifikuoja klientą, supranta problemą, renkasi kortelę, kokias žinias ir įrankius
naudoja, ką sako. Rasti, ką reikia pataisyti, ir taisyti pačiam.

**Darbo taisyklės**

- Vienas scenarijus per sesiją. Neskubam: pirma suprantam, tada tikrinam, tada keičiam.
- Pakeitimus darai **tu**. Aš paaiškinu, kur žiūrėti, ką paleisti ir ką reikštų pakeitimas.
- Nieko nekeičiam be aptarimo: ką pakeitimas duos, ką gali sugadinti, kuriais testais tai
  patikrinsim.
- Viskas, ką randam, įrašoma į [DERINIMO_RADINIAI.md](DERINIMO_RADINIAI.md), net jei
  netaisom iš karto.
- Komandos ir failų žemėlapis: [../testing/KAIP_TIKRINTI_IR_TAISYTI.md](../testing/KAIP_TIKRINTI_IR_TAISYTI.md).

## 1. Vieno scenarijaus ciklas

```
 ① LAUKIAMA EIGA      kartu surašom: ką klientas sako → ką agentas turi padaryti ir pasakyti
        │             (ėjimas po ėjimo, darbo lape)
        ▼
 ② ŽINIOS IR KODAS    atsidarom kortelę, modulius, frazes, promptus; kur kode tai vyksta
        │             (tik skaitom ir suprantam)
        ▼
 ③ TESTAI PRIEŠ       srities testai + susiję eval → žinom, nuo ko pradedam (žalia / spragos)
        │
        ▼
 ④ SKAMBUTIS          „Scenarijai“ → ▶ → skambini balsu arba tekstu pagal darbo lapą
        │
        ▼
 ⑤ ANALIZĖ            „Archyvas“ → ėjimas po ėjimo lyginam su ① ; logai
        │             kiekvienas nesutapimas → radinių žurnale
        ▼
 ⑥ APTARIMAS          ką norim keisti, ką tai duos, kur keisti (žodynas / kortelė /
        │             frazė / promptas / taisyklė), kuris testas tai įrodys
        ▼
 ⑦ PAKEITIMAS         tu keiti → testas (pirma krenta, po pakeitimo žalias) → sritis → eval
        │             → pakartotinis skambutis
        ▼
 ⑧ UŽDARYMAS          darbo lapas užpildytas, radiniai pažymėti, commit
```

Sesijos trukmė: ①–⑤ ~1,5–2 val.; ⑥–⑧ — atskirai, kai yra ką keisti.

## 2. Pasiruošimas (pirmadienio pradžia, ~1 val.)

| # | Ką daryti | Kaip |
|---|---|---|
| 0.1 | Naujausias kodas | `git switch develop` ir `git pull` (prieš tai sujunk atvirus PR) |
| 0.2 | Perkurti demo DB (nauji tiketų tipai) | iš projekto šaknies: `uv run python scripts/setup_db.py`, tada `uv run python scripts/seed_data.py` |
| 0.3 | Paleisti serverį | `uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080` → http://localhost:8080 |
| 0.4 | Bazinė būsena | iš `chatbot_core`: `uv run pytest -q`. Užsirašyk: kiek praėjo ir kiek spragų |
| 0.5 | Perskaityti, kaip veikia ėjimas | [ARCHITECTURE.md](../ARCHITECTURE.md) §3–§6 (~30 min): skambutis, ėjimas, taisyklių grandinė, Case, skaitymas |
| 0.6 | Atsidaryti redaktoriuje | kortelę `knowledge/v2/cards/router_hung.yaml`, `locales/lt/phrases.yaml`, `locales/lt/vocabulary.yaml`, `prompts/skills/` |
| 0.7 | Bandomasis skambutis | „Scenarijai“ → „Pakibęs routeris“ → ▶. Tikslas — tik pamatyti skirtukus: Testavimas (eiga gyvai), Archyvas (ėjimai), Stebėsena |

PowerShell'e, kad testų ataskaitoje būtų lietuviškos raidės: `$env:PYTHONIOENCODING = "utf-8"`.

## 3. Scenarijų eilė

Pirmas scenarijus eina per visą pokalbį (identifikacija, problema, kortelė, žingsniai,
pabaiga), todėl ilgiausias. Toliau — tik tai, kas nauja.

| Sesija | Scenarijus (skirtukas „Scenarijai“) | Kortelė | Ko mokomės | Žinomos spragos |
|---|---|---|---|---|
| 1 | **Pakibęs routeris** (`router_hung`, +37060020112) | `router_hung` | visa grandinė: pasisveikinimas → numerio paieška → adresas → vardas → telemetrija → radinys → perkrovimas → patikra → pabaiga | „Dar ne“ po perkrovimo |
| 2 | **Miręs routeris** (`dead_router`, +37060012353) | `no_mac_observed` | klausimai (lemputės, maitinimas), laikinas internetas per kompiuterį (tiltas), išvada, tiketas `equipment_replacement` | „Įjungtas“, „Įkišau dabar“; lemputės dega → kortelė neatmetama |
| 3 | **Pakeistas routeris** — scenarijaus dar nėra, sukursim (`scenarios.yaml`, CUST105 +37060020105) | `foreign_mac` | variklio veiksmas (MAC pririšimas, prievado perkrovimas), patikra per telemetriją | — |
| 4 | **Neveikia tik telefone** (`phone_only`) ir **neatsakytas klausimas** (`unanswered_question`) | `healthy_to_router` | kliento pusė, prielaidos (`assume`), naujas „nebaigtas“ kelias | — |
| 5 | **Linija nutrūkusi** (`link_down`), **CRC** (`crc`) | `link_down_local`, `crc_errors` | tinklo pusė, meistro tiketas, `only_after` | — |
| 6 | **Routeris pametė nustatymus** (`dhcp_silent`) | `dhcp_silent` | rašytinė procedūra, vedimas žingsniais, žinių bazė | — |
| 7 | **Avarija**, **switch**, **mazgas** (`outage`, `switch`, `node_fault`) | `active_outage`, `switch_unreachable`, `node_fault_unregistered` | žinios (inform), `network_fault` tiketas, „informuotas“ | — |
| 8 | **Skola**, **ginčijama skola**, **sąskaitos klausimas** | `billing_suspended`, prašymai | informavimas, prašymo tiketas atsakingam žmogui | — |
| 9 | **Pakartotinis**, **TV** (3 scenarijai), **neidentifikuotas** | `open_ticket_exists`, `service_not_subscribed`, `unclear_fault` | pastaba prie tiketo, paslaugų profilis, neaiškus gedimas | — |
| 10 | **Naujas gedimas žingsnis po žingsnio** | nauja | kortelė → frazės → demo klientas → testai → eval → skambutis; kartu rašom v2 kortelių gidą | — |

Šakos, kurias verta išbandyti kiekviename scenarijuje (po pagrindinio kelio): „negaliu dabar
prieiti“, klientas nori meistro, klientas paklausia ko nors kito, padeda ragelį vidury
pokalbio.

## 4. Darbo lapo šablonas

Kiekvienam scenarijui — failas `docs/demo/lapai/<nr>_<scenarijus>.md`:

```markdown
# <Scenarijus> — darbo lapas (data)

## ① Laukiama eiga
| # | Klientas sako | Agentas turi padaryti | Agentas turi pasakyti | Taisyklė (rule) |

## ② Žinios ir kodas
- Kortelė: … (`when`, `rules_out`, `needs`, `solution`, `escalate`)
- Moduliai: …   Frazės: …   Žinių bazė: …   Įrankiai: …
- Kodas, kurį verta žinoti: …

## ③ Testai prieš
- komandos ir rezultatas

## ④ Skambutis
- kada, balsu / tekstu, sesijos id (Archyve)

## ⑤ Ką pamatėm (ėjimas po ėjimo)
| # | Laukta | Įvyko | Gerai? | Pastaba |

## ⑥ Ką keičiam (aptarta)
| Radinys | Kur keisti | Ką duos | Rizika | Testas |

## ⑦ Po pakeitimo
- testai, eval, pakartotinis skambutis
```

## 5. Ką žiūrėti kiekviename ėjime (⑤ analizė)

Archyve atidaryk skambutį ir kiekviename ėjime eik iš viršaus žemyn:

```
 IŠGIRDO      ar tekstas toks, kokį sakei? (balsu — ASR klaidos)
    ▼
 PERSKAITĖ    kas perskaitė: variklis (engine / fast_path) ar modelis (llm)? kokie faktai?
    ▼
 NUSPRENDĖ    kuri taisyklė (rule)? kas ją laimėjo? (policy: kurios atsisakė)
    ▼
 KORTELĖ      kuri kortelė aktyvi, kuris žingsnis, ko laukiama (awaiting)?
    ▼
 ĮRANKIAI     kas paleista (find_customer, resolve_address, diagnose_connection, …), ką grąžino?
    ▼
 PASAKĖ       variklio frazė ar LLM? jei LLM — koks buvo tikslas (goal) ir ką gavo įvestyje?
    ▼
 LAIKAS       kur sugaišta (LLM, TTS)?
```

Logai, jei Archyvo neužtenka: gyvi skambučiai `logs/sessions/`, eval — `logs/eval/` (vienas
`.jsonl` failas skambučiui, eilutė = įvykis).

---

## 6. Sesija 1 — „Pakibęs routeris“: darbo lapas (paruoštas)

Klientas Paulius, +37060020112, Šiauliai, Vilniaus g. 33-2 (CUST112). Telemetrija: routeris
matomas linijoje, adresą gavo, bet srautas nevaikšto.

### ① Eiga, kurią šiandien daro variklis (patikrinta testu su netikru LLM)

| # | Klientas sako | Ką daro variklis | Ką sako agentas | Taisyklė |
|---|---|---|---|---|
| 0 | — | numerio paieška (`find_customer`) — kandidatas, dar ne patvirtintas | „Labas! Čia Andriuko IT pagalba… Kuo galiu padėti?“ (frazė) | `dialog.greeting` |
| 1 | „Neveikia internetas visuose įrenginiuose“ | perskaito problemą `internet_down`; siūlo rastą adresą | „Gerai — patikrinsiu ryšį. Ar skambinate dėl Vilniaus g. 33, butas 2?“ (frazė) | `identification.address_move` |
| 2 | „Taip“ | patvirtina adresą (`resolve_address`); paleidžia telemetriją (`diagnose_connection`); Case randa kortelę `router_hung` ir radinį | „Supratau — … Tuoj patikrinsiu ryšį iki jūsų buto. O su kuo kalbu — koks jūsų vardas?“ (frazė) | `identification.caller_name` |
| 3 | „Paulius“ | vardas įrašomas; pasakomas radinys | **LLM** (`ask_identity`): radinys — routeris matomas, bet srautas nevaikšto; **jokio žingsnio dar neprašo** | `identification.result_to_procedure` |
| 4 | „Taip, galiu prieiti“ | `reach` įvykdytas (pasakė pats) → perkrovimo instrukcija | **LLM** (`instruct_step`): perkraukite routerį iš maitinimo | `case.reboot` |
| 5 | „Perkroviau, internetas atsirado“ | demo: linija parodo perkrovimą (`simulate_router_reboot`), telemetrija iš naujo (`diagnose_connection`) — srautas yra, klientas patvirtino → išspręsta | **LLM** (`explain_finding`): matome srautą, išspręsta; „Ar dar kuo galiu padėti?“ | `case.resolved` |
| 6 | „Ne, ačiū, viso gero“ | uždaro skambutį | „Ačiū, kad paskambinote. Geros dienos!“ (frazė) | `closing.goodbye` |

Rezultatas: kontakto įrašas `resolved`, be tiketo, be peržiūros žymos.

**Klausimai, kuriuos aptarsim prieš skambutį** (ar taip ir turi būti?):

- 3 ėjimas: radinys pasakomas, bet žingsnio neprašoma (sprendimas 2026-09-23). Klientas turi
  ką nors atsakyti, kol agentas paprašys prieiti prie routerio. Ar balsu tai natūralu?
- 4 ėjimas: trace'e yra `stall` įvykis — pažiūrėsim, ką jis reiškia.
- Klausimo „ar galite prieiti“ nebuvo, nes klientas pasakė pats. Jei klientas tik pasakys
  „Gerai“ — agentas paklaus (patikrinsim šaka).

### ② Žinios ir kodas — ką atsidaryti ir ką juose žiūrėti

| Kas | Failas (`chatbot_core/src/agent/`) | Ką žiūrėti |
|---|---|---|
| Pasisveikinimas, numerio paieška | `execute/identification.py` (`preflight_phone`), `knowledge/tools/find_customer.yaml` | kodėl rastas adresas yra tik kandidatas |
| Identifikacija | `decide/rules/identification.py`, `knowledge/identification.yaml` | adreso patvirtinimas, vardo klausimas |
| Problemos supratimas | `knowledge/intents.yaml` (`internet_down`), `perceive/nlu.py` | kaip „neveikia internetas“ tampa `internet_down` |
| Telemetrija → faktai | `knowledge/tools/diagnose_connection.yaml`, `knowledge/signals.yaml`, `facts.py` | kokie faktai gaunami: `device_seen`, `dhcp`, `traffic` |
| Kortelė | `knowledge/v2/cards/router_hung.yaml` | `when` (kada tinka), `rules_out`, `needs.lights`, `solution` (reach → reboot → verify), `escalate.only_after` |
| Moduliai | `knowledge/v2/modules/reach.yaml`, `reboot.yaml`, `verify.yaml` | kaip klausiama, kaip skaitomas atsakymas (`detector`, `answers`) |
| Įrangos žodžiai | `knowledge/v2/equipment/` | kaip perkrauti būtent šį routerį |
| Frazės | `locales/lt/phrases.yaml` (`pack.router_hung.*`, `verdict.router_hung.*`) | radinio ir tiketo žodžiai |
| Žodynas | `locales/lt/vocabulary.yaml` (`reach_there`, `reported_reboot`, `restored_no`, `in_progress`) | kokie žodžiai skaitomi be modelio |
| Žinių bazė | `src/rag/knowledge_base/troubleshooting/internet_pakibes_routeris.md` | ką modelis gauna kaip žinias |
| Promptai | `prompts/speak/system.md`, `prompts/skills/ask_identity.md`, `instruct_step.md`, `explain_finding.md` | ką modelis gauna 3–5 ėjimuose |
| Case logika | `case.py` (`judge`, `candidates`), `decide/rules/case_rule.py` | tik suprasti; čia keičiam tik aptarę |

### ③ Testai prieš skambutį

```powershell
uv run pytest -m identification -q
uv run pytest tests/diagnosis/test_router_hung.py tests/diagnosis/test_phase.py -q
uv run pytest tests/diagnosis/test_steps.py -q -k "perkrovimas or patikra"
uv run python src/agent/eval/run_eval.py --only D8_router_hung
uv run python src/agent/eval/run_eval.py --only C1_no_question_before_the_reboot
```

### ④ Skambutis

„Scenarijai“ → „Pakibęs routeris“ → ▶. Kai agentas paprašo perkrauti — spausk 🔄 Routeris,
tada sakyk „Perkroviau“. Po pagrindinio kelio išbandyk šakas:

- „Negaliu dabar prieiti“ → laukiama: klausia, kada galėsit → namų darbas → perskambinimas;
- „Perkroviau“, bet 🔄 nespaudus → laukiama: linija perkrovimo nematė, prašo dar kartą;
- „Dar ne“ po perkrovimo prašymo → laukiama: palaukti. **Žinoma spraga:** dabar laikoma, kad
  perkrauta;
- padėti ragelį po perkrovimo prašymo → laukiama: įrašas „unfinished“ + `call_unfinished`
  tiketas.

## 7. Žinomos spragos pagal scenarijų (ištirta 2026-10-23, netaisyta)

| Scenarijus | Spraga | Priežastis | Siūlomas taisymas (aptarti) |
|---|---|---|---|
| visi | Testas: „atsakymą į pirmą klausimą po radinio skaito tik modelis“ | ne klaida: radinio ėjimas sąmoningai nieko neklausia (2026-09-23) | pataisyti testą; arba radinys + kortelės žingsnis kartu |
| 1 | „Dar ne“ po perkrovimo prašymo laikomas atliktu | instrukcijos žingsnis juda nuo bet kokio atsakymo | žodyno sąrašas „dar ne / nespėjau“ — tik instrukcijos žingsniui → laukti |
| 1, 2 | „Galiu, tuoj nueisiu“ | ne klaida: agentas laukia (sprendimas 2026-10-12), testas laukė kito | pataisyti testą |
| 2 | „Įjungtas“ neperskaitomas | žodyne yra tik „įjungtas į“ | žodynas `power_cable_in` |
| 2 | „Įkišau dabar“ grąžina prie klausimo | „įkišau“ nėra `power_cable_out` sąraše | žodynas: „įkišau / prijungiau“ = buvo ištrauktas |
| 1 | „Nežinau kada“ laikomas klausimu | žodis „kada“ klausimų sąraše | žodynas: netiesioginiai „nežinau kada / kiek / kur“ — ne klausimas |
| 2 | Lemputės dega, bet kortelė „miręs routeris“ lieka | kortelės `needs` reikšmė `rules_out` aprašyta, bet variklis jos neskaito | sprendimas tavo: A — įjungti (kortelė krenta → neaiškus gedimas); B — su degančiomis lemputėmis praleisti maitinimo žingsnius; C — nauja kortelė „routeris maitinamas, bet nematomas“ |

Kitos spragos (identifikacija, problema, tiketas, pabaiga): [../testing/TESTAI_PAGAL_FUNKCIJAS.md](../testing/TESTAI_PAGAL_FUNKCIJAS.md).

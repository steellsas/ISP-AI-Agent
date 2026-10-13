# Promptų ir LLM parametrų žurnalas (v3 6 etapas)

Kiekvienas prompto ar LLM parametro pakeitimas užrašomas čia: **ką** keičiame, **kodėl**, **kaip
matuojame** ir **koks rezultatas**. Andrius (2026-10-12): *„kiekvienam prompto koregavimui
pasirašysime, ką keičiame ir kodėl"*; kiekvieną žingsnį prieš keičiant aptariame.

## Kaip matuojama

```
uv run python src/agent/eval/run_eval.py --runs 3 --json ../logs/eval_<žingsnis>.json
uv run python src/agent/eval/metrics.py ../logs/eval_base.json --compare ../logs/eval_<žingsnis>.json
```

`metrics.py` iš eval ataskaitos ir trace'ų suskaičiuoja:

- LLM vaidmenims (suvokimas, kalbėjimas, analitikas): kvietimai, įeinantys / išeinantys tokenai,
  vėlavimo mediana ir p90;
- atsakymai: kiek parašė variklis, kiek LLM, ilgis (vidurkis / max);
- scenarijai: praėję visus paleidimus, **nestabilūs** (kartą praeina, kartą ne), krentantys visada;
- suvokimo stabilumas: tas pats kliento sakinys skirtinguose paleidimuose — kiek kartų perskaitytas
  skirtingai.

Terminai (Andrius, 2026-10-12): „maršrutizatorius" yra taisyklingas lietuviškas žodis, ne klaida.

## Žingsniai

| Žingsnis | Kas | Būsena |
|---|---|---|
| 6.0 | Matavimo pagrindas (`metrics.py`, eval ×3 dabartiniu kodu) | ✅ |
| 6c | Parametrai pagal vaidmenį | ✅ paliekama; stabilumo pagerėjimas nepasitvirtino |
| 6a | Kalbėjimo promptas pagal fazę | ✅ −22 % tokenų; 39/40, 0 nestabilių |
| 6b | Suvokimo LLM nekviesti, kai atsakymą perskaitė skaitytuvas | bus aptarta |
| 6d | Lietuvių kalbos taisyklės ir terminai | ✅ nežinomi žodžiai −31 %; `kalba.yaml` |

---

### 6.0 Pagrindas (2026-10-12)

Kodas: develop po `fix/live-calls-1012`. Eval ×3 (`logs/eval_base.json`).

| Vaidmuo | Kvietimai | Įeina tok. | Išeina tok. | ms mediana | ms p90 |
|---|---|---|---|---|---|
| Suvokimas | 547 | 1 890 | 66 | 626 | 949 |
| Kalbėjimas | 541 | 2 508 | 49 | 465 | 670 |
| Analitikas | 207 | 827 | 14 | 312 | 606 |

- Atsakymai: 1 026 (variklis 485 / LLM 541), ilgis vidutiniškai 108 simb., max 271.
- Scenarijai: 39/40 praeina visus 3 paleidimus; nestabilių 0; visada krenta **I2** — Gemma rašo
  „nerodu" vietoj „nerandu" (kalbos klaida, 6d kandidatas), todėl patikra žodžio neranda.
- Suvokimas: **8 iš 182** sakinių skirtinguose paleidimuose perskaityti skirtingai.

---

### 6c Parametrai pagal vaidmenį (2026-10-12, Andrius pritarė)

| Vaidmuo | Buvo | Dabar | Kodėl |
|---|---|---|---|
| Suvokimas ir tiketo skaitytuvas (JSON: ką klientas pasakė, telefonas / laikas) | temperature 0.3 (numatyta), max_tokens 500 (numatyta) | **0**, **200** | Tai skaitymas, ne kūryba: su 0.3 tas pats sakinys kartais perskaitomas kitaip (eval S4: „Vis tiek nedega" kartą „laidas ištrauktas", kitą „neaišku"). Didžiausias matytas atsakymas 131 tok. — 200 palieka atsargą, bet nebeleidžia išsiplėsti |
| Kalbėjimas (ką girdi klientas) | 0.3, 150 | **0.2**, 150 | Mažiau atsitiktinių žodžių ir kalbos klaidų („lemputžių"), tonas lieka gyvas. Riba 150 jau tinkama |
| Analitikas (fone) | 0.2, 700 | nekeista | atsakymo laikui įtakos neturi |
| Klasifikatorius | 0, 150 | nekeista | jau tinkama |

Reikšmės — `knowledge/limits.yaml` (`perception_temperature`, `perception_max_tokens`,
`speak_temperature`), kad jas būtų galima keisti be kodo.

Laukiama: stabilesni eval rezultatai (mažiau nestabilių scenarijų ir skirtingai perskaitytų
sakinių), šiek tiek trumpesnis suvokimas. Rizika maža; blogiau — grąžinam.

**Rezultatas (eval ×3, `logs/eval_6c.json`, palyginta su pagrindu):**

| | Pagrindas | 6c |
|---|---|---|
| Suvokimas: tas pats sakinys perskaitytas skirtingai | **8 / 182** | **3 / 182** |
| Scenarijai, praėję visus 3 kartus | 39 / 40 | 38 / 40 |
| Nestabilūs | 0 | 2 — I2 (Gemma „nerodu", 6d) ir K1 (ilgis 1 iš 3) |
| Visada krentantys | 1 (I2) | 0 |
| Atsakymo ilgis vid. / max | 108 / 271 | 109 / 259 |
| Suvokimo vėlavimas med. / p90 | 626 / 949 ms | 691 / 1 002 ms |

- ~~Pagrindinis tikslas pasiektas: suvokimo skaitymai beveik trigubai stabilesni (8 → 3).~~
  **Pataisyta po pakartotinių matavimų:** tolesniuose eval ×3 (su tuo pačiu suvokimo promptu ir
  temperatūra 0) skirtingai perskaitytų sakinių buvo 7, 5 ir 8 — tiek pat, kiek pagrinde. „3"
  buvo vieno paleidimo sėkmė: Scaleway atsakymai nėra deterministiniai net su temperatūra 0.
  6c paliekamas (skaitymui temperatūra 0 vis tiek teisinga, riba 200 saugi), bet stabilumo
  pagerėjimo **nepatvirtina**; stabilumą mažins 6b (mažiau sakinių per modelį).
- Vėlavimas +60 ms — ne dėl parametrų (temperatūra skaičiavimo nekeičia, tokenų tiek pat), o
  tiekėjo (Scaleway) svyravimas tarp paleidimų skirtingu paros metu.
- I2 iš „visada krenta" tapo „kartais praeina"; K1 — žinomas ilgio svyravimas (6a/6d).

Sprendimas: **paliekama** (laukia Andriaus patvirtinimo).

---

### 6a Kalbėjimo promptas pagal fazę (2026-10-12, Andrius pritarė)

**Kodėl.** Kalbėjimo kvietimo prefiksas buvo ~6 700 simbolių (79 % viso kvietimo), iš jų ~4 700
bendros dalies kiekviename ėjime. Joje taisyklės kartojosi (vienas klausimas ×3, „nieko, ko nėra
kortelėje" ×3, „ne užregistravau" ×2), keliavo kitų fazių taisyklės (identifikacija ir tiketas
tikrinant lemputes) ir pasenusios („kviesk įrankius tik su tikrais duomenimis" — kalbėtojas
įrankių neturi nuo M5).

**Kaip dabar sudedama.** `branduolys` + `fazės blokas` + `įgūdis`:

```
speak/system.md (+ partials/identity.md)    visada
phases/identify.md                           pasisveikinimas, kreipimosi priežastis, identifikacija
phases/investigate.md                        tyrimas
phases/ticket.md                             registracija (tik čia — kliento telefono numeris)
skills/<įgūdis>.md                           kaip iki šiol
```

**Kiekviena taisyklė — kur buvo, kur dabar:**

| Taisyklė | Buvo | Dabar | Kodėl |
|---|---|---|---|
| Kas tu esi (technikas, šiltas) | identity | branduolys | visada reikia |
| Interneto ir TV gedimai — tavo sritis | identity | branduolys (1 eil.) | visada reikia |
| Sąskaitos, sutartys ne tavo — atsakingas žmogus paskambins | identity | **išmesta iš branduolio** | jau yra `inform_news` įgūdyje; šalutinei temai atsakymą duoda kortelės SIDE TOPIC eilutė |
| Trumpi sakiniai, 5–10 žodžių, be markdown | identity + system | branduolys, **1 kartą** | dublikatas |
| Vienas klausimas atsakyme | identity + system + kortelės skyrius (×3) | branduolys, **1 kartą** | dublikatas |
| Reakcija tik į tai, ką pasakė; nesakyti „gerai, kad perkrovėte"; kaitalioti pradžią | identity + kortelės skyrius | branduolys, sujungta | dublikatas |
| Pirma KODĖL, pasitikėjimas su pagrindu; nekaltinti | identity | branduolys | visada reikia |
| Vardas — kada | identity | branduolys | visada reikia |
| Vardas šauksmininku (Andriau) | identity + kalbos instrukcija | **tik kalbos instrukcijoje** | dublikatas (ten išsamiau) |
| Ne aklavietė | identity | branduolys | visada reikia |
| Tyla — neatsiprašinėti | system | branduolys | visada reikia |
| Neturi įrankių, variklis sprendžia | system | branduolys | visada reikia |
| Kortelė yra tiesa; nieko, ko nėra kortelėje | system + identity + facts_integrity (×3) | branduolys, **1 kartą** | dublikatas |
| Nesakyti to, kas neįvyko | identity | branduolys | visada reikia |
| PLAN GOAL eilės tvarka; WORD FOR WORD; Backup | system | branduolys | identifikacija ir tiketas jas naudoja |
| CHECK BACK baigiasi „ar taip?" | system | **išmesta** | jau parašyta pačioje CHECK BACK eilutėje |
| FINDINGS MOMENT 2–3 sakiniai, be sąrašų | system | **išmesta** | jau parašyta pačioje FINDINGS MOMENT eilutėje |
| TICKET STEP: „užregistruosiu", ne „užregistravau"; REGISTERED | system + identity | **išmesta** | jau parašyta TICKET STEP eilutėje ir `inform_news` / `ticket_offscript` įgūdžiuose |
| SYMPTOMS — klausti tik to, ko trūksta | system | **kortelės SYMPTOMS eilutėje** | taisyklė keliauja tik kartu su eilute |
| Skaičiai skaitmenimis („dvylika" → 12) | facts_integrity | `phases/identify` | adresai ir butai — identifikacija |
| Neaiškus STT — pakartoti, ką išgirdai; adresas, kurį klientas PATVIRTINA | facts_integrity | `phases/identify` | identifikacija |
| Sutarties savininko vardo nesakyti | system | `phases/identify` | identifikacija |
| Sakyk, ką MATAI linijoje, abi puses | identity | `phases/investigate` | tyrimas |
| Kviesk įrankius tik su tikrais duomenimis | facts_integrity | **išmesta** | kalbėtojas įrankių neturi (M5) |
| Kliento telefono numeris | system | `phases/ticket` | reikia tik registruojant |

Kalbos instrukcija (Jūs forma, šauksmininkas, gramatika) — nekeista, tai 6d.

**Dydis:** prefiksas ~6 700 → **3 500–5 000** simbolių (pagal įgūdį ir fazę; ~−35 %). Testas
`test_skills` riba 7 300 → 5 300, kad nebeaugtų nepastebimai.

**Rezultatas (eval ×3, `logs/eval_6a2.json`, palyginta su 6c):**

| | 6c | 6a |
|---|---|---|
| Kalbėjimo įeinantys tokenai | 2 507 | **1 946 (−22 %)** |
| Kalbėjimo vėlavimas med. / p90 | 490 / 714 ms | **435 / 648 ms** |
| Atsakymo ilgis vid. / max | 109 / 259 | 106 / 259 |
| Praėję visus 3 kartus | 38 / 40 | 37 / 40 |
| Nestabilūs | I2, K1 | X_dhcp (1/3, žinomas žargonas) |
| Visada krenta | — | I2 (Gemma „nerodu"), S4b |
| Suvokimas: skirtingai perskaityta | 3 / 182 | 7 / 181 (suvokimo promptas nekeistas; pagrinde buvo 8) |

- **S4b praeidavo atsitiktinai**: Gemma pasakydavo pavyzdinį sakinį iš senos bendros dalies
  („…užregistruosiu jūsų klausimą"), ir pažado sargas jį paversdavo registracija. Tikroji klaida
  buvo ir anksčiau: šalutinis klausimas vidury sprendimo („Gerai, ačiū, veikia. Alio, kada dėl
  routerio paskambinsit?") užšaldo Case, „veikia" neįskaitomas, Gemma išsigalvoja žingsnį.
  Siūlytas variklio pataisymas — laukia Andriaus sprendimo.
- **Patikslinimo pataisymas pakeliui** (S9 krito dėl jo, ne dėl 6a): kliento būtojo laiko
  žodžiai („patikrinau", „pažiūrėjau") yra „padaryta"; nuogas „Gerai" ir „turiu rankoje" po
  nurodymo — „darau", agentas laukia, neklausia; konkretesni klausimai („Ar jau įkišote tą
  laidą į kompiuterį?"). S9 — 3/3.

Sprendimas: **paliekama** (kalbėjimas −22 % tokenų, −55 ms), S4b — atskiras variklio taisymas.

**Variklio taisymai, kuriuos atidengė 6a** (Andrius pritarė 2026-10-12):

1. *Rezultatas ir klausimas viename sakinyje* („Gerai, ačiū, veikia. Alio, kada dėl routerio
   paskambinsit?"): šalutinė tema nebeužšaldo Case, kai teiginyje yra sprendimo rezultatas
   („veikia" / „neveikia") ar „padariau"; Case pasiima rezultatą, į klausimą atsakoma tame
   pačiame atsakyme. Rezultatas skaitomas tik iš teiginių, ne iš klausimų.
2. *Patikra nebeklausia to, ką klientas jau pasakė*: linija rodo, kad veikia, ir klientas jau
   pasakė „veikia" — „ar jums jau veikia?" nebeklausiama.
3. *Atsisveikinimas be diakritikų*: „Ne, ačiu, viskas" (ASR be nosinės) buvo palaikytas
   „vis dar neveikia" ir atidarė išspręstą skambutį (S1, S1v). Dabar lyginama sulyginus
   diakritikus.

Abu S4b ir S1 anksčiau praeidavo **atsitiktinai** — perteklinis klausimas ar prompto pavyzdys
paslėpdavo klaidą.

**Galutinis rezultatas (eval ×3, `logs/eval_6a4.json`, palyginta su 6c):**

| | 6c | 6a + taisymai |
|---|---|---|
| Kalbėjimo įeinantys tokenai | 2 507 | **1 949 (−22 %)** |
| Kalbėjimo vėlavimas med. / p90 | 490 / 714 ms | **457 / 668 ms** |
| Atsakymo ilgis vid. / max | 109 / 259 | 105 / 259 |
| Praėję visus 3 kartus | 38 / 40 | **39 / 40** |
| Nestabilūs | 2 | **0** |
| Visada krenta | — | I2 (Gemma „nerodu" — 6d) |

---

### Išspręsto gedimo išvada ir sargas (2026-10-13, Andrius)

Ne prompto, o variklio pakeitimas, bet keičia tai, ką modelis gauna kaip PLAN GOAL:

- **Išvada** visada: koks buvo gedimas (`summary.resolved.<gedimas>` arba `fixes:` priežastis),
  ką padarėme (`summary.did`), kad veikia — ir tik tada „ar dar turite klausimų?". Atsisveikinus
  tame pačiame sakinyje — išvada ir atsisveikinimas, be klausimo.
- **Sargas**: patikra su klausimu („ar veikia?") užbaigiama tik kai linija IR klientas sutinka;
  „vis tiek neveikia" / „vėl nebeveikia" — neištaisyta; kita — perklausiama.
- Eval ×3: 41/42, 0 nestabilių (`logs/eval_concl.json`).

---

### 6d Lietuvių kalba (2026-10-13, Andrius pritarė)

**Kodėl.** ~9 400 agento atsakymų (eval + gyvi skambučiai): ~5 % LLM atsakymų turėjo aiškią
kalbos klaidą — dažniausios „sutvarkėsi" (55), „lemputžių" (42), „nerodu" (25), sugadintas
„Telefonu šio … neišspręsim" (29), išgalvoti žodžiai („pusmogaudis", „sušlykštėjo").

**Kur gyvena kalbos taisymai** — `locales/lt/kalba.yaml` (Andriaus sprendimas: ne į promptus):

| Sąrašas | Kam |
|---|---|
| `taisymai` | klaida → teisinga forma; taisytuvas keičia prieš balsą (pilni žodžiai, didžioji raidė išlaikoma), kiekvienas pakeitimas — trace `language_fix` |
| `i_prompta` | kurios iš jų keliauja į promptą kaip „nesakyk → sakyk" (tik dažniausios) |
| `teisingi` | teisingi žodžiai, kurių nėra kirčiavimo žodyne — kad matavimas jų nelaikytų klaida |

Naujas žodis — viena eilutė šiame faile; kodo ir prompto keisti nereikia.

**Pakeitimai:**

| Žingsnis | Kas | Kodėl |
|---|---|---|
| 6d.1 | `metrics.py`: atsakymai su žodžiu, kurio nėra žodyne (balso kirčiavimo žodynas + mūsų frazės + `teisingi`), taisytuvo pataisymai, 15 įtartiniausių žodžių | be skaičiaus nežinotume, ar padėjo; įtartini žodžiai — kandidatai į `taisymai` / `teisingi` |
| 6d.2 | `summary.did` frazės bendrine forma („pažiūrėjome", ne „pasižiūrėjom"); „Telefonu neišspręsim" → „Telefonu šio gedimo neišspręsime" | modelis perrašydavo šnekamąsias formas ir nepilną sakinį — ir sugadindavo |
| 6d.3 | Kalbos instrukcijoje: „tik žodžiai, kuriais tikras; jei ne — paprastas kasdienis; neišgalvok"; „kortelės cituojamų žodžių nelinksniuok"; „nesakyk → sakyk" eilutė iš `i_prompta` | konkretūs pavyzdžiai veikia geriau nei bendras „rašyk taisyklingai" |
| 6d.4 | Taisytuvas sakinių sarge (kartu su kirilicos keitimu) | kas praslysta pro promptą — klientas vis tiek išgirsta teisingai |

Prompto dydis +~450 simbolių; testo riba 5 300 → 5 600.

**Pagrindas (prieš 6d, `logs/eval_concl.json`):** 36 / 1 077 atsakymų su žodžiu, kurio nėra
žodyne (3,3 %); visada krenta I2 („nerodu").

**Rezultatas (eval ×3, `logs/eval_6d.json`, palyginta su pagrindu):**

| | Prieš 6d | 6d |
|---|---|---|
| Atsakymai su žodžiu, kurio nėra žodyne | 29 / 1 077 | **20 / 1 077 (−31 %)** |
| Taisytuvo pataisytos klaidos | — | 9 (pajungti ×6, nesusprendau, dalykštį, išgirta) |
| I2 („nerodu") | krenta 3/3 | praeina 2/3 |
| Kalbėjimo įeinantys tokenai | 1 947 | 2 114 (+167 — kalbos taisyklės) |
| Praėję visus 3 kartus | 41 / 42 | 39 / 42 |

- Nauji įtartini žodžiai (kandidatai į `taisymai`): nedėgamės, skoningos, perkišėme,
  išsaugtumėte, užtrūkimus, nenuradinau, nesužinau, prispaudžtas.
- S1 ir S4b nestabilumas — ne dėl 6d: abiem atvejais modelis pats pasako „užregistruosiu",
  ir pažado sargas paleidžia registraciją (S1 — identifikacijos metu, netikra; S4b — prie
  išvados prideda telefono klausimą, atsakymas 305 simb.). Tas pats S1 atvejis buvo ir prieš
  6d (1/3). Atskiras klausimas — kada modelio žodis gali paleisti veiksmą (aptarti).

Sprendimas: **paliekama**.

---

### Registracija tik variklio sprendimu (2026-10-13, Andrius pritarė)

Kortelės ir pavyzdžių pakeitimai (prompto dalis; visa — `STRUKTURA_V3.md` §6.1):

| Kur | Buvo | Dabar | Kodėl |
|---|---|---|---|
| STUCK (neidentifikuotas) | „…or register the problem for a call-back" | „Promise no registration — the engine decides that." | registraciją siūlė modelis, ne variklis |
| STUCK (identifikuotas) | „…or offer to register the fault (a technician will get in touch)" | „a smaller, simpler question. Promise no registration or technician" | — „ — |
| ONE MORE CHANCE | „…say that if it does not work you will register a technician" | „Promise nothing about a technician or a registration — the engine decides" | — „ — |
| LONG WAIT | „…or offer to register the fault" | „Promise no registration — the engine decides that." | — „ — |
| `skill_answer_side` pavyzdys | „…atsakingas žmogus, užregistruosiu klausimą" | „Tai ne mano sritis — šiuo klausimu geriausiai atsakys atsakingas žmogus" | pavyzdį modelis kartodavo ne vietoje |

**Rezultatas (eval ×3, `logs/eval_reg.json`, palyginta su 6d):**

| | 6d | Registracija tik variklio |
|---|---|---|
| Praėję visus 3 kartus | 39 / 42 | **40 / 42** |
| S1 (netikra registracija identifikacijos metu) | nestabilus | **3/3** |
| I2 („nerodu") | 2/3 | **3/3** |
| Nestabilūs | 3 | 2 — S4b (ėjimo ilgis 298 > 280, 1/3; buvo ir prieš), X_dhcp (žargonas, 1/3) |
| Ilgiausias atsakymas | 305 | 259 |

Sprendimas: **paliekama**.

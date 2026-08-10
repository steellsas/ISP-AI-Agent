# BALSO TESTŲ RAUNDAS — pertraukimai, nukrypimai, tiketo dialogas

*2026-08-08. Tikrina viską, kas pridėta po paskutinių tavo skambučių:
streaming + cancel, side_topic (FAQ + inkaras), politikos guard'ai drive
kelyje, reopen valymas, istorijos pilnumas.*

## Pasiruošimas (prieš PIRMĄ skambutį)

```bash
git checkout develop && git pull
uv run python -m uvicorn --app-dir chatbot_core src.app.main:app --port 8080
```

Naršyklėje `http://localhost:8080` → ⚙️ patikrink: **Barge-in ĮJUNGTAS**,
pertraukimo slenkstis 700 ms, „Srautinis kalbėjimas" ON. Tarp skambučių:
**Baigti → ♻️ DB → Skambinti**. Po kiekvieno skambučio mesk man trace failą
(`logs/sessions/...jsonl`) — analizuosiu.

Panelėje stebėk: `⚡ TTFA`, `⏹ BARGE-IN`, `turn_cancelled`, `◇ EVIDENCE`,
`DETERMINISTINIS VARIKLIS/LLM` chip'ą.

---

## T1 — Pertraukimas su ANKSTYVU ATSAKYMU (svarbiausias)

**Numeris:** `+37060012353` (CUST009, miręs routeris)

| Eiga | Tu sakai |
|---|---|
| 1 | „Neveikia internetas" |
| 2 | (anamnezė) „Vakar, po audros" |
| 3 | Agentas pradeda: „Ar skambinate dėl Vilniaus g…" — **PERTRAUK vidury** garsiai: **„Taip taip, Vilniaus dvidešimt devyni!"** |
| 4 | Toliau normaliai iki lempučių klausimo: agentas klausia „ar dega bent viena lemputė…" — **PERTRAUK**: **„Nedega nė viena!"** |

**Turi įvykti:** garsas nutyla < 0.5 s; adresas užsiskaito BE pakartotinio
klausimo; lempučių atsakymas užsiskaito (◇ EVIDENCE `lights=nedega`), kitas
klausimas — apie maitinimą, NE „ar dega lemputės?" dar kartą.
**FAIL, jei:** agentas perklausia tą patį, ką pasakei pertraukdamas.

## T2 — Pertraukimas su KLAUSIMU + grįžimas prie inkaro

**Numeris:** tas pats `+37060012353`, naujas skambutis (♻️ DB!)

| Eiga | Tu sakai |
|---|---|
| 1–2 | kaip T1 iki diagnozės paskelbimo |
| 3 | Agentas skelbia „Patikrinau: internetas ateina, bet…" — **PERTRAUK**: **„Palaukit, o kiek man tai kainuos?"** |
| 4 | Po atsakymo — „Gerai, tęskim" |
| 5 | Prie lempučių klausimo — atsakyk normaliai ir tęsk iki tiketo ar bridge |

**Turi įvykti:** `⏹ BARGE-IN` + `turn_cancelled` feed'e; atsakymas apie kainą
(„telefonu nieko nekainuoja…" iš faq.yaml) + **tas pats nutrauktas klausimas
pakartotas** (inkaras); jokio šuolio į kitą temą.
**FAIL, jei:** kainos klausimas ignoruotas ARBA grįžta ne prie tos vietos.

## T3 — Backchannel („aha") NEnutildo

Bet kuriame skambutyje, kai agentas sako ilgesnį sakinį — pasakyk trumpai
tyliai **„aha"** arba **„gerai"** (iki pusės sekundės).

**Turi įvykti:** agentas kalba toliau, jokio ⏹.
**FAIL, jei:** trumpas „aha" nutraukia kalbą. (Jei nutraukia — ⚙️ pakelk
pertraukimo slenkstį iki 900–1000 ms ir pakartok.)

## T4 — Trys nukrypimai iš eilės → tvirtas grįžimas

**Numeris:** `+37060012353`, iki diagnozės paskelbimo, tada iš eilės:

1. **„O kiek kainuos?"** → laukiam atsakymo + inkaro
2. **„O koks rytoj oras?"** → „ne mano sritis" + inkaras
3. **„O kur jūsų biuras yra?"** → **scripted rėmas**: „Grįžkime prie jūsų
   gedimo…" (be jokio atsakymo apie biurą)

Tada atsakyk į inkaro klausimą ir patikrink, kad seka tęsiasi iš TOS vietos.

## T5 — Skola: sąžiningumas + follow-up'ai

**Numeris:** `+37060020101` (CUST101, sustabdyta dėl skolos). Adresas — Tilžės g. 60, butas 7.

| Eiga | Tu sakai |
|---|---|
| 1 | „Neveikia internetas" → anamnezė → adresas → vardas |
| 2 | Po žinios apie skolą: **„O kokia suma? Kokia skola?"** |
| 3 | **„O kodėl tiek daug?"** (follow-up) |
| 4 | „Gerai, ačiū, viso gero" |

**Turi įvykti:** SĄŽININGAS atsakymas — „sumos nematau, rasite savitarnoje /
pasakys buhalterija" (NE žinios pakartojimas, NE atsisveikinimas!); follow-up
gauna rišlų atsakymą; pabaiga švari, be tiketo.
**FAIL, jei:** kartoja „paslauga sustabdyta…" arba uždaro pokalbį ant klausimo.

## T6 — „Neturiu laiko" → registracijos pasiūlymas

**Numeris:** `+37060012353`, iki pirmo evidence klausimo, tada:
**„Pala, aš nieko nedarysiu dabar, neturiu laiko."**

**Turi įvykti:** registracijos pasiūlymas / tiketo dialogas („užregistruosiu —
ar tinka?" kelias), NE „paskambinkite vėliau" ir padėtas ragelis be nieko.
Užbaik dialogą („tiks šis", „bet kada") — tiketas su kontaktais.

## T7 — Ragelio saugiklis + sveika linija

**Numeris:** `+37060020105` (foreign_mac kelias). Pereik iki bind („pakeičiau
routerį" scenarijus — sakyk, kad neseniai keitei routerį, sutik pririšti),
kai pasakys „internetas atsirado" — patvirtink **„Veikia!"** ir IŠKART spausk
**Baigti** (nelauk atsisveikinimo).

**Turi įvykti:** archyve `hangup_net/skip_solved` — **JOKIO tiketo** sveikai
linijai.

## T8 — Adreso pataisymas vidury (reopen + švarus žurnalas)

**Numeris:** `+37060012353`. Praeik iki lempučių klausimo (žurnale jau bus
faktų), tada: **„Palaukit, aš ne dėl šito — skambinu dėl Dainų gatvės 5."**

**Turi įvykti:** agentas atsiprašo, klausia/tvirtina NAUJĄ adresą, ir toliau
kalba TIK apie naują liniją (Dainų 5 — masinės avarijos zona, tad turėtų
pranešti apie avariją). Jokių „lemputės nedega" liekanų iš seno konteksto.

---

## Po raundo

Mesk man visų skambučių trace'us (užtenka pasakyti „padariau T1–T8") —
peržiūrėsiu kiekvieną, sužymėsiu PASS/FAIL su priežastimis ir sudarysiu
taisymų sąrašą aptarimui. Latency: stebėk TTFA skaičius — scripted turn'ai
turi būti < 1.5 s, LLM turn'ai < 5 s (jei blogiau — fiksuok, kuriuose).

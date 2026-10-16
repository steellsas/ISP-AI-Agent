# BALSO TESTŲ RAUNDAS — pertraukimai, nukrypimai, tiketo dialogas

*2026-08-08. Tikrina viską, kas pridėta po paskutinių tavo skambučių:
streaming + cancel, side_topic (FAQ + inkaras), politikos guard'ai drive
kelyje, reopen valymas, istorijos pilnumas.*
*Atnaujinta 2026-09-17 pagal vieno variklio kodą (refaktoringas M0–M6):
skydelio pavadinimai, anamnezės klausimo nebėra, skolos suma, archyvas.*

## Pasiruošimas (prieš PIRMĄ skambutį)

```bash
git checkout refactor/single-engine   # vieno variklio šaka; develop dar su senu varikliu
uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080
```

Naršyklėje `http://localhost:8080` → ⚙ patikrink: serverio
**„Pertraukimai (barge-in / duck)" = on**, **„Srautinis kalbėjimas (sakinys po
sakinio)" = on**; skyriuje „Mikrofonas (šios naršyklės)" — **„Barge-in (galima
pertraukti agentą)" pažymėta**, „Pertraukimo slenkstis (ms kalbos)" 700.
Tarp skambučių: **Baigti → ♻ DB → Skambinti**. Po kiekvieno skambučio mesk
man trace failą (`logs/sessions/<session_id>.jsonl`; arba skirtukas
**Archyvas** → skambutis → **⬇ JSON**) — analizuosiu.

Skirtuke **Testavimas** (dešinė kolona) stebėk:
- **Pokalbio linija** — kliento/agento garso juosta ir būsena („kalba
  agentas", „kalba klientas", „agentas galvoja…"): matosi, ar agento garsas
  nutilo, kai pertraukei.
- **Agento vidus — ėjimo kelias** (ASR → perceive → decide → execute →
  narrate → TTS): TTS mazge — `TTFA … ms`.
- **Ėjimo planas** — `Kalba:` ženkliukas **`variklis`** (frazė iš failų)
  arba **`LLM`** (kalba modelis); taip pat taisyklė, hipotezė, `laukia:`.
- **Įvykiai** — eilutės **`pertrauka`** (barge-in, filtras „ASR/TTS"),
  **`turn_cancelled`** (nutrauktas ėjimas, `spoken=` — kas spėta pasakyti),
  **`faktas`** (evidence, pvz. `fact lights=off`), **`sprendimas`**,
  **`planas`**.

---

## T1 — Pertraukimas su ANKSTYVU ATSAKYMU (svarbiausias)

**Numeris:** `+37060012353` (CUST009, miręs routeris)

| Eiga | Tu sakai |
|---|---|
| 1 | „Neveikia internetas, vakar dingo, po audros" (atskiro anamnezės klausimo nebėra — pasakyta pirmame sakinyje užsifiksuoja, capture-first) |
| 2 | Agentas pradeda adreso pasiūlymą: „…Ar skambinate dėl Vilniaus g…" — **PERTRAUK vidury** garsiai: **„Taip taip, Vilniaus dvidešimt devyni!"** |
| 3 | Vardo klausimui: „Giedrius, mano sutartis" |
| 4 | Toliau normaliai iki lempučių klausimo: agentas prašo pažiūrėti, „ar ant routerio dega bent viena lemputė" — **PERTRAUK**: **„Nedega nė viena!"** |

**Turi įvykti:** garsas nutyla < 0.5 s (`pertrauka` + `turn_cancelled`
Įvykiuose); adresas užsiskaito BE pakartotinio klausimo; lempučių atsakymas
užsiskaito (`faktas` … `lights=off`), kitas klausimas — apie maitinimą, NE
„ar dega lemputės?" dar kartą.
**FAIL, jei:** agentas perklausia tą patį, ką pasakei pertraukdamas.

## T2 — Pertraukimas su KLAUSIMU + grįžimas prie inkaro

**Numeris:** tas pats `+37060012353`, naujas skambutis (♻ DB!)

| Eiga | Tu sakai |
|---|---|
| 1–2 | kaip T1 iki diagnozės paskelbimo |
| 3 | Agentas skelbia „Patikrinau: …" — **PERTRAUK**: **„Palaukit, o kiek man tai kainuos?"** |
| 4 | Po atsakymo — „Gerai, tęskim" |
| 5 | Prie lempučių klausimo — atsakyk normaliai ir tęsk iki tiketo ar bridge |

**Turi įvykti:** `pertrauka` + `turn_cancelled` Įvykiuose; atsakymas apie
kainą („…telefonu nieko nekainuoja…" — frazė `faq.price`,
`agent/locales/lt/phrases.yaml`; tema ir raktažodžiai
`agent/knowledge/faq.yaml`) + **tas pats nutrauktas klausimas pakartotas**
(inkaras); jokio šuolio į kitą temą.
**FAIL, jei:** kainos klausimas ignoruotas ARBA grįžta ne prie tos vietos.

## T3 — Backchannel („aha") NEnutildo

Bet kuriame skambutyje, kai agentas sako ilgesnį sakinį — pasakyk trumpai
tyliai **„aha"** arba **„gerai"** (iki pusės sekundės).

**Turi įvykti:** agentas kalba toliau, jokios `pertrauka` eilutės.
**FAIL, jei:** trumpas „aha" nutraukia kalbą. (Jei nutraukia — ⚙ pakelk
„Pertraukimo slenkstis (ms kalbos)" iki 900–1000 ms ir pakartok.)

## T4 — Trys nukrypimai iš eilės → tvirtas grįžimas

**Numeris:** `+37060012353`, iki diagnozės paskelbimo, tada iš eilės:

1. **„O kiek kainuos?"** → laukiam atsakymo + inkaro
2. **„O koks rytoj oras?"** → „ne mano sritis" + inkaras
3. **„O kur jūsų biuras yra?"** → **scripted rėmas**: „Grįžkime prie jūsų
   gedimo…" (be jokio atsakymo apie biurą; riba `side_topic_streak_max: 3`,
   `knowledge/limits.yaml`)

Tada atsakyk į inkaro klausimą ir patikrink, kad seka tęsiasi iš TOS vietos.

## T5 — Skola: sąžiningumas + follow-up'ai

**Numeris:** `+37060020101` (CUST101, sustabdyta dėl skolos). Adresas — Tilžės g. 60, butas 3.

| Eiga | Tu sakai |
|---|---|
| 1 | „Neveikia internetas" → adreso pasiūlymas → „Taip" → vardas |
| 2 | Po žinios apie skolą: **„O kokia suma? Kiek aš skolingas?"** |
| 3 | **„O kodėl tiek daug?"** (follow-up) |
| 4 | „Ne, nereikia. Ačiū, viso gero" |

**Turi įvykti:** pati žinia jau pasako skolos sumą, mėnesius ir paskutinį
mokėjimą (šablonas `inform.billing_suspended.template` per
`knowledge/inform.yaml`; demo DB: dvi neapmokėtos sąskaitos po 24.99 EUR —
liepa ir rugpjūtis, paskutinis mokėjimas birželio 5 d.). Į „kokia suma?" —
atsakymas, nesikertantis su ką tik pasakyta suma (NE atsisveikinimas!).
„Kodėl tiek daug?" = skolos ginčas → agentas skolos NEaiškina, siūlo
užregistruoti klausimą atsakingam žmogui („Sąskaitų detalių aš nematau, bet
galiu užregistruoti jūsų klausimą… Ar registruoti?"). Atsisakius — švari
pabaiga be tiketo; Archyve Baigtis `informed_debt`.
**Variantas:** 4 žingsnyje „Taip, registruokite" → kontaktų dialogas →
tiketas, Baigtis `ticket`.
**FAIL, jei:** kartoja visą „paslauga sustabdyta…" žinią, uždaro pokalbį ant
klausimo ARBA po pasakytos sumos sako, kad sumos nemato (FAQ frazė
`faq.debt_amount` vis dar tokia — jei nuskamba, tai prieštaravimas).

## T6 — „Neturiu laiko" → registracijos pasiūlymas

**Numeris:** `+37060012353`, iki pirmo evidence klausimo, tada:
**„Pala, aš nieko nedarysiu dabar, neturiu laiko."**

**Turi įvykti:** negalėjimo-dabar kopėčios: patikslinimas („O kas nepatogu —
ar tiesiog negalite dabar patikrinti?") ir/arba pasiūlymas („…galiu
užregistruoti gedimą meistrui, arba paskambinkite, kai būsite prie routerio…
Kaip patogiau?"), NE „paskambinkite vėliau" ir padėtas ragelis be nieko.
Pasirink „Registruokite meistrą" ir užbaik dialogą („tiks šis", „bet kada")
— tiketas su kontaktais.

## T7 — Ragelio saugiklis + sveika linija

**Numeris:** `+37060020105` (foreign_mac kelias). Pereik iki bind („pakeičiau
routerį" scenarijus — sakyk, kad neseniai keitei routerį, sutik pririšti),
kai pasakys „internetas atsirado" — patvirtink **„Veikia!"** ir IŠKART spausk
**Baigti** (nelauk atsisveikinimo).

**Turi įvykti:** **JOKIO tiketo** sveikai linijai. Skirtuke **Archyvas**:
Baigtis `resolved`, Tiketas `—`; atidarius skambutį, Įvykiuose — `sprendimas`
`hangup_net skip_solved` (ragelio saugiklis `call_record/finalizer.py`;
jo nebus, jei agentas spėjo uždaryti skambutį pats). Filtras „tik
peržiūrai" šio skambučio neturi rodyti.

## T8 — Adreso pataisymas vidury (reopen + švarus žurnalas)

**Numeris:** `+37060012353`. Praeik iki lempučių klausimo (žurnale jau bus
faktų), tada: **„Palaukit, aš ne dėl šito — skambinu dėl Dainų gatvės 5."**

**Turi įvykti:** agentas PASITIKSLINA („ar tikrai skambinate dėl KITO adreso,
ne dėl …?") → „Taip" → identifikacija iš naujo (buto klausimas — demo DB:
Dainų g. 5-7), toliau kalba TIK apie naują liniją. Dainų g. — masinės
avarijos zona: apie avariją pranešama tik patvirtinus naują adresą. Jokių
„lemputės nedega" liekanų iš seno konteksto.

---

## Po raundo

Mesk man visų skambučių trace'us (užtenka pasakyti „padariau T1–T8") —
peržiūrėsiu kiekvieną, sužymėsiu PASS/FAIL su priežastimis ir sudarysiu
taisymų sąrašą aptarimui. Latency: stebėk TTFA skaičius — `variklis`
ėjimai turi būti < 1.5 s, `LLM` ėjimai < 5 s (jei blogiau — fiksuok,
kuriuose).

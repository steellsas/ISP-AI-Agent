# Delsa — kur dingsta ėjimo laikas ir ką daryti (gyvas dokumentas)

**Būsena (2026-10-15):** matavimo įrankis paruoštas, pirmas vaizdas iš 2026-10-14 skambučių
(prieš 6b). Laukiam Andriaus 3–5 naujų skambučių; po jų aptariam niuansus ir renkamės svertus.
Tikslas: **≤ 1,5 s** iki pirmo garso demo, < 1 s produktui. Planas trumpai — [STATUS.md §10](../STATUS.md#10-latency-plan).

Kiekvienas delsos pakeitimas užrašomas čia: ką keičiam, kodėl, kaip matuojam, rezultatas
(kaip [PROMPTAI.md](PROMPTAI.md)).

---

## 1. Kaip matuojama

```
uv run python scripts/latency_report.py --days 1 --turns     # šiandienos skambučiai, kiekvienas ėjimas
uv run python scripts/latency_report.py --last 5             # paskutiniai 5 skambučiai, suvestinė
uv run python scripts/latency_report.py --session <id>       # vienas skambutis
```

Skriptas skaito `logs/sessions/*.jsonl` ir kiekvieną balso ėjimą išskaido:

```
klientas nutyla
  │ endpoint*   tylos langas prieš nukerpant                 ĮVERTIS (limits.yaml pagal paskutinį partial režimą)
  ▼ ── garsas nukerptas (t=0) ─────────────────────────────────────────────
  │ asr         ASR trukmė                                    turn_timing.asr_ms
  │ read        suvokimo LLM kvietimai šiame ėjime            llm (perception / ticket_reader / problem_classifier)
  │ engine      decide + execute (su įrankiais)               graph_node
  │ speak       kalbėjimo LLM iki pirmo tokeno                first_token − asr − read − engine
  │ sentence    nuo pirmo tokeno iki pilno pirmo sakinio      first_sentence − first_token
  │ tts         pirmo sakinio sintezė                         first_audio − first_sentence
  ▼ first       PIRMAS GARSAS nuo nukirpimo                   turn_timing.first_audio_ms
    first+ep*   ką jaučia klientas nuo savo tylos pradžios    first + endpoint*
```

Suvestinės: visi ėjimai · kalbėjo LLM / parašyta frazė · su suvokimo LLM / be jo.

**Spraga:** tikras endpoint laukimas (nuo kalbos pabaigos iki nukirpimo) trace'e **neįrašomas** —
skriptas rodo tik sukonfigūruotą langą. Kad būtų tikslu, `app/audio_front.py` turėtų įrašyti
`endpoint` įvykį (kalbos pabaiga, nukirpimas, režimas). Tai kodo pakeitimas — aptarti.

---

## 2. Pirmas vaizdas — 2026-10-14, 3 skambučiai, 45 ėjimai (PRIEŠ 6b)

| Sluoksnis | Mediana | p90 | Pastaba |
|---|---|---|---|
| endpoint* | 900 | 900 | dauguma ėjimų be fast/slow užuominos → `server_silence_ms` 900 |
| asr (Groq) | 543 | 894 | |
| **read (suvokimo LLM)** | **673** | **997** | 36 iš 45 ėjimų — didžiausias valdomas sluoksnis |
| engine | 2 | 67 | su įrankiais iki ~350 ms |
| **speak (Gemma TTFT)** | **257** | **393** | ne 1,15 s, kaip rodė 10-05 matavimas |
| sentence | 80 | 200 | |
| tts (Piper) | 142 | 489 | ilgas pirmas sakinys (74–111 simb.) → 0,85–1,4 s |
| **first** | **1 730** | **2 469** | nuo nukirpimo |
| **first + endpoint*** | **2 702** | **3 395** | ką jaučia klientas |

Pagal ėjimo rūšį (first, mediana):

| | Ėjimai | first | first + ep* |
|---|---|---|---|
| su suvokimo LLM | 36 | 1 874 | 2 810 |
| be suvokimo LLM | 9 | 926 | 1 826 |
| parašyta frazė (be kalbėjimo LLM) | 6 | 738 | 1 638 |

**Ką tai sako:**

1. **Senas paveikslas pasikeitė.** 10-05 kalbėjimo LLM buvo ~1,15 s; dabar Gemma per Scaleway
   duoda pirmą tokeną per ~0,26 s. Kalbėjimas nebėra pagrindinė problema.
2. **Suvokimo LLM — didžiausias valdomas sluoksnis** (~0,7 s, kai kviečiamas). Ėjimas be jo yra
   ~1 s greitesnis. 6b (2026-10-15) jį praleidžia daugumoje trumpų atsakymų („Tiks", „Bet kada",
   „Taip") — **reikia išmatuoti po 6b**.
3. **Endpoint ~0,9 s** — fiksuotas laukimas prieš kiekvieną ėjimą, beveik vienodo dydžio kaip
   visas likęs vėlavimas po suvokimo praleidimo.
4. **Ilgas pirmas sakinys** išpučia TTS: 34 simb. ≈ 0,38 s, 67 simb. ≈ 0,86 s.
5. **ASR ~0,55 s** — stabilus, keisti tik su GPU.

---

## 3. Svertai — atnaujinta pagal pirmą vaizdą

| # | Svertas | Sluoksnis | Tikėtinas laimėjimas | Kaina | Prioritetas |
|---|---|---|---|---|---|
| L1 | Išmatuoti po 6b ir Piper (šis dokumentas) | visi | teisingas tikslas | maža | **dabar** |
| L1b | Įrašyti tikrą endpoint laukimą į trace | endpoint | tikslus matas | maža (kodas) | aptarti |
| **L5** | **Endpoint derinimas**: kodėl dauguma ėjimų be užuominos (900 ms); trumpesnis langas, kai atsakymas užbaigtas (fast 350) | endpoint | 0,3–0,5 s daugumoje ėjimų | maža–vid. | **aukštas** |
| **R1** | **Daugiau ėjimų be suvokimo LLM** (6b tęsinys: kur variklio skaitytuvai dar neperskaito) | read | ~0,7 s tuose ėjimuose | vidutinė | **aukštas** |
| R2 | **Mažesnis suvokimo promptas** (dabar ~2,3 tūkst. įvesties tokenų) | read | 0,1–0,3 s | vidutinė | vidutinis |
| L7 | Suvokimą pradėti nuo stabilaus dalinio ASR, kol klientas baigia | read | iki ~0,5 s | vidutinė | vidutinis |
| **L2** | **Trumpas pirmas sakinys** (≤ ~40 simb.) — reakcija pirma, paaiškinimas po jos | tts | 0,2–1 s ilgiems | maža | **aukštas** |
| L3 | Daugiau parašytų frazių vietoj direktyvų | speak | ~0,3 s + mažiau rizikos | mažai–vid. | vidutinis |
| L4 | Statuso frazė prieš žinomą laukimą (įrankis, ilgas suvokimas) — turininga, ne „mhm" | jaučiama | 1–2 s jaučiamo | maža | vidutinis |
| L6 | Mažesnis kalbėjimo promptas, prompt cache | speak | 0,1 s | vidutinė | žemas (TTFT jau ~0,26 s) |
| L8 | Srautinis ASR ant GPU | asr | 0,3–0,4 s | reikia GPU | vėliau |
| L9 | Lokalūs modeliai ant GPU (vLLM) | read + speak | read 0,7 → 0,2 s | didelė | vėliau (produkcija) |

Tikėtinas rezultatas be GPU (L5 + R1 + L2): **first ~1,0–1,3 s, first + endpoint ~1,5–2 s**.

---

## 3a. Sutarta (Andrius, 2026-10-16)

- **Matas, kuris svarbiausias:** tarpas tarp kliento tylos pradžios ir agento pirmo garso
  (`first+ep*`).
- **Demo tikslas: ~1,5 s.** Demo gali būti lėtesnis — prioritetas yra, kad variklis veiktų gerai.
- **Produkcijos tikslas: ~0,6 s** su lokaliais modeliais ant GPU.
- **Iki GPU daromi tik pigūs svertai, kurie liks naudingi ir produkcijoje:** L5 (endpoint), L2
  (trumpas pirmas sakinys), R1 (daugiau ėjimų be suvokimo LLM). L7, L8, L9 ir modelių derinimas
  atidedami, kol bus GPU.

**Ką duoda GPU + vLLM ir ko neduoda:**

| Sluoksnis | Demo (dabar) | Produkcija (GPU, vLLM) | Kas pagerina |
|---|---|---|---|
| endpoint | ~900 | 200–300 | turn detection modelis (Pipecat/LiveKit), **ne GPU** |
| ASR | ~550 | 100–200 | srautinis ASR ant GPU |
| suvokimo LLM | 0 / ~700 | 0 / 100–200 | vLLM: be tinklo, prefix cache, guided decoding |
| kalbėjimo LLM TTFT | ~260 | ~100 | vLLM, prefix cache |
| pirmas sakinys + TTS | ~250 | ~150 | trumpas pirmas sakinys; Piper jau lokalus |
| **iš viso** | **~2,7 s** | **~0,6–0,9 s** | 0,6 s — su persidengimu (žr. žemiau) |

**Persidengimas — kaip paslėpti delsą** (telefone dvi linijos — klientas ir agentas girdi vienas
kitą vienu metu):

1. **Išankstinis atsakymas į uždarą klausimą.** Kol agentas klausia „Ar dega lemputė?", variklis
   (~2 ms) jau suplanuoja ėjimą kiekvienam galimam atsakymui iš žingsnio uždaro sąrašo ir TTS
   paruošia parašytas frazes. Klientui pasakius „taip", atsakymas groja iškart. Tai jūsų variklio
   pranašumas — LLM agentai to padaryti negali.
2. **Preemptive generation** — pradėti skaityti ir generuoti nuo dalinio ASR, kol dar laukiama
   tylos; jei galutinis tekstas sutampa, atsakymas jau paruoštas (LiveKit Agents turi tai
   įmontuota; Pipecat — per savo procesorių, tikrinti).
3. **Turininga reakcija iškart** po kliento sakinio (iš anksto įrašyta, apie realų veiksmą —
   „Tikrinu jūsų liniją"), kol skaičiuojamas likęs atsakymas. Ne „mhm" (atmesta 2026-08-31).
4. **Trumpas pirmas sakinys** — groja, kol generuojama likusi mintis.

Pipecat / LiveKit agento „protingumo" nekeičia; jie duoda turn detection, pertraukimus,
telefoniją ir 2 punkto mechaniką. 1 punktą galima daryti ir dabar, be jų — tai variklio darbas.

## 3b. Turn detection — Smart Turn (sutarta 2026-10-16)

**Kodėl:** endpoint langas (~900 ms) yra didžiausias fiksuotas laukimas kiekviename ėjime.
Modelis, kuris iš intonacijos pasako „žmogus baigė", leistų nukirpti po ~200–300 ms.

**Pasirinkimas:** Pipecat **Smart Turn v3** — tik modelis, be Pipecat karkaso.

| | Smart Turn v3 | LiveKit turn detector |
|---|---|---|
| Ką analizuoja | garsą (intonacija, pauzės) | garsą (naujas) / tekstą (senas, pasenęs) |
| Kalbos | 23 (yra PL, RU, UK), **LT nėra** | 14, **LT nėra** |
| Dydis / greitis | 8 MB, CPU ~10–65 ms | v1-mini ~400 MB; pilnas v1 — LiveKit debesyje |
| Licencija | BSD-2, atviras mokymo kodas ir duomenys | LiveKit Model License |
| Be karkaso | ✓ (ONNX) | ✗ |

LT nėra nei viename, bet garso modelis vertina intonaciją, ne žodžius, o artimos kalbos (PL, RU, UK)
yra mokyme — tikėtina, kad veiks; **matuojam, ne spėjam**.

**Eiga:**

```
A1.1 bandymas ant įrašų ─► gerai? ─taip─► A1.2 endpoint trace ─► A1.3 Smart Turn + endpoint.py
                              │                                     (abu sutaria → kirpti po ~250 ms)
                              └─vidutiniškai─► A1.4 fine-tune su mūsų įrašais (train.py)
```

**A1.1 bandymas (be gyvų skambučių, kodo neliečia):**

- Duomenys: `logs/sessions/*/turn_NN_user.wav` (~600 kliento ėjimų) + `asr`/`user_turn` tekstas.
- Kiekvienam ėjimui modelis gauna: (a) visą ėjimą — turi sakyti „baigė"; (b) ėjimą, nukirptą
  per pauzę viduryje — turi sakyti „nebaigė".
- Matuojam: tikslumas abiem atvejais, klaidingų „baigė" dalis (tai pertraukimai — blogiausia
  klaida), inferencijos laikas CPU.
- Rezultatas įrašomas čia, §5.

## 4. Ką paskambinti (Andrius)

3–5 skambučiai per dashboard'ą, skirtingi keliai, kad suvestinė būtų reprezentatyvi:

| # | Scenarijus | Kodėl |
|---|---|---|
| 1 | Pakibęs routeris (perkrovimas, lemputės) | daug trumpų atsakymų — 6b efektas |
| 2 | Nežinomas numeris, adresas dalimis | identifikacijos skaitytuvai |
| 3 | Miręs routeris → tiketas su kontaktais | tiketo dialogas (telefonas, laikas) |
| 4 | Skola arba avarija | parašytos frazės, informavimas |
| 5 | Ilgas pasakojimas pradžioje, klausimas viduryje | suvokimo LLM, `story` endpoint |

Po skambučių:

```
uv run python scripts/latency_report.py --days 1 --turns
```

ir aptariam: kurie ėjimai lėčiausi ir kodėl (endpoint režimas, suvokimas, ilgas sakinys, įrankis).

---

## 5. Žingsniai (pildoma)

### 5.0 Pagrindas (2026-10-15)

- Pridėtas `scripts/latency_report.py`.
- Pirmas vaizdas — §2 (10-14 skambučiai, prieš 6b).
- Laukiam naujų skambučių.

### 5.1 A1.1 Smart Turn ant įrašų (2026-10-16)

`scripts/smart_turn_eval.py`, modelis `smart-turn-v3.2-cpu.onnx` (HF `pipecat-ai/smart-turn-v3`
@ `f766f81`), 597 įrašyti kliento ėjimai (2026-09-28 … 10-14).

| Matas | Rezultatas |
|---|---|
| Inferencija CPU | mediana **16 ms**, max 140 ms |
| Baigtas ėjimas → „baigė" | **95,9 %** (PL 95,4 %, RU 93,5 % gamintojo testuose) — LT intonaciją supranta |
| Nukirpta per vidurinę pauzę → „nebaigė" | 22,9 % |

**Bet „pauzė viduryje" dažniausiai nėra nebaigta mintis.** 40 nukirpimų perrašyti lokaliu
Whisper: dauguma — sakinio riba („Prie routerio. | Tuoj susikišiu…", „Viskas tvarkingai
sukišta. | Rasiat."), kur „baigė" akustiškai teisinga. Tikrai nebaigtų, kuriuos modelis laiko
baigtais („Ir savo jau…", „Admin…"), ~15–20 % tų atvejų.

**Ką tai reiškia praktiškai** — taisyklė „kirpti po W ms tylos":

| W | be modelio | Smart Turn p > 0,7 |
|---|---|---|
| 200 ms | 19,8 % ėjimų pertraukta | 18,2 % |
| 300 ms | 17,4 % | 15,5 % |
| 500 ms | 14,0 % | 12,0 % |

Modelis pertraukimų beveik nesumažina (~2 p. p.). Priežastis — ne kalba: **klientai sako pilną
sakinį ir tęsia**. Akustiškai to atskirti neįmanoma, todėl ir fine-tune (A1.4) to neišspręstų.

**Išvada:** vien Smart Turn endpoint'o iki ~250 ms nesutrumpins be ~15 % pertraukimų. Langą saugiai
sutrumpinti galima tik žinant **turinį** — ar klientas jau atsakė į tai, ko klausėme.

**Variantai (aptarti):**

| # | Variantas | Kaip | Rizika |
|---|---|---|---|
| T1 | **Variklis žino laukiamą atsakymą** | uždaras klausimas („Ar dega?") + dalinis ASR jau turi atsakymą iš žingsnio sąrašo („taip", „nedega") + Smart Turn „baigė" → kirpti po ~250 ms; kitur palikti dabartinius langus | maža; pritaikoma tik uždariems klausimams (didelė ėjimų dalis) |
| T2 | T1 + Smart Turn kaip papildomas signalas atviriems ėjimams: „nebaigė" (p < 0,3) → ilginti langą | mažiau nukirptų pasakojimų | maža |
| T3 | Vien Smart Turn su trumpu langu | | ~15 % pertraukimų — netinka |

T1 sutampa su A1.7 (išankstinis atsakymas į uždarą klausimą): abu remiasi tuo, kad variklis žino,
ko laukia.

### 5.2 Gyvi skambučiai po 6b (2026-10-16, 4 skambučiai, 52 ėjimai)

Skola · miręs routeris + tiltas + tiketas · linija nutrūkusi + tiketas · nežinomas numeris + avarija.

| Sluoksnis (mediana / p90, ms) | 10-14 (prieš 6b) | **10-16 (po 6b)** |
|---|---|---|
| endpoint* | 900 / 900 | 900 / 900 |
| asr | 543 / 894 | 514 / 720 |
| read | 673 / 997 | **0 / 862** |
| suvokimo LLM ėjimų dalis | 80 % (36/45) | **27 % (14/52)** |
| speak (TTFT) | 257 / 393 | 367 / 491 |
| tts | 142 / 489 | 176 / 436 |
| **first** | 1 730 / 2 469 | **1 236 / 2 021** |
| **first + endpoint*** | 2 702 / 3 395 | **2 150 / 2 999** |

- 6b veikia: suvokimo LLM kviečiamas 3 kartus rečiau, pirmas garsas −0,5 s.
- Ėjimas be suvokimo LLM: first 1,14 s, first + ep* 2,10 s. **Endpoint (900 ms) dabar — didžiausias
  sluoksnis**, toliau speak (~0,4 s) ir ASR (~0,5 s).
- Iki demo tikslo 1,5 s trūksta ~0,6 s — beveik tiek, kiek duotų endpoint sutrumpinimas (T1).
- Ilgas pirmas sakinys vis dar brangus: 88 simb. → TTS 0,9 s, 72–75 simb. → 0,7–0,8 s.

**Ne delsos radiniai iš tų pačių skambučių** (aptarti, netaisyta):

| # | Kas | Kur matyti | Priežastis |
|---|---|---|---|
| G1 | **Kliento atsakymas atmestas kaip „echo"** — 3 kartus („Lemputė nedega su interneto simboliu", „Ne. Dainų gatvė 5, butas 5", „Ne dega") | sk. 3, 4: `barge_in` / `overlay` echo | echo = žodžių sutapimas ≥ 0,8 su agento sakiniu; LT atsakymai kartoja klausimo žodžius (`agent/barge_in.py`, `app/voice.py`, `echo_overlap_threshold`) |
| G2 | „5. 5 butaski" → namas 55; adreso ciklas 8 ėjimai; butas klausiamas dar kartą po patvirtinimo; „Ar mane girdite?" | sk. 4 | adreso skaitytuvas sujungia skaičius; G1 prarado pataisymą |
| G3 | „Keno adresas" (= „Kieno adresas?") → „Keno gatvė, taip?" | sk. 4 | klausimas palaikytas gatvės pavadinimu |
| G4 | „Manau, vardas — Vilma" → vardas „Manau" | sk. 3 | ASR „Mano" → „Manau"; vardo skaitytuvas ima pirmą žodį |
| G5 | „einu susimokyti" → „sėkmės mokslams!"; „Ar dar kuo galiu padėti?" 3 kartus; „Ne, viskas" neuždaro | sk. 1 | kalbėtojas klaidingai suprato; pabaigos skaitytuvas nepriima „ne, viskas" |
| G6 | „Malonu, Tomai!" / „Malonu, Alojizos!" pokalbio gale | sk. 1, 4 | pasenęs „Malonu" (F-30 vėl) |
| G7 | Kabelio žingsnis: „Ne." → iškart išvada ir meistras, be pasitikslinimo | sk. 3 | neaiškus „ne" turėjo būti pasitikslintas („Ar pavyko įkišti?") |
| G8 | Valandos „13.18" → „Skambinsime …, 13.18" | sk. 3 | ASR „13–18" kaip laikas; skaitytuvas priėmė |
| G9 | „Gerai, palauksiu — pasakykite, kai būsite pasiruošęs" + tame pačiame sakinyje klausimas apie lemputes | sk. 2 | prieštaringa: žada laukti, bet iškart klausia |
| G10 | ASR kartojimas „Taip, dėl… ×4"; „Tai ypil šio adresu" neperskaitytas → 2 pakartotiniai klausimai | sk. 3 | ASR kokybė; adreso patvirtinimo skaitytuvas |

Gerai veikė: skolos pranešimas, avarija tik po identifikacijos, miręs routeris → tiltas → MAC
pririšimas → patikra → tiketas (sk. 2 — visas kelias be klaidų), tiketo kontaktai.

### 5.3 Pipecat bandymas — pirmas gyvas skambutis (2026-10-16)

Šaka `feature/pipecat-voice`, `chatbot_core/src/app/pipecat_bot.py`; skolos skambutis, 7 ėjimai.
Pipecat matuoja **nuo kliento tylos (VAD) iki agento garso** — tai mūsų pagrindinis matas.

| Ėjimas | Iš viso | endpoint | ASR | variklis + LLM | TTS (1-as sakinys) |
|---|---|---|---|---|---|
| „Taip, dėl šio…" (scripted) | 1 627 | 200 | 917 | ~0 | 452 |
| „Mano vardas Petras…" (scripted) | 2 186 | 200 | 1 007 | ~0 | 936 (73 simb.) |
| „…girdot" (scripted) | 2 152 | 200 | 537 | ~0 | 1 376 (106 simb.) |
| „Taip, kita." (scripted) | **863** | 200 | 485 | ~0 | 139 |
| „Tietos man." (LLM) | 2 260 | 200 | 495 | 1 175 | 345 |
| „Koks jūsų vardas?" (LLM) | 2 497 | 200 | 591 | 1 283 | 380 |
| „Kodėl neveikia?" (LLM) | 2 922 | 200 | 658 | 968 | 1 050 (79 simb.) |
| **mediana** | **2 186** | **200** | **591** | | |

**Ką rodo:**

1. **Endpoint 900 → 200 ms** — Smart Turn sprendžia per 3–5 ms; per visą skambutį tik vieną
   kartą nukirpo per anksti („Ne, negaliu." | „…Sėgaujau" → du ėjimai, agentas atsakė abiem).
2. **Visa mediana nepagerėjo** (2,19 s; senas balsas ~2,15 s su įvertintu endpoint), nes atsirado
   kiti: **ilgas pirmas sakinys** (Piper ~12 ms/simb.: 106 simb. = 1,4 s) ir LLM ėjimai (~1–1,3 s:
   suvokimas ~0,6 + kalbėjimas ~0,4–0,7).
3. **Trumpas parašytas ėjimas — 0,86 s.** Tai rodo, kur galima nueiti be GPU.
4. Pipecat suskaido laiką pats (`pipecat_latency` trace'e) — matavimas be savo kodo.

**Svertai, kuriuos parodė šis skambutis (tinka ir senam balsui):**

| # | Kas | Laimėtų |
|---|---|---|
| P1 | **Piper srautu**: recepto `gabalai()` jau duoda frazes po vieną — siųsti kiekvieną iškart, ne laukti viso sakinio | 0,3–1 s ilguose sakiniuose |
| P2 | Ilgą sakinį TTS'ui skaidyti ties „—" / kableliu (L2) | tas pats, paprasčiau |
| P3 | ASR ilgiems sakiniams ~0,9–1 s — Groq; srautinis ASR tik su GPU (L8) | vėliau |

**Elgesio radiniai (ne Pipecat kaltė):**

| # | Kas |
|---|---|
| G11 | **Gemma įterpė kiniškus rašmenis**: „paslauga la暂时iškai sustabdyta" — sargas taiso tik kirilicą |
| G12 | Vardas iš ASR šiukšlių: „Čestink ir girdot" → „Malonu susipažinti, Čestink!" |
| G13 | „Koks jūsų vardas?" (klausimas agentui) → „šis klausimas nėra mano kompetencija" |
| G14 | Pirmo ėjimo („neveikia internetas") `pipecat_latency` neįrašytas; paskutinio — klaidingas (151 s) |

### 5.4 Senas balsas prieš Pipecat — tas pats skambutis (2026-10-19)

Skolos skambutis abiem keliais dashboard'e, tas pats numeris; Piper — procesų baseine (abiem).
Pipecat skambutis `20261019-104806…0002`, senas `20261019-104947…0003`, po 6 ėjimus.

| Sluoksnis (mediana, ms) | Senas | Pipecat | Pastaba |
|---|---|---|---|
| endpoint (tyla iki nukirpimo) | ~900* | **200** | *nematuojama, sukonfigūruotas langas |
| ASR | 545 | 620 | Pipecat transkribuoja po nukirpimo; senas kartais naudoja dalinį |
| variklis + LLM | ~560 | ~470 | panašu — tas pats variklis |
| TTS 1-a frazė | 160 | 290 | **senas turi frazių talpyklą (0 ms kartotinėms), Pipecat — ne** |
| **pirmas garsas nuo nukirpimo** | **1 230** | ~1 490 | |
| **nuo kliento tylos** | **~2 130*** | **1 690** | **−0,45 s** |

- Pipecat laimi beveik vien endpoint'u (−0,7 s); dalį atiduoda ASR ir TTS talpyklos nebuvimui.
- Vienas Smart Turn „nebaigė" laukė 1,47 s („Ne, čia jau sėgėra.") — vienintelis tokis per skambutį.
- Elgesys abiem keliais tas pats (G6 „Malonu, Tomai!" gale abiem; Gemma: „Linkiu skambio ir gero
  dienos").

**Ką pigiai pataisyti Pipecat kelyje:**

| # | Kas | Laimėtų |
|---|---|---|
| Q1 | PCM talpykla parašytoms frazėms (kaip MP3 sename) | ~0,2–0,4 s kartotiniuose ėjimuose |
| Q2 | `SMART_TURN_STOP_SECS` 2,0 → ~1,2 | „nebaigė" atvejai trumpesni |
| Q3 | ASR iš dalinio (kaip sename) | ~0,1 s |

### 5.5 Pertraukimų skambutis (2026-10-19 12:57) — vyko senuoju balsu

`20261019-125749…0002` — antraštėje liko „senas", todėl Pipecat A3 (delivery) **dar neišbandytas
gyvai**. Sename kelyje `BARGE_IN` išjungtas: kalba ant agento balso tik užrašoma (`overlay`),
agentas kalba toliau — taip ir buvo abu kartus.

- Delsa: first 1,61 s, first + endpoint* ~2,5 s (5 ėjimai).
- G15: „Oho! Aš mokėjau vakar." / „Tikrai sakiau, kad mokėjau." → „Paslauga atsistatys
  automatiškai per valandą po apmokėjimo" (`inform.paid_just_now`). Mokėjo **vakar**, o paslauga
  vis dar sustabdyta — tai ginčas, ne „ką tik sumokėjau": turėtų būti paaiškinimas ir pasiūlymas
  registruoti `billing_request` (sutarta anksčiau).
- G16: antrasis `overlay` („Aš mokėjau vakar") neturi `overlay_applied` — sename kelyje dingo.

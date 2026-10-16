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

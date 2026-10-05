# Modelių pasirinkimas: ASR, TTS, LLM (2026-10-05)

Andrius: *„produkcijoje turėsim GPU, todėl reikia pagalvoti, pasirinkti geriausius modelius ir juos
ištestuoti. Multilanguage modelius, kad veiktų LT kalba. Pasigalvoti geriausias praktikas dėl ASR
ir TTS. LLM pasirinkti opensourcinį — jei galime, dabar įsidiegti mažesnį, o turint GPU turėti
alternatyvas didesniems. Gal kai kuriuos modelius galime pasiimti per nuorodą, kad juos
išsibandyti?"*

Šis dokumentas — **ką rinktis ir kaip tai pamatuoti**, ne galutinis sprendimas. Sprendimą priima
mūsų pačių garsas ir mūsų pačių eval'as, ne svetimi lyderių sąrašai.

---

## SPRENDIMAI 2026-10-05 (Andrius)

| # | Sprendimas | Ką tai reiškia |
|---|---|---|
| **S1** | **Atsisakyti mokamo `gpt-4o-mini`** | atviras modelis abiem darbams; pirma skaitymui (lengva), paskui kalbėjimui (reikia aklo A/B) |
| **S2** | **Pakeisti TTS, kad būtume nepriklausomi** | Piper + lietuviški balsai; edge-tts lieka tik atsarginis |
| **S3** | **ASR dabar NEDAROM** — tik surašom alternatyvas | §2 lentelė yra tas sąrašas; grįžtam, kai bus GPU |
| **S4** | Lokalius modelius pirma pabandyti **ant CPU** ir **per nuorodas** | žr. §9: ką realiai galima padaryti be GPU |
| **S5** | GPU dar nenupirkta — **reikia rekomendacijos** | žr. §10 |
| **S6** | Pirma — **L1 ir L2** (be modelio ten, kur atsakymas ar žodžiai jau yra) | padaryta 2026-10-05, žr. FIX_PLAN „Banga 9" |

## 0. Ką jau turim (ir kodėl tai svarbu)

| Turim | Kur | Kodėl svarbu |
|---|---|---|
| **333 įrašyti kliento ėjimai, 24,6 min tikro lietuviško telefoninio garso** (29 sesijos) | `logs/sessions/<id>/turn_NN_user.wav` | tai ir yra mūsų ASR testų rinkinys — su mūsų žargonu, mūsų klientais, mūsų mikrofonais |
| Gyvi transkriptai kiekvienam tam failui | trace'o `asr` įvykiai (`raw`, `transcript`) | etaloną (gold) kuriam **taisydami**, ne rašydami iš nulio — kelios valandos, ne savaitės |
| `replay_stt.py` — offline ASR stendas (`--backend groq|local --model --prompt`) | `chatbot_core/` | jau yra karkasas: belieka pridėti WER ir naujus backend'us |
| `eval/perception/run.py` — skaitymo eval'as (68 atvejai, realus modelis) | `src/agent/eval/perception/` | tai **LLM stendas**: pakeiti modelį, paleidi, lygini |
| Portai `ports/asr.py`, `ports/tts.py`; LLM per **litellm** | `src/ports/`, `src/services/llm/client.py` | modelio pakeitimas = naujas adapteris, variklis nekinta |
| Pamatuota delsa (3 skambučiai, 59 ėjimai) | žr. §1 | yra nuo ko atsispirti |

Svarbu: ASR porte jau yra **`context`** parametras (per ėjimą paduodamas agento klausimas kaip
biasing tekstas) — tai viena stipriausių ASR technikų, ir ji mums jau prijungta.

---

## 1. Delsos biudžetas: kur mes esam ir kur turim būti

Mediana iš 3 gyvų skambučių (59 ėjimai):

| Sluoksnis | Dabar | Pramonės 2026 tikslas (p95) | Komentaras |
|---|---|---|---|
| Endpointing (tyla prieš ASR) | nematuojam | 150–200 ms | semantinis endpointing'as (žr. §5) |
| ASR (galutinis) | 546 ms | 100–200 ms | srautinis ASR + partials |
| **Skaitymas LLM** | **1 556 ms** | 150–300 ms | lokalus 1,7–8B GPU, arba be modelio (fast_path) |
| Variklis (decide+execute) | **2 ms** | — | nieko taisyti nereikia |
| **Kalbos LLM (TTFT)** | **1 156 ms** | 150–300 ms | lokalus modelis arba parašyti žodžiai |
| TTS pirmas garsas | ~270 ms | 80–150 ms | Piper lokaliai |
| **Pirmas garsas klientui** | **3 009 ms** (p90 4 476) | **< 1 000 ms** | |

Išvada: variklis nekliudo. Visa delsa — trys I/O sluoksniai, ir **du nuoseklūs LLM skambučiai**.

---

## 2. ASR — ką bandyti

Lietuvių kalbai 2026 m. atsirado tai, ko pernai nebuvo: **LIEPA-3 korpusas** (~9 800 h,
Vilniaus universitetas, atviras) ir ant jo pritreniruoti modeliai. Bendri daugiakalbiai modeliai
lietuviškai pralošia specializuotiems maždaug dvigubai.

| # | Modelis | LT kokybė (jų pačių skaičiai) | Dydis / kaip leisti | Licencija | Mūsų tinkamumas |
|---|---|---|---|---|---|
| **A1** | [`akisviete/azuolas-qwen-lt`](https://huggingface.co/akisviete/azuolas-qwen-lt) (Ąžuolas v2, Qwen3-ASR pagrindu) | **FLEURS LT 9,74 % WER / 6,79 % CER**; Common Voice 5,35 % | 1,7B, `transformers >= 5.13` | CC-BY-4.0 (bazė Apache-2.0) | **Geriausi skaičiai.** Kortelėje tiesiai parašyta, kad apima **telefoninius įrašus**, ir kad į tylą/triukšmą grąžina **0 simbolių** — telefoniniam agentui tai aukso vertės savybė (Whisper tyloje mėgsta prigalvoti) |
| **A2** | [`Noctra-labs/parakeet-tdt-0.6b-v3-lt`](https://huggingface.co/Noctra-labs/parakeet-tdt-0.6b-v3-lt) | **LIEPA test 10,87 % WER** (bazė 33,57 %) | 0,6B, NVIDIA NeMo | CC-BY-4.0 | **Greičiausias** (TDT transduceris). Minusas: NeMo — sunkus naujas priklausomumas; treniruota daugiausia ant *skaitytos* kalbos |
| **A3** | [`kristijonas/paprika-whisper-lt`](https://huggingface.co/kristijonas/paprika-whisper-lt) (v3) | FLEURS LT 12,32 % WER; VoxPopuli 16,98 % | 0,8B (whisper-large-v3-turbo pagrindu); yra **CTranslate2/faster-whisper** ir [ONNX](https://huggingface.co/aztekvisur/paprika-whisper-lt-v3-onnx) | CC-BY-4.0 | **Pigiausias kelias**: įsijungia į MŪSŲ esamą `faster_whisper_asr` adapterį be naujų priklausomumų |
| **A4** | [`VULSK/nemotron-asr-streaming-0.6b-medical-lt`](https://huggingface.co/VULSK/nemotron-asr-streaming-0.6b-medical-lt) | — (medicinos dikt. + LIEPA-3) | 0,6B, **srautinis** | žr. kortelę | Vienintelis sąraše **srautinis** → partials ir semantinis endpointing'as |
| **A5** | [`nvidia/parakeet-tdt-0.6b-v3`](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | FLEURS LT 20,35 % | 0,6B, NeMo | CC-BY-4.0 | Bazinis daugiakalbis — tik kaip atskaitos taškas |
| **A6** | Groq `whisper-large-v3` (dabar) | — | hosted | — | Dabartinė bazinė linija: 546 ms, kokybė „pakenčiama" |
| **A7** | [`liepa-project/LIEPA-3`](https://huggingface.co/datasets/liepa-project/LIEPA-3_read-spon-dial_16kHz) | duomenų rinkinys | — | tyrimams | Jei reikės **savo** pritreniravimo (ISP žargonas: „routeris", „maršrutizatorius", „WAN", MAC adresai) |

**Bendra bėda:** visi trys LT pritreniruoti modeliai grąžina **mažąsias raides be skyrybos**. Mūsų
skaitytuvai vietomis dalija sakinį sąlygomis („Neturiu kito routerio, tik kompiuterį") — tai
**realus integracijos pavojus**, kurį reikia pamatuoti, ne nuspėti. Sprendimai: (a) atskiras
skyrybos/didžiųjų raidžių atkūrimo modelis, (b) skaitytuvus daryti nepriklausomus nuo skyrybos.

### ASR geriausios praktikos (ką taikyti, nepriklausomai nuo modelio)

1. **Konteksto biasing'as kiekvienam ėjimui** — agento klausimas + tikėtinas žodynas į `initial_prompt`
   (Whisper) arba į „hotwords"/žodžių sąrašą (transduceriai). Mums tai **jau prijungta** (`context`).
2. **Srautinis ASR + partials** ir **semantinis endpointing'as**: nutraukti pagal *prasmę*, ne pagal
   tylos ilgį. Pramonėje tai duoda 200–600 ms ir ~30 % mažiau klaidingų nutraukimų.
3. **Tyla turi grąžinti nieką.** Whisper į tylą „prigalvoja"; Ąžuolas kortelėje tai žada tiesiai.
4. **8 kHz telefono linija**: aukštinti iki 16 kHz, bet pamatuoti WER abiejuose — ir treniruoti/rinkti
   testus ties ta pačia kokybe, kurią duos linija.
5. **Nekelti teksto normalizavimo į modelį** — skaičiai, IP adresai, valandos tvarkomi mūsų pusėje
   (`lt_text.py`, `hours_words`, `speakable`). Taip modelio pakeitimas nelaužia logikos.

---

## 3. TTS — ką bandyti

| # | Variantas | Kokybė / greitis | Licencija | Komentaras |
|---|---|---|---|---|
| **T1** | **Piper lietuviški balsai:** [Reginutė](https://github.com/RobertasTa/reginute), [Ingutė](https://github.com/RobertasTa/ingute) | CPU, realaus laiko faktorius ~0,05–0,2 | CC-BY-4.0 (LIEPA duomenys) | **Pirmas kandidatas.** Piper kataloge lietuvių nebuvo iki 2026 rugsėjo; šie balsai treniruoti ant VU LIEPA (~3 h aktoriaus studijoje) ir turi **savo akcentus suprantantį fonemizatorių** (`phonemize_lithuanian.py`, 189 tūkst. atvaizdavimų) — be jo Piper lietuviškai nekalba taisyklingai |
| **T2** | edge-tts (dabar) | gera, bet **neoficialus** Microsoft endpoint'as | — | Produkcijai netinka kaip pagrindinis: gali nukirsti bet kada. Lieka atsarginis |
| **T3** | Savas VITS ant LIEPA | kaip T1, bet valdom | — | Tik jei T1 balsai netiks. VU tyrimas (Lėveris, Korvel, 2026) rodo: ~3 h duomenų **daugiakalbiai/daugiabalsiai** modeliai kokybę *blogina* → vienas balsas, vienas kalbėtojas |
| **T4** | Kokoro-82M, XTTS-v2, F5-TTS, Qwen3-TTS | — | — | Populiarūs, bet **lietuvių nėra** oficialiai palaikomų. Netikėti „multilanguage" užrašu — tikrinti balsų sąrašą |

### TTS geriausios praktikos

1. **Srautas per sakinį** — jau turim (`StreamingTTSProvider`, `split_sentences`). Pamatuota: TTS prie
   pirmo garso prideda tik ~270 ms, tad TTS **nėra** mūsų delsos problema.
2. **Diktavimas ≠ skaitymas.** IP adresai, MAC, numeriai — per `speakable()` (jau yra).
3. **Cache'as** pastoviems sakiniams (pasisveikinimas, „palauksiu") — `logs/tts_cache` jau yra.
4. **Vienas balsas visam produktui** ir fiksuota versija: balso pasikeitimas skambina klientui kaip
   „kitas žmogus".

---

## 4. LLM — du skirtingi darbai, du skirtingi modeliai

Mums LLM dirba du visiškai nevienodus darbus, ir tai leidžia **nepirkti vieno didelio**:

| Darbas | Kas tai | Ko reikia iš modelio | Dydis |
|---|---|---|---|
| **Skaitymas** (`perception`) | iš kliento sakinio — uždara žyma + faktai JSON | **klasifikacija**, ne kūryba; lietuvių *supratimas* | mažas (1,7–8B) pakanka |
| **Kalbėjimas** (`speak`) | agento žodžiai lietuviškai | **generavimas** be gramatikos klaidų, šiltas tonas | čia kokybė kainuoja |
| (fone) **analyst** | signalai iš pokalbio | ne kritiniame kelyje | mažas |

### Kandidatai pagal VRAM

| Pakopa | Modelis | Kodėl | Nuoroda |
|---|---|---|---|
| **Mažas — diegti dabar** | **EuroLLM-9B-Instruct** | treniruotas ant **visų 24 ES kalbų**; nepriklausomame Baltijos šalių tyrime (2026) **pirma vieta lietuviškiems benchmarkams** (Arc/HellaSwag/MMLU/TruthfulQA) | [utter-project](https://huggingface.co/utter-project) · [eurollm.io](https://eurollm.io/) |
| | Gemma-2-9B-it / Gemma-3-12B-it | tame pačiame tyrime lietuviškai lygiavertis EuroLLM | [Gemma](https://huggingface.co/google) |
| | Qwen3-8B-Instruct | 100+ kalbų, labai stipri instrukcijų disciplina (mūsų promptai griežti) | [Qwen](https://huggingface.co/Qwen) |
| | Salamandra-7B-instruct | 35 Europos kalbos, BSC | [BSC-LT](https://huggingface.co/BSC-LT) |
| **Didesnis — kai bus GPU** | **EuroLLM-22B-Instruct** | 2026 m. ES atviras modelis, 24 ES kalbos; yra **GPTQ** kvantas (telpa į 24 GB) | [utter-project/EuroLLM-22B-2512](https://huggingface.co/utter-project/EuroLLM-22B-2512) · [GPTQ](https://huggingface.co/Euraika/EuroLLM-22B-Instruct-GPTQ) |
| | Gemma-3-27B-it | stiprus vienos GPU modelis | |
| | Qwen3-30B-A3B (MoE) | didelio modelio kokybė, mažo modelio aktyvacija — geras srautui | |
| **Atskaitai** | VU/Neurotechnology LT-Llama-2 | pirmas atviras **lietuviškas** Llama2; bazė sena, bet gera atskaitos linija | [Informatica, VU](https://www.informatica.vu.lt/journal/INFORMATICA/article/1372/text) |

**Dėmesio:** modelių kartos keičiasi kas kelis mėnesius (paieškoje jau mirga Qwen3.6, Gemma 4).
Sąrašas — iš ko *pradėti stendą*, o ne tiesa amžiams. Testavimo dieną pirmiausia patikrinam, ar
nėra naujesnės tos pačios šeimos versijos.

### Kaip įsidiegti ir kaip išbandyti PRIEŠ diegiant

| Būdas | Kam | Pastaba |
|---|---|---|
| **Hosted per nuorodą (be diegimo)** | greitai palyginti kokybę lietuviškai | [OpenRouter](https://openrouter.ai/models) (Qwen, Gemma, Mistral…), [HF Inference Providers](https://huggingface.co/docs/inference-providers), [Groq](https://console.groq.com/docs/models) (labai greitas), [Together](https://api.together.ai/models). **litellm jau turi maršrutus** → `_get_provider` užtenka vienos šakos |
| **Ollama** (vienas `ollama pull`) | per valandą pajusti modelį savo mašinoje | litellm: `ollama/qwen3:8b`; patogu rankiniam bandymui, bet srautui/konkurencijai per lėtas |
| **vLLM** (produkcijai) | GPU, srautas, daug kanalų | OpenAI-suderinamas API → litellm `hosted_vllm/<modelis>` + `api_base`; **mūsų kode reikia ~10 eilučių** `_get_provider`/`api_base` |

Kaina ne argumentas (dabar 0,012 USD/skambutis). Argumentai: **delsa**, **GDPR** (garsas ir pokalbis
nepalieka mašinos), **nepriklausomumas** (edge-tts/rate limit'ai) ir **kanalų skaičius**.

---

## 5. Technikos, kurios duoda daugiau nei modelio pakeitimas

Eilės tvarka pagal naudą/kainą:

1. **Skaityti be modelio, kai atsakymas uždaras** (`fast_path` + žingsnio pasirinkimai). Dabar
   `fast_path` suveikia **2 ėjimuose iš 53**. Uždari „taip/ne/padariau" sudaro apie pusę ėjimų →
   **−1,6 s** pusei pokalbio, be jokios naujos technikos.
2. **Kalbėti parašytais žodžiais, kai jie jau yra kortelėje** (dabar 10 iš 59 ėjimų) → **−1,2 s**.
3. **Semantinis endpointing'as** (srautinis ASR + „ar mintis baigta?") → 200–600 ms *jaučiamos* delsos.
4. **Lokalus skaitymo modelis GPU** → **−1,2 s** kiekvienam ėjimui, kuriam vis dar reikia modelio.
5. **Du LLM skambučiai → vienas** ten, kur planas nepriklauso nuo skaitymo (spekuliatyvus
   „palauksiu"/instrukcijos pradėjimas, kol skaitymas dar eina). Sudėtingiausia — paskutinė.

Po 1+2+4 mediana turėtų būti **~1,2–1,6 s** vietoj 3,0 s.

---

## 6. Stendas (demo), kurį siūlau pasidaryti

Trys **matuojami** žingsniai ant to, kas jau yra. Kiekvieno pabaigoje — lentelė, ne nuojauta.

### Stendas A — ASR bake-off ant MŪSŲ garso
* Etalonas: 60 ėjimų iš 333 įrašytų (taisom gyvus transkriptus → `gold.jsonl`).
* `replay_stt.py` papildom: WER/CER metrika + backend'ai `hf` (Ąžuolas, paprika) ir `nemo` (parakeet-lt).
* Matuojam: **WER, CER, delsa (p50/p90), elgsena tyloje, skyrybos nebuvimo įtaka mūsų skaitytuvams**,
  ir visa tai 16 kHz ir 8 kHz (telefono imitacija).
* Rezultatas: lentelė „modelis × WER × delsa × rizika", ir sprendimas vienam.

### Stendas B — LLM bake-off ant skaitymo
* `eval/perception/run.py` papildom `--model` (ir `api_base`), paleidžiam 68 atvejus per kiekvieną
  kandidatą: gpt-4o-mini (bazinė linija), EuroLLM-9B, Qwen3-8B, Gemma-3-12B.
* Matuojam: **teisingų skaitymų %, delsa p50/p90, JSON disciplina** (kiek kartų sulaužo formatą).
* Kalbėjimui — atskiras aklas A/B: 20 tų pačių situacijų, du modeliai, Andrius renkasi, kuris skamba
  kaip žmogus. Lietuvių kalbos kokybė čia yra sprendžiamoji, ir jos benchmark'ai nepamatuoja.

### Stendas C — TTS klausymo testas
* 10 sakinių: pasisveikinimas, IP diktavimas, adresas, tiketo perskaitymas, ilgas paaiškinimas.
* edge-tts (dabar) vs Piper Reginutė vs Piper Ingutė → aklas klausymas + RTF/delsa + „ar nesilaužo
  ties mūsų `speakable()` tekstu".

### Priėmimo vartai (visiems trims)
Pilnas pokalbių eval'as **turi likti 195/195**, o gyvas skambutis — ne blogesnis. Nė vienas
modelis neįeina į produkciją, kol abu nepraeina.

---

## 7. Kiek kanalų atlaikysim (ko reikės GPU)

| Sluoksnis | Vienos GPU (24 GB klasės) pajėgumas | Riba |
|---|---|---|
| ASR (0,6–1,7B, int8) | ~10–20 vienalaikių srautų | GPU |
| LLM skaitymas (8B int4, vLLM) | ~8–16 vienalaikių trumpų užklausų < 400 ms | GPU |
| LLM kalbėjimas (9–22B) | mažiau; arba cloud, arba antra GPU | GPU/VRAM |
| TTS (Piper) | CPU, dešimtys srautų | CPU |
| Variklis | 2 ms/ėjimą — praktiškai neribotas | — |
| sqlite | iki ~20 skambučių ramu | vienas rašytojas → virš to Postgres |

Realus startas: **8–12 vienalaikių skambučių vienai GPU mašinai**. Dviem kanalams nereikia nieko
naujo. Prieš žadant „10 vienu metu" — apkrovos testas (N paralelių sesijų per tekstinį API):
įtariamiausia vieta yra viena bendra sqlite jungtis `database/connection.py`.

---

## 8. Ko reikia iš Andriaus, kad stendai pasidarytų

1. **GPU specifikacija** (modelis, VRAM, ar viena ar dvi) — nuo to priklauso, ar 9B, ar 22B, ir ar
   ASR su LLM dalijasi kortą.
2. **Ar linija bus 8 kHz** (SIP trunk per operatorių) — tada testus darom ties 8 kHz nuo pat pradžių.
3. Leidimas **60 ėjimų etalonui** (reikės tavo valandos: pataisyti transkriptus, ne surašyti).

---

## 9. Ką galima pabandyti JAU DABAR (be GPU)

| Sluoksnis | Ant CPU | Per nuorodą (be diegimo) | Ko NEIŠMATUOSIM be GPU |
|---|---|---|---|
| **TTS (Piper)** | **pilnai** — Piper ir buvo sukurtas CPU; RTF ~0,05–0,2, lietuviški balsai [Reginutė](https://github.com/RobertasTa/reginute) / [Ingutė](https://github.com/RobertasTa/ingute) | — | nieko: produkcijoje bus taip pat |
| **ASR (bake-off)** | **galima, bet lėtai**: `faster-whisper` int8 CPU, arba [paprika ONNX](https://huggingface.co/aztekvisur/paprika-whisper-lt-v3-onnx). Offline per 333 įrašus — tinka, nors užtruks | Groq (dabartinė bazinė linija) | gyvos delsos (CPU 3–10× lėčiau) |
| **LLM skaitymas** | 8B ant CPU ≈ 5–15 tok/s → 3–10 s atsakymui: **kokybei tinka, delsai ne** | [OpenRouter](https://openrouter.ai/models), [Groq](https://console.groq.com/docs/models), [HF Inference](https://huggingface.co/docs/inference-providers), [Together](https://api.together.ai/models) — litellm maršrutai jau yra | tikros delsos |
| **LLM kalbėjimas** | tas pats | tie patys | tikros delsos |

Tad eiliškumas be GPU: **(1)** Piper — tikras, galutinis pakeitimas; **(2)** LLM kokybės aklas A/B
**per nuorodas** (ten pat ir skaitymo eval'as su `--model`); **(3)** ASR bake-off offline, kai
turėsim etaloną. Delsos skaičius bus tik iš GPU — dėl to §10.

Techninė pastaba: `litellm` jau yra mūsų LLM klientas, tad atviras modelis per nuorodą yra
~10 eilučių `services/llm/client.py::_get_provider` (naujas maršrutas + `api_base`). Tas pats
kelias vėliau rodo į savo `vLLM` — prodo ir bandymų kodas tas pats.

---

## 10. GPU rekomendacija

Ko reikia vienu metu: **ASR** (0,6–1,7B), **LLM** (8–22B) ir **Piper** (CPU). Skaičiai apytiksliai,
int4/AWQ kvantams su KV atsargomis ~10 kanalams:

| Variantas | VRAM | Ką atlaiko | Kam |
|---|---|---|---|
| **1 × 24 GB** (RTX 4090 / L4 / A10) | ASR ~2–4 GB + LLM 8–9B ~8 GB + KV ~5 GB | **8–12 vienalaikių skambučių** | **Rekomendacija startui.** EuroLLM-9B arba Qwen3-8B skaitymui IR kalbėjimui |
| 1 × 32 GB (RTX 5090) | tas pats + atsarga | 10–15 | jei norisi vietos 12–14B kalbėjimo modeliui |
| **1 × 48 GB** (L40S / A6000) | ASR + **EuroLLM-22B** int4 ~14 GB + KV | 8–12 | jei aklas A/B parodys, kad 22B lietuviškai aiškiai geriau |
| 2 × 24 GB | ASR viena korta, LLM kita | 15–25 | kai kanalų reikės daugiau nei vienas modelis atlaiko |

Aplink GPU: 8+ branduolių CPU (Piper, VAD, garso perkodavimas), 32–64 GB RAM, NVMe ~100 GB
modeliams. Jei linija bus SIP — atskira (ar ta pati) mašina Asterisk/FreeSWITCH.

**Mano rekomendacija:** pradėti nuo **vienos 24 GB** kortos. Ji padengia viską, ko reikia
8–12 kanalams, ir jos pakanka sprendimui, ar 22B kalbėjimo modelis apskritai duoda girdimą
skirtumą. Jei duos — 48 GB korta arba antra 24 GB.

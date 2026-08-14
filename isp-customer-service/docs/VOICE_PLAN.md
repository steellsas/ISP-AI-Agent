# Balso natūralumo planas (sutarta 2026-08-14)

Tikslas: natūralus telefoninis dialogas — pritarimai abiem kryptim be pokalbio
stabdymo, vienas klausimas per atsikvėpimą, vertinantys patvirtinimai, o
ilgainiui — pilnas dupleksas. Principas nesikeičia: kodas = mechanika,
failai = elgsena; visi slenksčiai — konfigūracijoje, ne kode.

## Sutarta seka

Visi žingsniai daromi VOICE šakoje (po refactor/langgraph-v2 PR į develop).

| # | Žingsnis | Turinys | Būsena |
|---|----------|---------|--------|
| 1 | L1 + L2 | Vienas klausimas per turn'ą; vertinantys patvirtinimai (pack'ų `tikslas`); žingsnio kartojimo paaiškinimas | baigta (8739d03) |
| 2 | V1 + replay | Dinaminis Whisper prompt (klausimas + laukiami atsakymai), <0.3 s garso sargas, įrašymo manifest.jsonl, replay stendas (`chatbot_core/replay_stt.py`) | baigta (bf54f55) |
| 3 | L3a | Išmanus barge-in: default-deny + poliariškumas + aido tekstinis filtras | kitas |
| 4 | L3b | Agento „mhm" įterpimai diktavimo kontekstuose | — |
| 5 | L4 | Srautinis STT + semantinis turn-taking (sprendžiam po 1–4) | — |

## 1 žingsnio darbų sąrašas (L1+L2, paruošta įgyvendinimui)

1. **Vardo klausimas be uodegos** — `knowledge/identification.yaml` frazė
   `questions.caller`: „O su kuo kalbu — koks jūsų vardas? Ar jūs sutartį
   sudaręs asmuo?" → tik vardo klausimas. Ryšys su sutartimi skaitomas iš
   atsakymo, jei klientas pats pasako (`detect_caller_relation` jau veikia);
   atskirai nebeklausiamas.
2. **Vienas klausimas per atsakymą** — taisyklė į `prompts/partials/identity.md`
   (viena „?" per repliką; jei reikia dviejų dalykų — antras kitame ture).
   Skriptuotų frazių auditas: `identification.yaml` + pack'ų `klausimas` laukai.
3. **`tikslas:` laukas pack'ų žingsniuose** (atidėtas sąmoningumo punktas №1):
   `Step` dataclass + `faults.py` perdavimas + naratoriaus facts bloke
   „ŠIO ŽINGSNIO TIKSLAS: … — reaguodamas įvertink, ar pasiektas
   (‚Gerai — radote' / ‚Ne, ne šis kabelis'), tada tęsk." Užpildyti
   internet_mires_routeris.yaml žingsnius kaip šabloną.
4. **Žingsnio kartojimo paaiškinimas** (№2): žingsnio pristatymų skaitiklis;
   ≥2 → facts bloke „ŽINGSNIS KARTOJAMAS — paaiškink, kodėl klausi dar kartą."
   (naratoriaus atitikmuo solverio `repeat_ack`).
5. **Proceso žurnalas solveriui** (№3): atliktų žingsnių rezultatai solverio
   kontekste („kas jau padaryta ir kuo baigėsi"), kad analizė pildytųsi iš
   sprendimo eigos.

## Saugikliai (sutarti diskusijoje)

### L1/L2
- Opportunistic slot filling LIEKA: klausiam po vieną, bet iš vieno atsikvėpimo
  imami VISI slotai/faktai — jokių tarpinių klausimų, kai atsakyta į priekį.
- Vardo klausimas — be „ar sutartį sudaręs asmuo?" uodegos; ryšys su sutartimi
  skaitomas, jei klientas pats pasako, kitaip nebeklausiamas.

### L3a (barge-in)
- Neiginys/stabdymas („ne", „stop", „palauk", „blogai") → hard barge-in VISADA,
  nepriklausomai nuo trukmės.
- Baltasis pritarimo sąrašas („taip", „gerai", „aha", „mhm", „klausau") →
  agentas tęsia; žodis fiksuojamas kaip sutikimas.
- Visa kita (neaišku, „Nu…") → default-deny = barge-in kaip dabar; per klaidą
  „prakalbėtas" turiningas įsiterpimas neprarandamas — apdorojamas kitą turn'ą.
- Aido filtras: įsiterpimo transkriptas lyginamas su ŠIUO METU grojamo TTS
  sakinio tekstu — FUZZY token overlap (≥80 % → aidas, ignoruoti), ne griežtas
  `in` (Whisper iš garsiakalnio grįžusį garsą transkribuoja su 1–2 klaidom).

### L3b (agento įterpimai)
- Tik diktavimo kontekstuose (adresas, valandos, anamnezė) ir tik kai NLU jau
  atpažino dalinį vienetą (pvz., gatvė be namo nr.).
- Rate limit kaip apsauginis diržas: ne dažniau nei kas 5–7 s (config).
- Klipai generuojami serverio starte TUO PAČIU TTS balsu, kešuojami
  `data/backchannels/<balsas>/`; statiniai failai — tik fallback.
- Ducking −6…−10 dB, klipas <350 ms; garsumo kreivė su 20–30 ms
  ramp-down/ramp-up (jokio laiptuoto perėjimo — girdisi trūkčiojimas).
- Visi skaičiai — config puslapyje.

### L3c (nukrypusio kliento pertraukimas)
- Anamnezės fazėje NEPERTRAUKINĖJAMA — priešistorė yra duomenys.
- Sprendimo fazėje: tik po 6–8 s be IT raktažodžių (config), su mandagia
  cushion fraze iš failo („Atsiprašau, kad įsiterpiu, bet kad greičiau
  sutvarkytume ryšį — …").

### V2 (turn-taking, daroma kartu su 2–4)
- VAD parametrai (started_talking_threshold, speech_threshold,
  audio_chunk_duration, can_interrupt) → config puslapis.
- Adaptyvus VAD langas iš dialogo: po adreso klausimo — ilgas (≈3.5 s), po
  taip/ne — trumpas (≈1.8 s).
- Nebaigtos minties sargas: transkriptas baigiasi „ir/bet/tai…" → palaukti dar
  langą.

## Replay stendas (privalomas prieš 3–4)
- Ištisinis įrašymas dviem takeliais (klientas + agentas atskirai) su bendra
  laiko ašimi (manifestas su timestamp'ais) — persidengimo momentai atkuriami
  tiksliai.
- Blogų turn'ų WAV leidžiami per STT pakartotinai su skirtingais parametrais
  offline — derinimas matuojamas, ne spėliojamas.

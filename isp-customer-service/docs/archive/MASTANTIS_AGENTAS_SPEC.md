# Mąstantis agentas ant bėgių — dizaino specifikacija

> Projektas prieš kodą. Remiasi: [ARCHITEKTUROS_LINIJA.md](ARCHITEKTUROS_LINIJA.md)
> (sluoksniai) ir [ARCHITEKTUROS_SCHEMA.md](ARCHITEKTUROS_SCHEMA.md) (srautas).
> Sluoksniai: 🔒 mechanizmas (kodas) · ⚙️ politika (config) · 📚 žinios (RAG/promptai).

## Principas
Determinizmas riboja VEIKSMUS, ne MĄSTYMĄ. Vienas sprendėjas. Klasifikatorius —
jutiklis, ne sprendėjas. Kiekvieną saugos-kritinį veiksmą vykdo kodas, ne LLM.

## Kvietimų tvarka (variantas A)
Per ėjimą 3 serijiniai LLM kvietimai: **① klasifikatorius → ③ sprendėjas → ⑤ narratorius**.
Jei balso latencija per didelė — pereinam į **B**: sulieti ③+⑤ į vieną struktūrinį
kvietimą (vartai validuoja PRIEŠ ištariant; neteisingas `next_action` → tekstas
išmetamas, fallback). B — tik prireikus.

---

## ① SUVOKIMAS — klasifikatorius (jutiklis)
🔒 kvietimas + validacija · 📚 klasifikavimo instrukcijos. **NERAŠO į State.**
Gauna: kliento tekstą + kokio atsakymo laukiama (kontekstinė klasifikacija).

Grąžina `Candidate Observation`:
```json
{
  "candidate_observation": "lights_off | device_changed | restored | in_progress | ...",
  "intent": "answer | in_progress | question | confused | silence | done",
  "internally_inconsistent": false,
  "confidence": 0.0
}
```
- `internally_inconsistent` — klientas prieštarauja PATS SAU viename sakinyje
  („nedega, ai ne, dega"), be jokios telemetrijos. Sprendėjas žinos persiklausti.
- Kandidatas — TIK spėjimas. Sprendėjas sprendžia ar juo tikėti.

---

## ② TELEMETRIJA
🔒 `diagnose_connection` → raw faktai + 🔒 verdict tree kandidatas (žr. žemiau).

### Verdict tree — HIBRIDAS (sprendimas)
Verdict tree LIEKA kietas 🔒, bet kaip **faktų + kandidato-priežasties (su
pasitikėjimu) tiekėjas, NE galutinis žodis.**
- `gather_signals()` → faktai (port, MAC, CRC, DHCP, billing, incident). 🔒
- `decide()` → `{candidate_cause, confidence}` (pvz. `foreign_mac`). 🔒 — greitas,
  deterministinis, testuojamas pirmas spėjimas.
- **Interpretacija-kaip-galutinis-sprendimas** persikelia į sprendėją 📚: kandidatas =
  stiprus prior, kurį sprendėjas gali patvirtinti / patikslinti / atmesti pagal dialogą.

---

## ③ SPRENDĖJAS — vienintelis sprendėjas
📚 žinios (telemetrijos interpretacija + playbook'ai + conflict matrix).
Įvestis: `hypothesis` (gyva) + `candidate_observation` (①) + telemetrija/kandidatas (②) + istorija.

Darbas:
1. Sutaiko candidate ↔ telemetrija ↔ istorija.
2. Aptinka PRIEŠTARAVIMĄ (conflict matrix, žr. žemiau).
3. Peržiūri hipotezę (patvirtina / prieštarauja / patikslina / pivotuoja).
4. Siūlo kitą ėjimą iš LEISTINOS aibės.

Griežta struktūrinė išvestis (🔒 Pydantic kontraktas):
```json
{
  "current_hypothesis": "client_looking_at_wrong_device_ont_instead_of_router",
  "confidence": 0.85,
  "conflict_detected": true,
  "conflict_note": "klientas mini raudoną LOS, telemetrija: routeris gauna signalą",
  "hypothesis_changed": true,
  "reason_for_change": "Klientas minėjo raudoną 'LOS', bet telemetrija rodo signalą iki namų — žiūri į ONT, ne routerį.",
  "next_action": "disambiguate",
  "playbook_step": "dr_redirect_device",
  "narrator_instruction": "Atsiprašyk, paaiškink kad panašu žiūri į šviesolaidžio dėžutę (ONT), ne Wi-Fi stotelę. Paprašyk susirasti įrenginį su antenomis. Užjaučiantis, be terminų."
}
```
- `reason_for_change` — VIDINIS, telemetrija pagrįstas (logams / įrodymui). `narrator_instruction`
  — KLIENTUI skirtas tiltelis. Atskiri laukai, atskiros paskirtys.
- `disambiguate` čia = tavo `REDIRECT_CHECK_DEVICE` (nukreipti į teisingą įrenginį).

### Leistina `next_action` aibė
| action | reikšmė | vykdo |
|---|---|---|
| `ask` | užduok klausimą | narratorius |
| `disambiguate` | patikslink kurį įrenginį / ką turi omeny | narratorius |
| `instruct` | duok vieną instrukciją | narratorius |
| `wait` | palauk (klientas dar daro) | — (laiko žingsnį) |
| `reread_telemetry` | perskaityk telemetriją iš naujo | 🔒 tool |
| `verify` | patikrink ar atsistatė | narratorius + 🔒 telemetrija |
| `propose_fix` | siūlyk fix (bind/reset) | **🔒 VYKDO KODAS** |
| `pivot` | pakeisk hipotezę | sprendėjas (kito ciklo prior) |
| `escalate` | registruok gedimą | **🔒 VYKDO KODAS** |
| `close` | užbaik (išspręsta) | **🔒 VYKDO KODAS** |

---

## ④ VARTAI — validacija + saugiklis
🔒 enforcinimas · ⚙️ slenksčiai.

1. **Schema validacija** — `next_action` leistinoje aibėje? Ne → blokas + fallback.
2. **Cognitive Divergence, Action Convergence** — `current_hypothesis` gali būti LAISVAS
   string (peržengia verdict tree aibę: „klientas žiūri į kaimyno routerį", „painioja ONT
   su Wi-Fi"). Vartai tikrina TIK `next_action`. Nepažįstama hipotezė + `ask` → praleidžia.
   Nepažįstama hipotezė + saugos tool (`propose_fix`/`escalate`) → **ATMETA, reikalauja
   map'ingo.** Laisvas mąstymas, suvestas veiksmas.
3. **Autorizacija / saugumas** — `propose_fix`/`escalate`/`close` vykdo kodas su
   politikos patikra (identity gate, buto neatskleidimas, bind tik po patvirtinimo).
4. **Vidinis ciklas (thought loops)** — `Internal_Loop_Count <= 2` bekalbiams veiksmams
   (`reread_telemetry`, `pivot`), tada privalomai ėjimas su tekstu. 🔒 counteris — statomas iškart.
   - ⏳ *Priklausomybė (follow-up, ne dabar):* latencijos saugiklis — jei vidinis ciklas
     > 400 ms nuo STT, backchannel TTS filler („Tikrinu duomenis..."). Reikalauja **async
     telemetrijos** (dabar sinchr. DB) + **transporto filler'io** (dabar 1 atsakymas/ėjimą).
5. **Bailout counteris** (⚙️ slenksčiai):
   - `confidence < 0.4` tris žingsnius iš eilės, ARBA
   - `cycles_in_same_step > 3`
   → priverstinis `escalate` (demui `GENERIC_TICKET_CREATION` + mandagus „užregistravau,
     susisieks technikas"; `TRANSFER_TO_HUMAN` — kai bus operatorius).
   Agentas nekankina kliento be galo.

---

## ⑤ NARRATORIUS — vykdytojas + skaidrumas/tilteliai
📚 promptai + stilius. Mato TIK nuspręstą ėjimą (`narrator_instruction`) — izoliuota,
nemato ateities žingsnių, nespėlioja maršruto. Grąžina tekstą klientui.

### Skaidrumo / tiltelio taisyklės (📚, statoma DABAR — pokalbio kontrakto pratęsimas)
1. **Hipotezės kaita = privalomas paaiškinimas.** Jei `hypothesis_changed == true`,
   narratorius įterpia vieną sakinį apie naują įtarimą („Įtariu, kad...", „Kadangi minėjote
   X, patikrinkime Y...").
2. **Explicit Transition.** Niekada neužduok klausimo B neatsakęs / neatmetęs A konteksto.
   - BLOGAI: klientas „dega raudona LOS" → agentas staiga „laidu ar Wi-Fi?"
   - GERAI: „Supratau. Sistema rodo, kad ryšys iki namų ateina tvarkingai. Įtariu, kad
     žiūrite į šviesolaidžio dėžutę, ne Wi-Fi stotelę. Pažiūrėkim į didesnį įrenginį su
     antenomis — kokios lemputės ant jo?"
3. **Tylos eliminavimas.** Bet koks veiksmas > 1 s (telemetrija, API) pre-emptinamas trumpa
   fraze. ⏳ *mechanika = follow-up (async telemetrija + mid-turn TTS).*

### Filler'io saugiklis (KRITIŠKA)
Filler'is, ištartas PRIEŠ galutinį sprendimą, PRIVALO būti **krypties-neutralus**
(„Sekundėlę, tikrinu duomenis...") — niekada neužbėgantis už hipotezės. Kryptį atskleidžia
tik PO to, sekančiame sakinyje. Antraip agentas apsimeluoja, jei perskaityta telemetrija
paneigia kryptį.

### Latencijos maskavimas (⏳ follow-up, ne pirmam buildui)
„Kalbėk-tada-gauk": ① filler (neutralus TTS) → ② fone async telemetrija/sprendimas kol TTS
groja (~1.5–2 s) → ③ galutinis sakinys. Reikalauja async telemetrijos + mid-turn TTS.
**Shadow mode pradžioje NEKALBA klientui — tad filler'iai pirmam buildui nereikalingi;**
svarbūs tik cut-over momentu.

---

## Conflict Matrix (📚 sprendėjo žinios, .md)
Su **fakto autoritetu** — kas laimi konfliktą:
- **Telemetrija laimi** linijos/sesijų faktams (LOS, port state, active_sessions) — klientas jų nemato.
- **Klientas laimi** fiziniams-kambario faktams, kurių telemetrija nemato (į kurią dėžutę žiūri, ar įkišo kabelį).

| Klientas sako | Telemetrija | Autoritetas | Taktika |
|---|---|---|---|
| „neveikia niekas" | `active_sessions > 0` | telemetrija | švelnus patikslinimas („matau kitus įrenginius siunčia duomenis...") |
| „dega raudonai" | `LOS = true` | sutampa | tikra avarija → registruoti |
| „nedega lemputės" | port up, įrenginys matomas | mišru — klientas mato kambarį | įsitikink KURĮ įrenginį (ne aklai „miręs routeris") |
| „keičiau routerį" | `foreign_mac` | sutampa | patvirtinta → bind |
| „nieko nekeičiau" | `foreign_mac` | konfliktas | persiklausk PRIEŠ bind (kaimyno įrenginys? mesh? pamiršo?) |

---

## Kas NEsikeičia
🔒 Tool'ai, telemetrijos skaitymas, STT/TTS/transportas, router, checkpointer.
🔒 Saugos veiksmų vykdymas (bind/ticket/close). 🔒 Autorizacija, buto neatskleidimas.

## Eval harness — PRIVALOMA prieš pradedant (du lygiai)
Mąstymui persikėlus į žinias, unit testai nedengia.
- **Golden Dataset (CI/CD)** — fiksuoti scenarijai (9 + tavo rasti bug'ai). Bėga po
  KIEKVIENO `.md`/kodo pakeitimo. Sekundės, 100% deterministiška. Kietas vertinimas:
  verdiktas / veiksmas / žingsnis. Tikrina ar nesulaužyta bazinė logika.
- **LLM-aktorius (fuzzing / adversarial)** — bėga periodiškai (naktinis build / prieš
  shadow). LLM gauna personažą („irzlus senjoras, netaisyklinga lietuvių, neteisingai
  vadina lemputes") ir bando išvesti sprendėją iš pusiausvyros. Naujos klaidos →
  nauji fiksuoti scenarijai. LLM-as-judge kokybei (kontrakto laikymasis).

## Migracija — Shadow Mode
Neišraunam stuburo. Sprendėją auginam ant viršaus **viena kryptimi pirma** (miręs
routeris/tiltas).

- Garsas → STT → **splitter**: `WALKER` (master) atsako klientui; `Sprendėjas` (shadow)
  lygiagrečiai priima savo sprendimą.
- Shadow sprendimai rašomi kaip `shadow_decision` event į **esamą [JsonlFileTracer]**
  (ne BigQuery — jos nėra; BigQuery tik jei skalė augs).
- **Cut-over kriterijai** (100 realių skambučių): 0 kritinių saugos pažeidimų IR
  sutapimas su walker matuojamas automatiškai. **Nesutapimai — vertingiausias signalas** —
  reikalauja žmogaus/LLM-judge peržiūros (ten sprendėjas arba protingesnis, arba klysta),
  ne vien procento. Praėjus → `miręs-routeris` kryptis perjungiama tiesiogiai.

## Priklausomybės, kurių DABAR nėra (follow-up, nestabdo dizaino)
- **Async telemetrija (<150ms)** — dabar sinchroninis DB kvietimas.
- **Backchannel TTS filler** — transportas dabar duoda 1 atsakymą/ėjimą.
- **Žmogaus perjungimas** (`TRANSFER_TO_HUMAN`) — dabar tik `create_ticket`.
Šie reikalingi #2 latencijos saugikliui ir pilnam bailout'ui; iki tol — loop cap + ticket.
```

---

## Agento elgesio kontraktas (mąstantis agentas)

Kaip agentas turi elgtis SPRĘSDAMAS — nepriklausomai nuo gedimo. Tikslas: **mąstantis
agentas, kurio kryptis (kaip/kada elgtis) lengvai keičiama per domeno žinias.** Kiekvienas
elgesys turi aiškią vietą, kur nustatomas — todėl derinimas yra failo redagavimas.

| # | Elgesys | Kur nustatoma | Būsena |
|---|---|---|---|
| 1 | **Suprasti KODĖL skambina** (kokia problema) | `problems.triggers` manifeste + klasifikatorius | ✅ |
| 2 | **Išsiaiškinti priežastis** (telemetrija + dialogas) | verdict + solverio hipotezė/žinios | ✅ (interpretacija dar kode) |
| 3 | **Pašalinti priežastį, jei gali** | `propose_fix`→bind/reset (vykdo kodas) | ✅ |
| 4 | **Mąstyti garsiai + paaiškinti KĄ tikrina ir KODĖL** — klientas iškart supranta ką ir kokiu tikslu | `consultation.md` 1–3 + solverio `narrator_instruction` | ✅ |
| 5 | **Paaiškinti priežastį** — kodėl nėra paslaugos / kodėl dabar negali padėti | `consultation.md` 4 + inform playbook'ai | ✅ |
| 6 | **Vienodas tempas, viena mintis** | `consultation.md` 5 | ✅ |
| 7 | **Tiltelis keičiant įtarimą** („kadangi minėjote X, tikrinam Y") | `consultation.md` 6 | ✅ |
| 8 | **Telemetrija ↔ klientas prieštaravimas → persiklausti** | `consultation.md` 7 + conflict matrix (fakto autoritetas) | ✅ |
| 9 | **Grąžinti prie esmės, kai klientas nukrypsta** | *(NAUJA — pridėti į kontraktą + solverio veiksmą)* | ⏳ |
| 10 | **Laikinis prieštaravimas** — klientas anksčiau sakė X, dabar Y → „sakėte X, dabar Y — kaip iš tikrųjų?" | *(NAUJA — kontraktas + solveris skaito dialogo istoriją)* | ⏳ |

### 9. Grąžinimas prie esmės (NAUJA)
Kai klientas nukrypsta (kalba apie kitą dalyką, klausia nesusijusio), agentas **mandagiai
patvirtina, tada grąžina** prie dabartinio žingsnio: „Suprantu. Grįžkim prie interneto —
ar dega lemputė?" Solverio veiksmas: naujas `redirect`/`refocus` (arba `ask` su tokia
instrukcija). Nenutraukia grubiai, bet ir nenuklysta kartu.

### 10. Laikinis prieštaravimas — klientas ↔ klientas laike (NAUJA, svarbu)
Skiriasi nuo #8 (telemetrija↔klientas). Čia klientas PATS prieštarauja sau tarp ėjimų:
- **Situacijos skiriasi:** (a) suklydo, tada pataisė teisingai; (b) sakė teisingai, tada
  supainiojo; (c) tikra būsena pasikeitė (perkrovė → dabar dega). Agentas NEŽINO kurios.
- **Elgesys:** NEsirinkti tyliai. Persiklausti aiškiai: **„Prieš tai sakėte, kad nedega, o
  dabar sakote, kad dega — kaip yra dabar?"** Tada tikėti paskutiniu PATVIRTINTU atsakymu.
- **Iš kur agentas tai mato:** solveris jau gauna `POKALBIS IKI ŠIOL` (dialogo istoriją) —
  reikia taisyklės, kad jis LYGINTŲ dabartinį atsakymą su ankstesniu tuo pačiu klausimu ir,
  radęs neatitikimą, rinktųsi `disambiguate`/`ask` (ne aklai keliautų toliau).
- Klasifikatorius jau turi `internally_inconsistent` (viename sakinyje); ČIA reikia
  **tarp-ėjimų** nuoseklumo (dialogo istorijoje).

### Kur tai gyvena (santrauka)
- **Ką sakyti / tonas / persiklausimo formuluotės** → `consultation.md` (📚, lengvai keiti).
- **Kada persiklausti / grąžinti / pripažinti prieštaravimą** → solverio žinios + conflict
  matrix (📚); solveris skaito dialogo istoriją ir telemetriją.
- **Ką LEIDŽIAMA daryti** (veiksmų aibė, saugumas) → vartai + politika (🔒/⚙️).

**Tad naujo elgesio pridėjimas ar krypties keitimas = kontrakto/žinių redagavimas**, ne
kodas — išskyrus naują VEIKSMĄ (pvz. `redirect`), kurį reikia vieną kartą įtraukti į
leistiną `next_action` aibę.

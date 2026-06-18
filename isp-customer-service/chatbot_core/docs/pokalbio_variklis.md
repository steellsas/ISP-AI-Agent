# Pokalbio variklis — slotų pildymas, politika, node'ai

> Kaip agentas veda pokalbį patikimai: vietoj vieno laisvo ReAct ciklo —
> **struktūruotas dialogo variklis** su eksplicitiniais slotais, deterministine
> politika ir fokusuotais node'ais. LLM tik *supranta* ir *kalba*; **sprendimus
> priima kodas**.
>
> Statusas: **DIZAINAS** (Phase 3.5, žingsnis 0). Kodo dar nėra — tai šaltinis,
> prieš liečiant kodą.
>
> Susiję: `docs/ROADMAP.md` Phase 3.5; `kliento_identifikacijos_dizainas.md`
> (hierarchinis pildymas, §8.2 `resolve_address` kontraktas); `pokalbio_valdymas.md`
> (turn-taking, barge-in); `stebejimo_dizainas.md` (trace).

---

## 1. Kodėl — esamos schemos problema

Gyvi balso skambučiai (`logs/sessions/20260618-*`) atskleidė **struktūrines**
ydas, kurių promptas neištaiso:

- garbled ėjimas **PERRAŠO** jau išspręstą adresą (092029: „Tilžės 60-7" → „TILŽĖ 610");
- LLM **HALUCINUOJA** `customer_id='1'` (091508);
- LLM **DIAGNOZUOJA** prieš identifikaciją;
- adreso **SPIRALĖ** (70→10→6→60), nes nėra tvirto sloto, kurį apsaugotų pasitikėjimas.

Šaknis = **variklis**, ne promptas. Dabar „atmintis" yra žinučių logas + plonas
faktų blokas; adreso `city/street/house/apartment` **niekur nėra atskirai** — jie
gyvena tik LLM kontekste. Štai kodėl vienas blogas ėjimas viską nuverčia.

---

## 2. Modelis — NLU → DialogState → Policy → NLG

Kiekvienas pokalbio ėjimas teka per keturis etapus:

```
STT (+ skaičių normalizavimas)
      │
      ▼
  [1] NLU            tekstas → slotų atnaujinimai (+ vietovardžiai)   ← LLM (tik kai reikia)
      │
      ▼
  [2] DialogState    sukaupia slotus su pasitikėjimu; niekada neprarandama
      │
      ▼
  [3] Policy         deterministinė: ko trūksta? tikslinti? ieškoti? gate? diagnozuoti?
      │
      ▼
  [4] NLG            atkartoja suprastą + klausia TIK trūkstamo                ← LLM (frazavimas)
      │
      ▼
  TTS (filler grojamas kol [1]/[3] dirba)
```

**Esmė:** LLM atsakingas tik už [1] supratimą ir [4] frazavimą. **[3] sprendimus
priima kodas** — todėl agentas nebeatidaro išspręsto adreso, nehalucinuoja id,
neskuba diagnozuoti.

---

## 3. Slotų schema (`DialogState`)

Tipizuota būsena (Pydantic). Kiekvienas adreso slotas turi **reikšmę,
pasitikėjimą ir būseną**, todėl politika gali atskirti „tvirtą" nuo „spėjamo".

```python
class SlotStatus(StrEnum):
    EMPTY = "empty"        # dar nepasakyta
    HEARD = "heard"        # išgirsta, bet nepatvirtinta DB (žemas pasitikėjimas)
    RESOLVED = "resolved"  # patvirtinta prieš registrą/DB (aukštas)
    CONFIRMED = "confirmed"  # klientas patvirtino balsu

class Slot(BaseModel):
    value: str | None = None
    confidence: float = 0.0     # 0..1 (iš fuzzy/normalizatoriaus/LLM)
    status: SlotStatus = SlotStatus.EMPTY

class DialogState(BaseModel):
    # Problema
    problem_type: str | None = None        # internet_down | internet_slow | tv | billing | ...
    # Adreso slotai
    city: Slot = Slot()
    street: Slot = Slot()
    house: Slot = Slot()
    apartment: Slot = Slot()
    account_code: Slot = Slot()
    # Identifikacija
    customer_id: str | None = None
    address_verified: bool = False
    # Skambučio kontekstas (kaip dabar)
    caller_phone: str = "unknown"
    phone_candidate: dict | None = None    # pre-flight, UNCONFIRMED
```

| Slotas | Tipas | Kaip užpildomas | Pasitikėjimo taisyklė |
|---|---|---|---|
| `problem_type` | enum/str | NLU klasifikacija (Router) | — |
| `city` | Slot | numanoma „Šiauliai" jei nepasakyta; registro fuzzy | recovery iš gatvės+namo (§4) |
| `street` | Slot | **registro fuzzy** (deterministinis), LLM tik segmentuoja | `RESOLVED` kai ≥0.9 unikalus; `HEARD` kai 0.55–0.9 |
| `house` | Slot | **normalizatorius** + tikrinama prieš gatvės namus | `RESOLVED` kai yra namų sąraše; naujas garbled ≠ perrašo `RESOLVED` |
| `apartment` | Slot | normalizatorius + butų sąrašas | `RESOLVED` kai sutampa |
| `account_code` | Slot | `find_customer(account_code)` | greičiausias kelias |
| `customer_id` | str | tik iš `resolve_address`/`find_customer` sėkmės | niekada nespėjamas |
| `address_verified` | bool | `True` tik po kliento „taip" arba kliento pasakyto adreso radimo | **ANCHOR RULE** |

**Apsauga nuo perrašymo:** `RESOLVED`/`CONFIRMED` sloto **nenuverčia** žemesnio
pasitikėjimo `HEARD` reikšmė — politika tokiu atveju **klausia patvirtinimo**, ne
priima (taiso 092029 „610" bug'ą).

---

## 4. NLU — Dual-Track (deterministika pirma, LLM tik kai reikia)

Geriausi balso botai nepasikliauja vien LLM adreso išgavimu — lietuviškos galūnės
ir skaičiai dviprasmiški. Todėl **reikšmes valdo deterministika, LLM tik
segmentuoja**.

**Track A — deterministinis (greitas, be LLM):**
1. `normalize_lt_numbers` (jau yra): „keturiasdešimt keturi" → „44".
2. n-gram fuzzy prieš `streets` registrą (`street_match_score`, jau yra) → gatvės kandidatas + pasitikėjimas.
3. likę skaičiai → namas/butas heuristika; tikrinama prieš gatvės namų sąrašą.
4. **Jei švaru** (vienas stiprus gatvės atitikmuo ≥0.9 + tikėtini skaičiai) → slotai užpildomi, **LLM praleidžiamas** (greičiau + jokios halucinacijos).

**Track B — LLM segmentacija (tik kai Track A dviprasmiškas / sudėtinga frazė):**
- Pvz. „Persikėliau iš Vilniaus į Šiaulius, dabar Tilžės keturiasdešimt keturi".
- LLM grąžina **griežtą JSON** (segmentaciją, ne reikšmes):
  ```json
  {"city": "...", "street": "...", "house": "...", "apartment": "...",
   "problem_type": "...", "affirmation": true, "negation": false}
  ```
- **Reikšmės vis tiek validuojamos deterministiškai**: gatvė per registrą,
  skaičiai per normalizatorių. LLM **niekada** neperduoda gatvės tiesiai — ją
  patvirtina `resolve_address`. Taip LLM **fiziškai negali** įvesti gatvės, kurios
  nėra DB.

> Pastaba: `city` recovery (kai išgirstas miestas ne mūsų, bet gatvė+namas
> identifikuoja vieną vietovę) jau įgyvendintas `resolve_address`
> (`_recover_city_by_street`, su namo apsauga).

---

## 5. Politikos state machine (deterministinė)

Lentelė kaip verdiktų medis — duota slotų būsena → kitas veiksmas. Jokio LLM
sprendimo; LLM tik suformuluoja pasirinktą veiksmą (NLG).

| Sąlyga | Veiksmas |
|---|---|
| `problem_type` nežinomas | klasifikuoti / paklausti problemos |
| `address_verified == False` **ir** `phone_candidate` yra, slotai tušti | siūlyti pre-flight adresą patvirtinimui („Ar dėl … problema?") |
| `street` `EMPTY` | klausti gatvės (atkartoti bet kokį girdėtą fragmentą) |
| `street` yra, `house` `EMPTY` | patvirtinti gatvę + klausti namo |
| užtenka slotų → kviesti `resolve_address`; **nerado lygio** | perklausti TIK suklydusį lygį, atkartojant girdėtą reikšmę |
| `resolve_address` grąžino vieną sutartį (success) | echo-confirm adresą pirmyn-judančiu klausimu („Radau … Ar šiuo adresu neveikia internetas?") |
| kelios sutartys | klausti buto numerio / pavardės (be PII nutekėjimo) |
| klientas patvirtino („taip"/garbled teigiamas) | `address_verified = True`; `customer_id` iš rezultato |
| `address_verified == True` | maršrutas į **Diagnosis(problem_type)** |

### Tool-access GATE (deterministinis saugiklis)
Kol `address_verified == False`:
- **leidžiami**: `resolve_address`, `find_customer`, `check_outages` (pre-id);
- **blokuojami**: `diagnose_connection`, `update_mac`, `reset_port`,
  `create_ticket`.

Tai užmuša „diagnozuoja per anksti" ir „halucinuoja id" **iš principo** —
nepriklauso nuo prompto gerumo. *(Vertę duoda net be LangGraph.)*

---

## 6. Node'ai (LangGraph target)

Vienas grafas, tipizuota būsena (`DialogState`), `MemorySaver` checkpointer
(in-RAM; ne Redis/Postgres — to nereikia).

- **RouterNode** — klasifikuoja `problem_type` ir maršrutizuoja.
- **AddressValidationNode** (Režimas A) — slotų pildymas + gate. **Problemai-
  agnostiškas** — vienas visiems scenarijams.
- **DiagnosisNode** (Režimas B) — **per-problem-type strategijų registras**,
  visi dalijasi „signalai → verdiktas → veiksmas" forma. `diagnose_connection` =
  pirmoji strategija.

```
        [ Router ]
            │ problem_type
            ▼
   address_verified?
     ├── False ──► [ AddressValidation ]  (slotai + gate)
     │                   │ verified
     └── True ──────────►├──► [ Diagnosis: internet_down ]   ← diagnose_connection
                         ├──► [ Diagnosis: internet_slow ]
                         ├──► [ Diagnosis: tv ]
                         └──► [ Diagnosis: billing ]
```

---

## 7. Problemai-agnostiškas griaučių kelias

Visi scenarijai (neveikia internetas / lėtas / TV / sąskaita / …) turi **tą patį**
kelią:

```
identifikacija (BENDRA) → RAG/duomenų paėmimas → diagnozė → sprendimas
```

Skiriasi **tik diagnozės strategija ir RAG žinios** pagal `problem_type`.
**Naujas gedimo tipas = nauja diagnozės strategija + KB turinys**; identifikacija
ir branduolys **neliečiami**.

---

## 8. Forward-compat principai + korekcijos

**Principai (užkoduojami iš karto):**
1. **Įrankiai gali būti lėti** — SQLite tik testams; reali DB/OSS gali lėtinti.
   Įrankių kvietimai timeout- ir filler-ready; tikras async — Phase 5.
2. **Streaming TTS iš dizaino** — TTS portas yra streaming sąsaja dabar; gTTS =
   ne-streaming adapteris už jo; variklį keičiam neliesdami branduolio.
3. **Būsena augs** — dinaminė būsena **žinutėje gale** (ne system prompt'e), +
   būsenos santraukos žingsnis kai slotai/istorija išauga.
4. **Concurrency-ready (tolima ateitis)** — jokio globalaus mutuojamo state;
   node'ai gryni `(state) -> state`; checkpointer pagal `thread_id` (vienas state
   skambučiui).

**Korekcijos (iš trace įrodymų):**
- Latencija = **LLM + audio**, ne DB (įrankiai 1–13 ms) → gate'as = korektiškumui,
  filler maskuoja **LLM**, ne DB. **Neoptimizuojam DB I/O.**
- Fokusuoti node'ai = **tikslumas/kontrolė**, ne dramatiškas greitis (LLM round-trip
  grindys dominuoja).
- Token→TTS streaming reikalauja streaming variklio (gTTS blokuoja); filler — ne, jis pirma.
- Faktų reinjekcija į **system prompt griauna prompt cache** (tikras kaštas, ne
  token'ai) → stabilus system prompt + dinaminė būsena žinutėje gale.

---

## 9. Architektūra: esama vs target

**Esama** (nubraižyta): transportai → `AgentSession` → vienas `ReactAgent` ciklas
(LLM ↔ įrankiai), atmintis = žinučių logas + faktų blokas.

**Target:**

```
[ Transportai: CLI / Balsas (FastRTC) / Streamlit ]
        │  handle_turn(text)
        ▼
[ AgentSession ]  (stabili sąsaja — nepakeičiama)
        │  async run_step()
        ▼
[ LangGraph: Router → AddressValidation → Diagnosis registras ]
        │            ▲                │
        ▼            │ skaito/rašo     ▼
[ DialogState (slotai, tipizuota) + MemorySaver ]
        │
        ▼
[ NLG ] → [ TTS portas (streaming + audio kešas) ] → klientas
            (filler grojamas kol LLM/policy dirba)
```

`AgentSession` **lieka ta pati sąsaja** — refaktoras vyksta už jos.

---

## 10. Build order (Phase 3.5) + papildymai

- **0.** Šis dokumentas. ✅
- **1.1** Prompt-cache fix: stabilus system prompt + dinaminė būsena žinutėje gale.
- **1.2** Eksplicitiniai slotai (`DialogState`); `resolve_address` rašo į slotus.
- **1.3** Tool-access gate (§5) — deterministinis, **net be LangGraph**.
- **1.4** NLU **Dual-Track** (§4): deterministika valdo reikšmes, LLM tik segmentuoja.
- **2.1** TTS streaming portas + **audio kešas** (statinės frazės pre-render → 0ms;
  filler = kešo klientas; veikia tik FIKSUOTOMS frazėms, LLM-atsakymai sintezuojami).
- **2.2** Instant filler `AgentSession` sluoksnyje.
- **3.** LangGraph migracija (node'ai + `MemorySaver` + LangSmith).

**Perkelta į Phase 5 (realtime/telefonija):** async generator + token streaming;
fast-path/slow-path split; **AEC + asimetrinis barge-in filtras** (backchannel
„aha/taip" euristika atskiria nuo tikro pertraukimo — reikalauja AEC pirma).

---

## 11. Kas lieka nepaliesta

Verdiktų medis (`diagnose_connection`), `resolve_address` (tampa **slotų
validatoriumi**), 10-įrankių registras (tampa Diagnosis node turiniu), Tracer
(praplečiam node'ams), seed pasaulis, esami **259 testai**.

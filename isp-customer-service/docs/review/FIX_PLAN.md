# Taisymų planas (po peržiūros 2026-09-17/18)

Šaltinis: [PERZIURA.md](PERZIURA.md) — radiniai A–AU, principai P-1…P-9,
tikslinė architektūra (§3) ir bangų santrauka (§4). Šis dokumentas — darbo
planas: kas, kur, kaip tikrinama, ir eigos žurnalas.

## Darbo taisyklės

- Kiekviena banga — atskira šaka nuo `develop` (`fix/wave-N…`); commit'ai EN;
  push + compare URL, PR kuria Andrius.
- Atskiro vertinimo rinkinio PRIEŠ keitimus nekuriame: keičiame iš karto ir
  rašome **gebėjimų testus** (P-9, be LLM, atvejai lentelėse, prieš kontraktą).
- Apsauga: esami vienetų testai + esamas eval (33 scen.) — paleidžiami bangos
  pradžioje ir pabaigoje. Senieji testai, tikrinantys pakeičiamą vidų, trinami /
  perrašomi TAME PAČIAME pakeitime.
- Banga baigiama pilnai (kodas + testai + eval) — tik tada gyvas testavimas.
- Bangos pabaigoje — įrašas „Eigos žurnale" (apačioje).

## Bangos

```
BANGA 0  greiti taisymai ─ lygiagrečiai, maži atskiri pakeitimai
   │
BANGA 1  F1 grynas decide ─ nuosekliai, pamatas visam kitam
   │
   ├──► 2a  Perception (+ analyst per inbox, semantinis endpoint)
   ├──► 2b  Promptai pagal įgūdį + validatoriai          ← lygiagrečiai
   └──► 2c  Įrankių manifestai + gateway (P-7)
            │
BANGA 3  Case + kortelė v2 + moduliai + įrangos katalogas (P-6, P-8)
   │
BANGA 4  lėtas internetas + TV tik failais + RAG atviriems klausimams
   │
BANGA 5  valymas
            … vėliau: 11 lokalūs modeliai (Piper, LLM, embeddings) · 12 integracija
```

| Banga | Turinys | Radiniai | Priklauso nuo |
|---|---|---|---|
| 0 | Greiti taisymai ir matavimas (žr. žemiau) | C, B, L, AM, AC, AB, AL, S, X, E, AQ, AS | — |
| 1 | Grynas decide: close / register / bind / hang-up → `Action` per vieną gate; reply layer + backstop → decide (redecide ciklas); narrate tik kalba; vienas klausimų registras; perceive tik skaito | A, R, AF, T, J, Q | 0 |
| 2a | Vienas `Perception`: greitkelis, citatos prie faktų, faktų politika decide'e, analyst per inbox + trigeriai, semantinis endpoint, perception eval | G, H, K, AD, AE, AO | 1 |
| 2b | Promptai pagal įgūdį: branduolys + įgūdis + pavyzdžiai + ribota kortelė | Y, Z, AA, AN | 1 |
| 2c | Įrankių manifestai: capability portai, saugikliai, timeout / limitai / on_failure, fake adapteris | P-7, V, W | 1 |
| 3 | Case, keli kandidatai, vienas sprendėjas; kortelė v2 + konverteris; moduliai; įrangos katalogas modelis → šeima → bazinė; verdict medis → faktai | N, O, P, U, AG, AH, AI | 2a, 2c |
| 4 | Lėtas internetas + TV tik failais; RAG atviriems klausimams; pavyzdžių bankas | AJ, AK | 3, 2b |
| 5 | Valymas: vėliavos, seni keliai, pavadinimai, LT/EN raktai, testų žemėlapis | E, F5 | 4 |

Detalus 1–5 bangų planas rašomas kiekvienos bangos pradžioje.

---

## Banga 0 — greiti taisymai (šaka `fix/wave-0`)

Kiekvienas punktas — atskiras commit'as su testu.

| # | Kas | Kur | Testas (P-9) |
|---|---|---|---|
| W0-1 | **C: analyst signalai per inbox.** `analyst_next` nebetaiko signalų snapshot'ui — visi signalai keliauja per inbox į kito ėjimo grafo įvestį ir pritaikomi graph būsenai ėjimo pradžioje (checkpoint'e). | `agent/session.py`, `agent/graph_v2/state.py` (`TurnScratch`), `agent/perceive/node.py`, `agent/analyst/node.py` | Atkūrimo testas: async analyst → secondary_problem / contradiction atsiranda checkpoint'e po kito ėjimo |
| W0-2 | **B: visi LLM kvietimai trace'e.** Kiekvienas kvietimas (perception, classifier, problem classifier, ticket reader, solver, analyst, speak) → `llm` įvykis su `role` + `llm_stats`. | `services/llm/client.py` (stebėtojo kablys), `agent/session.py`, kvietimo vietos (`role=`) | Fake LLM: kiekvienas vaidmuo palieka `llm` įvykį su role |
| W0-3 | **L: testų trace'ai ne į `logs/sessions`.** | `chatbot_core/tests/conftest.py` | Testas: tracer rašo į TRACE_DIR |
| W0-4 | **AM: `turn_timing` įvykis** — viename įvykyje: ASR, pirmas agento tokenas, pirmas sakinys, pirmas garsas (ms nuo ėjimo pradžios). | `agent/voice_pipeline.py` | Fake ASR/TTS/agent: įvykis su visais laukais, didėjanti tvarka |
| W0-5 | **AC: `max_tokens` naratoriui ≈150.** | `agent/config.py` | Konfigūracijos testas |
| W0-6 | **AB: atsakymo sargas srauto metu** — generacija sustabdoma po pirmo sakinio su „?" ir pasiekus ilgio ribą sakinio pabaigoje; tai, kas neištarta, negeneruojama ir neįrašoma. | `agent/speak/node.py` (+ `limits.yaml`) | Lentelė: token srautas → ištartas tekstas (2 klausimai → 1; ilgas → nukirpta sakinio gale; vienas ilgas sakinys → nekerpama) |
| W0-7 | **AL: scripted frazių TTS iš anksto** — paleidžiant voice, fone sugeneruojamos frazės be kintamųjų (disko cache), kad mechaniniai ėjimai nelauktų TTS. | `adapters/tts/edge_tts.py`, `app/voice.py` / `app/main.py` | Fake TTS: frazė sugeneruota iš anksto → sintezė iš cache (0 kvietimų) |
| W0-8 | **S/X: ReAct palikimo trynimas** — `executor_flow.execute_tool_calls`, `close_case` įrankis ir jo gateway sargas, nenaudojami LLM įrankių aprašai. Įrankių katalogas perkuriamas 2c bangoje. | `agent/executor_flow.py`, `agent/tools.py`, `agent/tooling/gateway.py`, `agent/execute/observe.py`, susiję testai | Esami testai praeina; negyvo kodo testai pašalinami |
| W0-9 | **E: pasenę komentarai** (`handle_turn_stream` „SUBGRAPH"). | `agent/session.py` | — |
| W0-10 | **AQ/AS: eval voice režimas ir stabilumas** — `--voice` (async analyst tarp ėjimų, kaip balse) ir `--runs k` (kiekvienas scenarijus k kartų, stabilumo ataskaita). | `agent/eval/run_eval.py`, eval README | Paleidimas: ataskaitoje stabilumas per scenarijų |

**Bangos 0 baigimo kriterijai:** visi vienetų testai žali; eval (33 scen.) ne
blogesnis už baseline; `--voice` režimu praeina; C atkūrimo testas žalias;
trace'e matomi visi LLM kvietimai ir `turn_timing`.

---

## Eigos žurnalas

| Data | Banga | Kas padaryta | Testai / eval | Liko |
|---|---|---|---|---|
| 2026-09-18 | — | Peržiūra 0–10 baigta, planas sudarytas; šaka `fix/wave-0` | vienetų testai: 1242 passed | Banga 0 |

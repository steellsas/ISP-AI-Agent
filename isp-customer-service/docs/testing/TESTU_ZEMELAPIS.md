# Testų žemėlapis (sutarta 2026-08-31, peržiūra vyksta pažingsniui; atnaujinta 2026-09-17 po refaktoringo M0–M6)

Tikslas (Andrius): žinoti, kas KĄ tikrina; nebe kurti besidubliuojančių
testų; stambūs pokalbio lygio patikrinimai („supratimas veikia,
identifikacija veikia, tiketas veikia, užbaigimas veikia") + smulkūs vieno
funkcionalumo testai — kiekvienam faktui VIENA vieta.

Būsena 2026-09-17 (`refactor/single-engine`): **65 testų failai**
(`chatbot_core/tests/test_*.py`; atskiro šakninio `tests/` katalogo nėra),
**1242 testai** (`uv run pytest --collect-only -q`); eval **33 scenarijai**
(`chatbot_core/src/agent/eval/scenarios.json`), pilnas paleidimas — **~178
čekiai**. Čekių skaičius auga su kiekvienu scenarijumi: +2 visada
(`contact_record` ir `reply_len`) + po vieną už kiekvieną `expect` raktą
(`verdict_in`, `disposition` ≠ `any`, `identified`, `reply_any`, `reply_none`,
`record_outcome`) + po vieną už kiekvieną `tool_used` įrašą. (Peržiūros
pradžioje 2026-08-31 buvo 37 failai, 933 testai, 11 scenarijų / 44 čekiai.)

Variklis vienas: LangGraph grafas `perceive → decide → execute → narrate`
(`agent/graph_v2/graph.py`; `narrate` kalba per `agent/speak/`), viena būsena
`GraphState`, kiekvienas ėjimas — vienas `TurnPlan`, kiekvienas skambutis
palieka kontakto įrašą (`agent/call_record/`).

> **2026-10-22 (ROADMAP 3.4a):** visi testai suskirstyti **pagal sritis ir funkcijas** — kiekviena
> sritis yra aplankas `chatbot_core/tests/<sritis>/`, kiekvienas failas — viena funkcija. Istoriniai
> mišrūs failai (`test_agent`, `test_live_*`, `test_v3_stage3*`, `test_wave9/10`, `test_fault_packs`,
> `test_identify_first`, `test_without_the_model`) išskaidyti po testą į jų funkcijas; testų kodas
> nepakeistas. Kaip rašyti ir skaityti: [TESTAI_PAGAL_FUNKCIJAS.md](TESTAI_PAGAL_FUNKCIJAS.md).

## Sritys

| Aplankas | Sritis | Paleisti | Testų | Funkcijos (failai) |
|---|---|---|---|---|
| `identification/` | **Identifikacija** | `-m identification` | 269 | Paieška pagal numerį, Adreso supratimas, Adreso atmintis, Vietovės paieška, Gatvės paieška, Neaiški gatvė, Namo paieška, Buto paieška, Kelios sutartys name, Abonento kodas, Patvirtinimas, Kas skambina, Kai adreso nėra, Adreso keitimas, Nustatymai, Visa fazė |
| `problem/` | **Problema** | `-m problem` | 131 | Problemos klasifikavimas, Problemos ir simptomų skaitymas, Ketinimai, Pagrindinė problema, Anamnezė, Visa fazė |
| `understanding/` | **Supratimas** | `-m understanding` | 240 | Supratimas per modelį, Vienas skaitymas per ėjimą, Suvokimo sujungimas, Skaitymas be modelio, Atsakymų skaitymas, Atsakymų detektoriai, Detektorių glosos, Analitiko signalai, Patikslinti, ne spėti |
| `diagnosis/` | **Tyrimas** | `-m diagnosis` | 408 | Telemetrija kaip faktai, Linijos skaitymas, Kortelės, Galimi gedimai, Kitas žingsnis, Gedimo kelias, Moduliai, Įranga, Konkretūs gedimai, Paslaugų profilis, Atsisakytas žingsnis, Kantrus vedimas, Nuotoliniai veiksmai, Žingsnių serveris, Informavimas (skola, avarija), Klientas ne namie, Atsakymai žingsniuose, Visa fazė |
| `knowledge/` | **Žinios** | `-m knowledge` | 118 | Žinių poreikis, Žinių priminimas, Žinių bazė, Paieškos sąsaja, Qdrant indeksas |
| `ticket/` | **Tiketas** | `-m ticket` | 88 | Kontaktų dialogas, Registracijos priežastys, Prašymai, Atviri tiketai, Visa fazė |
| `closing/` | **Pabaiga** | `-m closing` | 119 | Uždarymas, Uždarymo taisyklės, Viena uždarymo vieta, Pabaiga balse, Kontakto įrašas, Skambučio santrauka, Atsisveikinimo ir sutikimo skaitymas |
| `speaking/` | **Kalba** | `-m speaking` | 165 | Kalbėtojas, Atsakymo sargai, Promptai, Vienas skill per atsakymą, Istorija, Kartojimo sargas, Pokalbio kokybė, Pokalbio sluoksnis, Promptas pagal fazę, Kalbos klaidos, Adreso tarimas, Rašyti žodžiai be modelio |
| `voice/` | **Balsas** | `-m voice` | 161 | ASR šališkumas, Balso adapteriai, Pertraukimai, Ką išgirdo klientas, Piper, Piper procesai, Paruoštos frazės, ASR teksto normalizavimas, Privaloma informacija, Generavimo stabdymas |
| `engine/` | **Variklis** | `-m engine` | 58 | Grafas, Būsena, Decide ciklas, Taisyklių tvarka, Plano vartai, Fazės, Ėjimo įvykiai, Konfigūracija |
| `tools/` | **Įrankiai** | `-m tools` | 100 | CRM ir tinklo įrankiai, Įrankių vartai, Prieiga iki identifikacijos, Manifestai, Kai sistema neatsako, Duomenų bazė |
| `contract/` | **Žinių failai** | `-m contract` | 27 | Schemos, Įkėlimas, Ribos, Frazės (locale) |
| `llm/` | **LLM** | `-m llm` | 33 | Atsarginis modelis, Kvietimų stebėjimas, Biudžetas, Srautas |
| `observe/` | **Stebėsena** | `-m observe` | 105 | API, Žurnalas (trace), Asmens duomenys, Kodėl taip, Skambučių suvestinė, Dashboard |

Po paleidimo ataskaita rodo Sritis → Funkcija → ✓/✗; paleidus vieną sritį (`-m identification`) —
ir žinomas spragas.

## Piramidė

| Sluoksnis | Kas garantuojama | Kur gyvena |
|---|---|---|
| EVAL (pokalbio lygis) | pilni pokalbiai su tikru LLM: supratimas, identifikacija, sprendimas, tiketas, užbaigimas, kontakto įrašas | `eval/scenarios.json` (S/I/D/R/T/U/G/A/X serijos) |
| Fazė | visa fazė per tikrą grafą, kalbantis LLM imituotas (`call` / `identified` fiktyvai) | `identification/test_phase.py`, `problem/test_phase.py`, `diagnosis/test_phase.py`, `ticket/test_phase.py`; kitoms fazėms — 3.4b |
| Funkcija | vienas gebėjimas, variantai lentele | srities aplankai (žr. aukščiau) |

## Taisyklės

1. **Vienas faktas — viena funkcija.** Pvz., identifikacijos variantai — TIK
   `tests/identification/` (+ eval I1–I6). Visuose kituose testuose identifikacija = paruošta
   būsena (fiktyvas `identified`, arba `make_state()` / `make_runtime()`).
2. **Naujas testas — tik į savo funkcijos failą.** Jei funkcija faktą jau dengia — keičiamas
   esamas testas, ne kuriamas naujas. Naujas gebėjimas = naujas failas su `FUNCTION = "..."`.
3. **Žinoma spraga** — `xfail(strict=True, reason=...)`, ne ištrintas testas.

## Dar tvarkyti (3.4b)

- Kiekvienai sričiai: variantų lentelės ir visos fazės testai (kaip `identification/`), fazių
  pradžios fiktyvai (`diagnosed`, `ticket` ir t. t.).
- `engine/test_graph.py` — docstring'as ir pavadinimai dar seni („diagnosis subgraph", „walker").
- `understanding/test_perception_merge.py` — docstring'as mini „walker".
- `diagnosis/test_case_rule.py`, `identification/test_caller_name.py` — `_Tracer` ir importuojamas,
  ir apibrėžiamas (veikia, bet verta suvienodinti į vieną pagalbinį modulį).

## Žinių sluoksnis (RAG, E1–E4)

| Failas | Ką įrodo |
|---|---|
| `knowledge/test_knowledge_base.py` | dokumento sutartis: rūšis, raktai, filtras, skyriai, žingsniai |
| `knowledge/test_knowledge_recall.py` | **arbitras**: 68 klausimai kliento žodžiais, `hit@1`/`hit@2` ribos, kiekvienas dokumentas turi klausimų |
| `knowledge/test_knowledge_need.py` | agento **ribos**: ką atsisako ieškoti (tema, paskirtis, prietaisas, ne klausimas), konkretus įrenginys prieš bendrą, kortelės `knowledge_need` |
| `knowledge/test_retrieval_port.py` | saugyklos keitimo siūlė: per portą grąžinami TIE PATYS dokumentai |
| `knowledge/test_qdrant_index.py` | indeksas: *sparse* sandauga = leksinis balas, hibridas, filtrai, versijos, aliasai, modelio saugiklis, sveikata |

Klausimų rinkinys gyvena **prie žinių** (`src/rag/knowledge_base/_questions.yaml`), ne testuose —
tą patį failą skaito ir ingestijos kanarėlė, tad CI ir gamyba negali nesutarti, kas yra
„pakankamai gerai".

### Ko CI nepaleidžia — ir kodėl tai nėra skylė

GitHub paleidėjas neturi embedding'ų modelio ir į HuggingFace neina (`HF_HUB_OFFLINE=1`,
kad nekiltų 419/429 audra). Todėl **dvylika** `knowledge/test_qdrant_index.py` testų — tie, kuriems
reikia `dense` vektorių — ten **praleidžiami**, ir tai matosi santraukoje (`pytest -rs`):

```
SKIPPED tests/knowledge/test_qdrant_index.py:331: embedding modelis nepasiekiamas: OSError: ...
```

Iki 2026-09-28 jie krisdavo kaip **12 klaidų**, nors niekas nebuvo sugedę — `embeddings_or_skip()`
dabar tikrina tikru kėlimu ir praleidžia švariai. Praleistis sako tiesą (nepaleista), klaida sakė
netieSĄ (sugedo).

Kas CI vis tiek lieka apsaugota:

| Vis dar tikrinama be modelio | Kodėl to užtenka |
|---|---|
| *sparse* sandauga **lygi** leksiniam balui (24 iš 36 to failo testų) | jei Qdrant atsako kitaip nei failai, kalta ne semantika, o indeksas |
| `knowledge/test_knowledge_recall.py` — 68 klausimai, `hit@1`/`hit@2` ribos | rikiavimo kokybė |
| `knowledge/test_knowledge_need.py` — ribos ir atsisakymai | agentas neina ne į savo sritis |
| `knowledge/test_retrieval_port.py` | portas grąžina tuos pačius dokumentus |

**Jei norėsim hibridą tikrinti ir CI:** įdėti `actions/cache` į `~/.cache/huggingface`, prieš
testus vieną kartą parsisiųsti modelį ir nuimti `HF_HUB_OFFLINE`. Kaina — ~0,5 GB kešo ir kelių
minučių pirmas paleidimas; nauda — hibrido regresijos pagaunamos PR metu, o ne ranka. Sprendimas
Andriaus; kol kas hibridas tikrinamas lokaliai ir per eval'ą.

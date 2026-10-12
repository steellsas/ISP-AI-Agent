# Promptų ir LLM parametrų žurnalas (v3 6 etapas)

Kiekvienas prompto ar LLM parametro pakeitimas užrašomas čia: **ką** keičiame, **kodėl**, **kaip
matuojame** ir **koks rezultatas**. Andrius (2026-10-12): *„kiekvienam prompto koregavimui
pasirašysime, ką keičiame ir kodėl"*; kiekvieną žingsnį prieš keičiant aptariame.

## Kaip matuojama

```
uv run python src/agent/eval/run_eval.py --runs 3 --json ../logs/eval_<žingsnis>.json
uv run python src/agent/eval/metrics.py ../logs/eval_base.json --compare ../logs/eval_<žingsnis>.json
```

`metrics.py` iš eval ataskaitos ir trace'ų suskaičiuoja:

- LLM vaidmenims (suvokimas, kalbėjimas, analitikas): kvietimai, įeinantys / išeinantys tokenai,
  vėlavimo mediana ir p90;
- atsakymai: kiek parašė variklis, kiek LLM, ilgis (vidurkis / max);
- scenarijai: praėję visus paleidimus, **nestabilūs** (kartą praeina, kartą ne), krentantys visada;
- suvokimo stabilumas: tas pats kliento sakinys skirtinguose paleidimuose — kiek kartų perskaitytas
  skirtingai.

Terminai (Andrius, 2026-10-12): „maršrutizatorius" yra taisyklingas lietuviškas žodis, ne klaida.

## Žingsniai

| Žingsnis | Kas | Būsena |
|---|---|---|
| 6.0 | Matavimo pagrindas (`metrics.py`, eval ×3 dabartiniu kodu) | ✅ |
| 6c | Parametrai pagal vaidmenį | ✅ suvokimas stabilesnis 8 → 3 |
| 6a | Kalbėjimo promptas pagal fazę | bus aptarta |
| 6b | Suvokimo LLM nekviesti, kai atsakymą perskaitė skaitytuvas | bus aptarta |
| 6d | Lietuvių kalbos taisyklės ir terminai | bus aptarta |

---

### 6.0 Pagrindas (2026-10-12)

Kodas: develop po `fix/live-calls-1012`. Eval ×3 (`logs/eval_base.json`).

| Vaidmuo | Kvietimai | Įeina tok. | Išeina tok. | ms mediana | ms p90 |
|---|---|---|---|---|---|
| Suvokimas | 547 | 1 890 | 66 | 626 | 949 |
| Kalbėjimas | 541 | 2 508 | 49 | 465 | 670 |
| Analitikas | 207 | 827 | 14 | 312 | 606 |

- Atsakymai: 1 026 (variklis 485 / LLM 541), ilgis vidutiniškai 108 simb., max 271.
- Scenarijai: 39/40 praeina visus 3 paleidimus; nestabilių 0; visada krenta **I2** — Gemma rašo
  „nerodu" vietoj „nerandu" (kalbos klaida, 6d kandidatas), todėl patikra žodžio neranda.
- Suvokimas: **8 iš 182** sakinių skirtinguose paleidimuose perskaityti skirtingai.

---

### 6c Parametrai pagal vaidmenį (2026-10-12, Andrius pritarė)

| Vaidmuo | Buvo | Dabar | Kodėl |
|---|---|---|---|
| Suvokimas ir tiketo skaitytuvas (JSON: ką klientas pasakė, telefonas / laikas) | temperature 0.3 (numatyta), max_tokens 500 (numatyta) | **0**, **200** | Tai skaitymas, ne kūryba: su 0.3 tas pats sakinys kartais perskaitomas kitaip (eval S4: „Vis tiek nedega" kartą „laidas ištrauktas", kitą „neaišku"). Didžiausias matytas atsakymas 131 tok. — 200 palieka atsargą, bet nebeleidžia išsiplėsti |
| Kalbėjimas (ką girdi klientas) | 0.3, 150 | **0.2**, 150 | Mažiau atsitiktinių žodžių ir kalbos klaidų („lemputžių"), tonas lieka gyvas. Riba 150 jau tinkama |
| Analitikas (fone) | 0.2, 700 | nekeista | atsakymo laikui įtakos neturi |
| Klasifikatorius | 0, 150 | nekeista | jau tinkama |

Reikšmės — `knowledge/limits.yaml` (`perception_temperature`, `perception_max_tokens`,
`speak_temperature`), kad jas būtų galima keisti be kodo.

Laukiama: stabilesni eval rezultatai (mažiau nestabilių scenarijų ir skirtingai perskaitytų
sakinių), šiek tiek trumpesnis suvokimas. Rizika maža; blogiau — grąžinam.

**Rezultatas (eval ×3, `logs/eval_6c.json`, palyginta su pagrindu):**

| | Pagrindas | 6c |
|---|---|---|
| Suvokimas: tas pats sakinys perskaitytas skirtingai | **8 / 182** | **3 / 182** |
| Scenarijai, praėję visus 3 kartus | 39 / 40 | 38 / 40 |
| Nestabilūs | 0 | 2 — I2 (Gemma „nerodu", 6d) ir K1 (ilgis 1 iš 3) |
| Visada krentantys | 1 (I2) | 0 |
| Atsakymo ilgis vid. / max | 108 / 271 | 109 / 259 |
| Suvokimo vėlavimas med. / p90 | 626 / 949 ms | 691 / 1 002 ms |

- Pagrindinis tikslas pasiektas: suvokimo skaitymai **beveik trigubai stabilesni** (8 → 3).
- Vėlavimas +60 ms — ne dėl parametrų (temperatūra skaičiavimo nekeičia, tokenų tiek pat), o
  tiekėjo (Scaleway) svyravimas tarp paleidimų skirtingu paros metu.
- I2 iš „visada krenta" tapo „kartais praeina"; K1 — žinomas ilgio svyravimas (6a/6d).

Sprendimas: **paliekama** (laukia Andriaus patvirtinimo).

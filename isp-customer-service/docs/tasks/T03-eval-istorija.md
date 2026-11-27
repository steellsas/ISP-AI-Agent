# T03 — Eval istorija su versijomis

**Būsena:** retro · **Šaka:** `feat/eval-history` · **ROADMAP:** Stage 3 (P3 test loop)

## Tikslas
Kiekvienas eval paleidimas paliekamas su versija; matosi scenarijų nestabilumas ir kas pasikeitė tarp dviejų paleidimų.

## Kodėl
`chatbot_core/src/agent/eval/run_eval.py:456` rašo rezultatus tik su `--json`, be commit/modelio žymės. Paskutinė suvestinė `logs/eval_1111_fix2.json` (11-11, 48/50), nuo tada 42 commit'ai. `database/eval.sqlite` yra CRM fixture. Nestabilumas (I2_ident_wrong_house_corrected 24/61, S4b 44/61, X_dhcp_silent 51/61) neatskiriamas nuo regresijos (projekto peržiūra 2026-11-26, P0-3).

## Apimtis
- Daroma:
  - `run_eval.py`: po KIEKVIENO paleidimo prirašo vieną eilutę į `logs/eval/history.jsonl` (S2=A; patikrink, kad gitignored): laikas, `agent/versions.py` `call_versions()` (commit, žinių/frazių/promptų hash'ai, modeliai), argumentai (`--only`, `--runs`, `--voice`), kiekvieno scenarijaus × run rezultatas (checks pass/fail, `known_bug`), suma. `--json` lieka.
  - Naujas `eval/history.py` CLI: paskutinių N paleidimų suvestinė; scenarijų nestabilumo lentelė (praėjo / paleista); dviejų paleidimų palyginimas (kas sulūžo / pasitaisė).
  - S3: vienkartinis importas iš 25 senų `logs/eval_*.json` į istoriją (versija „unknown“, data iš failo mtime arba vardo).
  - `eval/README.md` pataisa: 50 scenarijų (ne 33), nutrūkusi nuoroda `docs/refactoring/baseline/README.md` → `docs/archive/refactoring/baseline/`; aprašyk istoriją ir `history.py`.
  - mypy `run_eval.py:127` (`Module "database" has no attribute "connection"`) – tik jei tai tikra klaida.
- Nedaroma: eval paleidimas (T04), CI vartai, stebėsenos puslapis.

## Atlikta, kai
- [x] testas su netikru paleidimu tikrina history eilutės formatą ir `history.py` išvestį (be LLM)
- [x] importas atliktas, nestabilumo lentelė rodo I2, S4b, X_dhcp_silent
- [ ] `uv run pytest` žalias, `ruff check` / `ruff format --check` švarūs
  (ruff švarus; pytest 2397 ✓, 1 ✗ – `test_real_edge_synthesis_smoke`, tikras edge-tts tinklo kvietimas grąžino 0 baitų, su T03 nesusijęs)

## Sprendimai eigoje
- **Formatas savo modulyje.** Eilutės formatą kuria ir skaito `eval/history.py` (`record_from_results`,
  `record_from_report`, `append`, `load`); `run_eval.py` tik jį kviečia. `history.py` – tik stdlib, be `agent` importų.
- **Istorijoje be check'ų `detail`.** Tik `{name: bool}` – detalės yra `--json` ir trace'e; eilutė lieka maža.
- **`--history PATH`** naujas `run_eval.py` argumentas (numatytas `logs/eval/history.jsonl`). Nepavykus įrašyti
  (OSError) – įspėjimas, ataskaita ir `--json` vis tiek išvedami. Nepavykus `call_versions()` – `{"code": code_version()}`.
- **`hard_fails`** skaičiuojamas kaip `run_eval.py` vartai: scenarijus su bent vienu kritusiu run'u, ne `known_bug`.
- **Importas:** 25 `logs/eval_*.json` → pagrindinio checkout'o `logs/eval/history.jsonl` (ten vyks T04 paleidimai);
  data iš mtime (vardai `6a`, `1111` metų/datos nepasako), `versions: {"code": "unknown"}`. `s4_full.json`, `s4d.json`
  neimportuoti (ne `eval_*`, po 1 scenarijų). Rezultatas: I2 24/61, S4b 44/61, X_dhcp_silent 51/61 – sutampa su peržiūra.
- **Testas `tests/observe/test_eval_history.py`** (sritis „Stebėsena“, funkcija „Eval istorija“) – nauja sritis
  reikalautų keisti `function_report.py` MARKS.
- **mypy `run_eval.py:129` – ne tikra klaida, kodas nekeistas.** Vykdant `database` = `shared/src/database`;
  jo `init_database()` nustato tą patį `_db_connection`, kurį grąžina `agent.tools.get_db()`, tad `_close_db()` uždaro
  teisingą jungtį. mypy iš projekto šaknies mato `database/` duomenų aplanką (namespace package be `connection`).
  Kitos 12 mypy klaidų `run_eval.py` buvo ir anksčiau; `history.py` – be klaidų.
- **Peržiūra (`/code-review high`), 7 radiniai; Andrius patvirtino taisyti 1–4:**
  1. `_when` atsarginė reikšmė `datetime.min.astimezone()` Windows'e meta OSError → `datetime.min` su UTC.
  2. Laikas be laiko juostos + su juosta → `TypeError` rūšiuojant → laikas be juostos skaitomas kaip vietinis.
  3. PowerShell neišskleidžia `logs/eval_*.json` → `import` šablonus išskleidžia pats, neradęs – įspėja.
  4. Versijų hash'ai buvo imami po paleidimo → dabar prieš scenarijus.
  Neatlikti (smulkūs): 5 importo dublių atpažinimas tik pagal failo vardą; 6 rezultato eilutė be `id`/`pass`
  nulaužia `flaky`/`diff`; 7 eval iš worktree rašo istoriją į worktree `logs/` (naudoti `--history`).

## Rezultatas
- Commit'ai: `9ac5642` užduotis, `7b17baf` istorija + `history.py` + testai + README, `b4dad81` peržiūros pataisos 1–4.
- Sujungta: PR #142 (`752849a`), 2026-11-26.
- Importuota 25 senų ataskaitų į pagrindinio checkout'o `logs/eval/history.jsonl`.
- Liko: peržiūros radiniai 5–7 (smulkūs); `test_real_edge_synthesis_smoke` krenta dėl tinklo (ne T03);
  pirmas versijuotas eval etalono paleidimas – nauja užduotis (T04 numeris atiteko kitai užduočiai).
- Retro: pamokos `docs/lessons.md` (PowerShell bandymas CLI įrankiams; importas ir jo naudojimas tame pačiame Edit'e).

## Darbo taisyklės
- Eigoje priimtus sprendimus užrašyk skiltyje „Sprendimai eigoje“. Jei testai nepraeina ar atsiranda kelios galimybės – sustok, pateik variantus su rekomendacija ir lauk.
- Nerašyk istorinių komentarų (datų, „fixed after…“).
- Pabaigoje: testai + `ruff check` / `ruff format --check` → commit (EN) → `/code-review high` šakos diff'ui. Radinius pateik Andriui; taisyk tik su jo pritarimu, pataisas commit'ink atskirai. Tada push tik su leidimu → duok compare URL (`https://github.com/steellsas/ISP-AI-Agent/compare/develop...<šaka>`) + EN PR title/description (su peržiūros rezultatu) → būsena `peržiūra` (užduoties failas ir README eilutė, tame pačiame PR). PR per `gh` nekurk.

# T03 — Eval istorija su versijomis

**Būsena:** vykdoma · **Šaka:** `feat/eval-history` · **ROADMAP:** Stage 3 (P3 test loop)

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
- [ ] testas su netikru paleidimu tikrina history eilutės formatą ir `history.py` išvestį (be LLM)
- [ ] importas atliktas, nestabilumo lentelė rodo I2, S4b, X_dhcp_silent
- [ ] `uv run pytest` žalias, `ruff check` / `ruff format --check` švarūs

## Sprendimai eigoje
(pildyk čia)

## Rezultatas
(commit'ai, compare URL, kas liko)

## Darbo taisyklės
- Eigoje priimtus sprendimus užrašyk skiltyje „Sprendimai eigoje“. Jei testai nepraeina ar atsiranda kelios galimybės – sustok, pateik variantus su rekomendacija ir lauk.
- Nerašyk istorinių komentarų (datų, „fixed after…“).
- Pabaigoje: testai + `ruff check` / `ruff format --check` → commit (EN) → `/code-review high` šakos diff'ui. Radinius pateik Andriui; taisyk tik su jo pritarimu, pataisas commit'ink atskirai. Tada push tik su leidimu → duok compare URL (`https://github.com/steellsas/ISP-AI-Agent/compare/develop...<šaka>`) + EN PR title/description (su peržiūros rezultatu) → būsena `peržiūra` (užduoties failas ir README eilutė, tame pačiame PR). PR per `gh` nekurk.

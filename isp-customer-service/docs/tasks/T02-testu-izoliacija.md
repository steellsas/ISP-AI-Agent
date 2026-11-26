# T02 — Testai neliečia repo failų

**Būsena:** vykdoma · **Šaka:** `fix/test-locale-isolation` · **ROADMAP:** Stage 3 (test loop)

## Tikslas
Joks testas nerašo į repo žinių/frazių failus; jei parašytų – testų sesija tai pagauna.

## Kodėl
`chatbot_core/tests/contract/test_loader.py:100-122` (fixture `phrases_file`, testas `test_revalidate_sees_a_phrase_added_since_startup`) rašo į tikrą `chatbot_core/src/agent/locales/lt/phrases.yaml`. Nutrauktas pytest paliko `probe_wave5`, ir tas pats testas dabar krenta („DID NOT RAISE LocaleError“). Kitas `git add -A` tai įcommitintų (projekto peržiūra 2026-11-26, P0-2).

## Apimtis
- Daroma:
  - `chatbot_core/src/agent/contract/locale.py:107`: `load_locale(language, root=LOCALES_DIR)` → `root: Path | None = None`, `root = root or LOCALES_DIR` (dabar numatytoji reikšmė užšąla apibrėžimo metu, todėl monkeypatch neveikia). Patikrink ir kitas vietas, kur `LOCALES_DIR` importuojamas pagal vardą (`contract/language.py:18`, `contract/schema.py:791`, `locale.py:220`). Elgsena produkcijoje nesikeičia.
  - Fixture kopijuoja `locales/` į `tmp_path` ir per `monkeypatch` nukreipia `LOCALES_DIR`; testas repo failo nebeliečia; po testo `loader.reload()` kaip dabar.
  - Autouse sesijos apsauga `chatbot_core/tests/conftest.py`: `locales/` ir `knowledge/` failų hash'ai pradžioje ir pabaigoje; skiriasi → aiški klaida (kuris failas pasikeitė).
  - Paieška: ar kiti testai rašo į repo failus (write_text/open(...,'w') į src/, database/ ir pan.) – rasti sutvarkyk ar užrašyk.
- Nedaroma: kiti testų pakeitimai.

## Atlikta, kai
- [ ] po pilno `uv run pytest` `git status` švarus
- [ ] apsauga tikrai krenta, jei testas pakeičia failą (vienkartinis patikrinimas aprašytas „Sprendimai eigoje“)
- [ ] testai žali, `ruff check` / `ruff format --check` švarūs (Edge TTS tinklo testas gali kristi – žinomas radinys #1, ne šios užduoties)

## Sprendimai eigoje
(pildyk čia)

## Rezultatas
(commit'ai, compare URL, kas liko)

## Darbo taisyklės
- Eigoje priimtus sprendimus užrašyk skiltyje „Sprendimai eigoje“. Jei testai nepraeina ar atsiranda kelios galimybės – sustok, pateik variantus su rekomendacija ir lauk.
- Nerašyk istorinių komentarų (datų, „fixed after…“).
- Pabaigoje: testai + `ruff check` / `ruff format --check` → commit (EN) → `/code-review high` šakos diff'ui. Radinius pateik Andriui; taisyk tik su jo pritarimu, pataisas commit'ink atskirai. Tada push tik su leidimu → duok compare URL (`https://github.com/steellsas/ISP-AI-Agent/compare/develop...<šaka>`) + EN PR title/description (su peržiūros rezultatu) → būsena `peržiūra` (užduoties failas ir README eilutė, tame pačiame PR). PR per `gh` nekurk.

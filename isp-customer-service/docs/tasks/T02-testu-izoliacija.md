# T02 — Testai neliečia repo failų

**Būsena:** peržiūra · **Šaka:** `fix/test-locale-isolation` · **ROADMAP:** Stage 3 (test loop)

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
- [x] po pilno `uv run pytest` `git status` švarus
- [x] apsauga tikrai krenta, jei testas pakeičia failą (vienkartinis patikrinimas aprašytas „Sprendimai eigoje“)
- [x] testai žali (2391 passed, 13 skipped, 31 xfailed; vienintelis kritęs `test_real_edge_synthesis_smoke` vėliau ištrintas, voice: 259 passed), `ruff check` / `ruff format --check` švarūs (Edge TTS tinklo testas gali kristi – žinomas radinys #1, ne šios užduoties)

## Sprendimai eigoje
- `load_locale(root=None)` → `(root or LOCALES_DIR)`; `language.py` skaito `locale.LOCALES_DIR` per modulį
  (anksčiau `from .locale import LOCALES_DIR` užšaldydavo reikšmę). `schema.py:856` ir `locale._examples`
  jau skaitė kvietimo metu – nekeista.
- Fixture `phrases_file` kopijuoja visą `locales/` (be `__pycache__`), nes `revalidate()` per `check_prompts()`
  skaito ir `examples/*.md`.
- Apsauga `repo_files_unchanged` (`tests/conftest.py`): sha256 visiems `src/agent/locales/` ir
  `src/agent/knowledge/` failams sesijos pradžioje ir pabaigoje; skirtumas → teardown ERROR su sąrašu
  (`changed` / `added` / `removed`).
- Vienkartinis patikrinimas: laikinas testas pridėjo eilutę prie `knowledge/limits.yaml` →
  `ERROR at teardown … Tests changed repo files: src/agent/knowledge/limits.yaml (changed)`, exit 1.
  Failas atstatytas, testas ištrintas (necommitintas).
- Paieška (`write_text/write_bytes/open(..,'w')/unlink/copytree/sqlite3.connect` visuose `tests/`): kiti testai
  rašo tik į `tmp_path`; `observe/test_api.py` `API_CONFIG_FILE` → `tmp_path`; DB kūrimas ir `reset_db()` rašo į
  `database/isp_database.test.db` (gitignored, testų failas) – tvarkoje. Vienintelis pažeidėjas buvo `phrases_file`.
- Andriaus prašymu ištrintas `voice/test_voice_adapters.py::TestEdgeTTS::test_real_edge_synthesis_smoke`
  (tikras Edge tinklo kvietimas; Edge TTS nebenaudojamas). Kiti `TestEdgeTTS` testai (be tinklo) lieka, kol
  lieka pats adapteris.
- Pagrindiniame checkout'e likęs `probe_wave5` `locales/lt/phrases.yaml` nepaliestas (ten dirba kitos sesijos) –
  atstatyti rankiniu būdu.

## Rezultatas
- Commit'ai: `45edff0` (užduotis), `1c47aca` (izoliacija + apsauga), `82af8cc` (Edge TTS tinklo testas ištrintas).
- Compare: https://github.com/steellsas/ISP-AI-Agent/compare/develop...fix/test-locale-isolation
- Pagrindinio checkout'o `phrases.yaml` (`probe_wave5`) atstatytas.
- `/code-review high`: blokuojančių nėra. Liko (atskiroms užduotims, jei reikia):
  - jau buvęs: `loader.reload()` neišvalo `language._load` (`kalba.yaml` keitimas be restarto nematomas);
  - smulkmenos: apsauga neatskiria rankinio redagavimo testų metu; `monkeypatch.undo()` fixture'e atšaukia
    visus testo patch'us; `prompts/` neapsaugotas; apsauga veikia tik `chatbot_core/tests`.

## Darbo taisyklės
- Eigoje priimtus sprendimus užrašyk skiltyje „Sprendimai eigoje“. Jei testai nepraeina ar atsiranda kelios galimybės – sustok, pateik variantus su rekomendacija ir lauk.
- Nerašyk istorinių komentarų (datų, „fixed after…“).
- Pabaigoje: testai + `ruff check` / `ruff format --check` → commit (EN) → `/code-review high` šakos diff'ui. Radinius pateik Andriui; taisyk tik su jo pritarimu, pataisas commit'ink atskirai. Tada push tik su leidimu → duok compare URL (`https://github.com/steellsas/ISP-AI-Agent/compare/develop...<šaka>`) + EN PR title/description (su peržiūros rezultatu) → būsena `peržiūra` (užduoties failas ir README eilutė, tame pačiame PR). PR per `gh` nekurk.

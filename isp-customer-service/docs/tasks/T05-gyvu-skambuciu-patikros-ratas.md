# T05 — Gyvų skambučių patikros ratas

**Būsena:** vykdoma · **Šaka:** `docs/live-check-round` · **ROADMAP:** P0 (projekto peržiūra 2026-11-26) · **Modelis:** Opus

## Tikslas
Uždaryti atvirus gyvų skambučių patikros radinius (23 „taisomas“ + 9 „laukia gyvo“) ir gauti pirmą eval bazę su versijomis.

## Kodėl
Po P0 (T01 tiketo kontaktų grounding, T02 testų izoliacija, T03 eval istorija `logs/eval/history.jsonl`,
T04 numeris po registracijos) dalis „taisomas“ radinių gali būti jau išspręsti, bet niekas to nepatikrino.
Be bazės nežinome, ar agentas gerėja, ar blogėja. Radiniai: [`docs/demo/DERINIMO_RADINIAI.md`](../demo/DERINIMO_RADINIAI.md).

## Apimtis
- Daroma:
  1. Bazinis eval `--runs 3` (50 scenarijų, ~0,30 USD), tik su Andriaus leidimu. Rezultatas — `logs/eval/history.jsonl` su versijų žymomis.
  2. D8d: nustatyti, ar tai pastovus kritimas, ar triukšmas (3 paleidimai). Jei pastovus — aprašyti priežastį ir pasiūlyti taisymą (kodo netaisyti).
  3. Kiekvienam „taisomas“ radiniui patikrinti pagal kodą ir eval ir pažymėti: „pataisyta (PR #…)“, „vis dar yra“ arba „nebeaktualu“, su įrodymu (failas:eilutė, eval ID ar commit).
  4. „Laukia gyvo“ radiniams parengti trumpą LT gyvo skambučio scenarijų sąrašą `docs/testing/`, kad Andrius paskambintų pats.
- Nedaroma: naujų taisymų kode. Rasti dalykai tampa naujomis užduotimis (pasiūlymai žemiau).

## Atlikta, kai
- [ ] `history.jsonl` turi bazinį įrašą
- [ ] kiekvienas radinys turi būseną su įrodymu
- [ ] D8d turi išvadą
- [ ] gyvo skambučio sąrašas yra `docs/testing/`
- [ ] testai žali (`uv run pytest`), ruff švarus

## Sprendimai eigoje
- **29 unikalūs radiniai, ne 32.** #17, #19 ir #72 yra ir „taisomas“, ir „laukia gyvo“. Kiekvienas gauna vieną būseną;
  gyvo skambučio sąraše lieka visi 9 (Andrius patvirtino).
- **Eval leidimas.** Andrius leido paleisti bazinį `--runs 3` (2026-11-27). Istorija rašoma į pagrindinio checkout'o
  `logs/eval/history.jsonl` per `--history` (be jo eval iš worktree rašytų į worktree `logs/`).

## Radinių patikra
(pildoma eigoje)

## D8d
(pildoma po eval)

## Pasiūlymai naujoms užduotims
(pildoma eigoje)

## Rezultatas
(commit'ai, compare URL, kas liko)

## Darbo taisyklės
- Eigoje priimtus sprendimus užrašyk skiltyje „Sprendimai eigoje“. Jei testai nepraeina ar atsiranda kelios galimybės – sustok, pateik variantus su rekomendacija ir lauk.
- Nerašyk istorinių komentarų (datų, „fixed after…“).
- Pabaigoje: testai + `ruff check` / `ruff format --check` → commit (EN) → `/code-review high` šakos diff'ui. Radinius pateik Andriui; taisyk tik su jo pritarimu, pataisas commit'ink atskirai. Tada push tik su leidimu → compare URL (`https://github.com/steellsas/ISP-AI-Agent/compare/develop...docs/live-check-round`) + EN PR title/description (su peržiūros rezultatu) → būsena `peržiūra` (užduoties failas ir README eilutė, tame pačiame PR). PR per `gh` nekurk.

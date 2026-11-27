# Užduotys

> Vieta: `docs/tasks/README.md`. Viena užduotis yra vienas failas `T<NN>-trumpas-pavadinimas.md`.
> Sesijos pavadinimas sutampa su failu: `ISP-T07 TTS greitis`.

## Sąrašas

| ID | Užduotis | Būsena | Šaka | Sesija |
|---|---|---|---|---|
| T01 | Tiketo kontaktai tik iš kliento žodžių | retro | fix/ticket-contact-grounding | ISP-T01 tiketo kontaktų grounding |
| T02 | Testai neliečia repo failų | retro | fix/test-locale-isolation | ISP-T02 testų izoliacija |
| T03 | Eval istorija su versijomis | retro | feat/eval-history | ISP-T03 eval istorija |
| T04 | Numeris po registracijos tik perklausus | retro | fix/post-registration-phone-readback | ISP-T04 numeris po registracijos |
| T05 | Gyvų skambučių patikros ratas | vykdoma | docs/live-check-round | ISP-T05 gyvų skambučių patikra |

Būsenos: `planuojama` → `vykdoma` → `peržiūra` (push, laukia PR) → `atlikta` → `retro` (padaryta).

---

## Šablonas (`T<NN>-pavadinimas.md`)

```markdown
# T<NN> — <pavadinimas>

**Būsena:** planuojama · **Šaka:** `<tipas>/<pavadinimas>` · **ROADMAP:** <etapas>

## Tikslas
Ką turime gauti (1–3 sakiniai).

## Kodėl
Kokią problemą sprendžia ir ką duoda. Nuoroda į STATUS/ROADMAP/radinį.

## Apimtis
- Daroma: …
- Nedaroma: …

## Atlikta, kai
- [ ] …
- [ ] testai žali (`uv run pytest`), ruff švarus
- [ ] eval: <kurie scenarijai> (jei liečia elgseną)
- [ ] STATUS.md / docs atnaujinti

## Sprendimai eigoje
(sesija čia užrašo, ką aptarėme ir nusprendėme)

## Rezultatas
(commit'ai, compare URL, kas liko)
```

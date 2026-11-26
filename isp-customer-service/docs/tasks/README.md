# Užduotys

> Vieta: `docs/tasks/README.md`. Viena užduotis yra vienas failas `T<NN>-trumpas-pavadinimas.md`.
> Sesijos pavadinimas sutampa su failu: `ISP-T07 TTS greitis`.

## Sąrašas

| ID | Užduotis | Būsena | Šaka | Sesija |
|---|---|---|---|---|
| T01 | Tiketo kontaktai tik iš kliento žodžių | peržiūra | fix/ticket-contact-grounding | ISP-T01 tiketo kontaktų grounding |

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

# T01 — Tiketo kontaktai tik iš kliento žodžių

**Būsena:** vykdoma · **Šaka:** `fix/ticket-contact-grounding` · **ROADMAP:** Stage 2 (demo kokybė)

## Tikslas
Telefonas ir laikas tikete paimami tik iš to, ką klientas tikrai pasakė; padiktuotas numeris, kuris skiriasi nuo caller ID, perklausiamas prieš registruojant.

## Kodėl
`chatbot_core/src/agent/decide/rules/ticket.py:231-236` įrašo LLM perskaitytą numerį, jei jame ≥ 6 skaitmenys, bet nelygina su kliento fraze; valandos (`:249`) irgi iš LLM teksto. Klientas numerį išgirsta tik po registracijos ir tik paskutinius skaitmenis („Skambinsime ***0106“, `execute/ticket.py:145`). Pažeidžia „LLM tik kalba“ ir „Confirm, do not guess“ (projekto peržiūra 2026-11-26, P0-1).

## Apimtis
- Daroma:
  - LLM `value` telefonui priimamas tik jei jo skaitmenys sutampa su skaitmenimis iš kliento frazės (po esamos ASR skaičių normalizacijos `adapters/asr/lt_text.py`, jei taikoma); kitaip – esamas raktinių žodžių / pakartotinio klausimo kelias (`ticket.py:~294-317`). `same_number` lieka caller ID.
  - Valandos: pirma `hours_words(user_input)`; LLM reikšmė tik jei visi jos skaičiai yra kliento frazėje; kitaip esamas kelias.
  - S1=B: jei priimtas numeris ≠ caller ID, variklis klausia „Užrašiau {numeris} — ar teisingai?“ (per `case.confirm` ar esamą patvirtinimo mechanizmą; frazė `locales/lt/phrases.yaml`); „ne“ → klausti numerio iš naujo; „taip“ → valandos.
  - `docs/ARCHITECTURE.md`: decide kviečia `ticket_reader` (`understand_ticket`) tik neperskaitytame ėjime (ticket.py:~176).
- Nedaroma: `refusal` kelias (jau turi patvirtinimą); kaukė baigiamojoje frazėje; kiti gate apėjimai (P1, atskira užduotis).

## Atlikta, kai
- [ ] testai: LLM numeris ne iš frazės → neįrašomas, klausiama iš naujo; sutampantis → įrašomas; ≠ caller ID → perklausimas, „ne“ → klausti iš naujo; valandos be skaičių frazėje → LLM laikas neįrašomas. Pataisą įrodantys testai pirma krenta ant seno kodo.
- [ ] `uv run pytest` žalias, `ruff check` / `ruff format --check` švarūs
- [ ] eval: scenarijai su tiketo dialogu (`--only`, sąrašą įrašyk čia); pilnas eval tik su Andriaus leidimu (kainuoja)
- [ ] nauja frazė užregistruota `docs/review/PROMPTAI.md`; `ARCHITECTURE.md` atnaujintas

## Sprendimai eigoje
(pildyk čia)

## Rezultatas
(commit'ai, compare URL, kas liko)

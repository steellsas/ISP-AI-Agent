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
- [x] testai: LLM numeris ne iš frazės → neįrašomas, klausiama iš naujo; sutampantis → įrašomas; ≠ caller ID → perklausimas, „ne“ → klausti iš naujo; valandos be skaičių frazėje → LLM laikas neįrašomas. Pataisą įrodantys testai pirma krenta ant seno kodo (12 krito).
- [x] `pytest`: 2405 passed; 1 failed – `test_voice_adapters::test_real_edge_synthesis_smoke` (tikras Edge TTS tinklas, TTS nekeistas). `ruff check` / `ruff format --check` švarūs
- [x] eval `--only`: `T1_tv_unclear_fault_ticket` 6/6, `R1_billing_request` 7/7, `S4e_lights_declined_power_checked` 7/7, `S4f_dead_router_offer_heard_no_computer` 8/8, `D5_link_down` 6/6, `D8d_technician_requested_mid_fix` 7/8 (2 kartus). D8d: krenta `reply_any „per minutę“` – pasiūlymo frazėje prieš tiketo dialogą; trace'e jokio T01 sprendimo (`phone_confirm` / `phone_not_grounded`), scenarijaus ėjimai išsiderina ties `case.summary`. Su T01 nesusiję; ant `develop` netikrinta.
- [x] nauja frazė užregistruota `docs/review/PROMPTAI.md`; `ARCHITECTURE.md` atnaujintas

## Sprendimai eigoje
- Patvirtinimas – ne `case.confirm` (jis skirtas Case faktams), o tiketo dialogo nuosavas mechanizmas
  kaip `cancel_confirm_out`: `TicketContext.phone_pending` / `ask_phone_confirm` / `phone_confirm_out`.
  Atsakymas skaitomas **prieš** `ticket_reader` ir perception skaitytuvą – jie „Taip“ skaito kaip `same_number`.
- Perklausiamas bet koks padiktuotas numeris ≠ caller ID – ir iš LLM, ir iš raktinių žodžių (≥ 6 skaitmenys)
  kelio. Paslėptas caller ID → perklausiamas kiekvienas numeris.
- Numerių palyginimas pagal nacionalinę dalį (`370…` / `8…`): „860012353“ ≡ `+37060012353`, be perklausimo,
  į tiketą rašomas caller ID.
- Atsakymas į perklausimą: naujas numeris → perklausiamas jis; taip / backchannel → įrašomas; ne →
  „pasakykite numerį dar kartą“; neaiškus → perklausimas kartojamas 1 kartą, po to kaip „ne“.
- Grupuotai ištarti skaičiai („aštuoni šeši šimtai dvylika…“) `normalize_numbers` sumuojami → tokio LLM
  numerio grounding nepraeina → perklausiama. Sąmoningai: geriau perklausti nei įrašyti spėjimą.
- Frazės skriptinės (ne narratoriui), kaip retry ir cancel-confirm.
- Valandos – variantas B (Andrius 2026-11-26): `hours_words(kliento frazė)` su konkrečiu laiku (skaičiais)
  laimi; jei jis duoda tik „bet kada“ / dienos dalį ar nieko, imama `ticket_reader` reikšmė, bet tik kai ji
  sudaryta iš kliento žodžių: visi skaičiai frazėje, kiekvienas žodis turi bendrą kamieną (3–4 raidės) su
  kliento žodžiu, trumpi žodžiai („po“, „iki“) – pilnai; jungiamieji žodžiai `vocabulary.yaml`
  `hours_glue_words`. Taip išlieka „Bet kada galima per pietus iš ryto“ → „per pietus arba ryte“, o
  sugalvotas „vakare“ neįrašomas.
- Elgsenos pokytis esamuose testuose: „Ne, kitu numeriu: 861234567“ dabar → perklausimas
  (`test_contact_dialogue`, `test_phase::test_another_number_is_read_back`, `test_hidden_number`).
- `/code-review high` (8 radiniai): Andrius pritarė taisyti 3 svarbius ir 4 smulkius, atskiru commit'u.
  Perklausimo atsakymas dabar: tas pats numeris = „taip“; klausimas → narratorius atsako, perklausimas lieka;
  „neregistruokit“ / „sprendžiam toliau“ → esami cancel-confirm / abort keliai (po „registruokit“ numeris
  perskaitomas vėl); atsisveikinimas → registruojama su padiktuotu numeriu; padėtas ragelis → finalizer ima
  `phone_pending` prieš caller ID. Grounding: LLM numeris turi sutapti su visu kliento ištartu skaitmenų
  bloku (ne fragmentu); „bet kada“ keičia tik LLM reikšmė, kuri pati yra laikas. Nepataisyta (už apimties):
  `closing.py:65` numerio pataisymas po registracijos be perklausimo.
- Eval: nė vienas scenarijus nediktuoja kito numerio; naujo scenarijaus nedėta (`agent/eval/` liečia T03) – follow-up.

## Rezultatas
(commit'ai, compare URL, kas liko)

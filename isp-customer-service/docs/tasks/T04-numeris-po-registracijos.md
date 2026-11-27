# T04 — Numeris po registracijos tik perklausus

**Būsena:** retro · **Šaka:** `fix/post-registration-phone-readback` · **ROADMAP:** Stage 2 (demo kokybė)

## Tikslas
Po „Užregistravau“ kliento padiktuotas kitas numeris į tiketą patenka tik jį perskaičius atgal ir klientui patvirtinus – taip pat, kaip kontaktų dialoge po T01.

## Kodėl
`chatbot_core/src/agent/decide/rules/closing.py:~59-66` po registracijos bet kokią frazę su ≥ 6 skaitmenimis įrašo į `contact_phone` ir prideda tiketo pastabą „Skambinti kitu numeriu: …“ be perklausimo (gali būti sąskaitos / adreso skaičius ar ASR klaida). Pažeidžia „Confirm, do not guess“. Šaltinis: T01 `/code-review high` pre-existing radinys.

## Apimtis
- Daroma:
  - po registracijos padiktuotas numeris pirma perskaitomas „Užrašiau {phone} — ar teisingai?“, pakartotinai naudojant T01 mechanizmą (`decide/rules/ticket.py`: `_take_phone` / `_read_phone_confirm`, `TicketContext.phone_pending`) ar jo bendrą dalį;
  - „taip“ / tas pats numeris → `append_ticket` + `ticket_phone_fixed`; „ne“ → klausti numerio iš naujo; naujas numeris → perskaityti jį;
  - klausimas, atsisveikinimas, padėtas ragelis per perklausimą tvarkomi kaip T01 (pamoka `docs/lessons.md`: iš anksto surašyti visas atsakymo rūšis ir kiekvienai testą);
  - numeris, sutampantis su caller ID ar esamu `contact_phone` → jokio pakeitimo, jokios pastabos.
  - eval scenarijus, kuriame klientas diktuoja kitą numerį nei caller ID (kontaktų dialoge ir po registracijos); tiketas baigiasi patvirtintu numeriu (papildymas, Andrius per Patarėją 2026-11-27).
- Nedaroma: T01 kontaktų dialogo elgsenos keitimas; kiti closing keliai; kaukė baigiamojoje frazėje.

## Atlikta, kai
- [x] testai (pirma krenta ant seno kodo – 18 krito): po registracijos numeris → perklausimas, `append_ticket` dar nevyksta; „taip“ → pastaba + `contact_phone`; „ne“ → klausiama iš naujo, pastabos nėra; tas pats numeris → pastabos nėra; atsisveikinimas / klausimas / ragelis per perklausimą
- [x] `pytest`: 2439 passed, 13 skipped, 31 xfailed; `ruff check` / `ruff format --check` švarūs
- [x] eval `--only`: `T1_tv_unclear_fault_ticket` 6/6, `R1_billing_request` 7/7, `S4e_lights_declined_power_checked` 7/7, `S4f_dead_router_offer_heard_no_computer` 8/8, `D5_link_down` 6/6 (D8d – T05)
- [x] naujas eval scenarijus `T3_other_number_read_back` 8/8: tiketo kontaktas = patvirtintas `868321007`; trace – du perklausimai (T01 ir T04), `phone_confirmed`, `phone_noted`
- [x] nauja frazė (jei reikia) `docs/review/PROMPTAI.md`; `ARCHITECTURE.md` atnaujintas

## Sprendimai eigoje
- Atsisveikinimas / padėtas ragelis per perklausimą (Andrius 2026-11-26): į tiketą rašoma pastaba
  „nepatvirtintas“, `contact_phone` nekeičiamas.
- Laukiantis numeris laikomas T01 `TicketContext` (`phone_pending`, `phone_confirm_out`,
  `phone_confirm_unclear`), `ticket.stage` lieka `None` – `ticket.plan` jo neliečia (Andrius 2026-11-26).
- Bendra dalis: iš `_read_phone_confirm` iškeliamas atsakymo skaitytuvas (rūšis), T01 veiksmai nesikeičia.
- Kol perklausimas laukia atsakymo, `maybe_finish` nekviečiamas – ragelis nepakabinamas (anksčiau
  „Skambinkit 868…, viso gero“ ar numeris 2-ame closing ėjime dingdavo).
- Eval scenarijus `T3_other_number_read_back` (`agent/eval/scenarios.json`) ir nauja vertintojo patikra
  `ticket_phone` (`run_eval.py`: tiketo kontaktas skambučio pabaigoje). D8d kritimas – ne šios užduoties (T05).
- Tiketo pastabų tekstai perkelti į `locales/lt/phrases.yaml` (`ticket.details.*`).
- Elgsenos pokytis esamuose testuose: `test_closing_rules` ir `test_closing` (2 testai) – numeris po
  registracijos dabar pirma perklausiamas.

- `/code-review high` (7 radiniai): Andrius 2026-11-27 – taisyti 1, 2, 3, o 4–7 įrašyti į
  `docs/ROADMAP.md` (Stage 2, E6), kad nepasimirštų:
  - #1 ragelis per T01 perklausimą: pastaba „nepatvirtintas“ rašoma tik kai numeris ≠ `contact_phone`;
  - #2 klausimas per perklausimą (T01 ir po registracijos): kortelė liepia pakartoti perklausimą;
    variklis „taip / ne / neaiškus“ priima tik jei paskutinėje agento frazėje buvo tas numeris,
    kitaip perklausimas kartojamas skriptu (`TicketContext.phone_confirm_after_question`);
  - #3 pastaba žymima `[NEPATVIRTINTA]` (CRM `NOTE_KINDS.unconfirmed`).

## Rezultatas
- Commit'ai: `0306e23` užduoties failas · `8858305` perklausimas po registracijos + eval scenarijus · `d05e353` peržiūros pataisos (1–3) + ROADMAP E6.
- Compare: https://github.com/steellsas/ISP-AI-Agent/compare/develop...fix/post-registration-phone-readback
- `/code-review high`: 7 radiniai – 2 svarbūs + 1 smulkus pataisyti (`d05e353`), 4 atidėti į `docs/ROADMAP.md` E6 (vienas jų – buvęs ir anksčiau).
- PR #146 sujungtas į `develop` (`b9b8fd3`).
- Retro: 2 pamokos `docs/lessons.md` (sekantis ėjimas po atsakymo rūšies → CLAUDE.md; push leidimas toje pačioje sesijoje → skill `patarejas`).
- Liko: ROADMAP E6 (peržiūros radiniai #4–7, prieš pradedant patikrinti aktualumą); D8d – T05.

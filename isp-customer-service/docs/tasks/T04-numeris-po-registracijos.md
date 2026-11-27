# T04 — Numeris po registracijos tik perklausus

**Būsena:** vykdoma · **Šaka:** `fix/post-registration-phone-readback` · **ROADMAP:** Stage 2 (demo kokybė)

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
- Nedaroma: T01 kontaktų dialogo elgsenos keitimas; kiti closing keliai; kaukė baigiamojoje frazėje.

## Atlikta, kai
- [ ] testai (pirma krenta ant seno kodo): po registracijos numeris → perklausimas, `append_ticket` dar nevyksta; „taip“ → pastaba + `contact_phone`; „ne“ → klausiama iš naujo, pastabos nėra; tas pats numeris → pastabos nėra; atsisveikinimas / klausimas / ragelis per perklausimą
- [ ] `uv run pytest` žalias, `ruff check` / `ruff format --check` švarūs
- [ ] eval `--only` scenarijams, kurie baigiasi registracija (sąrašą įrašyk čia); pilnas eval tik su Andriaus leidimu (kainuoja)
- [ ] nauja frazė (jei reikia) `docs/review/PROMPTAI.md`; `ARCHITECTURE.md` atnaujintas

## Sprendimai eigoje
- Atsisveikinimas / padėtas ragelis per perklausimą (Andrius 2026-11-26): į tiketą rašoma pastaba
  „nepatvirtintas“, `contact_phone` nekeičiamas.
- Laukiantis numeris laikomas T01 `TicketContext` (`phone_pending`, `phone_confirm_out`,
  `phone_confirm_unclear`), `ticket.stage` lieka `None` – `ticket.plan` jo neliečia (Andrius 2026-11-26).
- Bendra dalis: iš `_read_phone_confirm` iškeliamas atsakymo skaitytuvas (rūšis), T01 veiksmai nesikeičia.
- Kol perklausimas laukia atsakymo, `maybe_finish` nekviečiamas – ragelis nepakabinamas (anksčiau
  „Skambinkit 868…, viso gero“ ar numeris 2-ame closing ėjime dingdavo).
- Tiketo pastabų tekstai perkelti į `locales/lt/phrases.yaml` (`ticket.details.*`).

## Rezultatas
(commit'ai, compare URL, kas liko)

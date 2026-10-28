# Identifikacija pagal adresą

Kai skambinančio numeris nežinomas, agentas klientą randa CRM pagal adresą. Šis dokumentas
aprašo, kaip tai turi veikti ir kas jau padaryta. Kilmė: demo skambutis
`20261028-085902-394727-0002` (Dainų g. 5-5, ~30 ėjimų ratu) — radiniai #11–#15
[DERINIMO_RADINIAI.md](DERINIMO_RADINIAI.md).

## Principas

Kaip darbuotojas su CRM programa: įveda, ką išgirdo, programa parodo, kas yra, ir pabaigoje
vieną kartą perskaito pilną adresą. Klientui tikslinama tik tai, ko nepavyko rasti arba kas
turi kelis variantus. Pasakyta informacija nedingsta.

```
 klientas: „Dainų 5 5“
     │
 ① SUPRATIMAS   ištraukia dalis IR kitus skaičių skaitymus      perceive/nlu.py extract_address
     │          gatvė Dainų │ 55  arba  5 + butas 5
 ② PAIEŠKA      DB tikrina skaitymus iš eilės                  perceive/slots.py lookup_heard_address
     │          Dainų 55 ✘   Dainų 5-5 ✔
 ③ SPRENDIMAS   rasta → patvirtinti; trūksta → klausti tos dalies   decide/rules/head.py
     │
 ④ ŽODŽIAI      variklio frazė iš to, ką jis turi              decide/rules/reply.py
                „Ar teisingai supratau — Šiauliai, Dainų g. 5, butas 5?“
```

## Skaičių skaitymai

Agentas DB gali tikrinti laisvai, bet klientui siūlo **vieną labiausiai tikėtiną** variantą,
sudarytą tik iš kliento paties pasakytų skaičių, ir jį pasitikslina (privatumo sprendimas,
2026-10-28).

| Klientas sako | Pirmas skaitymas | Kiti skaitymai |
|---|---|---|
| „Dainų 5-5“, „5.5“, „33-2“, „60/7“ | namas 5, butas 5 | — (brūkšnys aiškus) |
| „Dainų 5 5“ (du skaitmenys suklijuoti) | namas 55 | namas 5, butas 5 |
| „Dainų 55“ | namas 55 | namas 5, butas 5 |
| „Vilniaus 33 2“ | namas 33 | namas 33, butas 2 |
| „Dainų 5, butas 55“ | butas 55 | butas 5 |
| „Tildžės 6 0 būtų namas“ | namas 60 | — |

## Atsakymai į „Ar teisingai supratau — …?“

| Atsakymas | Kas daroma |
|---|---|
| „taip“, „teisingai“, „taip, patvirtinu 2 kartus“ | identifikuota; skaičius sakinyje adreso nekeičia |
| „ne, butas 25“, „5-2“ (pasakyta nauja dalis) | keičiama tik pasakyta dalis, ieškoma iš naujo |
| „ne“ (be naujų dalių) | „Pasakykite adresą dar kartą — gatvę, namo ir buto numerį.“ |
| neaišku („Haloo“, „Nesuprantu“, „5.“) | nieko netrinama, klausiama dar kartą |
| 3 neaiškūs iš eilės | „Nepavyksta patvirtinti adreso. Gal turite abonento kodą?“ |

Kitos taisyklės:

- Kai DB prašo buto, o klientas sako tik skaičių („5“, „trys“, „trečias“) — tai butas, ne namas.
- Kol laukiama abonento kodo, jo skaitmenys nelaikomi adresu (nebent pasakyta gatvė).
- Jei pagal adresą neranda po 3 bandymų: „Pagal adresą jūsų sutarties rasti nepavyksta.
  Pabandykime kitaip — gal turite abonento kodą?“
- Kai trūksta dalies, LLM gauna vieną užduotį: paklausti tik tos dalies.

## Kas dar neįgyvendinta

| Spraga | Testas |
|---|---|
| Pavardė į paiešką nepatenka (dvi sutartys name, „gal pagal vardą?“) | `test_phase.py` T-6 (xfail) |
| „ne, butas 25“, kai tokio buto nėra — atsakymą žodžiais vis dar formuoja LLM | — |
| Masinis gedimas: informuoti jau žinant gatvę (#16) | — |
| Kiti NLU skaitymai: „3 butas“, „trečias butas, Tilžės 60“, gatvė be diakritikų | `test_address_reading.py` (xfail) |

## Testai

```bash
uv run pytest chatbot_core/tests/identification -q
```

Gyvo skambučio atvejai: `tests/identification/test_phase.py` („5 5 — namas 5, butas 5“,
„neaiškus atsakymas — klausiama dar kartą“, `test_an_unclear_answer_asks_again_then_offers_the_code`…).

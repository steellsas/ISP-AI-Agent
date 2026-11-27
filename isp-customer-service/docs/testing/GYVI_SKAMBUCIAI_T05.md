# Gyvi skambučiai — radiniai, kurie laukia gyvo patikrinimo

Devyni radiniai iš [DERINIMO_RADINIAI.md](../demo/DERINIMO_RADINIAI.md), kurių taisymas padengtas testais,
bet gyvai dar nepatikrintas (T05). Kiekvienam — vienas trumpas skambutis. Formatas kaip
[BALSO_TESTAVIMAS.md](BALSO_TESTAVIMAS.md): **Tu** = ką sakai, **Agentas turi** = ko tikimės (ne pažodžiui),
**Nepavyko, jei** = ką žymėti kaip ✗.

## Prieš skambinant
1. Serveris ir dashboard'as: `uv run uvicorn --app-dir chatbot_core src.app.main:app --port 8080`.
2. ♻ **DB** dashboard'e tą pačią dieną (avarijos ETA).
3. **Telefono režimas** (8 kHz) skambučiams #63, #72, #73, #83 — jie atsirado per telefono liniją.
4. Po skambučio: skambučio ID iš Archyvo įrašyk į lentelės stulpelį „Rezultatas“, ✓/✗ ir trumpą pastabą.
   ✗ atveju radinys grįžta į `DERINIMO_RADINIAI.md` kaip naujas įrašas su skambučio ID.

Numeriai ir klientai — [DEMO_SCENARIJAI.md](../demo/DEMO_SCENARIJAI.md). „Nežinomas numeris“ — bet kuris
CRM nesantis numeris (pvz. `+37000000000`), kad agentas ieškotų pagal adresą.

## Suvestinė

| # | Ką tikrinam | Skambutis | Rezultatas (ID, ✓/✗) |
|---|---|---|---|
| 17 | „penki“, iškraipytas ASR („Pinki“), tampa namu 5 | Masinis gedimas, nežinomas numeris, Dainų g. 5-5 | |
| 19 | žinant gatvę ir namą, klausiama tik buto | ta pati | |
| 58 | „Malonu, Tomai!“ — vieną kartą, žinios pradžioje | ① Skola, +37060020101 | |
| 63 | TV fone: agento paties sakinys netampa kliento ėjimu | bet kuris, su įjungtu TV | |
| 66 | suma be „eurų“ perklausiama | ⑫ Ginčijama skola, +37060020101 | |
| 71 | „Ne… Būtinai, registruokit“ — galioja paskutinis atsakymas | ⑫ Ginčijama skola | |
| 72 | vardas iš pirmo karto (savininko vardas ASR užuominoje) | ③ Mazgo gedimas, +37060030306 (Lina) | |
| 73 | „Nuo“ (pauzė) „12 iki 13“ — vienas ėjimas | skambutis su tiketu, kai klausiama laiko | |
| 83 | sakinio tęsinys po pauzės nepriklijuojamas prie kito ėjimo | ⑨ Telefone neveikia, +37060020109 (Aldona) | |

---

## #17 ir #19 — adresas iš nežinomo numerio (vienas skambutis)

Eiga kaip testo `tests/identification/test_phase.py::test_the_warning_asks_only_for_the_missing_flat`.

- **Tu:** „Neveikia internetas.“ → kai paklausia adreso: „Dainų gatvėje.“
- **Tu:** „Mano namo numeris penki.“ (sakyk „penki“ greitai, neaiškiai — kaip „pinki“).
- **Agentas turi (#17):** namą 5 suprasti iš pirmo karto ir klausti toliau, ne „kokį namo numerį?“ antrą kartą.
- **Tu (#19):** du ėjimai be adreso dalies: „Ir ką?“ → „Nežinau.“
- **Agentas turi:** po antrojo — „Adresą Dainų g. 5 jau turiu, dar reikia buto numerio. Pasakykite jį — arba
  abonento kodą iš sąskaitos.“
- **Tu:** „Penki.“ (vien skaičius, vėl neaiškiai).
- **Agentas turi:** „penki“ laikyti butu → „Ar teisingai supratau — Šiauliai, Dainų g. 5, butas 5?“
- **Nepavyko, jei:** namo klausiama du kartus (#17); įspėjimas „nežinodamas adreso negalėsiu…“ ir viso adreso
  iš naujo, arba „penki“ po įspėjimo paimtas kaip abonento kodas (#19).

## #58 — „Malonu, Tomai!“ žinioje apie skolą

- **Tu:** „Neveikia internetas.“ → „Taip“ (adresas) → „Tomas.“
- **Agentas turi:** „Išgirdau — Tomas. Ar teisingai?“
- **Tu:** „Taip.“
- **Agentas turi:** žinia prasideda „Malonu, Tomai!“ ir toliau apie sustabdytą paslaugą.
- **Tu:** „O kiek tiksliai skolingas?“
- **Nepavyko, jei:** „Malonu, Tomai!“ pasakoma antrą kartą (kitame atsakyme) arba jos nėra, o vėliau atsiranda.

## #63 — TV fone, telefono režimas

- **Paruošk:** įjunk TV ar radiją su kalba fone, ~1–2 m nuo mikrofono.
- **Tu:** palauk agento pasisveikinimo, **ketvirtį minutės tylėk**, tada: „Neveikia internetas.“ ir toliau kaip įprasta.
- **Agentas turi:** tylos metu nepradėti gedimo eigos; Archyve tarp kliento ėjimų neturi būti agento paties
  sakinių („Aš padedu dėl interneto“, jo klausimų).
- **Nepavyko, jei:** kliento ėjimuose yra agento sakinys, arba agentas pradeda diagnozę be tavo žodžių.
- Pastaba: atsitiktiniai TV žodžiai kaip kliento ėjimai — atskiras radinys #64, čia jo nevertinam.

## #66 — suma be „eurų“

- **Tu:** „Neveikia internetas.“ → adresas → vardas „Petras“ → po žinios apie skolą: „Bet aš mokėjau.“
- **Agentas turi:** paklausti „…pasakykite — kokią sumą ir kokiu būdu — banku, savitarnoje ar grynais?“
- **Tu:** „Trisdešimt devyni.“ (be „eurų“)
- **Agentas turi:** „Ar teisingai supratau — mokėjote 39 €?“ → „Taip“ → suma tikete.
- **Nepavyko, jei:** suma praleidžiama, tiketas be sumos.

## #71 — sutikimas registruoti: galioja paskutinis atsakymas

- Tas pats skambutis kaip #66 arba naujas tuo pačiu numeriu, iki klausimo „Ar užregistruoti?“
- **Tu:** „Ne. Būtinai, registruokit.“
- **Agentas turi:** registruoti (klausti kontakto ar iškart patvirtinti registraciją).
- **Nepavyko, jei:** „Gerai, neregistruoju“ arba prireikia dar dviejų ėjimų iki tiketo.

## #72 — vardas iš pirmo karto (telefono režimas)

- **Tu:** „Neveikia internetas.“ → „Taip“ (adresas) → paklausus vardo: „Lina.“ (įprastai, ne skiemenimis)
- **Agentas turi:** „Išgirdau — Lina. Ar teisingai?“ → „Taip“ → „Malonu, Lina!“
- **Nepavyko, jei:** „Lenakas“, „Liūna“ ar kitas iškraipymas; agentas toliau kalba ne „Lina“.
- Pakartok su ⑦ Miręs routeris, +37060012353 („Giedrius“), jei laiko yra.

## #73 — nebaigta frazė (telefono režimas)

- Skambutis, kuriame agentas klausia, kada patogu susisiekti (pvz. ⑫ ginčijama skola po „Taip, registruokit“).
- **Tu:** „Nuo…“ (pauzė ~1 s) „…dvylikos iki pirmos.“
- **Agentas turi:** suprasti vieną atsakymą „nuo 12 iki 13 val.“.
- Papildomai vardo žingsnyje: „Mano vardas…“ (pauzė ~1 s) „…Tomas.“ → „Išgirdau — Tomas.“
- **Nepavyko, jei:** po „Nuo“ ar „Mano vardas“ agentas jau atsako („Nesupratau. Pavyzdžiui…“, „vardo gerai neišgirdau“).

## #83 — vėlyvas ėjimo perrašymas (telefono režimas)

- **Tu:** „Neveikia internetas telefone.“ → adreso klausimui: „Taip, dėl šio adreso…“ (pauzė ~1 s, kol agentas pradeda
  atsakyti) „…Ginkūnuose.“
- **Agentas turi:** kitas ėjimas — tik nauji žodžiai; instrukcija ar klausimas nekartojami.
- **Nepavyko, jei:** Archyve kitas kliento ėjimas prasideda senu tekstu („Taip, dėl šio adreso… …“) arba agentas
  pakartoja ką tik pasakytą instrukciją.

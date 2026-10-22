# Testai pagal funkcijas (ROADMAP 3.2, 2026-10-21)

Tikslas: testas iš karto pasako, **kuri funkcija** sugedo, žmonių kalba, dar prieš skaitant
traceback'ą. Nuo 3.4a (2026-10-22) **visi** testai yra srities aplanke, failas = funkcija — sričių
žemėlapis [TESTU_ZEMELAPIS.md](TESTU_ZEMELAPIS.md). Pilnai (variantų lentelės, visa fazė, žinomos
spragos) padaryta **identifikacija**, **problema** ir **tyrimas** (3.4b, 2026-10-22); kitos sritys pildomos
pagal tą patį šabloną.

## Kaip atrodo

```
uv run pytest -m identification chatbot_core/tests

============================= Funkcijų ataskaita ==============================
Identifikacija
  ✓ Paieška pagal numerį.. 4/4
  ✓ Adreso supratimas..... 33/33   (9 žinomos spragos)
      · spraga: tik butas: trečias butas — skaičius PRIEŠ „butas“ skaitomas kaip namas
  ✗ Buto paieška.......... 17/18
      ✗ T-4 namas be butų — neklausti — assert False is True
  ...
```

- **✓ / ✗** — funkcija veikia / sugedo; po ✗ — kuris variantas ir kodėl.
- **Žinoma spraga** — etalonas sako viena, variklis daro kita, ir tai žinoma (testas pažymėtas
  `xfail(strict=True)` su priežastimi). Spraga nelaužo paleidimo. Kai kas nors ją sutaiso,
  paleidimas krenta su „spraga sutaisyta — nuimkite xfail“, kad žymė nepasentų.
- Paleidžiant **visus** testus spragos tik suskaičiuojamos; paleidžiant **vieną sritį**
  (`-m identification`) — išvardijamos.

## Trys lygiai

| Lygis | Kas tikrinama | Kaip |
|---|---|---|
| **Funkcija** | vienas gebėjimas, daug variantų: „Tilžės 60-7“, „trečias butas“, be miesto, su ASR klaida… | lentelė `pytest.param(..., id="žmogiškas pavadinimas")` |
| **Fazė** | visa identifikacija nuo pirmų žodžių iki identifikuoto kliento (T-1…T-12) | `call` fiktyvas: tikras grafas, tik kalbantis LLM pakeistas |
| **Pokalbis** | visas skambutis su tikru LLM (formuluotės, supratimas) | eval (`agent/eval/scenarios.json`) |

## Identifikacijos funkcijos

| Failas | Funkcija | Etalonas |
|---|---|---|
| `test_phone_lookup.py` | Paieška pagal numerį | T-1, T-2; nieko apie sąskaitą iki „taip“ |
| `test_address_reading.py` | Adreso supratimas | kliento žodžiai → miestas, gatvė, namas, butas |
| `test_address_memory.py` | Adreso atmintis | dalys per kelis ėjimus (T-3), pataisymai |
| `test_city_search.py` | Vietovės paieška | T-5, T-11 |
| `test_street_search.py` | Gatvės paieška | panašios gatvės (PR) |
| `test_street_unclear.py` | Neaiški gatvė | raidžiavimas, sąžininga riba (PR-4) |
| `test_house_search.py` | Namo paieška | T-4 |
| `test_apartment_search.py` | Buto paieška | T-9b, T-4 |
| `test_contracts.py` | Kelios sutartys name | T-6, T-6R |
| `test_account_code.py` | Abonento kodas | T-10, A-3, A-3R |
| `test_confirmation.py` | Patvirtinimas | vartai (M6, D-09) |
| `test_caller_name.py` | Kas skambina | T-12 (privatumas) |
| `test_no_address.py` | Kai adreso nėra | T-7, A-3 |
| `test_address_change.py` | Adreso keitimas | T-8, A-2, A-2R |
| `test_policy.py` | Nustatymai | `identification.yaml` |
| `test_phase.py` | Visa fazė | T-1…T-12 per tikrą grafą |

## Fazės pradžia be ankstesnių fazių

Vėlesnės fazės testas neturi pereiti identifikacijos, kitaip sugedus identifikacijai kristų
visi testai po jos. Todėl yra fiktyvai, kurie pradeda skambutį **jau nuo fazės**:

```python
def test_kazkas_po_identifikacijos(identified):
    c = identified("CUST105")          # klientas priskirtas ir patvirtintas, vardas žinomas
    c.say("lemputės dega, bet interneto nėra")
    assert c.rule == "..."
```

`identified` priskiria klientą tuo pačiu variklio veiksmu, kaip po kliento „taip“
(`engine_resolve_from_slots`, kartu perskaitoma linija), bet be identifikacijos dialogo; kitas
ėjimas išgirsta radinį, kaip po tikro vardo atsakymo.

`diagnosing("router_hung")` — tas pats, bet demo klientui, kurio linija rodo nurodytą kortelę
(`tests/phases.py` `CARD_CUSTOMER`); įjungtos demo imitacijos (perkrovimas, tiltas), o po testo DB
atstatoma (imitacija pakeičia liniją). Tiketo ir pabaigos fiktyvai — 3.4b toliau.

## Visas skambutis teste (`call`)

```python
def test_t1(call):
    c = call("+37060020112")
    c.say("Laba diena, neveikia internetas")
    c.say("Taip")
    assert c.identity.customer_id == "CUST112"
    assert "koks jūsų vardas" in c.replies[-1].lower()
```

- Veikia tikras grafas ir test DB; kalbantis LLM atsako `‹LLM›`. Tikrinama tai, ką
  **nusprendė variklis** (taisyklės, būsena, įrankiai) ir variklio frazės pažodžiui.
- Kai kitas žingsnis priklauso nuo to, ko LLM paklausė, eilutė ją duoda:
  `c.say("Dainų gatvė 7", llm="Kokia jūsų pavardė?")`.
- `c.rules`, `c.tools`, `c.of("tool_call")`, `c.heard_everything()` (visi atsakymai ir LLM
  kortelės — privatumo patikroms).

## Kaip pridėti funkciją ar sritį

1. Srities katalogas su `__init__.py`: `AREA = "..."`, `MARK = "..."`, `FUNCTIONS = (...)`
   (ataskaitos tvarka).
2. Failas vienai funkcijai: `FUNCTION = "..."`, variantai lentele su lietuviškais `id`.
3. Žymę užregistruoti `tests/function_report.py` (`pytest_configure`).
4. Žinoma spraga — `marks=pytest.mark.xfail(strict=True, reason="kas negerai")`.

## Radiniai, kuriuos parodė nauji testai (2026-10-21, netaisyta)

Adreso supratimas:

- skaičius **prieš** „butas“ („trečias butas“, „3 butas“) skaitomas kaip namas;
- butas po brūkšnio pametamas („Tilžės 60-7“, „g. 33-2“);
- „keturiolika, antras butas“ → namas 16;
- gatvė be diakritikų („Tilzes“) nerandama — nei skaitant, nei ieškant;
- „Bubių kaime“ neskaitomas kaip Bubiai.

Atsakymas į „Koks buto numeris?“, kai klientas sako tik skaičių („7“, „trys“, „Trečias“),
įrašomas į namą, ne į butą.

Visa fazė:

- T-9b: „butas trys“ žodžiu laikomas tuščiu atsakymu, todėl paieška nevyksta;
- T-5: priėmus pasiūlytą vietovę, paieška nekartojama;
- T-6: pavardė į paiešką nepatenka;
- T-7: įspėjama po 3-io tuščio atsakymo, ne po 2-o; uždaroma tik po aiškaus „neturiu“.

Pastaba: dalis fazės radinių gali priklausyti nuo to, ką tikras LLM paklausia (testas jį
imituoja). Prieš taisant reikia patikrinti eval scenarijumi arba gyvu skambučiu.

## Problemos radiniai (3.4b, 2026-10-22, netaisyta)

Variklio skaitytuvas (L1, `intents.yaml` trigeriai) — **neteisinga klasė**:

- „neveikia elektra“, „telefonas neveikia“ → *internet_down* (bendras „neveikia“; tai ne mūsų sritis);
- „vaizdas stringa per televizorių“ → *internet_slow* (turėtų būti TV);
- „internetas vis nutrūksta“ → *internet_down* (katalogas tai aprašo kaip *internet_slow*);
- „norėčiau nutraukti interneto sutartį“ → *internet_down* (turėtų būti *disconnection*);
- „interneto bėdų neturiu, tik dėl sąskaitos“ → nieko (neigimas užgožia tikrą tikslą *billing*).

Ko variklis neatpažįsta, bet tai **modelio (L2) darbas** pagal dizainą (ne spraga): „niekas
nekrauna“, „kiek esu skolingas“, „routeris mirksi raudonai“, „greitesnio plano“.

Anamnezė: „nuo ryto“ neatpažįstama kaip laikas; „kai perkėliau routerį“ nėra tarp priežasčių.

Visa fazė:

- „Noriu nutraukti sutartį“ → agentas klausia „Ar tikrai norite baigti pokalbį?“ ir baigia —
  prašymas skaitomas kaip atsisveikinimas;
- prašymui (pvz. sąskaita) sakoma „Gerai — patikrinsiu ryšį“, nors linija netikrinama;
- lėtam internetui nėra kortelės — jis iškart eina į „neaiškaus gedimo“ tiketą su keista
  formuluote („gedimo tipas neaiškus — priežastis telefonu nenustatyta, perduota analizei“);
  tai Tyrimo srities klausimas.

## Tyrimo radiniai (3.4b 1 dalis, 2026-10-22, netaisyta)

- **Atsakymas į pirmą klausimą po radinio skaitomas tik modelio.** Radinį ir pirmą klausimą
  („Ar galite dabar prieiti prie routerio?“) pasako `identification.result_to_procedure` ėjimas,
  o variklis klausimą laiko nuskambėjusiu tik `case.*` ėjime — todėl jo paties skaitytuvas
  atsakymo nepaima ir klausimą užduoda dar kartą. Gyvuose rugsėjo skambučiuose tai buvo girdėti
  („Galiu, tuoj nueisiu“ → „Ar galite dabar prieiti prie routerio?“); spalio skambučiuose atsakymą
  paima modelio skaitymas, bet tai papildomas LLM kvietimas.
- Lėtam internetui kortelės nėra (žr. Problemos radinius).

## Tyrimo radiniai (3.4b 2 dalis — atsakymai žingsniuose, 2026-10-22, netaisyta)

Lentelė `diagnosis/test_steps.py`: žingsnis, kliento žodžiai → ką variklis daro kitame ėjime (visas
ėjimas, be modelio skaitymo). Neperskaitoma ir klausimas kartojamas:

- prieiti prie routerio: „Galiu, tuoj nueisiu“ (girdėta gyvai rugsėjį);
- maitinimo laidas: „Įjungtas“, „Įkišau dabar“.

Perskaitoma neteisingai:

- perkrovimas: „Dar ne“ laikomas atliktu — pereinama prie patikros;
- „Nežinau kada“ (kada galės prieiti) laikomas klausimu modeliui, ne „nežino kada“ (turėtų vesti
  į meistrą);
- lemputės užrašomos teisingai (dega / mirksi / nedega), bet degančios lemputės neatmeta kortelės
  „įrenginio nematyti“ — Case lieka prie jos ir klausia apie maitinimą, nors kortelė sako, kad
  dega = įrenginys gyvas, ieškom laido.

Veikia kaip aprašyta: perkrovimas, kurio linija nematė, prašomas pakartoti vieną kartą; nepadėjus —
išvada ir tiketas; sprendimui nepadėjus du kartus Case ieško kitos kortelės.

# Testai pagal funkcijas (ROADMAP 3.2, 2026-10-21)

Tikslas: testas iš karto pasako, **kuri funkcija** sugedo, žmonių kalba, dar prieš skaitant
traceback'ą. Nuo 3.4a (2026-10-22) **visi** testai yra srities aplanke, failas = funkcija — sričių
žemėlapis [TESTU_ZEMELAPIS.md](TESTU_ZEMELAPIS.md). Pilnai (variantų lentelės, visa fazė, žinomos
spragos) kol kas padaryta **identifikacija**; kitos sritys pildomos 3.4b pagal tą patį šabloną.

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
(`engine_resolve_from_slots`), bet be identifikacijos dialogo. Kitoms fazėms (diagnozė,
tiketas, pabaiga) tokie fiktyvai bus pridėti 3.4 etape.

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

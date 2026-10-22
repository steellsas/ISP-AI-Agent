"""Identifikacija — tests by function (ROADMAP 3.2; docs/testing/IDENT_TESTAI.md).

One file per ability, variants as tables:

    test_address_reading.py   Adreso supratimas      what the caller's words say (NLU)
    test_address_memory.py    Adreso atmintis        slots across turns
    test_street_search.py     Gatvės paieška         the street in the registry
    test_street_unclear.py    Neaiški gatvė          spelling, honest "no such street"
    test_city_search.py       Vietovės paieška       city, village, district, not served
    test_house_search.py      Namo paieška
    test_apartment_search.py  Buto paieška
    test_contracts.py         Kelios sutartys name   surname
    test_account_code.py      Abonento kodas
    test_phone_lookup.py      Paieška pagal numerį   the offer from the caller's phone
    test_confirmation.py      Patvirtinimas          nothing before „taip"; the gate
    test_caller_name.py       Kas skambina           name, holder check (privacy)
    test_no_address.py        Kai adreso nėra        warning, code, polite close
    test_address_change.py    Adreso keitimas        after identification
    test_policy.py            Nustatymai             identification.yaml knobs
    test_phase.py             Visa fazė              T-1…T-12 through the real graph

`pytest -m identification` runs the area; the report after the run lists each function.
"""

AREA = "Identifikacija"
MARK = "identification"

# The order the report lists them in — the order a call meets them.
FUNCTIONS = (
    "Paieška pagal numerį",
    "Adreso supratimas",
    "Adreso atmintis",
    "Vietovės paieška",
    "Gatvės paieška",
    "Neaiški gatvė",
    "Namo paieška",
    "Buto paieška",
    "Kelios sutartys name",
    "Abonento kodas",
    "Patvirtinimas",
    "Kas skambina",
    "Kai adreso nėra",
    "Adreso keitimas",
    "Nustatymai",
    "Visa fazė",
)

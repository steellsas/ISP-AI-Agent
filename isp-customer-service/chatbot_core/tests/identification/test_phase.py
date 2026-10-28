"""Visa fazė — identification from the first words to the identified customer, through the real
graph (docs/testing/IDENT_TESTAI.md T-1…T-12). The speaking LLM is faked (tests/phases.py):
where the next step depends on the question the model asked, the row gives that line (`llm=`).

A row is: the caller's number, the turns [(said, the model's line or None)], and the expected
end: the customer committed (or None), plus words the agent's last reply must contain.
"""

import pytest

FUNCTION = "Visa fazė"

SURNAME_Q = "Šiuo adresu kelios sutartys. Kokia jūsų pavardė?"
FLAT_Q = "Koks jūsų buto numeris?"

FLOWS = [
    pytest.param(
        "+37060020112",
        [("Laba diena, neveikia internetas", None), ("Taip", None)],
        "CUST112",
        "koks jūsų vardas",
        id="T-1 žinomas numeris, pasiūlytas adresas, taip",
    ),
    pytest.param(
        "+37060020112",
        [
            ("Neveikia internetas", None),
            ("Ne, skambinu dėl kito adreso — Tilžės gatvė 60", None),
            ("butas 3", None),
            ("Taip", None),
        ],
        "CUST101",
        "Tilžės g. 60-3",
        id="T-2 žinomas numeris, bet kitas adresas",
    ),
    pytest.param(
        "unknown",
        [
            ("Sveiki, nėra interneto", None),
            ("S. Dariaus ir Girėno gatvė", None),
            ("25 namas", None),
            ("butas 45", None),
            ("Taip", None),
        ],
        "CUST104",
        "koks jūsų vardas",
        id="T-3 adresas dalimis",
    ),
    pytest.param(
        "unknown",
        [
            ("Neveikia internetas", None),
            ("Vilniaus gatvė 39", None),
            ("A, atsiprašau — 29", None),
            ("Taip", None),
        ],
        "CUST009",
        "Vilniaus g. 29",
        id="T-4 klaidingas namas ir pataisymas, be buto klausimo",
    ),
    pytest.param(
        "unknown",
        [
            ("Neveikia internetas", None),
            ("Nepamenu tikslaus adreso, čia ne mano butas", None),
            ("nežinau", None),
            ("Turiu — AB-10104", None),
            ("Taip", None),
        ],
        "CUST104",
        "koks jūsų vardas",
        id="T-10 abonento kodas",
    ),
    pytest.param(
        "+37060012353",
        [("Neveikia internetas", None), ("Taip", None)],
        "CUST009",
        "koks jūsų vardas",
        id="T-12 savininko numeris, taip",
    ),
    pytest.param(
        "unknown",
        [
            ("Neveikia internetas", None),
            ("Tilžės gatvė 60", FLAT_Q),
            ("butas trys", None),
            ("Taip", None),
        ],
        "CUST101",
        "",
        id="T-9b butas žodžiu po buto klausimo",
    ),
    pytest.param(
        "unknown",
        [
            ("Neveikia internetas", None),
            ("Tilžės gatvė 60", FLAT_Q),
            ("Trečias", None),
            ("Taip", None),
        ],
        "CUST101",
        "",
        id="T-9b tik skaičius po buto klausimo",
    ),
    pytest.param(
        "unknown",
        [
            ("Internetas dingo", None),
            (
                "Šiauliai, Žeimių gatvė 12, butas 6",
                "Žeimių gatvę randu Ginkūnuose, Šiaulių rajone — ar ten skambinate?",
            ),
            ("Taip, Ginkūnuose", None),
            ("Taip", None),
        ],
        "CUST109",
        "",
        id="T-5 gatvė kitame kaime",
    ),
    # Live 2026-10-28 (Dainų g. 5-5, unknown number): the digits heard several ways, an
    # unclear answer to the confirm, a number in passing.
    pytest.param(
        "unknown",
        [("Neveikia internetas", None), ("Dainų gatvė 5 5", None), ("Taip", None)],
        "CUST102",
        "koks jūsų vardas",
        id="5 5 — namas 5, butas 5",
    ),
    pytest.param(
        "unknown",
        [("Neveikia internetas", None), ("Dainų gatvė 5, butas 55", None), ("Taip", None)],
        "CUST102",
        "koks jūsų vardas",
        id="butas 55 — rastas butas 5",
    ),
    pytest.param(
        "unknown",
        [
            ("Neveikia internetas", None),
            ("Dainų 5-5", None),
            ("Haloo!", None),
            ("Teisingai.", None),
        ],
        "CUST102",
        "koks jūsų vardas",
        id="neaiškus atsakymas — klausiama dar kartą",
    ),
    pytest.param(
        "unknown",
        [
            ("Neveikia internetas", None),
            ("Dainų 5-5", None),
            ("Taip, girdžiu, patvirtinu 2 kartus", None),
        ],
        "CUST102",
        "koks jūsų vardas",
        id="skaičius patvirtinime nekeičia adreso",
    ),
    pytest.param(
        "unknown",
        [
            ("Neveikia internetas", None),
            ("Dainų gatvė", None),
            ("5", None),
            ("5", None),
            ("Taip", None),
        ],
        "CUST102",
        "koks jūsų vardas",
        id="adresas dalimis, butas tik skaičiumi",
    ),
    pytest.param(
        "unknown",
        [
            ("Neveikia internetas", None),
            ("Dainų 5-5", None),
            ("Ne.", None),
            ("Dainų gatvė 5 butas 5", None),
            ("Taip", None),
        ],
        "CUST102",
        "koks jūsų vardas",
        id="ne — adresas iš naujo",
    ),
    # --- known gaps: the engine does not yet do what the standard says ---------------------
    pytest.param(
        "unknown",
        [
            ("Nerodo internetas", None),
            ("Dainų gatvė 7", SURNAME_Q),
            ("Petraitis", None),
            ("Taip", None),
        ],
        "CUST107",
        "",
        id="T-6 dvi sutartys, pavardė",
        marks=pytest.mark.xfail(strict=True, reason="pavardė į paiešką nepatenka"),
    ),
]


@pytest.mark.parametrize(("phone", "turns", "customer", "said"), FLOWS)
def test_identification_flow(call, phone, turns, customer, said):
    """Identifikacijos eiga"""
    c = call(phone)
    for text, llm in turns:
        c.say(text, llm=llm)
    assert c.identity.customer_id == customer
    assert c.identity.address_confirmed is True
    assert said.lower() in c.replies[-1].lower()


def test_t1_the_name_is_asked_and_kept(call):
    """T-1 vardas po patvirtinimo"""
    c = call("+37060020112")
    c.say("Laba diena, neveikia internetas")
    c.say("Taip")
    c.say("Paulius")
    assert c.identity.caller_name == "Paulius"
    assert c.rule == "identification.result_to_procedure"  # the finding comes next


def test_t11_a_city_we_do_not_serve_is_said_at_once(call):
    """T-11 neaptarnaujamas miestas — iš karto"""
    c = call()
    c.say("Neveikia internetas")
    reply = c.say("Kaunas, Laisvės alėja 5")
    assert "Šiaulių mieste ir rajone" in reply
    assert c.identity.customer_id is None and c.identity.address_empty_turns == 0


def test_t12_the_holders_name_is_never_said(call):
    """T-12 savininko vardas neištariamas"""
    c = call("+37060012353")  # the holder is Giedrius Giedraitis
    c.say("Neveikia internetas")
    c.say("Taip")
    reply = c.say("Petras, aš sutarties savininkas")
    assert "ar teisingai išgirdau" in reply.lower() and "Petras" in reply
    c.say("Taip, žmonos vardu")
    assert c.identity.caller_relation == "family"
    heard = c.heard_everything()
    assert "Giedri" not in heard and "Giedraitis" not in heard


def test_t8_another_address_is_taken_only_after_a_yes(call):
    """T-8 adreso keitimas tik patvirtinus"""
    c = call("+37060020112")
    for text in ("Neveikia internetas", "Taip", "Paulius"):
        c.say(text)
    reply = c.say("Atsiprašau, sumaišiau — iš tikrųjų skambinu dėl Tilžės gatvės 60")
    assert "KITO adreso" in reply and c.identity.customer_id == "CUST112"  # asked, not switched
    c.say("Taip")
    assert c.identity.customer_id is None  # identification opens again


def test_a2rb_the_current_address_is_told(call):
    """A-2R-b „dėl kokio adreso kalbame?“"""
    c = call("+37060020112")
    for text in ("Neveikia internetas", "Taip", "Paulius"):
        c.say(text)
    reply = c.say("Dėl kokio adreso mes dabar bendraujame?")
    assert "Vilniaus g. 33-2" in reply and c.rule == "identification.address_info"


@pytest.mark.xfail(
    strict=True,
    reason="įspėjama po 3-io tuščio atsakymo (ne po 2), uždaroma tik po aiškaus „neturiu“",
)
def test_t7_no_address_warns_after_two_and_closes_after_four(call):
    """T-7 be adreso: įspėjimas po 2, uždarymas po 4"""
    c = call()
    c.say("Neveikia internetas")
    c.say("Nežinau adreso, ne namie esu")
    warned = c.say("Negaliu dabar pasakyt")
    assert "negalėsiu" in warned
    c.say("Na nežinau tikrai")
    c.say("Nieko nepasakysiu")
    assert c.state.closing.case_closed and c.state.ticket.ticket_id is None


def test_the_found_address_is_confirmed_in_the_engines_words(call):
    """Rastas adresas tvirtinamas variklio žodžiais"""
    c = call()
    c.say("Neveikia internetas")
    reply = c.say("Dainų gatvė 5 5")
    assert reply == "Ar teisingai supratau — Šiauliai, Dainų g. 5, butas 5?"
    assert c.rule == "identification.address_heard_confirm"


def test_an_unclear_answer_asks_again_then_offers_the_code(call):
    """Neaiškus atsakymas: dar kartą, po trijų — abonento kodas"""
    c = call()
    c.say("Neveikia internetas")
    c.say("Dainų 5-5")
    for unclear in ("Haloo!", "Nesuprantu"):
        assert "Ar teisingai supratau — Šiauliai, Dainų g. 5, butas 5?" in c.say(unclear)
        assert c.identity.profile.house.value == "5" and c.identity.profile.apartment.value == "5"
    assert "abonento kodą" in c.say("Ką?")
    assert c.identity.account_code_mode is True
    c.say("AB-10102")
    c.say("Taip")
    assert c.identity.customer_id == "CUST102"


def test_a_corrected_flat_changes_only_the_flat(call):
    """„Ne, butas 25“ keičia tik butą"""
    c = call()
    c.say("Neveikia internetas")
    c.say("Dainų 5-5")
    c.say("Ne, butas 25")
    p = c.identity.profile
    assert (p.street.value, p.house.value, p.apartment.value) == ("Dainų g.", "5", "25")
    assert c.identity.customer_id is None

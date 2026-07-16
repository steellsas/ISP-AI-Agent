"""
Address resolver — rich-result customer lookup for voice identification.

Contract: chatbot_core/docs/kliento_identifikacijos_dizainas.md §8.2.

The tool does not just search: it returns a DIAGNOSIS of where the address
mismatched (city / street / house / apartment) plus alternatives, so the agent
can ask exactly the right clarifying question in one turn. Partial input is
allowed by design — the agent verifies each level as soon as it has it
("agent as thinker"), so a wrong city or street surfaces before the house
number is even asked.

PII: candidate lists contain only address structure and counts, never names.
The optional `surname` parameter only CONFIRMS (matched true/false) — the
agent never speaks a surname first.
"""

import sys
from pathlib import Path
from typing import Any

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from Levenshtein import ratio
from utils import get_logger

from database import DatabaseConnection

logger = get_logger(__name__)

# Fuzzy thresholds: voice/STT input is noisy, so these are deliberately loose;
# anything between AMBIGUOUS and MATCH becomes a candidate to confirm, not a
# silent accept.
MATCH_THRESHOLD = 0.75
AMBIGUOUS_THRESHOLD = 0.55

# Words that carry no identity in spoken street/locality names.
_STREET_STOPWORDS = {"g", "g.", "gatvė", "gatve", "ir"}
_LOCALITY_STOPWORDS = {"k", "k.", "kaimas", "kaime", "kaimo", "km", "mst", "m", "m."}
_DISTRICT_MARKERS = {"r", "r.", "raj", "raj.", "rajonas", "rajono", "rajone"}


# =============================================================================
# NORMALIZATION + MATCHING
# =============================================================================


def street_tokens(name: str) -> set[str]:
    """
    Spoken-identity token set of a street name.

    Drops initials ("S."), the connector "ir" and the g./gatvė suffix, so
    'S. Dariaus ir S. Girėno g.' -> {'dariaus', 'girėno'} and a caller saying
    "Girėno Dariaus" (any order, no initials) still matches 100%.
    """
    tokens = set()
    for raw in name.lower().replace(",", " ").split():
        token = raw.strip(".")
        if not token or token in _STREET_STOPWORDS:
            continue
        if len(token) == 1:  # initial like "s." / "v."
            continue
        tokens.add(token)
    return tokens


def street_match_score(query: str, candidate: str) -> float:
    """
    max(letter-level Levenshtein, word-set overlap).

    Levenshtein covers short names and typos (Dainų/Dailės); the token-set
    arm covers compound names said in a different order or without initials.
    """
    q_norm = " ".join(sorted(street_tokens(query)))
    c_norm = " ".join(sorted(street_tokens(candidate)))
    if not q_norm or not c_norm:
        return 0.0

    lev = ratio(q_norm, c_norm)

    q_tok, c_tok = street_tokens(query), street_tokens(candidate)
    overlap = len(q_tok & c_tok) / max(len(q_tok), len(c_tok))

    return max(lev, overlap)


def normalize_locality(name: str) -> str:
    """'Bubių kaimas' / 'Bubių k.' -> 'bubių'; 'Šiauliai' -> 'šiauliai'."""
    tokens = [
        t.strip(".")
        for t in name.lower().replace(",", " ").split()
        if t.strip(".") and t.strip(".") not in _LOCALITY_STOPWORDS
    ]
    return " ".join(tokens)


def is_district_reference(name: str) -> bool:
    """True when the customer named a DISTRICT ('Šiaulių rajonas'), not a city."""
    return any(t.strip(".,") in _DISTRICT_MARKERS for t in name.lower().replace(",", " ").split())


def locality_match_score(query: str, candidate: str) -> float:
    """Levenshtein over normalized locality names (handles genitive forms)."""
    q, c = normalize_locality(query), normalize_locality(candidate)
    if not q or not c:
        return 0.0
    return ratio(q, c)


def best_village_token_match(city_in: str, localities: list[dict]) -> tuple[float, dict | None]:
    """
    Best per-token match against DISTRICT villages.

    Handles 'Šiaulių rajonas, Bubių kaimas' arriving as one city string: the
    full-string match fails, but the token 'bubių' matches the village Bubiai.
    Only district-located villages are considered — the district marker in the
    phrase says the customer means the rajonas, not the city itself.
    """
    tokens = [
        t.strip(".")
        for t in city_in.lower().replace(",", " ").split()
        if t.strip(".")
        and t.strip(".") not in _DISTRICT_MARKERS
        and t.strip(".") not in _LOCALITY_STOPWORDS
        and len(t.strip(".")) > 2
    ]
    best: tuple[float, dict | None] = (0.0, None)
    for token in tokens:
        for loc in localities:
            if not loc["district"]:
                continue
            score = ratio(token, loc["city"].lower())
            if score > best[0]:
                best = (score, loc)
    return best


# =============================================================================
# RESOLVER
# =============================================================================


def _known_localities(db: DatabaseConnection) -> list[dict]:
    """All localities we serve: city + district from the streets reference."""
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT city, MAX(district) AS district
            FROM streets GROUP BY city
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def _streets_in_city(db: DatabaseConnection, city: str) -> list[str]:
    """Reference street names for a city (with their spoken 'g.' suffix)."""
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT street_name, street_type FROM streets
            WHERE LOWER(city) = LOWER(?)
            """,
            (city,),
        )
        rows = cursor.fetchall()
    return [f"{r['street_name']} {r['street_type'] or 'g.'}".strip() for r in rows]


def _street_everywhere(db: DatabaseConnection, street: str) -> list[dict]:
    """Localities where a street with this (fuzzy) name exists."""
    with db.cursor() as cursor:
        cursor.execute("SELECT city, district, street_name, street_type FROM streets")
        rows = [dict(r) for r in cursor.fetchall()]
    hits = []
    for r in rows:
        full = f"{r['street_name']} {r['street_type'] or 'g.'}".strip()
        if street_match_score(street, full) >= MATCH_THRESHOLD:
            hits.append({"city": r["city"], "district": r["district"], "street": full})
    return hits


def _houses_on_street(db: DatabaseConnection, city: str, street: str) -> list[str]:
    """Actual house numbers on a street (from real service addresses)."""
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT house_number FROM addresses
            WHERE LOWER(city) = LOWER(?) AND LOWER(street) = LOWER(?)
            """,
            (city, street),
        )
        return [row["house_number"] for row in cursor.fetchall()]


def _contracts_at_house(db: DatabaseConnection, city: str, street: str, house: str) -> list[dict]:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.customer_id, c.last_name, a.apartment_number, a.full_address
            FROM addresses a JOIN customers c ON c.customer_id = a.customer_id
            WHERE LOWER(a.city) = LOWER(?) AND LOWER(a.street) = LOWER(?)
              AND LOWER(a.house_number) = LOWER(?)
            """,
            (city, street, house),
        )
        return [dict(row) for row in cursor.fetchall()]


def _recover_city_by_street(
    db: DatabaseConnection, street: str, house: str
) -> dict[str, Any] | None:
    """
    Recover the locality from the STREET when the spoken city isn't one we serve.

    We only serve the Šiauliai region, so an out-of-area city ('Vilnius') is
    almost always an STT mishearing of a stray word — but the street + house can
    still pin the real address. Recovers ONLY when BOTH a street and a house are
    given, the street matches exactly one served locality at >= 0.9, AND the
    house exists on that street — so a misheard street can't silently snap to a
    real address, and a street-only utterance never auto-recovers.

    Returns {city, district, street} or None (stay safe → ask the caller).
    """
    if not street or not house:
        return None
    strong = [
        hit
        for hit in _street_everywhere(db, street)
        if street_match_score(street, hit["street"]) >= 0.9
    ]
    if len({hit["city"].lower() for hit in strong}) != 1:
        return None  # zero or several localities → not unique, don't guess
    hit = strong[0]
    houses = _houses_on_street(db, hit["city"], hit["street"])
    if not any(h.lower() == house.lower() for h in houses):
        return None  # street matches but the house doesn't → likely wrong street
    return hit


def resolve_address(db: DatabaseConnection, args: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve a (possibly partial) spoken address into a customer.

    Args keys (all optional strings): city, street, house_number,
    apartment_number, surname.

    Returns the §8.2 envelope: {success, customer_id, resolution: {city,
    street, house, apartment}, hint} — `hint` is a short Lithuanian
    instruction telling the agent what to clarify next.
    """
    city_in = (args.get("city") or "").strip()
    street_in = (args.get("street") or "").strip()
    house_in = (args.get("house_number") or "").strip()
    apartment_in = (args.get("apartment_number") or "").strip()
    surname_in = (args.get("surname") or "").strip()

    logger.info(
        f"Resolving address: city={city_in!r} street={street_in!r} "
        f"house={house_in!r} apt={apartment_in!r} surname={'<given>' if surname_in else ''}"
    )

    resolution: dict[str, Any] = {
        "city": {"given": city_in or None, "status": "skipped"},
        "street": {"given": street_in or None, "status": "skipped"},
        "house": {"given": house_in or None, "status": "skipped"},
        "apartment": {"given": apartment_in or None, "status": "skipped"},
    }
    envelope: dict[str, Any] = {
        "success": False,
        "customer_id": None,
        "resolution": resolution,
        "hint": "",
    }

    try:
        localities = _known_localities(db)

        # ---- CITY ----------------------------------------------------------
        city = None
        if not city_in:
            # STREET-FIRST: no city given. We serve one region, so the locality
            # falls out of the street — search it across served localities and
            # DERIVE the city (ask only if the street spans several). Avoids the
            # redundant "miestą, gatvę, namą, butą" recital and scales: the same
            # street in two cities just triggers a "which one?" question.
            if not street_in:
                envelope["hint"] = "Paklausk gatvės."
                resolution["street"]["status"] = "not_given"
                return envelope
            hits = _street_everywhere(db, street_in)
            cities = sorted({h["city"] for h in hits})
            if len(cities) == 1:
                hit = hits[0]
                city = hit["city"]
                resolution["city"].update(
                    {"status": "derived", "matched": city, "district": hit["district"]}
                )
            elif len(cities) > 1:
                resolution["city"].update(
                    {
                        "status": "ambiguous",
                        "candidates": [
                            {
                                "city": c,
                                "district": next(h["district"] for h in hits if h["city"] == c),
                            }
                            for c in cities
                        ],
                    }
                )
                envelope["hint"] = (
                    "Tokia gatvė yra keliose vietovėse — paklausk kurioje: "
                    + ", ".join(cities)
                    + "."
                )
                return envelope
            else:
                resolution["street"].update({"status": "not_found"})
                envelope["hint"] = (
                    "Tokios gatvės aptarnaujamose vietovėse nerandu. Atkartok, kaip "
                    "supratai, ir patikslink gatvę."
                )
                return envelope

        # District phrase may carry the village inside it ("Šiaulių rajonas,
        # Bubių kaimas") — extract it token-wise before declaring ambiguity.
        if is_district_reference(city_in):
            tok_score, tok_loc = best_village_token_match(city_in, localities)
            # 0.7 (not MATCH_THRESHOLD): spoken village names arrive in the
            # genitive ("Bubių kaimas" vs the locality "Bubiai" ≈ 0.73).
            if tok_score >= 0.7 and tok_loc is not None:
                city = tok_loc["city"]
                resolution["city"].update(
                    {"status": "ok", "matched": city, "district": tok_loc["district"]}
                )

        if city is None:
            district_only = is_district_reference(city_in) and not any(
                locality_match_score(city_in, loc["city"]) >= MATCH_THRESHOLD for loc in localities
            )
            if district_only:
                # 'Šiaulių rajonas' names the district, not a locality -> which village?
                villages = [
                    {"city": loc["city"], "district": loc["district"]}
                    for loc in localities
                    if loc["district"] and locality_match_score(city_in, loc["district"]) >= 0.5
                ]
                resolution["city"].update({"status": "ambiguous", "candidates": villages})
                names = ", ".join(v["city"] for v in villages) or "—"
                envelope["hint"] = f"Pasakytas rajonas, ne vietovė. Paklausk kurio kaimo: {names}."
                return envelope

            scored = [(locality_match_score(city_in, loc["city"]), loc) for loc in localities]
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_loc = scored[0] if scored else (0.0, None)

            if best_score < AMBIGUOUS_THRESHOLD or best_loc is None:
                # City unrecognized (we serve only the Šiauliai region, so this
                # is usually an STT mishearing). Try to recover it from the
                # street+house before dead-ending.
                recovered = _recover_city_by_street(db, street_in, house_in)
                if recovered is None:
                    resolution["city"].update(
                        {
                            "status": "not_found",
                            "candidates": [
                                {"city": loc["city"], "district": loc["district"]}
                                for s, loc in scored[:4]
                                if s >= 0.4
                            ],
                        }
                    )
                    envelope["hint"] = (
                        f"Vietovės '{city_in}' neaptarnaujame arba nesupratau pavadinimo "
                        "(aptarnaujame tik Šiaulių regioną). Atkartok klientui, kaip "
                        "supratai, ir paprašyk patikslinti."
                    )
                    return envelope

                city = recovered["city"]
                resolution["city"].update(
                    {
                        "status": "recovered",
                        "given": city_in,
                        "matched": city,
                        "district": recovered["district"],
                    }
                )
            else:
                city = best_loc["city"]
                resolution["city"].update(
                    {"status": "ok", "matched": city, "district": best_loc["district"]}
                )

        # ---- STREET --------------------------------------------------------
        if not street_in:
            envelope["hint"] = f"Vietovė {city} aiški. Paklausk gatvės."
            resolution["street"]["status"] = "not_given"
            return envelope

        streets = _streets_in_city(db, city)
        street_scored = sorted(
            ((street_match_score(street_in, s), s) for s in streets),
            key=lambda x: x[0],
            reverse=True,
        )
        top = [s for s in street_scored if s[0] >= MATCH_THRESHOLD]
        close = [s for s in street_scored if AMBIGUOUS_THRESHOLD <= s[0] < MATCH_THRESHOLD]

        # A STRONG hit in another locality must beat a WEAK guess in this city:
        # the caller saying "Žeimių" in Šiauliai is a city mix-up (exact street
        # in Ginkūnai), not a garbled "Žemaitės".
        elsewhere_strong = [
            hit
            for hit in _street_everywhere(db, street_in)
            if hit["city"].lower() != city.lower()
            and street_match_score(street_in, hit["street"]) >= 0.9
        ]
        close_best = close[0][0] if close else 0.0

        if len(top) == 1 or (top and top[0][0] - (top[1][0] if len(top) > 1 else 0) > 0.1):
            street = top[0][1]
            resolution["street"].update({"status": "ok", "matched": street})
        elif not top and elsewhere_strong and (close_best + 0.2 < 0.9):
            resolution["street"].update(
                {
                    "status": "not_in_city",
                    "found_elsewhere": elsewhere_strong,
                    "fuzzy_candidates": [s for _, s in close[:2]],
                }
            )
            alt = elsewhere_strong[0]
            where = f"{alt['city']}" + (f" ({alt['district']})" if alt["district"] else "")
            envelope["hint"] = (
                f"Tokios gatvės {city} nėra, bet {alt['street']} yra {where} — "
                "pasiūlyk klientui patikslinti vietovę."
            )
            return envelope
        elif top or close:
            cands = [s for _, s in (top + close)[:3]]
            resolution["street"].update({"status": "unclear", "fuzzy_candidates": cands})
            envelope["hint"] = "Gatvė neaiški — pasiūlyk pasirinkimą: " + " ar ".join(cands) + "?"
            return envelope
        else:
            elsewhere = [
                hit
                for hit in _street_everywhere(db, street_in)
                if hit["city"].lower() != city.lower()
            ]
            resolution["street"].update({"status": "not_in_city", "found_elsewhere": elsewhere})
            if elsewhere:
                alt = elsewhere[0]
                where = f"{alt['city']}" + (f" ({alt['district']})" if alt["district"] else "")
                envelope["hint"] = (
                    f"Tokios gatvės {city} nėra, bet {alt['street']} yra {where} — "
                    "pasiūlyk klientui patikslinti vietovę."
                )
            else:
                envelope["hint"] = (
                    f"Tokios gatvės nei {city}, nei kitose aptarnaujamose vietovėse "
                    "nerandu. Atkartok, kaip supratai, ir paprašyk patikslinti."
                )
            return envelope

        # ---- HOUSE ---------------------------------------------------------
        if not house_in:
            envelope["hint"] = f"{street}, {city} — aišku. Paklausk namo numerio."
            resolution["house"]["status"] = "not_given"
            return envelope

        houses = _houses_on_street(db, city, street)
        house = next((h for h in houses if h.lower() == house_in.lower()), None)

        if house is None:
            # Same street + house in another locality? (city/district mix-up)
            elsewhere = []
            for hit in _street_everywhere(db, street):
                if hit["city"].lower() == city.lower():
                    continue
                if any(
                    h.lower() == house_in.lower()
                    for h in _houses_on_street(db, hit["city"], hit["street"])
                ):
                    elsewhere.append(hit)
            resolution["house"].update(
                {"status": "not_found", "found_elsewhere": elsewhere, "known_houses": houses}
            )
            if elsewhere:
                alt = elsewhere[0]
                where = f"{alt['city']}" + (f" ({alt['district']})" if alt["district"] else "")
                envelope["hint"] = (
                    f"{street} {house_in} {city} nėra, bet toks namas yra {where} — "
                    "gal sumaišyta vietovė? Pasiūlyk."
                )
            else:
                envelope["hint"] = (
                    f"Namo {house_in} gatvėje {street} ({city}) nerandu. Perklausk TIK namo numerį."
                )
            return envelope

        resolution["house"].update({"status": "ok", "matched": house})

        # ---- APARTMENT + CONTRACTS ------------------------------------------
        contracts = _contracts_at_house(db, city, street, house)
        if not contracts:
            resolution["apartment"]["status"] = "no_contracts"
            envelope["hint"] = (
                "Adresas egzistuoja, bet aktyvios sutarties juo nėra. "
                "Patikslink adresą arba pasiūlyk abonento kodą."
            )
            return envelope

        if apartment_in:
            matches = [
                c
                for c in contracts
                if (c["apartment_number"] or "").lower() == apartment_in.lower()
            ]
            if not matches:
                resolution["apartment"].update(
                    {"status": "not_found", "contracts_count": len(contracts)}
                )
                envelope["hint"] = (
                    f"Buto {apartment_in} šiame name nerandu. Perklausk TIK buto numerį."
                )
                return envelope
            resolution["apartment"].update({"status": "ok"})
        else:
            no_apt = [c for c in contracts if not c["apartment_number"]]
            if len(contracts) == 1 and contracts[0]["apartment_number"]:
                # A single flat at this house still needs the caller to SAY the
                # apartment: filling it in from the DB would reveal an address part
                # they never gave (anyone could probe addresses). A house without a
                # flat number resolves as-is — there is nothing to reveal.
                resolution["apartment"].update({"status": "required", "contracts_count": 1})
                envelope["hint"] = (
                    "Šiuo adresu sutartis bute — paklausk buto numerio. NEsakyk jo pats."
                )
                return envelope
            if len(contracts) == 1:
                matches = contracts
                resolution["apartment"]["status"] = "ok"
            elif len(no_apt) == 1 and len(contracts) == len(no_apt):
                matches = no_apt
                resolution["apartment"]["status"] = "ok"
            else:
                # several contracts; maybe surname disambiguates (house w/o flats)
                matches = contracts
                if not surname_in:
                    resolution["apartment"].update(
                        {"status": "required", "contracts_count": len(contracts)}
                    )
                    has_flats = any(c["apartment_number"] for c in contracts)
                    envelope["hint"] = "Šiuo adresu kelios sutartys — paklausk " + (
                        "buto numerio." if has_flats else "pavardės (klientas sako, tu patvirtini)."
                    )
                    return envelope

        # ---- SURNAME CONFIRM -------------------------------------------------
        if surname_in:
            surname_hits = [
                c
                for c in matches
                if ratio(surname_in.lower(), (c["last_name"] or "").lower()) >= 0.8
            ]
            if len(surname_hits) == 1:
                matches = surname_hits
                resolution["surname_matched"] = True
            elif not surname_hits:
                resolution["surname_matched"] = False
                resolution["apartment"].setdefault("contracts_count", len(matches))
                envelope["hint"] = (
                    "Pavardė nesutampa su sutartimi šiuo adresu. NEATSKLEISK "
                    "registruotos pavardės — paprašyk patikslinti adresą ar pavardę."
                )
                return envelope
            else:
                matches = surname_hits

        if len(matches) > 1:
            resolution["apartment"].update({"status": "required", "contracts_count": len(matches)})
            envelope["hint"] = "Vis dar kelios sutartys — paklausk buto numerio arba pavardės."
            return envelope

        # ---- SUCCESS ---------------------------------------------------------
        found = matches[0]
        envelope.update(
            {
                "success": True,
                "customer_id": found["customer_id"],
                "hint": f"Radau sutartį adresu {found['full_address']} — patvirtink adresą klientui.",
            }
        )
        logger.info(f"Address resolved -> {found['customer_id']}")
        return envelope

    except Exception as e:
        logger.error(f"Error in resolve_address: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida: {str(e)}",
            "resolution": resolution,
            "hint": "Techninė klaida — atsiprašyk ir pasiūlyk abonento kodą.",
        }


# =============================================================================
# ACCOUNT CODE LOOKUP (fastest path when the customer knows it)
# =============================================================================


def lookup_customer_by_account_code(db: DatabaseConnection, account_code: str) -> dict[str, Any]:
    """Direct lookup by the invoice account code (abonento kodas)."""
    code = (account_code or "").strip().upper()
    logger.info(f"Looking up customer by account code: {code}")

    if not code:
        return {"success": False, "error": "missing_account_code", "message": "Kodas tuščias"}

    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT customer_id FROM customers WHERE UPPER(account_code) = ?",
                (code,),
            )
            row = cursor.fetchone()

        if not row:
            return {
                "success": False,
                "error": "customer_not_found",
                "message": f"Klientas su abonento kodu {code} nerastas",
            }

        return {"success": True, "customer": {"customer_id": dict(row)["customer_id"]}}

    except Exception as e:
        logger.error(f"Error in lookup_customer_by_account_code: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}

"""Identification execution — the caller-ID phone preflight lookup and the address
lookup's diagnosis note."""

from __future__ import annotations

from typing import Any


def preflight_phone(state: Any, rt: Any) -> None:
    """Look up the caller's number at the START of the call (deterministic).

    Runs once, in code (not via the LLM), so by the customer's first turn the
    phone account — if any — is already known and the agent can offer its
    address for confirmation without a tool round-trip. Stored as an
    UNCONFIRMED candidate (anchor rule), never as a confirmed customer.
    """
    phone = state.identity.caller_phone
    if not phone or phone == "unknown":
        return
    state.identity.preflight_done = True
    try:
        result = rt.tools.run(
            state, rt, "find_customer", {"phone": phone}, reason="preflight_phone", apply=False
        ).data
    except Exception:
        return
    if not result.get("success"):
        rt.tracer.emit("preflight", found=False)
        return
    addresses = result.get("addresses") or []
    primary = next(
        (a for a in addresses if a.get("is_primary")),
        addresses[0] if addresses else {},
    )
    state.identity.phone_candidate = {
        "customer_id": result.get("customer_id"),
        "name": result.get("name"),
        "address": primary.get("full_address"),
        # Structured parts for the phone cross-check: if the caller names this
        # street, offer the full address to confirm instead of making them
        # dictate the house/apartment (spoken numbers are STT-fragile).
        "city": primary.get("city"),
        "street": primary.get("street"),
        "house": primary.get("house_number"),
        "apartment": primary.get("apartment_number"),
    }
    rt.tracer.emit("preflight", found=True, customer_id=result.get("customer_id"))

    # Proactive mass-outage awareness (roadmap 6b): if this caller's street
    # has an active outage, remember it so the FIRST reply can inform right
    # away — no full identification needed (everyone at that street is down).
    try:
        outage = rt.tools.run(
            state,
            rt,
            "check_outages",
            {"customer_id": result.get("customer_id")},
            reason="preflight_outage",
            apply=False,
        ).data
    except Exception:
        return
    if outage.get("affected") and outage.get("active_outages"):
        first = outage["active_outages"][0]
        eta = first.get("estimated_resolution") or ""
        state.identity.preflight_outage = {
            "street": first.get("street"),
            "eta": eta[11:16] if len(eta) >= 16 else eta,  # HH:MM, voice-friendly
            "description": first.get("description"),
        }
        rt.tracer.emit("preflight_outage", street=first.get("street"))


def address_diag_note(obs: dict) -> str | None:
    """F2 (Andrius 2026-08-20): a FAILED address lookup must tell the caller
    exactly what WAS found and what was not — 'Vilniaus gatvę randu, bet 39
    numerio nematau' lets the caller correct themselves. Composed from the
    resolver's per-level diagnosis into a narrator directive; None when there
    is nothing more specific than the generic re-ask."""
    res = obs.get("resolution") or {}
    city = res.get("city") or {}
    street = res.get("street") or {}
    house = res.get("house") or {}
    place = city.get("matched") or city.get("given") or ""
    vieta = f" mieste {place}" if place else ""
    bits: list[str] = []
    st = street.get("status")
    if st in ("not_found", "not_in_city"):
        g = street.get("given") or "nurodytos gatvės"
        line = f"gatvės „{g}“{vieta} NERANDU"
        elsewhere = street.get("found_elsewhere") or []
        if elsewhere:
            kur = ", ".join(str(e.get("city") or e) for e in elsewhere[:3])
            line += f", bet tokia gatvė yra: {kur} — paklausk, ar ne ten"
        else:
            line += " (gal ji vadinasi kitaip? pavadinimai keičiasi)"
        bits.append(line)
    elif st == "unclear" and street.get("fuzzy_candidates"):
        cands = ", ".join(str(c) for c in street["fuzzy_candidates"][:3])
        bits.append(f"gatvės neišgirdau tiksliai — panašios: {cands}; paklausk, kuri")
    elif st in ("ok", "derived", "recovered") and house.get("status") == "not_found":
        g = street.get("matched") or street.get("given") or "gatvę"
        line = f"gatvę {g}{vieta} RANDU, bet namo {house.get('given')} numerio NĖRA"
        known = house.get("known_houses") or []
        if known:
            line += f" (toje gatvėje yra: {', '.join(str(h) for h in known[:6])})"
        line += " — paprašyk patikslinti namo numerį"
        bits.append(line)
    elif city.get("status") == "ambiguous":
        alts = city.get("alternatives") or city.get("candidates") or []
        kur = ", ".join(str(a.get("city") if isinstance(a, dict) else a) for a in alts[:3])
        bits.append(f"tokia gatvė yra keliuose miestuose ({kur}) — paklausk, kuriame")
    if not bits:
        return None
    return (
        "- ADRESO PAIEŠKOS DIAGNOZĖ (pasakyk klientui BŪTENT tai — kas rasta ir ko "
        "ne, savais žodžiais, trumpai — ir paprašyk patikslinti TIK trūkstamą "
        "dalį): " + "; ".join(bits) + ". Neišgalvok adresų."
    )

"""
Verdict glossaries — the caller-facing Lithuanian wording for verdict keys.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved out of react_agent.py so
both the narrator facts block and the ticket flow read one source. Data only —
no logic.
"""

# Short Lithuanian gloss for each verdict reason, surfaced in the case-state facts
# block so the agent can reconcile the finding with what the customer says.
DIAGNOSIS_LT = {
    "billing_suspended": "paslauga sustabdyta dėl neapmokėtos sąskaitos",
    # Worded WITHOUT "registruota" — the outage eval guard forbids "registr" (its
    # intent: no TICKET talk for outages) and the scripted news must not trip it.
    "active_outage": "rajone šiuo metu vyksta masinė avarija",
    "switch_unreachable": "tinklo mazgas nepasiekiamas (tiekėjo gedimas)",
    "node_fault_unregistered": "mazgo gedimas (neregistruotas)",
    "link_down_local": "ryšys iki kliento įrangos nutrūkęs (maitinimas/laidas)",
    "foreign_mac": "linijoje matomas kitas įrenginys (MAC) nei registruota",
    "crc_errors": "linijos klaidos (CRC) — kabelio/jungties problema",
    "dhcp_silent": "įranga negauna IP (DHCP tyli) — galbūt po gamyklinio atstatymo",
    "no_mac_observed": "linijoje nematoma jokio įrenginio",
    "healthy_to_router": "tinklas iki routerio veikia — problema kliento pusėje",
    "no_port_data": "nėra prievado duomenų",
}

# WHY the ticket is needed, in the caller's words — spoken in the dialogue intro
# ("Registruoju gedimą — reikalingas naujas maršrutizatorius.") and written on the
# ticket. Falls back to the DIAGNOSIS_LT gloss for causes without a need phrase.
TICKET_NEED_LT = {
    "no_mac_observed": "reikalingas naujas maršrutizatorius",
    "link_down_local": "reikia patikrinti liniją iki jūsų buto",
}

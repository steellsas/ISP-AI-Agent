"""Fixtures for the ticket tests."""

import pytest

FIRST = "Taip, galiu."
# A dead router (no device on the line): the findings, the checks, no computer → the ticket.
TO_CONTACTS = [
    "Gerai",
    FIRST,
    FIRST,
    "Nedega nė viena",
    "Maitinimo laidas įkištas tvirtai.",
    "Neturiu kompiuterio.",
    "Taip",
]


@pytest.fixture
def at_contacts(diagnosing):
    """`at_contacts()` → a CallDriver at the contact dialogue: the engine has decided the
    ticket (a dead router, `telefonu_nepataisoma`) and asked whether this number will do."""

    def _make():
        c = diagnosing("no_mac_observed")
        for text in TO_CONTACTS:
            c.say(text)
        assert c.rule == "ticket.phone_intro", "the path no longer reaches the contact dialogue"
        return c

    return _make

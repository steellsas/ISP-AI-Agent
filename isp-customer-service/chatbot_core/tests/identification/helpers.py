"""Shared helpers for the identification tests."""

from tests.calls import make_agent

# A hand-given registry for the pure reader tests (the real one comes from the seed DB).
STREETS = [
    "Tilžės g.",
    "Dainų g.",
    "Dailės g.",
    "Žemaitės g.",
    "S. Dariaus ir S. Girėno g.",
    "Žeimių g.",
    "Aušros g.",
    "Sodo g.",
    "Vilniaus g.",
]
LOCALITIES = ["Šiauliai", "Ginkūnai", "Bubiai", "Vinkšnėnai"]


def agent(phone="unknown"):
    """A new call as `.state` / `.runtime` (node- and rule-level tests)."""
    return make_agent(phone)


def extract(text):
    """The address reader over the hand-given registry."""
    from agent.perceive.nlu import extract_address

    return extract_address(text, STREETS, LOCALITIES)


def read(text):
    """The address reader over the seeded registry."""
    from agent.perceive.nlu import extract_address
    from agent.tooling import LocalToolProvider

    registry = LocalToolProvider().address_registry()
    return extract_address(text, registry.streets, registry.localities)


# The names the moved tests used.
_agent = agent
_extract = extract
_read = read

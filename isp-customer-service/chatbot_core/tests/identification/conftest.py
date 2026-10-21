"""Fixtures for the identification tests."""

import pytest


@pytest.fixture
def resolver(db_connection):
    """resolve_address bound to the seeded test DB: `resolver(street=..., house_number=...)`."""
    from crm_mcp.tools.address_resolver import resolve_address

    def _run(**kwargs):
        return resolve_address(db_connection, kwargs)

    return _run

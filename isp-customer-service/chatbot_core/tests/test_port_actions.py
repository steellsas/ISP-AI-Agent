"""
Tests for the simulated remote actions (update_mac / reset_port).

The stubs mutate the mock DB (approved design), so the key assertion is the
end-to-end effect: after update_mac on the S5a customer a repeated
diagnose_connection no longer reports foreign_mac.

Run: pytest tests/test_port_actions.py -v
"""

import pytest


@pytest.fixture(autouse=True)
def restore_s5a_state(db_connection):
    """
    The stubs intentionally mutate the seeded DB, but the DB is rebuilt once
    per SESSION — later test files (test_verdict's S5a case) expect CUST105
    to still have its foreign-MAC state. Snapshot and restore around each test.
    """
    tables = {
        "ports": ("port_id", "equipment_mac, observed_mac, dhcp_status"),
        "customer_equipment": ("equipment_id", "mac_address"),
        "ip_assignments": ("assignment_id", "mac_address, status"),
    }
    snapshot = {}
    with db_connection.cursor() as cursor:
        for table, (pk, cols) in tables.items():
            cursor.execute(
                f"SELECT {pk}, {cols} FROM {table} WHERE customer_id IN ('CUST104','CUST105')"
            )
            snapshot[table] = [dict(r) for r in cursor.fetchall()]

    yield

    with db_connection.transaction() as cursor:
        for table, (pk, cols) in tables.items():
            for row in snapshot[table]:
                sets = ", ".join(f"{c.strip()} = ?" for c in cols.split(","))
                values = [row[c.strip()] for c in cols.split(",")] + [row[pk]]
                cursor.execute(f"UPDATE {table} SET {sets} WHERE {pk} = ?", values)


class TestUpdateMac:
    def test_s5a_bind_resolves_foreign_mac(self, db_connection):
        """CUST105 (new router, foreign MAC): bind -> diagnosis turns healthy."""
        from agent.tools import diagnose_connection, update_mac

        before = diagnose_connection("CUST105")
        assert before["verdict"]["reason"] == "foreign_mac"
        foreign = before["signals"]["observed_mac"]

        result = update_mac("CUST105")
        assert result["success"] is True
        assert result["new_mac"] == foreign
        assert result["old_mac"] != foreign

        after = diagnose_connection("CUST105")
        assert after["verdict"]["reason"] != "foreign_mac"
        assert after["signals"]["registered_mac"].lower() == foreign.lower()

    def test_updates_crm_equipment_registry(self, db_connection):
        """The CRM-registered router MAC follows the binding."""
        from agent.tools import update_mac

        result = update_mac("CUST105")
        assert result["success"] is True

        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mac_address FROM customer_equipment
                WHERE customer_id = 'CUST105' AND equipment_type = 'router'
                  AND status = 'active'
                """
            )
            row = dict(cursor.fetchone())
        assert row["mac_address"].lower() == result["new_mac"].lower()

    def test_no_observed_mac_is_clean_error(self, db_connection):
        """CUST104's link is down (nothing observed) -> explicit error, no bind."""
        from agent.tools import update_mac

        result = update_mac("CUST104")
        assert result["success"] is False
        assert result["error"] == "no_observed_mac"

    def test_missing_customer_id(self, db_connection):
        from agent.tools import update_mac

        result = update_mac("")
        assert result["success"] is False
        assert result["error"] == "missing_customer_id"


class TestResetPort:
    def test_reset_succeeds_for_known_customer(self, db_connection):
        from agent.tools import reset_port

        result = reset_port("CUST105")
        assert result["success"] is True
        assert result["port_id"]

    def test_unknown_customer(self, db_connection):
        from agent.tools import reset_port

        result = reset_port("CUST999")
        assert result["success"] is False
        assert result["error"] == "no_port_found"

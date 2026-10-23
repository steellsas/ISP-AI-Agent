"""Tiketo tipas — kas važiuoja, kas perskambina, kas tik informuoja (Andrius, 2026-10-22).

A technician only when it is clear why to go to the caller. An unfinished call is reviewed by a
person who phones back; our own network fault needs no home visit.
"""

import re
from pathlib import Path

import pytest

FUNCTION = "Tiketo tipas"

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("cause", "reason", "kind"),
    [
        pytest.param("router_hung", "sprendimas_baigtas", "fault_technician", id="meistras"),
        pytest.param(
            "no_mac_observed", "telefonu_nepataisoma", "equipment_replacement", id="keitimas"
        ),
        pytest.param(
            "switch_unreachable", "musu_tinklo_gedimas", "network_fault", id="mūsų tinklas"
        ),
        pytest.param(
            "node_fault_unregistered", "musu_tinklo_gedimas", "network_fault", id="tinklo mazgas"
        ),
        pytest.param(
            "healthy_to_router", "nebaigtas", "call_unfinished", id="linija veikia, klientui ne"
        ),
        pytest.param("router_hung", "nebaigtas", "call_unfinished", id="nutrūko vidury taisymo"),
        pytest.param("unclear_fault", "neaiskus_gedimas", "fault_unclear", id="neaiškus"),
    ],
)
def test_the_call_decides_the_ticket_type(cause, reason, kind):
    """Gedimas ir priežastis → tiketo tipas"""
    from agent.ticket_types import for_call

    assert for_call(cause, reason) == kind


@pytest.mark.parametrize(
    ("kind", "department"),
    [
        ("fault_technician", "technical"),
        ("equipment_replacement", "technical"),
        ("network_fault", "network"),
        ("call_unfinished", "customer_service"),
        ("fault_unclear", "customer_service"),
        ("billing_request", "billing"),
    ],
)
def test_each_type_goes_to_its_department(kind, department):
    """Tipas → skyrius"""
    from agent import ticket_types

    assert ticket_types.department(kind) == department


def test_the_database_accepts_every_type():
    """DB schema priima kiekvieną žinių tipą"""
    from agent.ticket_types import _catalog

    sql = (ROOT / "database" / "schema" / "crm_schema.sql").read_text(encoding="utf-8")
    allowed = set(re.findall(r"'([a-z_]+)'", re.search(r"ticket_type TEXT[^\n]*", sql).group(0)))
    assert set(_catalog()) <= allowed, set(_catalog()) - allowed


def test_the_outcome_follows_the_ticket_type():
    """Nebaigtas → peržiūrai; mūsų tinklas → informuota; kitas → tiketas"""
    from agent.call_record.outcome import derive

    from tests.calls import make_state

    def outcome(kind):
        s = make_state("+37060012353")
        s.identity.customer_id = "CUST009"
        s.ticket.ticket_id, s.ticket.ticket_type = "T", kind
        o = derive(s)
        return o.outcome, o.needs_review

    assert outcome("call_unfinished") == ("unfinished", True)
    assert outcome("network_fault") == ("informed", False)
    assert outcome("fault_technician") == ("ticket", False)

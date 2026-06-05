"""Tests for PII (phone number) redaction in logs.

Customer phone numbers are direct personal identifiers (GDPR) and must never
land in plain-text logs. These tests lock the contract:
  * Lithuanian phone numbers are masked, keeping only the last 4 digits.
  * Non-PII identifiers (IPs, MAC addresses, CUST/ticket IDs) are NOT touched.
  * Redaction is gated by the REDACT_PII flag so local testing can opt into full
    numbers for traceability while deployed environments stay masked.
"""

import logging
import sys
from pathlib import Path

import pytest

# redact_phone lives in shared/src/utils — add it to the path the same way the
# service modules do.
_SHARED_SRC = Path(__file__).resolve().parents[2] / "shared" / "src"
if str(_SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(_SHARED_SRC))

from utils import redact_phone  # noqa: E402
from utils.logger import PiiRedactionFilter  # noqa: E402


# ---------------------------------------------------------------------------
# Masking: phones are redacted to their last 4 digits
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+37060012345", "***2345"),  # international LT mobile
        ("+37061234567", "***4567"),
        ("861234567", "***4567"),  # local 9-digit form
        ("8 612 34567", "***4567"),  # tolerates spaces
        ("8-612-34567", "***4567"),  # tolerates dashes
    ],
)
def test_phone_is_masked(raw, expected):
    assert redact_phone(raw, enabled=True) == expected


def test_phone_inside_sentence_is_masked():
    out = redact_phone("Klientas skambino iš +37060012345 vakar", enabled=True)
    assert "***2345" in out
    assert "+37060012345" not in out


# ---------------------------------------------------------------------------
# Non-PII identifiers must survive untouched (no false positives)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "192.168.1.8",  # IP address (dots break the digit run)
        "CUST008",  # customer ID
        "TKT12345678",  # ticket ID
        "AA:BB:88:00:11:22",  # MAC address (colons break the run)
        "order 1234 placed",  # short number
    ],
)
def test_non_pii_is_untouched(text):
    assert redact_phone(text, enabled=True) == text


def test_mixed_text_masks_only_the_phone():
    out = redact_phone(
        "caller +37060012345 id CUST008 ip 192.168.1.8 mac AA:BB:88:00:11:22",
        enabled=True,
    )
    assert "***2345" in out
    assert "+37060012345" not in out
    assert "CUST008" in out
    assert "192.168.1.8" in out
    assert "AA:BB:88:00:11:22" in out


# ---------------------------------------------------------------------------
# Traceability flag: REDACT_PII=false keeps full numbers (local testing)
# ---------------------------------------------------------------------------
def test_explicit_disabled_returns_original():
    assert redact_phone("+37060012345", enabled=False) == "+37060012345"


def test_env_flag_off_keeps_full_number(monkeypatch):
    monkeypatch.setenv("REDACT_PII", "false")
    assert redact_phone("+37060012345") == "+37060012345"


def test_env_flag_default_is_masked(monkeypatch):
    monkeypatch.delenv("REDACT_PII", raising=False)
    assert redact_phone("+37060012345") == "***2345"


def test_empty_text_is_safe():
    assert redact_phone("", enabled=True) == ""


# ---------------------------------------------------------------------------
# The logging filter redacts both f-string (msg) and %-style (args) records
# ---------------------------------------------------------------------------
def _make_record(msg, args=()):
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_filter_masks_fstring_record(monkeypatch):
    monkeypatch.setenv("REDACT_PII", "true")
    record = _make_record("caller +37060012345")
    assert PiiRedactionFilter().filter(record) is True
    assert record.getMessage() == "caller ***2345"


def test_filter_masks_percent_style_record(monkeypatch):
    monkeypatch.setenv("REDACT_PII", "true")
    record = _make_record("caller %s", args=("+37060012345",))
    PiiRedactionFilter().filter(record)
    assert record.getMessage() == "caller ***2345"
    assert record.args == ()


def test_filter_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("REDACT_PII", "false")
    record = _make_record("caller +37060012345")
    PiiRedactionFilter().filter(record)
    assert record.getMessage() == "caller +37060012345"

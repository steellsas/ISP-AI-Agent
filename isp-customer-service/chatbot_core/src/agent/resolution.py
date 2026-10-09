"""The routing outcome of a caller's turn — the shared vocabulary the readers and the
rules use for "yes / no / fixed / not fixed / pivot".

The v1 strategy registry and step walker that used to live here went with the fault
packs (`knowledge/faults/`); the v2 cards and the Case replaced them.
"""

from __future__ import annotations

from enum import Enum


class Outcome(str, Enum):
    """What the last turn produced."""

    YES = "yes"  # caller confirmed / step succeeded
    NO = "no"  # caller declined / denied
    FIXED = "fixed"  # verify: telemetry shows the line restored
    NOT_FIXED = "not_fixed"  # verify: fault persists (same verdict)
    PIVOT = "pivot"  # verify: telemetry shows a DIFFERENT verdict

"""Transport port — the I/O channel between a caller and the agent.

(Phase 3/4; no implementation yet.)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    """The connection that pumps turns to/from the core ``AgentSession``.

    A transport owns the live channel — a web WebSocket today, Twilio/PBX
    telephony later — and is the only place that knows about the wire. Concrete
    transports live in ``adapters/transport/``.

    Kept deliberately minimal: the exact streaming/barge-in contract is settled
    in Phase 3. For now this just pins down that transport is a *swappable
    boundary*, never baked into the framework-free core.
    """

    def start(self) -> None:
        """Open the channel and begin serving turns."""
        ...

    def stop(self) -> None:
        """Close the channel and release resources."""
        ...

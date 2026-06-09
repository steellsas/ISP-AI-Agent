"""Transport adapters — concrete `Transport` backends that own the wire."""

from .fastrtc_stream import FastRTCVoiceTransport

__all__ = ["FastRTCVoiceTransport"]

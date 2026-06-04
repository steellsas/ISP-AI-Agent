"""Ports — abstract interfaces for the hexagonal (ports & adapters) design.

Every component that can be swapped — LLM, tools, ASR, TTS, transport — is
declared here as a ``typing.Protocol``. The framework-free core (Phase 2)
depends only on these interfaces, never on a concrete adapter, so changing a
provider (cloud<->local model, web<->telephony, one TTS voice for another) is
an adapter swap with zero changes to the core.

Interfaces only: no behaviour, no concrete imports. This is the stable contract
every later phase plugs into.
"""

from .asr import ASRProvider
from .llm import LLMProvider, Message
from .tools import ToolProvider, ToolSpec
from .transport import Transport
from .tts import TTSProvider

__all__ = [
    "ASRProvider",
    "LLMProvider",
    "Message",
    "TTSProvider",
    "ToolProvider",
    "ToolSpec",
    "Transport",
]

"""TTS adapters — concrete `TTSProvider` backends."""

from .edge_tts import EdgeTTSProvider
from .gtts_tts import GTTSProvider
from .sentences import split_sentences

__all__ = ["EdgeTTSProvider", "GTTSProvider", "split_sentences"]

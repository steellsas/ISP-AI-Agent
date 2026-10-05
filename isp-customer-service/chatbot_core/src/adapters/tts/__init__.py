"""TTS adapters — concrete `TTSProvider` backends."""

from .edge_tts import EdgeTTSProvider
from .gtts_tts import GTTSProvider
from .sentences import speakable, split_sentences

__all__ = ["EdgeTTSProvider", "GTTSProvider", "speakable", "split_sentences"]

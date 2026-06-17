"""ASR adapters — concrete `ASRProvider` backends."""

from .faster_whisper_asr import FasterWhisperASR
from .lt_text import DOMAIN_PROMPT_LT, normalize_lt_numbers

__all__ = ["DOMAIN_PROMPT_LT", "FasterWhisperASR", "normalize_lt_numbers"]

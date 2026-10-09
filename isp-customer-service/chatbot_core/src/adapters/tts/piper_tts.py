"""
Piper adapter — local Lithuanian neural TTS behind `StreamingTTSProvider`.

Runs on the CPU, offline: no text leaves the machine, and there is no network
stall (edge-tts p90 4.3 s per sentence, review finding AL). Measured on the dev
PC (i5-14600K, 2026-10-07): first sentence 110–280 ms, real-time factor 0.02–0.06.

Two voices, both trained on the VU LIEPA corpus by Robertas Tarasevičius & Claude:
`reginute` (lt_LT-reginute1-medium, CC-BY-4.0) and `ingute` (lt_LT-ingute-medium,
OpenRAIL-D). Plain Piper cannot speak them — they need their own stress-aware
phonemizer, number expander and synthesis recipe, which ship next to the model
(GPL-3.0, so they live in `models/tts/piper/`, not in `src/`). Get everything with
`scripts/get_piper_voices.py`.

Emits MP3 bytes, one decodable blob per sentence — the same contract as edge-tts,
so the transport, the browser queue and the call recordings stay unchanged.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

logger = logging.getLogger(__name__)

# voice name (config page) -> model file stem in models/tts/piper/<voice>/
VOICES = {"reginute": "lt_LT-reginute1-medium", "ingute": "lt_LT-ingute-medium"}

# <isp-customer-service>/models/tts/piper — gitignored, filled by the script.
_DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[4] / "models" / "tts" / "piper"

# The recipe's own default tempo, approved by ear by the voice's authors (≈ the
# LIEPA speaker's 149 words per minute). TTS_RATE scales it like for edge-tts.
_BASE_LENGTH_SCALE = 1.30
# A sentence ends with the recipe's own punctuation pause; on top of that only a
# short gap, so per-sentence streaming does not sound like separate recordings.
_SENTENCE_GAP_S = 0.15


def models_dir() -> Path:
    root = os.getenv("TTS_PIPER_DIR", "").strip()
    return Path(root) if root else _DEFAULT_MODELS_DIR


def missing_files(voice: str, root: Path | None = None) -> list[str]:
    """What is not on disk yet for this voice (empty = ready to speak)."""
    root = root or models_dir()
    stem = VOICES[voice]
    needed = [
        root / "phonemize_lithuanian.py",
        root / "synth_reginute.py",
        root / "skaiciu_pletiklis.py",
        root / "lt_kirciai.tsv",
        root / voice / f"{stem}.onnx",
        root / voice / f"{stem}.onnx.json",
    ]
    return [str(p) for p in needed if not p.is_file()]


class PiperTTSProvider:
    """`StreamingTTSProvider` backed by a local Piper voice. Emits MP3 bytes per sentence."""

    # Loaded models are shared between providers (a config-page rebuild must not
    # reload 63 MB); the phonemizer and its 189k-word dictionary likewise.
    _ENGINES: dict[tuple, object] = {}
    _PHONEMIZER = None
    _LOAD_LOCK = threading.Lock()

    _CACHE: dict[tuple, bytes] = {}
    _CACHE_MAX = 512
    last_synthesis_ms: int = 0

    def __init__(
        self, *, voice: str = "reginute", default_language: str = "lt", root: Path | None = None
    ):
        """
        Args:
            voice: `reginute` or `ingute`.
            default_language: ISO code; Lithuanian is the only language these voices speak.
            root: models directory (default `models/tts/piper`, or TTS_PIPER_DIR).

        Raises:
            ValueError: unknown voice.
            FileNotFoundError: the voice is not downloaded — the caller falls back.
        """
        if voice not in VOICES:
            raise ValueError(f"unknown Piper voice {voice!r} (known: {', '.join(VOICES)})")
        self._voice = voice
        self._default_language = default_language
        self._root = root or models_dir()
        missing = missing_files(voice, self._root)
        if missing:
            raise FileNotFoundError(
                f"Piper voice {voice!r} is not downloaded ({missing[0]}); "
                "run scripts/get_piper_voices.py"
            )

    # --- knobs (config page; read per sentence, so they apply immediately) ---

    @staticmethod
    def _length_scale() -> float:
        """TTS_RATE '+10%' speaks 10 % faster — the same knob as for edge-tts."""
        raw = (os.getenv("TTS_RATE") or "").strip()
        m = re.fullmatch(r"([+-]\d{1,2})%", raw)
        factor = 1.0 + int(m.group(1)) / 100 if m else 1.0
        return round(_BASE_LENGTH_SCALE / max(factor, 0.5), 3)

    @staticmethod
    def _noise_scale() -> float:
        """TTS_PIPER_NOISE — intonation variety: lower is flatter and steadier,
        higher is livelier (and riskier). The recipe's default is 0.667."""
        try:
            value = float(os.getenv("TTS_PIPER_NOISE", "0.667"))
        except ValueError:
            return 0.667
        return min(max(value, 0.3), 1.0)

    @staticmethod
    def _levelling() -> bool:
        """TTS_PIPER_LEVEL — the recipe re-synthesizes a fragment (≤2×) until its
        tempo matches the rest, so the voice does not speak "in waves". Costs about
        +120 ms on the first sentence; off = fastest."""
        return os.getenv("TTS_PIPER_LEVEL", "on").lower() != "off"

    def _key(self, sentence: str) -> tuple:
        return (sentence, self._voice, self._length_scale(), self._noise_scale(), self._levelling())

    # --- engine -----------------------------------------------------------

    def _load(self):
        """(PiperVoice, phonemizer, recipe module) — loaded once per process."""
        with self._LOAD_LOCK:
            root = str(self._root)
            if root not in sys.path:
                # The phonemizer imports its expander by plain module name.
                sys.path.insert(0, root)
            import synth_reginute  # noqa: PLC0415 - shipped with the voice, GPL-3.0
            from phonemize_lithuanian import LithuanianPhonemizer  # noqa: PLC0415
            from piper import PiperVoice  # noqa: PLC0415 - optional `voice` extra

            if PiperTTSProvider._PHONEMIZER is None:
                PiperTTSProvider._PHONEMIZER = LithuanianPhonemizer(
                    dictionary_path=self._root / "lt_kirciai.tsv",
                    letters_path=self._root / "lt_raides.tsv",
                    vocatives_path=self._root / "lt_kreipiniai.tsv",
                )
            key = (root, self._voice)
            if key not in self._ENGINES:
                t0 = time.perf_counter()
                stem = VOICES[self._voice]
                model_path = str(self._root / self._voice / f"{stem}.onnx")
                voice = PiperVoice.load(model_path)
                voice.session = _cpu_session(model_path)
                self._ENGINES[key] = voice
                logger.info(
                    "piper: voice %s loaded in %d ms",
                    self._voice,
                    (time.perf_counter() - t0) * 1000,
                )
            return self._ENGINES[key], PiperTTSProvider._PHONEMIZER, synth_reginute

    def _synthesize_one(self, sentence: str) -> bytes:
        from .sentences import speakable

        sentence = speakable(sentence, self._default_language)
        key = self._key(sentence)
        cached = self._CACHE.get(key)
        if cached is not None:
            return cached

        import numpy as np

        voice, phonemizer, recipe = self._load()
        t0 = time.perf_counter()
        # A fresh recipe object per sentence: it keeps a tempo reference and a
        # measurement log, which must neither leak between calls nor grow forever.
        synth = recipe.ReginuteSynth(
            voice,
            phonemizer,
            length_scale=self._length_scale(),
            expand_text=phonemizer.expand_text,
            lyginti_greiti=self._levelling(),
        )
        synth.syn = replace(synth.syn, noise_scale=self._noise_scale())
        audio = np.concatenate([*synth.gabalai(sentence), np.zeros(1, dtype=np.float32)])
        # The recipe ends every call with 0.85 s of silence (it expects a whole
        # text); per sentence that would put a long hole between sentences.
        voiced = np.flatnonzero(audio)
        end = int(voiced[-1]) + 1 if voiced.size else 0
        tail = int(synth.sr * (synth.pauze.get(sentence.rstrip()[-1:], 0.0) + _SENTENCE_GAP_S))
        audio = np.concatenate([audio[:end], np.zeros(tail, dtype=np.float32)])
        mp3 = _to_mp3(recipe.i_int16(audio), synth.sr) if end else b""
        ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "piper %s: %d chars -> %d bytes in %d ms", self._voice, len(sentence), len(mp3), ms
        )
        self.last_synthesis_ms = ms
        if mp3:
            if len(self._CACHE) >= self._CACHE_MAX:
                self._CACHE.pop(next(iter(self._CACHE)))
            self._CACHE[key] = mp3
        return mp3

    # --- TTSProvider / StreamingTTSProvider --------------------------------

    def is_cached(self, sentence: str, *, language: str | None = None) -> bool:
        from .sentences import speakable

        return self._key(speakable(sentence, self._default_language)) in self._CACHE

    def stream(self, text: str, *, language: str | None = None) -> Iterator[bytes]:
        """Yield one MP3 blob per sentence as it is rendered."""
        from .sentences import split_sentences

        for sentence in split_sentences(text):
            try:
                audio = self._synthesize_one(sentence)
            except Exception:  # pragma: no cover - engine best-effort, like edge-tts
                logger.warning("piper synthesis failed for a sentence", exc_info=True)
                continue
            if audio:
                yield audio

    def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        """Full reply as one MP3 (concatenated per-sentence frames)."""
        return b"".join(self.stream(text, language=language))


def _cpu_session(model_path: str):
    """An ONNX session with a bounded thread pool and no spin-waiting.

    The default uses every core and spins between runs. On the 20-thread dev PC under load a
    sentence took 0.3–2.4 s in the server against ~0.15 s idle; 8 threads without spinning
    held ~30 % better under load and the same idle (measured 2026-10-07). TTS_PIPER_THREADS
    overrides the count.
    """
    import onnxruntime

    try:
        threads = int(os.getenv("TTS_PIPER_THREADS", "0"))
    except ValueError:
        threads = 0
    if threads <= 0:
        threads = min(8, os.cpu_count() or 4)
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    return onnxruntime.InferenceSession(
        model_path, sess_options=options, providers=["CPUExecutionProvider"]
    )


def _to_mp3(pcm16: bytes, sample_rate: int) -> bytes:
    """Mono int16 PCM -> MP3 (64 kbps is plenty for a 22 kHz voice; ~25 ms per 6 s)."""
    import lameenc

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(64)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm16) + encoder.flush())

"""Piper in worker processes — synthesis outside the server's GIL (DELSA, 2026-10-19).

The recipe and the phonemizer are mostly Python. Inside the server they wait for the GIL
behind the audio transport, VAD, ASR and LLM threads: a sentence that takes ~370 ms alone
took ~970 ms with two busy Python threads beside it (measured), and 10–13 ms per character
in live calls against ~3.7 ms alone. Here every worker process has its own GIL and its own
loaded voice; the server only sends text and receives PCM, phrase by phrase.

Several workers take jobs from one queue, so concurrent calls do not wait for each other's
sentences (TTS_PIPER_WORKERS, default 2). The config-page knobs (rate, noise, levelling)
travel with every job, because they live in the server's environment.

`PooledPiperTTSProvider` is a `PiperTTSProvider`: same MP3 cache, same `stream`/`synthesize`
for the dashboard voice, same `stream_pcm` for Pipecat — only the rendering moved out.
"""

from __future__ import annotations

import itertools
import logging
import multiprocessing as mp
import os
import queue
import signal
import threading
from collections.abc import Iterator
from pathlib import Path

from .piper_tts import PiperTTSProvider

logger = logging.getLogger(__name__)

# The knobs PiperTTSProvider reads per sentence from the environment.
_KNOBS = ("TTS_RATE", "TTS_PIPER_NOISE", "TTS_PIPER_LEVEL")
_DONE = "done"
_ERROR = "error"
_START_TIMEOUT_S = 60.0
_PIECE_TIMEOUT_S = 15.0


def _worker_main(voice: str, root: str, threads: int, jobs, results) -> None:
    """One worker: load the voice once, then render jobs until told to stop (None)."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    os.environ["TTS_PIPER_THREADS"] = str(threads)
    provider = PiperTTSProvider(voice=voice, root=Path(root))
    provider.synthesize_pcm("Labas.")  # loads the model and the phonemizer
    results.put((None, "ready", os.getpid()))
    while True:
        job = jobs.get()
        if job is None:
            return
        job_id, kind, text, knobs = job
        for name in _KNOBS:
            if knobs.get(name) is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = knobs[name]
        try:
            if kind == "render":  # text is already speakable
                pcm, rate = provider._render(text)
                results.put((job_id, pcm, rate))
            else:  # text is already speakable; the cache lives in the server
                for pcm, rate in provider._stream_speakable(text):
                    results.put((job_id, pcm, rate))
            results.put((job_id, _DONE, None))
        except Exception as exc:  # pragma: no cover - reported to the caller
            results.put((job_id, _ERROR, repr(exc)))


class PiperPool:
    """N worker processes, one job queue, results routed back to the asking thread."""

    def __init__(self, voice: str, root: Path, workers: int, threads: int) -> None:
        ctx = mp.get_context("spawn")
        self._jobs = ctx.Queue()
        self._results = ctx.Queue()
        self._ids = itertools.count(1)
        self._waiting: dict[int, queue.Queue] = {}
        self._lock = threading.Lock()
        self._procs = [
            ctx.Process(
                target=_worker_main,
                args=(voice, str(root), threads, self._jobs, self._results),
                name=f"piper-{i}",
                daemon=True,
            )
            for i in range(workers)
        ]
        for proc in self._procs:
            proc.start()
        ready = 0
        while ready < workers:  # every worker has its voice loaded before the first call
            _, tag, _ = self._results.get(timeout=_START_TIMEOUT_S)
            ready += tag == "ready"
        self._router = threading.Thread(target=self._route, name="piper-router", daemon=True)
        self._router.start()
        logger.info("piper pool: %d workers × %d threads, voice %s", workers, threads, voice)

    def _route(self) -> None:
        while True:
            job_id, payload, extra = self._results.get()
            with self._lock:
                inbox = self._waiting.get(job_id)
            if inbox is not None:
                inbox.put((payload, extra))

    def run(self, kind: str, text: str) -> Iterator[tuple[bytes, int]]:
        """Yield (pcm, rate) pieces of one job as the worker renders them."""
        job_id = next(self._ids)
        inbox: queue.Queue = queue.Queue()
        with self._lock:
            self._waiting[job_id] = inbox
        try:
            knobs = {name: os.environ.get(name) for name in _KNOBS}
            self._jobs.put((job_id, kind, text, knobs))
            while True:
                payload, extra = inbox.get(timeout=_PIECE_TIMEOUT_S)
                if payload == _DONE:
                    return
                if payload == _ERROR:
                    raise RuntimeError(f"piper worker: {extra}")
                yield payload, extra
        finally:
            with self._lock:
                self._waiting.pop(job_id, None)

    def alive(self) -> bool:
        return all(proc.is_alive() for proc in self._procs)

    def close(self) -> None:
        for _ in self._procs:
            self._jobs.put(None)
        for proc in self._procs:
            proc.join(timeout=2)


class PooledPiperTTSProvider(PiperTTSProvider):
    """`PiperTTSProvider` whose rendering runs in a `PiperPool`; falls back to rendering
    in-process if the pool dies, so a call never goes silent."""

    def __init__(self, *, voice: str = "reginute", default_language: str = "lt", root=None):
        super().__init__(voice=voice, default_language=default_language, root=root)
        workers = _env_int("TTS_PIPER_WORKERS", 2)
        threads = _env_int("TTS_PIPER_THREADS", max(2, min(8, (os.cpu_count() or 4) // workers)))
        self._pool = PiperPool(voice, self._root, workers, threads)

    def _render(self, sentence: str) -> tuple[bytes, int]:
        if not self._pool.alive():
            logger.warning("piper pool is down; rendering in-process")
            return super()._render(sentence)
        pieces = list(self._pool.run("render", sentence))
        return pieces[0] if pieces else (b"", 22050)

    def _stream_speakable(self, sentence: str) -> Iterator[tuple[bytes, int]]:
        if not self._pool.alive():
            logger.warning("piper pool is down; streaming in-process")
            yield from super()._stream_speakable(sentence)
            return
        yield from self._pool.run("stream", sentence)

    def close(self) -> None:
        self._pool.close()


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default

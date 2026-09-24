"""Embedding'ai žinių paieškai: vienas modelis, ribotas laukimas, nusileidimas (RAG planas, E3).

Kodėl `e5-small`, o ne didesnis: išmatuota (2026-09-24) ant to paties klausimų rinkinio —
`multilingual-e5-small` (118 mln. par., **13 ms** užklausai) davė tą pačią kokybę, kaip
`e5-base` (278 mln., 51 ms) ir geriau nei `paraphrase-multilingual-mpnet`, kuris repozitorijoje
buvo įrašytas nuo v1. Modelį rinkomės matuodami, ne pagal tai, kuris jau buvo.

Trys dalykai, kurie čia svarbesni už patį modelį:

  1. VIENAS egzempliorius. Balso servise dirba keli uvicorn worker'iai; modelis kiekviename jų
     reikštų N × 0,5 GB. Gamyboje tai sprendžiama atskiru servisu (`EMBED_URL`, pvz. HuggingFace
     TEI) — tada modelis vienas visiems ir su dinaminiu paketavimu. Be `EMBED_URL` modelis
     kraunamas procese vieną kartą (singleton), tinginiu būdu ir pakaitinamas.

  2. RIBOTAS LAUKIMAS. Balso ėjimas negali laukti modelio. `EMBED_TIMEOUT` (numatyta 150 ms) yra
     riba, kiek laukiam ATSAKYMO; nesulaukus paieška vyksta tik *sparse* puse. Tai riba laukimui,
     ne skaičiavimui: vietinis modelis CPU viduryje nenutraukiamas, tad gija pabaigs darbą, o mes
     jos nebelaukiam.

  3. RIBOTAS VIENALAIKIŠKUMAS. Dešimt skambučių vienu metu neturi imti dešimties CPU perėjimų:
     `EMBED_WORKERS` (numatyta 2) gijos ir eilė. Jei eilė užimta ilgiau nei timeout — vėl *sparse*.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

logger = logging.getLogger(__name__)

MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
DIM = int(os.getenv("EMBED_DIM", "384"))
TIMEOUT = float(os.getenv("EMBED_TIMEOUT", "0.15"))
WORKERS = int(os.getenv("EMBED_WORKERS", "2"))

# `e5` modelių sutartis: užklausa ir tekstas žymimi skirtingai. Be priešdėlių kokybė nukrenta — tai
# ne smulkmena, o modelio dalis.
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


class Local:
    """Modelis ŠIAME procese: vienas egzempliorius, tinginys, pakaitinamas, ribotos gijos."""

    name = "local"

    def __init__(self, model: str = MODEL, workers: int = WORKERS) -> None:
        self._model_name = model
        self._model: Any | None = None
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="embed")

    def _loaded(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info(f"[EMB] loading {self._model_name}")
                    self._model = SentenceTransformer(self._model_name)
        return self._model

    def warm(self) -> None:
        """Pakaitinimas STARTE, ne skambutyje: modelio uždėjimas kainuoja ~6 s."""
        self.encode_passages(["pasildymas"])

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        """Indeksavimui: paketu, be laukimo ribos — tai ne skambučio kelias."""
        if not texts:
            return []
        vectors = self._loaded().encode(
            [PASSAGE_PREFIX + text for text in texts], batch_size=32, normalize_embeddings=True
        )
        return [vector.tolist() for vector in vectors]

    def encode_query(self, text: str) -> list[float] | None:
        """Skambučio kelias: laukiam ne ilgiau `TIMEOUT`, o nesulaukę grąžinam None."""
        if not text.strip():
            return None
        try:
            future = self._pool.submit(
                lambda: (
                    self._loaded()
                    .encode([QUERY_PREFIX + text], normalize_embeddings=True)[0]
                    .tolist()
                )
            )
            return future.result(timeout=TIMEOUT)
        except TimeoutError:
            logger.warning(f"[EMB] query embedding did not arrive in {TIMEOUT * 1000:.0f}ms")
            return None
        except Exception as exc:
            logger.warning(f"[EMB] query embedding failed: {exc}")
            return None


class Remote:
    """Modelis ATSKIRAME servise (`EMBED_URL`, pvz. HuggingFace TEI).

    Gamybinė forma: viena modelio kopija visiems worker'iams, dinaminis paketavimas, savas
    health endpoint. Sąsaja ta pati, tad agentui nesvarbu, kur modelis gyvena.
    """

    name = "remote"

    def __init__(self, url: str, timeout: float = TIMEOUT) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _post(self, inputs: list[str], timeout: float) -> list[list[float]] | None:
        import json
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            f"{self.url}/embed",
            data=json.dumps({"inputs": inputs}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            logger.warning(f"[EMB] {self.url} did not answer: {exc}")
            return None

    def warm(self) -> None:
        self._post(["pasildymas"], timeout=30.0)

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), 32):
            batch = [PASSAGE_PREFIX + text for text in texts[start : start + 32]]
            got = self._post(batch, timeout=60.0)
            if got is None:
                raise RuntimeError(f"embedding service {self.url} failed while indexing")
            out.extend(got)
        return out

    def encode_query(self, text: str) -> list[float] | None:
        if not text.strip():
            return None
        got = self._post([QUERY_PREFIX + text], timeout=self.timeout)
        return got[0] if got else None


_shared: Any | None = None
_shared_lock = threading.Lock()


def embedder() -> Any | None:
    """Bendras embedder'is arba None, jei embedding'ai išjungti (`EMBED=off`).

    `None` reiškia, kad paieška vyksta tik *sparse* puse — lygiai kaip E2. Tai ne avarija, o
    numatytas nusileidimas: leksinė pusė gaudo modelius ir klaidų kodus ir viena veikia.
    """
    global _shared
    if (os.getenv("EMBED") or "on").strip().lower() in ("off", "0", "false", "no"):
        return None
    if _shared is None:
        with _shared_lock:
            if _shared is None:
                url = os.getenv("EMBED_URL")
                _shared = Remote(url) if url else Local()
    return _shared


def use(instance: Any | None) -> None:
    """Testams ir startui: pakeisti bendrą egzempliorių (taip pat ir į None)."""
    global _shared
    _shared = instance

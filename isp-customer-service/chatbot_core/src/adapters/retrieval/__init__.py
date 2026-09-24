"""Žinių paieškos adapteriai — konkrečios `RetrieverPort` realizacijos.

`LexicalRetriever` yra leksinė paieška per markdown failus, porto forma. `QdrantRetriever` —
ta pati paieška per Qdrant indeksą (RAG planas, E2), o `KnowledgeIndex` yra vienintelis dalykas,
kuris į tą indeksą rašo.

Failai lieka TIESOS ŠALTINIS: Qdrant yra išvestinis indeksas, tad neatsakius serveriui agentas
vis tiek turi žinias — `LexicalRetriever` skaito failus.
"""

from .lexical import LexicalRetriever
from .qdrant_store import KnowledgeIndex, QdrantRetriever

__all__ = ["KnowledgeIndex", "LexicalRetriever", "QdrantRetriever", "configure_from_env"]


def configure_from_env() -> str:
    """Kuri saugykla atsakys šiame procese — pagal aplinką, be kodo keitimo.

        KB_BACKEND=files    (numatyta) leksinė paieška per markdown failus
        KB_BACKEND=qdrant   Qdrant indeksas; neatsakius — nusileidžiam į failus

    Kodėl numatyta `files`: indeksas yra išvestinis, o dokumentai keliauja su atvaizdu. Perjungiama
    sąmoningai, o ne „atsitiktinai užsivedė, nes buvo nustatytas QDRANT_URL".
    """
    import logging
    import os

    from agent import knowledge_base as kb

    logger = logging.getLogger(__name__)
    wanted = (os.getenv("KB_BACKEND") or "files").strip().lower()
    if wanted != "qdrant":
        kb.use(None)
        return "files"
    try:
        from .qdrant_store import client

        store = QdrantRetriever(client())
        if not store.is_loaded():
            raise RuntimeError(f"no points behind alias '{store.collection}'")
        kb.use(store)
        _warm_embeddings()
        return "qdrant"
    except Exception as exc:
        # Indekso nėra arba serveris neatsako: agentas vis tiek turi žinias, tik per failus.
        logger.warning(f"[KB] KB_BACKEND=qdrant, but the index is unusable ({exc}) — using files")
        kb.use(None)
        return "files"


def _warm_embeddings() -> None:
    """Modelis pakaitinamas STARTE, fone.

    Be to pirmosios užklausos nesulaukia atsakymo: modelio uždėjimas kainuoja ~12 s, o balso ėjimo
    riba yra 150 ms — tad pirmieji skambučiai gautų tik leksinę pusę. Fone, o ne sinchroniškai, kad
    startas nelauktų; iki pakaitinimo pabaigos paieška veikia kaip E2.
    """
    import logging
    import threading

    from . import embed

    model = embed.embedder()
    if model is None:
        return

    def warm() -> None:
        try:
            model.warm()
            logging.getLogger(__name__).info(f"[EMB] warm: {embed.MODEL}")
        except Exception as exc:  # pragma: no cover - pakaitinimas niekada nelaužia starto
            logging.getLogger(__name__).warning(f"[EMB] warm-up failed: {exc}")

    threading.Thread(target=warm, name="embed-warm", daemon=True).start()

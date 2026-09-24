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
        return "qdrant"
    except Exception as exc:
        # Indekso nėra arba serveris neatsako: agentas vis tiek turi žinias, tik per failus.
        logger.warning(f"[KB] KB_BACKEND=qdrant, but the index is unusable ({exc}) — using files")
        kb.use(None)
        return "files"

"""Žinių paieškos adapteriai — konkrečios `RetrieverPort` realizacijos.

`LexicalRetriever` yra ta pati leksinė paieška per markdown failus, tik porto forma. Jos vieta
plane (RAG_PLANAS.md, E1) yra tiksliai apibrėžta: kai E2 atsiras `QdrantRetriever`, agentas
nepasikeis nė viena eilute, o ši realizacija liks ATSARGINIU keliu — neatsakius Qdrant, žinios
vis tiek yra failuose.
"""

from .lexical import LexicalRetriever

__all__ = ["LexicalRetriever"]

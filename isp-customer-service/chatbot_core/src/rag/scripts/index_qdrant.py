"""Žinių indekso ingestija į Qdrant (RAG planas, E2).

Vienintelis dalykas, kuris RAŠO į indeksą. Paleidžiamas ne skambučio metu: rankomis, iš CI arba iš
admin įrankio, kai pasikeičia dokumentai.

    uv run python src/rag/scripts/index_qdrant.py --status
    uv run python src/rag/scripts/index_qdrant.py --rebuild
    uv run python src/rag/scripts/index_qdrant.py --document troubleshooting/wifi_problems.md
    uv run python src/rag/scripts/index_qdrant.py --remove troubleshooting/senas.md

`--rebuild` stato NAUJĄ kolekciją (`kb_v4`), praleidžia per ją atgaminimo patikrą ir tik tada
perjungia aliasą `kb`. Senoji kolekcija lieka — atstatymas yra viena operacija. Tad gamyboje
perindeksavimas nereikalauja prastovos, o blogas indeksas nepasiekia nė vieno skambučio.

Raktai iš aplinkos: `QDRANT_URL`, `QDRANT_API_KEY` (rašymo). Agentas naudoja `QDRANT_READ_KEY` ir
rašyti negali techniškai.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
if str(SRC) not in sys.path:  # paleidžiama kaip skriptas, ne modulis
    sys.path.insert(0, str(SRC))

from adapters.retrieval import KnowledgeIndex, QdrantRetriever  # noqa: E402
from adapters.retrieval.qdrant_store import client  # noqa: E402
from adapters.retrieval.questions import passes  # noqa: E402
from agent import knowledge_base as kb  # noqa: E402


def _status(index: KnowledgeIndex) -> int:
    collection = index.current()
    print(f"aliasas {index.alias} -> {collection or '(nėra indekso)'}")
    if collection is None:
        return 1
    print(
        f"taškų: {index.qdrant.count(collection).count} · dokumentų failuose: {len(kb.documents())}"
    )
    drift = index.drift()
    if drift:
        print("SKIRIASI NUO FAILŲ:")
        for source, how in drift.items():
            print(f"  {how:8} {source}")
    else:
        print("indeksas atitinka failus")
    ok, seen = passes(QdrantRetriever(index.qdrant, collection))
    print(f"atgaminimas: {seen} — {'gerai' if ok else 'NEPAKANKAMA'}")
    return 0 if ok and not drift else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="visas indeksas iš naujo + aliasas")
    parser.add_argument("--document", help="perindeksuoti VIENĄ dokumentą")
    parser.add_argument("--remove", help="išimti dokumentą iš indekso")
    parser.add_argument("--status", action="store_true", help="versija, skirtumai, atgaminimas")
    parser.add_argument(
        "--no-canary", action="store_true", help="perjungti be patikros (nerekomenduojama)"
    )
    parser.add_argument(
        "--collection", default=None, help="aliaso vardas (numatytas: KB_COLLECTION)"
    )
    args = parser.parse_args(argv)

    qdrant = client()
    index = KnowledgeIndex(qdrant, args.collection) if args.collection else KnowledgeIndex(qdrant)

    if args.status:
        return _status(index)

    if args.document:
        count = index.upsert_document(args.document)
        print(f"{args.document}: {count} dalys atnaujintos kolekcijoje {index.current()}")
        return 0

    if args.remove:
        index.remove_document(args.remove)
        print(f"{args.remove}: išimtas iš {index.current()}")
        return 0

    if args.rebuild:

        def canary(collection: str) -> bool:
            ok, seen = passes(QdrantRetriever(qdrant, collection))
            print(f"kanarėlė {collection}: {seen} — {'gerai' if ok else 'STOP'}")
            if not ok:
                for miss in seen.misses[:5]:
                    print(f"    {miss}")
            return ok

        previous = index.rebuild(canary=None if args.no_canary else canary)
        print(f"aliasas {index.alias} -> {index.current()} (buvo {previous})")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

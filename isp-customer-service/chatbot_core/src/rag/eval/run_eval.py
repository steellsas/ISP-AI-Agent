"""
RAG retrieval evaluation harness (measure-first).

Runs a fixed LT->LT query set (eval/queries.json) against the knowledge base and
reports, per retriever:

  - recall@k (lenient): top-k contains AT LEAST ONE acceptable doc.
       Matches how RAG actually works -- the LLM gets all k chunks and
       synthesises, so "is sufficient info present?" is the real question.
  - recall@k (strict): top-k contains the canonical doc (docs[0]).
       Harsher; useful to detect regressions the lenient metric hides.
  - MRR: 1 / rank of the first acceptable chunk (0 if none in top-k).
       The SPEED lever -- if the right doc is consistently rank-1 we can
       shrink top_k (less context -> faster, cheaper voice replies).

It calls ONLY RetrieverPort.retrieve(), so the exact same harness measures
every Phase 1b change (cosine flip, RRF, chunking) without modification.
Base (semantic) and Hybrid (semantic + keyword) are run side by side, which
also surfaces the base-vs-hybrid path inconsistency with numbers.

Usage (KB must be built first):
    cd chatbot_core
    uv run python src/rag/scripts/build_kb.py --name production   # one-time / after KB edits
    uv run python src/rag/eval/run_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make `rag` and `isp_shared` importable when run as a script from chatbot_core.
_EVAL_DIR = Path(__file__).resolve().parent
_SRC_DIR = _EVAL_DIR.parent.parent  # chatbot_core/src
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from rag.embeddings import get_embedding_manager  # noqa: E402
from rag.hybrid_retriever import HybridRetriever  # noqa: E402
from rag.retriever import Retriever  # noqa: E402
from rag.vector_store import get_vector_store  # noqa: E402

try:
    from isp_shared.utils import get_config
except ImportError:  # config is optional; fall back to literals matching its defaults
    get_config = None


QUERIES_PATH = _EVAL_DIR / "queries.json"
KB_NAME = "production"


def _load_queries() -> tuple[int, list[dict]]:
    data = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    return int(data.get("k", 3)), [q for q in data["queries"] if isinstance(q, dict) and "q" in q]


def _sources(results: list[dict]) -> list[str]:
    """Chunk-level source filenames, in returned order (duplicates kept)."""
    return [r.get("metadata", {}).get("source", "") for r in results]


def _score_one(results: list[dict], acceptable: set[str], canonical: str, k: int) -> dict:
    srcs = _sources(results)[:k]
    lenient = any(s in acceptable for s in srcs)
    strict = canonical in srcs
    rr = 0.0
    for i, s in enumerate(srcs):
        if s in acceptable:
            rr = 1.0 / (i + 1)
            break
    return {"lenient": lenient, "strict": strict, "rr": rr, "srcs": srcs}


def _evaluate(name: str, retriever, queries: list[dict], k: int, threshold: float) -> None:
    print(f"\n{'=' * 78}\n{name}  (k={k}, threshold={threshold})\n{'=' * 78}")
    n = len(queries)
    sum_lenient = sum_strict = sum_rr = 0.0
    misses: list[str] = []

    for item in queries:
        q = item["q"]
        docs = item["docs"]
        acceptable = set(docs)
        canonical = docs[0]
        results = retriever.retrieve(q, top_k=k, threshold=threshold)
        s = _score_one(results, acceptable, canonical, k)

        sum_lenient += s["lenient"]
        sum_strict += s["strict"]
        sum_rr += s["rr"]

        mark = "ok " if s["lenient"] else "MISS"
        top = ", ".join(dict.fromkeys(s["srcs"])) or "(no results)"
        print(f"  [{mark}] rr={s['rr']:.2f}  {q[:42]:<42} -> {top}")
        if not s["lenient"]:
            misses.append(f"{q}  (want one of: {', '.join(docs)})")

    print(f"\n  recall@{k} lenient : {sum_lenient / n:.3f}  ({int(sum_lenient)}/{n})")
    print(f"  recall@{k} strict  : {sum_strict / n:.3f}  ({int(sum_strict)}/{n})")
    print(f"  MRR               : {sum_rr / n:.3f}")
    if misses:
        print("  misses:")
        for m in misses:
            print(f"    - {m}")


def main() -> int:
    if get_config is not None:
        cfg = get_config()
        top_k = cfg.rag_top_k
        threshold = cfg.rag_threshold
        keyword_weight = cfg.rag_keyword_weight
    else:
        top_k, threshold, keyword_weight = 3, 0.4, 0.3

    file_k, queries = _load_queries()
    k = file_k or top_k

    # Build retrievers directly (not the singletons) so eval fully controls the
    # knobs from config. Both share one loaded vector store.
    em = get_embedding_manager()
    vs = get_vector_store(embedding_dim=em.embedding_dim)
    base = Retriever(
        embedding_manager=em,
        vector_store=vs,
        top_k=top_k,
        similarity_threshold=threshold,
    )

    if not base.load(KB_NAME):
        print(
            f"\nKB '{KB_NAME}' could not be loaded. Build it first:\n"
            f"    cd chatbot_core\n"
            f"    uv run python src/rag/scripts/build_kb.py --name {KB_NAME}\n"
        )
        return 1
    if not base.is_loaded():
        print(f"\nKB '{KB_NAME}' loaded but empty. Rebuild with build_kb.py.\n")
        return 1

    hybrid = HybridRetriever(base, keyword_weight=keyword_weight)

    print(f"\nEval set: {len(queries)} queries from {QUERIES_PATH.name}")
    _evaluate("BASE (semantic only)", base, queries, k, threshold)
    _evaluate("HYBRID (semantic + keyword)", hybrid, queries, k, threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

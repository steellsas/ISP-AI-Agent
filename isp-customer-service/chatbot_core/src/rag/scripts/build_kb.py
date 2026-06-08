#!/usr/bin/env python3
"""
Knowledge Base Builder v2 - Optimized
Builds FAISS vector store from markdown documents AND YAML scenarios

Features:
- Smart document chunking (better precision)
- Metadata extraction (problem_type, section, chunk_type)
- Progress tracking
- Validation and testing

Usage:
    cd chatbot_core
    uv run python src/rag/scripts/build_kb.py
    uv run python src/rag/scripts/build_kb.py --name production
    uv run python src/rag/scripts/build_kb.py --rebuild-all
"""

import sys
import time
from pathlib import Path

# Setup paths for imports
current_dir = Path(__file__).parent
src_dir = current_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from rag import get_retriever
from rag.document_processor import DocumentProcessor

# from rag.scenario_loader import get_scenario_loader

# Import utilities from shared package
try:
    from utils import get_logger
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger(__name__)


# =============================================================================
# KNOWLEDGE BASE BUILDER
# =============================================================================


def build_knowledge_base(
    kb_name: str = "production",
    chunk_size: int = 400,
    chunk_overlap: int = 50,
    verbose: bool = True,
):
    """
    Build knowledge base from markdown files AND YAML scenarios.

    Args:
        kb_name: Name for saved knowledge base
        chunk_size: Chunk size for document splitting
        chunk_overlap: Overlap between chunks
        verbose: Print detailed output
    """
    start_time = time.time()

    def log(msg: str):
        if verbose:
            print(msg)

    log("=" * 80)
    log("KNOWLEDGE BASE BUILDER v2 (with Chunking)")
    log("=" * 80)

    # Initialize
    log("\n1. Initializing...")
    retriever = get_retriever(top_k=5, similarity_threshold=0.5)
    processor = DocumentProcessor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    try:
        from utils import get_config

        default_lang = get_config().rag_default_lang
    except Exception:
        default_lang = "lt"
    log("   ✅ Retriever ready")
    log(f"   ✅ Document processor ready (chunk_size={chunk_size}, default_lang={default_lang})")

    # Knowledge base path
    kb_path = current_dir.parent / "knowledge_base"
    log(f"\n2. Knowledge base path: {kb_path}")

    if not kb_path.exists():
        log(f"❌ Knowledge base not found: {kb_path}")
        return False

    # Collect all chunks
    all_chunks = []
    stats = {"markdown_files": 0, "markdown_chunks": 0, "scenarios": 0, "total_chunks": 0}

    # === PART 1: Load & Chunk Markdown Documents ===
    log("\n3. Processing markdown documents...")
    log("-" * 80)

    # Language is a data dimension, not code. A file's language comes from a
    # top-level language folder (knowledge_base/<lang>/<category>/file.md); files
    # sitting directly under a category folder fall back to default_lang. So the
    # current flat LT layout -> "lt", and dropping an "en/" tree later is picked
    # up automatically with zero code change. The category is preserved either way.
    lang_codes = {"lt", "en", "ru", "pl", "lv", "et", "de", "fr"}

    md_files = sorted(kb_path.rglob("*.md"))
    if not md_files:
        log("   No markdown files found")

    for md_file in md_files:
        rel_parts = md_file.relative_to(kb_path).parts

        if rel_parts and rel_parts[0].lower() in lang_codes:
            lang = rel_parts[0].lower()
            category = rel_parts[1] if len(rel_parts) >= 3 else "general"
        else:
            lang = default_lang
            category = rel_parts[0] if len(rel_parts) >= 2 else "general"

        # Skip empty files
        if md_file.stat().st_size == 0:
            log(f"   - {md_file.name} (empty, skipped)")
            continue

        try:
            content = md_file.read_text(encoding="utf-8")

            # Process into chunks
            chunks = processor.process_markdown(
                content=content,
                source=md_file.name,
                lang=lang,
                base_metadata={"category": category},
            )

            all_chunks.extend(chunks)
            stats["markdown_files"] += 1
            stats["markdown_chunks"] += len(chunks)

            log(f"   {category}/{md_file.name} [{lang}] -> {len(chunks)} chunks")

        except Exception as e:
            log(f"   ERROR {md_file.name}: {e}")

    log("\n" + "-" * 80)
    log(f"📊 Markdown: {stats['markdown_files']} files → {stats['markdown_chunks']} chunks")

    # === PART 2: Load YAML Scenarios ===
    log("\n4. Loading YAML scenarios...")
    log("-" * 80)

    # try:
    #     scenario_loader = get_scenario_loader()
    #     scenarios_data = scenario_loader.get_scenarios_for_embedding()

    #     if not scenarios_data:
    #         log("⚠️  No scenarios found")
    #     else:
    #         log(f"\n📋 Scenarios:")

    #         for scenario in scenarios_data:
    #             # Convert to chunk format
    #             chunk = {
    #                 "text": scenario["text"],
    #                 "metadata": {**scenario["metadata"], "type": "scenario"},
    #             }
    #             all_chunks.append(chunk)

    #             log(
    #                 f"   ✅ {scenario['metadata']['title']} ({scenario['metadata']['scenario_id']})"
    #             )

    #         stats["scenarios"] = len(scenarios_data)

    # except Exception as e:
    #     log(f"❌ Error loading scenarios: {e}")
    #     import traceback

    # traceback.print_exc()

    log("\n" + "-" * 80)
    log(f"📊 Scenarios: {stats['scenarios']}")

    # === PART 3: Add to Vector Store ===
    stats["total_chunks"] = len(all_chunks)

    log(f"\n5. Adding {stats['total_chunks']} chunks to vector store...")

    if stats["total_chunks"] == 0:
        log("❌ No documents loaded. Aborting.")
        return False

    try:
        # Prepare data
        texts = [c["text"] for c in all_chunks]
        metadata_list = [c["metadata"] for c in all_chunks]
        ids = [f"{c['metadata'].get('source', 'unknown')}_{i}" for i, c in enumerate(all_chunks)]

        # Add to retriever
        retriever.add_documents(documents=texts, metadata=metadata_list, ids=ids)

        log(f"   ✅ Added {stats['total_chunks']} chunks")

    except Exception as e:
        log(f"❌ Error adding documents: {e}")
        return False

    # === PART 4: Save ===
    log(f"\n6. Saving knowledge base as '{kb_name}'...")

    try:
        retriever.save(kb_name)
        log("   ✅ Saved successfully")
    except Exception as e:
        log(f"❌ Save failed: {e}")
        return False

    # === PART 5: Verify ===
    log("\n7. Verifying...")

    retriever_stats = retriever.get_statistics()
    save_path = Path(__file__).parent.parent / "vector_store_data"
    index_file = save_path / f"{kb_name}_index.faiss"
    meta_file = save_path / f"{kb_name}_metadata.pkl"

    if index_file.exists() and meta_file.exists():
        log(f"   Index: {index_file.name} ({index_file.stat().st_size / 1024:.1f} KB)")
        log(f"   Metadata: {meta_file.name} ({meta_file.stat().st_size / 1024:.1f} KB)")
        log(f"   Embedding model: {retriever_stats['embedding_model']}")
        log(f"   Embedding dim: {retriever_stats['embedding_dim']}")
        log(f"   Total chunks: {retriever_stats['total_documents']}")
    else:
        log("   ⚠️  Files not found")

    # === PART 6: Test Retrieval ===
    log("\n8. Testing retrieval...")

    test_queries = [
        ("neveikia internetas", "internet"),
        ("lėtas internetas", "internet"),
        ("internetas nutrūkinėja", "internet"),
        ("TV neveikia", "tv"),
        ("routerio lemputės", "internet"),
        ("WiFi slaptažodis", "internet"),
    ]

    test_passed = 0
    for query, expected_type in test_queries:
        results = retriever.retrieve(query, top_k=1, threshold=0.3)

        if results:
            result = results[0]
            result_type = result["metadata"].get("problem_type", "unknown")
            title = result["metadata"].get("title") or result["metadata"].get("source", "Unknown")
            section = result["metadata"].get("section", "")
            score = result["score"]
            chunk_type = result["metadata"].get("chunk_type", result["metadata"].get("type", ""))

            type_match = "✅" if result_type == expected_type else "⚠️"
            log(f"   {type_match} '{query}'")
            log(f"      → {title} | {section} | {chunk_type} ({score:.2f})")

            if result_type == expected_type:
                test_passed += 1
        else:
            log(f"   ❌ '{query}' → No results")

    # === Summary ===
    elapsed_time = time.time() - start_time

    log("\n" + "=" * 80)
    log("✅ KNOWLEDGE BASE BUILD COMPLETE")
    log("=" * 80)
    log("\n📊 Build Summary:")
    log(f"   Time: {elapsed_time:.1f}s")
    log(f"   KB name: {kb_name}")
    log(f"   Markdown files: {stats['markdown_files']}")
    log(f"   Markdown chunks: {stats['markdown_chunks']}")
    log(f"   Scenarios: {stats['scenarios']}")
    log(f"   Total chunks: {stats['total_chunks']}")

    if index_file.exists() and meta_file.exists():
        total_size = (index_file.stat().st_size + meta_file.stat().st_size) / 1024
        log(f"   Size: {total_size:.1f} KB")

    log(f"   Test queries: {test_passed}/{len(test_queries)} passed")

    log("\n📝 Usage:")
    log("   from rag import get_retriever")
    log("   retriever = get_retriever()")
    log(f"   retriever.load('{kb_name}')")
    log("   results = retriever.retrieve('neveikia internetas')")

    return True


def rebuild_all():
    """Rebuild all knowledge bases."""
    print("🔄 Rebuilding all knowledge bases...\n")

    success = build_knowledge_base("production")

    if success:
        print("\n✅ All knowledge bases rebuilt successfully!")
    else:
        print("\n❌ Build failed")
        sys.exit(1)


def show_stats():
    """Show current knowledge base statistics."""
    print("📊 Knowledge Base Statistics")
    print("=" * 60)

    retriever = get_retriever()

    # Try to load production KB
    save_path = Path(__file__).parent.parent / "vector_store_data"

    for kb_name in ["production", "default"]:
        index_file = save_path / f"{kb_name}_index.faiss"
        meta_file = save_path / f"{kb_name}_metadata.pkl"

        if index_file.exists() and meta_file.exists():
            success = retriever.load(kb_name)
            if success:
                stats = retriever.get_statistics()

                print(f"\n📁 {kb_name}:")
                print(f"   Documents: {stats['total_documents']}")
                print(f"   Index size: {index_file.stat().st_size / 1024:.1f} KB")
                print(f"   Metadata size: {meta_file.stat().st_size / 1024:.1f} KB")
                print(f"   Embedding dim: {stats['embedding_dim']}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build knowledge base with smart chunking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python build_kb.py                    # Build production KB
    python build_kb.py --name test        # Build test KB
    python build_kb.py --chunk-size 300   # Smaller chunks
    python build_kb.py --stats            # Show KB statistics
        """,
    )

    parser.add_argument(
        "--name", default="production", help="Knowledge base name (default: production)"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=400, help="Chunk size in words (default: 400)"
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=50, help="Chunk overlap in words (default: 50)"
    )
    parser.add_argument("--rebuild-all", action="store_true", help="Rebuild all knowledge bases")
    parser.add_argument("--stats", action="store_true", help="Show knowledge base statistics")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")

    args = parser.parse_args()

    try:
        if args.stats:
            show_stats()
        elif args.rebuild_all:
            rebuild_all()
        else:
            success = build_knowledge_base(
                kb_name=args.name,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
                verbose=not args.quiet,
            )
            sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Build interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

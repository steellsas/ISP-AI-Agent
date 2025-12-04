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
import re
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Setup paths for imports
current_dir = Path(__file__).parent
src_dir = current_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from rag import get_retriever
from rag.scenario_loader import get_scenario_loader

# Import utilities from shared package
try:
    from isp_shared.utils import get_logger
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger(__name__)


# =============================================================================
# DOCUMENT PROCESSOR - Smart Chunking
# =============================================================================


class DocumentProcessor:
    """
    Process markdown documents into chunks with rich metadata.

    Benefits:
    - Smaller chunks = better precision in retrieval
    - Metadata = better filtering (problem_type, section, etc.)
    - Section awareness = context preserved
    """

    def __init__(self, chunk_size: int = 400, chunk_overlap: int = 50):
        """
        Initialize processor.

        Args:
            chunk_size: Target chunk size in words
            chunk_overlap: Overlap between chunks in words
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process_markdown(
        self, content: str, source: str, base_metadata: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Process markdown file into chunks with metadata.

        Args:
            content: Markdown file content
            source: Source filename
            base_metadata: Additional metadata to include

        Returns:
            List of chunks with text and metadata
        """
        chunks = []
        base_metadata = base_metadata or {}

        # Extract problem_type from filename
        problem_type = self._extract_problem_type(source)

        # Extract title from first # header
        title = self._extract_title(content)

        # Split by ## headers (sections)
        sections = self._split_into_sections(content)

        for section_title, section_content in sections:
            # Determine chunk type based on section
            chunk_type = self._classify_section(section_title)

            # Check if section needs chunking
            word_count = len(section_content.split())

            if word_count <= self.chunk_size:
                # Small section - keep as one chunk
                chunks.append(
                    {
                        "text": f"# {title}\n## {section_title}\n{section_content}".strip(),
                        "metadata": {
                            "source": source,
                            "title": title,
                            "section": section_title,
                            "problem_type": problem_type,
                            "chunk_type": chunk_type,
                            "type": "document",
                            **base_metadata,
                        },
                    }
                )
            else:
                # Large section - split into chunks
                sub_chunks = self._chunk_text(section_content)

                for i, sub_chunk in enumerate(sub_chunks):
                    chunks.append(
                        {
                            "text": f"# {title}\n## {section_title} (dalis {i+1})\n{sub_chunk}".strip(),
                            "metadata": {
                                "source": source,
                                "title": title,
                                "section": section_title,
                                "problem_type": problem_type,
                                "chunk_type": chunk_type,
                                "chunk_index": i,
                                "type": "document",
                                **base_metadata,
                            },
                        }
                    )

        return chunks

    def _extract_problem_type(self, source: str) -> str:
        """Extract problem_type from filename."""
        source_lower = source.lower()

        if any(kw in source_lower for kw in ["internet", "wifi", "router"]):
            return "internet"
        elif any(kw in source_lower for kw in ["tv", "television", "decoder"]):
            return "tv"
        elif any(kw in source_lower for kw in ["phone", "telefon", "voip"]):
            return "phone"
        elif any(kw in source_lower for kw in ["billing", "invoice", "payment"]):
            return "billing"

        return "other"

    def _extract_title(self, content: str) -> str:
        """Extract title from first # header."""
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return "Unknown"

    def _split_into_sections(self, content: str) -> List[tuple]:
        """Split content by ## headers."""
        sections = []

        # Split by ## headers
        parts = re.split(r"\n##\s+", content)

        # First part might have # header
        if parts:
            first_part = parts[0]
            # Remove # header from first part
            first_part = re.sub(r"^#\s+.+\n", "", first_part).strip()
            if first_part:
                sections.append(("Įvadas", first_part))

        # Rest are ## sections
        for part in parts[1:]:
            lines = part.split("\n", 1)
            section_title = lines[0].strip()
            section_content = lines[1].strip() if len(lines) > 1 else ""

            if section_content:
                sections.append((section_title, section_content))

        return sections

    def _classify_section(self, title: str) -> str:
        """Classify section type for filtering."""
        title_lower = title.lower()

        if any(kw in title_lower for kw in ["žingsnis", "step", "troubleshoot"]):
            return "step"
        elif any(kw in title_lower for kw in ["simptom", "symptom", "požymi", "problema"]):
            return "symptom"
        elif any(kw in title_lower for kw in ["mcp", "diagnos", "check", "patikrin"]):
            return "diagnostic"
        elif any(kw in title_lower for kw in ["eskalac", "escalat", "sukurti", "ticket"]):
            return "escalation"
        elif any(kw in title_lower for kw in ["priežast", "cause", "dažn"]):
            return "cause"
        elif any(kw in title_lower for kw in ["greiti", "quick", "fast"]):
            return "quick_check"

        return "general"

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        words = text.split()
        chunks = []

        i = 0
        while i < len(words):
            chunk_words = words[i : i + self.chunk_size]
            chunks.append(" ".join(chunk_words))
            i += self.chunk_size - self.chunk_overlap

        return chunks


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
    log(f"   ✅ Retriever ready")
    log(f"   ✅ Document processor ready (chunk_size={chunk_size})")

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

    directories = ["troubleshooting", "procedures", "faq"]

    for directory in directories:
        dir_path = kb_path / directory

        if not dir_path.exists():
            log(f"⚠️  Skipping missing directory: {directory}/")
            continue

        md_files = list(dir_path.glob("*.md"))

        if not md_files:
            log(f"⚠️  No files in: {directory}/")
            continue

        log(f"\n📁 {directory}/")

        for md_file in md_files:
            # Skip empty files
            if md_file.stat().st_size == 0:
                log(f"   ⚠️  {md_file.name} (empty, skipped)")
                continue

            try:
                content = md_file.read_text(encoding="utf-8")

                # Process into chunks
                chunks = processor.process_markdown(
                    content=content, source=md_file.name, base_metadata={"category": directory}
                )

                all_chunks.extend(chunks)
                stats["markdown_files"] += 1
                stats["markdown_chunks"] += len(chunks)

                log(f"   ✅ {md_file.name} → {len(chunks)} chunks")

            except Exception as e:
                log(f"   ❌ {md_file.name}: {e}")

    log("\n" + "-" * 80)
    log(f"📊 Markdown: {stats['markdown_files']} files → {stats['markdown_chunks']} chunks")

    # === PART 2: Load YAML Scenarios ===
    log("\n4. Loading YAML scenarios...")
    log("-" * 80)

    try:
        scenario_loader = get_scenario_loader()
        scenarios_data = scenario_loader.get_scenarios_for_embedding()

        if not scenarios_data:
            log("⚠️  No scenarios found")
        else:
            log(f"\n📋 Scenarios:")

            for scenario in scenarios_data:
                # Convert to chunk format
                chunk = {
                    "text": scenario["text"],
                    "metadata": {**scenario["metadata"], "type": "scenario"},
                }
                all_chunks.append(chunk)

                log(
                    f"   ✅ {scenario['metadata']['title']} ({scenario['metadata']['scenario_id']})"
                )

            stats["scenarios"] = len(scenarios_data)

    except Exception as e:
        log(f"❌ Error loading scenarios: {e}")
        import traceback

        traceback.print_exc()

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
        log(f"   ✅ Saved successfully")
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
    log(f"\n📊 Build Summary:")
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

    log(f"\n📝 Usage:")
    log(f"   from rag import get_retriever")
    log(f"   retriever = get_retriever()")
    log(f"   retriever.load('{kb_name}')")
    log(f"   results = retriever.retrieve('neveikia internetas')")

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

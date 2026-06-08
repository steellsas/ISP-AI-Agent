"""
Document processing for the RAG knowledge base.

Turns markdown documents into retrieval chunks with rich metadata
(problem_type, section, chunk_type, lang). Smaller, section-aware chunks give
better retrieval precision, and the metadata lets retrieval filter by language
or problem domain.

This is the single canonical DocumentProcessor. build_kb.py imports it instead
of carrying its own copy, so chunking behaviour lives in exactly one place.
"""

from __future__ import annotations

import re
from typing import Any


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
        self, content: str, source: str, lang: str = "lt", base_metadata: dict | None = None
    ) -> list[dict[str, Any]]:
        """
        Process markdown file into chunks with metadata.

        Args:
            content: Markdown file content
            source: Source filename
            lang: Language code stamped on every chunk (matches ChunkMetadata.lang
                in ports/retrieval.py). Lets retrieval filter to one language.
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
                            "lang": lang,
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
                            "text": f"# {title}\n## {section_title} (dalis {i + 1})\n{sub_chunk}".strip(),
                            "metadata": {
                                "source": source,
                                "title": title,
                                "section": section_title,
                                "problem_type": problem_type,
                                "chunk_type": chunk_type,
                                "chunk_index": i,
                                "lang": lang,
                                "type": "document",
                                **base_metadata,
                            },
                        }
                    )

        return chunks

    def _extract_problem_type(self, source: str) -> str:
        """Extract problem_type from filename."""

        source_lower = source.lower()

        if any(kw in source_lower for kw in ["internet", "wifi"]):
            return "internet"
        elif any(kw in source_lower for kw in ["tv", "television", "decoder", "tv_box"]):
            return "tv"
        elif any(kw in source_lower for kw in ["phone", "telefon", "voip"]):
            return "phone"
        elif any(kw in source_lower for kw in ["router", "tplink", "equipment"]):
            return "equipment"
        elif any(kw in source_lower for kw in ["technician", "visit", "replacement", "procedur"]):
            return "procedure"

        return "other"

    def _extract_title(self, content: str) -> str:
        """Extract title from first # header."""
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return "Unknown"

    def _split_into_sections(self, content: str) -> list[tuple]:
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

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        words = text.split()
        chunks = []

        i = 0
        while i < len(words):
            chunk_words = words[i : i + self.chunk_size]
            chunks.append(" ".join(chunk_words))
            i += self.chunk_size - self.chunk_overlap

        return chunks

# document_processor.py - NAUJAS failas

from typing import List, Dict, Any
import re


class DocumentProcessor:
    """Process .md documents into chunks with metadata."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def process_markdown(self, content: str, source: str) -> List[Dict[str, Any]]:
        """
        Process markdown into chunks with extracted metadata.

        Returns list of:
        {
            "text": "chunk text",
            "metadata": {
                "source": "internet_intermittent.md",
                "section": "Troubleshooting Žingsniai",
                "problem_type": "internet",
                "chunk_type": "step" | "symptom" | "diagnostic" | "escalation"
            }
        }
        """
        chunks = []

        # Extract problem_type from filename
        problem_type = self._extract_problem_type(source)

        # Split by sections (## headers)
        sections = re.split(r"\n## ", content)

        for section in sections:
            if not section.strip():
                continue

            # Get section title
            lines = section.split("\n")
            section_title = lines[0].strip("#").strip()
            section_content = "\n".join(lines[1:])

            # Determine chunk type
            chunk_type = self._classify_section(section_title)

            # Chunk large sections
            if len(section_content) > self.chunk_size:
                sub_chunks = self._chunk_text(section_content)
                for i, sub_chunk in enumerate(sub_chunks):
                    chunks.append(
                        {
                            "text": f"{section_title}\n{sub_chunk}",
                            "metadata": {
                                "source": source,
                                "section": section_title,
                                "problem_type": problem_type,
                                "chunk_type": chunk_type,
                                "chunk_index": i,
                            },
                        }
                    )
            else:
                chunks.append(
                    {
                        "text": f"{section_title}\n{section_content}",
                        "metadata": {
                            "source": source,
                            "section": section_title,
                            "problem_type": problem_type,
                            "chunk_type": chunk_type,
                        },
                    }
                )

        return chunks

    def _extract_problem_type(self, source: str) -> str:
        """Extract problem_type from filename."""
        source_lower = source.lower()
        if "internet" in source_lower:
            return "internet"
        elif "tv" in source_lower:
            return "tv"
        elif "phone" in source_lower:
            return "phone"
        return "other"

    def _classify_section(self, title: str) -> str:
        """Classify section type for better filtering."""
        title_lower = title.lower()
        if any(kw in title_lower for kw in ["žingsnis", "step", "troubleshoot"]):
            return "step"
        elif any(kw in title_lower for kw in ["simptom", "symptom", "požymi"]):
            return "symptom"
        elif any(kw in title_lower for kw in ["mcp", "diagnos", "check"]):
            return "diagnostic"
        elif any(kw in title_lower for kw in ["eskalac", "escalat"]):
            return "escalation"
        elif any(kw in title_lower for kw in ["priežast", "cause", "dažn"]):
            return "cause"
        return "general"

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        words = text.split()
        chunks = []

        i = 0
        while i < len(words):
            chunk_words = words[i : i + self.chunk_size]
            chunks.append(" ".join(chunk_words))
            i += self.chunk_size - self.overlap

        return chunks

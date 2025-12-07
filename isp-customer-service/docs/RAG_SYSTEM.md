# RAG System Documentation

Complete reference for the Retrieval-Augmented Generation knowledge system.

---

## Overview

The RAG (Retrieval-Augmented Generation) system provides context-aware troubleshooting guidance by combining semantic search with structured knowledge documents.

**Key Features:**
- Hybrid search (semantic + keyword)
- Multilingual embeddings (Lithuanian + English)
- Markdown-based knowledge base
- Query caching for performance

**File Locations:**
- `src/rag/embeddings.py` — Embedding manager
- `src/rag/vector_store.py` — FAISS wrapper
- `src/rag/retriever.py` — Hybrid retriever

---

## Architecture

### Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            RAG Pipeline                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Query: "internetas nutrūkinėja"                                          │
│                      │                                                      │
│                      ▼                                                      │
│   ┌──────────────────────────────────────┐                                 │
│   │         Embedding Manager            │                                 │
│   │                                      │                                 │
│   │   ┌────────────────────────────┐    │                                 │
│   │   │      Query Cache           │    │                                 │
│   │   │    (LRU, 1000 entries)     │    │                                 │
│   │   └────────────────────────────┘    │                                 │
│   │                                      │                                 │
│   │   ┌────────────────────────────┐    │                                 │
│   │   │   Sentence Transformer     │    │                                 │
│   │   │ (multilingual-mpnet-base)  │    │                                 │
│   │   └────────────────────────────┘    │                                 │
│   │                                      │                                 │
│   └───────────────────┬──────────────────┘                                 │
│                       │                                                     │
│                       ▼                                                     │
│              Query Vector [768 dims]                                        │
│                       │                                                     │
│          ┌────────────┴────────────┐                                       │
│          ▼                         ▼                                        │
│   ┌─────────────┐          ┌──────────────┐                                │
│   │  Semantic   │          │   Keyword    │                                │
│   │   Search    │          │   Matching   │                                │
│   │   (FAISS)   │          │   (TF-IDF)   │                                │
│   │     70%     │          │     30%      │                                │
│   └──────┬──────┘          └──────┬───────┘                                │
│          │                        │                                         │
│          └───────────┬────────────┘                                         │
│                      ▼                                                      │
│   ┌──────────────────────────────────────┐                                 │
│   │        Score Combination             │                                 │
│   │   final = 0.7*semantic + 0.3*keyword │                                 │
│   └───────────────────┬──────────────────┘                                 │
│                       │                                                     │
│                       ▼                                                     │
│   ┌──────────────────────────────────────┐                                 │
│   │      Re-ranking & Filtering          │                                 │
│   │    - Threshold: 0.4                  │                                 │
│   │    - Top-K: 3-5                      │                                 │
│   └───────────────────┬──────────────────┘                                 │
│                       │                                                     │
│                       ▼                                                     │
│               Retrieved Documents                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Integration with Agent

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Agent ↔ RAG Integration                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────┐                                                       │
│   │   ReAct Agent   │                                                       │
│   │                 │                                                       │
│   │  "Action:       │                                                       │
│   │   search_       │                                                       │
│   │   knowledge"    │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐    │
│   │ search_knowledge│─────▶│    Retriever    │─────▶│    Embedding    │    │
│   │     (tool)      │      │                 │      │     Manager     │    │
│   └─────────────────┘      └────────┬────────┘      └─────────────────┘    │
│                                     │                                       │
│                                     ▼                                       │
│                            ┌─────────────────┐                              │
│                            │  Vector Store   │                              │
│                            │    (FAISS)      │                              │
│                            └────────┬────────┘                              │
│                                     │                                       │
│                                     ▼                                       │
│                            Troubleshooting                                  │
│                            Documents                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Components

### Embedding Manager

Handles text-to-vector conversion with caching.

**File:** `src/rag/embeddings.py`

```python
class EmbeddingManager:
    """
    Manages text embeddings with caching and batch processing.
    
    Features:
    - Lazy model loading
    - Query result caching
    - Batch encoding
    """
    
    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-mpnet-base-v2",
        cache_size: int = 1000
    ):
        self.model_name = model_name
        self.cache_size = cache_size
        self._model = None  # Lazy loading
        self._cache = {}
```

**Model Info:**

| Property | Value |
|----------|-------|
| Model | `paraphrase-multilingual-mpnet-base-v2` |
| Dimensions | 768 |
| Languages | 50+ (including Lithuanian) |
| Max Sequence | 128 tokens |

---

### Vector Store

FAISS-based similarity search.

**File:** `src/rag/vector_store.py`

```python
class VectorStore:
    """
    FAISS vector store for document embeddings.
    
    Features:
    - Fast similarity search
    - Metadata storage
    - Save/load functionality
    """
    
    def __init__(self, embedding_dim: int = 768):
        self.embedding_dim = embedding_dim
        self.index = faiss.IndexFlatIP(embedding_dim)
        self.documents = []
        self.metadata = []
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `add()` | Add documents with embeddings |
| `search()` | Find similar documents |
| `save()` | Persist index to disk |
| `load()` | Load index from disk |

---

### Hybrid Retriever

Combines semantic and keyword search.

**File:** `src/rag/retriever.py`

```python
class Retriever:
    """
    Document retriever combining embeddings and vector store.
    
    Features:
    - Query encoding
    - Similarity search
    - Hybrid scoring (semantic + keyword)
    - Result ranking
    """
    
    def __init__(
        self,
        embedding_manager: EmbeddingManager,
        vector_store: VectorStore,
        top_k: int = 3,
        similarity_threshold: float = 0.4,
        keyword_weight: float = 0.3
    ):
        ...
```

**Retrieval Process:**

1. Encode query to vector
2. Search FAISS for semantic matches
3. Calculate keyword match scores
4. Combine scores: `final = 0.7 * semantic + 0.3 * keyword`
5. Filter by threshold and return top-k

---

## Knowledge Base



### Document Format

Markdown documents with clear sections:

```markdown
# Internet Not Working

## Overview
Common causes for complete internet outage...

## Check Router Lights
First, look at your router's LED lights...

### Power Light
- Green: Router is powered on
- Off: Check power connection

### Internet/WAN Light
- Green: Connection to ISP established
- Red/Orange: Problem with ISP connection

## Restart Router
1. Unplug the power cable
2. Wait 30 seconds
3. Plug back in
4. Wait 2 minutes for full startup
```

### Chunking

Documents are chunked by `##` sections for optimal retrieval:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Document Chunking                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   internet_no_connection.md                                                 │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐          │
│   │   Chunk 1       │   │   Chunk 2       │   │   Chunk 3       │          │
│   │                 │   │                 │   │                 │          │
│   │ # Overview      │   │ ## Router       │   │ ## Restart      │          │
│   │ Common causes.. │   │ Lights          │   │ Router          │          │
│   │                 │   │ Check LEDs...   │   │ 1. Unplug...    │          │
│   │                 │   │                 │   │                 │          │
│   │ metadata:       │   │ metadata:       │   │ metadata:       │          │
│   │ source: file.md │   │ source: file.md │   │ source: file.md │          │
│   │ section: Overv. │   │ section: Lights │   │ section: Restart│          │
│   └─────────────────┘   └─────────────────┘   └─────────────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Usage

### Tool Usage (Agent)

The agent uses RAG through the `search_knowledge` tool:

```
Action: search_knowledge
Action Input: {"query": "lėtas internetas wifi"}
```

### Response Format

```json
{
  "success": true,
  "results": [
    {
      "title": "Slow Internet Troubleshooting",
      "content": "## WiFi Optimization\n\n1. Check router placement...",
      "score": 0.85,
      "category": "troubleshooting",
      "source": "internet_slow.md"
    }
  ]
}
```

### Direct API Usage

```python
from rag import get_retriever

retriever = get_retriever()

# Simple query
results = retriever.retrieve(
    query="internetas neveikia",
    top_k=3
)

for result in results:
    print(f"Score: {result['score']:.3f}")
    print(f"Content: {result['content'][:200]}...")
```

---

## Building Knowledge Base

### Initial Build

```bash
# Build FAISS index from markdown files
uv run python -m src.rag.scripts.build_kb
```

### What It Does

1. Scans `knowledge_base/` directory
2. Loads all `.md` files
3. Chunks by `##` sections
4. Generates embeddings
5. Builds FAISS index
6. Saves to `data/faiss_index/`

### Rebuild After Changes

```bash
# Rebuild index after adding/modifying documents
uv run python -m src.rag.scripts.build_kb --force
```

---

## Configuration

### Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `top_k` | 3 | Number of results to return |
| `similarity_threshold` | 0.4 | Minimum score to include |
| `keyword_weight` | 0.3 | Weight for keyword matching |
| `cache_size` | 1000 | Query cache size |

### Environment Variables

```bash
# Knowledge base location
RAG_KNOWLEDGE_BASE_PATH=./knowledge_base

# Index storage
RAG_INDEX_PATH=./data/faiss_index

# Embedding model (optional)
RAG_EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2
```

---

## Optimization

### Performance Tips

| Tip | Impact |
|-----|--------|
| Use query caching | Faster repeated queries |
| Chunk size ~500 tokens | Better retrieval accuracy |
| Pre-build index | Faster startup |
| Use GPU for embeddings | 10x faster encoding |

### Caching

Query embeddings are cached automatically:

```python
# First call - computes embedding
results = retriever.retrieve("internetas neveikia")

# Second call - uses cached embedding
results = retriever.retrieve("internetas neveikia")  # ~10x faster
```

---

## Adding Knowledge

### Step 1: Create Document

Create markdown file in `knowledge_base/troubleshooting/`:

```markdown
# New Issue Type

## Overview
Description of the issue...

## Step 1: Check Something
Instructions...

## Step 2: Try This
More instructions...
```

### Step 2: Rebuild Index

```bash
uv run python -m src.rag.scripts.build_kb --force
```

### Step 3: Test Retrieval

```bash
# Test search
uv run python -c "
from rag import get_retriever
r = get_retriever()
results = r.retrieve('new issue keywords')
print(results)
"
```

---

## Troubleshooting

### Low Relevance Scores

- Check document keywords match query terms
- Ensure documents are properly chunked
- Try lowering `similarity_threshold`

### Missing Results

- Verify document is in `knowledge_base/`
- Rebuild index after adding documents
- Check file encoding (UTF-8)

### Slow Performance

- Enable query caching
- Pre-build index at startup
- Consider GPU for large knowledge bases

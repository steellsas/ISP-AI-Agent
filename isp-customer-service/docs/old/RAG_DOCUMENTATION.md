# RAG System Documentation

## Overview

The RAG (Retrieval-Augmented Generation) system provides intelligent document retrieval for the ISP Customer Service Chatbot. It combines semantic understanding with keyword matching to find the most relevant troubleshooting guides, procedures, and FAQ content.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Components](#components)
3. [Knowledge Base Structure](#knowledge-base-structure)
4. [How Retrieval Works](#how-retrieval-works)
5. [Building the Knowledge Base](#building-the-knowledge-base)
6. [Usage Examples](#usage-examples)
7. [Configuration](#configuration)
8. [Performance Optimizations](#performance-optimizations)
9. [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAG System                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Query      │───▶│   Hybrid     │───▶│   Results    │       │
│  │   Input      │    │   Retriever  │    │   Ranked     │       │
│  └──────────────┘    └──────┬───────┘    └──────────────┘       │
│                             │                                    │
│                    ┌────────┴────────┐                          │
│                    │                 │                          │
│              ┌─────▼─────┐    ┌──────▼──────┐                   │
│              │  Semantic │    │   Keyword   │                   │
│              │  Search   │    │   Matching  │                   │
│              │  (70%)    │    │   (30%)     │                   │
│              └─────┬─────┘    └──────┬──────┘                   │
│                    │                 │                          │
│              ┌─────▼─────┐    ┌──────▼──────┐                   │
│              │  FAISS    │    │  Technical  │                   │
│              │  Index    │    │  Keywords   │                   │
│              └───────────┘    └─────────────┘                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Query Input**: User's problem description (e.g., "internet not working")
2. **Embedding**: Query converted to 768-dimensional vector
3. **Semantic Search**: FAISS finds similar document embeddings
4. **Keyword Boost**: Technical terms get additional scoring
5. **Re-ranking**: Results sorted by hybrid score
6. **Output**: Top-K most relevant documents with metadata

---

## Components

### 1. EmbeddingManager (`embeddings.py`)

Converts text into numerical vectors for similarity comparison.

**Features:**
- Model: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`
- Dimensions: 768
- Multilingual: Supports Lithuanian and English
- Lazy Loading: Model loads only when first needed
- Query Caching: Repeated queries served from cache

**Key Methods:**
```python
from rag import get_embedding_manager

manager = get_embedding_manager()
embedding = manager.encode_query("internet not working")  # Returns 768-dim vector
```

### 2. VectorStore (`vector_store.py`)

Stores and indexes document embeddings using FAISS.

**Features:**
- Index Type: FlatL2 (exact search)
- Persistence: Saves/loads from disk
- Metadata: Stores document metadata alongside vectors

**Key Methods:**
```python
from rag import get_vector_store

store = get_vector_store()
store.add(embeddings, documents, metadata)
results = store.search(query_embedding, top_k=5)
```

### 3. Retriever (`retriever.py`)

Base retriever combining embeddings and vector store.

**Features:**
- Semantic similarity search
- Configurable threshold and top_k
- Document loading from directories

**Key Methods:**
```python
from rag import get_retriever

retriever = get_retriever(top_k=5, similarity_threshold=0.5)
retriever.load("production")
results = retriever.retrieve("slow internet")
```

### 4. HybridRetriever (`hybrid_retriever.py`)

Enhanced retriever combining semantic search with keyword matching.

**Features:**
- Semantic Score (70%): Meaning-based similarity
- Keyword Score (30%): Exact term matching
- Technical Keywords: Boosted matching for ISP terms
- Stop Words: Filters common words in LT/EN

**Technical Keywords:**
```python
# Network terms
"wan", "lan", "dns", "dhcp", "ip", "nat", "gateway"
"wifi", "5ghz", "2.4ghz", "ssid", "wpa", "wpa2"

# Hardware
"router", "modem", "ont", "switch", "fiber", "dsl", "ethernet"

# Lithuanian terms
"maršrutizatorius", "modemas", "prievadas", "kabelis"
```

**Key Methods:**
```python
from rag import get_hybrid_retriever

retriever = get_hybrid_retriever(keyword_weight=0.3)
retriever.load("production")
results = retriever.retrieve("WAN cable disconnected", top_k=5)

# Results include:
# - semantic_score: 0.85
# - keyword_score: 0.60
# - hybrid_score: 0.78
# - keyword_matches: ["wan", "cable"]
```

### 5. DocumentProcessor (`document_processor.py`)

Processes markdown files into searchable chunks.

**Features:**
- Section-based splitting (by `##` headers)
- Configurable chunk size (default: 400 words)
- Overlapping chunks (default: 50 words)
- Rich metadata extraction

**Chunk Types:**
| Type | Detection Keywords |
|------|-------------------|
| `step` | žingsnis, step, troubleshoot |
| `symptom` | simptom, symptom, požymi, problema |
| `diagnostic` | mcp, diagnos, check, patikrin |
| `escalation` | eskalac, escalat, sukurti, ticket |
| `cause` | priežast, cause, dažn |
| `quick_check` | greiti, quick, fast |
| `general` | (default) |

### 6. ScenarioLoader (`scenario_loader.py`)

Loads YAML troubleshooting scenarios.

**Features:**
- Parses structured troubleshooting flows
- Extracts step sequences
- Generates embeddings for scenarios

---

## Knowledge Base Structure

```
src/rag/knowledge_base/
├── troubleshooting/
│   ├── internet_intermittent.md    # Intermittent connection issues
│   ├── internet_no_connection.md   # No internet connection
│   ├── internet_slow.md            # Slow internet speed
│   ├── tv_no_signal.md             # TV signal problems
│   └── scenarios/
│       ├── internet_no_connection.yaml
│       ├── internet_single_device.yaml
│       ├── internet_slow.yaml
│       └── tv_no_signal.yaml
├── procedures/
│   └── outer_restart.md            # Router restart procedure
└── faq/
    └── general_faq.md              # Frequently asked questions
```

### Document Format (Markdown)

```markdown
# Internet Not Working - Troubleshooting

## Problem
Customer reports no internet connectivity.

## Symptoms
- No WiFi connection
- Router lights abnormal
- All devices affected

## Quick Checks
1. Is the router powered on?
2. Are cables properly connected?
3. Is there a known outage?

## Step 1: Check Router Lights
Verify the power and WAN lights are solid green...

## Step 2: Restart Router
Unplug the router for 30 seconds...

## MCP Diagnostics
Use `check_port_status()` to verify connectivity...

## Escalation
Create ticket if problem persists after all steps...
```

### Scenario Format (YAML)

```yaml
id: internet_no_connection
title: "Internet Connection Issues"
description: "Troubleshooting for no internet"
problem_type: internet

steps:
  - id: check_lights
    title: "Check Router Lights"
    instruction: "Ask customer about router LED status"
    expected_responses:
      all_green: next_step
      red_light: escalate
      no_lights: check_power
    
  - id: restart_router
    title: "Restart Router"
    instruction: "Guide customer through router restart"
    wait_time: 30
```

---

## How Retrieval Works

### Step 1: Query Processing

```python
query = "internetas neveikia, visos lemputės raudonos"

# 1. Generate embedding
embedding = embedding_manager.encode_query(query)
# Result: [0.023, -0.145, 0.089, ...] (768 dimensions)
```

### Step 2: Semantic Search (FAISS)

```python
# 2. Find similar documents in vector store
# Uses cosine similarity (normalized L2 distance)
semantic_results = vector_store.search(embedding, top_k=15)

# Returns documents with similarity scores:
# - "Internet Not Working" → 0.85
# - "Router Restart Procedure" → 0.72
# - "Slow Internet" → 0.68
```

### Step 3: Keyword Boosting

```python
# 3. Extract keywords from query
query_keywords = {"internetas", "neveikia", "lemputės", "raudonos"}

# 4. Match against document keywords
for result in semantic_results:
    doc_keywords = extract_keywords(result.document)
    
    # Count overlaps
    common = query_keywords & doc_keywords  # {"internetas", "lemputės"}
    technical = common & TECHNICAL_KEYWORDS  # {"lemputės"}
    
    # Calculate keyword score
    keyword_score = len(common) * 0.1 + len(technical) * 0.15
```

### Step 4: Hybrid Scoring

```python
# 5. Combine scores
semantic_weight = 0.7
keyword_weight = 0.3

for result in results:
    result.hybrid_score = (
        result.semantic_score * semantic_weight +
        result.keyword_score * keyword_weight
    )

# 6. Re-rank by hybrid score
results.sort(by=hybrid_score, descending=True)
```

### Step 5: Return Results

```python
# Final output
[
    {
        "document": "# Internet Not Working...",
        "score": 0.82,  # hybrid_score
        "semantic_score": 0.85,
        "keyword_score": 0.75,
        "keyword_matches": ["internetas", "lemputės"],
        "metadata": {
            "source": "internet_no_connection.md",
            "title": "Internet Not Working",
            "section": "Check Router Lights",
            "problem_type": "internet",
            "chunk_type": "step"
        }
    },
    ...
]
```

---

## Building the Knowledge Base

### Initial Build

```bash
cd chatbot_core
uv run python src/rag/scripts/build_kb.py --name production
```

### Rebuild After Changes

```bash
uv run python src/rag/scripts/build_kb.py --rebuild-all
```

### Build Options

```bash
# Custom chunk size (smaller = more precise, larger = more context)
uv run python src/rag/scripts/build_kb.py --chunk-size 300

# View statistics
uv run python src/rag/scripts/build_kb.py --stats

# Quiet mode
uv run python src/rag/scripts/build_kb.py --quiet
```

### Build Output

```
================================================================================
KNOWLEDGE BASE BUILDER v2 (with Chunking)
================================================================================

📁 troubleshooting/
   ✅ internet_intermittent.md → 9 chunks
   ✅ internet_no_connection.md → 6 chunks
   ✅ internet_slow.md → 5 chunks
   ✅ tv_no_signal.md → 10 chunks

📁 procedures/
   ✅ outer_restart.md → 10 chunks

📁 faq/
   ✅ general_faq.md → 8 chunks

📊 Markdown: 6 files → 48 chunks
📊 Scenarios: 4
📊 TOTAL: 52 chunks

✅ KNOWLEDGE BASE BUILD COMPLETE
   Size: 191.9 KB
   Test queries: 4/6 passed
```

### Generated Files

```
src/rag/vector_store_data/
├── production_index.faiss      # FAISS vector index (~156 KB)
└── production_metadata.pkl     # Document metadata (~36 KB)
```

---

## Usage Examples

### Basic Retrieval

```python
from src.rag import get_hybrid_retriever, init_rag

# Initialize (do once at startup)
init_rag(kb_name="production", use_hybrid=True)

# Get retriever
retriever = get_hybrid_retriever()

# Search
results = retriever.retrieve("slow internet speed", top_k=3)

for r in results:
    print(f"Score: {r['score']:.2f}")
    print(f"Title: {r['metadata']['title']}")
    print(f"Section: {r['metadata']['section']}")
    print(f"Document: {r['document'][:200]}...")
    print("---")
```

### Filtered Retrieval

```python
# Only search internet-related documents
results = retriever.retrieve(
    query="connection drops",
    top_k=5,
    filter_metadata={"problem_type": "internet"}
)
```

### Context for LLM

```python
# Get formatted context for LLM prompt
context = retriever.retrieve_with_context(
    query="router lights are red",
    top_k=3,
    include_scores=True
)

prompt = f"""
Based on the following knowledge base:

{context}

Help the customer with their router issue.
"""
```

### In Troubleshooting Node

```python
# src/graph/nodes/troubleshooting.py

from src.rag import get_hybrid_retriever

def select_scenario(problem_description: str, problem_type: str) -> str:
    """Select best troubleshooting scenario using RAG."""
    
    retriever = get_hybrid_retriever()
    
    # Enrich query with context
    query = f"{problem_type} {problem_description}"
    
    results = retriever.retrieve(
        query=query,
        top_k=1,
        filter_metadata={"type": "scenario"}
    )
    
    if results:
        return results[0]["metadata"]["scenario_id"]
    
    return "internet_no_connection"  # fallback
```

---

## Configuration

### Default Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `embedding_model` | `paraphrase-multilingual-mpnet-base-v2` | Multilingual model |
| `embedding_dim` | 768 | Vector dimensions |
| `top_k` | 5 | Default results count |
| `similarity_threshold` | 0.5 | Minimum score |
| `keyword_weight` | 0.3 | Keyword vs semantic balance |
| `chunk_size` | 400 | Words per chunk |
| `chunk_overlap` | 50 | Overlap between chunks |
| `query_cache_size` | 500 | Cached query embeddings |

### Adjusting Retrieval

```python
# More semantic (meaning-focused)
retriever = get_hybrid_retriever(keyword_weight=0.1)

# More keyword (exact match focused)
retriever = get_hybrid_retriever(keyword_weight=0.5)

# Add custom technical keywords
retriever.add_technical_keywords(["ont", "gpon", "ftth"])
```

---

## Performance Optimizations

### 1. Lazy Model Loading

The embedding model loads only when first query is made:

```python
# At import: ~0ms (no model loaded)
from rag import get_embedding_manager

# First query: ~3-5s (model loads)
manager.encode_query("test")

# Subsequent queries: ~50ms
manager.encode_query("another test")
```

### 2. Query Caching

Repeated queries are served from cache:

```python
# First time: ~50ms (compute embedding)
manager.encode_query("internet not working")

# Second time: ~0.1ms (from cache)
manager.encode_query("internet not working")
```

### 3. Pre-built Index

Knowledge base is built once and loaded from disk:

```python
# Build (run once): ~10s
python build_kb.py

# Load at runtime: ~0.5s
retriever.load("production")
```

### 4. Background Preloading

Start model loading in background during app startup:

```python
from rag import preload_embedding_model

# Non-blocking, loads in background thread
preload_embedding_model()
```

### Performance Metrics

| Operation | Time |
|-----------|------|
| Cold start (first query) | ~3-5s |
| Warm query (cached) | ~0.1ms |
| New query (not cached) | ~50ms |
| KB load from disk | ~0.5s |
| Full KB rebuild | ~10s |

---

## Troubleshooting

### Common Issues

#### 1. "No results found"

**Cause:** Query doesn't match any documents above threshold.

**Solutions:**
- Lower threshold: `retriever.retrieve(query, threshold=0.3)`
- Check if KB is loaded: `retriever.get_statistics()`
- Rebuild KB: `python build_kb.py --rebuild-all`

#### 2. "Module not found: sentence_transformers"

**Solution:**
```bash
uv pip install sentence-transformers
```

#### 3. "FAISS index not found"

**Cause:** Knowledge base not built.

**Solution:**
```bash
uv run python src/rag/scripts/build_kb.py --name production
```

#### 4. "Wrong results returned"

**Solutions:**
- Check chunk size (smaller = more precise)
- Adjust keyword_weight
- Add domain-specific keywords
- Review document structure

### Debugging

```python
# Check RAG status
from rag import get_hybrid_retriever

retriever = get_hybrid_retriever()
stats = retriever.get_statistics()
print(stats)

# Output:
# {
#     "total_documents": 52,
#     "embedding_model": "paraphrase-multilingual-mpnet-base-v2",
#     "embedding_dim": 768,
#     "hybrid_enabled": True,
#     "keyword_weight": 0.3
# }
```

```python
# Debug retrieval scores
results = retriever.retrieve("test query", top_k=5)

for r in results:
    print(f"Semantic: {r['semantic_score']:.3f}")
    print(f"Keyword:  {r['keyword_score']:.3f}")
    print(f"Hybrid:   {r['hybrid_score']:.3f}")
    print(f"Matches:  {r['keyword_matches']}")
    print("---")
```

### Logging

Enable detailed logging:

```python
import logging
logging.getLogger("rag").setLevel(logging.DEBUG)
```

---

## API Reference

### `init_rag(kb_name, preload_model, use_hybrid) -> bool`

Initialize RAG system.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| kb_name | str | "production" | Knowledge base name |
| preload_model | bool | True | Preload embedding model |
| use_hybrid | bool | True | Use hybrid retriever |

### `get_hybrid_retriever(keyword_weight, top_k, similarity_threshold) -> HybridRetriever`

Get hybrid retriever singleton.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| keyword_weight | float | 0.3 | Keyword vs semantic weight |
| top_k | int | 5 | Default result count |
| similarity_threshold | float | 0.5 | Minimum similarity |

### `HybridRetriever.retrieve(query, top_k, threshold, filter_metadata) -> List[Dict]`

Retrieve relevant documents.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| query | str | required | Search query |
| top_k | int | 5 | Number of results |
| threshold | float | None | Minimum score |
| filter_metadata | dict | None | Metadata filter |

**Returns:** List of result dictionaries:
```python
{
    "document": str,        # Document text
    "score": float,         # Hybrid score
    "semantic_score": float,
    "keyword_score": float,
    "keyword_matches": List[str],
    "metadata": {
        "source": str,
        "title": str,
        "section": str,
        "problem_type": str,
        "chunk_type": str
    }
}
```

---

## Changelog

### v2.0 (Current)
- ✅ Hybrid retrieval (semantic + keyword)
- ✅ Document chunking with metadata
- ✅ Lazy model loading
- ✅ Query caching
- ✅ Lithuanian technical keywords
- ✅ Stop word filtering

### v1.0
- Basic semantic search
- Full document indexing
- FAISS vector store

---

## Contributing

### Adding New Documents

1. Create markdown file in appropriate directory
2. Follow document format (# title, ## sections)
3. Rebuild knowledge base:
   ```bash
   uv run python src/rag/scripts/build_kb.py --rebuild-all
   ```

### Adding Technical Keywords

```python
# In hybrid_retriever.py
self.technical_keywords.add("new_keyword")

# Or at runtime
retriever.add_technical_keywords(["keyword1", "keyword2"])
```

### Testing Changes

```bash
# Run RAG tests
uv run python src/rag/scripts/test_rag_loading.py

# Test specific query
python -c "from rag import get_hybrid_retriever; r = get_hybrid_retriever(); r.load('production'); print(r.retrieve('test'))"
```

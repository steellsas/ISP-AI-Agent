# RAG System Documentation

Complete reference for the Retrieval-Augmented Generation knowledge system.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Components](#components)
- [Knowledge Base](#knowledge-base)
- [Scenario Format](#scenario-format)
- [Smart Routing](#smart-routing)



---

## Overview

The RAG (Retrieval-Augmented Generation) system provides context-aware troubleshooting guidance by combining semantic search with structured scenarios.

**Key Features:**
- Hybrid search (semantic + keyword)
- Multilingual embeddings
- YAML-based scenarios
- Smart routing based on problem context
- Query caching for performance

**File Locations:**
- `src/rag/embeddings.py` — Embedding manager
- `src/rag/vector_store.py` — FAISS wrapper
- `src/rag/retriever.py` — Hybrid retriever
- `src/rag/scenario_loader.py` — YAML scenario loader

---

## Architecture

### Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAG Pipeline                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Query: "internetas nutrūkinėja"                               │
│                     │                                            │
│                     ▼                                            │
│   ┌─────────────────────────────────┐                           │
│   │      Embedding Manager          │                           │
│   │   ┌─────────────────────────┐   │                           │
│   │   │  Query Cache            │   │                           │
│   │   │  (LRU, 1000 entries)    │   │                           │
│   │   └─────────────────────────┘   │                           │
│   │   ┌─────────────────────────┐   │                           │
│   │   │  Sentence Transformer   │   │                           │
│   │   │  (multilingual-mpnet)   │   │                           │
│   │   └─────────────────────────┘   │                           │
│   └────────────────┬────────────────┘                           │
│                    │                                             │
│                    ▼                                             │
│          Query Vector [768 dims]                                │
│                    │                                             │
│          ┌─────────┴─────────┐                                  │
│          ▼                   ▼                                   │
│   ┌─────────────┐    ┌──────────────┐                           │
│   │  Semantic   │    │   Keyword    │                           │
│   │   Search    │    │   Matching   │                           │
│   │   (FAISS)   │    │  (TF-IDF)    │                           │
│   │    70%      │    │     30%      │                           │
│   └──────┬──────┘    └──────┬───────┘                           │
│          │                  │                                    │
│          └────────┬─────────┘                                    │
│                   ▼                                              │
│   ┌─────────────────────────────────┐                           │
│   │     Score Combination           │                           │
│   │  final = 0.7*semantic + 0.3*kw  │                           │
│   └────────────────┬────────────────┘                           │
│                    │                                             │
│                    ▼                                             │
│   ┌─────────────────────────────────┐                           │
│   │     Re-ranking & Filtering      │                           │
│   │  - Threshold: 0.5               │                           │
│   │  - Top-K: 3-5                   │                           │
│   └────────────────┬────────────────┘                           │
│                    │                                             │
│                    ▼                                             │
│            Retrieved Documents                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Component Interaction

```
┌────────────────┐     ┌──────────────────┐     ┌────────────────┐
│  Troubleshoot  │────▶│    Retriever     │────▶│  Embedding     │
│     Node       │     │                  │     │  Manager       │
└────────────────┘     └────────┬─────────┘     └────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                    ▼                     ▼
            ┌──────────────┐      ┌──────────────┐
            │ Vector Store │      │   Keyword    │
            │   (FAISS)    │      │   Index      │
            └──────────────┘      └──────────────┘
                    │                     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │  Scenario Loader │
                    │     (YAML)       │
                    └──────────────────┘
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
    - GPU support (optional)
    """
    
    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-mpnet-base-v2",
        cache_size: int = 1000,
        device: str = "cpu"
    ):
        self.model_name = model_name
        self.cache_size = cache_size
        self.device = device
        self._model = None  # Lazy loading
        self._cache = {}
```

**Key Methods:**

```python
def encode_query(self, query: str) -> np.ndarray:
    """Encode single query with caching."""
    
    # Check cache
    cache_key = hash(query)
    if cache_key in self._cache:
        return self._cache[cache_key]
    
    # Encode
    embedding = self._get_model().encode(query, convert_to_numpy=True)
    
    # Cache result
    self._cache[cache_key] = embedding
    return embedding


def encode_documents(
    self, 
    documents: List[str],
    batch_size: int = 32,
    show_progress: bool = False
) -> np.ndarray:
    """Encode multiple documents in batches."""
    
    embeddings = self._get_model().encode(
        documents,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True
    )
    return embeddings
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
    - Multiple index types
    """
    
    def __init__(
        self,
        embedding_dim: int = 768,
        index_type: str = "flat"  # "flat" | "ivf" | "hnsw"
    ):
        self.embedding_dim = embedding_dim
        self.index = self._create_index(index_type)
        self.documents = []
        self.metadata = []
```

**Key Methods:**

```python
def add(
    self,
    embeddings: np.ndarray,
    documents: List[str],
    metadata: Optional[List[Dict]] = None,
    ids: Optional[List[str]] = None
):
    """Add documents to the index."""
    
    # Normalize embeddings for cosine similarity
    faiss.normalize_L2(embeddings)
    
    # Add to FAISS index
    self.index.add(embeddings)
    
    # Store documents and metadata
    self.documents.extend(documents)
    self.metadata.extend(metadata or [{}] * len(documents))


def search(
    self,
    query_embedding: np.ndarray,
    k: int = 5,
    threshold: float = 0.5
) -> List[Dict]:
    """Search for similar documents."""
    
    # Normalize query
    faiss.normalize_L2(query_embedding.reshape(1, -1))
    
    # Search
    scores, indices = self.index.search(query_embedding.reshape(1, -1), k)
    
    # Filter by threshold and format results
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx >= 0 and score >= threshold:
            results.append({
                "document": self.documents[idx],
                "metadata": self.metadata[idx],
                "score": float(score)
            })
    
    return results
```

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
    - Hybrid scoring
    - Result ranking
    """
    
    def __init__(
        self,
        embedding_manager: EmbeddingManager,
        vector_store: VectorStore,
        top_k: int = 3,
        similarity_threshold: float = 0.7,
        keyword_weight: float = 0.3
    ):
        self.embedding_manager = embedding_manager
        self.vector_store = vector_store
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.keyword_weight = keyword_weight
```

**Retrieval Process:**

```python
def retrieve(
    self,
    query: str,
    top_k: Optional[int] = None,
    threshold: Optional[float] = None,
    filter_metadata: Optional[Dict] = None
) -> List[Dict]:
    """
    Retrieve relevant documents for a query.
    
    1. Encode query
    2. Semantic search via FAISS
    3. Keyword matching boost
    4. Combine scores
    5. Filter and rank
    """
    
    # Encode query
    query_embedding = self.embedding_manager.encode_query(query)
    
    # Semantic search
    semantic_results = self.vector_store.search(
        query_embedding,
        k=top_k * 2,  # Get more for filtering
        threshold=threshold * 0.8  # Lower threshold initially
    )
    
    # Keyword boost
    for result in semantic_results:
        keyword_score = self._keyword_match(query, result["document"])
        result["score"] = (
            (1 - self.keyword_weight) * result["score"] +
            self.keyword_weight * keyword_score
        )
    
    # Re-rank and filter
    results = sorted(semantic_results, key=lambda x: x["score"], reverse=True)
    results = [r for r in results if r["score"] >= threshold]
    
    return results[:top_k]
```

**Keyword Matching:**

```python
def _keyword_match(self, query: str, document: str) -> float:
    """Calculate keyword match score."""
    
    # Technical terms that should boost score
    technical_keywords = {
        "router", "maršrutizatorius",
        "wifi", "bevielis",
        "wan", "lan",
        "dns", "ip",
        "decoder", "dekoderis",
        "signal", "signalas"
    }
    
    query_lower = query.lower()
    doc_lower = document.lower()
    
    # Count matching keywords
    matches = sum(1 for kw in technical_keywords 
                  if kw in query_lower and kw in doc_lower)
    
    return min(matches / 3, 1.0)  # Normalize to 0-1
```

---

### Scenario Loader

Loads and parses YAML troubleshooting scenarios.

**File:** `src/rag/scenario_loader.py`

```python
class ScenarioLoader:
    """
    Loads troubleshooting scenarios from YAML files.
    """
    
    def __init__(self, scenarios_dir: Path):
        self.scenarios_dir = scenarios_dir
        self.scenarios = {}
        self._load_all()
    
    def get_scenario(self, scenario_id: str) -> Optional[Dict]:
        """Get scenario by ID."""
        return self.scenarios.get(scenario_id)
    
    def get_step(self, scenario_id: str, step_number: int) -> Optional[Dict]:
        """Get specific step from scenario."""
        scenario = self.get_scenario(scenario_id)
        if scenario:
            steps = scenario.get("steps", [])
            for step in steps:
                if step.get("step_id") == step_number:
                    return step
        return None
```

---

## Knowledge Base

### Directory Structure

```
knowledge_base/
├── troubleshooting/
│   ├── internet_intermittent.md     # Markdown docs for RAG
│   ├── internet_no_connection.md
│   ├── internet_slow.md
│   ├── tv_no_signal.md
│   └── scenarios/                    # YAML scenarios
│       ├── internet_no_connection.yaml
│       ├── internet_single_device.yaml
│       ├── internet_slow.yaml
│       ├── internet_intermittent.yaml
│       └── tv_no_signal.yaml
├── procedures/
│   └── router_restart.md
└── faq/
    └── general.md
```

### Document Format

Markdown documents are chunked by `##` sections:

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
- Off: No WAN connection

## Restart Router
1. Unplug the power cable
2. Wait 30 seconds
3. Plug back in
4. Wait 2 minutes for full startup
```

**Chunking Result:**
```python
chunks = [
    {
        "text": "# Internet Not Working\n\n## Overview\nCommon causes...",
        "metadata": {
            "source": "internet_no_connection.md",
            "section": "Overview",
            "problem_type": "internet"
        }
    },
    {
        "text": "## Check Router Lights\nFirst, look at your router's...",
        "metadata": {
            "source": "internet_no_connection.md",
            "section": "Check Router Lights",
            "problem_type": "internet"
        }
    },
    # ...
]
```

---

## Scenario Format

### YAML Structure

```yaml
scenario:
  id: internet_no_connection
  title: "Interneto ryšio nebuvimas"
  title_en: "Internet Connection Issues"
  problem_type: internet
  description: "Klientas negali prisijungti prie interneto"
  
  # Keywords for retrieval matching
  keywords:
    - "neveikia internetas"
    - "nėra interneto"
    - "neprisijungia"
    - "no internet"
    - "not working"
  
  # Pre-conditions for this scenario
  conditions:
    scope: "all_devices"  # or "single_device"
    connection_pattern: "none"  # "none" | "intermittent" | "slow"
  
  steps:
    - step_id: 1
      title: "Maršrutizatoriaus lemputės"
      title_en: "Router Lights"
      instruction: |
        Paprašykite kliento patikrinti maršrutizatoriaus lemputes.
        Ar visos lemputės šviečia? Kokios spalvos?
      instruction_en: |
        Ask customer to check router lights.
        Are all lights on? What colors?
      
      help_text: |
        Maršrutizatorius paprastai turi 4-5 lemputes:
        - Power (maitinimas) - turėtų šviesti žaliai
        - Internet/WAN - turėtų šviesti žaliai
        - WiFi - turėtų šviesti žaliai
        - LAN (1-4) - šviečia jei prijungti įrenginiai
      
      expected_outcomes:
        - pattern: "visos žalios|all green|šviečia"
          action: "next_step"
          
        - pattern: "raudona|red|oranžinė|orange"
          action: "escalate"
          reason: "WAN lemputė rodo ryšio problemą"
          
        - pattern: "nedega|nešviečia|off|no lights"
          action: "goto_step"
          target: "check_power"
      
      skip_if:
        - "router_lights" in problem_context
    
    - step_id: 2
      id: "router_restart"
      title: "Maršrutizatoriaus perkrovimas"
      instruction: |
        Paprašykite kliento perkrauti maršrutizatorių:
        1. Išjunkite maršrutizatorių iš elektros
        2. Palaukite 30 sekundžių
        3. Vėl įjunkite
        4. Palaukite 2 minutes kol užsikraus
      
      wait_time: 120  # seconds to wait
      
      expected_outcomes:
        - pattern: "veikia|works|pavyko|fixed"
          action: "resolve"
          
        - pattern: "neveikia|still not|vis dar"
          action: "next_step"
    
    - step_id: 3
      title: "Kabelių patikrinimas"
      instruction: |
        Patikrinkite ar visi kabeliai tvirtai prijungti:
        - Maitinimo kabelis
        - Interneto kabelis (į WAN portą)
        - LAN kabelis (jei naudojate)
      
      expected_outcomes:
        - pattern: "tvirtai|visi prijungti|all connected"
          action: "next_step"
          
        - pattern: "atsilaisvinęs|loose|unplugged"
          action: "retry_connection"
  
  escalation:
    conditions:
      - "3 žingsniai nesėkmingi"
      - "fizinė problema aptikta"
      - "kliento įranga sugedusi"
    
    ticket_type: "technician_visit"
    priority: "high"
    
    message: |
      Deja, problemos nepavyko išspręsti nuotoliniu būdu.
      Sukursiu užklausą technikui, kuris susisieks su jumis 
      per 24 valandas.
```

### Step Properties

| Property | Type | Description |
|----------|------|-------------|
| `step_id` | `int` | Unique step number |
| `id` | `str` | Optional string ID for references |
| `title` | `str` | Step title (LT) |
| `title_en` | `str` | Step title (EN) |
| `instruction` | `str` | What to tell customer |
| `help_text` | `str` | Additional explanation if customer asks |
| `wait_time` | `int` | Seconds to wait (for restart steps) |
| `expected_outcomes` | `list` | Pattern-action mappings |
| `skip_if` | `list` | Conditions to auto-skip step |

### Outcome Actions

| Action | Description |
|--------|-------------|
| `next_step` | Proceed to next step |
| `resolve` | Mark problem as resolved |
| `escalate` | Create ticket and end |
| `goto_step` | Jump to specific step |
| `retry_connection` | Re-check after fix |

---

## Smart Routing

The system uses intelligent scenario selection based on problem context.

**File:** `src/rag/retriever.py` → `get_smart_scenario_id()`

### Routing Logic

```python
def get_smart_scenario_id(
    problem_type: str,
    problem_context: dict,
    problem_description: str,
    diagnostic_results: dict
) -> str:
    """
    Hybrid scenario selection: Smart routing + RAG.
    
    Priority order:
    1. Instant routing for clear patterns
    2. RAG search for complex cases
    3. Default fallback
    """
    
    # PRIORITY 1: Single device issue
    scope = problem_context.get("scope", "").lower()
    if any(kw in scope for kw in ["telefonas", "vienas", "phone", "one device"]):
        return "internet_single_device"
    
    # PRIORITY 2: Connection pattern
    pattern = problem_context.get("connection_pattern", "").lower()
    
    if any(kw in pattern for kw in ["nutrūksta", "kartais", "intermittent"]):
        return "internet_intermittent"
    
    if any(kw in pattern for kw in ["lėtas", "slow", "wolno"]):
        return "internet_slow"
    
    # PRIORITY 3: RAG search
    query = f"{problem_type} {problem_description}"
    results = retriever.retrieve(query, top_k=1, threshold=0.6)
    
    if results:
        scenario_id = results[0]["metadata"].get("scenario_id")
        if scenario_id:
            return scenario_id
    
    # PRIORITY 4: Default by problem type
    defaults = {
        "internet": "internet_no_connection",
        "tv": "tv_no_signal",
        "phone": "phone_no_dial_tone"
    }
    return defaults.get(problem_type, "internet_no_connection")
```

### Routing Decision Tree

```
                    ┌─────────────────┐
                    │  Problem Type   │
                    │  + Context      │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   Single Device?     Connection Pattern?    RAG Search
        │                    │                    │
        ▼                    ▼                    ▼
internet_single_     ┌──────┴──────┐      scenario from
    device           │             │      similarity
                 intermittent?  slow?
                     │             │
                     ▼             ▼
              internet_      internet_
              intermittent   slow
```

---

## Usage

### Initialization

```python
from rag import init_rag, get_retriever

# Initialize RAG system (once at startup)
init_rag(
    kb_path="knowledge_base/",
    use_hybrid=True,
    cache_size=1000
)

# Get retriever instance
retriever = get_retriever()
```

### Basic Retrieval

```python
# Simple query
results = retriever.retrieve(
    query="internetas neveikia",
    top_k=3
)

for result in results:
    print(f"Score: {result['score']:.3f}")
    print(f"Document: {result['document'][:200]}...")
    print(f"Source: {result['metadata']['source']}")
```

### Filtered Retrieval

```python
# Filter by problem type
results = retriever.retrieve(
    query="connection drops randomly",
    top_k=5,
    filter_metadata={"problem_type": "internet"}
)
```

### Context Retrieval

```python
# Get formatted context for LLM
context = retriever.retrieve_with_context(
    query="router lights are red",
    top_k=3,
    include_scores=True
)


```

### With Scenario Loader

```python
from rag.scenario_loader import get_scenario_loader

loader = get_scenario_loader()

# Get scenario
scenario = loader.get_scenario("internet_no_connection")

# Get specific step
step = loader.get_step("internet_no_connection", step_number=2)
print(step["instruction"])
```

---

## Optimization

### Performance Tuning

| Parameter | Default | Range | Impact |
|-----------|---------|-------|--------|
| `top_k` | 3 | 1-10 | More = slower, more comprehensive |
| `threshold` | 0.5 | 0.3-0.8 | Higher = fewer but better matches |
| `cache_size` | 1000 | 100-5000 | Higher = more memory, faster repeats |
| `keyword_weight` | 0.3 | 0.0-0.5 | Higher = more keyword influence |

### Caching Strategy

```python

embedding_manager = EmbeddingManager(cache_size=1000)

# Document caching (results)
@lru_cache(maxsize=500)
def cached_retrieve(query: str, top_k: int) -> tuple:
    results = retriever.retrieve(query, top_k)
    return tuple(results)  # Convert to hashable
```

### Index Types

| Type | Speed | Memory | Use Case |
|------|-------|--------|----------|
| `flat` | Fast for <10K docs | High | Demo, small KB |
| `ivf` | Fast for >10K docs | Medium | Production |
| `hnsw` | Very fast | High | Real-time apps |




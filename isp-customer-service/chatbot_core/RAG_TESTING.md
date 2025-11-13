# RAG System - Testing Instructions

## 📦 Installation

Install dependencies using UV:

```bash
cd chatbot_core
uv sync
```

This will install:
- `sentence-transformers` - Multilingual embeddings
- `faiss-cpu` - Vector store
- `numpy` - Numerical operations
- `pyyaml` - Config loading

## 📁 Knowledge Base Structure

```
src/rag/knowledge_base/
├── troubleshooting/
│   └── internet_slow.md          ✅ Sample doc
├── procedures/
│   └── router_restart.md         ✅ Sample doc
└── faq/
    └── general_faq.md            ✅ Sample doc
```

## 🧪 Running Tests

### Method 1: Using launcher script (Recommended)

```bash
cd chatbot_core
uv run python run_rag_test.py
```

### Method 2: Direct test execution

```bash
cd chatbot_core
uv run python src/rag/test_rag_loading.py
```

### Method 3: Python module

```bash
cd chatbot_core
uv run python -m src.rag.test_rag_loading
```

## 📊 Expected Output

```
==================================================
RAG DOCUMENT LOADING TEST
==================================================

1. Initializing retriever...
✅ Retriever initialized

2. Knowledge base path: .../knowledge_base

3. Loading documents from: troubleshooting/
------------------------------------------------------------
   Found 1 markdown files
✅ Loaded 1 documents from troubleshooting/
   📄 internet_slow.md

3. Loading documents from: procedures/
------------------------------------------------------------
   Found 1 markdown files
✅ Loaded 1 documents from procedures/
   📄 router_restart.md

3. Loading documents from: faq/
------------------------------------------------------------
   Found 1 markdown files
✅ Loaded 1 documents from faq/
   📄 general_faq.md

==================================================
TOTAL DOCUMENTS LOADED: 3
==================================================

4. Retriever Statistics:
------------------------------------------------------------
   embedding_model: paraphrase-multilingual-mpnet-base-v2
   embedding_dim: 768
   total_documents: 3
   top_k: 3
   similarity_threshold: 0.5

==================================================
TESTING DOCUMENT RETRIEVAL
==================================================

1. Query: 'Internetas neveikia'
------------------------------------------------------------

   Result 1 (Score: 0.782)
   Title: Lėtas Internetas - Troubleshooting
   Category: troubleshooting
   File: internet_slow.md
   Snippet: # Lėtas Internetas - Troubleshooting...
```

## 🔧 Troubleshooting

### Issue: sentence-transformers not found

```bash
cd chatbot_core
uv pip install sentence-transformers
```

### Issue: faiss not found

```bash
cd chatbot_core
uv pip install faiss-cpu
```

### Issue: Model download slow

First run downloads ~400MB model from HuggingFace.
- Be patient (5-10 minutes)
- Model is cached for future use
- Location: `~/.cache/torch/sentence_transformers/`

### Issue: Import errors

Make sure you're in the `chatbot_core` directory:
```bash
pwd  # Should show: .../isp-customer-service/chatbot_core
```

## 📝 Test Details

The test performs 4 checks:

1. **Document Loading** - Loads 3 sample documents
2. **Retrieval Testing** - Tests 7 queries (Lithuanian & English)
3. **Context Formatting** - Tests formatted context generation
4. **Persistence** - Tests save/load functionality

## 🎯 What's Being Tested

### Multilingual Support
- Lithuanian queries: "Internetas neveikia", "Lėtas internetas"
- English queries: "Internet not working", "Slow speed"
- Should retrieve relevant docs regardless of language

### Semantic Search
- Query: "Kaip perkrauti maršrutizatorių?"
- Should find: `router_restart.md`
- Even though exact words may differ

### Similarity Scoring
- Higher score = more relevant
- Threshold: 0.5 (configurable)
- Top 3 results returned

## 📈 Next Steps

After successful test:
1. Add more documents to knowledge_base directories
2. Adjust `top_k` and `similarity_threshold` in config
3. Integrate with LangGraph workflow
4. Test in production scenarios

## 🐛 Known Issues

- First run is slow (model download)
- Large documents may need chunking (TODO)
- FAISS on Windows may require specific build (use faiss-cpu)

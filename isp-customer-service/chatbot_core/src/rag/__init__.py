"""RAG data — the knowledge itself, and the tool that indexes it.

Nuo 5 bangos čia nebe kodas, o **duomenys**: `knowledge_base/` markdown dokumentai su YAML
antgalviais, jiems skirtas žodynas (`_vocabulary.yaml`) ir rikiavimo klausimų rinkinys
(`_questions.yaml`), plius viena eksploatacijos priemonė — `scripts/index_qdrant.py`.

Paieškos kodas gyvena kitur, ir sąmoningai:

    agent/knowledge_base.py        vienintelės durys į žinias (`find`)
    agent/knowledge_need.py        ko agentui reikia ir kur jo srities riba
    adapters/retrieval/            leksinis, *sparse*, embedding'ai, Qdrant

Iki tol čia buvo v1 RAG: `embeddings.py`, `vector_store.py`, `retriever.py`,
`hybrid_retriever.py`, `document_processor.py` ir FAISS indeksas. Kvietiklis buvo vienas —
LLM įrankis `search_knowledge`, kurio variklis niekada nekvietė (kalbėtojas be įrankių, M5), o
indeksas paskutinį kartą perstatytas 2026-06-12, kai dokumentai keisti rugsėjį. Visa tai
pakeitė E1–E4: leksinis rikiavimas su lietuviškomis šaknimis, Qdrant ir hibridas.
"""

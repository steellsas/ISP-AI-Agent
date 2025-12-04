# Architecture Documentation

High-level system architecture and design decisions.

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Component Details](#component-details)
- [Data Flow](#data-flow)
- [Design Decisions](#design-decisions)
- [Scalability Considerations](#scalability-considerations)

---

## Overview

The ISP Customer Service Chatbot follows a modular architecture with clear separation of concerns:

- **Interface Layer** — User-facing components (UI, CLI)
- **Core Engine** — LangGraph workflow orchestration
- **Services Layer** — LLM, RAG, MCP integrations
- **External Services** — MCP servers, databases

---

## System Architecture

### High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ISP Customer Service Bot                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                        Interface Layer                              │    │
│   │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │    │
│   │  │  Streamlit   │   │   CLI Chat   │   │   REST API   │            │    │
│   │  │   Demo UI    │   │  Interface   │   │   (Future)   │            │    │
│   │  └──────────────┘   └──────────────┘   └──────────────┘            │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                        Core Engine                                  │    │
│   │                                                                     │    │
│   │   ┌─────────────────────────────────────────────────────────┐      │    │
│   │   │              LangGraph Workflow Engine                   │      │    │
│   │   │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │      │    │
│   │   │  │ Greeting│→│ Problem │→│ Phone   │→│ Address │       │      │    │
│   │   │  │         │ │ Capture │ │ Lookup  │ │ Confirm │       │      │    │
│   │   │  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │      │    │
│   │   │       │           │           │           │             │      │    │
│   │   │       ▼           ▼           ▼           ▼             │      │    │
│   │   │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │      │    │
│   │   │  │Diagnos- │→│Trouble- │→│ Create  │→│ Closing │       │      │    │
│   │   │  │  tics   │ │ shoot   │ │ Ticket  │ │         │       │      │    │
│   │   │  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │      │    │
│   │   │                                                         │      │    │
│   │   │  ┌──────────────────────────────────────────────────┐  │      │    │
│   │   │  │           Pydantic State Model                    │  │      │    │
│   │   │  │  (conversation_id, messages, customer_id, ...)    │  │      │    │
│   │   │  └──────────────────────────────────────────────────┘  │      │    │
│   │   └─────────────────────────────────────────────────────────┘      │    │
│   │                              │                                      │    │
│   │          ┌───────────────────┼───────────────────┐                 │    │
│   │          ▼                   ▼                   ▼                 │    │
│   │   ┌────────────┐     ┌─────────────┐     ┌────────────┐           │    │
│   │   │    LLM     │     │     MCP     │     │    RAG     │           │    │
│   │   │  Service   │     │   Client    │     │  System    │           │    │
│   │   │ (LiteLLM)  │     │             │     │  (FAISS)   │           │    │
│   │   └─────┬──────┘     └──────┬──────┘     └─────┬──────┘           │    │
│   │         │                   │                   │                  │    │
│   └─────────│───────────────────│───────────────────│──────────────────┘    │
│             │                   │                   │                        │
│             ▼                   ▼                   ▼                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        External Services                             │   │
│   │                                                                      │   │
│   │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐             │   │
│   │  │              │   |  MCP Servers │   │  Knowledge   │             │   │
│   │  │   OpenAI /   │   │  ┌────────┐  │   │    Base      │             │   │
│   │  │   Gemini     │   │  │  CRM   │  │   │  (Markdown)  │             │   │
│   │  │              │   │  │Service │  │   │              │             │   │
│   │  └──────────────┘   │  ├────────┤  │   └──────┬───────┘             │   │
│   │                     │  │Network │  │          │                     │   │
│   │                     │  │  Diag  │  │          ▼                     │   │
│   │                     │  └────────┘  │   ┌──────────────┐             │   │
│   │                     └──────┬───────┘   │    FAISS     │             │   │
│   │                            │           │    Index     │             │   │
│   │                            ▼           └──────────────┘             │   │
│   │                     ┌──────────────┐                                │   │
│   │                     │   SQLite     │                                │   │
│   │                     │   Database   │                                │   │
│   │                     └──────────────┘                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### Interface Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| Streamlit UI | Streamlit 1.40+ | Demo interface with monitoring |
| CLI Chat | Python | Command-line testing |


### Core Engine

| Component | Technology | Purpose |
|-----------|------------|---------|
| Workflow Engine | LangGraph | State machine orchestration |
| State Model | Pydantic | Type-safe conversation state |
| Node Functions | Python | Individual workflow steps |
| Routers | Python | Conditional path selection |

### Services Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| LLM Service | LiteLLM | Multi-provider LLM access |
| MCP Client | MCP SDK | Tool execution protocol |
| RAG System | FAISS + Transformers | Knowledge retrieval |
| Config Loader | PyYAML | Configuration management |

### External Services

| Component | Technology | Purpose |
|-----------|------------|---------|
| LLM Providers | Claude/OpenAI/Gemini | Language understanding |
| CRM MCP Server | Python + SQLite | Customer data access |
| Network MCP Server | Python | Network diagnostics |
| Knowledge Base | Markdown + YAML | Troubleshooting content |

---

## Data Flow

### Request Flow

```
User Input
     │
     ▼
┌──────────────────┐
│   Streamlit UI   │  ◄─── Session state management
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  LangGraph App   │  ◄─── Compiled workflow graph
│  app.invoke()    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Entry Router    │  ◄─── Determines active node
└────────┬─────────┘
         │
         ▼
┌──────────────────┐      ┌──────────────┐
│   Active Node    │─────►│ LLM Service  │─────► OpenAI/Gemini
│  (e.g. problem   │      └──────────────┘
│   capture)       │      ┌──────────────┐
│                  │─────►│ MCP Client   │─────► CRM/Network MCP
│                  │      └──────────────┘
│                  │      ┌──────────────┐
│                  │─────►│ RAG System   │─────► FAISS Index
└────────┬─────────┘      └──────────────┘
         │
         ▼
┌──────────────────┐
│   Node Router    │  ◄─── Determines next node
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  State Update    │  ◄─── Merge node output with state
└────────┬─────────┘
         │
         ▼
    Response to UI
```

### State Update Flow

```
┌──────────────┐    invoke()    ┌──────────────┐
│  Current     │───────────────►│    Node      │
│   State      │                │  Function    │
└──────────────┘                └──────┬───────┘
                                       │
                                       │ returns {partial updates}
                                       ▼
                                ┌──────────────┐
                                │   Reducer    │
                                │  (merge)     │
                                └──────┬───────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │    New       │
                                │   State      │
                                └──────────────┘
```

---

## Design Decisions

### Why LangGraph?

| Alternative | Reason Not Chosen |
|-------------|-------------------|
| Raw LLM | No state management, complex routing |
| LangChain Agents | Less control over flow |


**LangGraph Benefits:**
- Built-in state persistence
- Conditional routing
- Checkpoint/restore
- Type-safe with Pydantic


### Why Hybrid RAG?

| Alternative | Reason Not Chosen |
|-------------|-------------------|
| Pure semantic | Misses exact technical terms |
| Pure keyword | Misses semantic meaning |
| LLM-based | Too slow, expensive |

**Hybrid Benefits:**
- Semantic understanding (70%)
- Technical term matching (30%)
- Fast retrieval
- Multilingual support

### Why LiteLLM?

| Alternative | Reason Not Chosen |
|-------------|-------------------|
| Direct API calls | Different APIs per provider |
| LangChain LLMs | Extra dependency |
| Single provider | Vendor lock-in |

**LiteLLM Benefits:**
- Unified interface
- Easy provider switching
- Cost tracking
- Fallback support

---

## Scalability Considerations

### Current Limitations (Demo)

| Component | Limitation | Production Solution |
|-----------|------------|---------------------|
| State | In-memory | Redis/PostgreSQL |
| RAG Index | File-based | Pinecone/Weaviate |
| MCP Servers | Single process | Container orchestration |
| Database | SQLite | PostgreSQL |

### Horizontal Scaling

```
                    ┌──────────────┐
                    │ Load Balancer│
                    └──────┬───────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Instance 1  │   │  Instance 2  │   │  Instance 3  │
│  (Chatbot)   │   │  (Chatbot)   │   │  (Chatbot)   │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Redis      │   │  PostgreSQL  │   │   Vector     │
│  (Sessions)  │   │  (CRM Data)  │   │   Store      │
└──────────────┘   └──────────────┘   └──────────────┘
```

### Performance Targets

| Metric | Demo | Production Target |
|--------|------|-------------------|
| Response latency | ~2s | <1s |
| Concurrent users | 1-5 | 100+ |
| RAG retrieval | ~50ms | <20ms |
| LLM calls/min | 10 | 1000 |

---

## Module Dependencies

```
┌─────────────────────────────────────────────────────────┐
│                    Application                           │
│  ┌─────────────────────────────────────────────────┐    │
│  │                 streamlit_ui/                    │    │
│  │                     app.py                       │    │
│  └─────────────────────────┬───────────────────────┘    │
│                            │                             │
│  ┌─────────────────────────▼───────────────────────┐    │
│  │                    graph/                        │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │    │
│  │  │ graph.py │  │ state.py │  │   nodes/*    │   │    │
│  │  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │    │
│  └───────│─────────────│───────────────│───────────┘    │
│          │             │               │                 │
│  ┌───────▼─────────────▼───────────────▼───────────┐    │
│  │                  services/                       │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │    │
│  │  │  llm.py  │  │ mcp_*.py │  │config_loader │   │    │
│  │  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │    │
│  └───────│─────────────│───────────────│───────────┘    │
│          │             │               │                 │
│  ┌───────▼─────────────│───────────────▼───────────┐    │
│  │                    rag/                          │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │    │
│  │  │retriever │  │embeddings│  │ vector_store │   │    │
│  │  └──────────┘  └──────────┘  └──────────────┘   │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │                   config/                        │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │    │
│  │  │*.yaml    │  │ locales/ │  │  prompts/    │   │    │
│  │  └──────────┘  └──────────┘  └──────────────┘   │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## Security Considerations

### Current State (Demo)

| Area | Status | Notes |
|------|--------|-------|
| Authentication | None | Demo only |
| Data encryption | None | SQLite local |
| API keys | Env vars | .env file |
| Input validation | Pydantic | Type checking |

### Production Requirements

- API key management (vault)
- Database encryption
- Input sanitization
- Rate limiting
- Audit logging
- GDPR compliance

---

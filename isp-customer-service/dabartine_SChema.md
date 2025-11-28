isp-customer-service/
├── chatbot_core/
│   ├── cli_chat.py                    # CLI testavimui
│   └── src/
│       ├── config/
│       │   ├── config.py
│       │   └── config.yaml
│       ├── graph/
│       │   ├── state.py               # Pydantic State schema
│       │   ├── graph.py               # LangGraph workflow definition
│       │   └── nodes/
│       │       ├── __init__.py
│       │       ├── greeting.py        # Statinis pasisveikinimas
│       │       ├── problem_capture.py # LLM loop - problema
│       │       ├── phone_lookup.py    # CRM lookup by phone
│       │       ├── address_confirmation.py  # LLM patvirtina adresą
│       │       ├── address_search.py  # LLM ištraukia adresą
│       │       ├── diagnostics.py     # Network checks
│       │       ├── inform_provider_issue.py # Informuoja apie gedimą
│       │       ├── troubleshooting.py # RAG + LLM step-by-step
│       │       ├── create_ticket.py   # Registruoja tiketą CRM
│       │       └── closing.py         # Atsisveikina
│       ├── services/
│       │   ├── llm.py                 # LiteLLM wrapper
│       │   ├── crm.py                 # CRM service wrapper
│       │   └── network.py             # Network diagnostics wrapper
│       └── rag/
│           ├── __init__.py
│           ├── embeddings.py          # Sentence transformers
│           ├── vector_store.py        # FAISS
│           ├── retriever.py           # RAG retriever
│           ├── scenario_loader.py     # YAML scenario loader
│           ├── knowledge_base/
│           │   ├── troubleshooting/
│           │   │   ├── *.md           # Markdown docs
│           │   │   └── scenarios/
│           │   │       ├── internet_no_connection.yaml
│           │   │       ├── internet_slow.yaml
│           │   │       └── tv_no_signal.yaml
│           │   ├── procedures/
│           │   └── faq/
│           ├── vector_store_data/     # FAISS index
│           └── scripts/
│               └── build_kb.py        # KB builder
│
├── crm_service/
│   └── src/
│       └── tools/
│           ├── customer_lookup.py
│           └── tickets.py
│
├── network_diagnostic_service/
│   └── src/
│       └── tools/
│           ├── connectivity_tests.py
│           ├── outage_checks.py
│           └── port_diagnostics.py
│
├── shared/
│   └── src/
│       └── utils/
│
└── database/
    └── isp_database.db               # SQLite (100 customers)


┌─────────────────────────────────────────────────────────────────────────────┐
│                        ISP CUSTOMER SERVICE CHATBOT                         │
│                            LangGraph Workflow                               │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────┐    ┌─────────────────┐    ┌──────────────┐    ┌───────────────────┐
│  START  │───▶│    greeting     │───▶│problem_capture│───▶│   phone_lookup    │
└─────────┘    └─────────────────┘    └──────────────┘    └───────────────────┘
                                              │                     │
                                              │ (loop iki           │
                                              │  aiški problema)    ▼
                                              │              ┌──────────────┐
                                              │              │ Customer     │
                                              │              │ found?       │
                                              │              └──────────────┘
                                              │                 │       │
                                              │            YES  │       │ NO
                                              │                 ▼       ▼
                                      ┌───────────────────┐  ┌─────────────────┐
                                      │address_confirmation│  │  address_search │
                                      └───────────────────┘  └─────────────────┘
                                              │                      │
                                              │ (confirmed)          │ (found)
                                              ▼                      ▼
                                      ┌───────────────────────────────┐
                                      │         diagnostics           │
                                      │  (check provider issues)      │
                                      └───────────────────────────────┘
                                              │
                              ┌───────────────┴───────────────┐
                              │                               │
                       provider_issue=True            provider_issue=False
                              │                               │
                              ▼                               ▼
                 ┌─────────────────────┐          ┌─────────────────────┐
                 │inform_provider_issue│          │   troubleshooting   │
                 │  (gedimas rajone)   │          │ (step-by-step LLM)  │
                 └─────────────────────┘          └─────────────────────┘
                              │                               │
                              │                   ┌───────────┴───────────┐
                              │                   │                       │
                              │           problem_resolved=True   needs_escalation=True
                              │                   │                       │
                              │                   ▼                       ▼
                              │           ┌─────────────────────────────────┐
                              │           │        create_ticket            │
                              │           │  (resolved=silent, escalate=msg)│
                              │           └─────────────────────────────────┘
                              │                           │
                              │                           ▼
                              │                   ┌───────────────┐
                              │                   │    closing    │
                              │                   │ (atsisveikina)│
                              │                   └───────────────┘
                              │                           │
                              ▼                           ▼
                           ┌─────────────────────────────────┐
                           │              END                │
                           └─────────────────────────────────┘


                           Node aprašymai
NodeTipasAprašymasgreetingStaticPasisveikinimas, pristato agentąproblem_captureLLM LoopKlausinėja iki aiški problema (type + description)phone_lookupDeterministicCRM lookup pagal telefono numerįaddress_confirmationLLMPatvirtina adresą su klientuaddress_searchLLM + CRMIštraukia adresą iš teksto, ieško CRMdiagnosticsDeterministicTikrina outages, port status, IP assignmentinform_provider_issueStaticInformuoja apie gedimą rajonetroubleshootingRAG + LLMStep-by-step instrukcijos telefonucreate_ticketDeterministicRegistruoja tiketą (silent arba su pranešimu)closingStaticAtsisveikina pagal rezultatą


class State(BaseModel):
    # Conversation
    conversation_id: str
    messages: Annotated[list[dict], operator.add]
    current_node: str
    
    # Customer
    phone_number: str
    customer_id: str | None
    customer_name: str | None
    customer_addresses: list[dict]
    confirmed_address: str | None
    
    # Problem
    problem_type: Literal["internet", "tv", "phone", "other"] | None
    problem_description: str | None
    
    # Workflow control
    address_confirmed: bool | None
    address_search_successful: bool | None
    
    # Diagnostics
    diagnostics_completed: bool
    provider_issue_detected: bool
    diagnostic_results: dict
    
    # Troubleshooting
    troubleshooting_scenario_id: str | None
    troubleshooting_current_step: int
    troubleshooting_completed_steps: list
    troubleshooting_needs_escalation: bool
    problem_resolved: bool
    
    # Ticket
    ticket_created: bool
    ticket_id: str | None
    ticket_type: str | None
    
    # End
    conversation_ended: bool
```

---

### Troubleshooting flow (detali)
```
┌─────────────────────────────────────────────────────────────────┐
│                    TROUBLESHOOTING NODE                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  First time?      │
                    └─────────┬─────────┘
                         YES  │  NO
                              │   │
              ┌───────────────┘   └───────────────┐
              ▼                                   ▼
    ┌─────────────────┐                 ┌─────────────────┐
    │ RAG: Select     │                 │ Get user        │
    │ scenario        │                 │ response        │
    └─────────────────┘                 └─────────────────┘
              │                                   │
              ▼                                   ▼
    ┌─────────────────┐                 ┌─────────────────┐
    │ Load YAML       │                 │ Check goodbye   │
    │ scenario        │                 │ phrases         │
    └─────────────────┘                 └─────────────────┘
              │                                   │
              ▼                                   ▼
    ┌─────────────────┐                 ┌─────────────────┐
    │ Format first    │                 │ LLM: Analyze    │
    │ step (LLM)      │                 │ with context    │
    └─────────────────┘                 └─────────────────┘
              │                                   │
              ▼                           ┌───────┴───────┐
    ┌─────────────────┐                   │               │
    │ Return step     │           needs_substep    branch_selected
    │ instruction     │                   │               │
    └─────────────────┘                   ▼               ▼
                                  ┌───────────┐   ┌───────────────┐
                                  │ Ask next  │   │ action=       │
                                  │ substep   │   │ resolved/     │
                                  └───────────┘   │ escalate/     │
                                                  │ next_step     │
                                                  └───────────────┘

                                                  Key features:

Phone-friendly: Vienas veiksmas per kartą
Context aware: LLM mato pokalbio istoriją
Goodbye detection: Atpažįsta atsisveikinimą lietuviškai
Flexible branching: YAML scenarios su multiple branches


Ticket logika
ScenarijusTicket TypeVeiksmaiProblema išspręstaresolvedTyliai sukuria tiketą, atsisveikinaReikia technikotechnician_visitInformuoja klientą, sukuria tiketą su žingsniaisScenario not foundescalationInformuoja, sukuria tiketą

Technologijos
KomponentasTechnologijaWorkflowLangGraphStatePydanticLLMLiteLLM (GPT-4o-mini)Embeddingssentence-transformers (multilingual)Vector StoreFAISSDatabaseSQLiteScenariosYAML



CLI naudojimas
bash# Testuoti su žinomu numeriu
cd chatbot_core
uv run python cli_chat.py --phone "+37060012345"

# Rebuild RAG knowledge base
uv run python src/rag/scripts/build_kb.py
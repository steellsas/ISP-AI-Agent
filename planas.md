📅 DEVELOPMENT PHASES
PHASE 0: Project Setup & Planning (1 day)
Goal: Establish project structure and development environment
Tasks:

Project Structure Creation

Create directory structure
Initialize UV project
Setup .gitignore
Create requirements/dependencies file


Documentation Setup

README.md with project overview
ARCHITECTURE.md with system design
CHANGELOG.md for tracking changes
docs/ folder for detailed documentation


Development Environment

Setup virtual environment with UV
Install core dependencies (LangGraph, LangChain, etc.)
Configure LangSmith API keys
Setup code formatter (black, ruff)


Git Repository

Initialize git
Create initial commit
Setup .env.example for configuration



Deliverables:

✅ Working project structure
✅ Dependencies installed
✅ Development environment ready
✅ Documentation skeleton


PHASE 1: Core Architecture (3-4 days)
Goal: Build foundational LangGraph state machine and config system
Task 1.1: State Schema Definition (0.5 day)

Define ConversationState TypedDict
Create state validation utilities
Document all state fields
Create state helper functions

Task 1.2: Config System (1 day)

Create config/ directory structure
Design problems.yaml schema
Design prompts_lt.yaml schema
Design tools_mapping.yaml schema
Create config loader utility
Add config validation

Task 1.3: Basic LangGraph Structure (1.5 days)

Create base graph with 8 nodes:

greeting_node
customer_identification_node
check_history_node (placeholder)
problem_identification_node
diagnostics_node
troubleshooting_node
ticket_registration_node
resolution_node


Define conditional edges
Setup state transitions
Add basic logging

Task 1.4: Testing Framework (1 day)

Setup pytest
Create test fixtures
Write unit tests for state transitions
Create mock state examples

Deliverables:

✅ Config system working
✅ LangGraph skeleton with all nodes
✅ Basic tests passing
✅ State management working


PHASE 2: Database & CRM System (3 days)
Goal: Create mock CRM database and data models
Task 2.1: Database Schema Design (0.5 day)

Design SQLite schema:

customers table
addresses table
service_plans table
tickets table
customer_history table
conversations table
customer_memory table


Create migration scripts
Document database schema

Task 2.2: Database Implementation (1 day)

Create database connection manager
Implement ORM models (SQLAlchemy or similar)
Create CRUD operations
Add database utilities

Task 2.3: Mock Data Generation (1 day)

Create mock customer data (50-100 customers)
Generate realistic Lithuanian addresses
Create sample service plans
Generate historical tickets
Create seed data script

Task 2.4: Data Access Layer (0.5 day)

Create repository pattern classes
Implement query functions
Add caching if needed
Write database tests

Deliverables:

✅ SQLite database with schema
✅ Mock data populated
✅ CRUD operations working
✅ Database tests passing


PHASE 3: MCP Servers (4-5 days)
Goal: Create three MCP servers with auto-discovery
Task 3.1: MCP Server Framework (1 day)

Setup MCP server project structure
Create base server template
Implement tool registration system
Setup server discovery mechanism
Create server testing utilities

Task 3.2: CRM MCP Server (1.5 days)
Tools to implement:

lookup_customer_by_phone(phone: str)
lookup_customer_by_address(address: dict)
lookup_customer_by_name(name: str)
fuzzy_address_search(city, street, house, apt)
fuzzy_street_match(city: str, street: str)
check_house_numbers(street: str, house: str)
get_customer_history(customer_id: str)
get_service_plan(customer_id: str)
get_customer_memory(customer_id: str)
save_customer_memory(customer_id: str, memory: dict)

Task 3.3: Network Diagnostics MCP Server (1.5 days)
Tools to implement (all mock initially):

check_switch_port(customer_id: str)
check_ip_assignment(customer_id: str)
check_mac_address(customer_id: str)
measure_bandwidth(customer_id: str)
check_area_issues(address: str)
check_payment_status(customer_id: str)
check_service_status(customer_id: str, service_type: str)
check_packet_loss(customer_id: str)
check_signal_quality(customer_id: str)

Task 3.4: Ticket System MCP Server (1 day)
Tools to implement:

create_ticket(type, customer_id, summary, details)
update_ticket(ticket_id, status, notes)
get_ticket_history(customer_id: str)
schedule_technician(ticket_id, address, time_slot)
send_sms_notification(phone: str, message: str)
close_ticket(ticket_id, resolution_summary)

Task 3.5: MCP Integration Testing (0.5 day)

Test all tools individually
Test server discovery
Create integration tests
Document all tools

Deliverables:

✅ 3 working MCP servers
✅ ~25 tools implemented
✅ Auto-discovery working
✅ All tools tested


PHASE 4: RAG System (3-4 days)
Goal: Implement Agentic RAG with troubleshooting knowledge
Task 4.1: RAG Architecture (0.5 day)

Design document structure
Choose embedding model (sentence-transformers)
Setup FAISS vector store
Create document loader

Task 4.2: Knowledge Base Documents (2 days)
Create structured markdown docs:

internet_no_connection.md (detailed)
internet_slow.md
internet_unstable.md
tv_no_signal.md
tv_poor_quality.md
phone_no_service.md (for future)
general_troubleshooting.md

Each doc should have:

PROVIDER_CHECKS section
CUSTOMER_TROUBLESHOOTING section
DECISION_LOGIC section
SUCCESS_INDICATORS
FAILURE_INDICATORS

Task 4.3: RAG Implementation (1 day)

Implement document chunking strategy
Create embeddings
Build FAISS index
Implement semantic search
Create RAG query utilities

Task 4.4: RAG Integration (0.5 day)

Integrate with LangGraph nodes
Add RAG tool to MCP or direct integration
Test retrieval quality
Add relevance scoring

Task 4.5: RAG Testing (0.5 day)

Test document retrieval accuracy
Test different query types
Evaluate relevance scores
Create RAG test suite

Deliverables:

✅ 7+ knowledge base documents
✅ FAISS vector store working
✅ Semantic search functional
✅ RAG tests passing


PHASE 5: Node Implementation (5-6 days)
Goal: Implement logic for all LangGraph nodes
Task 5.1: Greeting Node (0.5 day)

Welcome message generation
Caller ID check logic
Language detection
Initial state setup

Task 5.2: Customer Identification Node (2 days)
Complex node with:

Phone lookup flow
Address fuzzy matching (multiple retries)
Name search fallback
Retry counters and limits
Timeout handling (5 min)
Confirmation loops
Proxy call detection
Escalation to ticket creation
Logging all attempts

Task 5.3: Customer History Check Node (0.5 day)

Fetch customer ticket history
Detect recurring issues
Load previous solutions
Add context to state

Task 5.4: Problem Identification Node (0.5 day)

Use config to list problem types
Parse user input
Categorize problem
Ask clarifying questions if needed

Task 5.5: Diagnostics Node (1.5 days)

Load problem config
Query RAG for provider checks
Execute provider-side tools dynamically
Interpret results
Decision: provider issue vs customer issue
Log all diagnostic results

Task 5.6: Troubleshooting Node (1.5 days)
Most complex node:

Query RAG for troubleshooting steps
Interactive step-by-step execution
Parse customer responses
Loop detection (max iterations)
Customer opt-out handling
Success detection
Collect attempted actions

Task 5.7: Ticket Registration Node (0.5 day)

Create ticket based on outcome type:

Network issue ticket
Resolved ticket
Technician visit ticket


Save to database via MCP
Generate ticket summary

Task 5.8: Resolution Node (0.5 day)

Final message generation
Save conversation to CRM
Log session summary
Goodbye message

Deliverables:

✅ All 8 nodes fully implemented
✅ Conditional edges working
✅ Flow tested end-to-end
✅ State transitions correct


PHASE 6: UI Development (3 days)
Goal: Create Streamlit interface
Task 6.1: Basic Chat Interface (1 day)

Streamlit chat UI
Message display (user + assistant)
Input field
Session management
Lithuanian language UI

Task 6.2: Settings Panel (1 day)

LLM selection dropdown (Claude, GPT-4, etc.)
Temperature slider
Top-p slider
Max tokens input
Personality selector (formal/friendly)
Language toggle (LT/EN)

Task 6.3: Dashboard & Monitoring (1 day)

Token usage display
Cost calculation
Session statistics
Conversation history viewer
Download conversation option

Deliverables:

✅ Working Streamlit UI
✅ All settings functional
✅ Dashboard with metrics
✅ Good UX with Lithuanian language


PHASE 7: Multi-Model Support (2 days)
Goal: Support multiple LLM providers
Task 7.1: Model Router (1 day)

Create LLM factory
Support Anthropic (Claude)
Support OpenAI (GPT-4)
Support Google (Gemini)
Unified interface
Model-specific prompt adjustments

Task 7.2: Token Tracking (0.5 day)

Track tokens per model
Calculate costs per model
Display in UI
Log to database

Task 7.3: Model Testing (0.5 day)

Test all models
Compare outputs
Document differences
Create model selection guide

Deliverables:

✅ 3 LLM providers working
✅ Token tracking accurate
✅ Cost calculation correct
✅ Model switching seamless


PHASE 8: Memory & Learning (3 days)
Goal: Implement memory systems
Task 8.1: Short-term Memory (0.5 day)

Session conversation storage
Message history in state
Context window management
Save to database after session

Task 8.2: Long-term Memory (1 day)

Customer memory schema
Store preferences
Store communication style
Store device info
Load at session start
Update during conversation

Task 8.3: Learning Engine (1.5 days)

Analyze successful resolutions
Extract patterns
Update RAG documents
Mark ineffective steps
Success rate tracking
Pattern detection algorithm

Deliverables:

✅ Conversation history saved
✅ Customer memory working
✅ Learning from patterns
✅ RAG auto-updates (basic)


PHASE 9: Observability & Monitoring (2 days)
Goal: Implement LangSmith and logging
Task 9.1: LangSmith Integration (1 day)

Configure LangSmith
Add tracing to all nodes
Track tool calls
Monitor performance
Debug UI familiarization

Task 9.2: Logging System (0.5 day)

Structured logging
Log levels configuration
Session logs
Error tracking
Performance metrics

Task 9.3: Analytics (0.5 day)

Success rate calculation
Average resolution time
Escalation rate
Most common problems
Tool usage statistics

Deliverables:

✅ LangSmith tracking working
✅ Comprehensive logging
✅ Analytics dashboard
✅ Debugging tools ready


PHASE 10: Testing & Quality (3-4 days)
Goal: Comprehensive testing and bug fixes
Task 10.1: Unit Tests (1 day)

Test all nodes individually
Test state transitions
Test config loading
Test database operations
Achieve >80% code coverage

Task 10.2: Integration Tests (1 day)

Test full flow scenarios:

Successful resolution
Provider issue escalation
Customer stops troubleshooting
Customer not found
Recurring issue handling


Test edge cases
Test error handling

Task 10.3: End-to-End Tests (1 day)

Test with real conversations
Test all problem types
Test multi-language
Test different LLMs
Performance testing

Task 10.4: Bug Fixes & Polish (1 day)

Fix discovered bugs
Improve error messages
Optimize performance
Refactor code
Update documentation

Deliverables:

✅ All tests passing
✅ >80% code coverage
✅ No critical bugs
✅ Code quality high


PHASE 11: Feedback & Plugin System (2-3 days)
Goal: User feedback and tool management
Task 11.1: Feedback System (1 day)

Add rating UI (1-5 stars)
Collect feedback comments
Store in database
Display feedback history
Basic analytics

Task 11.2: Plugin Manager (1.5 days)

UI to enable/disable tools
Tool dependency management
Dynamic tool loading
Plugin configuration
Test plugin system

Task 11.3: Feedback Learning (0.5 day)

Analyze feedback patterns
Adjust RAG based on feedback
Improve low-rated responses
Track improvement metrics

Deliverables:

✅ Feedback collection working
✅ Plugin manager functional
✅ Tool enable/disable working
✅ Feedback influences system


PHASE 12: Documentation & Deployment Prep (2 days)
Goal: Complete documentation and prepare for deployment
Task 12.1: User Documentation (0.5 day)

User guide (Lithuanian)
FAQ section
Troubleshooting guide
Video tutorial (optional)

Task 12.2: Developer Documentation (0.5 day)

Code documentation
API documentation
Architecture diagrams
Setup guide
Contributing guide

Task 12.3: Configuration Guide (0.5 day)

How to add new problem types
How to add new tools
How to add RAG documents
How to modify prompts
How to add new languages

Task 12.4: Deployment Preparation (0.5 day)

Create Docker configuration
Environment variables documentation
Deployment checklist
Security considerations
Backup procedures

Deliverables:

✅ Complete documentation
✅ Deployment ready
✅ Configuration guide clear
✅ Handover materials ready


📊 TIMELINE SUMMARY
PhaseDurationCumulativePhase 0: Setup1 day1 dayPhase 1: Core Architecture4 days5 daysPhase 2: Database & CRM3 days8 daysPhase 3: MCP Servers5 days13 daysPhase 4: RAG System4 days17 daysPhase 5: Node Implementation6 days23 daysPhase 6: UI Development3 days26 daysPhase 7: Multi-Model2 days28 daysPhase 8: Memory & Learning3 days31 daysPhase 9: Observability2 days33 daysPhase 10: Testing4 days37 daysPhase 11: Feedback System3 days40 daysPhase 12: Documentation2 days42 days
Total Estimated Time: ~6-8 weeks (depending on complexity and issues encountered)

🎯 MILESTONES
Milestone 1: MVP (End of Phase 5) - ~3 weeks

Basic flow working
CRM + MCP + RAG integrated
Lithuanian language
Mock data
Can handle internet issues

Milestone 2: Feature Complete (End of Phase 9) - ~5 weeks

Multi-model support
Memory system
Observability
All problem types
Production-ready core

Milestone 3: Production Ready (End of Phase 12) - ~6-8 weeks

Fully tested
Feedback system
Complete documentation
Ready for deployment


🔄 ITERATIVE APPROACH
Each phase should follow:

Plan - Review tasks, clarify requirements
Implement - Write code incrementally
Test - Unit + integration tests
Review - Code review, refactor
Document - Update docs
Demo - Show working feature


🚀 NEXT STEPS
When ready to start, we'll begin with Phase 0:

Create project structure
Setup development environment
Initialize git repository
Create documentation skeleton

Then proceed incrementally through each phase.

❓ Questions before we start?

Does this timeline seem reasonable?
Any phases you want to prioritize differently?
Should we adjust scope of MVP?
Any additional features to plan for?
Ready to start with Phase 0? 🎯

-------------------------------------------------------------

📅 REVISED DEVELOPMENT PHASES
PHASE 0: Project Setup (1 day)
Tasks:

Create monorepo structure
Initialize 4 sub-projects with UV:

chatbot-core
crm-service
network-diagnostic-service
shared


Setup workspace in root pyproject.toml
Create .env.example
Setup .gitignore
Initialize git repository
Create basic README files

Deliverables:

✅ Monorepo structure ready
✅ UV workspace configured
✅ Git initialized


PHASE 1: Database Setup (2 days)
Task 1.1: Schema Design & Creation (1 day)

Create database/schema/crm_schema.sql
Create database/schema/network_schema.sql
Create database/migrations/001_initial_schema.sql
Create scripts/setup_db.py to initialize DB
Test schema creation

Task 1.2: Mock Data Generation (1 day)

Create seed scripts in database/seeds/
Generate 50-100 mock customers (Lithuanian names, addresses)
Generate mock equipment data
Generate mock network infrastructure (switches, ports)
Generate mock historical tickets
Create scripts/seed_data.py
Test data loading

Deliverables:

✅ SQLite database with schemas
✅ Mock data populated
✅ Setup scripts working


PHASE 2: Shared Package (1 day)
Tasks:

Create database connection manager in shared/src/database/
Create shared types in shared/src/types/
Create logger utility
Create config loader
Test shared package imports

Deliverables:

✅ Shared utilities working
✅ Database connection tested
✅ Importable from other packages


PHASE 3: CRM Service MCP Server (3 days)
Task 3.1: MCP Server Setup (0.5 day)

Create MCP server in crm-service/src/mcp_server/server.py
Setup tool registration
Test basic server startup

Task 3.2: Customer Lookup Tools (1 day)
Implement MCP tools:

lookup_customer_by_phone(phone: str)
lookup_customer_by_address(city, street, house, apt)
lookup_customer_by_name(first_name, last_name)
get_customer_full_profile(customer_id: str)

Task 3.3: Fuzzy Search Tools (1 day)
Implement MCP tools:

fuzzy_city_search(city: str, threshold: float = 0.5)
fuzzy_street_search(city: str, street: str, threshold: float = 0.5)
fuzzy_house_search(street: str, house: str)
fuzzy_apartment_search(house: str, apartment: str)

Task 3.4: History & Equipment Tools (0.5 day)
Implement MCP tools:

get_customer_history(customer_id: str, limit: int = 10)
get_customer_equipment(customer_id: str)
get_customer_memory(customer_id: str)
save_customer_memory(customer_id: str, key: str, value: str)

Task 3.5: Ticket Tools (1 day)
Implement MCP tools:

create_ticket(customer_id, type, problem_type, summary, details)
update_ticket(ticket_id, status, notes)
get_ticket_history(customer_id: str)
close_ticket(ticket_id, resolution_summary)

Deliverables:

✅ CRM MCP Server running
✅ ~15 tools implemented
✅ All tools tested
✅ Documentation written


PHASE 4: Network Diagnostic Service MCP Server (3 days)
Task 4.1: MCP Server Setup (0.5 day)

Create MCP server structure
Setup tool registration

Task 4.2: Mock Diagnostic Logic (1 day)

Create diagnostics/mock_responses.py
Mock switch port status
Mock IP assignment logic
Mock bandwidth measurements
Mock area outage detection

Task 4.3: Network Check Tools (1.5 days)
Implement MCP tools:

check_switch_port(customer_id: str)
check_ip_assignment(customer_id: str)
check_mac_address(customer_id: str)
measure_bandwidth(customer_id: str)
check_area_issues(city: str, street: str)
check_payment_status(customer_id: str) (queries CRM)
check_signal_quality(customer_id: str)
check_packet_loss(customer_id: str)

Deliverables:

✅ Network MCP Server running
✅ ~8-10 tools implemented
✅ Mock diagnostics working
✅ All tools tested


PHASE 5: Chatbot Core - Config System (2 days)
Task 5.1: Config Files (1 day)
Create in chatbot-core/src/config/:
problems.yaml:
yamlproblems:
  internet_down:
    name: "Internetas neveikia"
    category: "internet"
    provider_checks:
      - check_switch_port
      - check_ip_assignment
      - check_area_issues
    customer_checks:
      - router_power
      - cable_connection
      - device_restart
    rag_queries:
      - "internet not working troubleshooting"
  
  internet_slow:
    name: "Lėtas internetas"
    category: "internet"
    provider_checks:
      - measure_bandwidth
      - check_packet_loss
    customer_checks:
      - wifi_interference
      - multiple_devices
    rag_queries:
      - "slow internet causes"
  
  # Add more...
prompts_lt.yaml:
yamlgreeting:
  initial: "Labas! Aš virtualus asistentas. Kaip galiu padėti?"
  with_caller_id: "Labas, {name}! Matau skambinate iš adreso {address}. Kaip galiu padėti?"

customer_identification:
  ask_address: "Prašau nurodyti savo adresą: miestą, gatvę, namo numerį."
  confirm_address: "Ar tai jūsų adresas: {address}?"
  # ... more prompts
Task 5.2: Config Loader (0.5 day)

Create config loader utility
Validate config on load
Test config access

Task 5.3: State Schema (0.5 day)

Define ConversationState in graph/state.py
Create state helpers
Document all fields

Deliverables:

✅ Config system working
✅ YAML files created
✅ State schema defined


PHASE 6: Chatbot Core - LangGraph Structure (3 days)
Task 6.1: MCP Client Setup (0.5 day)

Create MCP client in mcp_client/client.py
Connect to CRM server
Connect to Network server
Test tool discovery

Task 6.2: Basic Graph Structure (1 day)

Create graph in graph/graph.py
Define all 8 nodes (empty implementations)
Define conditional edges
Test graph compilation

Task 6.3: Simple Nodes Implementation (1 day)
Implement simple nodes:

greeting_node - basic welcome
problem_identification_node - use config
resolution_node - goodbye message

Task 6.4: Testing (0.5 day)

Create test fixtures
Test state transitions
Test conditional edges

Deliverables:

✅ LangGraph structure complete
✅ MCP clients connected
✅ Basic nodes working
✅ Tests passing


PHASE 7: RAG System (3 days)
Task 7.1: Knowledge Base Documents (1.5 days)
Create in chatbot-core/src/rag/knowledge_base/:

internet_no_connection.md (very detailed)
internet_slow.md
internet_unstable.md
tv_no_signal.md

Each with structured sections:

PROVIDER_CHECKS
CUSTOMER_TROUBLESHOOTING
DECISION_LOGIC
SUCCESS/FAILURE_INDICATORS

Task 7.2: RAG Implementation (1 day)

Choose embedding model (sentence-transformers)
Create FAISS vector store
Implement document chunking
Create semantic search

Task 7.3: RAG Integration (0.5 day)

Integrate with diagnostics node
Integrate with troubleshooting node
Test retrieval quality

Deliverables:

✅ 4+ knowledge documents
✅ FAISS working
✅ Semantic search tested
✅ RAG integrated with nodes


PHASE 8: Complex Nodes Implementation (5 days)
Task 8.1: Customer Identification Node (2 days)
Most complex node!

Phone lookup flow
Address fuzzy matching with retries
Name fallback search
Confirmation loops
Timeout handling (5 min)
Retry counters per method
Escalation to ticket
Full logging

Task 8.2: Check History Node (0.5 day)

Query customer history via CRM MCP
Detect recurring issues
Load previous solutions
Add to state

Task 8.3: Diagnostics Node (1 day)

Load problem config
Query RAG for checks
Call provider tools dynamically
Interpret results
Decision: provider vs customer issue

Task 8.4: Troubleshooting Node (1.5 days)

Query RAG for steps
Interactive step execution
Parse customer responses
Loop detection
Success/failure detection
Collect attempted actions

Task 8.5: Ticket Registration Node (0.5 day)

Create tickets via CRM MCP
Different ticket types
Generate summaries

Deliverables:

✅ All nodes implemented
✅ Full flow working
✅ Edge cases handled
✅ Comprehensive tests


PHASE 9: UI Development (3 days)
Task 9.1: Basic Chat Interface (1 day)

Streamlit chat UI
Message display
Input field
Session management
Lithuanian UI

Task 9.2: Settings Panel (1 day)

LLM selection (Claude, GPT-4)
Temperature slider
Top-p slider
Personality selector
Language toggle

Task 9.3: Monitoring Dashboard (1 day)

Token usage display
Session stats
Conversation history
Download option

Deliverables:

✅ Working Streamlit UI
✅ Settings functional
✅ Dashboard with metrics


PHASE 10: Multi-Model Support (2 days)
Task 10.1: Model Router (1 day)

LLM factory
Support Claude (Anthropic)
Support GPT-4 (OpenAI)
Unified interface

Task 10.2: Token Tracking (1 day)

Track tokens per model
Calculate costs
Display in UI
Log to database

Deliverables:

✅ 2+ LLM providers working
✅ Token tracking accurate
✅ Model switching seamless


PHASE 11: Memory & Learning (3 days)
Task 11.1: Conversation Storage (1 day)

Save conversations to CRM
Session logs
Summary generation

Task 11.2: Customer Memory (1 day)

Load/save preferences
Communication style
Device info

Task 11.3: Pattern Learning (1 day)

Analyze successful resolutions
Extract patterns
Update RAG (basic)

Deliverables:

✅ Memory system working
✅ Learning from patterns
✅ RAG updates


PHASE 12: Observability (2 days)
Task 12.1: LangSmith Integration (1 day)

Configure LangSmith
Add tracing
Monitor performance

Task 12.2: Logging & Analytics (1 day)

Structured logging
Session analytics
Performance metrics

Deliverables:

✅ LangSmith working
✅ Comprehensive logging
✅ Analytics dashboard


PHASE 13: Testing & Polish (3 days)
Task 13.1: Unit Tests (1 day)

Test all nodes
Test MCP tools


80% coverage



Task 13.2: Integration Tests (1 day)

Full flow scenarios
Edge cases
Error handling

Task 13.3: Bug Fixes (1 day)

Fix bugs
Polish UX
Optimize performance

Deliverables:

✅ All tests passing
✅ No critical bugs
✅ Production ready


PHASE 14: Documentation (2 days)
Task 14.1: User Documentation (1 day)

User guide (Lithuanian)
Setup instructions
Configuration guide

Task 14.2: Developer Documentation (1 day)

Architecture docs
API documentation
How to extend guide

Deliverables:

✅ Complete documentation
✅ Ready for handover


📊 REVISED TIMELINE SUMMARY
PhaseDurationCumulativePhase 0: Setup1 day1 dayPhase 1: Database2 days3 daysPhase 2: Shared1 day4 daysPhase 3: CRM Service3 days7 daysPhase 4: Network Service3 days10 daysPhase 5: Config System2 days12 daysPhase 6: Graph Structure3 days15 daysPhase 7: RAG System3 days18 daysPhase 8: Complex Nodes5 days23 daysPhase 9: UI3 days26 daysPhase 10: Multi-Model2 days28 daysPhase 11: Memory3 days31 daysPhase 12: Observability2 days33 daysPhase 13: Testing3 days36 daysPhase 14: Documentation2 days38 days
Total: ~6-7 weeks

🎯 MILESTONES
Milestone 1: Infrastructure Ready (End Phase 4) - ~2 weeks

Database working
Both MCP servers running
All tools implemented
Mock data populated

Milestone 2: MVP (End Phase 8) - ~4 weeks

Full chatbot flow working
RAG integrated
Lithuanian language
Can handle internet issues end-to-end

Milestone 3: Production Ready (End Phase 14) - ~6-7 weeks

Multi-model support
Memory & learning
Full testing
Complete documentation

++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

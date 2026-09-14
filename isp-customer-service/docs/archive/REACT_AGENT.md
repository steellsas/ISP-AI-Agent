# ReAct Agent Documentation

Complete reference for the ReAct (Reasoning + Acting) agent architecture.

---

## Overview

The bot uses a **ReAct (Reasoning + Acting)** pattern - an autonomous AI agent that thinks through problems step-by-step and decides which tools to use.

Unlike traditional state machines or workflow engines, the ReAct agent:
- Makes autonomous decisions based on conversation context
- Selects tools dynamically rather than following a fixed path
- Provides transparent reasoning for each action
- Self-corrects when actions don't produce expected results

**File Location:** `src/agent/react_agent.py`

---

## How ReAct Works

### The Core Loop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ReAct Agent Loop                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                         ┌─────────────────┐                                 │
│                         │  User Message   │                                 │
│                         └────────┬────────┘                                 │
│                                  │                                          │
│                                  ▼                                          │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │                                                                 │     │
│    │  ┌───────────┐    ┌───────────┐    ┌─────────────┐             │     │
│    │  │  THOUGHT  │───▶│  ACTION   │───▶│ OBSERVATION │────┐        │     │
│    │  │           │    │           │    │             │    │        │     │
│    │  │ Reasoning │    │ Tool call │    │ Tool result │    │        │     │
│    │  │ about     │    │ or        │    │             │    │        │     │
│    │  │ next step │    │ response  │    │             │    │        │     │
│    │  └───────────┘    └───────────┘    └─────────────┘    │        │     │
│    │        ▲                                              │        │     │
│    │        └──────────────────────────────────────────────┘        │     │
│    │                         (loop)                                  │     │
│    │                                                                 │     │
│    └─────────────────────────────────────────────────────────────────┘     │
│                                  │                                          │
│                                  ▼                                          │
│                         ┌─────────────────┐                                 │
│                         │    Response     │                                 │
│                         │   to Customer   │                                 │
│                         └─────────────────┘                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step-by-Step Process

| Step | Name | Description |
|------|------|-------------|
| 1 | **Thought** | Agent analyzes situation and decides what to do next |
| 2 | **Action** | Agent selects a tool or decides to respond to customer |
| 3 | **Observation** | Agent receives tool result and incorporates into context |
| 4 | **Loop** | Repeat until ready to respond or conversation ends |

---

## Agent Response Format

The agent always responds in this structured format:

```
Thought: <reasoning about what to do next>
Action: <tool_name or "respond" or "finish">
Action Input: <JSON parameters>
```

### Examples

**Using a Tool:**
```
Thought: Customer called about internet not working. I need to find their account first.
Action: find_customer
Action Input: {"phone": "+37060012345"}
```

**Responding to Customer:**
```
Thought: I found the customer account. I should confirm their address before diagnostics.
Action: respond
Action Input: {"message": "Radau jūsų paskyrą. Ar skambinate dėl adreso Vilniaus g. 15?"}
```

**Ending Conversation:**
```
Thought: Problem is resolved, customer confirmed everything works.
Action: finish
Action Input: {"summary": "Internet issue resolved after router restart"}
```

---

## Agent Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ReactAgent Class                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                         Components                                   │  │
│   │                                                                      │  │
│   │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │  │
│   │   │    State     │  │    Config    │  │   Prompts    │             │  │
│   │   │  (AgentState)│  │ (AgentConfig)│  │   (YAML)     │             │  │
│   │   │              │  │              │  │              │             │  │
│   │   │ • messages   │  │ • model      │  │ • system     │             │  │
│   │   │ • customer   │  │ • temperature│  │ • tools desc │             │  │
│   │   │ • context    │  │ • max_turns  │  │ • language   │             │  │
│   │   └──────────────┘  └──────────────┘  └──────────────┘             │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                          Main Loop                                   │  │
│   │                                                                      │  │
│   │   run_until_response(user_input)                                    │  │
│   │         │                                                            │  │
│   │         ▼                                                            │  │
│   │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │  │
│   │   │    step()   │───▶│   _parse    │───▶│  _execute   │             │  │
│   │   │             │    │  _response  │    │   _action   │             │  │
│   │   │ LLM call    │    │             │    │             │             │  │
│   │   │ with tools  │    │ Extract:    │    │ • tool call │             │  │
│   │   │ description │    │ • thought   │    │ • respond   │             │  │
│   │   │             │    │ • action    │    │ • finish    │             │  │
│   │   │             │    │ • input     │    │             │             │  │
│   │   └─────────────┘    └─────────────┘    └─────────────┘             │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent State

The agent maintains state throughout the conversation.

**File:** `src/agent/state.py`

### State Fields

| Field | Type | Description |
|-------|------|-------------|
| `caller_phone` | str | Phone number of caller |
| `customer_id` | str | CRM customer ID (after lookup) |
| `customer_name` | str | Customer name |
| `customer_address` | str | Service address |
| `address_confirmed` | bool | Whether address was confirmed |
| `problem_type` | str | Classified problem type |
| `problem_description` | str | Problem details |
| `messages` | list | Conversation history |
| `is_complete` | bool | Whether conversation ended |
| `ticket_id` | str | Created ticket ID (if any) |

### State Methods

```python
# Set customer info after lookup
state.set_customer_info(
    customer_id="CUST001",
    name="Jonas Jonaitis",
    address="Vilniaus g. 15"
)

# Confirm address
state.confirm_address(caller_name="Jonas")

# Convert to dict for inspection
data = state.to_dict()
```

---

## Agent Configuration

**File:** `src/agent/config.py`

### Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `model` | gpt-4o-mini | LLM model to use |
| `temperature` | 0.3 | Response creativity (0-1) |
| `max_tokens` | 1000 | Maximum response length |
| `max_turns` | 20 | Maximum conversation turns |
| `language` | lt | Response language (lt/en) |

### Updating Configuration

```python
from agent.config import update_config, get_config

# Update settings
update_config(
    model="gpt-4o",
    temperature=0.5,
    language="en"
)

# Get current config
config = get_config()
print(config.model)  # "gpt-4o"
```

---

## Decision Making

### How Agent Decides What To Do

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Agent Decision Logic                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Conversation Start                                                        │
│         │                                                                   │
│         ▼                                                                   │
│   ┌─────────────────┐                                                       │
│   │ Customer known? │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│       NO   │   YES                                                          │
│            │                                                                │
│   ┌────────┴────────┐                                                       │
│   ▼                 ▼                                                       │
│ find_customer    Address confirmed?                                         │
│                     │                                                       │
│                NO   │   YES                                                 │
│                     │                                                       │
│            ┌────────┴────────┐                                              │
│            ▼                 ▼                                              │
│         respond           check_outages                                     │
│        (ask address)      check_network_status                              │
│                              │                                              │
│                              ▼                                              │
│                     ┌─────────────────┐                                     │
│                     │ Issues found?   │                                     │
│                     └────────┬────────┘                                     │
│                              │                                              │
│                    YES       │        NO                                    │
│                              │                                              │
│                     ┌────────┴────────┐                                     │
│                     ▼                 ▼                                     │
│               create_ticket      search_knowledge                           │
│              (if critical)       (troubleshooting)                          │
│                                       │                                     │
│                                       ▼                                     │
│                              Guide customer through                         │
│                              troubleshooting steps                          │
│                                       │                                     │
│                              ┌────────┴────────┐                            │
│                              ▼                 ▼                            │
│                          Resolved?        Not resolved?                     │
│                              │                 │                            │
│                              ▼                 ▼                            │
│                           finish          create_ticket                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## System Prompt

The system prompt instructs the agent how to behave.

**File:** `src/agent/prompts/system_prompt.txt`

### Key Instructions

| Instruction | Purpose |
|-------------|---------|
| Language requirement | Respond in informal Lithuanian ("tu" form) |
| Process flow | 1) Identify → 2) Confirm address → 3) Diagnose → 4) Troubleshoot → 5) Escalate |
| Tool usage | When to use each tool |
| Response format | Thought/Action/Action Input structure |
| Escalation rules | When to create ticket vs continue troubleshooting |

### Prompt Structure

```
You are an ISP customer support agent...

## Your Goal
Help customers resolve technical issues...

## Process
1. IDENTIFY customer (find_customer)
2. CONFIRM address
3. CHECK for outages (check_outages)
4. CHECK network status (check_network_status)
5. SEARCH knowledge base (search_knowledge)
6. GUIDE troubleshooting
7. ESCALATE if needed (create_ticket)

## Available Tools
- find_customer: ...
- check_network_status: ...
- check_outages: ...
- search_knowledge: ...
- create_ticket: ...

## Response Format
Thought: <reasoning>
Action: <tool_name>
Action Input: <json>

## Language
Respond in INFORMAL Lithuanian...
```

---

## Conversation Example

### Full Conversation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ CUSTOMER: Labas, neveikia internetas                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ AGENT THINKING:                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ Thought: Customer reports internet not working. Need to find account.   ││
│ │ Action: find_customer                                                    ││
│ │ Action Input: {"phone": "+37060012345"}                                  ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│ TOOL RESULT: {customer_id: "CUST001", name: "Jonas", address: "..."}       │
│                                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ Thought: Found customer. Need to confirm address before diagnostics.    ││
│ │ Action: respond                                                          ││
│ │ Action Input: {"message": "Radau paskyrą. Ar tai adresas Vilniaus g.?"} ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ CUSTOMER: Taip, teisingai                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ Thought: Address confirmed. Check for outages first.                     ││
│ │ Action: check_outages                                                    ││
│ │ Action Input: {"customer_id": "CUST001"}                                 ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│ TOOL RESULT: {affected: false}                                              │
│                                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ Thought: No outages. Check network status.                               ││
│ │ Action: check_network_status                                             ││
│ │ Action Input: {"customer_id": "CUST001"}                                 ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│ TOOL RESULT: {port_status: "up", ip_assigned: true, overall_status: "ok"}  │
│                                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ Thought: Network looks ok. Search for troubleshooting steps.             ││
│ │ Action: search_knowledge                                                 ││
│ │ Action Input: {"query": "internet neveikia"}                             ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│ TOOL RESULT: [router restart guide...]                                      │
│                                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ Thought: Found troubleshooting steps. Guide customer through restart.   ││
│ │ Action: respond                                                          ││
│ │ Action Input: {"message": "Pabandykime perkrauti routerį..."}           ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Error Handling

### Retry Logic

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Error Handling Flow                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   LLM Call                                                                  │
│      │                                                                      │
│      ▼                                                                      │
│   Success? ───YES──▶ Continue                                               │
│      │                                                                      │
│      NO                                                                     │
│      │                                                                      │
│      ▼                                                                      │
│   Retry count < 3? ───YES──▶ Wait and retry                                 │
│      │                                                                      │
│      NO                                                                     │
│      │                                                                      │
│      ▼                                                                      │
│   Return error response                                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Parse Errors

If agent response doesn't match expected format:
1. Try to extract action from malformed response
2. If JSON invalid, treat as plain text response
3. Log warning for debugging

---

## Statistics Tracking

The agent tracks LLM usage statistics.

### Available Stats

| Stat | Description |
|------|-------------|
| `total_calls` | Number of LLM API calls |
| `total_input_tokens` | Input tokens used |
| `total_output_tokens` | Output tokens generated |
| `total_cost` | Estimated cost in USD |
| `average_latency_ms` | Average response time |

### Accessing Stats

```python
agent = ReactAgent(caller_phone="+37060012345")

# After conversation
stats = agent.get_stats()
print(f"Calls: {stats['total_calls']}")
print(f"Cost: ${stats['total_cost']:.4f}")
```

---

## Usage

### Basic Usage

```python
from agent import ReactAgent

# Create agent
agent = ReactAgent(caller_phone="+37060012345")

# Get greeting
response = agent.run_until_response()
print(response)  # "Labas! Kuo galiu padėti?"

# Process user message
response = agent.run_until_response("Neveikia internetas")
print(response)
```

### With Configuration

```python
from agent import ReactAgent
from agent.config import AgentConfig

config = AgentConfig(
    model="gpt-4o",
    temperature=0.3,
    language="en"
)

agent = ReactAgent(
    caller_phone="+37060012345",
    config=config
)
```

### CLI Mode

```bash
# Run interactive CLI
uv run python -m src.agent.react_agent

# With phone number
uv run python -m src.agent.react_agent --phone "+37060012345"
```

---

## Comparison: ReAct vs LangGraph

| Aspect | ReAct Agent | LangGraph Workflow |
|--------|-------------|-------------------|
| **Flow Control** | Autonomous, dynamic | Predefined state machine |
| **Tool Selection** | Agent decides per-turn | Fixed per node |
| **Flexibility** | High - adapts to situation | Medium - follows graph |
| **Debugging** | Thought traces | Node transitions |
| **Error Recovery** | Self-correcting | Explicit error nodes |
| **Complexity** | Single loop | Multiple nodes + routers |

---

## Best Practices

### Prompt Engineering

1. **Be specific** about expected response format
2. **Provide examples** of tool usage
3. **Define escalation criteria** clearly
4. **Specify language** requirements explicitly

### Tool Design

1. **Return structured data** (JSON)
2. **Include success/error flags**
3. **Provide human-readable messages**
4. **Handle edge cases** gracefully

### State Management

1. **Update state** after each significant action
2. **Preserve context** across turns
3. **Track customer identification** status
4. **Log important decisions**

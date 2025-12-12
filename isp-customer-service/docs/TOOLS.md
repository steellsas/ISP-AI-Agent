# Tools Documentation

Reference for agent tools and their specifications.

---

## Overview

The ReAct agent has access to 6 specialized tools for customer service operations. Each tool is a Python function that interacts with databases or external services.

**File Location:** `src/agent/tools.py`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Agent Tools                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                         ReAct Agent                                  │  │
│   │                              │                                       │  │
│   │                              ▼                                       │  │
│   │                      execute_tool()                                  │  │
│   │                              │                                       │  │
│   └──────────────────────────────┼──────────────────────────────────────┘  │
│                                  │                                          │
│         ┌────────────────────────┼────────────────────────┐                 │
│         │                        │                        │                 │
│         ▼                        ▼                        ▼                 │
│   ┌───────────┐           ┌───────────┐           ┌───────────┐            │
│   │    CRM    │           │  Network  │           │    RAG    │            │
│   │   Tools   │           │   Tools   │           │   Tools   │            │
│   │           │           │           │           │           │            │
│   │ • find_   │           │ • check_  │           │ • search_ │            │
│   │   customer│           │   network │           │   knowledge│           │
│   │ • create_ │           │ • check_  │           │           │            │
│   │   ticket  │           │   outages │           │           │            │
│   │           │           │ • run_    │           │           │            │
│   │           │           │   ping    │           │           │            │
│   └─────┬─────┘           └─────┬─────┘           └─────┬─────┘            │
│         │                       │                       │                   │
│         ▼                       ▼                       ▼                   │
│   ┌───────────┐           ┌───────────┐           ┌───────────┐            │
│   │    CRM    │           │  Network  │           │   FAISS   │            │
│   │  Database │           │  Database │           │   Index   │            │
│   └───────────┘           └───────────┘           └───────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Tools Reference

### Quick Reference Table

| Tool | Purpose | Returns |
|------|---------|---------|
| `find_customer` | Find customer by phone/address | Customer info, addresses, services |
| `check_network_status` | Check port, IP, packet loss | Network diagnostics |
| `check_outages` | Check for area outages | Outage info if affected |
| `search_knowledge` | Search troubleshooting guides | Relevant documents |
| `create_ticket` | Create support ticket | Ticket ID |
| `run_ping_test` | Test connection quality | Latency and packet loss |

---

## 1. find_customer

Find customer in CRM database by phone number or address.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `phone` | string | No* | Phone number (e.g., "+37060012345") |
| `address` | string | No* | Address to search |
| `name` | string | No | Customer name |

*At least one of phone or address is required

### Usage

```
Action: find_customer
Action Input: {"phone": "+37060012345"}
```

### Response

**Success:**
```json
{
  "success": true,
  "customer_id": "CUST001",
  "name": "Jonas Jonaitis",
  "phone": "+37060012345",
  "email": "jonas@email.com",
  "status": "active",
  "addresses": [
    {
      "address_id": "ADDR001",
      "full_address": "Vilniaus g. 15-3, Šiauliai",
      "is_primary": true
    }
  ],
  "active_services": ["Fiber 100", "TV Basic"]
}
```

**Not Found:**
```json
{
  "success": false,
  "error": "not_found",
  "message": "Customer not found with this phone number"
}
```

### When To Use

- At the start of every conversation
- When phone lookup fails and customer provides address
- To verify customer information

---

## 2. check_network_status

Comprehensive network diagnostics for a customer.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `customer_id` | string | Yes | Customer ID from CRM |
| `address_id` | string | No | Specific address (if multiple) |

### Usage

```
Action: check_network_status
Action Input: {"customer_id": "CUST001"}
```

### Response

```json
{
  "success": true,
  "customer_id": "CUST001",
  "overall_status": "healthy",
  "port_status": "up",
  "ip_assigned": true,
  "ip_address": "192.168.1.100",
  "packet_loss": {
    "has_packet_loss": false,
    "avg_packet_loss": 0,
    "test_count": 10
  },
  "issues": null,
  "interpretation": "Network connection is healthy. Router is connected."
}
```

**With Issues:**
```json
{
  "success": true,
  "customer_id": "CUST001",
  "overall_status": "issues_detected",
  "port_status": "down",
  "ip_assigned": false,
  "packet_loss": {
    "has_packet_loss": true,
    "avg_packet_loss": 35.5
  },
  "issues": [
    "Port is down - no connection to network",
    "No active IP assignment"
  ],
  "interpretation": "Port is down - requires technician visit."
}
```

### Diagnostics Performed

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     check_network_status Flow                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   customer_id                                                               │
│        │                                                                    │
│        ▼                                                                    │
│   ┌─────────────────┐                                                       │
│   │ 1. Port Status  │──▶ up / down / unknown                               │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │ 2. IP Assignment│──▶ active IP / no IP / expired                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │ 3. Signal Qual. │──▶ good / weak / poor (TV only)                      │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │ 4. Packet Loss  │──▶ % loss from ping tests                            │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │ 5. Bandwidth    │──▶ speed history, jitter, intermittent               │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│      Overall Status                                                         │
│      + Interpretation                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### When To Use

- After customer confirms address
- Before starting troubleshooting
- To verify if issue is on provider side

---

## 3. check_outages

Check for active outages or planned maintenance affecting customer.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `customer_id` | string | No* | Customer ID to check |
| `area` | string | No* | Area/city to check |

*At least one required

### Usage

```
Action: check_outages
Action Input: {"customer_id": "CUST001"}
```

### Response

**No Outage:**
```json
{
  "success": true,
  "customer_id": "CUST001",
  "affected": false,
  "active_outages": [],
  "message": "Customer is not affected by any known outages"
}
```

**Outage Detected:**
```json
{
  "success": true,
  "customer_id": "CUST001",
  "affected": true,
  "active_outages": [
    {
      "outage_id": "OUT001",
      "type": "emergency",
      "description": "Fiber cable damage",
      "start_time": "2024-01-15T08:00:00",
      "estimated_fix": "2024-01-15T14:00:00",
      "affected_services": ["internet", "tv"]
    }
  ],
  "outage_count": 1,
  "message": "Customer is affected by 1 outage"
}
```

### When To Use

- ALWAYS before troubleshooting
- If multiple customers report same issue
- Before escalating to technician

---

## 4. search_knowledge

Search troubleshooting knowledge base using RAG.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Problem description to search |

### Usage

```
Action: search_knowledge
Action Input: {"query": "lėtas internetas wifi"}
```

### Response

```json
{
  "success": true,
  "results": [
    {
      "title": "Slow Internet Troubleshooting",
      "content": "## WiFi Optimization\n\n1. Check router placement...\n2. Change WiFi channel...",
      "score": 0.85,
      "category": "troubleshooting",
      "source": "internet_slow.md"
    },
    {
      "title": "Router Restart Guide",
      "content": "## How to restart your router\n\n1. Unplug power cable...",
      "score": 0.72,
      "category": "procedures",
      "source": "router_restart.md"
    }
  ]
}
```

### Search Features

| Feature | Description |
|---------|-------------|
| Semantic search | Understands meaning, not just keywords |
| Multilingual | Works with Lithuanian and English |
| Hybrid ranking | Combines semantic + keyword matching |
| Score threshold | Only returns relevant results (>0.4) |

### When To Use

- After confirming no outages/network issues
- To find specific troubleshooting steps
- When customer describes a problem

---

## 5. create_ticket

Create support ticket for technician visit or escalation.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `customer_id` | string | Yes | Customer ID |
| `problem_type` | string | Yes | network_issue, technician_visit, equipment_replacement |
| `problem_description` | string | Yes | Detailed description |
| `priority` | string | No | low, medium, high, critical (default: medium) |
| `notes` | string | No | Additional notes for technician |

### Usage

```
Action: create_ticket
Action Input: {
  "customer_id": "CUST001",
  "problem_type": "technician_visit",
  "problem_description": "Port down, router restart did not help. Customer reports all lights are green but no internet.",
  "priority": "high",
  "notes": "Troubleshooting attempted: router restart, cable check"
}
```

### Response

```json
{
  "success": true,
  "ticket_id": "TKT-2024-001234",
  "message": "Ticket created successfully. ID: TKT-2024-001234"
}
```

### When To Use

- Port is down (requires physical intervention)
- High packet loss (line issue)
- Remote troubleshooting exhausted
- Equipment needs replacement

---

## 6. run_ping_test

Test connection latency and packet loss.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `customer_id` | string | Yes | Customer ID |

### Usage

```
Action: run_ping_test
Action Input: {"customer_id": "CUST001"}
```

### Response

```json
{
  "success": true,
  "customer_id": "CUST001",
  "status": "healthy",
  "statistics": {
    "packets_sent": 10,
    "packets_received": 10,
    "packet_loss_percent": 0,
    "min_latency_ms": 12.5,
    "max_latency_ms": 25.3,
    "avg_latency_ms": 18.2
  },
  "summary": "Connection is good. Average ping: 18.2ms"
}
```

### Status Values

| Status | Meaning |
|--------|---------|
| `healthy` | <5% packet loss, <100ms latency |
| `warning` | 5-10% packet loss or high latency |
| `critical` | >10% packet loss |

---

## Tool Registration

Tools are registered in the `REAL_TOOLS` list:

```python
REAL_TOOLS = [
    Tool(
        name="find_customer",
        description="Search for customer in CRM...",
        parameters={
            "phone": {"type": "string", "description": "..."},
            "address": {"type": "string", "description": "..."},
        },
        function=find_customer,
    ),
    # ... more tools
]
```

---

## Tool Execution

### How Tools Are Called

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Tool Execution Flow                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Agent Response:                                                           │
│   "Action: find_customer"                                                   │
│   "Action Input: {"phone": "+37060012345"}"                                │
│                                                                             │
│         │                                                                   │
│         ▼                                                                   │
│   ┌─────────────────┐                                                       │
│   │  Parse Action   │                                                       │
│   │  + Action Input │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │ execute_tool()  │                                                       │
│   │                 │                                                       │
│   │ Find tool in    │                                                       │
│   │ REAL_TOOLS list │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │ Call function   │                                                       │
│   │ with arguments  │                                                       │
│   │                 │                                                       │
│   │ find_customer(  │                                                       │
│   │   phone="..."   │                                                       │
│   │ )               │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │ Return JSON     │                                                       │
│   │ as Observation  │                                                       │
│   └─────────────────┘                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### execute_tool Function

```python
def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool by name with given arguments."""
    for tool in REAL_TOOLS:
        if tool.name == tool_name:
            try:
                result = tool.function(**arguments)
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": str(e)})
    
    return json.dumps({"error": f"Unknown tool: {tool_name}"})
```

---

## Error Handling

### Common Errors

| Error | Cause | Agent Response |
|-------|-------|----------------|
| `missing_customer_id` | Tool requires customer_id | Find customer first |
| `not_found` | Customer/data not found | Ask for alternative info |
| `database_error` | Database connection issue | Retry or apologize |
| `import_error` | Module not available | Use fallback |

### Fallback Behavior

Each tool has a fallback for when external services are unavailable:

```python
try:
    # Try real implementation
    from network_diagnostic_mcp.tools import check_port_status
    result = check_port_status(db, customer_id)
except ImportError:
    # Use fallback
    result = _check_network_status_fallback(customer_id)
```

---

## Adding New Tools

### Step 1: Create Function

```python
def my_new_tool(param1: str, param2: int = None) -> dict:
    """Tool description."""
    try:
        # Implementation
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Step 2: Register Tool

```python
REAL_TOOLS.append(
    Tool(
        name="my_new_tool",
        description="What this tool does",
        parameters={
            "param1": {"type": "string", "required": True},
            "param2": {"type": "integer", "description": "Optional param"},
        },
        function=my_new_tool,
    )
)
```

### Step 3: Update System Prompt

Add tool description to agent's system prompt so it knows how to use it.

---

## Testing Tools

### Run Tool Tests

```bash
# All tool tests
uv run pytest tests/test_scenarios.py -v

# Specific scenario
uv run pytest tests/test_scenarios.py::TestScenario04PortDown -v
```

### Manual Testing

```python
from agent.tools import find_customer, check_network_status

# Test find_customer
result = find_customer(phone="+37060012345")
print(result)

# Test check_network_status
result = check_network_status(customer_id="CUST001")
print(result)
```

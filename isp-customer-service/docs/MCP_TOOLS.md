# MCP Tools Documentation

Reference for Model Context Protocol (MCP) servers and tools.

## Table of Contents

- [Overview](#overview)
- [CRM Service](#crm-service)
- [Network Diagnostics](#network-diagnostics)
- [MCP Client Usage](#mcp-client-usage)
- [Adding New Tools](#adding-new-tools)
- [Error Handling](#error-handling)

---

## Overview

The system uses MCP (Model Context Protocol) to communicate with external services. MCP provides a standardized JSON-RPC interface for tool execution.

### Architecture

```
┌──────────────┐      JSON-RPC       ┌──────────────┐
│  Workflow    │◄───────────────────►│  MCP Server  │
│    Node      │      (stdio)        │              │
└──────────────┘                     └──────┬───────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │   Database   │
                                    │   (SQLite)   │
                                    └──────────────┘
```

### Available Servers

| Server | Purpose | Location |
|--------|---------|----------|
| CRM Service | Customer data, tickets | `crm_service/src/crm_mcp/server.py` |
| Network Diagnostics | Network status checks | `network_service/src/server.py` *(simulated)* |

---

## CRM Service

### Server Configuration

**File:** `crm_service/src/crm_mcp/server.py`

```python
class CRMServer:
    def __init__(self, db_path: str | Path):
        self.db = init_database(db_path)
        self.server = Server("crm-service")
        self._register_tools()
```

### Available Tools

#### lookup_customer_by_phone

Find customer by phone number.

**Schema:**
```python
Tool(
    name="lookup_customer_by_phone",
    description="Find customer by phone number",
    inputSchema={
        "type": "object",
        "properties": {
            "phone_number": {
                "type": "string",
                "description": "Phone number (e.g., '+37060000000', '860000000')"
            }
        },
        "required": ["phone_number"]
    }
)
```

**Usage:**
```python
result = await mcp.call_tool(
    "crm_service",
    "lookup_customer_by_phone",
    {"phone_number": "+37060000000"}
)
```

**Response:**
```python
# Success
{
    "success": True,
    "customer": {
        "customer_id": "CUST001",
        "name": "Jonas Jonaitis",
        "phone": "+37060000000",
        "email": "jonas@email.com",
        "addresses": [
            {
                "address_id": "ADDR001",
                "city": "Šiauliai",
                "street": "Tilžės g.",
                "house_number": "12",
                "apartment": "5",
                "full_address": "Tilžės g. 12-5, Šiauliai",
                "is_primary": True
            }
        ]
    }
}

# Not found
{
    "success": False,
    "error": "Customer not found",
    "customer": None
}
```

---

#### lookup_customer_by_address

Find customer by address with fuzzy matching.

**Schema:**
```python
Tool(
    name="lookup_customer_by_address",
    description="Find customer by address. Supports fuzzy matching for street names.",
    inputSchema={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name (e.g., 'Šiauliai')"
            },
            "street": {
                "type": "string",
                "description": "Street name (e.g., 'Tilžės', 'Tilzes g.')"
            },
            "house_number": {
                "type": "string",
                "description": "House number (e.g., '12')"
            },
            "apartment_number": {
                "type": "string",
                "description": "Apartment number (optional, e.g., '5')"
            }
        },
        "required": ["city", "street", "house_number"]
    }
)
```

**Features:**
- Fuzzy street name matching (handles typos)
- Lithuanian character normalization (ž→z, š→s, etc.)
- Common abbreviations (g. = gatvė, pr. = prospektas)

**Response:**
```python
# Found
{
    "success": True,
    "customer": {
        "customer_id": "CUST001",
        "name": "Jonas Jonaitis",
        # ... full customer data
    },
    "match_confidence": 0.95
}

# Multiple matches
{
    "success": True,
    "multiple_matches": True,
    "customers": [
        {"customer_id": "CUST001", ...},
        {"customer_id": "CUST002", ...}
    ]
}

# Not found
{
    "success": False,
    "error": "No customer found at this address",
    "suggestions": [
        "Tilžės g. 10-5, Šiauliai",
        "Tilžės g. 12-3, Šiauliai"
    ]
}
```

---

#### get_customer_details

Get detailed customer information including services and equipment.

**Schema:**
```python
Tool(
    name="get_customer_details",
    description="Get detailed customer information including services, equipment, and history.",
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "Customer ID (e.g., 'CUST001')"
            }
        },
        "required": ["customer_id"]
    }
)
```

**Response:**
```python
{
    "success": True,
    "customer": {
        "customer_id": "CUST001",
        "name": "Jonas Jonaitis",
        "phone": "+37060000000",
        "email": "jonas@email.com",
        "status": "active",
        "since": "2020-03-15",
        "addresses": [...],
        "services": [
            {
                "service_id": "SVC001",
                "type": "internet",
                "plan": "Fiber 100",
                "speed": "100 Mbps",
                "status": "active",
                "address_id": "ADDR001"
            },
            {
                "service_id": "SVC002",
                "type": "tv",
                "plan": "TV Basic",
                "channels": 80,
                "status": "active"
            }
        ],
        "equipment": [
            {
                "equipment_id": "EQ001",
                "type": "router",
                "model": "TP-Link Archer C7",
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "status": "active"
            }
        ]
    }
}
```

---

#### get_customer_equipment

Get customer's equipment list.

**Schema:**
```python
Tool(
    name="get_customer_equipment",
    description="Get customer's equipment (routers, decoders, etc.)",
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "Customer ID"
            }
        },
        "required": ["customer_id"]
    }
)
```

**Response:**
```python
{
    "success": True,
    "equipment": [
        {
            "equipment_id": "EQ001",
            "type": "router",
            "model": "TP-Link Archer C7",
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "serial_number": "SN123456",
            "installed_date": "2020-03-20",
            "status": "active",
            "last_seen": "2024-01-15T10:00:00"
        },
        {
            "equipment_id": "EQ002",
            "type": "decoder",
            "model": "MAG 322",
            "mac_address": "11:22:33:44:55:66",
            "status": "active"
        }
    ]
}
```

---

#### create_ticket

Create a new support ticket.

**Schema:**
```python
Tool(
    name="create_ticket",
    description="Create a new support ticket.",
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "Customer ID"
            },
            "ticket_type": {
                "type": "string",
                "enum": [
                    "network_issue",
                    "resolved",
                    "technician_visit",
                    "customer_not_found",
                    "no_service_area"
                ],
                "description": "Type of ticket"
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "Ticket priority"
            },
            "summary": {
                "type": "string",
                "description": "Brief summary of the issue"
            },
            "details": {
                "type": "string",
                "description": "Detailed description"
            },
            "troubleshooting_steps": {
                "type": "string",
                "description": "Steps already taken"
            }
        },
        "required": ["customer_id", "ticket_type", "summary"]
    }
)
```

**Usage:**
```python
result = await mcp.call_tool(
    "crm_service",
    "create_ticket",
    {
        "customer_id": "CUST001",
        "ticket_type": "network_issue",
        "priority": "high",
        "summary": "Internet not working after router restart",
        "details": "Customer reports no internet connection...",
        "troubleshooting_steps": "1. Checked router lights - all green\n2. Restarted router - no change"
    }
)
```

**Response:**
```python
{
    "success": True,
    "ticket": {
        "ticket_id": "TKT-2024-001234",
        "status": "open",
        "created_at": "2024-01-15T10:45:00",
        "assigned_to": None,
        "estimated_response": "2024-01-15T14:00:00"
    }
}
```

---

#### get_customer_tickets

Get customer's ticket history.

**Schema:**
```python
Tool(
    name="get_customer_tickets",
    description="Get customer's ticket history",
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "Customer ID"
            },
            "status": {
                "type": "string",
                "enum": ["open", "in_progress", "closed", "all"],
                "description": "Filter by status (default: all)"
            }
        },
        "required": ["customer_id"]
    }
)
```

**Response:**
```python
{
    "success": True,
    "tickets": [
        {
            "ticket_id": "TKT-2024-001234",
            "type": "network_issue",
            "summary": "Internet not working",
            "status": "closed",
            "created_at": "2024-01-10T10:00:00",
            "closed_at": "2024-01-10T15:00:00",
            "resolution": "Router replaced"
        },
        {
            "ticket_id": "TKT-2024-001100",
            "type": "technician_visit",
            "summary": "Fiber cable damage",
            "status": "in_progress",
            "created_at": "2024-01-14T09:00:00",
            "assigned_to": "Tech Team A"
        }
    ],
    "total_count": 2
}
```

---

## Network Diagnostics

> ⚠️ **Note:** Network diagnostics are simulated in this demo. Production would require integration with real network monitoring systems.

### Available Tools

#### check_area_outages

Check for known outages in customer's area.

**Schema:**
```python
Tool(
    name="check_area_outages",
    description="Check for known outages in area",
    inputSchema={
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "street": {"type": "string"}
        },
        "required": ["city"]
    }
)
```

**Response:**
```python
# No outage
{
    "outage_detected": False,
    "outage_type": None,
    "estimated_fix": None,
    "affected_services": []
}

# Outage detected
{
    "outage_detected": True,
    "outage_type": "emergency",  # "planned_maintenance" | "emergency"
    "start_time": "2024-01-15T08:00:00",
    "estimated_fix": "2024-01-15T14:00:00",
    "affected_services": ["internet", "tv"],
    "description": "Fiber cable damage in area"
}
```

---

#### check_port_status

Check customer's network port status.

**Schema:**
```python
Tool(
    name="check_port_status",
    description="Check customer's network port status",
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"}
        },
        "required": ["customer_id"]
    }
)
```

**Response:**
```python
{
    "status": "up",  # "up" | "down" | "flapping"
    "last_change": "2024-01-15T08:00:00",
    "uptime_percent": 99.9,
    "error_count": 0,
    "speed": "1000 Mbps",
    "duplex": "full"
}
```

---

#### check_ip_assignment

Check if customer has active IP assignment.

**Schema:**
```python
Tool(
    name="check_ip_assignment",
    description="Check customer's IP assignment",
    inputSchema={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"}
        },
        "required": ["customer_id"]
    }
)
```

**Response:**
```python
{
    "has_active_ip": True,
    "ip_address": "192.168.1.100",
    "assignment_type": "dhcp",  # "dhcp" | "static"
    "lease_start": "2024-01-15T00:00:00",
    "lease_expires": "2024-01-16T00:00:00",
    "gateway": "192.168.1.1",
    "dns_servers": ["8.8.8.8", "8.8.4.4"]
}
```

---

## MCP Client Usage

### Basic Usage

```python
from services.mcp_service import get_mcp_service

async def example():
    mcp = get_mcp_service()
    
    # Call tool
    result = await mcp.call_tool(
        server_name="crm_service",
        tool_name="lookup_customer_by_phone",
        arguments={"phone_number": "+37060000000"}
    )
    
    if result["success"]:
        customer = result["customer"]
        print(f"Found: {customer['name']}")
    else:
        print(f"Error: {result['error']}")
```

### With Timeout

```python
result = await mcp.call_tool(
    server_name="crm_service",
    tool_name="lookup_customer_by_phone",
    arguments={"phone_number": "+37060000000"},
    timeout=5.0  # 5 second timeout
)
```

### Batch Calls

```python
async def get_full_customer_data(customer_id: str):
    mcp = get_mcp_service()
    
    # Run multiple calls in parallel
    details, equipment, tickets = await asyncio.gather(
        mcp.call_tool("crm_service", "get_customer_details", {"customer_id": customer_id}),
        mcp.call_tool("crm_service", "get_customer_equipment", {"customer_id": customer_id}),
        mcp.call_tool("crm_service", "get_customer_tickets", {"customer_id": customer_id}),
    )
    
    return {
        "details": details,
        "equipment": equipment,
        "tickets": tickets
    }
```

---

## Adding New Tools

### Step 1: Define Tool in Server

```python
# In server.py

@self.server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        # ... existing tools
        
        Tool(
            name="my_new_tool",
            description="Description of what the tool does",
            inputSchema={
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "Parameter description"
                    },
                    "param2": {
                        "type": "integer",
                        "description": "Another parameter"
                    }
                },
                "required": ["param1"]
            }
        )
    ]
```

### Step 2: Implement Handler

```python
@self.server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    if name == "my_new_tool":
        result = await self._my_new_tool(arguments)
    # ...
    
async def _my_new_tool(self, args: Dict[str, Any]) -> Dict[str, Any]:
    param1 = args["param1"]
    param2 = args.get("param2", 0)  # Optional with default
    
    # Your logic here
    
    return {
        "success": True,
        "data": result_data
    }
```

### Step 3: Use in Workflow Node

```python
# In your node file
async def my_node(state):
    mcp = get_mcp_service()
    
    result = await mcp.call_tool(
        "crm_service",
        "my_new_tool",
        {"param1": "value", "param2": 42}
    )
    
    if result["success"]:
        # Process result
        pass
```

---

## Error Handling

### Common Errors

| Error | Cause | Handling |
|-------|-------|----------|
| `ConnectionError` | Server not running | Start MCP server |
| `TimeoutError` | Tool took too long | Retry or use longer timeout |
| `ToolNotFound` | Invalid tool name | Check tool registration |
| `ValidationError` | Invalid arguments | Check input schema |

### Error Response Format

```python
{
    "success": False,
    "error": "Error message",
    "error_code": "ERROR_CODE",
    "details": {
        # Additional error context
    }
}
```

### Handling in Nodes

```python
async def safe_tool_call(state):
    mcp = get_mcp_service()
    
    try:
        result = await mcp.call_tool(
            "crm_service",
            "lookup_customer_by_phone",
            {"phone_number": state.phone_number}
        )
        
        if not result.get("success"):
            # Tool returned error
            return {
                "last_error": result.get("error", "Unknown error"),
                "customer_id": None
            }
        
        return {
            "customer_id": result["customer"]["customer_id"],
            "last_error": None
        }
        
    except TimeoutError:
        return {
            "last_error": "CRM service timeout",
            "customer_id": None
        }
    except Exception as e:
        return {
            "last_error": str(e),
            "customer_id": None
        }
```

---

## Server Management

### Starting Servers

```bash
# Start CRM service
python -m crm_service.src.crm_mcp.server

# Or with specific database
DB_PATH=/path/to/database.db python -m crm_service.src.crm_mcp.server
```

### Server Logs

Logs are written to `crm_service/logs/crm_service.log`:

```
2024-01-15 10:00:00 INFO CRM Service initialized
2024-01-15 10:00:05 INFO Tool called: lookup_customer_by_phone with args: {'phone_number': '+37060000000'}
2024-01-15 10:00:05 INFO Customer found: CUST001
```

### Health Check

```python
async def check_server_health():
    mcp = get_mcp_service()
    
    try:
        # Simple ping
        result = await mcp.call_tool(
            "crm_service",
            "get_customer_details",
            {"customer_id": "TEST"},
            timeout=2.0
        )
        return True
    except:
        return False
```

---



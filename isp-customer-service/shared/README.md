# ISP Shared Library

Shared utilities, types, and database access for ISP Customer Service microservices.

## 📦 What's Inside

### Database (`src/database/`)
- **`connection.py`** - Thread-safe SQLite connection manager with pooling
- **`base.py`** - Base repository class with common CRUD operations

### Types (`src/types/`)
Pydantic models for data validation across all services:
- **`customer.py`** - Customer, Address, ServicePlan, Equipment models
- **`ticket.py`** - Ticket, TicketType, Priority, Status models
- **`network.py`** - Switch, Port, IPAssignment, AreaOutage models

### Utils (`src/utils/`)
- **`logger.py`** - Centralized logging configuration
- **`config.py`** - Environment variable and settings management

## 🚀 Usage

### Database Connection

```python
from shared.src.database import init_database, get_db_connection

# Initialize once at startup
db = init_database("database/isp_database.db")

# Use in your code
with db.cursor() as cursor:
    cursor.execute("SELECT * FROM customers WHERE customer_id = ?", ("CUST001",))
    result = cursor.fetchone()
```

### Using Types

```python
from shared.src.types import Customer, Ticket, TicketType

# Create customer instance
customer = Customer(
    customer_id="CUST001",
    first_name="Jonas",
    last_name="Jonaitis",
    phone="+37060012345",
    email="jonas@example.com"
)

# Validate data
try:
    ticket = Ticket(
        ticket_id="TKT001",
        customer_id="CUST001",
        ticket_type=TicketType.NETWORK_ISSUE,
        summary="Internet connection problem"
    )
except ValidationError as e:
    print(f"Validation error: {e}")
```

### Logging

```python
from shared.src.utils import setup_logger

# Service-specific loggers
logger = setup_crm_logger(level="INFO")
logger.info("CRM service started")

# Or custom logger
logger = setup_logger("my_service", level="DEBUG", log_file="logs/my_service.log")
```

### Configuration

```python
from shared.src.utils import get_config, load_env

# Load .env file
load_env()

# Get configuration
config = get_config()
print(f"Database: {config.database_path}")
print(f"OpenAI Model: {config.openai_model}")

# Validate configuration
if config.validate():
    print("Configuration is valid")
```

## 📋 Dependencies

Core dependencies:
- `pydantic>=2.0.0` - Data validation
- `pydantic-settings>=2.0.0` - Settings management
- `python-dotenv>=1.0.0` - Environment variables

## 🧪 Testing

```bash
pytest tests/
```

## 📚 Used By

This shared library is used by:
- **chatbot-core** - Main chatbot with LangGraph
- **crm-service** - CRM data MCP server
- **network-diagnostic-service** - Network diagnostics MCP server
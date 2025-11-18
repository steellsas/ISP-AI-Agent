"""
CRM Service MCP Server
Provides customer data access tools via MCP protocol
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from database import init_database




# Setup logger



from utils.logger import setup_mcp_server_logger

# logger = setup_mcp_server_logger(
#     "crm_service",
#     level="INFO",
#     log_file=Path("logs/crm_service.log")
# )

# Setup logger with absolute path
log_dir = Path(__file__).parent.parent.parent / "logs"  # crm_service/logs/
log_dir.mkdir(exist_ok=True)  # Ensure directory exists

logger = setup_mcp_server_logger(
    "crm_service",
    level="INFO",
    log_file=log_dir / "crm_service.log"
)




class CRMServer:
    """CRM Service MCP Server."""
    
    def __init__(self, db_path: str | Path):
        """
        Initialize CRM Server.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db = init_database(db_path)
        self.server = Server("crm-service")
        
        # Register tools
        self._register_tools()
        
        logger.info("CRM Service initialized")
    
    def _register_tools(self) -> None:
        """Register all MCP tools."""
        
        # Tool 1: Customer Lookup by Address
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name="lookup_customer_by_address",
                    description=(
                        "Find customer by address. Supports fuzzy matching for street names. "
                        "Use this when user provides their address (city, street, house number)."
                    ),
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
                ),
                Tool(
                    name="get_customer_details",
                    description=(
                        "Get detailed customer information including services, equipment, and history. "
                        "Use after customer is identified."
                    ),
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
                ),
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
                ),
                Tool(
                    name="create_ticket",
                    description=(
                        "Create a new support ticket. "
                        "Use after troubleshooting when issue requires technician or further action."
                    ),
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
                ),
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
                ),
            ]
        
        # Tool handlers
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls."""
            
            logger.info(f"Tool called: {name} with args: {arguments}")
            
            try:
                if name == "lookup_customer_by_address":
                    result = await self._lookup_customer_by_address(arguments)
                elif name == "get_customer_details":
                    result = await self._get_customer_details(arguments)
                elif name == "get_customer_equipment":
                    result = await self._get_customer_equipment(arguments)
                elif name == "create_ticket":
                    result = await self._create_ticket(arguments)
                elif name == "get_customer_tickets":
                    result = await self._get_customer_tickets(arguments)
                else:
                    result = {"error": f"Unknown tool: {name}"}
                
                return [TextContent(
                    type="text",
                    text=str(result)
                )]
                
            except Exception as e:
                logger.error(f"Error in tool {name}: {e}", exc_info=True)
                return [TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )]
    
    async def _lookup_customer_by_address(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Lookup customer by address with fuzzy matching."""
        from .tools.customer_lookup import lookup_customer_by_address
        return lookup_customer_by_address(self.db, args)
    
    async def _get_customer_details(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed customer information."""
        from .tools.customer_lookup import get_customer_details
        return get_customer_details(self.db, args["customer_id"])
    
    async def _get_customer_equipment(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get customer equipment."""
        from .tools.equipment import get_customer_equipment
        return get_customer_equipment(self.db, args["customer_id"])
    
    async def _create_ticket(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create support ticket."""
        from .tools.tickets import create_ticket
        return create_ticket(self.db, args)
    
    async def _get_customer_tickets(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get customer tickets."""
        from .tools.tickets import get_customer_tickets
        return get_customer_tickets(
            self.db,
            args["customer_id"],
            args.get("status", "all")
        )
    
    async def run(self) -> None:
        """Run the MCP server."""
        logger.info("Starting CRM Service MCP Server... Run ")
        logger.info("Waiting for stdio streams...")
    
     
        
        # async with stdio_server() as (read_stream, write_stream):
        #     await self.server.run(
        #         read_stream,
        #         write_stream,
        #         self.server.create_initialization_options()
        #     )
        logger.info("Waiting for stdio streams...")
    
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Got stdio streams")
            logger.info("Calling server.run()...")

            original_run = self.server.run
        
            logger.info("Server ready to receive requests")
         
            
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )
            
            # ADD THIS (won't reach if blocking):
            logger.info("Server.run() completed")


def create_server(db_path: str | Path) -> CRMServer:
    """
    Create CRM MCP Server instance.
    
    Args:
        db_path: Path to database file
        
    Returns:
        CRMServer instance
    """
    return CRMServer(db_path)


async def main():
    """Main entry point."""
    # Get database path
    project_root = Path(__file__).parent.parent.parent.parent
    db_path = project_root / "database" / "isp_database.db"
    
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        sys.exit(1)
    
    # Create and run server
    server = create_server(db_path)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
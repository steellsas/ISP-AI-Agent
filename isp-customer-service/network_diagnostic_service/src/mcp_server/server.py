"""
Network Diagnostic Service MCP Server
Provides network diagnostic tools via MCP protocol
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
from utils import setup_logger

# Setup logger
logger = setup_logger("network_diagnostic_service", level="INFO")


class NetworkDiagnosticServer:
    """Network Diagnostic Service MCP Server."""
    
    def __init__(self, db_path: str | Path):
        """
        Initialize Network Diagnostic Server.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db = init_database(db_path)
        self.server = Server("network-diagnostic-service")
        
        # Register tools
        self._register_tools()
        
        logger.info("Network Diagnostic Service initialized")
    
    def _register_tools(self) -> None:
        """Register all MCP tools."""
        
        # Tool definitions
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name="check_port_status",
                    description=(
                        "Check network port status for a customer. "
                        "Returns port connection status, speed, and diagnostics. "
                        "Use when troubleshooting connectivity issues."
                    ),
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
                    name="check_ip_assignment",
                    description=(
                        "Check IP address assignment and DHCP lease status. "
                        "Use to verify IP configuration and connectivity."
                    ),
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
                    name="check_bandwidth_history",
                    description=(
                        "Get bandwidth usage history and speed test results. "
                        "Shows recent download/upload speeds and performance metrics."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "customer_id": {
                                "type": "string",
                                "description": "Customer ID"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of recent measurements (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["customer_id"]
                    }
                ),
                Tool(
                    name="check_area_outages",
                    description=(
                        "Check for area-wide service outages affecting customer's location. "
                        "Use when multiple customers in same area report issues."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "City name"
                            },
                            "street": {
                                "type": "string",
                                "description": "Street name (optional)"
                            }
                        },
                        "required": ["city"]
                    }
                ),
                Tool(
                    name="check_signal_quality",
                    description=(
                        "Check signal quality for TV/Cable service. "
                        "Returns signal strength, SNR, and quality metrics."
                    ),
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
                    name="ping_test",
                    description=(
                        "Perform mock ping test to customer's equipment. "
                        "Returns latency and packet loss simulation. "
                        "Note: This is a simulated test based on historical data."
                    ),
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
                    name="get_switch_info",
                    description=(
                        "Get information about the network switch serving a customer. "
                        "Shows switch status, location, and health."
                    ),
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
            ]
        
        # Tool handlers
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls."""
            
            logger.info(f"Tool called: {name} with args: {arguments}")
            
            try:
                if name == "check_port_status":
                    result = await self._check_port_status(arguments)
                elif name == "check_ip_assignment":
                    result = await self._check_ip_assignment(arguments)
                elif name == "check_bandwidth_history":
                    result = await self._check_bandwidth_history(arguments)
                elif name == "check_area_outages":
                    result = await self._check_area_outages(arguments)
                elif name == "check_signal_quality":
                    result = await self._check_signal_quality(arguments)
                elif name == "ping_test":
                    result = await self._ping_test(arguments)
                elif name == "get_switch_info":
                    result = await self._get_switch_info(arguments)
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
    
    async def _check_port_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check port status for customer."""
        from .tools.port_diagnostics import check_port_status
        return check_port_status(self.db, args["customer_id"])
    
    async def _check_ip_assignment(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check IP assignment."""
        from .tools.connectivity_tests import check_ip_assignment
        return check_ip_assignment(self.db, args["customer_id"])
    
    async def _check_bandwidth_history(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check bandwidth history."""
        from .tools.connectivity_tests import check_bandwidth_history
        return check_bandwidth_history(
            self.db,
            args["customer_id"],
            args.get("limit", 10)
        )
    
    async def _check_area_outages(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check area outages."""
        from .tools.outage_checks import check_area_outages
        return check_area_outages(
            self.db,
            args["city"],
            args.get("street")
        )
    
    async def _check_signal_quality(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check signal quality."""
        from .tools.connectivity_tests import check_signal_quality
        return check_signal_quality(self.db, args["customer_id"])
    
    async def _ping_test(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Perform ping test."""
        from .tools.connectivity_tests import ping_test
        return ping_test(self.db, args["customer_id"])
    
    async def _get_switch_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get switch information."""
        from .tools.port_diagnostics import get_switch_info
        return get_switch_info(self.db, args["customer_id"])
    
    async def run(self) -> None:
        """Run the MCP server."""
        logger.info("Starting Network Diagnostic Service MCP Server...")
        
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def create_server(db_path: str | Path) -> NetworkDiagnosticServer:
    """
    Create Network Diagnostic MCP Server instance.
    
    Args:
        db_path: Path to database file
        
    Returns:
        NetworkDiagnosticServer instance
    """
    return NetworkDiagnosticServer(db_path)


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
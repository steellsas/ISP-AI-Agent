"""
MCP Service
Orchestrates calls to CRM and Network Diagnostic MCP servers
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from enum import Enum

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger

logger = get_logger(__name__)


class MCPServerType(str, Enum):
    """MCP server types."""
    CRM = "crm"
    NETWORK = "network"


class MCPService:
    """
    MCP Service for orchestrating MCP tool calls.
    
    Features:
    - Call CRM MCP tools
    - Call Network Diagnostic MCP tools
    - Tool call logging and monitoring
    - Error handling and retries
    """
    
    def __init__(
        self,
        crm_server_url: Optional[str] = None,
        network_server_url: Optional[str] = None
    ):
        """
        Initialize MCP service.
        
        Args:
            crm_server_url: CRM MCP server URL
            network_server_url: Network MCP server URL
        """
        self.crm_server_url = crm_server_url or "stdio://crm-service"
        self.network_server_url = network_server_url or "stdio://network-diagnostic-service"
        
        # TODO: Initialize actual MCP clients
        # For now, we'll simulate the calls
        self.crm_client = None
        self.network_client = None
        
        # Statistics
        self.tool_calls = []
        self.total_calls = 0
        self.failed_calls = 0
        
        logger.info("MCPService initialized")
    
    async def call_crm_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call CRM MCP tool.
        
        Available tools:
        - lookup_customer_by_address
        - get_customer_details
        - get_customer_equipment
        - create_ticket
        - get_customer_tickets
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result dictionary
        """
        logger.info(f"Calling CRM tool: {tool_name} with args: {arguments}")
        
        try:
            # TODO: Replace with actual MCP client call
            # result = await self.crm_client.call_tool(tool_name, arguments)
            
            # For now, simulate the call
            result = self._simulate_crm_tool(tool_name, arguments)
            
            # Log the call
            self._log_tool_call(MCPServerType.CRM, tool_name, arguments, result, success=True)
            
            return result
            
        except Exception as e:
            logger.error(f"Error calling CRM tool {tool_name}: {e}", exc_info=True)
            self.failed_calls += 1
            
            error_result = {
                "success": False,
                "error": "mcp_error",
                "message": str(e)
            }
            
            self._log_tool_call(MCPServerType.CRM, tool_name, arguments, error_result, success=False)
            
            return error_result
    
    async def call_network_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call Network Diagnostic MCP tool.
        
        Available tools:
        - check_port_status
        - check_ip_assignment
        - check_bandwidth_history
        - check_area_outages
        - check_signal_quality
        - ping_test
        - get_switch_info
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result dictionary
        """
        logger.info(f"Calling Network tool: {tool_name} with args: {arguments}")
        
        try:
            # TODO: Replace with actual MCP client call
            # result = await self.network_client.call_tool(tool_name, arguments)
            
            # For now, simulate the call
            result = self._simulate_network_tool(tool_name, arguments)
            
            # Log the call
            self._log_tool_call(MCPServerType.NETWORK, tool_name, arguments, result, success=True)
            
            return result
            
        except Exception as e:
            logger.error(f"Error calling Network tool {tool_name}: {e}", exc_info=True)
            self.failed_calls += 1
            
            error_result = {
                "success": False,
                "error": "mcp_error",
                "message": str(e)
            }
            
            self._log_tool_call(MCPServerType.NETWORK, tool_name, arguments, error_result, success=False)
            
            return error_result
    
    def _simulate_crm_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate CRM tool calls (temporary)."""
        
        if tool_name == "lookup_customer_by_address":
            # Simulate customer lookup
            city = arguments.get("city")
            house_number = arguments.get("house_number")
            
            if city == "Šiauliai" and house_number == "60":
                return {
                    "success": True,
                    "customer": {
                        "customer_id": "CUST001",
                        "first_name": "Jonas",
                        "last_name": "Jonaitis",
                        "phone": "+37060012345",
                        "email": "jonas@example.com",
                        "address": {
                            "city": city,
                            "street": arguments.get("street", "Tilžės g."),
                            "house_number": house_number,
                            "apartment_number": arguments.get("apartment_number"),
                            "full_address": f"{city}, Tilžės g. {house_number}"
                        }
                    }
                }
            else:
                return {
                    "success": False,
                    "error": "customer_not_found",
                    "message": "Klientas nerastas"
                }
        
        elif tool_name == "get_customer_details":
            return {
                "success": True,
                "customer": {
                    "customer_id": arguments.get("customer_id"),
                    "first_name": "Jonas",
                    "last_name": "Jonaitis"
                },
                "services": [
                    {"service_type": "internet", "plan_name": "300 Mbps"}
                ],
                "equipment": [
                    {"equipment_type": "router", "model": "TP-Link"}
                ]
            }
        
        elif tool_name == "create_ticket":
            import uuid
            ticket_id = f"TKT{uuid.uuid4().hex[:8].upper()}"
            
            return {
                "success": True,
                "ticket": {
                    "ticket_id": ticket_id,
                    "customer_id": arguments.get("customer_id"),
                    "ticket_type": arguments.get("ticket_type"),
                    "priority": arguments.get("priority", "medium"),
                    "summary": arguments.get("summary")
                }
            }
        
        else:
            return {"success": False, "error": "unknown_tool"}
    
    def _simulate_network_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate Network tool calls (temporary)."""
        
        if tool_name == "check_port_status":
            return {
                "success": True,
                "diagnostics": {
                    "total_ports": 1,
                    "ports_up": 1,
                    "ports_down": 0,
                    "all_ports_healthy": True
                }
            }
        
        elif tool_name == "check_ip_assignment":
            return {
                "success": True,
                "active_count": 1,
                "ip_assignments": [{
                    "ip_address": "192.168.1.100",
                    "assignment_type": "dhcp",
                    "status": "active"
                }]
            }
        
        elif tool_name == "ping_test":
            return {
                "success": True,
                "status": "healthy",
                "statistics": {
                    "packet_loss_percent": 0.0,
                    "avg_latency_ms": 22.5
                }
            }
        
        elif tool_name == "check_area_outages":
            return {
                "success": True,
                "outages": [],
                "message": "Nėra gedimų rajone"
            }
        
        else:
            return {"success": False, "error": "unknown_tool"}
    
    def _log_tool_call(
        self,
        server_type: MCPServerType,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
        success: bool
    ):
        """Log tool call for monitoring."""
        from datetime import datetime
        
        call_log = {
            "timestamp": datetime.now().isoformat(),
            "server_type": server_type.value,
            "tool_name": tool_name,
            "arguments": arguments,
            "success": success,
            "result_summary": {
                "success": result.get("success"),
                "error": result.get("error")
            }
        }
        
        self.tool_calls.append(call_log)
        self.total_calls += 1
        
        # Keep only last 100 calls
        if len(self.tool_calls) > 100:
            self.tool_calls = self.tool_calls[-100:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get MCP service statistics.
        
        Returns:
            Statistics dictionary
        """
        crm_calls = sum(1 for call in self.tool_calls if call["server_type"] == "crm")
        network_calls = sum(1 for call in self.tool_calls if call["server_type"] == "network")
        
        return {
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "success_rate": (self.total_calls - self.failed_calls) / self.total_calls if self.total_calls > 0 else 0,
            "crm_calls": crm_calls,
            "network_calls": network_calls,
            "recent_calls": len(self.tool_calls)
        }
    
    def get_recent_calls(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent tool calls.
        
        Args:
            limit: Maximum number of calls to return
            
        Returns:
            List of recent call logs
        """
        return self.tool_calls[-limit:]
    
    def reset_statistics(self):
        """Reset statistics."""
        self.tool_calls = []
        self.total_calls = 0
        self.failed_calls = 0
        logger.info("MCP statistics reset")


# Singleton instance
_mcp_service: Optional[MCPService] = None


def get_mcp_service(
    crm_server_url: Optional[str] = None,
    network_server_url: Optional[str] = None
) -> MCPService:
    """
    Get or create MCPService singleton instance.
    
    Args:
        crm_server_url: CRM server URL (only used on first call)
        network_server_url: Network server URL (only used on first call)
        
    Returns:
        MCPService instance
    """
    global _mcp_service
    
    if _mcp_service is None:
        _mcp_service = MCPService(
            crm_server_url=crm_server_url,
            network_server_url=network_server_url
        )
    
    return _mcp_service


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_mcp():
        """Test MCP service."""
        mcp = MCPService()
        
        # Test CRM tool
        print("Testing CRM tool...")
        result = await mcp.call_crm_tool("lookup_customer_by_address", {
            "city": "Šiauliai",
            "street": "Tilžės g.",
            "house_number": "60"
        })
        print(f"Result: {result}")
        
        # Test Network tool
        print("\nTesting Network tool...")
        result = await mcp.call_network_tool("check_port_status", {
            "customer_id": "CUST001"
        })
        print(f"Result: {result}")
        
        # Statistics
        print("\nStatistics:")
        stats = mcp.get_statistics()
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        # Recent calls
        print("\nRecent calls:")
        recent = mcp.get_recent_calls(limit=5)
        for call in recent:
            print(f"  {call['tool_name']} - Success: {call['success']}")
    
    asyncio.run(test_mcp())

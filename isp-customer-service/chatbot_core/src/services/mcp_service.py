"""
MCP Service
Orchestrates calls to CRM and Network Diagnostic MCP servers
Uses CustomMCPClient instead of MCP SDK (Windows compatibility)
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from enum import Enum

try:
    from isp_shared.utils.logger import get_logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)

# Use custom MCP client (fixes Windows stdio issues)
from src.services.custom_mcp_client import CustomMCPClient

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
    - Custom MCP client (Windows compatible)
    - Tool call logging and monitoring
    - Error handling and retries
    """
    
    def __init__(
        self,
        crm_server_path: Optional[str] = None,
        network_server_path: Optional[str] = None
    ):
        """
        Initialize MCP service.
        
        Args:
            crm_server_path: Path to CRM service directory (relative or absolute)
            network_server_path: Path to Network service directory (relative or absolute)
        """
        # Default paths (relative to chatbot_core)
        if crm_server_path:
            self.crm_server_path = Path(crm_server_path)
        else:
            # Default: ../crm_service from chatbot_core root
            self.crm_server_path = Path(__file__).parent.parent.parent.parent / "crm_service"
        
        if network_server_path:
            self.network_server_path = Path(network_server_path)
        else:
            # Default: ../network_diagnostic_service from chatbot_core root
            self.network_server_path = Path(__file__).parent.parent.parent.parent / "network_diagnostic_service"
        
        # MCP clients
        self.crm_client = None
        self.network_client = None
        
        # Connection state
        self.is_initialized = False
        
        # Statistics
        self.tool_calls = []
        self.total_calls = 0
        self.failed_calls = 0
        
        logger.info("MCPService created (not connected yet)")
    
    async def initialize(self):
        """
        Initialize MCP connections to servers.
        
        This must be called before using any tool methods.
        Establishes connections to CRM and Network MCP servers.
        """
        if self.is_initialized:
            logger.warning("MCPService already initialized")
            return
        
        try:
            logger.info("Initializing MCP connections...")
            
            # Initialize CRM client
            logger.info(f"Connecting to CRM service at {self.crm_server_path}")
            self.crm_client = CustomMCPClient(self.crm_server_path, "CRM")
            await self.crm_client.initialize()
            logger.info("SUCCESS: CRM service connected")
            
            # Initialize Network client
            logger.info(f"Connecting to Network service at {self.network_server_path}")
            self.network_client = CustomMCPClient(self.network_server_path, "Network")
            await self.network_client.initialize()
            logger.info("SUCCESS: Network service connected")
            
            self.is_initialized = True
            logger.info("SUCCESS: MCPService fully initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP connections: {e}", exc_info=True)
            # Cleanup on failure
            await self._cleanup_connections()
            raise RuntimeError(f"MCP initialization failed: {e}")
    
    async def close(self):
        """Close MCP connections gracefully."""
        logger.info("Closing MCP connections...")
        await self._cleanup_connections()
        logger.info("SUCCESS: MCP connections closed")
    
    async def _cleanup_connections(self):
        """Internal cleanup of MCP connections."""
        if self.crm_client:
            try:
                await self.crm_client.close()
            except Exception as e:
                logger.warning(f"Error closing CRM connection: {e}")
            finally:
                self.crm_client = None
        
        if self.network_client:
            try:
                await self.network_client.close()
            except Exception as e:
                logger.warning(f"Error closing Network connection: {e}")
            finally:
                self.network_client = None
        
        self.is_initialized = False
    
    def _check_initialized(self):
        """Check if service is initialized."""
        if not self.is_initialized:
            raise RuntimeError("MCPService not initialized. Call await mcp_service.initialize() first.")
    
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
        self._check_initialized()
        
        logger.info(f"Calling CRM tool: {tool_name} with args: {arguments}")
        
        try:
            result = await self.crm_client.call_tool(tool_name, arguments)
            
            # Log the call
            self._log_tool_call(MCPServerType.CRM, tool_name, arguments, result, success=True)
            
            logger.info(f"CRM tool {tool_name} completed successfully")
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
        self._check_initialized()
        
        logger.info(f"Calling Network tool: {tool_name} with args: {arguments}")
        
        try:
            result = await self.network_client.call_tool(tool_name, arguments)
            
            # Log the call
            self._log_tool_call(MCPServerType.NETWORK, tool_name, arguments, result, success=True)
            
            logger.info(f"Network tool {tool_name} completed successfully")
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
            "recent_calls": len(self.tool_calls),
            "is_initialized": self.is_initialized
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
    crm_server_path: Optional[str] = None,
    network_server_path: Optional[str] = None
) -> MCPService:
    """
    Get or create MCPService singleton instance.
    
    Note: You must call await mcp_service.initialize() before using.
    
    Args:
        crm_server_path: CRM server path (only used on first call)
        network_server_path: Network server path (only used on first call)
        
    Returns:
        MCPService instance (not yet initialized)
    """
    global _mcp_service
    
    if _mcp_service is None:
        _mcp_service = MCPService(
            crm_server_path=crm_server_path,
            network_server_path=network_server_path
        )
    
    return _mcp_service


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_mcp():
        """Test MCP service."""
        print("Creating MCP service...")
        mcp = MCPService()
        
        try:
            print("Initializing connections...")
            await mcp.initialize()
            
            print("\n" + "="*60)
            print("Testing CRM tool: lookup_customer_by_address")
            print("="*60)
            result = await mcp.call_crm_tool("lookup_customer_by_address", {
                "city": "Šiauliai",
                "street": "Tilžės g.",
                "house_number": "60"
            })
            print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            print("\n" + "="*60)
            print("Testing Network tool: check_port_status")
            print("="*60)
            result = await mcp.call_network_tool("check_port_status", {
                "customer_id": "1"
            })
            print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            print("\n" + "="*60)
            print("Statistics")
            print("="*60)
            stats = mcp.get_statistics()
            for key, value in stats.items():
                print(f"  {key}: {value}")
            
            print("\n" + "="*60)
            print("Recent calls")
            print("="*60)
            recent = mcp.get_recent_calls(limit=5)
            for call in recent:
                print(f"  {call['timestamp']} - {call['tool_name']} - Success: {call['success']}")
            
        finally:
            # Always close connections
            print("\nClosing connections...")
            await mcp.close()
            print("SUCCESS: Test completed")
    
    asyncio.run(test_mcp())

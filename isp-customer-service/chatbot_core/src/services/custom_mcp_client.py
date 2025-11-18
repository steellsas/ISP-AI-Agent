"""
Custom MCP Client
Bypasses MCP SDK ClientSession.initialize() bug on Windows
Uses direct subprocess communication (which we know works!)
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class CustomMCPClient:
    """Custom MCP client using direct subprocess communication."""
    
    def __init__(self, server_path: Path, server_name: str):
        """
        Initialize custom MCP client.
        
        Args:
            server_path: Path to MCP server directory
            server_name: Name for logging (e.g., "crm", "network")
        """
        self.server_path = server_path
        self.server_name = server_name
        self.process = None
        self.next_id = 1
        self.initialized = False
        
    async def initialize(self):
        """Start MCP server and initialize connection."""
        logger.info(f"Starting {self.server_name} MCP server...")
        
        # Set unbuffered environment
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        # Determine module name based on server
        if "crm" in self.server_name.lower():
            module_name = "crm_mcp.server"
        elif "network" in self.server_name.lower():
            module_name = "network_diagnostic_mcp.server"
        else:
            # Fallback to old name (shouldn't happen)
            module_name = "mcp_server.server"
        
        # Start subprocess
        self.process = await asyncio.create_subprocess_exec(
            "uv",
            "--directory", str(self.server_path),
            "run", "python", "-m", module_name,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        logger.info(f"{self.server_name} server started, PID: {self.process.pid}")
        
        # Wait for server to start
        await asyncio.sleep(2)
        
        # Check if process is still running
        if self.process.returncode is not None:
            # Process crashed, read stderr
            stderr = await self.process.stderr.read()
            stderr_text = stderr.decode() if stderr else "(no stderr)"
            raise RuntimeError(
                f"{self.server_name} server process crashed immediately.\n"
                f"Exit code: {self.process.returncode}\n"
                f"Stderr: {stderr_text}"
            )
        
        logger.info(f"{self.server_name} server process is running")
        
        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "custom-mcp-client",
                    "version": "1.0.0"
                }
            }
        }
        
        response = await self._send_request(init_request)
        
        if response and "result" in response:
            self.initialized = True
            logger.info(f"✓ {self.server_name} server initialized")
            logger.info(f"  Server: {response['result'].get('serverInfo', {}).get('name')}")
            return response["result"]
        else:
            raise RuntimeError(f"Failed to initialize {self.server_name} server")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call MCP tool.
        
        Args:
            tool_name: Tool name
            arguments: Tool arguments
            
        Returns:
            Tool result dictionary
        """
        if not self.initialized:
            raise RuntimeError(f"{self.server_name} client not initialized")
        
        logger.info(f"Calling {self.server_name} tool: {tool_name}")
        
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        response = await self._send_request(request)
        
        if response and "result" in response:
            # Parse result content
            result = response["result"]
            if "content" in result and len(result["content"]) > 0:
                content = result["content"][0]
                if "text" in content:
                    text = content["text"]
                    # Try to parse as JSON
                    try:
                        parsed = json.loads(text)
                        return parsed
                    except json.JSONDecodeError:
                        # Try eval for Python dict strings (fallback)
                        try:
                            import ast
                            parsed = ast.literal_eval(text)
                            return parsed
                        except:
                            return {"success": True, "result": text}
            return {"success": True, "result": result}
        elif response and "error" in response:
            error = response["error"]
            return {
                "success": False,
                "error": error.get("code"),
                "message": error.get("message")
            }
        else:
            return {
                "success": False,
                "error": "no_response",
                "message": "No response from server"
            }
    
    async def _send_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send JSON-RPC request and get response."""
        if not self.process or self.process.returncode is not None:
            raise RuntimeError(f"{self.server_name} server process not running")
        
        # Send request
        request_json = json.dumps(request) + "\n"
        self.process.stdin.write(request_json.encode())
        await self.process.stdin.drain()
        
        # Read response with timeout
        try:
            response_line = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=10.0
            )
            
            if response_line:
                response_str = response_line.decode().strip()
                return json.loads(response_str)
            else:
                logger.error(f"{self.server_name}: Empty response")
                return None
                
        except asyncio.TimeoutError:
            logger.error(f"{self.server_name}: Response timeout")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"{self.server_name}: Invalid JSON response: {e}")
            return None
    
    def _get_next_id(self) -> int:
        """Get next request ID."""
        request_id = self.next_id
        self.next_id += 1
        return request_id
    
    async def close(self):
        """Close connection and terminate server."""
        if self.process and self.process.returncode is None:
            logger.info(f"Closing {self.server_name} server...")
            self.process.terminate()
            await self.process.wait()
        
        self.process = None
        self.initialized = False
        logger.info(f"✓ {self.server_name} server closed")


# Example usage
if __name__ == "__main__":
    async def test():
        """Test custom MCP client."""
        
        # CRM client - fix path (go up 4 levels to workspace root)
        crm_path = Path(__file__).parent.parent.parent.parent / "crm_service"
        print(f"CRM path: {crm_path}")
        print(f"Path exists: {crm_path.exists()}")
        
        crm = CustomMCPClient(crm_path, "CRM")
        
        try:
            # Initialize
            print("Initializing CRM client...")
            await crm.initialize()
            
            # Call tool
            print("\nCalling lookup_customer_by_address...")
            result = await crm.call_tool("lookup_customer_by_address", {
                "city": "Šiauliai",
                "street": "Tilžės g.",
                "house_number": "60"
            })
            
            print(f"\nResult:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        finally:
            await crm.close()
    
    asyncio.run(test())

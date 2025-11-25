"""Test MCP Tools"""
import asyncio
from src.services.mcp_service import get_mcp_service

async def test_tools():
    mcp = get_mcp_service()
    await mcp.initialize()
    
    # List CRM tools
    print("=== CRM TOOLS ===")
    if mcp.crm_client:
        tools = await mcp.crm_client.list_tools()
        for tool in tools:
            print(f"  • {tool.name}")
    
    await mcp.close()

asyncio.run(test_tools())
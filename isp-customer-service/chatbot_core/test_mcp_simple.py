import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from services.mcp_service import MCPService

async def test():
    mcp = MCPService()
    
    # Enable more logging
    import logging
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    
    try:
        print("Initializing with 15 sec timeout...")
        await asyncio.wait_for(mcp.initialize(), timeout=15.0)
        print("✅ Connected!")
        
        # Try a call
        result = await mcp.call_crm_tool("lookup_customer_by_address", {
            "city": "Šiauliai",
            "street": "Tilžės g.",
            "house_number": "60"
        })
        print(f"Result: {result}")
        
        await mcp.close()
        
    except asyncio.TimeoutError:
        print("❌ Timeout - hanging on connection")
        print("\nCheck if CRM server is running standalone:")
        print("  cd crm_service")
        print("  uv run python -m mcp_server.server")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
asyncio.run(test())
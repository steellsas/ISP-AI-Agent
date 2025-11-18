"""
Test direct subprocess communication
Bypass MCP SDK to see if subprocess stdio works
"""

import asyncio
import json
import sys
from pathlib import Path

async def test_direct_subprocess():
    """Test direct subprocess communication."""
    
    print("="*60)
    print("DIRECT SUBPROCESS TEST")
    print("="*60)
    
    crm_path = Path(__file__).parent.parent / "crm_service"
    
    print(f"\n1. Starting CRM server...")
    print(f"   Path: {crm_path}")
    
    # Start subprocess with unbuffered IO
    import os
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    proc = await asyncio.create_subprocess_exec(
        "uv",
        "--directory", str(crm_path),
        "run", "python", "-m", "mcp_server.server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env
    )
    
    print(f"✅ Process started, PID: {proc.pid}")
    
    # Wait for server to start
    print("\n2. Waiting 2 seconds for server startup...")
    await asyncio.sleep(2)
    
    # Check stderr logs
    print("\n3. Reading server logs (stderr)...")
    try:
        stderr_data = await asyncio.wait_for(
            proc.stderr.read(1024),
            timeout=0.5
        )
        print(f"Server logs:\n{stderr_data.decode()}")
    except asyncio.TimeoutError:
        print("(No stderr yet)")
    
    # Send initialize request
    print("\n4. Sending initialize request...")
    
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "direct-test",
                "version": "1.0.0"
            }
        }
    }
    
    request_json = json.dumps(init_request)
    print(f"Request: {request_json}")
    
    # Write to stdin
    proc.stdin.write(request_json.encode() + b"\n")
    await proc.stdin.drain()
    print(" Request sent and flushed")
    
    # Try to read response
    print("\n5. Reading response (10 second timeout)...")
    
    try:
        response_line = await asyncio.wait_for(
            proc.stdout.readline(),
            timeout=10.0
        )
        
        if response_line:
            response_str = response_line.decode().strip()
            print(f" Got response!")
            print(f"Raw: {response_str}")
            
            try:
                response_json = json.loads(response_str)
                print(f"\n✅ Valid JSON:")
                print(json.dumps(response_json, indent=2))
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON: {e}")
        else:
            print("❌ Empty response")
    
    except asyncio.TimeoutError:
        print("❌ Timeout - no response received")
        
        # Check if process is still running
        if proc.returncode is not None:
            print(f"Process exited with code: {proc.returncode}")
        else:
            print("Process still running but not responding")
    
    # Cleanup
    print("\n6. Cleaning up...")
    proc.terminate()
    await proc.wait()
    print("✅ Done")
    
    print("\n" + "="*60)
    print("TEST COMPLETED")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_direct_subprocess())
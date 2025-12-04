"""
Test MCP Server Protocol
Tests MCP server startup and JSON-RPC communication
"""

import asyncio
import json
import sys
from pathlib import Path


async def test_mcp_server():
    """Test MCP server communication."""

    print("=" * 60)
    print("MCP SERVER PROTOCOL TEST")
    print("=" * 60)

    # Start CRM server as subprocess
    print("\n1. Starting CRM MCP Server subprocess...")

    crm_path = Path(__file__).parent.parent / "crm_service"

    proc = await asyncio.create_subprocess_exec(
        "uv",
        "--directory",
        str(crm_path),
        "run",
        "python",
        "-m",
        "mcp_server.server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    print(f"✅ Process started, PID: {proc.pid}")

    # Wait a bit for server to initialize
    print("\n2. Waiting for server to initialize (2 seconds)...")
    await asyncio.sleep(2)

    # Check if process is still running
    if proc.returncode is not None:
        print(f"❌ Process exited with code: {proc.returncode}")
        stderr = await proc.stderr.read()
        print(f"stderr: {stderr.decode()}")
        return

    print("✅ Server process running")

    # Read stderr (logs)
    print("\n3. Reading server logs (stderr)...")
    try:
        # Non-blocking read of stderr
        stderr_task = asyncio.create_task(proc.stderr.read(1024))
        stderr_data = await asyncio.wait_for(stderr_task, timeout=1.0)
        print(f"Server logs:\n{stderr_data.decode()}")
    except asyncio.TimeoutError:
        print("(No stderr output yet)")

    # Send MCP initialize request
    print("\n4. Sending MCP initialize request...")

    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }

    request_str = json.dumps(init_request) + "\n"
    print(f"Request: {request_str.strip()}")

    proc.stdin.write(request_str.encode())
    await proc.stdin.drain()

    print("✅ Request sent")

    # Read response
    print("\n5. Reading response (10 second timeout)...")

    try:
        response_task = asyncio.create_task(proc.stdout.readline())
        response_line = await asyncio.wait_for(response_task, timeout=10.0)

        if response_line:
            response_str = response_line.decode().strip()
            print(f"Raw response: {response_str}")

            try:
                response_json = json.loads(response_str)
                print(f"\n✅ Valid JSON response:")
                print(json.dumps(response_json, indent=2))

                if response_json.get("id") == 1:
                    print("\n✅ Response ID matches request!")

                if "result" in response_json:
                    print("✅ Initialize successful!")
                    print(f"Server info: {response_json['result'].get('serverInfo')}")

            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON response: {e}")
        else:
            print("❌ No response received")

    except asyncio.TimeoutError:
        print("❌ Timeout waiting for response")

    # Cleanup
    print("\n6. Cleaning up...")
    proc.terminate()
    await proc.wait()
    print("✅ Process terminated")

    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_mcp_server())

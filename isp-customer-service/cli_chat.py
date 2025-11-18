#!/usr/bin/env python3
"""CLI Chat Interface for ISP Customer Service Bot"""

import sys
import asyncio
from pathlib import Path

# Add paths
chatbot_src = Path(__file__).parent / "chatbot_core" / "src"
shared_src = Path(__file__).parent / "shared" / "src"

for path in [chatbot_src, shared_src]:
    if path.exists():
        sys.path.insert(0, str(path))

from agent.conversation_agent import ConversationAgent
from utils import get_logger

logger = get_logger(__name__)


class CLIChat:
    """Interactive CLI Chat Interface."""
    
    def __init__(self):
        self.agent = None
        self.state = None
        self.debug_mode = False
        self.running = True
        print("=" * 70)
        print("🤖 ISP CUSTOMER SERVICE BOT - CLI")
        print("=" * 70)
    
    async def initialize(self):
        """Initialize agent."""
        print("\n📡 Initializing agent...")
        self.agent = ConversationAgent()
        self.state, greeting = await self.agent.start_conversation()
        print("✅ Agent ready!\n")
        print(f"🤖 Bot: {greeting}")
        print(f"[NODE: {self.state['current_node']}]\n")
        print("💡 Commands: /state /debug /quit /help")
        print("─" * 70 + "\n")
    
    async def run(self):
        """Main chat loop."""
        while self.running:
            try:
                user_input = input("👤 You: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.startswith("/"):
                    await self._handle_command(user_input)
                    continue
                
                # Process message
                node_before = self.state['current_node']
                self.state, response = await self.agent.process_message(self.state, user_input)
                node_after = self.state['current_node']
                
                if self.debug_mode and node_before != node_after:
                    print(f"  🔄 {node_before} → {node_after}")
                
                print(f"\n🤖 Bot: {response}")
                print(f"[NODE: {node_after}]\n")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
    
    async def _handle_command(self, cmd):
        """Handle commands."""
        if cmd == "/quit":
            self.running = False
            print("\n👋 Goodbye!")
        
        elif cmd == "/state":
            print("\n📊 STATE:")
            print(f"  Node: {self.state['current_node']}")
            print(f"  Customer ID: {self.state['customer_identified']}")
            print(f"  Problem ID: {self.state['problem_identified']}")
            print(f"  Messages: {len(self.state['messages'])}\n")
        
        elif cmd == "/debug":
            self.debug_mode = not self.debug_mode
            print(f"\n🔧 Debug: {'ON' if self.debug_mode else 'OFF'}\n")
        
        elif cmd == "/help":
            print("\n📖 COMMANDS:")
            print("  /state  - Show state")
            print("  /debug  - Toggle debug")
            print("  /quit   - Exit")
            print("  /help   - This help\n")
        
        else:
            print(f"❌ Unknown: {cmd}\n")
    
    async def cleanup(self):
        """Cleanup."""
        print("\n🔄 Closing...")
        if self.agent:
            await self.agent.close()
        print("✅ Done!")


async def main():
    cli = CLIChat()
    try:
        await cli.initialize()
        await cli.run()
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await cli.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
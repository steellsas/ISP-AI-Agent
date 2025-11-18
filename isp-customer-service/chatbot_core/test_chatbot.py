#!/usr/bin/env python3
"""
ISP Chatbot Interactive Tester
Paleisti iš: isp-customer-service/chatbot_core/

USAGE:
    cd C:/path/to/isp-customer-service/chatbot_core
    python test_chatbot.py
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Setup paths relative to chatbot_core
SCRIPT_DIR = Path(__file__).parent.resolve()
CHATBOT_SRC = SCRIPT_DIR / "src"
SHARED_SRC = SCRIPT_DIR.parent / "shared" / "src"

print("=" * 70)
print("🤖 ISP CHATBOT INTERACTIVE TESTER")
print("=" * 70)
print()
print(f"📁 Script location: {SCRIPT_DIR}")
print(f"📁 Chatbot src: {CHATBOT_SRC}")
print(f"📁 Shared src: {SHARED_SRC}")
print()

# Add to Python path
for path in [CHATBOT_SRC, SHARED_SRC]:
    if path.exists():
        sys.path.insert(0, str(path))
        print(f"✅ Added to path: {path}")
    else:
        print(f"⚠️  Not found: {path}")

print()

# Import after path setup
try:
    from graph.workflow import ISPSupportWorkflow
    from graph.state import create_initial_state, add_message
    from services.mcp_service import MCPService
    from utils import get_logger, get_config
    
    logger = get_logger(__name__)
    print("✅ Imports successful!")
    print()
    
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print()
    print("Troubleshooting:")
    print("1. Make sure you're running from chatbot_core directory")
    print("2. Check that all files exist:")
    print(f"   - {CHATBOT_SRC / 'graph' / 'workflow.py'}")
    print(f"   - {CHATBOT_SRC / 'services' / 'mcp_service.py'}")
    print(f"   - {SHARED_SRC / 'utils' / '__init__.py'}")
    input("\nPress Enter to exit...")
    sys.exit(1)


class ChatbotTester:
    """Interactive chatbot tester."""
    
    def __init__(self):
        self.workflow = None
        self.mcp_service = None
        self.state = None
        self.running = True
        self.debug_mode = False
        
    async def initialize(self):
        """Initialize all services."""
        print("📡 Initializing services...")
        print()
        
        try:
            # Load config (gets OpenAI key from .env)
            config = get_config()
            if not config.openai_api_key:
                print("❌ OpenAI API key not found!")
                print("   Make sure .env file exists with OPENAI_API_KEY")
                raise ValueError("Missing OPENAI_API_KEY")
            
            print(f"✅ Config loaded (API key: {config.openai_api_key[:8]}...)")
            
            # Initialize MCP service
            print("  → Starting MCP servers (CRM + Network)...")
            self.mcp_service = MCPService()
            await self.mcp_service.initialize()
            print("  ✅ MCP services ready")
            
            # Create workflow
            print("  → Building workflow graph...")
            self.workflow = ISPSupportWorkflow()
            print("  ✅ Workflow compiled")
            
            # Create initial state
            conv_id = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            self.state = create_initial_state(conv_id, language="lt")
            print(f"  ✅ Conversation: {conv_id}")
            
            print()
            print("✅ All systems ready!")
            print()
            
        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            logger.error("Init error", exc_info=True)
            raise
    
    async def close(self):
        """Cleanup."""
        if self.mcp_service:
            await self.mcp_service.close()
    
    def show_state(self):
        """Show current state."""
        print("\n" + "=" * 70)
        print("📊 CURRENT STATE")
        print("=" * 70)
        print(f"Conversation ID: {self.state['conversation_id']}")
        print(f"Current Node: {self.state['current_node']}")
        print(f"Language: {self.state['language']}")
        print()
        print(f"✓ Customer Identified: {self.state['customer_identified']}")
        if self.state['customer_identified']:
            cust = self.state['customer']
            print(f"  - Name: {cust.get('first_name', '')} {cust.get('last_name', '')}")
            print(f"  - ID: {cust.get('customer_id', 'N/A')}")
        
        print(f"✓ Problem Identified: {self.state['problem_identified']}")
        if self.state['problem_identified']:
            prob = self.state['problem']
            print(f"  - Type: {prob.get('problem_type', 'N/A')}")
            print(f"  - Category: {prob.get('category', 'N/A')}")
        
        print()
        print(f"Diagnostics Done: {self.state['diagnostics_completed']}")
        print(f"Troubleshooting: {self.state['troubleshooting_attempted']}")
        print(f"Ticket Created: {self.state['ticket_created']}")
        print(f"Ended: {self.state['conversation_ended']}")
        print()
        print(f"Total Messages: {len(self.state['messages'])}")
        print(f"Tool Calls: {len(self.state['tool_calls'])}")
        print("=" * 70 + "\n")
    
    def show_history(self, limit=10):
        """Show conversation history."""
        print(f"\n📜 Last {limit} messages:")
        print("─" * 70)
        
        for msg in self.state['messages'][-limit:]:
            role = "👤 You" if msg['role'] == 'user' else "🤖 Bot"
            content = msg['content']
            
            # Truncate long messages
            if len(content) > 150:
                content = content[:150] + "..."
            
            print(f"\n{role}:")
            print(f"  {content}")
        
        print("\n" + "─" * 70 + "\n")
    
    async def process_message(self, user_input: str):
        """Process user message through workflow."""
        
        # Add user message
        add_message(self.state, "user", user_input)
        
        # Get current node BEFORE processing
        current_node = self.state['current_node']
        
        if self.debug_mode:
            print(f"  🔧 Processing in node: {current_node}")
        
        try:
            # Import node functions
            from graph.nodes.greeting import greeting_node
            from graph.nodes.customer_identification import customer_identification_node
            from graph.nodes.problem_identification import problem_identification_node
            from graph.nodes.diagnostics import diagnostics_node
            from graph.nodes.troubleshooting import troubleshooting_node
            from graph.nodes.ticket_registration import ticket_registration_node
            from graph.nodes.resolution import resolution_node
            
            # Node mapping
            nodes = {
                'greeting': customer_identification_node,  # After greeting, go to customer_identification
                'customer_identification': customer_identification_node,
                'problem_identification': problem_identification_node,
                'diagnostics': diagnostics_node,
                'troubleshooting': troubleshooting_node,
                'ticket_registration': ticket_registration_node,
                'resolution': resolution_node
            }
            
            # Execute appropriate node
            if current_node in nodes:
                node_before = current_node
                self.state = nodes[current_node](self.state)
                node_after = self.state['current_node']
                
                if self.debug_mode and node_before != node_after:
                    print(f"  🔄 Transition: {node_before} → {node_after}")
            
            # Get bot response (last assistant message)
            bot_response = None
            for msg in reversed(self.state['messages']):
                if msg['role'] == 'assistant':
                    bot_response = msg['content']
                    break
            
            return bot_response
            
        except Exception as e:
            logger.error(f"Process error: {e}", exc_info=True)
            return f"❌ Error: {e}"
    
    def show_help(self):
        """Show help."""
        print("\n" + "=" * 70)
        print("📖 HELP")
        print("=" * 70)
        print()
        print("Commands:")
        print("  /state     - Show conversation state")
        print("  /history   - Show message history")
        print("  /debug     - Toggle debug mode")
        print("  /reset     - Start new conversation")
        print("  /quit      - Exit")
        print("  /help      - Show this help")
        print()
        print("Workflow Nodes:")
        print("  greeting → customer_identification → problem_identification")
        print("  → diagnostics → troubleshooting → ticket_registration → resolution")
        print()
        print("Example Conversation:")
        print("  You: Šiauliai, Tilžės 60-12")
        print("  Bot: [finds customer]")
        print("  You: Internetas neveikia")
        print("  Bot: [diagnostics + troubleshooting]")
        print("=" * 70 + "\n")
    
    async def run(self):
        """Main chat loop."""
        
        # Initial greeting
        print("🚀 Starting conversation...")
        print()
        
        from graph.nodes.greeting import greeting_node
        self.state = greeting_node(self.state)
        
        # Show greeting
        for msg in self.state['messages']:
            if msg['role'] == 'assistant':
                print(f"🤖 Bot: {msg['content']}")
                break
        
        print(f"[NODE: {self.state['current_node']}]")
        print()
        print("💡 Type /help for commands")
        print("─" * 70)
        print()
        
        # Main loop
        while self.running:
            try:
                user_input = input("👤 You: ").strip()
                
                if not user_input:
                    continue
                
                # Commands
                if user_input.startswith("/"):
                    if user_input == "/quit":
                        print("\n👋 Goodbye!")
                        break
                    
                    elif user_input == "/state":
                        self.show_state()
                        continue
                    
                    elif user_input == "/history":
                        self.show_history()
                        continue
                    
                    elif user_input == "/debug":
                        self.debug_mode = not self.debug_mode
                        print(f"\n🔧 Debug mode: {'ON' if self.debug_mode else 'OFF'}\n")
                        continue
                    
                    elif user_input == "/reset":
                        conv_id = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                        self.state = create_initial_state(conv_id, language="lt")
                        from graph.nodes.greeting import greeting_node
                        self.state = greeting_node(self.state)
                        print("\n🔄 New conversation started\n")
                        for msg in self.state['messages']:
                            if msg['role'] == 'assistant':
                                print(f"🤖 Bot: {msg['content']}")
                                break
                        print(f"[NODE: {self.state['current_node']}]\n")
                        continue
                    
                    elif user_input == "/help":
                        self.show_help()
                        continue
                    
                    else:
                        print(f"❌ Unknown command. Type /help\n")
                        continue
                
                # Process message
                response = await self.process_message(user_input)
                
                if response:
                    print(f"\n🤖 Bot: {response}")
                    print(f"[NODE: {self.state['current_node']}]")
                    print()
                
                # Check if ended
                if self.state['conversation_ended']:
                    print("✅ Conversation completed!")
                    print("   Type /reset to start over or /quit to exit\n")
                
            except KeyboardInterrupt:
                print("\n\n⚠️  Interrupted")
                break
            except EOFError:
                print("\n\n⚠️  EOF")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
                logger.error("Loop error", exc_info=True)


async def main():
    """Main entry point."""
    tester = ChatbotTester()
    
    try:
        await tester.initialize()
        await tester.run()
        
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        logger.error("Fatal error", exc_info=True)
    finally:
        print("\n🔄 Closing connections...")
        await tester.close()
        print("✅ Done!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
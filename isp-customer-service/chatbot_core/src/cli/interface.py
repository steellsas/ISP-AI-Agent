# # """
# # CLI Interface
# # Interactive command-line interface for testing the chatbot
# # """

# # import sys
# # import uuid
# # import asyncio
# # from pathlib import Path
# # from typing import Optional, Dict, Any

# # # Add src to path
# # sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# # from src.graph.workflow import app, get_workflow
# # from src.graph.state import create_initial_state, add_message, get_last_user_message
# # from src.services.llm_service import get_llm_service
# # from src.services.mcp_service import get_mcp_service
# # from src.cli.utils import (
# #     Colors,
# #     print_header,
# #     print_separator,
# #     print_assistant,
# #     print_user,
# #     print_system,
# #     print_error,
# #     print_warning,
# #     print_success,
# #     print_help,
# #     clear_screen,
# #     get_user_input,
# #     confirm,
# #     format_state_info,
# #     format_history
# # )


# # class ChatInterface:
# #     """Interactive CLI chatbot interface."""
    
# #     def __init__(self, phone_number: Optional[str] = None, debug: bool = False):
# #         """
# #         Initialize chat interface.
        
# #         Args:
# #             phone_number: Optional phone number
# #             debug: Enable debug mode
# #         """
# #         self.conversation_id = str(uuid.uuid4())[:8]
# #         self.phone_number = phone_number
# #         self.debug = debug
# #         self.state = None
# #         self.running = False
# #         self.mcp_initialized = False
        
# #         # Initialize workflow
# #         try:
# #             self.workflow = get_workflow()
# #             print_success("Workflow inicializuotas")
# #         except Exception as e:
# #             print_error(f"Nepavyko inicializuoti workflow: {e}")
# #             sys.exit(1)
        
# #         # Initialize services
# #         self.llm = None
# #         self.mcp = None
    
# #     async def initialize_services(self):
# #         """Initialize LLM and MCP services."""
# #         try:
# #             # Initialize LLM service
# #             print_system("Inicializuojama LLM paslauga...")
# #             self.llm = get_llm_service()
# #             print_success("✓ LLM paslauga inicializuota")
            
# #             # Initialize MCP service
# #             print_system("Inicializuojamos MCP paslaugos...")
# #             self.mcp = get_mcp_service()
# #             await self.mcp.initialize()
# #             self.mcp_initialized = True
# #             print_success("✓ MCP paslaugos inicializuotos")
            
# #         except Exception as e:
# #             print_warning(f"MCP inicializacija nepavyko: {e}")
# #             print_warning("Tęsiama be MCP paslaugų (mock režimas)")
# #             self.mcp_initialized = False
    
# #     def initialize_state(self):
# #         """Initialize conversation state."""
# #         self.state = create_initial_state(
# #             conversation_id=self.conversation_id,
# #             phone_number=self.phone_number,
# #             language="lt"
# #         )
        
# #         if self.debug:
# #             print_system(f"State inicializuotas: {self.conversation_id}")
    
# #     def process_command(self, user_input: str) -> bool:
# #         """
# #         Process special commands.
        
# #         Args:
# #             user_input: User input
            
# #         Returns:
# #             True if should exit, False otherwise
# #         """
# #         command = user_input.lower().strip()
        
# #         # Exit commands
# #         if command in ['exit', 'quit', 'q', 'išeiti']:
# #             if confirm("Ar tikrai norite išeiti?", default=False):
# #                 self.running = False
# #                 print_success("Viso gero!")
# #                 return True
# #             return False
        
# #         # Force exit (no cleanup)
# #         if command in ['exit!', 'quit!', 'q!', 'force']:
# #             print_warning("⚡ Priverstinis išėjimas be cleanup...")
# #             import sys
# #             sys.exit(0)
        
# #         # Help
# #         if command in ['help', 'h', '?', 'pagalba']:
# #             print_help()
# #             return False
        
# #         # Clear screen
# #         if command in ['clear', 'cls', 'valyti']:
# #             clear_screen()
# #             print_header()
# #             return False
        
# #         # Show state
# #         if command == 'state':
# #             if self.state:
# #                 print(format_state_info(self.state))
# #             else:
# #                 print_warning("State dar neinicializuotas")
# #             return False
        
# #         # Show history
# #         if command == 'history':
# #             if self.state:
# #                 print(format_history(self.state))
# #             else:
# #                 print_warning("Pokalbio istorija dar tuščia")
# #             return False
        
# #         # Debug toggle
# #         if command.startswith('debug'):
# #             parts = command.split()
# #             if len(parts) > 1:
# #                 if parts[1] == 'on':
# #                     self.debug = True
# #                     print_success("Debug režimas įjungtas")
# #                 elif parts[1] == 'off':
# #                     self.debug = False
# #                     print_success("Debug režimas išjungtas")
# #             else:
# #                 status = "Įjungtas" if self.debug else "Išjungtas"
# #                 print_system(f"Debug režimas: {status}")
# #             return False
        
# #         # Not a command - normal message
# #         return False
    
# #     async def run_workflow_stream(self):
# #         """
# #         Run workflow and stream results.
        
# #         This continues execution from current state.
# #         """
# #         try:
# #             if self.debug:
# #                 print_system("Pradedamas workflow vykdymas...")
# #                 print_system(f"Current node: {self.state.get('current_node')}")
# #                 print_system(f"Waiting for input: {self.state.get('waiting_for_user_input')}")

               
# #                 messages = self.state.get('messages', [])
# #                 print_system(f"Total messages in state: {len(messages)}")
# #                 if messages:
# #                     print_system(f"Last message: {messages[-1].get('role')} - {messages[-1].get('content')[:50]}...")
            
# #             step_count = 0
# #             max_steps = 20
# #             last_assistant_message = None
            
# #             # Stream workflow execution
# #             for step_output in self.workflow.stream(self.state):
# #                 step_count += 1
                
# #                 if step_count > max_steps:
# #                     print_warning("Pasiektas maksimalus žingsnių skaičius")
# #                     break
                
# #                 # Get node name from output
# #                 node_name = list(step_output.keys())[0] if step_output else "unknown"
# #                 node_state = step_output.get(node_name, {})
                
# #                 if self.debug:
# #                     print_system(f"Step {step_count}: {node_name}")
# #                     if node_state:
# #                         print_system(f"  State keys: {list(node_state.keys())}")
                
# #                 # Update state with node output
# #                 self.state.update(node_state)
                
# #                 # Display new assistant messages (avoid duplicates)
# #                 if "messages" in node_state:
# #                     messages = node_state.get("messages", [])
# #                     if messages:
# #                         last_msg = messages[-1]
# #                         if last_msg.get("role") == "assistant":
# #                             content = last_msg.get("content")
# #                             # Only print if this is a new message
# #                             if content and content != last_assistant_message:
# #                                 print_assistant(content)
# #                                 last_assistant_message = content
                
# #                 # Check if waiting for user input
# #                 if self.state.get("waiting_for_user_input"):
# #                     if self.debug:
# #                         print_system("Laukiama vartotojo atsakymo")
# #                     break
                
# #                 # Check if conversation ended
# #                 if self.state.get("conversation_ended"):
# #                     if self.debug:
# #                         print_system("Pokalbis baigtas")
# #                     break
            
# #             if self.debug:
# #                 print_system(f"Workflow baigtas po {step_count} žingsnių")
            
# #         except Exception as e:
# #             print_error(f"Klaida vykdant workflow: {e}")
# #             if self.debug:
# #                 import traceback
# #                 traceback.print_exc()
    
# #     async def run_workflow_step(self, user_message: str):
# #         """
# #         Process user message and run workflow.
        
# #         Args:
# #             user_message: User's message
# #         """
# #         try:
# #             if self.debug:
# #                 print_system(f"Processing message: '{user_message[:50]}...'")
            
# #             # Add user message to state
# #             self.state = add_message(
# #                 self.state,
# #                 role="user",
# #                 content=user_message,
# #                 node=self.state.get("current_node")
# #             )
            
# #             # Reset waiting flag BEFORE streaming
# #             self.state["waiting_for_user_input"] = False
            
# #             if self.debug:
# #                 print_system(f"Message added to state. Total messages: {len(self.state.get('messages', []))}")
            
# #             # Run workflow with UPDATED state
# #             await self.run_workflow_stream()
            
# #         except Exception as e:
# #             print_error(f"Klaida apdorojant žinutę: {e}")
# #             if self.debug:
# #                 import traceback
# #                 traceback.print_exc()
    
# #     async def start_async(self):
# #         """Start the interactive chat (async)."""
# #         self.running = True
        
# #         # Print header
# #         clear_screen()
# #         print_header()
        
# #         print_system("Sveiki! Pradedame pokalbį su ISP pagalbos botu.")
# #         print_system(f"Pokalbio ID: {self.conversation_id}")
        
# #         if self.phone_number:
# #             print_system(f"Telefono numeris: {self.phone_number}")
        
# #         print()
        
# #         # Initialize services
# #         await self.initialize_services()
        
# #         print()
# #         print_system("Įveskite 'help' informacijai arba 'exit' išeiti.")
# #         print_separator()
# #         print()
        
# #         # Initialize state
# #         self.initialize_state()
        
# #         # Run initial greeting
# #         try:
# #             await self.run_workflow_stream()
# #         except Exception as e:
# #             print_error(f"Klaida pradedant pokalbį: {e}")
# #             if self.debug:
# #                 import traceback
# #                 traceback.print_exc()
        
# #         print()
        
# #         # Main loop
# #         try:
# #             while self.running:
# #                 # Get user input
# #                 user_input = get_user_input()
                
# #                 # Handle EOF or keyboard interrupt
# #                 if user_input is None:
# #                     print()
# #                     if confirm("Ar norite išeiti?", default=True):
# #                         print_success("Viso gero!")
# #                         break
# #                     continue
                
# #                 # Skip empty input
# #                 if not user_input:
# #                     continue
                
# #                 # Process commands
# #                 should_exit = self.process_command(user_input)
# #                 if should_exit:
# #                     break
                
# #                 # If it was a command that doesn't exit, skip workflow
# #                 if user_input.lower().strip() in ['help', 'h', '?', 'pagalba', 'state', 'history', 'clear', 'cls', 'valyti'] or user_input.lower().startswith('debug'):
# #                     continue
                
# #                 # Normal message - run workflow
# #                 print()
# #                 await self.run_workflow_step(user_input)
# #                 print()
        
# #         except KeyboardInterrupt:
# #             print()
# #             print_warning("Programa nutraukta (Ctrl+C)")
# #             self.running = False
        
# #         finally:
# #             # Cleanup
# #             await self.cleanup()
    
# #     def start(self):
# #         """Start the interactive chat (sync wrapper)."""
# #         try:
# #             asyncio.run(self.start_async())
# #         except KeyboardInterrupt:
# #             print()
# #             print_warning("Programa nutraukta")
    
# #     async def cleanup(self):
# #         """Cleanup resources with timeout."""
# #         if self.mcp_initialized and self.mcp:
# #             try:
# #                 print_system("Uždaromos MCP paslaugos...")
                
# #                 # Cleanup with timeout
# #                 await asyncio.wait_for(self.mcp.close(), timeout=3.0)
                
# #                 print_success("✓ MCP paslaugos uždarytos")
# #             except asyncio.TimeoutError:
# #                 print_warning("⚠️  MCP timeout - priverstinai uždaroma")
# #             except Exception as e:
# #                 if self.debug:
# #                     print_warning(f"MCP klaida: {e}")
    
# #     def stop(self):
# #         """Stop the chat."""
# #         self.running = False


# # def main():
# #     """Main entry point."""
# #     import argparse
    
# #     parser = argparse.ArgumentParser(description="ISP Chatbot CLI Interface")
# #     parser.add_argument(
# #         "--phone",
# #         type=str,
# #         help="Phone number for customer lookup"
# #     )
# #     parser.add_argument(
# #         "--debug",
# #         action="store_true",
# #         help="Enable debug mode"
# #     )
    
# #     args = parser.parse_args()
    
# #     # Create and start interface
# #     interface = ChatInterface(
# #         phone_number=args.phone,
# #         debug=args.debug
# #     )
    
# #     try:
# #         interface.start()
# #     except KeyboardInterrupt:
# #         print()
# #         print_success("Programa nutraukta. Viso gero!")
# #     except Exception as e:
# #         print_error(f"Netikėta klaida: {e}")
# #         import traceback
# #         traceback.print_exc()
# #         sys.exit(1)


# # if __name__ == "__main__":
# #     main()



# """
# CLI Interface
# Interactive command-line interface for testing the chatbot
# """

# import sys
# import uuid
# import asyncio
# from pathlib import Path
# from typing import Optional, Dict, Any

# # Add src to path
# sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# from src.graph.workflow import app, get_workflow
# from src.graph.state import create_initial_state, add_message, get_last_user_message
# from src.services.llm_service import get_llm_service
# from src.services.mcp_service import get_mcp_service
# from src.cli.utils import (
#     Colors,
#     print_header,
#     print_separator,
#     print_assistant,
#     print_user,
#     print_system,
#     print_error,
#     print_warning,
#     print_success,
#     print_help,
#     clear_screen,
#     get_user_input,
#     confirm,
#     format_state_info,
#     format_history
# )

# # Add shared to path
# shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
# if str(shared_path) not in sys.path:
#     sys.path.insert(0, str(shared_path))

# from utils import  get_config

# # import os
# # from dotenv import load_dotenv

# # # Load environment variables
# # load_dotenv()

# class ChatInterface:
#     """Interactive CLI chatbot interface."""
    
#     def __init__(self, phone_number: Optional[str] = None, debug: bool = False):
#         """
#         Initialize chat interface.
        
#         Args:
#             phone_number: Optional phone number
#             debug: Enable debug mode
#         """
#         # ========== LOAD CONFIGURATION ==========
      
        
#         self.config = get_config()
        
#         # Apply to environment (for LangSmith)
#         self.config.apply_to_environment()
        
#         # Print config status if debug
#         if debug:
#             self.config.print_status(verbose=True)


#         self.conversation_id = str(uuid.uuid4())[:8]
#         self.phone_number = phone_number
#         self.debug = debug
#         self.state = None
#         self.running = False
#         self.mcp_initialized = False
        
#         # Track printed messages to avoid duplicates
#         self.printed_message_ids = set()
        
#         # Initialize workflow
#         try:
#             self.workflow = get_workflow()
#             print_success("Workflow inicializuotas")
#         except Exception as e:
#             print_error(f"Nepavyko inicializuoti workflow: {e}")
#             sys.exit(1)
        
#         # Initialize services
#         self.llm = None
#         self.mcp = None
    
#     async def initialize_services(self):
#         """Initialize LLM and MCP services."""
#         try:
#             # Initialize LLM service
#             print_system("Inicializuojama LLM paslauga...")
#             self.llm = get_llm_service()
#             print_success("✓ LLM paslauga inicializuota")
            
#             # Initialize MCP service
#             print_system("Inicializuojamos MCP paslaugos...")
#             self.mcp = get_mcp_service()
#             await self.mcp.initialize()
#             self.mcp_initialized = True
#             print_success("✓ MCP paslaugos inicializuotos")
            
#         except Exception as e:
#             print_warning(f"MCP inicializacija nepavyko: {e}")
#             print_warning("Tęsiama be MCP paslaugų (mock režimas)")
#             self.mcp_initialized = False
    
#     def initialize_state(self):
#         """Initialize conversation state."""
#         self.state = create_initial_state(
#             conversation_id=self.conversation_id,
#             phone_number=self.phone_number,
#             language="lt"
#         )
        
#         if self.debug:
#             print_system(f"State inicializuotas: {self.conversation_id}")
    
#     def process_command(self, user_input: str) -> bool:
#         """
#         Process special commands.
        
#         Args:
#             user_input: User input
            
#         Returns:
#             True if should exit, False otherwise
#         """
#         command = user_input.lower().strip()
        
#         # Exit commands
#         if command in ['exit', 'quit', 'q', 'išeiti']:
#             if confirm("Ar tikrai norite išeiti?", default=False):
#                 self.running = False
#                 print_success("Viso gero!")
#                 return True
#             return False
        
#         # Force exit (no cleanup)
#         if command in ['exit!', 'quit!', 'q!', 'force']:
#             print_warning("⚡ Priverstinis išėjimas be cleanup...")
#             import sys
#             sys.exit(0)
        
#         # Help
#         if command in ['help', 'h', '?', 'pagalba']:
#             print_help()
#             return False
        
#         # Clear screen
#         if command in ['clear', 'cls', 'valyti']:
#             clear_screen()
#             print_header()
#             return False
        
#         # Show state
#         if command == 'state':
#             if self.state:
#                 print(format_state_info(self.state))
#             else:
#                 print_warning("State dar neinicializuotas")
#             return False
        
#         # Show history
#         if command == 'history':
#             if self.state:
#                 print(format_history(self.state))
#             else:
#                 print_warning("Pokalbio istorija dar tuščia")
#             return False
        
#         # Debug toggle
#         if command.startswith('debug'):
#             parts = command.split()
#             if len(parts) > 1:
#                 if parts[1] == 'on':
#                     self.debug = True
#                     print_success("Debug režimas įjungtas")
#                 elif parts[1] == 'off':
#                     self.debug = False
#                     print_success("Debug režimas išjungtas")
#             else:
#                 status = "Įjungtas" if self.debug else "Išjungtas"
#                 print_system(f"Debug režimas: {status}")
#             return False
        
#         # Not a command - normal message
#         return False
    
#     def _get_message_id(self, message: Dict[str, Any]) -> str:
#         """Generate unique ID for message to avoid duplicate printing."""
#         return f"{message.get('role')}:{message.get('timestamp')}:{message.get('content', '')[:20]}"
    
#     # async def run_workflow_stream(self):
#     #     """
#     #     Run workflow and stream results.
        
#     #     KEY FIX: This continues execution from CURRENT state, not restart.
#     #     """
#     #     try:
#     #         if self.debug:
#     #             print_system("Pradedamas workflow vykdymas...")
#     #             print_system(f"Current node: {self.state.get('current_node')}")
#     #             print_system(f"Waiting for input: {self.state.get('waiting_for_user_input')}")
#     #             messages = self.state.get('messages', [])
#     #             print_system(f"Total messages in state: {len(messages)}")
#     #             if messages:
#     #                 last = messages[-1]
#     #                 print_system(f"Last message: {last.get('role')} - {last.get('content')[:50]}...")
            
#     #         step_count = 0
#     #         max_steps = 20

#     #         # KEY FIX: Use config with thread_id for checkpointing
#     #         config = {
#     #             "configurable": {
#     #                 "thread_id": self.conversation_id  
#     #             }
#     #         }
            

#     #         for step_output in self.workflow.stream(self.state, config=config):
#     #             step_count += 1
                
#     #             if step_count > max_steps:
#     #                 print_warning("Pasiektas maksimalus žingsnių skaičius")
#     #                 break
                
#     #             # Get node name from output
#     #             node_name = list(step_output.keys())[0] if step_output else "unknown"
#     #             node_state = step_output.get(node_name, {})
                
#     #             if self.debug:
#     #                 print_system(f"Step {step_count}: {node_name}")
#     #                 if node_state:
#     #                     print_system(f"  State keys: {list(node_state.keys())}")
                
#     #             # KEY FIX: Properly merge node output into state
#     #             # Use update() to merge, preserving existing keys
#     #             for key, value in node_state.items():
#     #                 if key == "messages":
#     #                     # For messages, use the full list from node output
#     #                     self.state[key] = value
#     #                 else:
#     #                     # For other keys, update
#     #                     self.state[key] = value
                
#     #             # Display new assistant messages (avoid duplicates)
#     #             if "messages" in node_state:
#     #                 messages = node_state.get("messages", [])
#     #                 for msg in messages:
#     #                     if msg.get("role") == "assistant":
#     #                         msg_id = self._get_message_id(msg)
#     #                         if msg_id not in self.printed_message_ids:
#     #                             content = msg.get("content")
#     #                             if content:
#     #                                 print_assistant(content)
#     #                                 self.printed_message_ids.add(msg_id)
                
#     #             # Check if waiting for user input
#     #             if node_state.get("waiting_for_user_input"):
#     #                 if self.debug:
#     #                     print_system("Laukiama vartotojo atsakymo")
#     #                 break
                
#     #             # Check if conversation ended
#     #             if node_state.get("conversation_ended"):
#     #                 if self.debug:
#     #                     print_system("Pokalbis baigtas")
#     #                 self.running = False
#     #                 break
            
#     #         if self.debug:
#     #             print_system(f"Workflow baigtas po {step_count} žingsnių")
            
#     #     except Exception as e:
#     #         print_error(f"Klaida vykdant workflow: {e}")
#     #         if self.debug:
#     #             import traceback
#     #             traceback.print_exc()
#     async def run_workflow_stream(self):
#         """
#         Run workflow using LangGraph with proper checkpointing.
        
#         This uses invoke() with thread_id to properly persist state
#         and continue from where we left off.
#         """
#         try:
#             if self.debug:
#                 print_system("Pradedamas workflow vykdymas...")
#                 print_system(f"Current node: {self.state.get('current_node')}")
#                 print_system(f"Waiting for input: {self.state.get('waiting_for_user_input')}")
#                 print_system(f"Thread ID: {self.conversation_id}")
#                 messages = self.state.get('messages', [])
#                 print_system(f"Total messages in state: {len(messages)}")
            
#             # CRITICAL: Config with thread_id for checkpointing
#             config = {
#                 "configurable": {
#                     "thread_id": self.conversation_id
#                 }
#             }
            
#             step_count = 0
            
#             # Use stream with config to get step-by-step updates
#             async for event in self.workflow.astream(self.state, config=config):
#                 step_count += 1
                
#                 # event is {node_name: output_state}
#                 for node_name, node_state in event.items():
#                     if self.debug:
#                         print_system(f"Step {step_count}: {node_name}")
#                         print_system(f"  State keys: {list(node_state.keys())}")
                    
#                     # Update our local state
#                     self.state.update(node_state)
                    
#                     # Display new assistant messages
#                     if "messages" in node_state:
#                         messages = node_state.get("messages", [])
#                         for msg in messages:
#                             if msg.get("role") == "assistant":
#                                 msg_id = self._get_message_id(msg)
#                                 if msg_id not in self.printed_message_ids:
#                                     content = msg.get("content")
#                                     if content:
#                                         print_assistant(content)
#                                         self.printed_message_ids.add(msg_id)
                    
#                     # Check if waiting for user input
#                     if node_state.get("waiting_for_user_input"):
#                         if self.debug:
#                             print_system("Laukiama vartotojo atsakymo")
#                         break
                    
#                     # Check if conversation ended
#                     if node_state.get("conversation_ended"):
#                         if self.debug:
#                             print_system("Pokalbis baigtas")
#                         self.running = False
#                         break
            
#             if self.debug:
#                 print_system(f"Workflow baigtas po {step_count} žingsnių")
            
#         except Exception as e:
#             print_error(f"Klaida vykdant workflow: {e}")
#             if self.debug:
#                 import traceback
#                 traceback.print_exc()
    
#     async def run_workflow_step(self, user_message: str):
#         """
#         Process user message and run workflow.
        
#         Args:
#             user_message: User's message
#         """
#         try:
#             if self.debug:
#                 print_system(f"Processing message: '{user_message[:50]}...'")
            
#             # KEY FIX 1: Add user message to state
#             self.state = add_message(
#                 self.state,
#                 role="user",
#                 content=user_message,
#                 node=None  # Don't set node for user messages
#             )
            
#             # KEY FIX 2: Reset waiting flag to continue workflow
#             self.state["waiting_for_user_input"] = False
            
#             if self.debug:
#                 print_system(f"Message added to state. Total messages: {len(self.state.get('messages', []))}")
            
#             # KEY FIX 3: Run workflow with UPDATED state
#             await self.run_workflow_stream()
            
#         except Exception as e:
#             print_error(f"Klaida apdorojant žinutę: {e}")
#             if self.debug:
#                 import traceback
#                 traceback.print_exc()
    
#     async def start_async(self):
#         """Start the interactive chat (async)."""
#         self.running = True
        
#         # Print header
#         clear_screen()
#         print_header()
        
#         print_system("Sveiki! Pradedame pokalbį su ISP pagalbos botu.")
#         print_system(f"Pokalbio ID: {self.conversation_id}")
        
#         if self.phone_number:
#             print_system(f"Telefono numeris: {self.phone_number}")
        
#         print()
        
#         # Initialize services
#         await self.initialize_services()
        
#         print()
#         print_system("Įveskite 'help' informacijai arba 'exit' išeiti.")
#         print_separator()
#         print()
        
#         # Initialize state
#         self.initialize_state()
        
#         # Run initial greeting
#         try:
#             await self.run_workflow_stream()
#         except Exception as e:
#             print_error(f"Klaida pradedant pokalbį: {e}")
#             if self.debug:
#                 import traceback
#                 traceback.print_exc()
        
#         print()
        
#         # Main loop
#         try:
#             while self.running:
#                 # Get user input
#                 user_input = get_user_input()
                
#                 # Handle EOF or keyboard interrupt
#                 if user_input is None:
#                     print()
#                     if confirm("Ar norite išeiti?", default=True):
#                         print_success("Viso gero!")
#                         break
#                     continue
                
#                 # Skip empty input
#                 if not user_input:
#                     continue
                
#                 # Process commands
#                 should_exit = self.process_command(user_input)
#                 if should_exit:
#                     break
                
#                 # If it was a command that doesn't exit, skip workflow
#                 if user_input.lower().strip() in ['help', 'h', '?', 'pagalba', 'state', 'history', 'clear', 'cls', 'valyti'] or user_input.lower().startswith('debug'):
#                     continue
                
#                 # Normal message - run workflow
#                 print()
#                 await self.run_workflow_step(user_input)
#                 print()
        
#         except KeyboardInterrupt:
#             print()
#             print_warning("Programa nutraukta (Ctrl+C)")
#             self.running = False
        
#         finally:
#             # Cleanup
#             await self.cleanup()
    
#     def start(self):
#         """Start the interactive chat (sync wrapper)."""
#         try:
#             asyncio.run(self.start_async())
#         except KeyboardInterrupt:
#             print()
#             print_warning("Programa nutraukta")
    
#     async def cleanup(self):
#         """Cleanup resources with timeout."""
#         if self.mcp_initialized and self.mcp:
#             try:
#                 print_system("Uždaromos MCP paslaugos...")
                
#                 # Cleanup with timeout
#                 await asyncio.wait_for(self.mcp.close(), timeout=3.0)
                
#                 print_success("✓ MCP paslaugos uždarytos")
#             except asyncio.TimeoutError:
#                 print_warning("⚠️  MCP timeout - priverstinai uždaroma")
#             except Exception as e:
#                 if self.debug:
#                     print_warning(f"MCP klaida: {e}")
    
#     def stop(self):
#         """Stop the chat."""
#         self.running = False


# def main():
#     """Main entry point."""
#     import argparse
    
#     parser = argparse.ArgumentParser(description="ISP Chatbot CLI Interface")
#     parser.add_argument(
#         "--phone",
#         type=str,
#         help="Phone number for customer lookup"
#     )
#     parser.add_argument(
#         "--debug",
#         action="store_true",
#         help="Enable debug mode"
#     )
    
#     args = parser.parse_args()

#     # Show config and exit

#     # from utils import get_config
#     # config = get_config()
#     # config.print_status(verbose=True)
#     # return   
    
#     # Create and start interface
#     interface = ChatInterface(
#         phone_number=args.phone,
#         debug=args.debug
#     )
    
#     try:
#         interface.start()
#     except KeyboardInterrupt:
#         print()
#         print_success("Programa nutraukta. Viso gero!")
#     except Exception as e:
#         print_error(f"Netikėta klaida: {e}")
#         import traceback
#         traceback.print_exc()
#         sys.exit(1)


# if __name__ == "__main__":
#     main()



"""
CLI Interface
Interactive command-line interface for testing the chatbot
"""

import sys
import uuid
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Add shared to path for config
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from src.graph.workflow import get_workflow
from src.graph.state import create_initial_state
from src.services.llm_service import get_llm_service
from src.services.mcp_service import get_mcp_service
from src.cli.utils import (
    print_header,
    print_separator,
    print_assistant,
    print_system,
    print_error,
    print_warning,
    print_success,
    print_help,
    clear_screen,
    get_user_input,
    confirm,
    format_state_info,
    format_history
)
from utils import get_config


class ChatInterface:
    """Interactive CLI chatbot interface."""
    
    def __init__(self, phone_number: Optional[str] = None, debug: bool = False):
        """
        Initialize chat interface.
        
        Args:
            phone_number: Optional phone number
            debug: Enable debug mode
        """
        # Load and apply configuration
        self.config = get_config()
        self.config.apply_to_environment()
        
        if debug:
            self.config.print_status(verbose=True)
        
        # Initialize conversation
        self.conversation_id = str(uuid.uuid4())[:8]
        self.phone_number = phone_number
        self.debug = debug
        self.state = None
        self.running = False
        self.mcp_initialized = False
        self.printed_message_ids = set()
        
        # Initialize workflow
        try:
            self.workflow = get_workflow()
            if not debug:
                print_success("Workflow inicializuotas")
        except Exception as e:
            print_error(f"Nepavyko inicializuoti workflow: {e}")
            sys.exit(1)
        
        self.llm = None
        self.mcp = None
    
    async def initialize_services(self):
        """Initialize LLM and MCP services."""
        try:
            print_system("Inicializuojama LLM paslauga...")
            self.llm = get_llm_service()
            print_success("✓ LLM paslauga inicializuota")
            
            print_system("Inicializuojamos MCP paslaugos...")
            self.mcp = get_mcp_service()
            await self.mcp.initialize()
            self.mcp_initialized = True
            print_success("✓ MCP paslaugos inicializuotos")
            
        except Exception as e:
            print_warning(f"MCP inicializacija nepavyko: {e}")
            print_warning("Tęsiama be MCP paslaugų")
            self.mcp_initialized = False
    
    def initialize_state(self):
        """Initialize conversation state."""
        self.state = create_initial_state(
            conversation_id=self.conversation_id,
            phone_number=self.phone_number,
            language="lt"
        )
        
        if self.debug:
            print_system(f"State inicializuotas: {self.conversation_id}")
    
    def process_command(self, user_input: str) -> bool:
        """Process special commands. Returns True if should exit."""
        command = user_input.lower().strip()
        
        if command in ['exit', 'quit', 'q', 'išeiti']:
            if confirm("Ar tikrai norite išeiti?", default=False):
                self.running = False
                print_success("Viso gero!")
                return True
            return False
        
        if command in ['exit!', 'quit!', 'q!']:
            print_warning("⚡ Priverstinis išėjimas...")
            sys.exit(0)
        
        if command in ['help', 'h', '?', 'pagalba']:
            print_help()
            return False
        
        if command in ['clear', 'cls', 'valyti']:
            clear_screen()
            print_header()
            return False
        
        if command == 'state':
            if self.state:
                print(format_state_info(self.state))
            else:
                print_warning("State dar neinicializuotas")
            return False
        
        if command == 'history':
            if self.state:
                print(format_history(self.state))
            else:
                print_warning("Pokalbio istorija tuščia")
            return False
        
        if command.startswith('debug'):
            parts = command.split()
            if len(parts) > 1:
                self.debug = (parts[1] == 'on')
                print_success(f"Debug režimas {'įjungtas' if self.debug else 'išjungtas'}")
            else:
                status = "Įjungtas" if self.debug else "Išjungtas"
                print_system(f"Debug režimas: {status}")
            return False
        
        return False
    
    def _get_message_id(self, message: Dict[str, Any]) -> str:
        """Generate unique ID for message."""
        return f"{message.get('role')}:{message.get('timestamp')}:{message.get('content', '')[:20]}"
    
    async def run_workflow(self, input_data: Optional[Dict] = None):
        """
        Run workflow with LangGraph checkpointing.
        
        Args:
            input_data: Optional input (None = continue from checkpoint)
        """
        try:
            if self.debug:
                print_system("Pradedamas workflow vykdymas...")
                print_system(f"Thread ID: {self.conversation_id}")
                if input_data:
                    print_system(f"Input: {list(input_data.keys())}")
                else:
                    print_system("Input: None (using checkpoint)")
            
            # Config with thread_id for checkpointing
            config = {
                "configurable": {
                    "thread_id": self.conversation_id
                }
            }
            
            step_count = 0
            
            # Stream workflow execution
            async for event in self.workflow.astream(input_data, config=config):
                step_count += 1
                
                # event is {node_name: output_state}
                for node_name, node_state in event.items():
                    if self.debug:
                        print_system(f"Step {step_count}: {node_name}")
                        print_system(f"  Keys: {list(node_state.keys())}")
                    
                    # Update local state (for display)
                    self.state.update(node_state)
                    
                    # Display new assistant messages
                    if "messages" in node_state:
                        for msg in node_state["messages"]:
                            if msg.get("role") == "assistant":
                                msg_id = self._get_message_id(msg)
                                if msg_id not in self.printed_message_ids:
                                    content = msg.get("content")
                                    if content:
                                        print_assistant(content)
                                        self.printed_message_ids.add(msg_id)
                    
                    # Check if waiting for user input
                    if node_state.get("waiting_for_user_input"):
                        if self.debug:
                            print_system("Laukiama vartotojo atsakymo")
                        return
                    
                    # Check if conversation ended
                    if node_state.get("conversation_ended"):
                        if self.debug:
                            print_system("Pokalbis baigtas")
                        self.running = False
                        return
            
            if self.debug:
                print_system(f"Workflow baigtas po {step_count} žingsnių")
            
        except Exception as e:
            print_error(f"Klaida vykdant workflow: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
    
    # async def send_user_message(self, message: str):
    #     """Send user message and run workflow."""
    #     try:
    #         if self.debug:
    #             print_system(f"Processing: '{message[:50]}...'")
            
    #         # Create input with user message
    #         # LangGraph will append to checkpoint
    #         import datetime
    #         input_data = {
    #             "messages": [{
    #                 "role": "user",
    #                 "content": message,
    #                 # "timestamp": datetime.datetime.now().isoformat(),
    #                 # "node": None
    #             }]
    #         }
            
    #         # Run workflow with input
    #         await self.run_workflow(input_data)
            
    #     except Exception as e:
    #         print_error(f"Klaida apdorojant žinutę: {e}")
    #         if self.debug:
    #             import traceback
    #             traceback.print_exc()

    async def send_user_message(self, message: str):
        """Send user message and run workflow."""
        try:
            if self.debug:
                print_system(f"Processing: '{message[:50]}...'")
            
            # CRITICAL FIX: Use SIMPLE message format for LangGraph
            # Don't add timestamp/node - LangGraph doesn't expect them
            input_data = {
                "messages": [{
                    "role": "user",
                    "content": message
                }]
            }
            
            # Run workflow with input
            await self.run_workflow(input_data)
            
        except Exception as e:
            print_error(f"Klaida apdorojant žinutę: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
    
    async def start_async(self):
        """Start the interactive chat."""
        self.running = True
        
        # Print header
        clear_screen()
        print_header()
        
        print_system("Sveiki! Pradedame pokalbį su ISP pagalbos botu.")
        print_system(f"Pokalbio ID: {self.conversation_id}")
        
        if self.phone_number:
            print_system(f"Telefono numeris: {self.phone_number}")
        
        print()
        
        # Initialize services
        await self.initialize_services()
        
        print()
        print_system("Įveskite 'help' informacijai arba 'exit' išeiti.")
        print_separator()
        print()
        
        # Initialize state
        self.initialize_state()
        
        # Run initial greeting
        try:
            await self.run_workflow(self.state)
        except Exception as e:
            print_error(f"Klaida pradedant pokalbį: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
        
        print()
        
        # Main loop
        try:
            while self.running:
                user_input = get_user_input()
                
                if user_input is None:
                    print()
                    if confirm("Ar norite išeiti?", default=True):
                        print_success("Viso gero!")
                        break
                    continue
                
                if not user_input:
                    continue
                
                # Process commands
                if self.process_command(user_input):
                    break
                
                # Skip if it was a command
                if user_input.lower().strip() in [
                    'help', 'h', '?', 'pagalba', 'state', 'history',
                    'clear', 'cls', 'valyti'
                ] or user_input.lower().startswith('debug'):
                    continue
                
                # Normal message
                print()
                await self.send_user_message(user_input)
                print()
        
        except KeyboardInterrupt:
            print()
            print_warning("Programa nutraukta (Ctrl+C)")
            self.running = False
        
        finally:
            await self.cleanup()
    
    def start(self):
        """Start the interactive chat (sync wrapper)."""
        try:
            asyncio.run(self.start_async())
        except KeyboardInterrupt:
            print()
            print_warning("Programa nutraukta")
    
    async def cleanup(self):
        """Cleanup resources."""
        if self.mcp_initialized and self.mcp:
            try:
                print_system("Uždaromos MCP paslaugos...")
                await asyncio.wait_for(self.mcp.close(), timeout=3.0)
                print_success("✓ MCP paslaugos uždarytos")
            except asyncio.TimeoutError:
                print_warning("⚠️  MCP timeout")
            except Exception as e:
                if self.debug:
                    print_warning(f"MCP klaida: {e}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ISP Chatbot CLI Interface")
    parser.add_argument("--phone", type=str, help="Phone number")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    parser.add_argument("--show-config", action="store_true", help="Show config and exit")
    
    args = parser.parse_args()
    
    # Show config and exit
    if args.show_config:
        from utils import get_config
        config = get_config()
        config.print_status(verbose=True)
        return
    
    # Create and start interface
    interface = ChatInterface(
        phone_number=args.phone,
        debug=args.debug
    )
    
    try:
        interface.start()
    except KeyboardInterrupt:
        print()
        print_success("Programa nutraukta. Viso gero!")
    except Exception as e:
        print_error(f"Netikėta klaida: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
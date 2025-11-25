#!/usr/bin/env python3
"""
CLI Chat - Test the ISP Support Agent

Usage:
    python cli_chat.py
    
    # With custom phone number:
    python cli_chat.py --phone "+37061234567"
"""

import sys
import uuid
import argparse

# Add src to path
sys.path.insert(0, ".")

from src.graph.graph import get_app
from src.graph.state import create_initial_state, get_last_assistant_message, add_message


def run_chat(phone_number: str = "+37061234567"):
    """
    Run interactive chat session.
    
    Args:
        phone_number: Customer phone number (simulated caller ID)
    """
    print("=" * 50)
    print("ISP Support Agent - CLI Test")
    print("=" * 50)
    print(f"Phone: {phone_number}")
    print("Type 'quit' or 'exit' to end")
    print("Type 'debug' to see current state")
    print("=" * 50)
    print()
    
    # Get compiled app
    app = get_app()
    
    # Create conversation ID and config
    conversation_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": conversation_id}}
    
    # Create initial state
    initial_state = create_initial_state(
        conversation_id=conversation_id,
        phone_number=phone_number
    )
    
    # Run initial invocation (greeting + wait for problem_capture)
    print("[Starting conversation...]")
    print()
    
    result = app.invoke(initial_state, config)
    
    # Print all new assistant messages
    for msg in result.get("messages", []):
        if msg["role"] == "assistant":
            print(f"🤖 Agent: {msg['content']}")
            print()
    
    # Track last message count to detect new messages
    last_msg_count = len(result.get("messages", []))
    
    # Interactive loop
    while True:
        try:
            # Get user input
            user_input = input("👤 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ("quit", "exit", "q"):
                print("\n👋 Viso gero!")
                break
            
            if user_input.lower() == "debug":
                print("\n=== DEBUG STATE ===")
                print(f"  conversation_id: {result.get('conversation_id')}")
                print(f"  current_node: {result.get('current_node')}")
                print(f"  problem_type: {result.get('problem_type')}")
                print(f"  problem_description: {result.get('problem_description')}")
                print(f"  messages count: {len(result.get('messages', []))}")
                print("===================\n")
                continue
            
            # Create user message
            user_message = add_message(
                role="user",
                content=user_input,
                node="user_input"
            )
            
            # Invoke with new user message
            result = app.invoke(
                {"messages": [user_message]},
                config
            )
            
            # Print only NEW assistant messages
            current_messages = result.get("messages", [])
            new_messages = current_messages[last_msg_count:]
            
            for msg in new_messages:
                if msg["role"] == "assistant":
                    print()
                    print(f"🤖 Agent: {msg['content']}")
                    print()
            
            last_msg_count = len(current_messages)
            
            # Check if conversation ended
            if result.get("conversation_ended"):
                print("\n[Conversation ended]")
                break
                
             # Check if provider issue informed
            if result.get("provider_issue_informed"):
                print("\n[Provider issue informed!]")
                diagnostic_results = result.get("diagnostic_results", {})
                issues = diagnostic_results.get("issues_found", [])
                for issue in issues:
                    if issue.get("source") == "provider":
                        print(f"  Issue: {issue.get('type')} - {issue.get('message')}")
                break
            
            # Check if problem resolved (troubleshooting successful)
            if result.get("problem_resolved"):
                print("\n[Problem resolved through troubleshooting!]")
                completed_steps = result.get("troubleshooting_completed_steps", [])
                print(f"  Completed steps: {len(completed_steps)}")
                break
            
            # Check if troubleshooting needs escalation
            if result.get("troubleshooting_needs_escalation"):
                print("\n[Troubleshooting escalated to technician]")
                reason = result.get("troubleshooting_escalation_reason")
                if reason:
                    print(f"  Reason: {reason}")
                completed_steps = result.get("troubleshooting_completed_steps", [])
                print(f"  Completed steps: {len(completed_steps)}")
                break
            
            # Check if address search completed successfully
            if result.get("address_search_successful") is True:
                print("\n[Customer found by address! Continuing to diagnostics...]")
                # Don't break - continue flow
                pass
            
            # Check if address search failed (customer not found)
            if result.get("address_search_successful") is False:
                print("\n[Customer not found by address - conversation ended]")
                break
            # # Check if provider issue informed
            # if result.get("provider_issue_informed"):
            #     print("\n[Provider issue informed!]")
            #     diagnostic_results = result.get("diagnostic_results", {})
            #     issues = diagnostic_results.get("issues_found", [])
            #     for issue in issues:
            #         if issue.get("source") == "provider":
            #             print(f"  Issue: {issue.get('type')} - {issue.get('message')}")
            #     break
            
            # # Check if diagnostics completed and going to troubleshooting
            # if result.get("diagnostics_completed") and not result.get("provider_issue_detected"):
            #     print("\n[Diagnostics complete! Next: troubleshooting (coming soon)]")
            #     print(f"  Needs troubleshooting: {result.get('needs_troubleshooting')}")
            #     issues = result.get("diagnostic_results", {}).get("issues_found", [])
            #     if issues:
            #         print("  Found issues:")
            #         for issue in issues:
            #             print(f"    - {issue.get('type')}: {issue.get('message')}")
            #     break
            
            # # Check if address search completed successfully
            # if result.get("address_search_successful") is True:
            #     print("\n[Customer found by address! Next: diagnostics]")
            #     print(f"  Customer: {result.get('customer_name')}")
            #     # Don't break - continue to diagnostics
            #     pass
            
            # # Check if address search failed (customer not found)
            # if result.get("address_search_successful") is False:
            #     print("\n[Customer not found by address - conversation ended]")
            #     break
            
            # # Check if address search completed successfully
            # if result.get("address_search_successful") is True:
            #     print("\n[Customer found by address! Next: diagnostics (coming soon)]")
            #     print(f"  Customer: {result.get('customer_name')}")
            #     break
            
            # # Check if address search failed (customer not found)
            # if result.get("address_search_successful") is False:
            #     print("\n[Customer not found by address - conversation ended]")
            #     break
            # # Check if provider issue informed
            # if result.get("provider_issue_informed"):
            #     print("\n[Provider issue informed! Conversation can continue or end]")
            #     # Don't break - let user respond
            #     pass
            
            # # Check if diagnostics completed and going to troubleshooting
            # if result.get("diagnostics_completed") and not result.get("provider_issue_detected"):
            #     print("\n[Diagnostics complete! Next: troubleshooting (coming soon)]")
            #     break

        except KeyboardInterrupt:
            print("\n\n👋 Viso gero!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="ISP Support Agent CLI")
    parser.add_argument(
        "--phone", 
        default="+37061234567",
        help="Customer phone number"
    )
    args = parser.parse_args()
    
    try:
        run_chat(phone_number=args.phone)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
"""
CLI Utilities
Helper functions for CLI interface
"""

import sys
from typing import Optional
from colorama import Fore, Back, Style, init

# Initialize colorama for Windows
init(autoreset=True)


class Colors:
    """ANSI color codes."""
    HEADER = Fore.CYAN + Style.BRIGHT
    ASSISTANT = Fore.GREEN
    USER = Fore.YELLOW
    ERROR = Fore.RED + Style.BRIGHT
    WARNING = Fore.YELLOW
    SUCCESS = Fore.GREEN + Style.BRIGHT
    INFO = Fore.BLUE
    DIM = Style.DIM
    RESET = Style.RESET_ALL


def print_header():
    """Print CLI header."""
    print(Colors.HEADER + "=" * 60)
    print("   ISP CUSTOMER SERVICE CHATBOT - CLI INTERFACE")
    print("=" * 60 + Colors.RESET)
    print()


def print_separator(char="-", length=60):
    """Print separator line."""
    print(Colors.DIM + char * length + Colors.RESET)


def print_assistant(message: str):
    """Print assistant message."""
    print(Colors.ASSISTANT + "🤖 Asistentas: " + Colors.RESET + message)


def print_user(message: str):
    """Print user message."""
    print(Colors.USER + "👤 Jūs: " + Colors.RESET + message)


def print_system(message: str):
    """Print system message."""
    print(Colors.INFO + "ℹ️  System: " + Colors.RESET + message)


def print_error(message: str):
    """Print error message."""
    print(Colors.ERROR + "❌ Klaida: " + Colors.RESET + message)


def print_warning(message: str):
    """Print warning message."""
    print(Colors.WARNING + "⚠️  Įspėjimas: " + Colors.RESET + message)


def print_success(message: str):
    """Print success message."""
    print(Colors.SUCCESS + "✅ " + message + Colors.RESET)


def print_help():
    """Print help message."""
    print(Colors.INFO + "\n📋 Komandos:")
    print("  exit, quit, q    - Išeiti iš programos")
    print("  help, h, ?       - Parodyti šią pagalbą")
    print("  clear, cls       - Išvalyti ekraną")
    print("  state            - Parodyti dabartinę būseną")
    print("  history          - Parodyti pokalbio istoriją")
    print("  debug on/off     - Įjungti/išjungti debug režimą")
    print(Colors.RESET)


def clear_screen():
    """Clear terminal screen."""
    import os
    os.system('cls' if os.name == 'nt' else 'clear')


def get_user_input(prompt: str = "Jūs: ") -> Optional[str]:
    """
    Get user input with prompt.
    
    Args:
        prompt: Input prompt
        
    Returns:
        User input or None if EOF
    """
    try:
        user_input = input(Colors.USER + prompt + Colors.RESET)
        return user_input.strip()
    except (EOFError, KeyboardInterrupt):
        print()  # New line
        return None


def confirm(question: str, default: bool = False) -> bool:
    """
    Ask yes/no question.
    
    Args:
        question: Question to ask
        default: Default answer
        
    Returns:
        True if yes, False if no
    """
    default_str = "[T/n]" if default else "[t/N]"
    response = input(Colors.WARNING + f"{question} {default_str}: " + Colors.RESET)
    
    if not response:
        return default
    
    return response.lower() in ['t', 'taip', 'y', 'yes']


def format_state_info(state: dict) -> str:
    """
    Format state information for display.
    
    Args:
        state: Conversation state
        
    Returns:
        Formatted string
    """
    lines = []
    lines.append(Colors.HEADER + "\n📊 DABARTINĖ BŪSENA:" + Colors.RESET)
    lines.append(Colors.DIM + "-" * 60 + Colors.RESET)
    
    # Basic info
    lines.append(f"Pokalbio ID: {state.get('conversation_id')}")
    lines.append(f"Dabartinis node: {state.get('current_node')}")
    lines.append(f"Kalba: {state.get('language')}")
    
    # Customer info
    if state.get('customer_identified'):
        customer = state.get('customer', {})
        lines.append(f"\n👤 Klientas:")
        lines.append(f"   ID: {customer.get('customer_id')}")
        lines.append(f"   Vardas: {customer.get('first_name')} {customer.get('last_name')}")
        lines.append(f"   Telefonas: {customer.get('phone')}")
    
    # Problem info
    if state.get('problem_identified'):
        problem = state.get('problem', {})
        lines.append(f"\n❗ Problema:")
        lines.append(f"   Tipas: {problem.get('problem_type')}")
        lines.append(f"   Aprašymas: {problem.get('description')}")
    
    # Diagnostics
    if state.get('diagnostics_completed'):
        diagnostics = state.get('diagnostics', {})
        lines.append(f"\n🔍 Diagnostika:")
        lines.append(f"   Tiekėjo problema: {'Taip' if diagnostics.get('provider_issue') else 'Ne'}")
    
    lines.append(Colors.DIM + "-" * 60 + Colors.RESET)
    
    return "\n".join(lines)


def format_history(state: dict, max_messages: int = 10) -> str:
    """
    Format conversation history.
    
    Args:
        state: Conversation state
        max_messages: Max messages to show
        
    Returns:
        Formatted string
    """
    messages = state.get('messages', [])
    
    if not messages:
        return Colors.WARNING + "Pokalbio istorija tuščia." + Colors.RESET
    
    lines = []
    lines.append(Colors.HEADER + "\n💬 POKALBIO ISTORIJA:" + Colors.RESET)
    lines.append(Colors.DIM + "-" * 60 + Colors.RESET)
    
    # Show last N messages
    recent_messages = messages[-max_messages:]
    
    for msg in recent_messages:
        role = msg.get('role')
        content = msg.get('content')
        timestamp = msg.get('timestamp', '')
        
        if role == 'user':
            lines.append(f"{Colors.USER}👤 Jūs:{Colors.RESET} {content}")
        elif role == 'assistant':
            lines.append(f"{Colors.ASSISTANT}🤖 Asistentas:{Colors.RESET} {content}")
        else:
            lines.append(f"{Colors.DIM}[{role}]: {content}{Colors.RESET}")
    
    lines.append(Colors.DIM + "-" * 60 + Colors.RESET)
    
    return "\n".join(lines)
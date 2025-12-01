#!/usr/bin/env python3
"""
ISP Customer Service - Quick Setup & Verification Script
========================================================

This script verifies the project structure and runs initial setup
"""

import os
import sys
from pathlib import Path


def check_directory_structure(root_path):
    """Verify all required directories exist"""
    
    required_dirs = [
        "chatbot_core/src/config",
        "chatbot_core/src/graph/nodes",
        "chatbot_core/src/graph/edges",
        "chatbot_core/src/services/llm",
        "chatbot_core/src/rag/knowledge_base/troubleshooting/scenarios",
        "chatbot_core/src/rag/scripts",
        "chatbot_core/src/locales/translations",
        "chatbot_core/src/prompts",
        "chatbot_core/streamlit_ui/components",
        "chatbot_core/tests",
        "crm_service/src/crm_mcp/tools",
        "crm_service/src/repository",
        "crm_service/tests",
        "network_diagnostic_service/src/network_diagnostic_mcp",
        "network_diagnostic_service/src/repository",
        "network_diagnostic_service/tests",
        "shared/src/database",
        "shared/src/isp_types",
        "shared/src/utils",
        "database/schema",
        "database/seeds",
        "database/migrations",
        "scripts",
        "docs",
    ]
    
    missing = []
    for dir_path in required_dirs:
        full_path = os.path.join(root_path, dir_path)
        if not os.path.isdir(full_path):
            missing.append(dir_path)
    
    return missing


def check_core_files(root_path):
    """Verify all critical files exist"""
    
    required_files = [
        "chatbot_core/src/graph/state.py",
        "chatbot_core/src/graph/graph.py",
        "chatbot_core/src/graph/nodes/greeting.py",
        "chatbot_core/src/graph/nodes/problem_capture.py",
        "chatbot_core/src/graph/nodes/phone_lookup.py",
        "chatbot_core/src/graph/nodes/address_confirmation.py",
        "chatbot_core/src/graph/nodes/address_search.py",
        "chatbot_core/src/graph/nodes/diagnostics.py",
        "chatbot_core/src/graph/nodes/troubleshooting.py",
        "chatbot_core/src/graph/nodes/create_ticket.py",
        "chatbot_core/src/graph/nodes/closing.py",
        "chatbot_core/src/services/crm.py",
        "chatbot_core/src/services/network.py",
        "chatbot_core/src/services/llm/llm_service.py",
        "chatbot_core/src/rag/embeddings.py",
        "chatbot_core/src/rag/vector_store.py",
        "chatbot_core/src/rag/retriever.py",
        "chatbot_core/src/rag/scenario_loader.py",
        "chatbot_core/src/config/config.yaml",
        "database/schema/crm_schema.sql",
        "database/schema/network_schema.sql",
        "scripts/setup_db.py",
        "README.md",
        "PROJECT_STRUCTURE.md",
    ]
    
    missing = []
    for file_path in required_files:
        full_path = os.path.join(root_path, file_path)
        if not os.path.isfile(full_path):
            missing.append(file_path)
    
    return missing


def print_status(status_type, message):
    """Print formatted status message"""
    symbols = {
        "✓": "✓",
        "✗": "✗",
        "➜": "➜",
        "⚠": "⚠",
    }
    print(f"{symbols.get(status_type, status_type)} {message}")


def main():
    """Main setup verification"""
    
    root_path = os.path.dirname(os.path.abspath(__file__))
    
    print("=" * 70)
    print("ISP CUSTOMER SERVICE - STRUCTURE VERIFICATION")
    print("=" * 70)
    print()
    
    # Check directories
    print("📁 Checking directory structure...")
    missing_dirs = check_directory_structure(root_path)
    
    if not missing_dirs:
        print_status("✓", "All required directories exist")
    else:
        print_status("✗", f"Missing {len(missing_dirs)} directories:")
        for d in missing_dirs:
            print(f"    - {d}")
    
    print()
    
    # Check files
    print("📄 Checking core files...")
    missing_files = check_core_files(root_path)
    
    if not missing_files:
        print_status("✓", "All core files exist")
    else:
        print_status("✗", f"Missing {len(missing_files)} files:")
        for f in missing_files:
            print(f"    - {f}")
    
    print()
    print("=" * 70)
    print("PROJECT STRUCTURE STATUS")
    print("=" * 70)
    
    if not missing_dirs and not missing_files:
        print_status("✓", "Project structure is complete!")
        print()
        print("Next steps:")
        print("  1. Install dependencies: pip install -r chatbot_core/requirements.txt")
        print("  2. Initialize database: python scripts/setup_db.py")
        print("  3. Set environment variables in .env")
        print("  4. Run tests: pytest chatbot_core/tests/")
        print("  5. Start CLI: python chatbot_core/cli_chat.py --phone '+37060012345'")
        print("  6. Start UI: streamlit run chatbot_core/streamlit_ui/app.py")
    else:
        print_status("✗", "Project structure has issues")
        sys.exit(1)
    
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()

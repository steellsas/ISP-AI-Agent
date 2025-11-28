#!/usr/bin/env python3
"""
RAG System Test Launcher
Quick test of document loading and retrieval

Usage from chatbot_core directory:
    uv run python run_rag_test.py
"""

import sys
from pathlib import Path

# Ensure we're running from chatbot_core directory
if not (Path.cwd() / "src" / "rag").exists():
    print("❌ Error: Please run this script from chatbot_core directory")
    print("   cd chatbot_core")
    print("   uv run python run_rag_test.py")
    sys.exit(1)

# Import and run the test
from src.rag.test_rag_loading import main

if __name__ == "__main__":
    print("🚀 Starting RAG System Test...\n")
    main()

"""
ISP Customer Service Agent Tests

Run all tests:
    cd chatbot_core
    pytest tests/ -v

Run specific test file:
    pytest tests/test_tools.py -v
    pytest tests/test_rag.py -v
    pytest tests/test_agent.py -v

Run with coverage:
    pytest tests/ -v --cov=src

Run only fast tests (no LLM):
    pytest tests/ -v -m "not slow"

Quick smoke test:
    pytest tests/ -v --tb=short -q
"""

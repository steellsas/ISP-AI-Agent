"""
ISP Customer Service Agent tests — by area and function (ROADMAP 3.2/3.4).

Every folder is an area (identification/, problem/, understanding/, diagnosis/, knowledge/,
ticket/, closing/, speaking/, voice/, engine/, tools/, contract/, llm/, observe/); every file
one function. After a run the report lists Area → Function → ✓/✗.

    uv run pytest chatbot_core/tests                    # everything
    uv run pytest -m identification chatbot_core/tests  # one area (its known gaps listed)
    uv run pytest chatbot_core/tests/diagnosis/test_cards.py

See docs/testing/TESTAI_PAGAL_FUNKCIJAS.md.
"""

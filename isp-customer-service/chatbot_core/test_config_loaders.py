#!/usr/bin/env python3
"""
Test Config & Prompt Loaders
Verify that all configuration files load correctly.

Usage:
    cd chatbot_core
    uv run python src/scripts/test_config_loaders.py
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def test_config_loader():
    """Test config_loader module."""
    print("\n" + "=" * 60)
    print("TESTING CONFIG LOADER")
    print("=" * 60)
    
    from src.services.config_loader import (
        load_config,
        get_problem_type_config,
        get_all_problem_types,
        get_context_fields,
        get_context_threshold,
        get_max_questions,
        get_question_priority,
        get_skip_phrases,
        classify_problem_type_by_keywords,
        calculate_context_score,
        get_next_question,
        get_message,
        format_problem_types_list,
        format_context_fields_description,
    )
    
    # Test loading configs
    print("\n1. Loading problem_types.yaml...")
    config = load_config("problem_types")
    print(f"   ✅ Loaded {len(config['problem_types'])} problem types")
    
    print("\n2. Loading messages.yaml...")
    messages = load_config("messages")
    print(f"   ✅ Loaded {len(messages)} message categories")
    
    # Test problem types
    print("\n3. Testing problem types...")
    types = get_all_problem_types()
    print(f"   ✅ Problem types: {types}")
    
    # Test internet config
    print("\n4. Testing internet config...")
    internet_config = get_problem_type_config("internet")
    print(f"   ✅ Display name: {internet_config['display_name']}")
    print(f"   ✅ Keywords: {internet_config['keywords'][:5]}...")
    print(f"   ✅ Context threshold: {get_context_threshold('internet')}%")
    print(f"   ✅ Max questions: {get_max_questions('internet')}")
    
    # Test context fields
    print("\n5. Testing context fields...")
    fields = get_context_fields("internet")
    print(f"   ✅ Fields: {list(fields.keys())}")
    
    # Test question priority
    print("\n6. Testing question priority...")
    priority = get_question_priority("internet")
    print(f"   ✅ Priority: {priority}")
    
    # Test keyword classification
    print("\n7. Testing keyword classification...")
    test_messages = [
        "Neveikia internetas",
        "Televizorius nerodo",
        "Problema su sąskaita",
        "Telefonas neveikia",
    ]
    for msg in test_messages:
        ptype = classify_problem_type_by_keywords(msg)
        print(f"   '{msg}' → {ptype}")
    
    # Test context score calculation
    print("\n8. Testing context score...")
    known_facts = {
        "duration": "nuo vakar",
        "scope": "visi įrenginiai",
        "tried_restart": None,
        "router_lights": None,
        "wifi_visible": None,
    }
    score = calculate_context_score("internet", known_facts)
    print(f"   ✅ Score with duration+scope: {score}%")
    
    known_facts["tried_restart"] = True
    score = calculate_context_score("internet", known_facts)
    print(f"   ✅ Score with +tried_restart: {score}%")
    
    # Test get next question
    print("\n9. Testing get_next_question...")
    known = {"duration": "nuo ryto", "scope": None}
    next_q = get_next_question("internet", known)
    print(f"   ✅ Next question field: {next_q['field']}")
    print(f"   ✅ Question: {next_q['question']}")
    
    # Test messages
    print("\n10. Testing messages...")
    greeting = get_message("greeting", "welcome", agent_name="Andrius")
    print(f"   ✅ Greeting: {greeting[:50]}...")
    
    ack = get_message("problem_capture", "initial_acknowledgment", problem_type="internet")
    print(f"   ✅ Acknowledgment (internet): {ack}")
    
    # Test formatting for prompts
    print("\n11. Testing prompt formatting...")
    types_list = format_problem_types_list()
    print(f"   ✅ Problem types list:\n{types_list[:200]}...")
    
    fields_desc = format_context_fields_description("internet")
    print(f"   ✅ Context fields description:\n{fields_desc[:200]}...")
    
    print("\n" + "=" * 60)
    print("✅ CONFIG LOADER TESTS PASSED")
    print("=" * 60)


def test_prompt_loader():
    """Test prompt_loader module."""
    print("\n" + "=" * 60)
    print("TESTING PROMPT LOADER")
    print("=" * 60)
    
    from src.services.prompt_loader import (
        load_prompt_template,
        get_prompt,
        get_system_persona,
        build_conversation_history,
        list_available_prompts,
    )
    
    # Test loading prompts
    print("\n1. Loading system persona...")
    persona = get_system_persona()
    print(f"   ✅ Loaded ({len(persona)} chars)")
    print(f"   Preview: {persona[:100]}...")
    
    print("\n2. Loading analyze_problem prompt...")
    prompt = load_prompt_template("problem_capture", "analyze_problem")
    print(f"   ✅ Loaded ({len(prompt)} chars)")
    
    # Test formatting
    print("\n3. Testing prompt formatting...")
    formatted = get_prompt(
        "problem_capture", 
        "analyze_problem",
        user_message="neveikia internetas",
        current_problem_type="internet",
        problem_types_list="- internet\n- tv\n- phone",
        context_fields_description="- duration: Nuo kada",
        known_facts_summary="Kol kas nežinoma",
        questions_asked=0,
        max_questions=3,
        conversation_history="Klientas: neveikia internetas",
        question_priority="duration → scope → tried_restart",
        context_threshold=70,
    )
    print(f"   ✅ Formatted prompt ({len(formatted)} chars)")
    
    # Test conversation history
    print("\n4. Testing conversation history builder...")
    messages = [
        {"role": "assistant", "content": "Labas, kuo galiu padėti?"},
        {"role": "user", "content": "Neveikia internetas"},
        {"role": "assistant", "content": "Suprantu. Nuo kada?"},
    ]
    history = build_conversation_history(messages)
    print(f"   ✅ History:\n{history}")
    
    # List available prompts
    print("\n5. Available prompts...")
    prompts = list_available_prompts()
    for category, names in prompts.items():
        print(f"   📁 {category}/")
        for name in names:
            print(f"      ✅ {name}.txt")
    
    print("\n" + "=" * 60)
    print("✅ PROMPT LOADER TESTS PASSED")
    print("=" * 60)


def main():
    """Run all tests."""
    print("\n" + "#" * 60)
    print("#  CONFIG & PROMPT LOADER TESTS")
    print("#" * 60)
    
    try:
        test_config_loader()
        test_prompt_loader()
        
        print("\n" + "#" * 60)
        print("#  ALL TESTS PASSED ✅")
        print("#" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
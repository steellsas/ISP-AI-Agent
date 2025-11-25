"""
Test Runner
Run all workflow tests
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("RUNNING ALL TESTS")
    print("=" * 60)
    
    test_files = [
        "tests/test_routers.py",
        "tests/test_workflow_integration.py"
    ]
    
    for test_file in test_files:
        print(f"\n📝 Running: {test_file}")
        print("-" * 60)
        
        result = pytest.main([test_file, "-v", "-s"])
        
        if result != 0:
            print(f"\n❌ Tests failed in {test_file}")
            return False
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
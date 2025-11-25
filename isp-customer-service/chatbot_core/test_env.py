"""Test environment variables"""
import os
import sys

print("=" * 60)
print("ENVIRONMENT VARIABLES CHECK")
print("=" * 60)

# Check LangSmith
langsmith_vars = {
    "LANGCHAIN_TRACING_V2": os.getenv("LANGCHAIN_TRACING_V2"),
    "LANGCHAIN_API_KEY": os.getenv("LANGCHAIN_API_KEY"),
    "LANGCHAIN_PROJECT": os.getenv("LANGCHAIN_PROJECT"),
    "LANGCHAIN_ENDPOINT": os.getenv("LANGCHAIN_ENDPOINT"),
}

print("\n📊 LangSmith Configuration:")
for key, value in langsmith_vars.items():
    if value:
        # Mask API key for security
        if "API_KEY" in key:
            display_value = value[:8] + "..." if len(value) > 8 else "***"
        else:
            display_value = value
        print(f"  ✅ {key}: {display_value}")
    else:
        print(f"  ❌ {key}: Not set")

# Check OpenAI
openai_key = os.getenv("OPENAI_API_KEY")
if openai_key:
    print(f"\n✅ OPENAI_API_KEY: {openai_key[:8]}...")
else:
    print("\n❌ OPENAI_API_KEY: Not set")

# Check Python env
print(f"\n🐍 Python: {sys.version}")
print(f"📁 Executable: {sys.executable}")

# Check if .env file exists
from pathlib import Path
env_file = Path(__file__).parent / ".env"
print(f"\n📄 .env file: {env_file}")
print(f"   Exists: {env_file.exists()}")
if env_file.exists():
    print(f"   Size: {env_file.stat().st_size} bytes")

print("\n" + "=" * 60)
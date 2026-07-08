from llm.provider import get_provider
import sys

print("Initializing LLM provider...")
try:
    provider = get_provider()
    print(f"Backend: {provider.backend}, Model: {provider.model}")
    print("Generating response...")
    resp = provider.generate("Say hello in one sentence")
    print(f"Response: {resp}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

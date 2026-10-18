"""
llm/provider.py — Unified OpenAI-compatible LLM client

All LLM calls in the project go through this module. The backend is
configured via LLM_BASE_URL which points to either OpenRouter (cloud) or
Ollama (local). Both support the standard chat.completions.create()
interface.

Configuration via .env:
  - LLM_BASE_URL:  https://openrouter.ai/api/v1  (OpenRouter cloud)
                  or http://localhost:11434/v1  (Ollama local)
  - LLM_API_KEY:   OpenRouter real key, or "ollama" for local
  - LLM_MODEL_NAME:meta-llama/llama-3-8b-instruct:free (OpenRouter)
                   or llama3 (Ollama)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


class LLMProvider:
    """Unified interface to OpenAI-compatible LLM backends.

    The provider uses a single OpenAI client configured via
    LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL_NAME environment variables.
    """

    def __init__(self):
        # Validate required environment variables
        self.base_url = os.environ.get("LLM_BASE_URL")
        if not self.base_url:
            raise RuntimeError("LLM_BASE_URL is not set in .env")

        self.api_key = os.environ.get("LLM_API_KEY")
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not set in .env")

        self.model_name = os.environ.get("LLM_MODEL_NAME")
        if not self.model_name:
            raise RuntimeError("LLM_MODEL_NAME is not set in .env")

        # Import and configure OpenAI client with explicit timeout
        from openai import OpenAI
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=120.0  # Explicit timeout to prevent hanging
        )
        print(f"[LLMProvider] Using model {self.model_name} @ {self.base_url}")

    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        """
        Generate a response from the configured LLM backend.

        Args:
            prompt:     The user prompt to send.
            max_tokens: Maximum tokens in the response.

        Returns:
            The generated text.

        Raises:
            RuntimeError: If the call fails.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"LLM API call failed: {e}") from e


# ------------------------------------------------------------------
# Convenience: module-level singleton
# ------------------------------------------------------------------
_default_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Get or create the default LLMProvider singleton."""
    global _default_provider
    if _default_provider is None:
        _default_provider = LLMProvider()
    return _default_provider


if __name__ == "__main__":
    p = LLMProvider()
    print(p.generate("Say hello in one sentence"))
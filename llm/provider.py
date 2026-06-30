"""
llm/provider.py — LLM abstraction layer

All LLM calls in the project go through this module. Switching from
cloud API to local Ollama is a one-line env change: LLM_PROVIDER=ollama

Supported providers:
  - "api"    → Anthropic (claude-sonnet-4-6) or OpenAI (gpt-4o-mini)
  - "ollama" → Local Ollama server (llama3.1)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


class LLMProvider:
    """Unified interface to cloud and local LLM backends."""

    def __init__(self, provider: str | None = None):
        self.provider = provider or os.environ.get("LLM_PROVIDER", "api")

        if self.provider == "api":
            self._init_api()
        elif self.provider == "ollama":
            self._init_ollama()
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------

    def _init_api(self):
        """Set up Anthropic, OpenAI, OpenRouter, or Gemini client based on available keys."""
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        self.gemini_key = os.environ.get("GEMINI_API_KEY")

        # If they put the Gemini key in OPENROUTER_API_KEY, detect it
        if not self.gemini_key and self.openrouter_key and not self.openrouter_key.startswith("sk-or-"):
            self.gemini_key = self.openrouter_key

        if self.api_key:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
            self.backend = "anthropic"
            self.model = "claude-sonnet-4-6"
            print(f"[LLMProvider] Using Anthropic ({self.model})")
        elif self.openai_key:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.openai_key)
            self.backend = "openai"
            self.model = "gpt-4o-mini"
            print(f"[LLMProvider] Using OpenAI ({self.model})")
        elif self.gemini_key:
            import httpx
            self.client = httpx.Client(timeout=60.0)
            self.backend = "gemini"
            self.model = "gemini-2.5-flash"
            print(f"[LLMProvider] Using Gemini ({self.model})")
        elif self.openrouter_key:
            import httpx
            self.client = httpx.Client(timeout=60.0)
            self.backend = "openrouter"
            self.model = "google/gemini-2.5-flash:free"
            print(f"[LLMProvider] Using OpenRouter ({self.model})")
        else:
            self.client = None
            self.backend = None
            print("[LLMProvider] WARNING: No API key found. "
                  "Set ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY in .env")

    def _init_ollama(self):
        """Set up local Ollama client."""
        try:
            import ollama
            self.client = ollama
            self.backend = "ollama"
            self.model = "llama3.1"
            print(f"[LLMProvider] Using Ollama ({self.model})")
        except ImportError:
            raise ImportError(
                "Ollama package not installed. Run: pip install ollama"
            )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        """
        Generate a response from the configured LLM backend.

        Args:
            prompt:     The user prompt to send.
            max_tokens: Maximum tokens in the response.

        Returns:
            The generated text.

        Raises:
            RuntimeError: If no backend is configured or call fails.
        """
        if self.provider == "api":
            return self._generate_api(prompt, max_tokens)
        elif self.provider == "ollama":
            return self._generate_ollama(prompt)
        else:
            raise RuntimeError(f"No generation method for provider: {self.provider}")

    def _generate_api(self, prompt: str, max_tokens: int) -> str:
        """Call Anthropic, OpenAI, OpenRouter, or Gemini API."""
        if self.client is None:
            raise RuntimeError(
                "No API key configured. Set ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY in your .env file."
            )

        if self.backend == "anthropic":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        elif self.backend == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content

        elif self.backend == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.3
                }
            }
            response = self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                raise RuntimeError(f"Unexpected Gemini API response format: {data}")

        elif self.backend == "openrouter":
            headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/sofonyas66/red-team-platform",
                "X-Title": "Red Team Planning Platform"
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.3
            }
            response = self.client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    def _generate_ollama(self, prompt: str) -> str:
        """Call local Ollama server."""
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]


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

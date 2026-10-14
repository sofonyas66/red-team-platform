"""
config.py — Centralised environment / secrets configuration for ETHIO-RTAP.

All modules should import from here rather than calling os.getenv directly,
so that the startup guards fire at import time (i.e. before the first request).
"""
import os

ENV = os.getenv("ENV", "development")

# ── Postgres ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

# ── Neo4j ─────────────────────────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme")  # dev-only fallback

# ── Auth ──────────────────────────────────────────────────────────────────
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

# ── LLM Provider / API Keys (install-time prompts) ─────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # gemini / ollama
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # Gemini via OpenRouter
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")  # Ollama offline
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ── CORS ──────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

# ── Startup guards (non-development only) ─────────────────────────────────
if ENV != "development":
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY must be set outside development environments"
        )
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL must be set outside development environments"
        )

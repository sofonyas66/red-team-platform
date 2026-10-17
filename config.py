"""
config.py — Centralised environment / secrets configuration for ETHIO-RTAP.

All modules should import from here rather than calling os.getenv directly,
so that the startup guards fire at import time (i.e. before the first request).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

ENV = os.getenv("ENV", "development")

# ── Postgres ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

# ── Neo4j ─────────────────────────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme")  # dev-only fallback

# ── Auth ──────────────────────────────────────────────────────────────────
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

# ── LLM Provider (OpenAI-compatible interface) ────────────────────────────
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME")

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

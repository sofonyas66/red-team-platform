#!/usr/bin/env python3
"""
Verify that importing the API modules does NOT require torch/sentence-transformers.
We mock out the heavy deps as unimportable, then check the import chain.
"""
import sys
import types
import os
import importlib.util
import pathlib

# ── Simulate ML packages being absent ─────────────────────────────────────
for mod in ["torch", "torch.nn", "torch.nn.functional", "torch_geometric",
            "torch_geometric.nn", "sentence_transformers"]:
    sys.modules[mod] = None  # type: ignore

# ── Stub out heavy infra packages so we don't need live services ──────────
class _FakeModule(types.ModuleType):
    def __getattr__(self, name):
        return _FakeModule(name)
    def __call__(self, *a, **kw):
        return _FakeModule("instance")
    def __iter__(self):
        return iter([])
    def __bool__(self):
        return True

for mod in [
    "neo4j", "neo4j.exceptions",
    "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.ext",
    "sqlalchemy.ext.declarative", "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
    "alembic",
    "passlib", "passlib.context",
    "jose", "jose.jwt", "jose.exceptions",
    "qdrant_client", "qdrant_client.models",
    "slowapi", "slowapi.util", "slowapi.errors",
    "fastapi", "fastapi.middleware", "fastapi.middleware.cors",
    "fastapi.responses", "fastapi.security",
    "pydantic",
    "uvicorn",
]:
    sys.modules[mod] = _FakeModule(mod)

os.environ.setdefault("ENV", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test")

errors = []

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, pathlib.Path(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# 1. gnn/model.py
try:
    mod_model = load("gnn.model", "gnn/model.py")
    assert hasattr(mod_model, "get_path_gat_class"), "missing get_path_gat_class"
    assert not hasattr(mod_model, "PathGAT"), "PathGAT should NOT be a top-level name"
    print("PASS  gnn/model.py imports without torch")
except Exception as e:
    errors.append(f"FAIL  gnn/model.py: {e}")
    print(errors[-1])
    mod_model = _FakeModule("gnn.model")
    sys.modules["gnn.model"] = mod_model

# 2. gnn/init_gat.py
try:
    # graph.connection needs to be stubbed
    sys.modules.setdefault("graph", _FakeModule("graph"))
    sys.modules.setdefault("graph.connection", _FakeModule("graph.connection"))
    mod_init = load("gnn.init_gat", "gnn/init_gat.py")
    print("PASS  gnn/init_gat.py imports without torch")
except Exception as e:
    errors.append(f"FAIL  gnn/init_gat.py: {e}")
    print(errors[-1])
    mod_init = _FakeModule("gnn.init_gat")
    sys.modules["gnn.init_gat"] = mod_init

# 3. llm/rag.py
try:
    sys.modules.setdefault("llm", _FakeModule("llm"))
    mod_rag = load("llm.rag", "llm/rag.py")
    assert hasattr(mod_rag, "_get_encoder"), "missing _get_encoder"
    print("PASS  llm/rag.py imports without sentence_transformers")
except Exception as e:
    errors.append(f"FAIL  llm/rag.py: {e}")
    print(errors[-1])
    mod_rag = _FakeModule("llm.rag")
    sys.modules["llm.rag"] = mod_rag

# 4. llm/planner.py
try:
    sys.modules.setdefault("llm.provider", _FakeModule("llm.provider"))
    mod_planner = load("llm.planner", "llm/planner.py")
    print("PASS  llm/planner.py imports without ML stack")
except Exception as e:
    errors.append(f"FAIL  llm/planner.py: {e}")
    print(errors[-1])

print()
if errors:
    print(f"RESULT: {len(errors)} failure(s)")
    sys.exit(1)
else:
    print("RESULT: all lazy-import checks passed")
    sys.exit(0)

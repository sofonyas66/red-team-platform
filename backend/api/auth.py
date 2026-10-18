"""
api/auth.py — JWT Authentication backed by Postgres (SQLAlchemy).

Token payload includes: sub (user UUID), org_id, role.
Every authenticated request resolves tenant scope from the token — no
per-request Postgres round-trip needed for org_id.
"""
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from config import DATABASE_URL, JWT_SECRET_KEY, ENV, _sync_url
from db.models import User as UserModel

# ── Crypto ────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── JWT config ────────────────────────────────────────────────────────────
# In development, fall back to a local dev secret so the app still starts
# without a .env file.  In any other ENV the config module already raised
# RuntimeError if JWT_SECRET_KEY is unset.
SECRET_KEY: str = JWT_SECRET_KEY or "dev-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

security = HTTPBearer(auto_error=False)

# ── SQLAlchemy sync engine (used only for auth lookups) ───────────────────
# Use the shared sync URL from config
_engine = create_engine(_sync_url, pool_pre_ping=True) if _sync_url else None


def _get_db_session() -> Session:
    if _engine is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    return Session(_engine)


# ── Pydantic models ───────────────────────────────────────────────────────

class TokenData(BaseModel):
    sub: str          # user UUID
    org_id: str
    role: str


class AuthenticatedUser(BaseModel):
    id: str
    org_id: str
    role: str


# ── Token helpers ─────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        org_id = payload.get("org_id")
        role = payload.get("role")
        if not sub or not org_id or not role:
            raise HTTPException(status_code=401, detail="Invalid token claims")
        return TokenData(sub=sub, org_id=org_id, role=role)
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Auth helpers ──────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(email: str, password: str) -> UserModel:
    """Look up user by email, verify bcrypt password. Raises 401 on failure."""
    with _get_db_session() as db:
        stmt = select(UserModel).where(UserModel.email == email, UserModel.is_active == True)  # noqa: E712
        user = db.execute(stmt).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user


# ── FastAPI dependencies ──────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token_data = decode_token(credentials.credentials)
    return AuthenticatedUser(id=token_data.sub, org_id=token_data.org_id, role=token_data.role)


def require_roles(*allowed_roles: str):
    """Dependency factory for role-based access control."""
    async def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker


async def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[AuthenticatedUser]:
    """Auth that doesn't raise if missing (for public endpoints with optional auth)."""
    if credentials is None:
        return None
    try:
        token_data = decode_token(credentials.credentials)
        return AuthenticatedUser(id=token_data.sub, org_id=token_data.org_id, role=token_data.role)
    except HTTPException:
        return None


# ── Public paths (no auth required) ──────────────────────────────────────
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/auth/login", "/auth/logout"}

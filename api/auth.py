"""
api/auth.py — JWT Authentication for production API
"""
import os
import time
from typing import Optional
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
from jwt.exceptions import PyJWTError

# In production, load from environment/secrets manager
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

security = HTTPBearer(auto_error=False)

class TokenData(BaseModel):
    username: str
    roles: list[str] = []

class User(BaseModel):
    username: str
    roles: list[str] = []

# Simple user store (in production: database/LDAP)
USERS_DB = {
    "admin": {"password_hash": "$2b$12$dummy", "roles": ["admin", "analyst"]},
    "analyst": {"password_hash": "$2b$12$dummy", "roles": ["analyst"]},
}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        roles: list = payload.get("roles", [])
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return TokenData(username=username, roles=roles)
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token_data = decode_token(credentials.credentials)
    return User(username=token_data.username, roles=token_data.roles)

def require_roles(*allowed_roles: str):
    """Dependency factory for role-based access control."""
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker

# Public endpoints that don't require auth
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

async def optional_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[User]:
    """Auth that doesn't raise if missing (for public endpoints with optional auth)."""
    if credentials is None:
        return None
    try:
        token_data = decode_token(credentials.credentials)
        return User(username=token_data.username, roles=token_data.roles)
    except HTTPException:
        return None
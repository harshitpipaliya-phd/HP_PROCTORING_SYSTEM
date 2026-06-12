"""
api/routers/auth.py
===================
Authentication endpoints: JWT token issuance.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from jose import jwt

from core.config import get_settings
from api.core.dependencies import ROLES

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    role: str = "proctor"


@router.post("/login")
def login(req: LoginRequest):
    """
    Issue a JWT token for testing/dev purposes.
    In production, replace with proper OAuth2/email+password verification.
    """
    settings = get_settings()
    if not settings.JWT_SECRET_KEY:
        raise HTTPException(status_code=500, detail="JWT_SECRET_KEY not configured on server")

    if req.role not in ROLES.values():
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed: {list(ROLES.values())}")

    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": req.email,
        "email": req.email,
        "role": req.role,
        "iat": now,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "role": req.role,
    }

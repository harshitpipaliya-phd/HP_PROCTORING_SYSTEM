"""
api/core/dependencies.py
=========================
FastAPI dependency injection for auth, DB sessions, and services.

Provides:
- get_db            : Supabase client session (SQLAlchemy-style pattern)
- get_current_user  : JWT + Supabase auth guard
- get_current_admin : Role-based access control for admin endpoints
- get_internal_auth: Internal API key verification for inter-service calls
- verify_hp_webhook : HMAC-SHA256 signature verification for HP webhooks
- get_hp_mapper     : HP webhook mapper service
- get_media_storage : Cloudinary-backed media storage
"""

import os
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from core.config import get_settings

settings = get_settings()
_bearer = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────────────────────────────────────────
# Role-based access control
# ─────────────────────────────────────────────────────────────────────────────

ROLES = {
    "SUPERADMIN": "superadmin",
    "ADMIN": "admin", 
    "PROCTOR": "proctor",
}


def _verify_jwt_token(token: str) -> dict:
    """Verify JWT token signature and decode payload."""
    if not settings.JWT_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET_KEY not configured on server"
        )
    
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_signature": True, "verify_aud": False, "verify_exp": True},
        )
        return payload
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Authentication dependency
# ─────────────────────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """
    Validate JWT against configured secret.
    Returns a dict with at least ``user_id``, ``email``, and ``role``.
    Raises 401 if token is missing or invalid.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing auth token")

    token = credentials.credentials
    payload = _verify_jwt_token(token)

    user_id: Optional[str] = payload.get("sub")
    email: Optional[str] = payload.get("email")
    role: Optional[str] = payload.get("role", "user")
    
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")

    return {"user_id": user_id, "email": email or "", "role": role, "raw": payload}


# ─────────────────────────────────────────────────────────────────────────────
# Optional-auth variant (doesn't require a token)
# ─────────────────────────────────────────────────────────────────────────────

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[dict]:
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Role-based access control for admin endpoints
# ─────────────────────────────────────────────────────────────────────────────

def require_role(*allowed_roles: str):
    """
    Dependency factory that enforces role-based access.
    Usage: Depends(require_role("admin", "superadmin"))
    """
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role", "user")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' not authorized. Required: {allowed_roles}"
            )
        return user
    return role_checker


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require admin or superadmin role for admin endpoints."""
    role = user.get("role", "user")
    if role not in ("admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Admin access required. Current role: {role}"
        )
    return user


# ─────────────────────────────────────────────────────────────────────────────
# Internal API Key authentication for inter-service calls
# ─────────────────────────────────────────────────────────────────────────────

async def get_internal_auth(
    x_internal_api_key: Optional[str] = Header(default=None, alias="X-Internal-API-Key")
) -> bool:
    """
    Verify internal API key for AI worker / microservice communication.
    AI workers must provide the key to call protected endpoints.
    """
    if not settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_API_KEY not configured on server"
        )
    
    if not x_internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Internal-API-Key header"
        )
    
    if not hmac.compare_digest(x_internal_api_key, settings.INTERNAL_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key"
        )
    
    return True


# ─────────────────────────────────────────────────────────────────────────────
# HP Webhook signature verification
# ─────────────────────────────────────────────────────────────────────────────

def verify_hp_webhook(body: bytes, signature: Optional[str] = Header(default=None, alias="X-HP-Signature")) -> bool:
    """
    Verify HMAC-SHA256 signature for HP webhook payloads.
    Signature must be provided in X-HP-Signature header.
    """
    if not settings.HP_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="HP_WEBHOOK_SECRET not configured on server"
        )
    
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-HP-Signature header"
        )
    
    expected_sig = hmac.new(
        settings.HP_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature"
        )
    
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Service factories
# ─────────────────────────────────────────────────────────────────────────────

def get_hp_mapper():
    """Return the HP webhook payload builder."""
    from api.services.hp_mapper import HPMapper
    return HPMapper()


def get_media_storage():
    """Return the media storage service (Cloudinary)."""
    from api.services.media_storage import MediaStorageService
    return MediaStorageService()

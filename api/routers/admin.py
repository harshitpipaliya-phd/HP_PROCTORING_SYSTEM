"""
api/routers/admin.py
====================
Organization, exam, user management, and admin session endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional

from core.session import (
    create_organization, create_exam, get_session_status,
    get_session_by_id, get_current_session,
    _session_registry, _registry_lock,
)
from api.schemas.admin import (
    OrganizationRequest, ExamRequest, SessionFlagRequest, SessionFlagResponse,
    UserCreateRequest, UserResponse,
)
from api.core.dependencies import get_current_admin, require_role

router = APIRouter(prefix="/v1/admin", tags=["Admin"])


@router.post("/organizations")
def api_create_organization(
    req: OrganizationRequest,
    admin_user: dict = Depends(get_current_admin)
):
    result = create_organization(name=req.name, slug=req.slug, settings=req.settings)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return {"success": True, "organization": result}


@router.post("/exams")
def api_create_exam(
    req: ExamRequest,
    admin_user: dict = Depends(get_current_admin)
):
    result = create_exam(
        name=req.name, organization_id=req.organization_id,
        duration_minutes=req.duration_minutes,
        risk_weights=req.risk_weights, proctoring_config=req.proctoring_config,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return {"success": True, "exam": result}


@router.get("/sessions/active")
def api_admin_sessions_active(
    admin_user: dict = Depends(get_current_admin),
    limit: int = Query(default=50, le=200),
):
    """List all active sessions from the in-memory registry."""

    sessions = []
    with _registry_lock:
        for sid, sess in list(_session_registry.items()):
            if getattr(sess, "_active", False):
                sessions.append({
                    "session_id": sess.session_id,
                    "user_id": sess.user_id,
                    "candidate_id": sess.candidate_id,
                    "exam_id": sess.exam_id,
                    "organization_id": sess.organization_id,
                    "start_time": sess.start_time,
                    "risk_score": sess.risk_score,
                    "focus_score": sess.focus_score,
                    "violations_count": len(sess.violations),
                    "total_frames": sess.total_frames,
                })
                if len(sessions) >= limit:
                    break

    return {"success": True, "active_count": len(sessions), "sessions": sessions}


@router.get("/sessions/{session_id}/feed")
def api_admin_session_feed(
    session_id: str,
    admin_user: dict = Depends(get_current_admin),
):
    """Get a specific session's detailed feed: violations, events, and status."""

    sess = get_session_by_id(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "success": True,
        "session_id": sess.session_id,
        "user_id": sess.user_id,
        "candidate_id": sess.candidate_id,
        "exam_id": sess.exam_id,
        "organization_id": sess.organization_id,
        "active": getattr(sess, "_active", False),
        "risk_score": sess.risk_score,
        "focus_score": sess.focus_score,
        "violations_count": len(sess.violations),
        "total_frames": sess.total_frames,
        "tab_switches": sess.tab_switches,
        "attention_breaks": sess.attention_breaks,
        "violations": sess.violations[-100:],
        "risk_flags": sess.risk_flags[-50:],
        "events": sess.events[-50:],
        "prohibited_objects": list(set(sess.prohibited_objects_detected)),
        "start_time": sess.start_time,
        "end_time": sess.end_time,
    }


@router.post("/sessions/{session_id}/flag", response_model=SessionFlagResponse)
def api_admin_flag_session(
    session_id: str,
    body: SessionFlagRequest,
    admin_user: dict = Depends(get_current_admin),
):
    """Manually flag a session for review."""

    sess = get_session_by_id(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    sess.add_violation("ADMIN_FLAG", {
        "reason": body.reason,
        "notes": body.notes or "",
        "flagged_by": admin_user.get("email", "unknown"),
        "flagged_at": __import__("datetime").datetime.now().isoformat(),
    })

    return SessionFlagResponse(
        session_id=session_id,
        flagged=True,
        reason=body.reason,
        notes=body.notes,
    )


@router.get("/users", response_model=List[UserResponse])
def api_admin_list_users(
    admin_user: dict = Depends(get_current_admin),
    role: Optional[str] = Query(default=None),
    organization_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """List users from the database."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        query = _supabase.table("users").select("*").order("created_at", desc=True).limit(limit)

        if role:
            query = query.eq("role", role)
        if organization_id:
            query = query.eq("organization_id", organization_id)

        resp = query.execute()
        rows = resp.data or []
        return [
            UserResponse(
                id=r.get("id", ""),
                email=r.get("email", ""),
                name=r.get("name", ""),
                role=r.get("role", "proctor"),
                organization_id=r.get("organization_id"),
                is_active=r.get("is_active", True),
                created_at=r.get("created_at"),
            )
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users", response_model=UserResponse)
def api_admin_create_user(
    body: UserCreateRequest,
    admin_user: dict = Depends(get_current_admin),
):
    """Create a new user (admin, proctor, superadmin)."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        import uuid
        user_id = str(uuid.uuid4())
        import hashlib
        password_hash = hashlib.sha256(body.password.encode()).hexdigest()

        data = {
            "id": user_id,
            "email": body.email,
            "name": body.name,
            "role": body.role,
            "organization_id": body.organization_id,
            "password_hash": password_hash,
            "is_active": True,
        }
        resp = _supabase.table("users").insert(data).execute()
        if resp.data:
            row = resp.data[0]
            return UserResponse(
                id=row.get("id", user_id),
                email=row.get("email", body.email),
                name=row.get("name", body.name),
                role=row.get("role", body.role),
                organization_id=row.get("organization_id"),
                is_active=row.get("is_active", True),
                created_at=row.get("created_at"),
            )
        raise HTTPException(status_code=500, detail="User creation failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}")
def api_admin_delete_user(
    user_id: str,
    admin_user: dict = Depends(get_current_admin),
):
    """Soft-delete a user by setting is_active=False."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        _supabase.table("users").update({"is_active": False}).eq("id", user_id).execute()
        return {"success": True, "user_id": user_id, "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/organizations")
def api_admin_list_organizations(
    admin_user: dict = Depends(get_current_admin),
    limit: int = Query(default=50, le=200),
):
    """List all organizations."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        resp = _supabase.table("organizations").select("*").order("created_at", desc=True).limit(limit).execute()
        rows = resp.data or []
        return {"success": True, "total": len(rows), "organizations": rows}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/organizations/{org_id}")
def api_admin_get_organization(
    org_id: str,
    admin_user: dict = Depends(get_current_admin),
):
    """Get a specific organization by ID."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        resp = _supabase.table("organizations").select("*").eq("id", org_id).single().execute()
        if resp.data:
            return {"success": True, "organization": resp.data}
        raise HTTPException(status_code=404, detail="Organization not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/organizations/{org_id}")
def api_admin_update_organization(
    org_id: str,
    body: OrganizationRequest,
    admin_user: dict = Depends(get_current_admin),
):
    """Update organization details."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        update_data = {k: v for k, v in body.model_dump().items() if v is not None}
        resp = _supabase.table("organizations").update(update_data).eq("id", org_id).execute()
        if resp.data:
            return {"success": True, "organization": resp.data[0]}
        raise HTTPException(status_code=404, detail="Organization not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/organizations/{org_id}")
def api_admin_delete_organization(
    org_id: str,
    admin_user: dict = Depends(get_current_admin),
):
    """Delete an organization (cascade)."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        _supabase.table("organizations").delete().eq("id", org_id).execute()
        return {"success": True, "organization_id": org_id, "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

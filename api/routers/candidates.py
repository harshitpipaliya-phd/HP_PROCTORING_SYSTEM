"""
api/routers/candidates.py
=========================
Candidate enrollment, lookup, update, and delete endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from typing import List, Optional
import base64
import numpy as np
import cv2

from core.session import enroll_candidate, get_candidate
from api.schemas.candidate import CandidateEnrollRequest
from api.schemas.admin import CandidateUpdateRequest
from api.core.dependencies import require_role

router = APIRouter(prefix="/v1/candidates", tags=["Candidates"])


@router.post("/enroll")
def api_enroll_candidate(
    req: CandidateEnrollRequest,
    user: dict = Depends(require_role("admin", "superadmin", "proctor"))
):
    result = enroll_candidate(
        name=req.name, email=req.email,
        external_id=req.external_id, organization_id=req.organization_id,
        face_embedding=req.face_embedding,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return {"success": True, "candidate": result}


@router.get("/{candidate_id}")
def api_get_candidate(
    candidate_id: str,
    user: dict = Depends(require_role("admin", "superadmin", "proctor"))
):
    cand = get_candidate(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"success": True, "candidate": cand}


@router.get("/")
def api_list_candidates(
    user: dict = Depends(require_role("admin", "superadmin", "proctor")),
    organization_id: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """List candidates, optionally filtered by organization or search term."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        query = _supabase.table("candidates").select("*").order("updated_at", desc=True).limit(limit)

        if organization_id:
            query = query.eq("organization_id", organization_id)

        resp = query.execute()
        rows = resp.data or []

        if search:
            s = search.lower()
            rows = [r for r in rows if s in r.get("name", "").lower() or s in r.get("email", "").lower()]

        return {"success": True, "total": len(rows), "candidates": rows}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{candidate_id}")
def api_update_candidate(
    candidate_id: str,
    body: CandidateUpdateRequest,
    user: dict = Depends(require_role("admin", "superadmin", "proctor")),
):
    """Update candidate details."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        update_data = {k: v for k, v in body.model_dump().items() if v is not None}
        if "face_embedding" in update_data:
            import json
            update_data["face_embedding"] = json.dumps(update_data["face_embedding"])

        resp = _supabase.table("candidates").update(update_data).eq("id", candidate_id).execute()
        if resp.data:
            return {"success": True, "candidate": resp.data[0]}
        raise HTTPException(status_code=404, detail="Candidate not found or not updated")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{candidate_id}")
def api_delete_candidate(
    candidate_id: str,
    user: dict = Depends(require_role("admin", "superadmin")),
):
    """Delete a candidate record."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            raise HTTPException(status_code=503, detail="Database not available")

        resp = _supabase.table("candidates").delete().eq("id", candidate_id).execute()
        if resp.data:
            return {"success": True, "candidate_id": candidate_id, "deleted": True}
        raise HTTPException(status_code=404, detail="Candidate not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enroll-face")
def api_enroll_face(
    candidate_id: str = Query(..., description="Candidate ID to enroll face for"),
    image_b64: str = Query(..., description="Base64-encoded face image"),
    user: dict = Depends(require_role("admin", "superadmin", "proctor")),
):
    """Enroll a face embedding for a candidate using MediaPipe Face Mesh."""
    from ai_workers.models.face_analyzer import enroll_face
    result = enroll_face(image_b64, candidate_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Face enrollment failed"))
    return {"success": True, "candidate_id": candidate_id, "embedding": result.get("embedding")}


@router.post("/verify-face")
def api_verify_face(
    candidate_id: str = Query(..., description="Candidate ID to verify against"),
    image_b64: str = Query(..., description="Base64-encoded face image for verification"),
    user: dict = Depends(require_role("admin", "superadmin", "proctor")),
):
    """Verify face against enrolled candidate embedding using cosine similarity."""
    from ai_workers.models.face_analyzer import verify_face
    img_bytes = base64.b64decode(image_b64)
    arr = np.frombuffer(img_bytes, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="Image decode failed")
    result = verify_face(image, candidate_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Face verification failed"))
    return {"success": True, "match": result.get("match"), "score": result.get("score"),
            "candidate_id": candidate_id}


@router.post("/face/verify")
async def api_face_verify_upload(
    file: UploadFile = File(...),
    candidate_id: str = Query(..., description="Candidate ID to verify against"),
    user: dict = Depends(require_role("admin", "superadmin", "proctor")),
):
    """Verify face using uploaded image file."""
    content = base64.b64encode(await file.read()).decode()
    from ai_workers.models.face_analyzer import verify_face
    import base64
    import numpy as np
    img_bytes = base64.b64decode(content)
    arr = np.frombuffer(img_bytes, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="Image decode failed")
    result = verify_face(image, candidate_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Face verification failed"))
    return {"success": True, "match": result.get("match"), "score": result.get("score"),
            "candidate_id": candidate_id}

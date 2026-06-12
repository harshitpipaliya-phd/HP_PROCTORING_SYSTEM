"""
ai_workers/app.py
=================
Worker application entry-point.

Launches a FastAPI worker service for offloading GPU-bound AI analysis
from the main API process. Horizontally scalable AI inference endpoints.
"""

from fastapi import FastAPI, HTTPException, Header, Body
import os
import hmac

app = FastAPI(
    title="HP Proctoring AI Workers",
    version="2.0.0",
)


def _verify_internal_api_key(x_internal_api_key: str = Header(default=None, alias="X-Internal-API-Key")) -> None:
    """Verify internal API key for inter-service authentication."""
    from core.config import get_settings
    settings = get_settings()
    
    if not settings.INTERNAL_API_KEY:
        raise HTTPException(500, "INTERNAL_API_KEY not configured on server")
    
    if not x_internal_api_key:
        raise HTTPException(401, "Missing X-Internal-API-Key header")
    
    if not hmac.compare_digest(x_internal_api_key, settings.INTERNAL_API_KEY):
        raise HTTPException(403, "Invalid internal API key")


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai_workers"}


@app.post("/analyze/frame")
def analyze_frame_worker(
    payload: dict = Body(...),
    x_internal_api_key: str = Header(default=None, alias="X-Internal-API-Key")
):
    _verify_internal_api_key(x_internal_api_key)
    frame_b64 = payload.get("frame_b64", "")
    user_id = payload.get("user_id", "api_user")
    session_id = payload.get("session_id", "unknown")
    
    try:
        import base64
        import cv2
        import numpy as np
        from video_ai.processor import analyze_frame
        img_bytes = base64.b64decode(frame_b64)
        arr = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(422, "Image decode failed")
        _, result = analyze_frame(image)
        result.pop("annotated_frame", None)
        result.pop("evidence", None)
        return {"success": True, "session_id": session_id, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/analyze/audio")
def analyze_audio_worker(
    payload: dict = Body(...),
    x_internal_api_key: str = Header(default=None, alias="X-Internal-API-Key")
):
    _verify_internal_api_key(x_internal_api_key)
    file_path = payload.get("file_path", "")
    user_id = payload.get("user_id", "api_user")
    
    try:
        from audio_proctoring.stream import analyze_audio_file
        result = analyze_audio_file(file_path, user_id)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/analyze/video")
def analyze_video_worker(
    payload: dict = Body(...),
    x_internal_api_key: str = Header(default=None, alias="X-Internal-API-Key")
):
    """Spec-compliant alias: POST /analyze/video (mirrors /analyze/frame)."""
    return analyze_frame_worker(payload, x_internal_api_key)


@app.post("/verify/face")
def verify_face_worker(
    payload: dict = Body(...),
    x_internal_api_key: str = Header(default=None, alias="X-Internal-API-Key")
):
    """
    Verify a live face embedding against the enrolled candidate reference.

    Request body:
        candidate_id: str
        frame_b64:    str  (base64-encoded BGR/JPEG frame)

    Returns:
        { match: bool, similarity: float, candidate_id: str }

    Threshold: similarity >= 0.6 = match  (per spec Section 11, Note 3)
    """
    _verify_internal_api_key(x_internal_api_key)
    candidate_id = payload.get("candidate_id", "")
    frame_b64 = payload.get("frame_b64", "")

    if not candidate_id or not frame_b64:
        raise HTTPException(422, "candidate_id and frame_b64 are required")

    try:
        import base64
        import cv2
        import numpy as np

        img_bytes = base64.b64decode(frame_b64)
        arr = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(422, "Image decode failed")

        # Retrieve enrolled embedding from DB
        enrolled_embedding = None
        try:
            from database.client import _supabase, _db_available
            if _db_available and _supabase:
                resp = (_supabase.table("face_references")
                        .select("embedding")
                        .eq("candidate_id", candidate_id)
                        .limit(1)
                        .execute())
                rows = resp.data or []
                if rows:
                    enrolled_embedding = rows[0].get("embedding")
        except Exception:
            pass

        if not enrolled_embedding:
            return {
                "match": False, "similarity": 0.0,
                "candidate_id": candidate_id,
                "error": "No enrolled face embedding found for candidate",
            }

        # Extract live embedding using face analyzer
        from ai_workers.models.face_analyzer import FaceAnalyzer
        analyzer = FaceAnalyzer()
        face_result = analyzer.analyze_faces(image)

        if not face_result or face_result.get("faces", 0) == 0:
            return {
                "match": False, "similarity": 0.0,
                "candidate_id": candidate_id,
                "error": "No face detected in live frame",
            }

        live_embedding = face_result.get("embedding")
        if live_embedding is None:
            return {
                "match": False, "similarity": 0.0,
                "candidate_id": candidate_id,
                "error": "Could not extract embedding from live frame",
            }

        # Cosine similarity
        e1 = np.array(enrolled_embedding, dtype=float)
        e2 = np.array(live_embedding, dtype=float)
        n1, n2 = np.linalg.norm(e1), np.linalg.norm(e2)
        similarity = float(np.dot(e1, e2) / (n1 * n2)) if (n1 > 0 and n2 > 0) else 0.0

        MATCH_THRESHOLD = 0.6
        return {
            "match": similarity >= MATCH_THRESHOLD,
            "similarity": round(similarity, 4),
            "candidate_id": candidate_id,
            "threshold": MATCH_THRESHOLD,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AI_WORKER_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)

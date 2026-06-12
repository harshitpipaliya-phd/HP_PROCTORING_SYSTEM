"""
api/routers/webhooks.py
=======================
Webhook endpoints including HP-compatible webhook payload delivery.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi import status as _status
import json
import hmac
import hashlib

from core.session import get_session_status
from video_ai.risk_engine import generate_report
from core.config import get_settings

router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


def _verify_hp_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature for HP webhook payloads."""
    settings = get_settings()
    if not settings.HP_WEBHOOK_SECRET:
        return False
    
    if not signature:
        return False
    
    expected_sig = hmac.new(
        settings.HP_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_sig)


@router.post("/hp/compliance")
async def hp_webhook_endpoint(request: Request):
    """
    Accept an incoming HP compliance webhook.
    Requires HMAC-SHA256 signature in X-HP-Signature header.
    Logs the raw payload and returns ack.
    """
    body = await request.body()
    signature = request.headers.get("X-HP-Signature")
    
    if not _verify_hp_webhook_signature(body, signature):
        raise HTTPException(_status.HTTP_401_UNAUTHORIZED, "Invalid or missing webhook signature")
    
    try:
        payload = json.loads(body.decode()) if body else {}
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    try:
        from database.client import _async_insert
        _async_insert("webhook_logs", {
            "source": "hp_compliance",
            "payload": json.dumps(payload),
        })
    except Exception:
        pass

    return {"success": True, "ack": True, "message": "HP webhook received"}


@router.get("/hp/payload")
def api_hp_payload():
    """HP-compatible webhook payload with competency model scores."""
    session_state = get_session_status()
    if not session_state.get("session_id"):
        raise HTTPException(status_code=400, detail="No session available")
    from video_ai.risk_engine import generate_report, build_hp_webhook_payload
    report = generate_report(session_state)
    payload = build_hp_webhook_payload(report)
    return {"success": True, "hp_payload": payload}

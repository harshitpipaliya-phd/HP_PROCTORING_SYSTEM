"""
api/main.py
===========
Application entry-point for the HP Proctoring API.

Run:
  uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

import datetime as _dt
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse


from api.core.config import get_settings
from api.core.dependencies import get_current_user_optional

settings = get_settings()

# ── Structured logging (structlog) ──────────────────────────────────────────
try:
    import structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _log = structlog.get_logger("hp_proctoring.api")
    _log.info("structlog_initialized", service="hp-proctoring-api", version="2.0.0")
except ImportError:
    import logging
    _log = logging.getLogger("hp_proctoring.api")

# ── Sentry error tracking ────────────────────────────────────────────────────
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.2,
            environment=os.getenv("ENVIRONMENT", "production"),
            release=f"hp-proctoring@2.0.0",
            send_default_pii=False,
        )
        _log.info("sentry_initialized", dsn_truncated=_sentry_dsn[:20] + "...")
    except ImportError:
        _log.warning("sentry_sdk_not_installed", hint="pip install sentry-sdk[fastapi]")

app = FastAPI(
    title="HP Proctoring Backend API",
    description="Unified AI Proctoring System — modular routers v2.0",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Rate limiting (slowapi) ──────────────────────────────────────────────────
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
except ImportError:
    pass

# ── CORS ─────────────────────────────────────────────────────────────────────
cors_origins = settings.CORS_ORIGINS
if "*" in cors_origins:
    allow_origins = ["http://localhost:3000", "http://localhost:8000", "http://localhost:8501"]
else:
    allow_origins = cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ── Router imports ─────────────────────────────────────────────────────────
from api.routers.sessions import router as sessions_router
from api.routers.auth import router as auth_router
from api.routers.detection import router as detection_router
from api.routers.monitoring import router as monitoring_router
from api.routers.candidates import router as candidates_router
from api.routers.admin import router as admin_router
from api.routers.webhooks import router as webhooks_router
from api.routers.logs import router as logs_router
from api.routers.events import router as events_router
from api.routers.reports import router as reports_router

from api.websockets.stream_handler import ws_audio_stream
from api.websockets.dashboard_handler import ws_dashboard
from api.websockets.stream_video_handler import ws_stream_endpoint
from api.websockets.admin_handler import ws_admin_session_endpoint
from api.websockets.admin_broadcast_handler import ws_admin_broadcast_endpoint

# ── Health & Root ─────────────────────────────────────────────────────────

@app.post("/auth/login", tags=["Auth"])
def auth_login_compat(req: dict = Body(...)):
    """Backward-compatible login (no /v1 prefix)."""
    from api.routers.auth import LoginRequest, login as _login
    model = LoginRequest(**req)
    return _login(model)


@app.get("/", tags=["Info"])
def root():
    """API info and endpoint map."""
    from database import is_available as db_available
    from core.session import get_session_status
    try:
        from screen_monitoring.capture import is_screen_capture_available
        sc = is_screen_capture_available()
    except Exception:
        sc = False

    libs = {}
    for mod, key in [("mediapipe", "mediapipe"), ("ultralytics", "yolov8"),
                     ("cv2", "opencv"), ("soundfile", "soundfile")]:
        try:
            __import__(mod)
            libs[key] = True
        except Exception:
            libs[key] = False
    libs["screen_capture"] = sc

    return {
        "service": "HP Proctoring Backend API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "session": ["/v1/sessions", "/v1/sessions/{id}", "/v1/sessions/{id}/end",
                        "/v1/sessions/{id}/terminate", "/v1/sessions/{id}/events"],
            "detection": ["/v1/detect/video", "/v1/detect/audio"],
            "monitoring": ["/v1/monitor/violations", "/v1/monitor/risk", "/v1/monitor/report"],
            "candidates": ["/v1/candidates/enroll", "/v1/candidates/{candidate_id}"],
            "admin": ["/v1/admin/sessions/active", "/v1/admin/sessions/{id}/feed"],
            "auth": ["/v1/auth/login"],
            "events": ["/v1/events?session_id="],
            "reports": ["/v1/reports/{session_id}", "/v1/reports/{session_id}/pdf"],
            "websockets": ["/ws/stream/{session_id}", "/ws/admin/{session_id}",
                           "/ws/admin/broadcast", "/ws/audio/{session_id}", "/ws/dashboard"],
        },
    }


@app.get("/health", tags=["Info"])
def health():
    """Health check with library and DB status."""
    from database import is_available as db_available
    from core.session import get_current_session

    libs = {}
    for mod, key in [("mediapipe", "mediapipe"), ("ultralytics", "yolov8"),
                     ("cv2", "opencv"), ("soundfile", "soundfile")]:
        try:
            __import__(mod)
            libs[key] = True
        except Exception:
            libs[key] = False

    try:
        from screen_monitoring.capture import is_screen_capture_available
        libs["screen_capture"] = is_screen_capture_available()
    except Exception:
        libs["screen_capture"] = False
    libs["audio_analysis"] = True

    session = get_current_session()
    return {
        "status": "ok",
        "service": "HP Proctoring Backend",
        "version": "2.0.0",
        "timestamp": _dt.datetime.now().isoformat(),
        "libraries": libs,
        "database": db_available(),
        "session_active": session is not None and getattr(session, "_active", False),
        "session_id": session.session_id if session else None,
    }


# ── Router mounts ─────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(detection_router)
app.include_router(monitoring_router)
app.include_router(candidates_router)
app.include_router(admin_router)
app.include_router(webhooks_router)
app.include_router(events_router)
app.include_router(reports_router)

app.include_router(logs_router)

# ── Backward-compatible flat session routes (/session/* without /v1) ──────

@app.post("/session/start", tags=["Compat"], include_in_schema=False)
def session_start_compat(
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user_optional),
):
    from api.schemas.session import StartRequest
    from api.routers.sessions import api_start_session
    req = StartRequest(**body)
    return api_start_session(req, user=user or {})


@app.post("/session/start/v2", tags=["Compat"], include_in_schema=False)
def session_start_v2_compat(
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user_optional),
):
    from api.schemas.session import StartRequest
    from api.routers.sessions import api_start_session
    from core.session import get_current_session
    req = StartRequest(**body)
    # Stop any existing session first for v2 (idempotent per-user)
    session = get_current_session()
    if session and getattr(session, "_active", False):
        if session.user_id == req.user_id:
            return {
                "success": True,
                "session_id": session.session_id,
                "candidate_id": session.candidate_id,
                "message": "Session already active",
            }
    result = api_start_session(req, user=user or {})
    result["candidate_id"] = body.get("candidate_id")
    return result


@app.get("/session/status", tags=["Compat"], include_in_schema=False)
def session_status_compat(user: dict = Depends(get_current_user_optional)):
    from core.session import get_session_status
    status = get_session_status()
    return {"success": True, **status}


@app.post("/session/stop", tags=["Compat"], include_in_schema=False)
def session_stop_compat(
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user_optional),
):
    from core.session import get_current_session, stop_session
    session = get_current_session()
    if not session or not getattr(session, "_active", False):
        return {"success": True, "message": "No active session"}
    reason = body.get("reason", "manual")
    info = stop_session(reason)
    return {"success": True, **info}


# Backward-compat flat monitor routes (tests call /monitor/* not /v1/monitor/*)
@app.get("/monitor/violations", tags=["Compat"], include_in_schema=False)
def monitor_violations_compat(user: dict = Depends(get_current_user_optional)):
    from api.routers.monitoring import api_violations
    return api_violations(user=user or {})


@app.get("/monitor/risk", tags=["Compat"], include_in_schema=False)
def monitor_risk_compat(user: dict = Depends(get_current_user_optional)):
    from api.routers.monitoring import api_risk
    return api_risk(user=user or {})


@app.get("/monitor/report/text", response_class=PlainTextResponse,
         tags=["Compat"], include_in_schema=False)
def monitor_report_text_compat(user: dict = Depends(get_current_user_optional)):
    from api.routers.monitoring import api_report_text
    return api_report_text(user=user or {})


@app.get("/monitor/stats", tags=["Compat"], include_in_schema=False)
def monitor_stats_compat(user: dict = Depends(get_current_user_optional)):
    from api.routers.monitoring import api_stats
    return api_stats(user=user or {})


@app.get("/monitor/monitors", tags=["Compat"], include_in_schema=False)
def monitor_monitors_compat(user: dict = Depends(get_current_user_optional)):
    from api.routers.monitoring import api_monitors
    return api_monitors(user=user or {})


@app.get("/monitor/events", tags=["Compat"], include_in_schema=False)
def monitor_events_compat(user: dict = Depends(get_current_user_optional)):
    from video_ai.processor import get_event_log, get_behavior_trends
    events = get_event_log()
    trends = get_behavior_trends()
    return {"total": len(events), "events": events[-100:], "trends": trends}


@app.get("/monitor/risk-weights", tags=["Compat"], include_in_schema=False)
def monitor_risk_weights_compat(user: dict = Depends(get_current_user_optional)):
    from api.routers.monitoring import api_get_risk_weights
    return api_get_risk_weights(user=user or {})


# Backward-compat flat log routes (/logs/* without /v1)
@app.get("/logs/behavior", tags=["Compat"], include_in_schema=False)
def logs_behavior_compat(limit: int = 20):
    from database import fetch_recent_logs, is_available as db_available
    if not db_available():
        return {"success": False, "message": "Database not available", "logs": []}
    return {"success": True, "logs": fetch_recent_logs("behavior_logs", limit)}


@app.get("/logs/audio", tags=["Compat"], include_in_schema=False)
def logs_audio_compat(limit: int = 20):
    from database import fetch_recent_logs, is_available as db_available
    if not db_available():
        return {"success": False, "message": "Database not available", "logs": []}
    return {"success": True, "logs": fetch_recent_logs("audio_logs", limit)}


@app.get("/logs/sessions", tags=["Compat"], include_in_schema=False)
def logs_sessions_compat(limit: int = 20):
    from database import fetch_sessions, is_available as db_available
    if not db_available():
        return {"success": False, "message": "Database not available", "logs": []}
    return {"success": True, "sessions": fetch_sessions(limit=limit)}


# ── WebSocket routes ───────────────────────────────────────────────────────

@app.websocket("/ws/stream/{session_id}")
async def ws_stream_endpoint_rt(websocket: WebSocket, session_id: str):
    await ws_stream_endpoint(websocket, session_id)


@app.websocket("/ws/admin/{session_id}")
async def ws_admin_endpoint_rt(websocket: WebSocket, session_id: str):
    await ws_admin_session_endpoint(websocket, session_id)


@app.websocket("/ws/admin/broadcast")
async def ws_admin_broadcast_rt(websocket: WebSocket):
    await ws_admin_broadcast_endpoint(websocket)


@app.websocket("/ws/audio/{session_id}")
async def ws_audio_endpoint(websocket: WebSocket, session_id: str):
    await ws_audio_stream(websocket, session_id)


@app.websocket("/ws/dashboard")
async def ws_dashboard_endpoint(websocket: WebSocket):
    await ws_dashboard(websocket)


# ── Compat routes for browser integrity events ───────────────────────────
@app.post("/monitor/face-absent", tags=["Compat"], include_in_schema=False)
def compat_face_absent(
    req: dict = Body(default={}),
    user: dict = Depends(get_current_user_optional),
):
    from api.routers.monitoring import api_face_absent
    return api_face_absent(req, user=user or {})


@app.post("/monitor/window-blur", tags=["Compat"], include_in_schema=False)
def compat_window_blur(
    req: dict = Body(default={}),
    user: dict = Depends(get_current_user_optional),
):
    from api.routers.monitoring import api_window_blur
    return api_window_blur(req, user=user or {})


@app.post("/monitor/fullscreen-exit", tags=["Compat"], include_in_schema=False)
def compat_fullscreen_exit(
    req: dict = Body(default={}),
    user: dict = Depends(get_current_user_optional),
):
    from api.routers.monitoring import api_fullscreen_exit
    return api_fullscreen_exit(req, user=user or {})


# ── Entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=settings.HOST, port=settings.PORT,
                reload=False, log_level="info")

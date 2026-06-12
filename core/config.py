"""
core/config.py
==============
Unified configuration for HP Proctoring Backend.
Loads environment variables and provides settings throughout the application.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Main settings class for the proctoring system."""

    APP_NAME: str = "HP Proctoring Backend"
    VERSION: str = "2.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", "").strip())
    SUPABASE_KEY: str = field(default_factory=lambda: os.getenv("SUPABASE_KEY", "").strip())

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = field(default_factory=lambda: os.getenv("JWT_SECRET_KEY", "").strip())
    JWT_ALGORITHM: str = field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = field(
        default_factory=lambda: int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    )

    # ── Internal API ──────────────────────────────────────────────────────────
    INTERNAL_API_KEY: str = field(default_factory=lambda: os.getenv("INTERNAL_API_KEY", "").strip())

    # ── Cloudinary ────────────────────────────────────────────────────────────
    CLOUDINARY_CLOUD_NAME: str = field(default_factory=lambda: os.getenv("CLOUDINARY_CLOUD_NAME", ""))
    CLOUDINARY_API_KEY: str = field(default_factory=lambda: os.getenv("CLOUDINARY_API_KEY", ""))
    CLOUDINARY_API_SECRET: str = field(default_factory=lambda: os.getenv("CLOUDINARY_API_SECRET", ""))

    # ── HP Webhook ────────────────────────────────────────────────────────────
    HP_WEBHOOK_URL: str = field(default_factory=lambda: os.getenv("HP_WEBHOOK_URL", ""))
    HP_WEBHOOK_SECRET: str = field(default_factory=lambda: os.getenv("HP_WEBHOOK_SECRET", "").strip())

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    # ── AI Worker ─────────────────────────────────────────────────────────────
    AI_WORKER_URL: str = field(default_factory=lambda: os.getenv("AI_WORKER_URL", "http://localhost:8001"))

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8501",
    ])

    # ── Video AI ──────────────────────────────────────────────────────────────
    VIDEO_MAX_FPS: int = int(os.getenv("VIDEO_MAX_FPS", "30"))
    VIDEO_FRAME_SKIP: int = int(os.getenv("VIDEO_FRAME_SKIP", "0"))
    RISK_THRESHOLD: int = int(os.getenv("RISK_THRESHOLD", "50"))

    EAR_THRESHOLD: float = 0.20
    BLINK_CONSEC_FRAMES: int = 2
    LOOK_AWAY_WINDOW_SECONDS: int = 60
    SUSPICIOUS_LOOK_AWAY_COUNT: int = 5

    YAW_THRESHOLD: float = 15.0
    PITCH_THRESHOLD: float = 12.0
    ROLL_THRESHOLD: float = 20.0

    # ── Audio ─────────────────────────────────────────────────────────────────
    AUDIO_SAMPLE_RATE: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    AUDIO_CHUNK_SIZE: int = int(os.getenv("AUDIO_CHUNK_SIZE", "512"))
    AUDIO_WINDOW_SECONDS: float = 2.0
    AUDIO_OVERLAP_SECONDS: float = 0.5

    # ── Storage paths ─────────────────────────────────────────────────────────
    SCREENSHOT_DIR: str = field(default_factory=lambda: os.getenv("SCREENSHOT_DIR", "static/screenshots"))
    REPORT_DIR: str = field(default_factory=lambda: os.getenv("REPORT_DIR", "static/reports"))
    MONITOR_CHECK_INTERVAL: int = int(os.getenv("MONITOR_CHECK_INTERVAL", "5"))

    # ── Model paths ───────────────────────────────────────────────────────────
    AUDIO_MODEL_PATH: str = field(default_factory=lambda: os.getenv("AUDIO_MODEL_PATH", "models/audio_classifier.pkl"))
    MODEL_META_PATH: str = field(default_factory=lambda: os.getenv("MODEL_META_PATH", "models/model_meta.json"))

    # ── Evidence / Session limits ─────────────────────────────────────────────
    EVIDENCE_ENABLED: bool = True
    MAX_EVIDENCE_FRAMES: int = 50
    MAX_EVENT_LOG: int = 500
    MAX_SESSION_LOG: int = 1000


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the singleton settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings from environment."""
    global _settings
    _settings = Settings()
    return _settings

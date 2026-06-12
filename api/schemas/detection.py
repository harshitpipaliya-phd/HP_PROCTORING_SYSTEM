"""
api/schemas/detection.py
=======================
Schemas for detection and analysis endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional


class VideoDetectRequest(BaseModel):
    image_b64: str = Field(..., description="Base64-encoded JPEG/PNG frame")
    user_id: Optional[str] = Field(default="api_user")


class TabSwitchRequest(BaseModel):
    user_id: Optional[str] = Field(default="api_user")


class AudioDetectRequest(BaseModel):
    file_format: Optional[str] = Field(default="auto", description="Force format (wav/mp3/ogg)")
    user_id: Optional[str] = Field(default="api_user")


class RiskWeightsRequest(BaseModel):
    weights: dict = Field(default_factory=dict, description="Risk weight key-value pairs")


class RiskWeightsLoadRequest(BaseModel):
    exam_id: Optional[str] = None
    organization_id: Optional[str] = None


class AutoScreenshotRequest(BaseModel):
    interval_seconds: int = Field(default=30, ge=5, le=300)
    upload_cloudinary: bool = Field(default=False)

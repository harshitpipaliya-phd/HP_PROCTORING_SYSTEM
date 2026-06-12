"""
api/models/recording.py
========================
ORM model for session recordings (video/audio captures).

Missing model — created to fill spec gap.
Recordings track Cloudinary-stored media assets tied to sessions.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, BigInteger
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SessionRecording(Base):
    """
    A video or audio recording segment associated with a proctoring session.
    Maps to the `session_recordings` table in Supabase.
    """
    __tablename__ = "session_recordings"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    candidate_id = Column(String, index=True, nullable=True)

    # Recording type: "video", "audio", "screen", "screenshot"
    recording_type = Column(String, nullable=False, default="video", index=True)

    # Storage location
    storage_backend = Column(String, default="cloudinary")  # "cloudinary", "s3", "local"
    storage_url = Column(Text, nullable=True)
    storage_public_id = Column(String, nullable=True)  # Cloudinary public_id

    # File metadata
    filename = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    mime_type = Column(String, nullable=True)

    # Video/image dimensions
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    # Processing state: "pending", "processing", "ready", "failed"
    status = Column(String, default="pending", index=True)
    error_message = Column(Text, nullable=True)

    # Risk context at time of recording
    risk_score_at_capture = Column(Integer, default=0)
    triggered_by_event = Column(String, nullable=True)  # event_type that triggered capture

    # Extra metadata (format, codec, fps, etc.)
    metadata = Column(JSON, default={})

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SessionRecording {self.recording_type} "
            f"session={self.session_id} status={self.status}>"
        )

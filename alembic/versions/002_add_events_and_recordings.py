"""add proctoring_events and session_recordings tables

Revision ID: 002_events_recordings
Revises: 001_initial_schema
Create Date: 2026-06-12

Adds:
  - proctoring_events: browser + detection events with risk weights
  - session_recordings: Cloudinary/S3-stored media assets
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "002_events_recordings"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── proctoring_events ─────────────────────────────────────────────────
    op.create_table(
        "proctoring_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_source", sa.String(), nullable=True),
        sa.Column("risk_weight", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("risk_score_at_event", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("severity", sa.String(), nullable=True, server_default="'LOW'"),
        sa.Column("alert_sent", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proctoring_events_session_id", "proctoring_events", ["session_id"])
    op.create_index("ix_proctoring_events_event_type", "proctoring_events", ["event_type"])
    op.create_index("ix_proctoring_events_created_at", "proctoring_events", ["created_at"])

    # ── session_recordings ────────────────────────────────────────────────
    op.create_table(
        "session_recordings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("candidate_id", sa.String(), nullable=True),
        sa.Column("recording_type", sa.String(), nullable=False, server_default="'video'"),
        sa.Column("storage_backend", sa.String(), nullable=True, server_default="'cloudinary'"),
        sa.Column("storage_url", sa.Text(), nullable=True),
        sa.Column("storage_public_id", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True, server_default="'pending'"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("risk_score_at_capture", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("triggered_by_event", sa.String(), nullable=True),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_recordings_session_id", "session_recordings", ["session_id"])
    op.create_index("ix_session_recordings_recording_type", "session_recordings", ["recording_type"])
    op.create_index("ix_session_recordings_status", "session_recordings", ["status"])


def downgrade() -> None:
    op.drop_table("session_recordings")
    op.drop_table("proctoring_events")

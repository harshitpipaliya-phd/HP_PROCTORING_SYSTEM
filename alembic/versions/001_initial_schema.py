"""Initial schema — HP Proctoring System

Revision ID: 001_initial
Revises: 
Create Date: 2026-06-12

Transcribed from database/migrations/001_initial_schema.sql.
Includes pgvector extension, all 9 spec tables, RLS policies,
and key indexes.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ

# revision identifiers
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Extensions --
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    # pgvector: required for face re-verification cosine similarity
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # -- organizations --
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, unique=True, nullable=False),
        sa.Column("hp_webhook_url", sa.Text),
        sa.Column("settings", JSONB, server_default="{}"),
        sa.Column("risk_weights", JSONB, server_default="{}"),
        sa.Column("active", sa.Boolean, server_default="true"),
        sa.Column("created_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
        sa.Column("updated_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
    )

    # -- admin_users --
    op.create_table(
        "admin_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("email", sa.Text, unique=True, nullable=False),
        sa.Column("role", sa.Text, server_default="proctor"),
        sa.Column("created_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
    )

    # -- exams --
    op.create_table(
        "exams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("duration_minutes", sa.Integer),
        sa.Column("settings", JSONB, server_default="{}"),
        sa.Column("created_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
    )

    # -- candidates --
    op.create_table(
        "candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("email", sa.Text, unique=True, nullable=False),
        sa.Column("full_name", sa.Text),
        sa.Column("face_embedding", JSONB),
        sa.Column("enrolled", sa.Boolean, server_default="false"),
        sa.Column("created_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
        sa.Column("updated_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
    )

    # -- sessions --
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("exam_id", UUID(as_uuid=True),
                  sa.ForeignKey("exams.id", ondelete="SET NULL")),
        sa.Column("candidate_id", UUID(as_uuid=True),
                  sa.ForeignKey("candidates.id", ondelete="SET NULL")),
        sa.Column("status", sa.Text, server_default="pending"),
        sa.Column("started_at", TIMESTAMPTZ),
        sa.Column("ended_at", TIMESTAMPTZ),
        sa.Column("risk_score", sa.Integer, server_default="0"),
        sa.Column("risk_level", sa.Text),
        sa.Column("ai_verdict", sa.Text),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_sessions_exam_status", "sessions", ["exam_id", "status"])
    op.create_index("ix_sessions_candidate", "sessions", ["candidate_id"])

    # -- events --
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("session_id", UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("severity", sa.Text),
        sa.Column("risk_increment", sa.Integer, server_default="0"),
        sa.Column("confidence", sa.Float),
        sa.Column("frame_ts", TIMESTAMPTZ),
        sa.Column("payload", JSONB, server_default="{}"),
        sa.Column("created_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_events_session_created", "events",
                    ["session_id", sa.text("created_at DESC")])
    op.create_index("ix_events_session_type", "events", ["session_id", "event_type"])

    # -- recordings --
    op.create_table(
        "recordings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("session_id", UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="CASCADE")),
        sa.Column("event_id", UUID(as_uuid=True),
                  sa.ForeignKey("events.id", ondelete="SET NULL")),
        sa.Column("type", sa.Text),
        sa.Column("cloudinary_public_id", sa.Text, nullable=False),
        sa.Column("cloudinary_url", sa.Text, nullable=False),
        sa.Column("duration_seconds", sa.Float),
        sa.Column("captured_at", TIMESTAMPTZ),
        sa.Column("created_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_recordings_session_type", "recordings", ["session_id", "type"])

    # -- reports --
    op.create_table(
        "reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("session_id", UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="CASCADE"), unique=True),
        sa.Column("overall_risk_score", sa.Integer),
        sa.Column("risk_level", sa.Text),
        sa.Column("ai_verdict", sa.Text),
        sa.Column("recommendation", sa.Text),
        sa.Column("event_summary", JSONB, server_default="{}"),
        sa.Column("timeline", JSONB, server_default="[]"),
        sa.Column("focus_score", sa.Float),
        sa.Column("attention_span_avg_s", sa.Float),
        sa.Column("behavior_flags", JSONB, server_default="{}"),
        sa.Column("pdf_url", sa.Text),
        sa.Column("generated_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
    )

    # -- face_references (pgvector) --
    op.create_table(
        "face_references",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("candidate_id", UUID(as_uuid=True),
                  sa.ForeignKey("candidates.id", ondelete="CASCADE"), unique=True),
        sa.Column("image_url", sa.Text),
        sa.Column("enrolled_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
        sa.Column("captured_at", TIMESTAMPTZ, server_default=sa.text("NOW()")),
    )
    # NOTE: embedding vector(128) column added in separate DDL
    # because SQLAlchemy does not have a built-in Vector type.
    # After upgrade, run: ALTER TABLE face_references ADD COLUMN IF NOT EXISTS embedding vector(128);
    op.execute(
        "ALTER TABLE face_references "
        "ADD COLUMN IF NOT EXISTS embedding vector(128)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_face_references_embedding "
        "ON face_references USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # -- RLS: enable on all tables --
    for table in ["organizations", "admin_users", "exams", "candidates",
                  "sessions", "events", "recordings", "reports", "face_references"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY service_role_bypass ON {table} "
            f"TO service_role USING (true) WITH CHECK (true)"
        )


def downgrade() -> None:
    for table in ["face_references", "reports", "recordings", "events",
                  "sessions", "candidates", "exams", "admin_users", "organizations"]:
        op.drop_table(table)

-- Migration 002: Add proctoring_events and session_recordings tables
-- Run in Supabase SQL Editor or via psql
-- Date: 2026-06-12

-- ── proctoring_events ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS proctoring_events (
    id                  TEXT        PRIMARY KEY,
    session_id          TEXT        NOT NULL,
    user_id             TEXT,
    event_type          TEXT        NOT NULL,
    event_source        TEXT,
    risk_weight         INTEGER     DEFAULT 0,
    risk_score_at_event INTEGER     DEFAULT 0,
    payload             JSONB       DEFAULT '{}'::jsonb,
    severity            TEXT        DEFAULT 'LOW',
    alert_sent          BOOLEAN     DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_proctoring_events_session_id
    ON proctoring_events (session_id);

CREATE INDEX IF NOT EXISTS ix_proctoring_events_event_type
    ON proctoring_events (event_type);

CREATE INDEX IF NOT EXISTS ix_proctoring_events_created_at
    ON proctoring_events (created_at DESC);

-- Enable RLS (Row Level Security) — adjust policies per your auth setup
ALTER TABLE proctoring_events ENABLE ROW LEVEL SECURITY;

-- ── session_recordings ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session_recordings (
    id                     TEXT        PRIMARY KEY,
    session_id             TEXT        NOT NULL,
    candidate_id           TEXT,
    recording_type         TEXT        NOT NULL DEFAULT 'video',
    -- recording_type: 'video' | 'audio' | 'screen' | 'screenshot'

    storage_backend        TEXT        DEFAULT 'cloudinary',
    storage_url            TEXT,
    storage_public_id      TEXT,

    filename               TEXT,
    file_size_bytes        BIGINT,
    duration_seconds       FLOAT,
    mime_type              TEXT,
    width                  INTEGER,
    height                 INTEGER,

    status                 TEXT        DEFAULT 'pending',
    -- status: 'pending' | 'processing' | 'ready' | 'failed'
    error_message          TEXT,

    risk_score_at_capture  INTEGER     DEFAULT 0,
    triggered_by_event     TEXT,

    metadata               JSONB       DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ DEFAULT now(),
    updated_at             TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_session_recordings_session_id
    ON session_recordings (session_id);

CREATE INDEX IF NOT EXISTS ix_session_recordings_recording_type
    ON session_recordings (recording_type);

CREATE INDEX IF NOT EXISTS ix_session_recordings_status
    ON session_recordings (status);

ALTER TABLE session_recordings ENABLE ROW LEVEL SECURITY;

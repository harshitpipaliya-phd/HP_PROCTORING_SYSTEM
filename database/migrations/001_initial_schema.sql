-- HP Proctoring Backend - Full Normalized Database Schema
-- Migration: 001_initial_schema
-- Run this in your Supabase SQL editor

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- pgvector for face embeddings — required for cosine-similarity face re-verification
-- Enable in Supabase: Dashboard → Database → Extensions → search "vector" → Enable
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- ORGANIZATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    risk_weights JSONB DEFAULT '{}',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ADMIN USERS
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    role TEXT DEFAULT 'proctor' CHECK (role IN ('admin','proctor','viewer')),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- EXAMS
-- ============================================================
CREATE TABLE IF NOT EXISTS exams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    duration_minutes INTEGER DEFAULT 60,
    risk_weights JSONB DEFAULT '{}',
    proctoring_config JSONB DEFAULT '{}',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- CANDIDATES
-- ============================================================
CREATE TABLE IF NOT EXISTS candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    external_id TEXT,
    name TEXT,
    email TEXT,
    face_embedding JSONB DEFAULT NULL,
    enrolled BOOLEAN DEFAULT FALSE,
    enrollment_photo_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (organization_id, external_id)
);

-- ============================================================
-- FACE REFERENCES (for enrollment / identity verification)
-- ============================================================
CREATE TABLE IF NOT EXISTS face_references (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE UNIQUE,
    image_url TEXT,
    -- pgvector 128-d embedding for cosine similarity (face_recognition library)
    -- Cosine query: SELECT 1 - (embedding <=> $1::vector) AS similarity
    --               FROM face_references WHERE candidate_id = $2
    -- Match threshold: similarity >= 0.6
    embedding vector(128),
    enrolled_at TIMESTAMPTZ DEFAULT NOW(),
    captured_at TIMESTAMPTZ DEFAULT NOW(),
    is_primary BOOLEAN DEFAULT FALSE
);

-- ============================================================
-- SESSIONS (normalized)
-- ============================================================
CREATE TABLE IF NOT EXISTS proctoring_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT UNIQUE NOT NULL,
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    exam_id UUID REFERENCES exams(id) ON DELETE SET NULL,
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    status TEXT DEFAULT 'active' CHECK (status IN ('active','paused','completed','terminated')),
    risk_score INTEGER DEFAULT 0,
    focus_score INTEGER DEFAULT 100,
    ai_verdict TEXT DEFAULT 'INCONCLUSIVE',
    start_time TIMESTAMPTZ DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    duration_seconds NUMERIC(10,1),
    total_frames INTEGER DEFAULT 0,
    violations_count INTEGER DEFAULT 0,
    tab_switches INTEGER DEFAULT 0,
    attention_breaks INTEGER DEFAULT 0,
    stop_reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- EVENTS (normalized, append-only audit trail)
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT DEFAULT 'info' CHECK (severity IN ('info','low','medium','high','critical')),
    risk_delta INTEGER DEFAULT 0,
    detail TEXT,
    payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- RECORDINGS (screenshot / video evidence)
-- ============================================================
CREATE TABLE IF NOT EXISTS recordings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT NOT NULL,
    recording_type TEXT DEFAULT 'screenshot' CHECK (recording_type IN ('screenshot','video','audio')),
    url TEXT,
    local_path TEXT,
    cloudinary_public_id TEXT,
    monitor_id INTEGER DEFAULT 1,
    file_size_bytes INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- REPORTS (generated session reports)
-- ============================================================
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT UNIQUE NOT NULL,
    user_id TEXT,
    risk_score INTEGER DEFAULT 0,
    focus_score INTEGER DEFAULT 100,
    verdict TEXT DEFAULT 'INCONCLUSIVE',
    total_violations INTEGER DEFAULT 0,
    report_json JSONB DEFAULT '{}',
    pdf_url TEXT,
    cloudinary_public_id TEXT,
    hp_payload JSONB DEFAULT '{}',
    behavior_flags JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- BEHAVIOR LOGS (per-frame video AI analysis)
-- ============================================================
CREATE TABLE IF NOT EXISTS behavior_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT,
    user_id TEXT,
    looking_away BOOLEAN DEFAULT FALSE,
    gaze_direction TEXT DEFAULT 'N/A',
    left_gaze TEXT DEFAULT 'N/A',
    right_gaze TEXT DEFAULT 'N/A',
    ear_left FLOAT DEFAULT 0.0,
    ear_right FLOAT DEFAULT 0.0,
    blink_count INTEGER DEFAULT 0,
    look_away_frequency INTEGER DEFAULT 0,
    frequent_look_away BOOLEAN DEFAULT FALSE,
    head_direction TEXT DEFAULT 'N/A',
    yaw FLOAT DEFAULT 0.0,
    pitch FLOAT DEFAULT 0.0,
    roll FLOAT DEFAULT 0.0,
    attention_score INTEGER DEFAULT 0,
    attention_label TEXT DEFAULT 'N/A',
    person_count INTEGER DEFAULT 0,
    multiple_persons BOOLEAN DEFAULT FALSE,
    person_engine TEXT DEFAULT 'N/A',
    prohibited_objects JSONB DEFAULT '[]',
    phone_detected BOOLEAN DEFAULT FALSE,
    book_detected BOOLEAN DEFAULT FALSE,
    notes_detected BOOLEAN DEFAULT FALSE,
    laptop_detected BOOLEAN DEFAULT FALSE,
    object_engine TEXT DEFAULT 'N/A',
    mobile_phone BOOLEAN DEFAULT FALSE,
    phone_confidence FLOAT DEFAULT 0.0,
    hands_detected INTEGER DEFAULT 0,
    unusual_gesture BOOLEAN DEFAULT FALSE,
    gesture_labels JSONB DEFAULT '[]',
    motion_score FLOAT DEFAULT 0.0,
    risk_score INTEGER DEFAULT 0,
    risk_flags JSONB DEFAULT '[]',
    risk_breakdown JSONB DEFAULT '{}',
    events_json JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- AUDIO LOGS
-- ============================================================
CREATE TABLE IF NOT EXISTS audio_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT,
    user_id TEXT DEFAULT 'unknown',
    total_risk INTEGER DEFAULT 0,
    risk_level TEXT DEFAULT 'LOW',
    speech_segments INTEGER DEFAULT 0,
    anomaly_segments INTEGER DEFAULT 0,
    background_voice_segments INTEGER DEFAULT 0,
    unauthorized_segments INTEGER DEFAULT 0,
    estimated_speakers INTEGER DEFAULT 0,
    result TEXT DEFAULT '',
    volume FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- VIDEO LOGS (legacy flat table - kept for backward compat)
-- ============================================================
CREATE TABLE IF NOT EXISTS video_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT,
    event TEXT,
    result TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- SESSIONS (legacy flat table - kept for backward compat)
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT,
    user_id TEXT,
    event TEXT,
    metadata TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_events_session_id ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_behavior_logs_session_id ON behavior_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_behavior_logs_created_at ON behavior_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audio_logs_session_id ON audio_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_recordings_session_id ON recordings(session_id);
CREATE INDEX IF NOT EXISTS idx_proctoring_sessions_session_id ON proctoring_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_proctoring_sessions_user_id ON proctoring_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_proctoring_sessions_created_at ON proctoring_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_session_id ON reports(session_id);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE exams ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE proctoring_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE recordings ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE behavior_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audio_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE face_references ENABLE ROW LEVEL SECURITY;

-- Service role bypass (for backend API calls)
CREATE POLICY "service_role_all" ON organizations TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON admin_users TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON exams TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON candidates TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON proctoring_sessions TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON events TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON recordings TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON reports TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON behavior_logs TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON audio_logs TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON face_references TO service_role USING (true) WITH CHECK (true);

-- Public read for video_logs and sessions (legacy)
CREATE POLICY "allow_all" ON video_logs USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON sessions USING (true) WITH CHECK (true);

-- ============================================================
-- pgvector: ivfflat index for fast cosine similarity search
-- (run AFTER CREATE EXTENSION vector succeeds)
-- ============================================================
-- Index for fast approximate nearest-neighbor on face embeddings
CREATE INDEX IF NOT EXISTS idx_face_references_embedding
    ON face_references USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Safe upgrade path: if face_references.embedding is JSONB from a prior migration,
-- run this once to convert (requires pgvector enabled first):
-- ALTER TABLE face_references ALTER COLUMN embedding TYPE vector(128)
--   USING embedding::text::vector;

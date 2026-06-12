-- migrations/001_initial_schema.sql
-- =====================================
-- Initial HP Proctoring database schema.
-- Run against Supabase Postgres or any Postgres 12+.

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Core tables
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}'::jsonb,
    risk_weights JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    organization_id UUID REFERENCES organizations(id),
    duration_minutes INTEGER DEFAULT 60,
    risk_weights JSONB DEFAULT '{}'::jsonb,
    proctoring_config JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    external_id TEXT,
    organization_id UUID REFERENCES organizations(id),
    enrolled BOOLEAN DEFAULT TRUE,
    face_embedding TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS proctoring_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    candidate_id UUID REFERENCES candidates(id),
    exam_id UUID REFERENCES exams(id),
    organization_id UUID REFERENCES organizations(id),
    status TEXT DEFAULT 'active',
    risk_score INTEGER DEFAULT 0,
    focus_score INTEGER DEFAULT 100,
    total_frames INTEGER DEFAULT 0,
    violations_count INTEGER DEFAULT 0,
    tab_switches INTEGER DEFAULT 0,
    attention_breaks INTEGER DEFAULT 0,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    duration_seconds FLOAT,
    stop_reason TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON proctoring_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_exam ON proctoring_sessions(exam_id);
CREATE INDEX IF NOT EXISTS idx_sessions_org ON proctoring_sessions(organization_id);

-- Logs
CREATE TABLE IF NOT EXISTS behavior_logs (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    user_id TEXT,
    looking_away BOOLEAN DEFAULT FALSE,
    gaze_direction TEXT DEFAULT 'N/A',
    head_direction TEXT DEFAULT 'N/A',
    person_count INTEGER DEFAULT 0,
    multiple_persons BOOLEAN DEFAULT FALSE,
    phone_detected BOOLEAN DEFAULT FALSE,
    risk_score INTEGER DEFAULT 0,
    attention_score INTEGER DEFAULT 0,
    events_json TEXT DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audio_logs (
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    total_risk INTEGER DEFAULT 0,
    risk_level TEXT DEFAULT 'LOW',
    speech_segments INTEGER DEFAULT 0,
    anomaly_segments INTEGER DEFAULT 0,
    background_voice_segments INTEGER DEFAULT 0,
    unauthorized_segments INTEGER DEFAULT 0,
    estimated_speakers INTEGER DEFAULT 0,
    volume FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    session_id TEXT UNIQUE,
    risk_score INTEGER,
    focus_score INTEGER,
    verdict TEXT,
    total_violations INTEGER,
    report_json TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_logs (
    id SERIAL PRIMARY KEY,
    source TEXT,
    payload TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT DEFAULT 'proctor' CHECK (role IN ('superadmin', 'admin', 'proctor')),
    organization_id UUID REFERENCES organizations(id),
    is_active BOOLEAN DEFAULT TRUE,
    password_hash TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);

-- Row Level Security (optional — enable for multi-tenant)
-- ALTER TABLE behavior_logs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE audio_logs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE reports ENABLE ROW LEVEL SECURITY;

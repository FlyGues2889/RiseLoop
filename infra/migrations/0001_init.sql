-- Rise Loop RDS (PostgreSQL 兼容) 初始迁移
-- 说明：主键由 cloud-api 生成 UUID；本文件可重复执行（IF NOT EXISTS）。

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS assessments (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    body_parts JSONB NOT NULL,
    sedentary_minutes INTEGER NOT NULL,
    available_minutes INTEGER NOT NULL,
    pain_score INTEGER NOT NULL,
    red_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    initial_state VARCHAR(2) NOT NULL,
    risk_level VARCHAR(16) NOT NULL,
    plan JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_assessments_user_id ON assessments (user_id);

CREATE TABLE IF NOT EXISTS state_transitions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    from_state VARCHAR(2) NOT NULL,
    to_state VARCHAR(2) NOT NULL,
    reason TEXT NOT NULL,
    transition_type VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_state_transitions_user_id ON state_transitions (user_id);
CREATE INDEX IF NOT EXISTS ix_state_transitions_type ON state_transitions (transition_type);

CREATE TABLE IF NOT EXISTS actions (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    state VARCHAR(2) NOT NULL,
    body_parts JSONB NOT NULL,
    duration_minutes INTEGER NOT NULL,
    intensity VARCHAR(16) NOT NULL,
    steps JSONB NOT NULL,
    caution TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_actions_state ON actions (state);

CREATE TABLE IF NOT EXISTS intervention_logs (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    action_id VARCHAR(64) NOT NULL,
    state VARCHAR(2) NOT NULL,
    completion VARCHAR(16) NOT NULL,
    feeling VARCHAR(16) NOT NULL,
    pain_score INTEGER NOT NULL,
    obstacle VARCHAR(16),
    pushed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_intervention_logs_user_id ON intervention_logs (user_id);

CREATE TABLE IF NOT EXISTS sitting_events (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    event_type VARCHAR(16) NOT NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'manual',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sitting_events_user_id ON sitting_events (user_id);
CREATE INDEX IF NOT EXISTS ix_sitting_events_occurred_at ON sitting_events (occurred_at);

CREATE TABLE IF NOT EXISTS qa_logs (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_qa_logs_user_id ON qa_logs (user_id);

CREATE TABLE IF NOT EXISTS safety_events (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users (id) ON DELETE CASCADE,
    source VARCHAR(32) NOT NULL,
    red_flags JSONB NOT NULL,
    action_taken VARCHAR(32) NOT NULL DEFAULT 'short_circuit',
    occurred_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_safety_events_user_id ON safety_events (user_id);
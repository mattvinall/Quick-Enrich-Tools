-- QuickEnrich Database Schema
-- Paste into Supabase SQL Editor

-- 1. email_captures: Lead capture
CREATE TABLE IF NOT EXISTS email_captures (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email          VARCHAR(255) NOT NULL,
    ip_address     INET,
    tool_slug      VARCHAR(50)  NOT NULL,
    source         VARCHAR(50),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (email, tool_slug)
);

CREATE INDEX IF NOT EXISTS idx_email_captures_email
    ON email_captures (email);


-- 2. tools: Platform tool registry
CREATE TABLE IF NOT EXISTS tools (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    slug          VARCHAR(50)  UNIQUE NOT NULL,
    name          VARCHAR(100) NOT NULL,
    description   TEXT,
    is_active     BOOLEAN      NOT NULL DEFAULT true,
    config_schema JSONB
);

INSERT INTO tools (slug, name, description, is_active)
VALUES (
    'website-finder',
    'Company Website Finder',
    'Find company websites from names and locations',
    true
)
ON CONFLICT (slug) DO NOTHING;


-- 3. jobs: Processing jobs
CREATE TABLE IF NOT EXISTS jobs (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email_capture_id  UUID         NOT NULL REFERENCES email_captures (id),
    tool_slug         VARCHAR(50)  NOT NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'pending',
    total_rows        INT          NOT NULL DEFAULT 0,
    processed_rows    INT          NOT NULL DEFAULT 0,
    current_phase     VARCHAR(30),
    phase_progress    JSONB        DEFAULT '{}',
    config            JSONB        DEFAULT '{}',
    input_file_path   VARCHAR(500),
    output_file_path  VARCHAR(500),
    error_message     TEXT,
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT jobs_status_check CHECK (
        status IN ('pending','parsing','searching','verifying','normalizing','enriching','delivering','completed','failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_jobs_email_capture_id
    ON jobs (email_capture_id);

CREATE INDEX IF NOT EXISTS idx_jobs_status
    ON jobs (status);


-- 4. job_results: One row per CSV row
CREATE TABLE IF NOT EXISTS job_results (
    id                      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id                  UUID         NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    row_index               INT          NOT NULL,
    input_data              JSONB        NOT NULL,
    search_results          JSONB,
    raw_domain              VARCHAR(500),
    verified_domain         VARCHAR(500),
    verification_confidence FLOAT,
    normalized_domain       VARCHAR(500),
    contacts                JSONB,
    status                  VARCHAR(20)  NOT NULL DEFAULT 'pending',
    error_message           TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_results_job_id
    ON job_results (job_id);

CREATE INDEX IF NOT EXISTS idx_job_results_job_id_status
    ON job_results (job_id, status);


-- 5. rate_limits: Abuse prevention
CREATE TABLE IF NOT EXISTS rate_limits (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    identifier      VARCHAR(255) NOT NULL,
    identifier_type VARCHAR(10)  NOT NULL,
    action          VARCHAR(50)  NOT NULL,
    window_start    TIMESTAMPTZ  NOT NULL,
    request_count   INT          NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_lookup
    ON rate_limits (identifier, identifier_type, action, window_start);

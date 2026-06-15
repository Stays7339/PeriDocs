-- ====================================================================
-- PeriDocs RADICLE v0 - Identity & Credentialing Storage
-- ====================================================================

CREATE TABLE IF NOT EXISTS app.accounts (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    totp_secret TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index the username for fast lookup during login requests
CREATE INDEX IF NOT EXISTS idx_accounts_username ON app.accounts (username);
-- ====================================================================
-- PeriDocs RADICLE v0 - Identity & Credentialing Storage
-- Location: database-management/schemas/tables/app_schema.sql
-- save-state: 2026-07-12T11:09-04:00
-- ====================================================================

CREATE TABLE IF NOT EXISTS app.accounts (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    totp_secret_encrypted TEXT NOT NULL, -- Renamed/Added to match Python
    role VARCHAR(50) NOT NULL,           -- Added to match Python
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_accounts_username ON app.accounts (username);
-- WIM Online — password reset tokens (admin-initiated, rep-completes). Additive.
CREATE TABLE IF NOT EXISTS wim_password_resets (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES wim_users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,         -- SHA-256 of random token (never plaintext)
    created_by  INT REFERENCES wim_users(id), -- issuing admin
    created_at  TIMESTAMP DEFAULT NOW(),
    expires_at  TIMESTAMP NOT NULL,           -- NOW()+interval '24 hours'
    used_at     TIMESTAMP                     -- NULL until consumed (single-use)
);
CREATE INDEX IF NOT EXISTS idx_password_resets_user ON wim_password_resets(user_id);
CREATE INDEX IF NOT EXISTS idx_password_resets_exp ON wim_password_resets(expires_at);
CREATE INDEX IF NOT EXISTS idx_pr_exp_unused ON wim_password_resets(expires_at) WHERE used_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sessions_user ON wim_sessions(user_id);

-- Audit: track when a password was last changed
ALTER TABLE wim_users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP;

GRANT SELECT, INSERT, UPDATE, DELETE ON wim_password_resets TO wim_app;
GRANT USAGE ON SEQUENCE wim_password_resets_id_seq TO wim_app;
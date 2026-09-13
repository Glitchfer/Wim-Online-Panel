-- ============================================================
-- WIM Online — Promo editor: Any-Product condition, AND/OR rows,
-- per-order + lifetime redeem limits (additive & reversible).
-- ============================================================

-- 1) Operator between requirement rows (AND | OR)
ALTER TABLE wim_promo_conditions ADD COLUMN IF NOT EXISTS and_or VARCHAR(8) DEFAULT 'or';
-- 'or'  = alternative to previous (ANY), legacy default
-- 'and' = must be met together (ALL)

-- 2) Redeem limits on wim_promo (both per-order and lifetime; NULL/0 = unlimited)
ALTER TABLE wim_promo ADD COLUMN IF NOT EXISTS redeem_limit_per_order INT;
ALTER TABLE wim_promo ADD COLUMN IF NOT EXISTS redeem_limit_lifetime INT;

-- 3) Lifetime usage counter
CREATE TABLE IF NOT EXISTS wim_promo_usage (
    promo_id   INT NOT NULL REFERENCES wim_promo(id) ON DELETE CASCADE,
    used_count INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (promo_id)
);

-- 4) Grants for wim_app
GRANT SELECT, INSERT, UPDATE, DELETE ON wim_promo_conditions TO wim_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON wim_promo TO wim_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON wim_promo_usage TO wim_app;
-- wim_promo_usage PK is promo_id (no serial sequence); wim_app inserts promo_id explicitly.
-- Existing serial sequences (conditions/rewards) already granted by prior migrations.
-- ============================================================
-- WIM Online — Post-Review additive migration (M2-M4)
-- ALL statements are additive & reversible (IF NOT EXISTS /
-- ADD COLUMN IF NOT EXISTS). No data destruction.
-- Apply: psql -f this file against wim_sfa.
-- Revert: DROP TABLE / DROP COLUMN the items you don't want.
-- ============================================================

-- ── B. Invoice & Receivables (P2) ────────────────────────────
CREATE TABLE IF NOT EXISTS wim_invoice (
    id SERIAL PRIMARY KEY,
    invoice_no VARCHAR(40) UNIQUE NOT NULL,
    order_uuid UUID REFERENCES wim_orders(uuid) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'unpaid',   -- unpaid | paid | partial
    subtotal DECIMAL(15,2) DEFAULT 0,
    discount DECIMAL(15,2) DEFAULT 0,
    promo_value DECIMAL(15,2) DEFAULT 0,
    grand_total DECIMAL(15,2) DEFAULT 0,
    customer_name VARCHAR(255),
    issued_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_invoice_order ON wim_invoice(order_uuid);
CREATE INDEX IF NOT EXISTS idx_invoice_status ON wim_invoice(status);

CREATE TABLE IF NOT EXISTS wim_payment (
    id SERIAL PRIMARY KEY,
    invoice_id INT REFERENCES wim_invoice(id) ON DELETE CASCADE,
    amount DECIMAL(15,2) NOT NULL,
    method VARCHAR(30) DEFAULT 'cash',      -- cash | credit | transfer | cod
    paid_at TIMESTAMP DEFAULT NOW(),
    note TEXT,
    created_by INT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_payment_invoice ON wim_payment(invoice_id);

-- ── C. Stock on-hand (P4) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS wim_stock_balance (
    id SERIAL PRIMARY KEY,
    product_id INT,
    product_sku VARCHAR(50),
    depot_id INT,
    qty DECIMAL(15,3) DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    changed_by INT,
    source VARCHAR(30) DEFAULT 'seed',      -- seed | adjustment | import
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_stock_balance_prod_depo ON wim_stock_balance(product_id, depot_id);

-- ── D. Store enrichment (P5 reduced) ──────────────────────────
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS assigned_salesperson_id INT REFERENCES wim_users(id);
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS credit_limit DECIMAL(15,2) DEFAULT 0;
-- (region_id already exists on wim_stores; add FK if missing)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stores_region') THEN
        ALTER TABLE wim_stores ADD CONSTRAINT fk_stores_region FOREIGN KEY (region_id) REFERENCES wim_regions(id);
    END IF;
END $$;

-- ── E. Order/product additive nullable columns ────────────────
ALTER TABLE wim_orders ADD COLUMN IF NOT EXISTS requested_delivery_date DATE;
ALTER TABLE wim_products ADD COLUMN IF NOT EXISTS barcode VARCHAR(64);
-- verified_at used by POST /api/orders/verify (order verification timestamp)
ALTER TABLE wim_orders ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP;
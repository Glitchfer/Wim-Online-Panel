-- 01-schema.sql — WIM Online PostgreSQL schema (wim_sfa)
-- Clean, organized 32-table design. See DATABASE-MAPPING.md for the source of truth.
-- This runs once on first wim-db container init (docker-entrypoint-initdb.d).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ═══════════════════════════════════════════
-- AUTH & USERS
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_users (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) DEFAULT 'sales' NOT NULL,
    phone VARCHAR(30),
    status VARCHAR(20) DEFAULT 'active',
    driver_uuid VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_role ON wim_users(role);

CREATE TABLE IF NOT EXISTS wim_sessions (
    id VARCHAR(64) PRIMARY KEY,
    user_id INT REFERENCES wim_users(id),
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wim_api_keys (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    scope TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wim_user_meta (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES wim_users(id),
    jenis_sales VARCHAR(30),
    depot_id INT,
    depot_ids INT[],
    photo_url TEXT,
    vehicle_id VARCHAR(50),
    nik VARCHAR(30),
    npwp VARCHAR(30),
    alamat TEXT,
    tanggal_bergabung DATE,
    supervisor_id INT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id)
);

-- ═══════════════════════════════════════════
-- STORES / NOO
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_stores (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    address TEXT,
    city VARCHAR(100),
    province VARCHAR(100),
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    owner_name VARCHAR(255),
    phone VARCHAR(30),
    channel VARCHAR(50),
    category VARCHAR(100),
    nik VARCHAR(30),
    npwp VARCHAR(30),
    npwp_name VARCHAR(255),
    kendaraan VARCHAR(50),
    kode_pos VARCHAR(10),
    kelurahan VARCHAR(100),
    kecamatan VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    region_id INT,
    meta JSONB,
    fleetbase_place_uuid UUID,
    created_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stores_city ON wim_stores(city, channel, category);
CREATE INDEX IF NOT EXISTS idx_stores_geo ON wim_stores(latitude, longitude);

CREATE TABLE IF NOT EXISTS wim_store_contacts (
    id SERIAL PRIMARY KEY,
    store_id INT REFERENCES wim_stores(id),
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    role VARCHAR(50),
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wim_store_photos (
    id SERIAL PRIMARY KEY,
    visit_id INT,
    store_id INT REFERENCES wim_stores(id),
    photo_data TEXT NOT NULL,
    description TEXT,
    photo_type VARCHAR(30),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wim_store_relations (
    id SERIAL PRIMARY KEY,
    store_id INT REFERENCES wim_stores(id),
    related_store_id INT REFERENCES wim_stores(id),
    relation_type VARCHAR(50),
    notes TEXT
);

-- ═══════════════════════════════════════════
-- PRODUCTS
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_products (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    sku VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    price DECIMAL(15,2) DEFAULT 0,
    brand VARCHAR(100),
    category VARCHAR(100),
    unit VARCHAR(30) DEFAULT 'karton',
    qty_per_unit INT DEFAULT 1,
    weight DECIMAL(10,2) DEFAULT 0,
    weight_unit VARCHAR(10) DEFAULT 'pcs',
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    meta JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_products_brand ON wim_products(brand);
CREATE INDEX IF NOT EXISTS idx_products_category ON wim_products(category);

CREATE TABLE IF NOT EXISTS wim_product_prices (
    id SERIAL PRIMARY KEY,
    product_id INT REFERENCES wim_products(id),
    price DECIMAL(15,2) NOT NULL,
    effective_date DATE NOT NULL,
    set_by INT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════
-- DEPOT & TERRITORY
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_regions (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL UNIQUE,
    kode_area VARCHAR(20) UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wim_depots (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    address TEXT,
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    radius_m INT DEFAULT 50,
    kode_depo VARCHAR(20),
    region_id INT REFERENCES wim_regions(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wim_depot_stores (
    id SERIAL PRIMARY KEY,
    depot_id INT REFERENCES wim_depots(id),
    store_uuid UUID NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (depot_id, store_uuid)
);

CREATE TABLE IF NOT EXISTS wim_depot_products (
    id SERIAL PRIMARY KEY,
    depot_id INT REFERENCES wim_depots(id),
    product_id INT REFERENCES wim_products(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (depot_id, product_id)
);

-- ═══════════════════════════════════════════
-- VISIT PLAN
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_visit_plan (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES wim_users(id),
    place_uuid UUID NOT NULL,
    visit_date DATE NOT NULL,
    source VARCHAR(20) DEFAULT 'route',
    visit_order INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, place_uuid, visit_date)
);
CREATE INDEX IF NOT EXISTS idx_visit_plan_date ON wim_visit_plan(user_id, visit_date);

CREATE TABLE IF NOT EXISTS wim_visit_plan_templates (
    id SERIAL PRIMARY KEY,
    depot_id INT REFERENCES wim_depots(id),
    user_id INT REFERENCES wim_users(id),
    nama_template VARCHAR(100),
    week_number INT,
    day_of_week INT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wim_visit_plan_template_stores (
    id SERIAL PRIMARY KEY,
    template_id INT REFERENCES wim_visit_plan_templates(id),
    store_uuid UUID NOT NULL,
    visit_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════
-- VISITS
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_visits (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES wim_users(id),
    place_uuid UUID NOT NULL,
    place_name VARCHAR(255),
    checkin_at TIMESTAMP,
    checkout_at TIMESTAMP,
    duration_seconds INT,
    status VARCHAR(30) DEFAULT 'checkin',
    photos TEXT DEFAULT '[]',
    notes TEXT,
    location_lat DECIMAL(10,7),
    location_lng DECIMAL(10,7),
    source VARCHAR(20),
    geofence_status VARCHAR(20),
    depot_id INT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_visits_user_date ON wim_visits(user_id, checkin_at);
CREATE INDEX IF NOT EXISTS idx_visits_open ON wim_visits(user_id) WHERE checkout_at IS NULL;

-- ═══════════════════════════════════════════
-- ATTENDANCE
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_attendance (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES wim_users(id),
    date DATE NOT NULL,
    clock_in VARCHAR(10),
    clock_out VARCHAR(10),
    clock_in_photo TEXT,
    clock_out_photo TEXT,
    duration VARCHAR(20),
    location_lat DECIMAL(10,7),
    location_lng DECIMAL(10,7),
    geofence_status VARCHAR(20),
    depot_id INT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, date)
);

-- ═══════════════════════════════════════════
-- ORDERS
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_orders (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    user_id INT REFERENCES wim_users(id),
    store_id INT,
    store_uuid UUID,
    visit_id INT,
    order_ref VARCHAR(30),
    status VARCHAR(30) DEFAULT 'pending',
    total DECIMAL(15,2) DEFAULT 0,
    payment_method VARCHAR(30) DEFAULT 'cod',
    notes TEXT,
    source VARCHAR(20) DEFAULT 'route',
    off_route_reason TEXT,
    items JSONB DEFAULT '[]'::jsonb,
    promos_applied JSONB DEFAULT '[]'::jsonb,
    verification_status VARCHAR(30) DEFAULT 'pending',
    sales_channel VARCHAR(30) DEFAULT 'app',
    synced_to_fleetbase BOOLEAN DEFAULT FALSE,
    fleetbase_order_uuid UUID,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_user ON wim_orders(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_store ON wim_orders(store_id, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON wim_orders(status);

CREATE TABLE IF NOT EXISTS wim_order_items (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES wim_orders(id),
    product_id INT,
    product_name VARCHAR(255),
    product_sku VARCHAR(50),
    quantity INT NOT NULL,
    unit_price DECIMAL(15,2) NOT NULL,
    total_price DECIMAL(15,2) NOT NULL,
    is_bonus BOOLEAN DEFAULT FALSE,
    promo_ref VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON wim_order_items(order_id);

CREATE TABLE IF NOT EXISTS wim_order_status_log (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES wim_orders(id),
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    changed_by INT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════
-- STOCK
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_stock_check (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES wim_users(id),
    visit_id INT,
    place_uuid UUID NOT NULL,
    product_id INT,
    sku VARCHAR(50) NOT NULL,
    qty INT DEFAULT 0,
    previous_stock INT DEFAULT 0,
    last_order_qty INT DEFAULT 0,
    checked_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stock_store_sku ON wim_stock_check(place_uuid, sku, checked_at DESC);

-- ═══════════════════════════════════════════
-- PROMO
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_promo (
    id SERIAL PRIMARY KEY,
    promo_ref VARCHAR(50) UNIQUE NOT NULL,
    nama VARCHAR(255) NOT NULL,
    jenis VARCHAR(30) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    priority INT DEFAULT 0,
    stackable BOOLEAN DEFAULT FALSE,
    region_id INT REFERENCES wim_regions(id),
    periode_start DATE,
    periode_end DATE,
    min_transaction_amount DECIMAL(15,2),
    max_discount_amount DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wim_promo_conditions (
    id SERIAL PRIMARY KEY,
    promo_id INT REFERENCES wim_promo(id),
    condition_type VARCHAR(50) NOT NULL,
    condition_value VARCHAR(255),
    condition_product_id INT
);

CREATE TABLE IF NOT EXISTS wim_promo_rewards (
    id SERIAL PRIMARY KEY,
    promo_id INT REFERENCES wim_promo(id),
    reward_type VARCHAR(50) NOT NULL,
    reward_value VARCHAR(255),
    reward_sku_ref VARCHAR(50),
    reward_qty INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS wim_promo_assignments (
    id SERIAL PRIMARY KEY,
    promo_id INT REFERENCES wim_promo(id),
    target_type VARCHAR(30),
    target_id INT,
    target_value VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════
-- ADMIN / RBAC
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_admin_depot_access (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES wim_users(id),
    depot_id INT REFERENCES wim_depots(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, depot_id)
);

-- ═══════════════════════════════════════════
-- AUDIT / SYNC / CONFIG
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_audit_log (
    id SERIAL PRIMARY KEY,
    user_id INT,
    action VARCHAR(100),
    entity_type VARCHAR(50),
    entity_id INT,
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON wim_audit_log(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS wim_sync_queue (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INT NOT NULL,
    action VARCHAR(20) NOT NULL,
    target VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    payload JSONB,
    error TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    synced_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sync_status ON wim_sync_queue(status, target, created_at);

CREATE TABLE IF NOT EXISTS wim_sync_log (
    id SERIAL PRIMARY KEY,
    queue_id INT REFERENCES wim_sync_queue(id),
    entity_type VARCHAR(50),
    entity_id INT,
    target VARCHAR(50) NOT NULL,
    action VARCHAR(20),
    status VARCHAR(20),
    external_ref VARCHAR(100),
    request_payload JSONB,
    response_payload JSONB,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wim_app_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    description TEXT,
    updated_by INT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════
-- DEFAULT CONFIG SEED
-- ═══════════════════════════════════════════
INSERT INTO wim_app_config (config_key, config_value, description) VALUES
    ('min_visit_seconds', '"180"', 'Minimum visit duration in seconds'),
    ('geofence_radius_m', '"50"', 'Geofence radius in meters'),
    ('app_name', '"WIM Online"', 'Application display name')
ON CONFLICT (config_key) DO NOTHING;

-- ═══════════════════════════════════════════════════
-- Area-based pricing (2026-09-10)
-- A product can have a price per region (area); base wim_products.price is default.
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wim_product_prices (
    id SERIAL PRIMARY KEY,
    product_uuid UUID NOT NULL REFERENCES wim_products(uuid),
    region_id INT NOT NULL REFERENCES wim_regions(id),
    price DECIMAL(15,2) NOT NULL,
    effective_from DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(product_uuid, region_id)
);
CREATE INDEX IF NOT EXISTS idx_product_prices_region ON wim_product_prices(region_id);
CREATE INDEX IF NOT EXISTS idx_product_prices_product ON wim_product_prices(product_uuid);

-- Promo applicability by region (multi-area)
CREATE TABLE IF NOT EXISTS wim_promo_regions (
    promo_id INT NOT NULL REFERENCES wim_promo(id),
    region_id INT NOT NULL REFERENCES wim_regions(id),
    PRIMARY KEY(promo_id, region_id)
);

-- Sales positions tracking (2026-09-10) — every reported sales geolocation
CREATE TABLE IF NOT EXISTS wim_sales_positions (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES wim_users(id),
    user_name VARCHAR(255),
    latitude DECIMAL(10,7) NOT NULL,
    longitude DECIMAL(10,7) NOT NULL,
    accuracy_m DECIMAL(10,2),
    source VARCHAR(20) DEFAULT 'app',
    recorded_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sales_positions_user ON wim_sales_positions(user_id);
CREATE INDEX IF NOT EXISTS idx_sales_positions_time ON wim_sales_positions(recorded_at);

-- Rencana kunjungan rework (2026-09-10) — check-in selfie separate from foto tambahan,
-- and numbered visit-plan ordering for the drag-drop editor
ALTER TABLE wim_visits ADD COLUMN IF NOT EXISTS checkin_photo TEXT;
ALTER TABLE wim_visit_plan ADD COLUMN IF NOT EXISTS seq_no INT DEFAULT 0;
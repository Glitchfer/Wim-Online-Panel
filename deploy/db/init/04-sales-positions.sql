-- Sales positions tracking (2026-09-10)
-- Saves every reported sales/user geolocation (recorded each time they hit the API),
-- timestamped so it can be joined to visits/orders/absensi later.
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

GRANT SELECT, INSERT, UPDATE, DELETE ON wim_sales_positions TO wim_app;
GRANT USAGE, SELECT ON SEQUENCE wim_sales_positions_id_seq TO wim_app;

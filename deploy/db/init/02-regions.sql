-- WIM Online — Add regions + depot.region_id (2026-09-10)
CREATE TABLE IF NOT EXISTS wim_regions (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL UNIQUE,
    kode_area VARCHAR(20) UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE wim_depots ADD COLUMN IF NOT EXISTS region_id INT REFERENCES wim_regions(id);

-- Seed major regions (JABODETABEK, Jawa Tengah, Jawa Timur, ...)
INSERT INTO wim_regions (name, kode_area, description) VALUES
    ('JABODETABEK', 'REG-JAB', 'Jakarta Metro: Jakarta, Bogor, Delhi, Taralabek, Bekasi'),
    ('Jawa Tengah', 'REG-JT', 'Central Java'),
    ('Jawa Timur',  'REG-JE', 'Eastern Java'),
    ('Jawa Barat',  'REG-JB', 'Western Java'),
    ('Luar Jawa',   'REG-LJ', 'Outside Java (other islands)')
ON CONFLICT (name) DO NOTHING;

-- Link existing Jakarta depots to JABODETABEK
UPDATE wim_depots SET region_id = (SELECT id FROM wim_regions WHERE name='JABODETABEK')
WHERE region_id IS NULL AND (name ILIKE '%Jakarta%' OR name ILIKE '%Gudang%' OR kode_depo ILIKE 'GDG%' OR kode_depo ILIKE 'DEP%');
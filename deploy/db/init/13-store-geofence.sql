-- WIM Online — store geofence radius (additive & reversible)
-- Per-store geofence radius override (meters) for the sales-app visit popup.
-- NULL => use the app default (100 m).
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS geofence_radius_m INT;
GRANT SELECT, UPDATE ON wim_stores TO wim_app;
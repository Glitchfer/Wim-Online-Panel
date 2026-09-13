-- Rencana kunjungan rework (2026-09-10)
-- 1) Separate the check-in selfie from "foto tambahan" (merchandise photos).
--    wim_visits.checkin_photo holds the salesperson's selfie taken at check-in;
--    wim_visits.photos keeps the "foto tambahan" (merchandise) array as today.
ALTER TABLE wim_visits ADD COLUMN IF NOT EXISTS checkin_photo TEXT;

-- 2) wim_visit_plan gains ordering so the admin can drag-drop a numbered kunjungan list per
--    (user, day). seq_no = order in the list for that user+date.
ALTER TABLE wim_visit_plan ADD COLUMN IF NOT EXISTS seq_no INT DEFAULT 0;

GRANT SELECT, INSERT, UPDATE, DELETE ON wim_visits TO wim_app;

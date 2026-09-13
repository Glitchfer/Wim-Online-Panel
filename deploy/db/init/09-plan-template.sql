-- ============================================================
-- WIM Online — Plan-Edit template rework (additive & reversible)
-- Adds UNIQUE constraints + resolver/materializer functions for the
-- monthly-repeating route template (day1..day6 x week1..week4).
-- wim_visit_plan (daily execution) is kept untouched.
-- Apply: psql -f this file against wim_sfa.
-- ============================================================

-- 1) Dedupe slot: one template per (user, week, day).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uniq_plan_tpl_slot') THEN
    ALTER TABLE wim_visit_plan_templates
      ADD CONSTRAINT uniq_plan_tpl_slot UNIQUE (user_id, week_number, day_of_week);
  END IF;
END $$;

-- 2) Dedupe store per template slot.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uniq_plan_tpl_store') THEN
    ALTER TABLE wim_visit_plan_template_stores
      ADD CONSTRAINT uniq_plan_tpl_store UNIQUE (template_id, store_uuid);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_plan_tpl_stores_order ON wim_visit_plan_template_stores(template_id, visit_order);

-- 3) Resolver: for a given date, compute week-of-month + ISODOW and return the slot's stores.
DROP FUNCTION IF EXISTS resolve_template_for_date(BIGINT, DATE);
CREATE OR REPLACE FUNCTION resolve_template_for_date(p_user_id BIGINT, p_visit_date DATE)
RETURNS TABLE(store_uuid UUID, visit_order INT) AS $$
DECLARE v_week SMALLINT; v_dow SMALLINT;
BEGIN
  v_dow := EXTRACT(ISODOW FROM p_visit_date)::SMALLINT;  -- 1=Mon..7=Sun
  IF v_dow = 7 THEN RETURN; END IF;                        -- no slot on Sunday
  v_week := LEAST(CEIL(EXTRACT(DAY FROM p_visit_date)/7.0)::SMALLINT, 4);
  RETURN QUERY
    SELECT ts.store_uuid, ts.visit_order
    FROM wim_visit_plan_template_stores ts
    JOIN wim_visit_plan_templates t ON t.id = ts.template_id
    WHERE t.user_id = p_user_id AND t.week_number = v_week AND t.day_of_week = v_dow
    ORDER BY ts.visit_order;
END; $$ LANGUAGE plpgsql STABLE;

-- 4) Materializer: reconcile a slot into wim_visit_plan for a concrete date (field execution).
--    First deletes that user+date's 'template'-sourced rows, then inserts the current template,
--    so slot edits (add/remove/reorder) propagate and stale rows are purged.
DROP FUNCTION IF EXISTS materialize_template_for_date(BIGINT, DATE);
CREATE OR REPLACE FUNCTION materialize_template_for_date(p_user_id BIGINT, p_visit_date DATE)
RETURNS INT AS $$
DECLARE r RECORD; n INT := 0;
BEGIN
  DELETE FROM wim_visit_plan WHERE user_id=p_user_id AND visit_date=p_visit_date AND source='template';
  FOR r IN SELECT * FROM resolve_template_for_date(p_user_id, p_visit_date) LOOP
    INSERT INTO wim_visit_plan (user_id, place_uuid, visit_date, source, seq_no, status)
    VALUES (p_user_id, r.store_uuid, p_visit_date, 'template', r.visit_order, 'planned')
    ON CONFLICT (user_id, place_uuid, visit_date) DO UPDATE SET seq_no=EXCLUDED.seq_no, source='template';
    n := n + 1;
  END LOOP;
  RETURN n;
END; $$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION resolve_template_for_date(BIGINT, DATE) TO wim_app;
GRANT EXECUTE ON FUNCTION materialize_template_for_date(BIGINT, DATE) TO wim_app;
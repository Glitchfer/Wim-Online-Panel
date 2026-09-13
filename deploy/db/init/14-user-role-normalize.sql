-- WIM Online — User role normalization (reversible; run in this order)
-- 1) Name contains kepala depo / kepala gudang / gudang -> depo_admin
UPDATE wim_users SET role='depo_admin'
WHERE deleted_at IS NULL AND role != 'super_admin'
  AND (LOWER(name) LIKE '%kepala depo%' OR LOWER(name) LIKE '%kepala gudang%' OR LOWER(name) LIKE '%gudang%');

-- 2) Name contains PIC / coordinator -> manager
UPDATE wim_users SET role='manager'
WHERE deleted_at IS NULL AND role != 'super_admin'
  AND (LOWER(name) LIKE '%pic%' OR LOWER(name) LIKE '%coordinator%');

-- 3) regional_manager -> manager
UPDATE wim_users SET role='manager'
WHERE deleted_at IS NULL AND role='regional_manager';
# NOO Region Dropdowns (Wilayah) — Implementation

> **Date:** 2026-09-11 · **Status:** Live & verified
> Replaces free-text provinsi/kota/kecamatan/kelurahan in the NOO form with **cascading
> searchable dropdowns** using official BPS/Kemendagri administrative codes — so addresses
> cannot be misspelled.

## Why
The NOO (New Outlet Opening) address fields were free-text (typo-prone). The user requested
4 cascading dropdowns (Provinsi → Kota/Kabupaten → Kecamatan → Kelurahan), each with a search
box when opened, narrowing to the official names. Local, no cloud dependency (user's
local-first preference).

## Data source
- Snapshot of the **BPS (Badan Pusat Statistik) + Kemendagri** administrative codes, sourced
  from `api-wilayah-indonesia-2026` via jsDelivr CDN (a static mirror of official codes).
- **Local** files in `deploy/wilayah/` (committed): `provinces.json` (38),
  `regencies.json` (514), `districts_all.json` (7285), `villages_all.json` (83762).
  → No runtime CDN dependency; works offline.
- Covers all of **Indonesia**: 38 provinces, 514 kab/kota, 7,285 kecamatan, 83,762 kelurahan.

## DB
- Table `wim_wilayah` (`deploy/db/init/07-wilayah.sql`):
  `kode` (BPS, UNIQUE), `nama`, `level` (prov/kab/kec/kel), `parent_kode`, `kode_pos`.
  Indexes on parent_kode, level, lower(nama).
- Imported **91,599 rows** into the live `wim_sfa` DB (via COPY from `deploy/wilayah/*.json`,
  granted read to `wim_app`).
- Rebuild script: `scripts/import_wilayah.py` (reads the local JSON, idempotent TRUNCATE+insert).

## API
- `GET /api/wilayah?level=prov|kab|kec|kel[&parent=<kode>][&q=<search>]` (auth: any session).
- Returns `{level, parent, rows:[{kode,nama}], total}`. Uses the local DB, ordered by name,
  LIMIT 2000; optional case-insensitive `q` filter.

## Frontend (noo.html)
- Rebuilt the "Alamat" card: 4 dropdown controls (provinsi, kota, kecamatan, kelurahan), each a
  `wilayah-dd` component with a hidden `*Kode` field.
- Cascading: opening kota loads kabupatens of the chosen province; kecamatan of the chosen
  city; kelurahan of the chosen kecamatan. Behind-the-scenes stores BPS codes.
- **Search on open**: each dropdown has a type-to-filter query box; results are official names
  only (no typos).
- "Alamat Lengkap" stays free-text for the street (jalan/no.), since it can't be a dropdown.
- `submitNOO` still reads `kota.value`/`kecamatan.value`/`provinsi.value` (now official names)
  and sends `city/province/district` to the store API; the BPS codes are retained for future
  geo/master-data use.

## Verification (manual, live)
- `GET /api/wilayah?level=prov` → 38.
- `level=kab&parent=31` → 6 (DKI Jakarta kotas incl. "Kota Administrasi Jakarta Selatan").
- `level=kec&parent=3174` → 10 (Cilandak, Jagakarsa, …).
- `level=kel&parent=317406` → 5 (Cilandak Barat, Cipete Selatan, …).
- noo.html serves on the field app; proxy to `/api/wilayah` authenticated.
- Inline JS passes `node --check`.

## Files
- `deploy/db/init/07-wilayah.sql` — table + indexes
- `deploy/wilayah/*.json` — official dataset (local)
- `scripts/import_wilayah.py` — rebuild/import
- `frontend/serve.py` — `do_WILAYAH` endpoint (+ GET route)
- `frontend/noo.html` — cascading searchable dropdowns

## Reversible / rollback
- Re-import: `python3 scripts/import_wilayah.py` after truncating `wim_wilayah`.
- Revert NOO form: restore the old free-text fields (commit before `8860b56`).
- No schema/behavior of existing features changed.
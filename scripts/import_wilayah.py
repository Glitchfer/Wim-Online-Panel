#!/usr/bin/env python3
"""
Import the WIM administrative region dataset (wilayah_id) into PostgreSQL.

Reads local JSON files from deploy/wilayah/ (provinces.json, regencies.json,
districts_all.json, villages_all.json) — a snapshot of BPS/Kemendagri codes via
api-wilayah-indonesia-2026. Populates table wim_wilayah (run 07-wilayah.sql first).

Usage:
    python3 import_wilayah.py [--pg-dsn "postgresql://user:pass@host/db"]

Defaults read from WIM_PG_* env vars (WIM_PG_HOST/PORT/DB/USER/PASS) or localhost
postgres. Idempotent: re-run deletes prior wim_wilayah rows and re-inserts.
"""
import os, sys, json, argparse

def get_conn():
    import psycopg2
    dsn = os.environ.get('WIM_PG_HOST', 'localhost')
    port = int(os.environ.get('WIM_PG_PORT', '5432'))
    db   = os.environ.get('WIM_PG_DB', 'wim_sfa')
    user = os.environ.get('WIM_PG_USER', 'postgres')
    pw   = os.environ.get('WIM_PG_PASS', '')
    return psycopg2.connect(host=dsn, port=port, dbname=db, user=user, password=pw)

def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=os.path.join(os.path.dirname(__file__), '..', 'deploy', 'wilayah'))
    ap.add_argument('--dsn', default=None)
    args = ap.parse_args()
    d = os.path.abspath(args.dir)
    provinces = load(os.path.join(d, 'provinces.json'))
    regencies = load(os.path.join(d, 'regencies.json'))
    districts = load(os.path.join(d, 'districts_all.json'))
    villages  = load(os.path.join(d, 'villages_all.json'))
    print(f"Loaded prov={len(provinces)} kab={len(regencies)} kec={len(districts)} kel={len(villages)}")

    conn = get_conn() if not args.dsn else None
    if args.dsn:
        import psycopg2
        conn = psycopg2.connect(args.dsn)
    cur = conn.cursor()
    cur.execute("TRUNCATE wim_wilayah RESTART IDENTITY")
    rows = []
    for p in provinces:
        rows.append((p['id'], p['name'], 'prov', None, None))
    for r in regencies:
        rows.append((r['id'], r['name'], 'kab', r.get('provinceId'), None))
    for s in districts:
        rows.append((s['id'], s['name'], 'kec', s.get('regencyId'), None))
    for v in villages:
        parent = v.get('districtId') or (v['id'][:6] if len(v['id']) >= 6 else None)
        rows.append((v['id'], v['name'], 'kel', parent, v.get('kodepos')))
    # Bulk insert in chunks
    CH = 5000
    for i in range(0, len(rows), CH):
        chunk = rows[i:i+CH]
        args_sql = ','.join(['(%s,%s,%s,%s,%s)'] * len(chunk))
        flat = [x for row in chunk for x in row]
        cur.execute(
            f"INSERT INTO wim_wilayah (kode, nama, level, parent_kode, kode_pos) VALUES {args_sql} "
            f"ON CONFLICT (kode) DO UPDATE SET nama=EXCLUDED.nama, level=EXCLUDED.level, "
            f"parent_kode=EXCLUDED.parent_kode, kode_pos=EXCLUDED.kode_pos", flat)
    conn.commit()
    cur.execute("SELECT count(*), COUNT(*) FILTER (WHERE level='prov'), COUNT(*) FILTER (WHERE level='kab'), "
                "COUNT(*) FILTER (WHERE level='kec'), COUNT(*) FILTER (WHERE level='kel') FROM wim_wilayah")
    print("Imported:", cur.fetchone())
    cur.close(); conn.close()
    print("OK")

if __name__ == '__main__':
    main()
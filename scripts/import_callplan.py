#!/usr/bin/env python3
"""Import Call Plan Sales (rencana kunjungan) into wim_sfa. Idempotent/additive.
Pre-loads store_code->uuid, employee_code->user_id, depot name->id; then for
each slot (week,day,store) upserts the template + store link."""
import csv, uuid as U, psycopg2, sys
CSV=sys.argv[1] if len(sys.argv)>1 else '/tmp/callplan_slots.csv'
DB=dict(host='192.168.6.110', dbname='wim_sfa', user='wim_app', password='wim_app_sfa_2026')
c=psycopg2.connect(**DB); c.set_client_encoding('UTF8'); cur=c.cursor()

print("preloading...")
cur.execute("SELECT store_code, uuid FROM wim_stores WHERE store_code IS NOT NULL AND deleted_at IS NULL")
store_map={_r[0]:_r[1] for _r in cur.fetchall()}
cur.execute("SELECT employee_code, user_id FROM wim_user_meta WHERE employee_code IS NOT NULL")
emp_map={_r[0]:_r[1] for _r in cur.fetchall()}
cur.execute("SELECT name, id FROM wim_depots")
depot_map={_r[0]:_r[1] for _r in cur.fetchall()}
print(f"cached stores={len(store_map)} emps={len(emp_map)} depots={len(depot_map)}")

new_stores=0; new_emps=0; new_depots=0
def get_store(code,name,lat,lng,addr,kec,kel,kota,prov,did):
    global new_stores
    if code in store_map: return store_map[code]
    su=str(U.uuid4())
    try:
        cur.execute("INSERT INTO wim_stores (uuid,store_code,name,latitude,longitude,address,kecamatan,kelurahan,city,province,depot_id,status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active') RETURNING uuid",
                    (su,code,name or 'Tanpa Nama', float(lat) if lat else None, float(lng) if lng else None,
                     addr or '', kec or '', kel or '', kota or '', prov or '', did))
        store_map[code]=su; new_stores+=1; return su
    except Exception:
        return None

def get_emp(code,name):
    global new_emps
    if code in emp_map: return emp_map[code]
    if name:
        cur.execute("SELECT id FROM wim_users WHERE LOWER(name)=LOWER(%s) AND deleted_at IS NULL LIMIT 1",(name,))
        r=cur.fetchone()
        if r:
            try: cur.execute("INSERT INTO wim_user_meta (user_id,employee_code) VALUES (%s,%s) ON CONFLICT (user_id) DO UPDATE SET employee_code=EXCLUDED.employee_code",(r[0],code))
            except: pass
            emp_map[code]=r[0]; return r[0]
    return None

def get_depot(name):
    global new_depots
    if name in depot_map: return depot_map[name]
    cur.execute("INSERT INTO wim_depots (name,is_active) VALUES (%s,TRUE) RETURNING id",(name,))
    depot_map[name]=cur.fetchone()[0]; new_depots+=1; return depot_map[name]

nrow=0; n_slot=0; miss_store=0; miss_emp=0
order={}
with open(CSV, encoding='utf-8') as f:
    rd=csv.reader(f); next(rd,None)
    for row in rd:
        row=(row+['']*14)[:14]
        depot,ecode,ename,scode,sname,week,day,lat,lng,addr,kec,kel,kota,prov=row
        nrow+=1
        did=get_depot(depot) if depot else None
        su=get_store(scode,sname,lat,lng,addr,kec,kel,kota,prov,did)
        if not su: miss_store+=1; continue
        uid=get_emp(ecode,ename)
        if not uid: miss_emp+=1; continue
        key=(uid,int(week),int(day)); order[key]=order.get(key,0)+1
        cur.execute("""INSERT INTO wim_visit_plan_templates (user_id,week_number,day_of_week)
                       VALUES (%s,%s,%s) ON CONFLICT (user_id,week_number,day_of_week) DO UPDATE SET week_number=EXCLUDED.week_number RETURNING id""",
                    (uid,int(week),int(day)))
        tid=cur.fetchone()[0]
        cur.execute("""INSERT INTO wim_visit_plan_template_stores (template_id,store_uuid,visit_order)
                       VALUES (%s,%s,%s) ON CONFLICT (template_id,store_uuid) DO NOTHING""",(tid,su,order[key]))
        n_slot+=1
        if nrow%50000==0: c.commit(); print(f"..{nrow} rows, {n_slot} slots")
c.commit()
print(f"DONE rows={nrow} slots={n_slot} new_stores={new_stores} new_emps={new_emps} new_depots={new_depots} miss_store={miss_store} miss_emp={miss_emp}")
cur.close(); c.close()
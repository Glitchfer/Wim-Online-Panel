#!/usr/bin/env python3
"""
WIM Online — Goovi/Klikorder CSV import (weights: reference data).
Stages: vehicles | depots | users | customers
Reads /root/goovi/*.csv. Upserts, skips MOCK/TRIAL rows. Idempotent.
Run on middleware LXC (has psycopg2).
"""
import sys, csv, re
import psycopg2

DB=dict(host='192.168.6.110', dbname='wim_sfa', user='wim_app', password='wim_app_sfa_2026')
BASE='/root/goovi'
MOCK=re.compile(r'(?i)mock|trial|dummy|qa[_-]?e2e|percobaan|(?:^|\W)test(?:\W|$)|prueba|\buji\b|contoh')

def conn_():
    c=psycopg2.connect(**DB); c.set_client_encoding('UTF8'); return c
def cl(v): return '' if v is None else str(v).strip()

def rows(fname):
    with open(f'{BASE}/{fname}', newline='', encoding='utf-8-sig') as f:
        for r in csv.reader(f): yield ['' if c is None else c for c in r]

def is_mock(*vals):
    return any(MOCK.search(v) for v in vals if v)

# ── 1. Vehicles ──
def stage_vehicles():
    c=conn_(); cur=c.cursor(); n=0
    data=list(rows('kendaraan.csv'))
    for r in data[1:]:
        if len(r)<3: continue
        kode=cl(r[0]); plat=cl(r[1]); jenis=cl(r[2]); kub=cl(r[3]); berat=cl(r[4]); depo=cl(r[5])
        if not kode or is_mock(kode,plat,depo): continue
        did=None
        if depo:
            tail=depo.split(' - ')[-1].strip()
            cur.execute("SELECT id FROM wim_depots WHERE name ILIKE %s ORDER BY id LIMIT 1", ('%'+tail[:6]+'%',))
            row=cur.fetchone()
            if row: did=row[0]
        cur.execute("INSERT INTO wim_vehicles (kode,plat_no,jenis,kubikasi,berat_jenis,depot_id) VALUES (%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (kode) DO UPDATE SET plat_no=EXCLUDED.plat_no,jenis=EXCLUDED.jenis,kubikasi=EXCLUDED.kubikasi,berat_jenis=EXCLUDED.berat_jenis,depot_id=EXCLUDED.depot_id",
                    (kode,plat,jenis,float(kub) if kub else 0, float(berat) if berat else 0, did))
        n+=cur.rowcount
    c.commit(); cur.close(); c.close(); print('vehicles upserted', n)

# ── 2. Depots ──
def stage_depots():
    c=conn_(); cur=c.cursor(); n=0
    seen=set()
    for f in ('user.csv','karyawan.csv'):
        data=list(rows(f))
        # header row detect
        hdr=0
        for i,r in enumerate(data[:5]):
            if any('Depo' in str(x) for x in r): hdr=i; break
        for r in data[hdr+1:]:
            # find the depo column: user.csv col0, karyawan.csv col2
            name = cl(r[0]) if f=='user.csv' else cl(r[2]) if f=='karyawan.csv' else ''
            if name and name not in seen and not is_mock(name):
                seen.add(name)
                # derive kode from depot name token
                kode = 'DP-'+str(len(seen)).zfill(3)
                cur.execute("INSERT INTO wim_depots (name,kode_depo,is_active) VALUES (%s,%s,TRUE) "
                            "ON CONFLICT DO NOTHING", (name,kode))
                n+=cur.rowcount
    c.commit(); cur.close(); c.close(); print('depots upserted', n, 'unique', len(seen))

# ── 3. Users + user_meta (from Data_User) ──
def stage_users():
    c=conn_(); cur=c.cursor(); n=0
    data=list(rows('user.csv'))
    # header: Nama Depo, Kode Karyawan, Nama Karyawan, Username, Role, Status, Jenis Sales, ...
    hdr=0
    for i,r in enumerate(data[:5]):
        if 'Username' in r: hdr=i; break
    placeholder_hash='$2b$12$importgooviplaceholder2026DoNotUseLogin.0'  # never logs in
    for r in data[hdr+1:]:
        if len(r)<7: continue
        depo=cl(r[0]); emp_code=cl(r[1]); name=cl(r[2]); username=cl(r[3]); role=cl(r[4]); status=cl(r[5]); jns=cl(r[6])
        if not name or is_mock(name,username,depo): continue
        # email: username@wim.sales (username often like 'Audrey123')
        email=(username or name.replace(' ','').lower())+'@wim.sales'
        role_map={'Sales':'sales','Admin':'admin','Delivery':'delivery','Kadep':''}
        rl='sales' if role.lower()=='sales' else ('delivery' if role.lower()=='delivery' else 'sales')
        # depot id
        did=None
        if depo:
            cur.execute("SELECT id FROM wim_depots WHERE name=%s ORDER BY id LIMIT 1",(depo,))
            row=cur.fetchone()
            if row: did=row[0]
        # upsert user by email
        cur.execute("INSERT INTO wim_users (email,name,password_hash,role,status) VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (email) DO UPDATE SET name=EXCLUDED.name,role=EXCLUDED.role,status=EXCLUDED.status RETURNING id",
                    (email,name,placeholder_hash,rl,'active' if status.lower()!='non aktif' else 'active'))
        row=cur.fetchone()
        uid=row[0] if row else None
        if uid:
            cur.execute("INSERT INTO wim_user_meta (user_id,depot_id,jenis_sales,employee_code) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT (user_id) DO UPDATE SET depot_id=EXCLUDED.depot_id,jenis_sales=EXCLUDED.jenis_sales,employee_code=EXCLUDED.employee_code",
                        (uid,did,jns or None,emp_code or None))
        n+=1
        if n%100==0: c.commit()
    c.commit(); cur.close(); c.close(); print('users upserted', n)

# ── 4. Customers / stores (from Data_Pelanggan) ──
def stage_customers():
    c=conn_(); cur=c.cursor(); n=0
    data=list(rows('pelanggan.csv'))
    hdr=0
    for i,r in enumerate(data[:5]):
        if 'Nama' in r and 'Kode' in r: hdr=i; break
    # build wilayah lookup: province_id/city_id/kecamatan_id/kelurahan_id by name
    cur.execute("SELECT kode,nama,level FROM wim_wilayah")
    wil={}
    for k,nm,lv in cur.fetchall():
        wil.setdefault(lv,{})[nm.lower()]=k
    def code4(lvl,name):
        return wil.get(lvl,{}).get((name or '').strip().lower())
    for rr in data[hdr+1:]:
        if len(rr)<14: continue
        scode=cl(rr[0]); name=cl(rr[1])
        lng=rr[2]; lat=rr[3]
        depo=cl(rr[4]); sales=cl(rr[5]); channel=cl(rr[6]); cat=cl(rr[7])
        owner=cl(rr[8]); contact=cl(rr[9]); phone=cl(rr[10]).lstrip("'"); phil=cl(rr[11])
        addr=cl(rr[12]); pos=cl(rr[13])
        nik=cl(rr[14]); npwp=cl(rr[15]); npwp_name=cl(rr[16])
        kec=cl(rr[17]); kel=cl(rr[18]); kota=cl(rr[19]); prov=cl(rr[20])
        if not scode and not name: continue
        if is_mock(scode,name): continue
        # depot
        did=None
        if depo:
            cur.execute("SELECT id FROM wim_depots WHERE name=%s ORDER BY id LIMIT 1",(depo,))
            row=cur.fetchone()
            if row: did=row[0]
        # sales rep
        sid=None
        if sales:
            cur.execute("SELECT u.id FROM wim_users u WHERE LOWER(u.name)=LOWER(%s) AND u.role='sales' LIMIT 1",(sales,))
            row=cur.fetchone()
            if row: sid=row[0]
        prov_id=code4('prov',prov); kota_id=code4('kab',kota); kec_id=code4('kec',kec); kel_id=code4('kel',kel)
        try:
            lat_f=float(lat) if lat not in (None,'') else None
            lng_f=float(lng) if lng not in (None,'') else None
        except: lat_f=lng_f=None
        try:
            cur.execute("INSERT INTO wim_stores (store_code,name,latitude,longitude,depot_id,assigned_salesperson_id,channel,category,owner_name,phone,phone_verified,address,kode_pos,nik,npwp,npwp_name,kecamatan,kelurahan,city,province,province_id,city_id,kecamatan_id,kelurahan_id,status) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active') "
                        "ON CONFLICT (store_code) DO UPDATE SET name=EXCLUDED.name,latitude=EXCLUDED.latitude,longitude=EXCLUDED.longitude,"
                        "province_id=EXCLUDED.province_id,city_id=EXCLUDED.city_id,kecamatan_id=EXCLUDED.kecamatan_id,kelurahan_id=EXCLUDED.kelurahan_id",
                        (scode or None,name,lat_f,lng_f,did,sid,channel,cat,owner,phone,phil,addr,pos,nik,npwp,npwp_name,kec,kel,kota,prov,prov_id,kota_id,kec_id,kel_id))
            n+=cur.rowcount
        except Exception as e:
            sys.stderr.write('skip store {}\n'.format(e)[:140])
        if n%200==0: c.commit()
    c.commit(); cur.close(); c.close(); print('customers upserted', n)

if __name__=='__main__':
    s=sys.argv[1] if len(sys.argv)>1 else 'vehicles'
    {'vehicles':stage_vehicles,'depots':stage_depots,'users':stage_users,'customers':stage_customers}.get(s, lambda: print('unknown'))()
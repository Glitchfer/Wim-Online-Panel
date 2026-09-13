#!/usr/bin/env python3
"""
WIM Online — Standalone PostgreSQL Frontend Server
Serves static files + WIM API (no Fleetbase dependency)
Auth via wim_users (bcrypt), all data in PostgreSQL wim_* tables
"""
import http.server
import os, sys, json, time, threading, hashlib, secrets, datetime, math
import bcrypt
import psycopg2
import psycopg2.extras
import uuid as libuuid
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get('PORT', 8080))
MIN_VISIT_SECONDS = int(os.environ.get('MIN_VISIT_SECONDS', '180'))
DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'wim-server.log')
LOG_LOCK = threading.Lock()

# PostgreSQL config
PG_HOST = os.environ.get('WIM_PG_HOST', '127.0.0.1')
PG_PORT = int(os.environ.get('WIM_PG_PORT', '5432'))
PG_DB = os.environ.get('WIM_PG_DB', 'wim_sfa')
PG_USER = os.environ.get('WIM_PG_USER', 'postgres')
PG_PASS = os.environ.get('WIM_PG_PASS', 'wim_postgres_2026')

os.makedirs(LOG_DIR, exist_ok=True)

def write_log(level, context, message, data=None):
    entry = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'level': level, 'context': context, 'message': message, 'data': data if data else None}
    line = json.dumps(entry, default=str)
    with LOG_LOCK:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 5*1024*1024:
            rotate = LOG_FILE + '.1'
            if os.path.exists(rotate): os.remove(rotate)
            os.rename(LOG_FILE, rotate)
        with open(LOG_FILE, 'a') as f: f.write(line + '\n')
    print(f"[{entry['ts']}] [{level}] [{context}] {message}")

def generate_session_id(): return secrets.token_hex(32)

# ── PostgreSQL connection
PG_CONN_PARAMS = {
    'host': PG_HOST,
    'port': PG_PORT,
    'dbname': PG_DB,
    'user': PG_USER,
    'password': PG_PASS,
    'connect_timeout': 5,
}

from queue import Queue, Empty
CONN_POOL = Queue(maxsize=20)

def get_pg():
    try:
        try:
            conn = CONN_POOL.get_nowait()
            try:
                conn.ping()
                return conn
            except:
                try: conn.close()
                except: pass
        except Empty:
            pass
        conn = psycopg2.connect(**PG_CONN_PARAMS)
        try:
            conn.set_client_encoding('UTF8')  # handle non-ASCII store/order data (Goovi import)
        except Exception:
            pass
        conn.autocommit = True
        return conn
    except Exception as e:
        write_log('ERROR', 'auth', f'PostgreSQL connect failed: {e}')
        return None

def ret_pg(conn):
    if conn:
        try:
            CONN_POOL.put_nowait(conn)
        except Exception:
            try: conn.close()
            except: pass

# ── Auth against wim_users (PostgreSQL)
def verify_login(email, password):
    conn = get_pg()
    if not conn: return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, uuid, email, name, role, password_hash AS password, status "
            "FROM wim_users WHERE email=%s AND status='active' AND deleted_at IS NULL",
            (email,)
        )
        row = cur.fetchone()
        if not row:
            write_log('WARN', 'auth', f'User not found: {email}')
            cur.close(); ret_pg(conn); return None
        user_id = row['id']
        user_uuid = row['uuid']
        user_email = row['email']
        user_name = row['name']
        user_role = row['role']
        pw_hash = row['password']
        user_status = row['status']
        driver_uuid = row.get('driver_uuid')
        if not pw_hash or not pw_hash.startswith('$2'):
            write_log('WARN', 'auth', f'No bcrypt password for: {email}')
            cur.close(); ret_pg(conn); return None
        try:
            if not bcrypt.checkpw(password.encode(), pw_hash.encode()):
                write_log('WARN', 'auth', f'Wrong password for: {email}')
                cur.close(); ret_pg(conn); return None
        except Exception as e:
            write_log('ERROR', 'auth', f'bcrypt check failed: {e}')
            cur.close(); ret_pg(conn); return None
        cur.close(); ret_pg(conn)
        role = user_role or 'sales'
        write_log('INFO', 'auth', f'Login OK: {email} ({role})')
        return {
            'id': user_id,
            'uuid': user_uuid,
            'name': user_name or email.split('@')[0],
            'email': user_email,
            'role': role,
            'driver_uuid': str(driver_uuid) if driver_uuid else None,
        }
    except Exception as e:
        write_log('ERROR', 'auth', f'Login query failed: {e}')
        return None

SESSIONS = {}
SESSION_LOCK = threading.Lock()

LOGIN_ATTEMPTS = {}
ATTEMPT_LOCK = threading.Lock()

def check_login_rate(email, ip):
    key = f"{email}|{ip}"
    with ATTEMPT_LOCK:
        now = time.time()
        ent = LOGIN_ATTEMPTS.get(key)
        if ent:
            if ent['count'] >= 5 and now - ent['first'] < 300:
                return False, round(300 - (now - ent['first']))
            if now - ent['first'] > 300:
                LOGIN_ATTEMPTS[key] = {'count': 0, 'first': now}
        else:
            LOGIN_ATTEMPTS[key] = {'count': 0, 'first': now}
        return True, 0

def record_login_fail(email, ip):
    key = f"{email}|{ip}"
    with ATTEMPT_LOCK:
        ent = LOGIN_ATTEMPTS.get(key)
        if ent and time.time() - ent['first'] >= 300:
            ent = {'count': 0, 'first': time.time()}
            LOGIN_ATTEMPTS[key] = ent
        if not ent:
            ent = {'count': 0, 'first': time.time()}
            LOGIN_ATTEMPTS[key] = ent
        ent['count'] += 1

def clear_login_attempts(email, ip):
    with ATTEMPT_LOCK:
        LOGIN_ATTEMPTS.pop(f"{email}|{ip}", None)

def session_cleanup():
    while True:
        time.sleep(300)
        try:
            now = time.time()
            with SESSION_LOCK:
                stale = [k for k, v in SESSIONS.items() if v.get('expires', 0) <= now]
                for k in stale: SESSIONS.pop(k, None)
            if stale:
                write_log('INFO', 'sessions', f'Purged {len(stale)} expired sessions')
        except Exception as e:
            write_log('ERROR', 'sessions', f'cleanup failed: {e}')

def create_session(user_id):
    sid = generate_session_id()
    with SESSION_LOCK:
        conn = get_pg()
        if not conn: return None
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO wim_sessions (id, user_id, expires_at) "
                "VALUES (%s, %s, NOW() + INTERVAL '7 days')",
                (sid, user_id)
            )
            conn.commit()
            cur.close(); ret_pg(conn)
        except Exception as e:
            write_log('ERROR', 'sessions', f'create_session failed: {e}')
            ret_pg(conn); return None
    return sid

def get_session(session_id):
    write_log('DEBUG', 'session', f'get_session start: {session_id[:12]}')
    with SESSION_LOCK:
        if session_id in SESSIONS:
            s = SESSIONS[session_id]
            if s.get('expires', 0) > time.time():
                write_log('DEBUG', 'session', 'cache hit')
                return s
        write_log('DEBUG', 'session', 'cache miss, querying DB')
        conn = get_pg()
        if not conn: return None
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT s.user_id, u.id, u.uuid, u.email, u.name, u.role, u.status, u.driver_uuid "
                "FROM wim_sessions s JOIN wim_users u ON s.user_id=u.id "
                "WHERE s.id=%s AND s.expires_at > NOW() LIMIT 1",
                (session_id,)
            )
            row = cur.fetchone()
            write_log('DEBUG', 'session', f'query done, row: {bool(row)}')
            if row:
                cur.close(); ret_pg(conn)
                user = {
                    'id': row['id'],
                    'uuid': row['uuid'],
                    'email': row['email'],
                    'name': row['name'] or row['email'].split('@')[0],
                    'role': row['role'] or 'sales',
                    'driver_uuid': str(row['driver_uuid']) if row.get('driver_uuid') else None,
                    'expires': time.time() + 300,
                }
                SESSIONS[session_id] = user
                return user
        except Exception as e:
            write_log('ERROR', 'sessions', f'get_session: {e}')
            if 'conn' in locals() and conn: ret_pg(conn)
    return None

def delete_session(session_id):
    with SESSION_LOCK:
        SESSIONS.pop(session_id, None)
        conn = get_pg()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM wim_sessions WHERE id=%s", (session_id,))
                conn.commit(); cur.close(); ret_pg(conn)
            except: ret_pg(conn)

# ── Geofence: Haversine distance to nearest depot
def haversine_m(lat1, lng1, lat2, lng2):
    """Distance in meters between two lat/lng points."""
    if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
        return None
    try:
        lat1, lng1, lat2, lng2 = float(lat1), float(lng1), float(lat2), float(lng2)
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = math.sin(math.radians(dlat/2))**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(dlng/2))**2
        return 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    except Exception:
        return None

def check_geofence(lat, lng):
    """Returns (name, depot_id, is_inside) if within 50m of any depot."""
    if lat is None or lng is None:
        return ('', None, False)
    try:
        conn = get_pg()
        if not conn: return ('', None, False)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, name, latitude, longitude, radius_m FROM wim_depots")
        for r in cur.fetchall():
            dlat = lat - float(r['latitude'])
            dlng = lng - float(r['longitude'])
            a = math.sin(math.radians(dlat/2))**2 + math.cos(math.radians(float(r['latitude']))) * math.cos(math.radians(lat)) * math.sin(math.radians(dlng/2))**2
            dist = 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            if dist <= float(r['radius_m']):
                cur.close(); ret_pg(conn)
                return (r['name'], r['id'], True)
        cur.close(); ret_pg(conn)
    except Exception as e:
        write_log('ERROR', 'geofence', str(e))
    return ('', None, False)

# ── HTTP Handler
# ── Role helpers ──
def fmt_idr(n):
    """Format a number as Indonesian rupiah without decimals."""
    try:
        return '{:,}'.format(int(round(float(n or 0))))
    except Exception:
        return '%s' % (n or 0)

ADMIN_ROLES = ('super_admin', 'depo_admin', 'admin')
# Higher-level admin (full control); depo_admin is scoped but still an admin.

class WIMHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def _send_response_raw(self, code, headers, body_bytes):
        parts = [b"HTTP/1.0 %d OK\r\n" % code]
        for k, v in headers:
            parts.append(("%s: %s\r\n" % (k, v)).encode())
        parts.append(b"Content-Length: %d\r\n" % len(body_bytes))
        parts.append(b"\r\n")
        parts.append(body_bytes)
        self.wfile.write(b"".join(parts))

    def _send_json(self, code, obj):
        body = json.dumps(obj, default=str).encode()
        self._send_response_raw(code, [
            ('Content-Type', 'application/json'),
            ('Access-Control-Allow-Origin', '*'),
            ('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS'),
            ('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept, Customer-Token'),
        ], body)

    def _send_bytes(self, code, body, content_type, filename=None):
        hdrs = [
            ('Content-Type', content_type),
            ('Access-Control-Allow-Origin', '*'),
            ('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS'),
            ('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept, Customer-Token'),
            ('Content-Disposition', 'attachment; filename="%s"' % filename) if filename else ('X-Content-Type-Options', 'nosniff'),
        ]
        self._send_response_raw(code, hdrs, body)

    def _read_body(self, max_size=5*1024*1024):
        cl = int(self.headers.get('Content-Length', 0))
        if cl > max_size:
            raise ValueError(f'Body too large: {cl} > {max_size}')
        return self.rfile.read(cl) if cl > 0 else b''

    def _client_ip(self):
        x = self.headers.get('X-Forwarded-For', '')
        if x: return x.split(',')[0].strip()
        return self.client_address[0] if self.client_address else '?'

    def _get_session_from_cookie(self):
        c = self.headers.get('Cookie', '')
        for part in c.split(';'):
            part = part.strip()
            if part.startswith('wim_session='):
                return part[12:]
        return None

    def _auth_external_key(self):
        """Validate Authorization: Bearer <api_key> against wim_api_keys.
        Returns a synthetic user dict (role=api scope) or None.
        This is the gateway for future external apps to access the DB."""
        ah = self.headers.get('Authorization', '')
        if not ah.lower().startswith('bearer '):
            return None
        api_key = ah[7:].strip()
        if not api_key:
            return None
        conn = get_pg()
        if not conn: return None
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, name, api_key, scope, is_active, expires_at "
                "FROM wim_api_keys WHERE api_key=%s AND is_active=TRUE LIMIT 1",
                (api_key,))
            row = cur.fetchone()
            cur.close()
            if not row:
                ret_pg(conn); return None
            if row.get('expires_at') and row['expires_at'] < datetime.datetime.now():
                write_log('WARN', 'auth', f'Expired API key: {row.get("name")}')
                ret_pg(conn); return None
            # update last_used_at
            try:
                cur2 = conn.cursor()
                cur2.execute("UPDATE wim_api_keys SET last_used_at=NOW() WHERE id=%s", (row['id'],))
                conn.commit()
                cur2.close()
            except Exception:
                conn.rollback()
            ret_pg(conn)
            scope = (row.get('scope') or '').split(',') if row.get('scope') else []
            # Translate scope to a role the auth checkers understand
            role = 'super_admin' if ('sync:write' in scope or 'report:read' in scope) else 'admin'
            if scope and all(s.startswith('data:') for s in scope):
                role = 'admin'
            return {
                'id': row['id'],
                'uuid': None,
                'email': f"apikey:{row['name']}",
                'name': row['name'],
                'role': role,
                'driver_uuid': None,
                'is_api': True,
                'scope': scope,
                'expires': time.time() + 300,
            }
        except Exception as e:
            write_log('ERROR', 'auth', f'external key check: {e}')
            if 'conn' in locals() and conn: ret_pg(conn)
        return None

    def _require_auth(self):
        # 1) external bearer API key (future apps / integrations)
        ext = self._auth_external_key()
        if ext:
            return ext
        # 2) cookie session (app users)
        sid = self._get_session_from_cookie()
        if not sid: return None
        return get_session(sid)

    def _match_path(self, pattern):
        """Match /api/users/:id returning {'id': '123'} or None."""
        p = self.path.split('?')[0]
        parts = pattern.strip('/').split('/')
        path_parts = p.strip('/').split('/')
        if len(parts) != len(path_parts):
            return None
        params = {}
        for pat, val in zip(parts, path_parts):
            if pat.startswith(':'):
                params[pat[1:]] = val
            elif pat != val:
                return None
        return params

    # ═══════════════════════════════════════════════════
    # Auth endpoints
    # ═══════════════════════════════════════════════════

    def do_LOGIN(self):
        try:
            body = self._read_body()
            try: data = json.loads(body)
            except: return self._send_json(400, {'error': 'Invalid JSON'})
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
            email = (data.get('email') or '').strip().lower()
            password = data.get('password') or ''
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        if not email or not password:
            return self._send_json(400, {'error': 'Email dan password diperlukan'})
        ok, wait = check_login_rate(email, self._client_ip())
        if not ok:
            return self._send_json(429, {'error': f'Terlalu banyak percobaan. Coba lagi dalam {wait} detik'})
        user = verify_login(email, password)
        if not user:
            record_login_fail(email, self._client_ip())
            return self._send_json(401, {'error': 'Email atau password salah'})
        clear_login_attempts(email, self._client_ip())
        session_id = create_session(user['id'])
        if not session_id:
            return self._send_json(500, {'error': 'Gagal membuat session'})
        login_body = json.dumps({
            'token': session_id,
            'user': {
                'name': user['name'],
                'email': user['email'],
                'role': user['role'],
                'driver_uuid': user.get('driver_uuid') or '',
            }
        }, default=str).encode()
        expires = time.strftime('%a, %d-%b-%Y %H:%M:%S GMT', time.gmtime(time.time() + 86400 * 7))
        self._send_response_raw(200, [
            ('Content-Type', 'application/json'),
            ('Access-Control-Allow-Origin', '*'),
            ('Set-Cookie', f'wim_session={session_id}; Path=/; HttpOnly; SameSite=Lax; Expires={expires}'),
        ], login_body)

    def do_LOGOUT(self):
        sid = self._get_session_from_cookie()
        if sid: delete_session(sid)
        self._send_response_raw(200, [
            ('Content-Type', 'application/json'),
            ('Access-Control-Allow-Origin', '*'),
            ('Set-Cookie', 'wim_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'),
        ], json.dumps({'status': 'ok'}).encode())

    def do_SESSION(self):
        user = self._require_auth()
        if not user:
            self._send_response_raw(401, [
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*'),
                ('Set-Cookie', 'wim_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'),
            ], json.dumps({'error': 'Session expired'}).encode())
            return
        sesh_body = json.dumps({
            'user': {
                'name': user['name'],
                'email': user['email'],
                'role': user['role'],
                'driver_uuid': user.get('driver_uuid') or '',
            }
        }, default=str).encode()
        self._send_response_raw(200, [
            ('Content-Type', 'application/json'),
            ('Access-Control-Allow-Origin', '*'),
        ], sesh_body)

    # ═══════════════════════════════════════════════════
    # Absensi (attendance)
    # ═══════════════════════════════════════════════════

    def do_DEPOTS(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT id, name, address, latitude, longitude, radius_m, kode_depo, region_id FROM wim_depots ORDER BY name")
            depots = []
            for r in cur.fetchall():
                depots.append({
                    'id': r['id'],
                    'name': r['name'],
                    'address': r['address'] or '',
                    'lat': float(r['latitude']) if r['latitude'] is not None else None,
                    'lng': float(r['longitude']) if r['longitude'] is not None else None,
                    'radiusM': r['radius_m'],
                    'kodeDepo': r['kode_depo'] or '',
                    'regionId': r['region_id'],
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'depots': depots})
        except Exception as e:
            write_log('ERROR', 'depots', str(e))
            self._send_json(500, {'error': str(e)})

    def do_DEPOTS_POST(self):
        """POST /api/depots — create a depot. super_admin/admin only.
        Body: {name, address, latitude, longitude, radius_m, region_id?}"""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        name = (data.get('name') or '').strip()
        if not name:
            return self._send_json(400, {'error': 'name diperlukan'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO wim_depots (name, address, latitude, longitude, radius_m, kode_depo, region_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (name,
                 (data.get('address') or ''),
                 float(data['latitude']) if data.get('latitude') is not None else None,
                 float(data['longitude']) if data.get('longitude') is not None else None,
                 int(data.get('radius_m', 50) or 50),
                 (data.get('kode_depo') or ''),
                 data.get('region_id') if data.get('region_id') is not None else None))
            dep_id = cur.fetchone()[0]
            conn.commit(); cur.close(); ret_pg(conn)
            write_log('INFO', 'depots', f'Depot created: {name}')
            self._send_json(201, {'status': 'ok', 'id': dep_id})
        except Exception as e:
            write_log('ERROR', 'depots', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_DEPOT_PATCH(self, params):
        """PATCH /api/depots/:id — edit a depot. super_admin/admin only.
        Body may include name, address, latitude, longitude, radius_m, kode_depo, region_id, is_active."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        dep_id = params.get('id')
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            set_clauses = []
            vals = []
            for field, col in (('name','name'),('address','address'),('kode_depo','kode_depo')):
                if field in data:
                    set_clauses.append(f'{col}=%s'); vals.append((data[field] or ''))
            for field, col in (('latitude','latitude'),('longitude','longitude')):
                if field in data:
                    set_clauses.append(f'{col}=%s')
                    vals.append(float(data[field]) if data[field] is not None else None)
            if 'radius_m' in data:
                set_clauses.append('radius_m=%s'); vals.append(int(data['radius_m'] or 0))
            if 'region_id' in data:
                set_clauses.append('region_id=%s'); vals.append(data['region_id'] if data['region_id'] is not None else None)
            if 'is_active' in data and isinstance(data['is_active'], bool):
                set_clauses.append('is_active=%s'); vals.append(bool(data['is_active']))
            if not set_clauses:
                cur.close(); ret_pg(conn)
                return self._send_json(400, {'error': 'Belum ada field untuk diperbarui'})
            vals.append(dep_id)
            cur.execute(f"UPDATE wim_depots SET {', '.join(set_clauses)} WHERE id=%s", vals)
            conn.commit()
            ok = cur.rowcount > 0
            cur.close(); ret_pg(conn)
            if not ok:
                return self._send_json(404, {'error': 'Depot tidak ditemukan'})
            write_log('INFO', 'depots', f'Depot updated: {dep_id}')
            self._send_json(200, {'status': 'ok'})
        except Exception as e:
            write_log('ERROR', 'depots', f'PATCH failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_FILTER_OPTIONS(self):
        """Admin dropdown sources: sales users, depots (with region), regions."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Sales users (all roles that can appear on reports; filter client-side if needed)
            cur.execute(
                "SELECT u.id, u.name, u.role, um.depot_id, d.name AS depot_name, d.region_id, "
                "r.name AS region_name "
                "FROM wim_users u "
                "LEFT JOIN wim_user_meta um ON u.id=um.user_id "
                "LEFT JOIN wim_depots d ON d.id=um.depot_id "
                "LEFT JOIN wim_regions r ON r.id=d.region_id "
                "WHERE u.deleted_at IS NULL AND u.status='active' "
                "AND u.role IN ('sales','depo_admin','head_of_sales','regional_manager') "
                "ORDER BY u.name")
            users = [{'id': r['id'], 'name': r['name'], 'role': r['role'],
                      'depotId': r['depot_id'], 'depotName': r['depot_name'] or '',
                      'regionId': r['region_id'], 'regionName': r['region_name'] or ''}
                     for r in cur.fetchall()]
            cur.execute(
                "SELECT d.id, d.name, d.kode_depo, d.region_id, r.name AS region_name "
                "FROM wim_depots d LEFT JOIN wim_regions r ON r.id=d.region_id "
                "WHERE d.is_active ORDER BY d.name")
            depots = [{'id': r['id'], 'name': r['name'], 'kodeDepo': r['kode_depo'] or '',
                       'regionId': r['region_id'], 'regionName': r['region_name'] or ''}
                      for r in cur.fetchall()]
            cur.execute("SELECT id, name, kode_area FROM wim_regions WHERE is_active ORDER BY name")
            regions = [{'id': r['id'], 'name': r['name'], 'kode_area': r['kode_area'] or ''} for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {'users': users, 'depots': depots, 'regions': regions})
        except Exception as e:
            write_log('ERROR', 'filter_options', str(e))
            self._send_json(500, {'error': str(e)})

    def do_ABSENSI_GET(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        date = (qs.get('date') or [''])[0][:10]
        date_from = (qs.get('date_from') or [''])[0][:10]
        date_to = (qs.get('date_to') or [''])[0][:10]
        # API-key requests: return ALL attendance for the date (admin scope), optional ?user_id filter
        user_filter = (qs.get('user_id') or [None])[0]
        depot_filter = (qs.get('depot_id') or [''])[0].strip()
        region_filter = (qs.get('region_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            if user.get('is_api'):
                # Date clause: prefer explicit date, else period (date_from..date_to), else today
                if date:
                    where = "WHERE a.date=%s"; params = [date]
                elif date_from and date_to:
                    where = "WHERE a.date >= %s AND a.date <= %s"; params = [date_from, date_to]
                elif date_from:
                    where = "WHERE a.date >= %s"; params = [date_from]
                elif date_to:
                    where = "WHERE a.date <= %s"; params = [date_to]
                else:
                    where = "WHERE a.date=%s"; params = [time.strftime('%Y-%m-%d')]
                if user_filter:
                    where += " AND a.user_id=%s"; params.append(user_filter)
                # Depot/region filter via the user's assigned depot (wim_user_meta.depot_id -> wim_depots)
                if depot_filter:
                    where += " AND um.depot_id=%s"; params.append(int(depot_filter))
                if region_filter:
                    where += " AND ud.region_id=%s"; params.append(int(region_filter))
                cur.execute(
                    f"SELECT a.id, a.user_id, u.name, a.date, a.clock_in, a.clock_out, a.clock_in_photo, "
                    f"a.clock_out_photo, a.duration, a.location_lat, a.location_lng, a.geofence_status, "
                    f"a.depot_id, a.created_at, d.name AS depot_name, "
                    f"um.depot_id AS user_depot_id, ud.name AS user_depot_name, "
                    f"r.name AS region_name "
                    f"FROM wim_attendance a LEFT JOIN wim_users u ON a.user_id=u.id "
                    f"LEFT JOIN wim_depots d ON a.depot_id=d.id "
                    f"LEFT JOIN wim_user_meta um ON um.user_id=a.user_id "
                    f"LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
                    f"LEFT JOIN wim_regions r ON r.id=ud.region_id "
                    f"{where} ORDER BY a.date, u.name", params)
                records = []
                for row in cur.fetchall():
                    records.append({
                        'id': row['id'], 'user_id': row['user_id'], 'name': row['name'],
                        'date': str(row['date']), 'clockIn': row['clock_in'] or None,
                        'clockOut': row['clock_out'] or None, 'duration': row['duration'],
                        'geofenceStatus': row['geofence_status'] or '', 'depot_name': row['depot_name'] or '',
                        'userDepotName': row['user_depot_name'] or '', 'regionName': row['region_name'] or '',
                        'lat': float(row['location_lat']) if row['location_lat'] else None,
                        'lng': float(row['location_lng']) if row['location_lng'] else None,
                        'createdAt': str(row['created_at']) if row['created_at'] else None,
                    })
                cur.close(); ret_pg(conn)
                self._send_json(200, {'records': records, 'total': len(records)})
            else:
                cur.execute(
                    "SELECT id, date, clock_in, clock_out, clock_in_photo, clock_out_photo, "
                    "duration, location_lat, location_lng, geofence_status, depot_id, created_at "
                    "FROM wim_attendance WHERE user_id=%s AND date=%s ORDER BY id DESC LIMIT 1",
                    (user['id'], date)
                )
                row = cur.fetchone()
                cur.close(); ret_pg(conn)
                if row:
                    result = {
                        'id': row['id'],
                        'date': str(row['date']),
                        'clockIn': row['clock_in'] or None,
                        'clockOut': row['clock_out'] or None,
                        'clockInPhoto': row['clock_in_photo'],
                        'clockOutPhoto': row['clock_out_photo'],
                        'duration': row['duration'],
                        'location': {
                            'lat': float(row['location_lat']) if row['location_lat'] else None,
                            'lng': float(row['location_lng']) if row['location_lng'] else None,
                        } if row['location_lat'] else None,
                        'geofenceStatus': row['geofence_status'] or '',
                        'depotId': row['depot_id'],
                        'createdAt': str(row['created_at']) if row['created_at'] else None,
                    }
                    self._send_json(200, result)
                else:
                    self._send_json(200, {})
        except Exception as e:
            write_log('ERROR', 'absensi', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ABSENSI_POST(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        action = data.get('action', '')
        date = data.get('date', time.strftime('%Y-%m-%d'))
        time_str = data.get('time', '')
        photo = data.get('photo', '')
        lat = data.get('lat')
        lng = data.get('lng')
        duration = data.get('duration', '')
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            if action == 'clock_in':
                depot_name, depot_id, is_inside = check_geofence(lat, lng)
                gf_status = 'in_depot' if is_inside else 'outside'
                # UPSERT: INSERT ... ON CONFLICT DO UPDATE
                cur.execute(
                    "INSERT INTO wim_attendance (user_id, date, clock_in, clock_in_photo, "
                    "location_lat, location_lng, geofence_status, depot_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (user_id, date) DO UPDATE SET "
                    "clock_in=EXCLUDED.clock_in, clock_in_photo=EXCLUDED.clock_in_photo, "
                    "location_lat=EXCLUDED.location_lat, location_lng=EXCLUDED.location_lng, "
                    "geofence_status=EXCLUDED.geofence_status, depot_id=EXCLUDED.depot_id",
                    (user['id'], date, time_str, photo, lat, lng, gf_status, depot_id)
                )
                write_log('INFO', 'absensi', f'Clock in: {user["email"]} @ {time_str} [{gf_status}]')
            elif action == 'clock_out':
                cur.execute(
                    "UPDATE wim_attendance SET clock_out=%s, clock_out_photo=%s, duration=%s "
                    "WHERE user_id=%s AND date=%s",
                    (time_str, photo, duration, user['id'], date)
                )
                write_log('INFO', 'absensi', f'Clock out: {user["email"]} @ {time_str} (dur: {duration})')
            else:
                cur.close(); ret_pg(conn)
                return self._send_json(400, {'error': f'Unknown action: {action}'})
            conn.commit()
            cur.close(); ret_pg(conn)
            self._send_json(200, {'status': 'ok', 'action': action, 'date': date})
        except Exception as e:
            write_log('ERROR', 'absensi', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Dashboard (per-user)
    # ═══════════════════════════════════════════════════

    def do_DASHBOARD(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        today = time.strftime('%Y-%m-%d')
        # API-key requesters: return GLOBAL/team KPIs (admin scope) instead of one fake user's own
        if user.get('is_api'):
            try:
                conn = get_pg()
                if not conn: return self._send_json(500, {'error': 'DB connection failed'})
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("SELECT COUNT(*) c FROM wim_users WHERE status='active'")
                staff = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) c FROM wim_visit_plan WHERE visit_date=%s", (today,))
                planned_today = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) c FROM wim_visit_plan WHERE visit_date=%s AND status='visited'", (today,))
                visited_today = cur.fetchone()['c']
                # Actual stores visited today (from real visits), distinct per planned store.
                cur.execute(
                    "SELECT COUNT(DISTINCT v.place_uuid) c FROM wim_visits v "
                    "WHERE DATE(v.checkin_at)=%s",
                    (today,))
                stores_visited = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) c FROM wim_visits WHERE DATE(checkin_at)=%s", (today,))
                visits_today = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) c FROM wim_orders WHERE deleted_at IS NULL AND DATE(created_at)=%s", (today,))
                orders_today = cur.fetchone()['c']
                cur.execute("SELECT COUNT(*) c FROM wim_attendance WHERE date=%s AND clock_in IS NOT NULL", (today,))
                attended_today = cur.fetchone()['c']
                cur.close(); ret_pg(conn)
                self._send_json(200, {
                    'plan': {'total': planned_today, 'visited': visited_today, 'route': planned_today, 'luar_rute': 0},
                    'orders': orders_today, 'attendance': attended_today,
                    'visitsToday': visits_today, 'totalStaff': staff,
                    'storesVisited': stores_visited,
                })
            except Exception as e:
                write_log('ERROR', 'dashboard', f'GET (api) failed: {e}')
                self._send_json(500, {'error': str(e)})
            return
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Plan stores for today
            cur.execute(
                "SELECT COUNT(*) as c, source FROM wim_visit_plan "
                "WHERE user_id=%s AND visit_date=%s GROUP BY source",
                (user['id'], today)
            )
            plan_rows = cur.fetchall()
            plan_counts = {'route': 0, 'luar_rute': 0, 'total': 0}
            for r in plan_rows:
                plan_counts[r['source']] = r['c']
                plan_counts['total'] += r['c']

            # Orders count for this user
            cur.execute(
                "SELECT COUNT(*) as c FROM wim_orders WHERE user_id=%s AND deleted_at IS NULL",
                (user['id'],)
            )
            order_count = cur.fetchone()['c']

            # Attendance today
            cur.execute(
                "SELECT id, clock_in, clock_out, duration FROM wim_attendance "
                "WHERE user_id=%s AND date=%s",
                (user['id'], today)
            )
            absen = cur.fetchone()
            attendance = {'clockIn': None, 'clockOut': None, 'duration': None}
            if absen:
                attendance = {
                    'clockIn': absen['clock_in'],
                    'clockOut': absen['clock_out'],
                    'duration': absen['duration'],
                }

            # Visits today
            cur.execute(
                "SELECT COUNT(*) as c FROM wim_visits "
                "WHERE user_id=%s AND DATE(checkin_at)=%s",
                (user['id'], today)
            )
            visits_today = cur.fetchone()['c']

            # Recent visits (last 5)
            cur.execute(
                "SELECT place_name, checkin_at, checkout_at, status, source "
                "FROM wim_visits WHERE user_id=%s AND DATE(checkin_at)=%s "
                "ORDER BY checkin_at DESC LIMIT 5",
                (user['id'], today)
            )
            recent_visits = [
                {
                    'placeName': r['place_name'],
                    'checkinAt': str(r['checkin_at']) if r['checkin_at'] else None,
                    'checkoutAt': str(r['checkout_at']) if r['checkout_at'] else None,
                    'status': r['status'],
                    'source': r['source'],
                }
                for r in cur.fetchall()
            ]

            cur.close(); ret_pg(conn)
            self._send_json(200, {
                'plan': plan_counts,
                'orders': order_count,
                'attendance': attendance,
                'visitsToday': visits_today,
                'recentVisits': recent_visits,
            })
        except Exception as e:
            write_log('ERROR', 'dashboard', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Position tracking — sales geolocation logging
    # ═══════════════════════════════════════════════════

    def do_POSITION_POST(self):
        """POST /api/positions — record the sales/user's current geolocation.
        Body: {latitude, longitude, accuracy} . Saves time + coords + user id/name so it
        can be joined to visits/orders later."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        lat = data.get('latitude', data.get('lat'))
        lng = data.get('longitude', data.get('lng'))
        if lat is None or lng is None:
            return self._send_json(400, {'error': 'latitude dan longitude diperlukan'})
        try:
            lat = float(lat); lng = float(lng)
        except Exception:
            return self._send_json(400, {'error': 'latitude/longitude tidak valid'})
        accuracy = data.get('accuracy', data.get('accuracy_m'))
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO wim_sales_positions (user_id, user_name, latitude, longitude, accuracy_m, source, recorded_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,NOW())",
                (user.get('id'), user.get('name') or user.get('email'), lat, lng,
                 float(accuracy) if accuracy is not None else None,
                 (data.get('source') or 'app')[:20])
            )
            conn.commit()
            cur.close(); ret_pg(conn)
            self._send_json(200, {'status': 'ok', 'recordedAt': time.strftime('%Y-%m-%d %H:%M:%S')})
        except Exception as e:
            write_log('ERROR', 'position', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_POSITION_GET(self):
        """GET /api/positions/latest — the rep's most recent recorded position."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, user_id, user_name, latitude, longitude, accuracy_m, recorded_at "
                "FROM wim_sales_positions WHERE user_id=%s "
                "ORDER BY recorded_at DESC NULLS LAST, id DESC LIMIT 1",
                (user.get('id'),))
            r = cur.fetchone()
            cur.close(); ret_pg(conn)
            if not r:
                return self._send_json(200, {'position': None})
            self._send_json(200, {'position': {
                'id': r['id'], 'userId': r['user_id'], 'userName': r['user_name'],
                'latitude': float(r['latitude']) if r['latitude'] else None,
                'longitude': float(r['longitude']) if r['longitude'] else None,
                'accuracy': float(r['accuracy_m']) if r['accuracy_m'] is not None else None,
                'recordedAt': str(r['recorded_at']),
            }})
        except Exception as e:
            write_log('ERROR', 'position', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_POSITIONS_ALL(self):
        """GET /api/positions/all — admin: latest position per sales user + recent app-opened points.
        Returns {positions:[{userId,userName,latitude,longitude,accuracy,recordedAt}],
                  trend:[{userId,userName,latitude,longitude,recordedAt}] recent fixes}."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        qs = parse_qs(urlparse(self.path).query)
        limit = 30
        try: limit = max(1, min(200, int((qs.get('limit') or ['30'])[0] or 30)))
        except Exception: limit = 30
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Latest position per user (their "current whereabouts")
            cur.execute(
                "SELECT p.user_id, p.user_name, p.latitude, p.longitude, p.accuracy_m, p.recorded_at "
                "FROM wim_sales_positions p "
                "JOIN (SELECT user_id, MAX(recorded_at) as mx FROM wim_sales_positions GROUP BY user_id) g "
                "ON g.user_id=p.user_id AND g.mx=p.recorded_at "
                "WHERE p.user_id IS NOT NULL ORDER BY p.user_name"
            )
            positions = []
            for r in cur.fetchall():
                positions.append({
                    'userId': r['user_id'], 'userName': r['user_name'] or 'Sales',
                    'latitude': float(r['latitude']) if r['latitude'] is not None else None,
                    'longitude': float(r['longitude']) if r['longitude'] is not None else None,
                    'accuracy': float(r['accuracy_m']) if r['accuracy_m'] is not None else None,
                    'recordedAt': str(r['recorded_at']),
                })
            # Recent trend (app-opened / refreshed points) for the route-map dots
            cur.execute(
                "SELECT user_id, user_name, latitude, longitude, recorded_at "
                "FROM wim_sales_positions WHERE user_id IS NOT NULL "
                "ORDER BY recorded_at DESC NULLS LAST, id DESC LIMIT %s",
                (limit,))
            trend = []
            for r in cur.fetchall():
                trend.append({
                    'userId': r['user_id'], 'userName': r['user_name'] or 'Sales',
                    'latitude': float(r['latitude']) if r['latitude'] is not None else None,
                    'longitude': float(r['longitude']) if r['longitude'] is not None else None,
                    'recordedAt': str(r['recorded_at']),
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'positions': positions, 'trend': trend, 'total': len(positions)})
        except Exception as e:
            write_log('ERROR', 'position', f'ALL failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ROUTE_MAP(self):
        """GET /api/admin/route-map?date=YYYY-MM-DD — everything the route/travel map needs:
        - stores with visit/order status (green=visited&ordered, red=visited no order, blue=unvisited)
        - sales travel lines (ordered position fixes per user) + current position + last-known
        - attendance checkin/checkout locations (icons)
        - depot locations (warehouse icons)"""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        qs = parse_qs(urlparse(self.path).query)
        date = (qs.get('date') or [''])[0][:10] or time.strftime('%Y-%m-%d')
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Stores + visit plan status + whether an order was placed for that store on the date
            cur.execute(
                "SELECT s.uuid, s.name AS store_name, s.address, s.city, s.latitude, s.longitude, "
                "vp.user_id, u.name AS user_name, vp.status AS visit_status, "
                "(SELECT COUNT(*) FROM wim_orders o "
                "  WHERE o.store_uuid = s.uuid AND o.deleted_at IS NULL "
                "  AND o.user_id = vp.user_id AND DATE(o.created_at) = %s) AS order_count "
                "FROM wim_visit_plan vp "
                "LEFT JOIN wim_stores s ON vp.place_uuid = s.uuid "
                "LEFT JOIN wim_users u ON vp.user_id = u.id "
                "WHERE vp.visit_date=%s AND s.latitude IS NOT NULL AND s.longitude IS NOT NULL",
                (date, date))
            stores = []
            for r in cur.fetchall():
                visited = r['visit_status'] in ('visited', 'completed', 'checked')
                ordered = int(r['order_count'] or 0) > 0
                # An order for the store implies the sales was there (visited)
                if ordered: visited = True
                stores.append({
                    'uuid': r['uuid'], 'storeName': r['store_name'] or 'Tanpa Nama',
                    'address': r['address'] or '', 'city': r['city'] or '',
                    'latitude': float(r['latitude']),
                    'longitude': float(r['longitude']),
                    'userId': r['user_id'], 'userName': r['user_name'] or '',
                    'visited': visited, 'ordered': ordered,
                    # green visited&ordered / red visited-no-order / blue unvisited
                    'color': '#2eb872' if (visited and ordered) else ('#e63946' if visited else '#4361ee'),
                })

            # Sales travel lines: all position fixes ordered by time per user
            cur.execute(
                "SELECT user_id, user_name, latitude, longitude, recorded_at "
                "FROM wim_sales_positions WHERE user_id IS NOT NULL "
                "AND latitude IS NOT NULL AND longitude IS NOT NULL "
                "ORDER BY user_id, recorded_at, id")
            travels = {}  # userId -> [{lat,lng,recordedAt}]
            order = []
            for r in cur.fetchall():
                uid = r['user_id']
                if uid not in travels:
                    travels[uid] = []
                    order.append(uid)
                travels[uid].append({
                    'latitude': float(r['latitude']), 'longitude': float(r['longitude']),
                    'recordedAt': str(r['recorded_at']), 'userName': r['user_name'] or '',
                })
            travelLines = [{'userId': uid, 'userName': travels[uid][0]['userName'] if travels[uid] else '', 'points': travels[uid]} for uid in order]
            # last-known position per user = last fix
            currentPositions = [{'userId': uid, 'userName': pt['userName'], 'latitude': pt['latitude'], 'longitude': pt['longitude'], 'recordedAt': pt['recordedAt']} for uid, pts in travels.items() for pt in [pts[-1]]]

            # Attendance checkin/checkout locations for the date
            cur.execute(
                "SELECT a.user_id, u.name AS user_name, a.clock_in, a.clock_out, "
                "a.location_lat, a.location_lng "
                "FROM wim_attendance a LEFT JOIN wim_users u ON a.user_id=u.id "
                "WHERE a.date=%s AND a.location_lat IS NOT NULL",
                (date,))
            attendance = []
            for r in cur.fetchall():
                attendance.append({
                    'userId': r['user_id'], 'userName': r['user_name'] or '',
                    'clockIn': r['clock_in'], 'clockOut': r['clock_out'],
                    'latitude': float(r['location_lat']),
                    'longitude': float(r['location_lng']),
                })

            # Depots (warehouse icons)
            cur.execute(
                "SELECT id, name, latitude, longitude FROM wim_depots "
                "WHERE latitude IS NOT NULL AND longitude IS NOT NULL")
            depots = [{'id': r['id'], 'name': r['name'], 'latitude': float(r['latitude']), 'longitude': float(r['longitude'])} for r in cur.fetchall()]

            cur.close(); ret_pg(conn)
            self._send_json(200, {
                'stores': stores, 'travelLines': travelLines,
                'currentPositions': currentPositions,
                'attendance': attendance, 'depots': depots,
                'date': date,
            })
        except Exception as e:
            write_log('ERROR', 'route-map', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Stores (from visit plan + wim_stores)
    # ═══════════════════════════════════════════════════

    def do_MY_STORES(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        today = time.strftime('%Y-%m-%d')
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Auto-materialize this user's monthly template into today's plan
            # (idempotent ON CONFLICT DO NOTHING) so templated visits appear.
            try:
                cur.execute("SELECT materialize_template_for_date(%s, %s::date)", (user['id'], today))
                conn.commit()
            except Exception as m_err:
                write_log('WARN', 'stores', f'auto-materialize failed (non-fatal): {m_err}')
                conn.rollback()
            cur.execute(
                "SELECT vp.id as plan_id, vp.place_uuid, vp.source, vp.status as plan_status, "
                "p.name, p.address, p.city, p.uuid as place_uuid2, p.latitude, p.longitude, "
                "p.geofence_radius_m, "
                "p.phone, p.owner_name, p.channel, p.category "
                "FROM wim_visit_plan vp "
                "LEFT JOIN wim_stores p ON vp.place_uuid = p.uuid "
                "WHERE vp.user_id=%s AND vp.visit_date=%s "
                "ORDER BY vp.source, p.name",
                (user['id'], today)
            )
            stores = []
            for r in cur.fetchall():
                stores.append({
                    'planId': r['plan_id'],
                    'uuid': r['place_uuid'] or r['place_uuid2'],
                    'name': r['name'] or 'Tanpa Nama',
                    'address': r['address'] or '',
                    'city': r['city'] or '',
                    'latitude': float(r['latitude']) if r['latitude'] else None,
                    'longitude': float(r['longitude']) if r['longitude'] else None,
                    'geofenceRadiusM': r['geofence_radius_m'],
                    'phone': r['phone'] or '',
                    'owner_name': r['owner_name'] or '',
                    'channel': r['channel'] or '',
                    'category': r['category'] or '',
                    'source': r['source'],
                    'status': r['plan_status'],
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'stores': stores, 'total': len(stores)})
        except Exception as e:
            write_log('ERROR', 'stores', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ALL_STORES(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        today = time.strftime('%Y-%m-%d')
        qs = parse_qs(urlparse(self.path).query)
        q = (qs.get('q') or [''])[0].strip().lower()
        chan = (qs.get('chan') or [''])[0].strip()
        stat = (qs.get('status') or [''])[0].strip()
        try:
            page = max(1, int((qs.get('page') or ['1'])[0] or 1))
            per_page = min(500, max(1, int((qs.get('per_page') or ['100'])[0] or 100)))
        except Exception:
            page, per_page = 1, 100
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get place UUIDs already in user's plan
            cur.execute(
                "SELECT place_uuid FROM wim_visit_plan WHERE user_id=%s AND visit_date=%s",
                (user['id'], today)
            )
            planned = set(r['place_uuid'] for r in cur.fetchall())

            # Build shared WHERE with q + channel + status filters (server-side so total + paging are correct)
            conditions = "deleted_at IS NULL"
            cond_params = []
            if q:
                conditions += " AND (LOWER(name) LIKE %s OR LOWER(city) LIKE %s)"
                cond_params += [f'%{q}%', f'%{q}%']
            if chan:
                conditions += " AND channel = %s"
                cond_params.append(chan)
            if stat:
                conditions += " AND status = %s"
                cond_params.append(stat)
            cur.execute(
                f"SELECT COUNT(*) AS total FROM wim_stores WHERE {conditions}", cond_params
            )
            total = cur.fetchone()['total']
            cur.execute(
                "SELECT uuid, name, address, city, latitude, longitude, phone, "
                "owner_name, channel, category, status, province, "
                "assigned_salesperson_id, credit_limit, "
                "kecamatan, kelurahan, kode_pos, kendaraan, nik, npwp, npwp_name "
                ", geofence_radius_m "
                f"FROM wim_stores WHERE {conditions} ORDER BY name LIMIT %s OFFSET %s",
                cond_params + [per_page, (page - 1) * per_page]
            )

            stores = []
            for r in cur.fetchall():
                stores.append({
                    'uuid': r['uuid'],
                    'name': r['name'] or 'Tanpa Nama',
                    'address': r['address'] or '',
                    'city': r['city'] or '',
                    'latitude': float(r['latitude']) if r['latitude'] else None,
                    'longitude': float(r['longitude']) if r['longitude'] else None,
                    'geofence_radius_m': r['geofence_radius_m'],
                    'owner_name': r['owner_name'] or '',
                    'channel': r['channel'] or '',
                    'category': r['category'] or '',
                    'status': r['status'] or 'active',
                    'province': r['province'] or '',
                    'phone': r['phone'] or '',
                    'assigned_salesperson_id': r['assigned_salesperson_id'],
                    'credit_limit': float(r['credit_limit']) if r['credit_limit'] is not None else None,
                    'kecamatan': r['kecamatan'] or '',
                    'kelurahan': r['kelurahan'] or '',
                    'kode_pos': r['kode_pos'] or '',
                    'kendaraan': r['kendaraan'] or '',
                    'nik': r['nik'] or '', 'npwp': r['npwp'] or '', 'npwp_name': r['npwp_name'] or '',
                    'inPlan': r['uuid'] in planned,
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'stores': stores, 'total': total})
        except Exception as e:
            write_log('ERROR', 'stores', f'ALL failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Store Order History (from wim_orders)
    # ═══════════════════════════════════════════════════

    def do_STORE_ORDERS(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        place_uuid = (qs.get('place_uuid') or [''])[0].strip()
        if not place_uuid:
            return self._send_json(400, {'error': 'place_uuid required'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT uuid, order_ref AS public_id, status, created_at, total AS grand_total FROM wim_orders "
                "WHERE store_id=%s AND deleted_at IS NULL "
                "ORDER BY created_at DESC LIMIT 3",
                (place_uuid,)
            )
            orders = []
            for r in cur.fetchall():
                orders.append({
                    'uuid': r['uuid'],
                    'orderId': r['public_id'],
                    'status': r['status'],
                    'createdAt': str(r['created_at']) if r['created_at'] else '',
                    'total': float(r['grand_total'] or 0),
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'orders': orders})
        except Exception as e:
            write_log('ERROR', 'orders', f'GET failed: {e}')
            self._send_json(200, {'orders': []})

    # ═══════════════════════════════════════════════════
    # Visit Plan (add luar rute store)
    # ═══════════════════════════════════════════════════

    def do_VISIT_PLAN_GET(self):
        """GET /api/visit_plan — route plans.
        API-key/admin: all reps' today plans (joined user names). Cookie: own plan."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        date = (qs.get('date') or [''])[0][:10]
        date_from = (qs.get('date_from') or [''])[0][:10]
        date_to = (qs.get('date_to') or [''])[0][:10]
        user_filter = (qs.get('user_id') or [None])[0]
        depot_filter = (qs.get('depot_id') or [''])[0].strip()
        region_filter = (qs.get('region_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            if user.get('is_api'):
                if date:
                    where = "WHERE vp.visit_date=%s"; params = [date]
                elif date_from and date_to:
                    where = "WHERE vp.visit_date >= %s AND vp.visit_date <= %s"; params = [date_from, date_to]
                elif date_from:
                    where = "WHERE vp.visit_date >= %s"; params = [date_from]
                elif date_to:
                    where = "WHERE vp.visit_date <= %s"; params = [date_to]
                else:
                    where = "WHERE vp.visit_date=%s"; params = [time.strftime('%Y-%m-%d')]
                if user_filter:
                    where += " AND vp.user_id=%s"; params.append(user_filter)
                if depot_filter:
                    where += " AND um.depot_id=%s"; params.append(int(depot_filter))
                if region_filter:
                    where += " AND ud.region_id=%s"; params.append(int(region_filter))
                cur.execute(
                    "SELECT vp.id, vp.place_uuid, vp.visit_date, vp.source, vp.status, "
                    "u.name AS user_name, u.id AS user_id, s.name AS store_name, "
                    "s.address, s.latitude, s.longitude, "
                    "um.depot_id AS user_depot_id, ud.name AS user_depot_name, "
                    "r.name AS region_name "
                    "FROM wim_visit_plan vp "
                    "LEFT JOIN wim_users u ON vp.user_id=u.id "
                    "LEFT JOIN wim_stores s ON vp.place_uuid=s.uuid "
                    "LEFT JOIN wim_user_meta um ON um.user_id=vp.user_id "
                    "LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
                    "LEFT JOIN wim_regions r ON r.id=ud.region_id "
                    f"{where} ORDER BY u.name, s.name",
                    params
                )
            else:
                d = date or time.strftime('%Y-%m-%d')
                cur.execute(
                    "SELECT vp.id, vp.place_uuid, vp.visit_date, vp.source, vp.status, "
                    "u.name AS user_name, u.id AS user_id, s.name AS store_name, "
                    "s.address, s.latitude, s.longitude "
                    "FROM wim_visit_plan vp "
                    "LEFT JOIN wim_users u ON vp.user_id=u.id "
                    "LEFT JOIN wim_stores s ON vp.place_uuid=s.uuid "
                    "WHERE vp.visit_date=%s AND vp.user_id=%s ORDER BY s.name",
                    (d, user['id'])
                )
            plans = []
            for r in cur.fetchall():
                plans.append({
                    'id': r['id'], 'placeUuid': r['place_uuid'],
                    'userName': r['user_name'] or '', 'userId': r['user_id'],
                    'visitDate': str(r['visit_date']) if r['visit_date'] else '',
                    'userDepotName': r.get('user_depot_name') or '',
                    'regionName': r.get('region_name') or '',
                    'storeName': r['store_name'] or 'Tanpa Nama',
                    'address': r['address'] or '', 'source': r['source'],
                    'status': r['status'],
                    'lat': float(r['latitude']) if r['latitude'] else None,
                    'lng': float(r['longitude']) if r['longitude'] else None,
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'plans': plans, 'total': len(plans)})
        except Exception as e:
            write_log('ERROR', 'visit_plan', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_VISIT_PLAN(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        place_uuid = (data.get('place_uuid') or '').strip()
        today = time.strftime('%Y-%m-%d')
        if not place_uuid:
            return self._send_json(400, {'error': 'place_uuid required'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO wim_visit_plan (user_id, place_uuid, visit_date, source, status) "
                "VALUES (%s, %s, %s, 'luar_rute', 'pending') "
                "ON CONFLICT DO NOTHING",
                (user['id'], place_uuid, today)
            )
            conn.commit()
            added = cur.rowcount > 0
            cur.close(); ret_pg(conn)
            self._send_json(200, {
                'status': 'ok',
                'added': added,
                'message': 'Toko ditambahkan ke daftar kunjungan' if added else 'Toko sudah ada dalam daftar',
            })
        except Exception as e:
            write_log('ERROR', 'visit_plan', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PLAN_DAY_GET(self):
        """GET /api/admin/plan/day?user_id=&date= — numbered kunjungan list for a sales+day.
        Returns {stores:[{seq, uuid, name, address, region, source, status}], planned:[]}."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get('user_id') or [''])[0]
        date = (qs.get('date') or [''])[0][:10]
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT vp.place_uuid, vp.source, vp.status, vp.seq_no, "
                "s.name, s.address, s.city, s.region_id, r.name AS region_name "
                "FROM wim_visit_plan vp "
                "LEFT JOIN wim_stores s ON vp.place_uuid=s.uuid "
                "LEFT JOIN wim_regions r ON s.region_id=r.id "
                "WHERE vp.user_id=%s AND vp.visit_date=%s ORDER BY vp.seq_no NULLS LAST, s.name",
                (uid, date))
            planned = set()
            stores = []
            for r in cur.fetchall():
                planned.add(r['place_uuid'])
                stores.append({
                    'uuid': r['place_uuid'], 'name': r['name'] or 'Tanpa Nama',
                    'address': r['address'] or '', 'city': r['city'] or '',
                    'regionName': r['region_name'] or '',
                    'source': r['source'] or 'route', 'status': r['status'] or 'pending',
                    'seq': r['seq_no'] or 0,
                })
            # All stores (for the picker), filtered by region/search + not already planned
            region_filter = (qs.get('region_id') or [''])[0].strip()
            q = (qs.get('q') or [''])[0].strip().lower()
            cond = "deleted_at IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL"
            params = []
            if region_filter:
                cond += " AND region_id=%s"; params.append(int(region_filter))
            if q:
                cond += " AND (LOWER(name) LIKE %s OR LOWER(city) LIKE %s)"
                params += [f'%{q}%', f'%{q}%']
            cur.execute(
                "SELECT uuid, name, address, city, region_id, "
                "(SELECT name FROM wim_regions wr WHERE wr.id=s.region_id) AS region_name "
                f"FROM wim_stores s WHERE {cond} ORDER BY name LIMIT 200", params)
            available = [{
                'uuid': r['uuid'], 'name': r['name'] or 'Tanpa Nama',
                'address': r['address'] or '', 'city': r['city'] or '',
                'regionName': r['region_name'] or '', 'inPlan': bool(r['uuid'] in planned),
            } for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {'stores': stores, 'available': available, 'planned': sorted(planned)})
        except Exception as e:
            write_log('ERROR', 'visit_plan', f'PLAN DAY GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PLAN_DAY_POST(self):
        """POST /api/admin/plan/day — save the numbered kunjungan list for a sales+day.
        Body: {user_id, date, stores:[uuid,...] (in order)}. Replaces the list; seq = position+1.
        Returns {saved:n}."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        uid = data.get('user_id')
        date = (data.get('date') or '')[:10]
        stores = data.get('stores') or []
        if not uid or not date:
            return self._send_json(400, {'error': 'user_id dan date diperlukan'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            # Delete existing rows for this user+date, then insert with seq order
            cur.execute("DELETE FROM wim_visit_plan WHERE user_id=%s AND visit_date=%s", (uid, date))
            for i, suuid in enumerate(stores, start=1):
                cur.execute(
                    "INSERT INTO wim_visit_plan (user_id, place_uuid, visit_date, source, status, seq_no) "
                    "VALUES (%s,%s,%s,'route','pending',%s) ON CONFLICT DO NOTHING",
                    (uid, suuid, date, i))
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'visit_plan', f'Plan saved: user {uid} {date} x {len(stores)} stores')
            self._send_json(200, {'status': 'ok', 'saved': len(stores)})
        except Exception as e:
            write_log('ERROR', 'visit_plan', f'PLAN DAY POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PLAN_TEMPLATES_GET(self):
        """GET /api/admin/plan/templates?user_id= — monthly repeating template slots (4x6)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get('user_id') or [''])[0].strip()
        if not uid: return self._send_json(400, {'error': 'user_id required'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # All 24 slots with store count
            cur.execute("""
                SELECT t.id, t.week_number, t.day_of_week,
                       COUNT(ts.id) AS store_count,
                       COALESCE(MAX(ts.visit_order),0) AS max_order
                FROM (SELECT w FROM generate_series(1,4) w) weeks
                CROSS JOIN generate_series(1,6) days(d)
                LEFT JOIN wim_visit_plan_templates t
                  ON t.user_id=%s AND t.week_number=weeks.w AND t.day_of_week=days.d
                LEFT JOIN wim_visit_plan_template_stores ts ON ts.template_id=t.id
                GROUP BY t.id, t.week_number, t.day_of_week, weeks.w, days.d
                ORDER BY weeks.w, days.d
            """, (int(uid),))
            slots = []
            for r in cur.fetchall():
                slots.append({
                    'week': r['week_number'] or '', 'day': r['day_of_week'] or '',
                    'count': int(r['store_count'] or 0), 'templateId': r['id'],
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'slots': slots})
        except Exception as e:
            write_log('ERROR', 'visit_plan', f'PLAN TEMPLATES GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PLAN_TEMPLATE_GET(self):
        """GET /api/admin/plan/template?user_id=&week=&day= — one slot's ordered stores + available stores."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get('user_id') or [''])[0].strip()
        week = (qs.get('week') or [''])[0].strip()
        day = (qs.get('day') or [''])[0].strip()
        if not uid or not week or not day:
            return self._send_json(400, {'error': 'user_id, week, day required'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # ordered stores for this slot (with geo + address + region ids)
            cur.execute("""
                SELECT s.uuid, s.name, s.address, s.city, s.latitude, s.longitude,
                       s.province_id, s.city_id, s.kecamatan_id, s.kelurahan_id,
                       s.kecamatan, s.kelurahan, s.province,
                       ts.visit_order AS seq
                FROM wim_visit_plan_template_stores ts
                JOIN wim_visit_plan_templates t ON t.id=ts.template_id
                JOIN wim_stores s ON s.uuid=ts.store_uuid
                WHERE t.user_id=%s AND t.week_number=%s AND t.day_of_week=%s
                ORDER BY ts.visit_order
            """, (int(uid), week, day))
            stores = [dict(r) for r in cur.fetchall()]
            planned = {r['uuid'] for r in stores}
            # available stores (active, with geo + address + region ids) not already planned
            cur.execute("""
                SELECT s.uuid, s.name, s.address, s.city, s.latitude, s.longitude,
                       s.province_id, s.city_id, s.kecamatan_id, s.kelurahan_id,
                       s.kecamatan, s.kelurahan, s.province
                FROM wim_stores s
                WHERE (s.status IS NULL OR s.status != 'closed')
                  AND s.latitude IS NOT NULL AND s.longitude IS NOT NULL
                ORDER BY s.name LIMIT 500
            """)
            available = []
            for r in cur.fetchall():
                d = dict(r)
                d['inPlan'] = bool(d['uuid'] in planned)
                available.append(d)
            cur.close(); ret_pg(conn)
            self._send_json(200, {'stores': stores, 'available': available})
        except Exception as e:
            write_log('ERROR', 'visit_plan', f'PLAN TEMPLATE GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PLAN_TEMPLATE_POST(self):
        """POST /api/admin/plan/template — save one slot's ordered store list (replace, seq=position)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        try:
            body = self._read_body(); data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        uid = data.get('user_id'); week = data.get('week'); day = data.get('day')
        stores = data.get('stores') or []  # ordered uuids
        if not uid or not week or not day:
            return self._send_json(400, {'error': 'user_id, week, day required'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            # upsert template slot
            cur.execute("""
                INSERT INTO wim_visit_plan_templates (user_id, week_number, day_of_week)
                VALUES (%s,%s,%s)
                ON CONFLICT (user_id, week_number, day_of_week) DO UPDATE SET week_number=EXCLUDED.week_number
                RETURNING id
            """, (uid, week, day))
            tpl_id = cur.fetchone()[0]
            # replace stores
            cur.execute("DELETE FROM wim_visit_plan_template_stores WHERE template_id=%s", (tpl_id,))
            for i, uuid in enumerate(stores):
                cur.execute("""
                    INSERT INTO wim_visit_plan_template_stores (template_id, store_uuid, visit_order)
                    VALUES (%s,%s,%s) ON CONFLICT DO NOTHING
                """, (tpl_id, uuid, i+1))
            conn.commit(); cur.close(); ret_pg(conn)
            write_log('INFO', 'visit_plan', f'Plan template saved user {uid} w{week}d{day} x {len(stores)}')
            self._send_json(200, {'status': 'ok', 'saved': len(stores), 'templateId': tpl_id})
        except Exception as e:
            write_log('ERROR', 'visit_plan', f'PLAN TEMPLATE POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PLAN_TEMPLATE_RESOLVE(self):
        """POST /api/admin/plan/template/resolve — materialize one slot into wim_visit_plan for a date."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        try:
            body = self._read_body(); data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        uid = data.get('user_id'); date = (data.get('date') or '')[:10]
        if not uid or not date:
            return self._send_json(400, {'error': 'user_id dan date required'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute("SELECT materialize_template_for_date(%s, %s::date)", (int(uid), date))
            n = cur.fetchone()[0]
            conn.commit(); cur.close(); ret_pg(conn)
            self._send_json(200, {'status': 'ok', 'materialized': n, 'user_id': int(uid), 'date': date})
        except Exception as e:
            write_log('ERROR', 'visit_plan', f'PLAN TEMPLATE RESOLVE failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_RENCANA_VIEW(self):
        """GET /api/admin/rencana/view?date= — lihat list kunjungan.
        Returns per-sales summary + per-store detail for a date:
        sales:[{userId,userName,region,status(Berjalan/belum masuk/sudah selesai),
                inRouteCount,outRouteCount,
                stores:[{storeUuid,storeName,source,visited,checkinAt,checkoutAt,
                         orderCount,alasan,checkinPhoto,photos}]}]"""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        qs = parse_qs(urlparse(self.path).query)
        date = (qs.get('date') or [''])[0][:10] or time.strftime('%Y-%m-%d')
        user_filter = (qs.get('user_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Auto-materialize templates into wim_visit_plan for this date so
            # templated visits actually appear (idempotent ON CONFLICT DO NOTHING).
            try:
                if user_filter:
                    cur.execute("SELECT materialize_template_for_date(%s, %s::date)", (int(user_filter), date))
                else:
                    cur.execute("SELECT user_id FROM wim_user_meta WHERE depot_id IS NOT NULL OR user_id IN (SELECT DISTINCT user_id FROM wim_visit_plan_templates)")
                    for rrow in cur.fetchall():
                        cur.execute("SELECT materialize_template_for_date(%s, %s::date)", (rrow['user_id'], date))
                conn.commit()
            except Exception as m_err:
                write_log('WARN', 'rencana', f'auto-materialize failed (non-fatal): {m_err}')
                conn.rollback()
            plan_where = "vp.visit_date=%s"
            plan_params = [date]
            if user_filter:
                plan_where += " AND vp.user_id=%s"
                plan_params.append(str(user_filter))
            cur.execute(
                "SELECT vp.user_id, u.name AS user_name, u.email, "
                "dp.name AS depot_name, ud.name AS region_name, "
                "vp.place_uuid, vp.source, vp.status AS plan_status, vp.seq_no, "
                "s.name AS store_name, "
                "(SELECT COUNT(*) FROM wim_orders o WHERE o.store_uuid=vp.place_uuid "
                "  AND o.user_id=vp.user_id AND o.deleted_at IS NULL AND DATE(o.created_at)=%s) AS order_count, "
                "(SELECT v.checkin_at FROM wim_visits v WHERE v.user_id=vp.user_id "
                "  AND v.place_uuid=vp.place_uuid AND DATE(v.checkin_at)=%s "
                "  AND v.checkout_at IS NOT NULL ORDER BY v.checkin_at DESC LIMIT 1) AS checkin_at, "
                "(SELECT v.checkout_at FROM wim_visits v WHERE v.user_id=vp.user_id "
                "  AND v.place_uuid=vp.place_uuid AND DATE(v.checkin_at)=%s "
                "  AND v.checkout_at IS NOT NULL ORDER BY v.checkin_at DESC LIMIT 1) AS checkout_at, "
                "(SELECT v.photos FROM wim_visits v WHERE v.user_id=vp.user_id "
                "  AND v.place_uuid=vp.place_uuid AND DATE(v.checkin_at)=%s "
                "  AND v.checkout_at IS NOT NULL ORDER BY v.checkin_at DESC LIMIT 1) AS photos, "
                "(SELECT v.checkin_photo FROM wim_visits v WHERE v.user_id=vp.user_id "
                "  AND v.place_uuid=vp.place_uuid AND DATE(v.checkin_at)=%s "
                "  AND v.checkout_at IS NOT NULL ORDER BY v.checkin_at DESC LIMIT 1) AS checkin_photo, "
                "(SELECT v.notes FROM wim_visits v WHERE v.user_id=vp.user_id "
                "  AND v.place_uuid=vp.place_uuid AND DATE(v.checkin_at)=%s "
                "  AND v.checkout_at IS NOT NULL ORDER BY v.checkin_at DESC LIMIT 1) AS notes "
                "FROM wim_visit_plan vp "
                "LEFT JOIN wim_users u ON vp.user_id=u.id "
                "LEFT JOIN wim_user_meta um ON um.user_id=vp.user_id "
                "LEFT JOIN wim_depots dp ON dp.id=um.depot_id "
                "LEFT JOIN wim_regions ud ON ud.id=dp.region_id "
                "LEFT JOIN wim_stores s ON vp.place_uuid=s.uuid "
                f"WHERE {plan_where} ORDER BY u.name, vp.seq_no, s.name",
                [date,date,date,date,date,date] + plan_params)
            byUser = {}
            order = []
            for r in cur.fetchall():
                uid = r['user_id']
                if uid not in byUser:
                    byUser[uid] = {'userId': uid, 'userName': r['user_name'] or '',
                                   'email': r['email'] or '', 'region': r['region_name'] or '',
                                   'inRouteCount': 0, 'outRouteCount': 0, 'stores': []}
                    order.append(uid)
                uu = byUser[uid]
                st = {
                    'storeUuid': r['place_uuid'], 'storeName': r['store_name'] or 'Tanpa Nama',
                    'source': r['source'] or 'route', 'visited': bool(r['checkin_at']),
                    'checkinAt': str(r['checkin_at']) if r['checkin_at'] else None,
                    'checkoutAt': str(r['checkout_at']) if r['checkout_at'] else None,
                    'orderCount': int(r['order_count'] or 0), 'alasan': r['notes'] or '',
                    'checkinPhoto': r['checkin_photo'] or '', 'photos': r['photos'] or '[]',
                }
                if st['source'] == 'luar_rute': uu['outRouteCount'] += 1
                else: uu['inRouteCount'] += 1
                uu['stores'].append(st)
            # status per sales: if all planned visited -> sudah selesai, some -> berjalan, none -> belum masuk
            sales = []
            for uid in order:
                uu = byUser[uid]
                total = len(uu['stores'])
                visited = sum(1 for s in uu['stores'] if s['visited'])
                if total == 0: status = 'belum_masuk'
                elif visited == total: status = 'selesai'
                elif visited > 0: status = 'berjalan'
                else: status = 'belum_masuk'
                uu['status'] = status
                sales.append(uu)
            cur.close(); ret_pg(conn)
            self._send_json(200, {'date': date, 'sales': sales})
        except Exception as e:
            write_log('ERROR', 'rencana', f'VIEW failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_VISITS_GET(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        date = (qs.get('date') or [''])[0][:10]
        if not date:
            date = time.strftime('%Y-%m-%d')
        date_from = (qs.get('date_from') or [''])[0][:10]
        date_to = (qs.get('date_to') or [''])[0][:10]
        user_filter = (qs.get('user_id') or [None])[0]
        depot_filter = (qs.get('depot_id') or [''])[0].strip()
        region_filter = (qs.get('region_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # API-key / external requests see ALL users' visits (admin scope); cookie users see only their own
            if user.get('is_api'):
                if date:
                    where = "WHERE DATE(v.checkin_at)=%s"; params = [date]
                elif date_from and date_to:
                    where = "WHERE DATE(v.checkin_at) >= %s AND DATE(v.checkin_at) <= %s"; params = [date_from, date_to]
                elif date_from:
                    where = "WHERE DATE(v.checkin_at) >= %s"; params = [date_from]
                elif date_to:
                    where = "WHERE DATE(v.checkin_at) <= %s"; params = [date_to]
                else:
                    where = "WHERE DATE(v.checkin_at)=%s"; params = [time.strftime('%Y-%m-%d')]
                if user_filter:
                    where += " AND v.user_id=%s"; params.append(user_filter)
                if depot_filter:
                    where += " AND um.depot_id=%s"; params.append(int(depot_filter))
                if region_filter:
                    where += " AND ud.region_id=%s"; params.append(int(region_filter))
                cur.execute(
                    "SELECT v.id, v.place_uuid, v.place_name, v.checkin_at, v.checkout_at, v.duration_seconds, "
                    "v.status, v.photos, v.notes, v.location_lat, v.location_lng, v.source, u.name AS user_name, "
                    "v.user_id, um.depot_id AS user_depot_id, ud.name AS user_depot_name, "
                    "r.name AS region_name "
                    "FROM wim_visits v LEFT JOIN wim_users u ON v.user_id=u.id "
                    "LEFT JOIN wim_user_meta um ON um.user_id=v.user_id "
                    "LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
                    "LEFT JOIN wim_regions r ON r.id=ud.region_id "
                    f"{where} ORDER BY v.checkin_at DESC",
                    params
                )
            else:
                cur.execute(
                    "SELECT id, place_uuid, place_name, checkin_at, checkout_at, duration_seconds, "
                    "status, photos, notes, location_lat, location_lng, source "
                    "FROM wim_visits WHERE user_id=%s AND DATE(checkin_at)=%s ORDER BY checkin_at DESC",
                    (user['id'], date)
                )
            visits = []
            for r in cur.fetchall():
                visits.append({
                    'id': r['id'],
                    'user_id': r.get('user_id'),
                    'user_name': r.get('user_name') or '',
                    'userDepotName': r.get('user_depot_name') or '', 'regionName': r.get('region_name') or '',
                    'placeUuid': r['place_uuid'],
                    'placeName': r['place_name'],
                    'checkinAt': str(r['checkin_at']) if r['checkin_at'] else None,
                    'checkoutAt': str(r['checkout_at']) if r['checkout_at'] else None,
                    'durationSeconds': r['duration_seconds'],
                    'status': r['status'],
                    'photos': r['photos'] if r['photos'] else '[]',
                    'notes': r['notes'] or '',
                    'lat': float(r['location_lat']) if r['location_lat'] else None,
                    'lng': float(r['location_lng']) if r['location_lng'] else None,
                    'source': r['source'],
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'visits': visits})
        except Exception as e:
            write_log('ERROR', 'visits', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_VISITS_POST(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        action = data.get('action', '')
        place_uuid = (data.get('place_uuid') or '').strip()
        place_name = data.get('place_name', '')
        if action in ('checkin', 'checkout') and not place_uuid:
            return self._send_json(400, {'error': 'place_uuid diperlukan'})
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        lat = data.get('lat')
        lng = data.get('lng')
        source = data.get('source', 'route')
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            if action == 'checkin':
                # Prevent double check-in to the SAME store.
                cur.execute(
                    "SELECT id FROM wim_visits WHERE user_id=%s AND place_uuid=%s "
                    "AND checkout_at IS NULL LIMIT 1",
                    (user['id'], place_uuid)
                )
                if cur.fetchone():
                    cur.close(); ret_pg(conn)
                    return self._send_json(409, {'error': 'Kunjungan sudah check-in, selesaikan dulu'})
                # Prevent a SECOND concurrent active visit (one open visit per rep at a time).
                cur.execute(
                    "SELECT place_name FROM wim_visits WHERE user_id=%s AND checkout_at IS NULL "
                    "ORDER BY id DESC LIMIT 1",
                    (user['id'],)
                )
                other = cur.fetchone()
                if other:
                    cur.close(); ret_pg(conn)
                    return self._send_json(409, {
                        'error': 'Masih ada kunjungan aktif di "%s". Selesaikan dulu sebelum check-in toko lain.' % other[0]
                    })
                # Geofence: require the rep's reported location to be within ~10m of the store
                # (when both the store coords and the sent location are available).
                GEOFENCE_RADIUS_M = 10.0
                try:
                    cur2 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                    cur2.execute("SELECT latitude, longitude FROM wim_stores WHERE uuid=%s", (place_uuid,))
                    srow = cur2.fetchone()
                    cur2.close()
                    if srow and srow.get('latitude') is not None and lat is not None and lng is not None:
                        dist_m = haversine_m(lat, lng, float(srow['latitude']), float(srow['longitude']))
                        if dist_m is not None and dist_m > GEOFENCE_RADIUS_M:
                            cur.close(); ret_pg(conn)
                            return self._send_json(400, {
                                'error': f'Lokasi terlalu jauh dari toko (~{int(dist_m)}m). Silakan ke lokasi toko (max {int(GEOFENCE_RADIUS_M)}m)'
                            })
                except Exception:
                    pass  # if DB lookup fails, do not block check-in
                cur.execute(
                    "INSERT INTO wim_visits (user_id, place_uuid, place_name, "
                    "checkin_at, location_lat, location_lng, source, checkin_photo) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (user['id'], place_uuid, place_name,
                     now, lat, lng, source, data.get('checkin_photo') or None)
                )
                row = cur.fetchone()
                visit_id = row[0] if row else None
                conn.commit()
                write_log('INFO', 'visits', f'Checkin: {user["email"]} @ {place_name}')
                self._send_json(200, {'status': 'ok', 'action': 'checkin', 'visitId': visit_id})
            elif action == 'checkout':
                photos = data.get('photos', '[]')
                notes = data.get('notes', '')
                duration = data.get('durationSeconds', 0)
                status_v = data.get('status', 'visited')
                # Server-side minimum visit duration check (3 min = 180s)
                cur.execute(
                    "SELECT checkin_at FROM wim_visits WHERE user_id=%s AND place_uuid=%s "
                    "AND checkout_at IS NULL ORDER BY id DESC LIMIT 1",
                    (user['id'], place_uuid)
                )
                checkin_row = cur.fetchone()
                if checkin_row:
                    checkin_time = checkin_row[0]
                    if isinstance(checkin_time, str):
                        checkin_dt = datetime.datetime.strptime(checkin_time, '%Y-%m-%d %H:%M:%S')
                    else:
                        checkin_dt = checkin_time
                    elapsed = (datetime.datetime.now() - checkin_dt).total_seconds()
                    if elapsed < MIN_VISIT_SECONDS:
                        cur.close(); ret_pg(conn)
                        return self._send_json(400, {
                            'error': f'Kunjungan minimal 3 menit. Tunggu {int(MIN_VISIT_SECONDS - elapsed)} detik lagi'
                        })
                cur.execute(
                    "UPDATE wim_visits SET checkout_at=%s, duration_seconds=%s, photos=%s, notes=%s, status=%s "
                    "WHERE id = (SELECT id FROM wim_visits WHERE user_id=%s AND place_uuid=%s "
                    "AND checkout_at IS NULL ORDER BY id DESC LIMIT 1)",
                    (now, duration, photos, notes, status_v, user['id'], place_uuid)
                )
                if cur.rowcount == 0:
                    cur.close(); ret_pg(conn)
                    return self._send_json(400, {'error': 'Belum ada check-in untuk toko ini'})
                # Also update visit plan status
                today = time.strftime('%Y-%m-%d')
                cur.execute(
                    "UPDATE wim_visit_plan SET status='visited' "
                    "WHERE user_id=%s AND place_uuid=%s AND visit_date=%s",
                    (user['id'], place_uuid, today)
                )
                conn.commit()
                write_log('INFO', 'visits', f'Checkout: {user["email"]} @ {place_name}')
                self._send_json(200, {'status': 'ok', 'action': 'checkout'})
            else:
                cur.close(); ret_pg(conn)
                return self._send_json(400, {'error': f'Unknown action: {action}'})
            cur.close(); ret_pg(conn)
        except Exception as e:
            write_log('ERROR', 'visits', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ── Active Visit (current check-in without checkout)
    def do_VISITS_ACTIVE(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        # Optional place_uuid filter: return the open visit for THIS store, or null.
        qs = parse_qs(urlparse(self.path).query)
        place_filter = (qs.get('place_uuid') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            if place_filter:
                cur.execute(
                    "SELECT id, place_uuid, place_name, checkin_at, source FROM wim_visits "
                    "WHERE user_id=%s AND checkout_at IS NULL AND place_uuid=%s "
                    "ORDER BY id DESC LIMIT 1",
                    (user['id'], place_filter)
                )
            else:
                cur.execute(
                    "SELECT id, place_uuid, place_name, checkin_at, source FROM wim_visits "
                    "WHERE user_id=%s AND checkout_at IS NULL ORDER BY id DESC LIMIT 1",
                    (user['id'],)
                )
            row = cur.fetchone()
            cur.close(); ret_pg(conn)
            if row:
                visit = {
                    'id': row['id'],
                    'place_uuid': row['place_uuid'],
                    'place_name': row['place_name'],
                    'checkin_at': str(row['checkin_at']) if row['checkin_at'] else None,
                    'source': row['source'],
                }
                self._send_json(200, {'visit': visit, 'active': visit})
            else:
                self._send_json(200, {'visit': None, 'active': None})
        except Exception as e:
            write_log('ERROR', 'visits', f'ACTIVE failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Report (per-user)
    # ═══════════════════════════════════════════════════

    def do_REPORT(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        period = (qs.get('period') or ['harian'])[0]
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Attendance count this month
            cur.execute(
                "SELECT COUNT(*) as c FROM wim_attendance "
                "WHERE user_id=%s AND EXTRACT(MONTH FROM date)=EXTRACT(MONTH FROM NOW()) "
                "AND EXTRACT(YEAR FROM date)=EXTRACT(YEAR FROM NOW()) AND clock_in IS NOT NULL",
                (user['id'],)
            )
            att_days = cur.fetchone()['c']

            # Visits this month
            cur.execute(
                "SELECT COUNT(*) as c FROM wim_visits "
                "WHERE user_id=%s AND EXTRACT(MONTH FROM checkin_at)=EXTRACT(MONTH FROM NOW()) "
                "AND EXTRACT(YEAR FROM checkin_at)=EXTRACT(YEAR FROM NOW())",
                (user['id'],)
            )
            visit_count = cur.fetchone()['c']

            # Distinct stores visited this month
            cur.execute(
                "SELECT COUNT(DISTINCT place_uuid) as c FROM wim_visits "
                "WHERE user_id=%s AND EXTRACT(MONTH FROM checkin_at)=EXTRACT(MONTH FROM NOW()) "
                "AND EXTRACT(YEAR FROM checkin_at)=EXTRACT(YEAR FROM NOW())",
                (user['id'],)
            )
            stores_visited = cur.fetchone()['c']

            # Orders for this user
            cur.execute(
                "SELECT COUNT(*) as c FROM wim_orders WHERE user_id=%s AND deleted_at IS NULL",
                (user['id'],)
            )
            order_count = cur.fetchone()['c']

            # Daily breakdown (last 7 days)
            cur.execute(
                "SELECT a.date, a.clock_in, a.clock_out, a.duration, "
                "(SELECT COUNT(*) FROM wim_visits v WHERE v.user_id=a.user_id "
                "AND DATE(v.checkin_at)=a.date) as visits "
                "FROM wim_attendance a "
                "WHERE a.user_id=%s AND a.date >= (NOW() - INTERVAL '7 days')::date "
                "ORDER BY a.date DESC",
                (user['id'],)
            )
            daily = [
                {
                    'date': str(r['date']),
                    'clockIn': r['clock_in'],
                    'clockOut': r['clock_out'],
                    'duration': r['duration'],
                    'visits': r['visits'],
                }
                for r in cur.fetchall()
            ]

            cur.close(); ret_pg(conn)
            self._send_json(200, {
                'attendanceDays': att_days,
                'visits': visit_count,
                'storesVisited': stores_visited,
                'orders': order_count,
                'daily': daily,
            })
        except Exception as e:
            write_log('ERROR', 'report', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Stock Check (persist per-store stock data)
    # ═══════════════════════════════════════════════════

    def do_STOCK_POST(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        place_uuid = (data.get('place_uuid') or '').strip()
        items = data.get('items', [])
        if not place_uuid or not items:
            return self._send_json(400, {'error': 'place_uuid dan items diperlukan'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            today = time.strftime('%Y-%m-%d %H:%M:%S')
            for item in items:
                sku = item.get('sku', '')
                qty = int(item.get('qty', 0))
                if sku and qty >= 0:
                    cur.execute(
                        "INSERT INTO wim_stock_check (user_id, place_uuid, sku, qty, checked_at) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (user['id'], place_uuid, sku, qty, today)
                    )
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'stock', f'Stock check: {user["email"]} @ {place_uuid} ({len(items)} items)')
            self._send_json(200, {'status': 'ok', 'count': len(items)})
        except Exception as e:
            write_log('ERROR', 'stock', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_STOCK_GET(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        place_uuid = (qs.get('place_uuid') or [''])[0].strip()
        if not place_uuid:
            return self._send_json(400, {'error': 'place_uuid parameter required'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT sku, qty, checked_at FROM wim_stock_check "
                "WHERE user_id=%s AND place_uuid=%s ORDER BY checked_at DESC LIMIT 20",
                (user['id'], place_uuid)
            )
            items = [{'sku': r['sku'], 'qty': r['qty'], 'checkedAt': str(r['checked_at'])} for r in cur.fetchall()]

            # previousOrderQty: last order qty for this store+SKU from wim_orders.items JSONB
            prev_qty = {}
            if items:
                cur.execute(
                    "SELECT items FROM wim_orders WHERE deleted_at IS NULL "
                    "AND store_uuid=%s ORDER BY created_at DESC LIMIT 20",
                    (place_uuid,)
                )
                for r in cur.fetchall():
                    items_data = r['items']
                    if items_data and isinstance(items_data, (list, tuple)):
                        for it in items_data:
                            if isinstance(it, dict):
                                sku = it.get('sku')
                                if sku and sku not in prev_qty:
                                    prev_qty[sku] = it.get('qty', 0)
            for item in items:
                item['previousOrderQty'] = prev_qty.get(item['sku'], 0)

            cur.close(); ret_pg(conn)
            self._send_json(200, {'items': items})
        except Exception as e:
            write_log('ERROR', 'stock', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Products catalog (from wim_products)
    # ═══════════════════════════════════════════════════

    def do_PRODUCTS(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        brand = (qs.get('brand') or [''])[0].strip()
        search = (qs.get('q') or [''])[0].strip()
        store_uuid = (qs.get('store') or [None])[0]
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Resolve the DEPOT whose price to show: store's depot first, else the rep's depot.
            # (Pricing is per depot, not per region/area.)
            depot_id = None
            if store_uuid:
                cur.execute("SELECT depot_id FROM wim_stores WHERE uuid=%s AND deleted_at IS NULL", (store_uuid,))
                st = cur.fetchone()
                if st: depot_id = st.get('depot_id')
            if not depot_id and user.get('id'):
                cur.execute(
                    "SELECT um.depot_id FROM wim_user_meta um WHERE um.user_id=%s LIMIT 1",
                    (user.get('id'),))
                rr = cur.fetchone()
                if rr: depot_id = rr.get('depot_id')
            where = "WHERE p.deleted_at IS NULL"
            params = []
            if brand:
                where += " AND p.brand=%s"; params.append(brand)
            if search:
                where += " AND (p.name ILIKE %s OR p.sku ILIKE %s)"
                params.extend([f'%{search}%', f'%{search}%'])
            cur.execute(
                f"SELECT p.uuid, p.name, p.sku, p.brand, p.category, p.price, p.description, "
                f"p.weight, p.weight_unit, p.unit, p.qty_per_unit, p.meta, "
                f"pp.price AS area_price, pp.effective_from, pp.depot_id AS price_depot_id "
                f"FROM wim_products p "
                f"LEFT JOIN wim_product_prices pp ON pp.product_uuid=p.uuid AND pp.depot_id=%s "
                f"{where} ORDER BY p.name",
                [depot_id] + params
            )
            products = []
            for r in cur.fetchall():
                meta = r['meta'] or {}
                area_price = r['area_price'] if r['area_price'] is not None else r['price']
                products.append({
                    'uuid': r['uuid'],
                    'name': r['name'],
                    'sku': r['sku'],
                    'price': float(area_price) if area_price else 0,
                    'basePrice': float(r['price']) if r['price'] else 0,
                    'isAreaPrice': r['area_price'] is not None,
                    'depotId': r['price_depot_id'] or depot_id,
                    'brand': r['brand'] or '',
                    'category': r['category'] or '',
                    'description': r['description'] or '',
                    'weight': float(r['weight'] or 0),
                    'weightUnit': r['weight_unit'] or 'pcs',
                    'unit': r['unit'] or 'karton',
                    'qtyPerUnit': r['qty_per_unit'] or 1,
                    'image': meta.get('image') or '',
                })
            cur.close(); ret_pg(conn)
            brands = sorted(set(p['brand'] for p in products if p['brand']))
            self._send_json(200, {'products': products, 'brands': brands, 'total': len(products), 'depotId': depot_id})
        except Exception as e:
            write_log('ERROR', 'products', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PRODUCTS_POST(self):
        """Create a product. super_admin/admin only. Canonical wim_products schema."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        sku = (data.get('sku') or '').strip()
        name = (data.get('name') or '').strip()
        if not sku or not name:
            return self._send_json(400, {'error': 'sku dan name diperlukan'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT 1 FROM wim_products WHERE sku=%s AND deleted_at IS NULL", (sku,))
            if cur.fetchone():
                cur.close(); ret_pg(conn)
                return self._send_json(409, {'error': 'SKU sudah ada'})
            cur.execute(
                "INSERT INTO wim_products (name, sku, price, brand, category, unit, qty_per_unit, "
                "weight, weight_unit, description, is_active) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE) "
                "RETURNING uuid, id",
                (name, sku, float(data.get('price', 0)),
                 (data.get('brand') or ''), (data.get('category') or ''),
                 (data.get('unit') or 'karton'), int(data.get('qty_per_unit', 1) or 1),
                 float(data.get('weight', 0) or 0), (data.get('weight_unit') or 'pcs'),
                 (data.get('description') or '')))
            r = cur.fetchone()
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'products', f'Product created: {sku} by {user["email"]}')
            self._send_json(201, {'data': {'uuid': r['uuid'], 'id': r['id'], 'sku': sku}})
        except Exception as e:
            write_log('ERROR', 'products', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PRODUCTS_PATCH(self, params):
        """Update a product (details/pricing/image). Admin only. uuid in path."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        uuid = params['uuid']
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT uuid FROM wim_products WHERE uuid=%s AND deleted_at IS NULL", (uuid,))
            if not cur.fetchone():
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'Produk tidak ditemukan'})
            set_clauses = []
            params_list = []
            # scalar fields (nullable-safe)
            for field, col in (('name','name'),('sku','sku'),('price','price'),('brand','brand'),
                               ('category','category'),('unit','unit'),('qty_per_unit','qty_per_unit'),
                               ('weight','weight'),('weight_unit','weight_unit'),('description','description')):
                if field in data and data[field] is not None:
                    set_clauses.append(f"{col}=%s")
                    v = data[field]
                    if field in ('price','weight'):
                        try: v = float(v)
                        except: return self._send_json(400, {'error': f'{field} tidak valid'})
                    if field == 'qty_per_unit':
                        try: v = int(v)
                        except: return self._send_json(400, {'error': 'qty_per_unit tidak valid'})
                    params_list.append(v)
            if 'is_active' in data and isinstance(data['is_active'], bool):
                set_clauses.append("is_active=%s")
                params_list.append(data['is_active'])
            # image stored in meta JSONB (no schema change)
            if 'image' in data:
                set_clauses.append("meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb")
                params_list.append(json.dumps({'image': data['image']}))
            if not set_clauses:
                cur.close(); ret_pg(conn)
                return self._send_json(400, {'error': 'Belum ada field untuk diperbarui'})
            params_list.append(uuid)
            cur.execute(
                f"UPDATE wim_products SET {', '.join(set_clauses)} WHERE uuid=%s AND deleted_at IS NULL",
                params_list
            )
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'products', f'Product updated: {uuid} by {user["email"]}')
            self._send_json(200, {'status': 'ok', 'message': 'Produk diperbarui', 'uuid': uuid})
        except Exception as e:
            write_log('ERROR', 'products', f'PATCH failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ── Area-based pricing (2026-09-10) ──────────────────────────────
    def do_PRODUCTS_PRICES_GET(self):
        """GET /api/admin/products/prices — current prices PER DEPOT per product.
        Returns products with base price + a per-depot map of {price, effective_from}."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT id,name FROM wim_depots WHERE is_active IS NOT FALSE ORDER BY name")
            depots = [{'id': r['id'], 'name': r['name']} for r in cur.fetchall()]
            cur.execute(
                "SELECT p.uuid, p.sku, p.name, p.price, "
                "pp.depot_id, pp.price AS depot_price, pp.effective_from "
                "FROM wim_products p "
                "LEFT JOIN wim_product_prices pp ON pp.product_uuid=p.uuid "
                "WHERE p.deleted_at IS NULL ORDER BY p.name, pp.depot_id"
            )
            products = {}
            order = []
            for r in cur.fetchall():
                if r['uuid'] not in products:
                    products[r['uuid']] = {
                        'uuid': r['uuid'], 'sku': r['sku'], 'name': r['name'],
                        'basePrice': float(r['price'] or 0),
                        'depotPrices': {},  # depot_id -> {price, effectiveFrom}
                    }
                    order.append(r['uuid'])
                if r['depot_id'] is not None:
                    products[r['uuid']]['depotPrices'][r['depot_id']] = {
                        'price': float(r['depot_price'] or 0),
                        'effectiveFrom': str(r['effective_from']) if r['effective_from'] else None,
                    }
            cur.close(); ret_pg(conn)
            out = [products[u] for u in order]
            self._send_json(200, {'products': out, 'depots': depots, 'total': len(out)})
        except Exception as e:
            write_log('ERROR', 'prices', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PRODUCTS_PRICES_POST(self):
        """POST /api/admin/products/prices — bulk set DEPOT prices.
        Body: { entries:[{sku, price, effective_from}], depotIds:[1,2], allDepots:bool }
        UPSERTs into wim_product_prices per (sku × depot). Returns changed + skipped summary."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Admin hanya'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        entries = data.get('entries') or []
        removes = data.get('removes') or []
        if not entries and not removes:
            return self._send_json(400, {'error': 'entries/removes diperlukan'})
        depot_ids = data.get('depotIds') or []
        all_depots = bool(data.get('allDepots'))
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            if all_depots:
                cur.execute("SELECT id FROM wim_depots WHERE is_active IS NOT FALSE")
                depot_ids = [r['id'] for r in cur.fetchall()]
            if not depot_ids and (entries or removes):
                cur.close(); ret_pg(conn)
                return self._send_json(400, {'error': 'Pilih minimal satu depo'})
            changed = []
            removed = []
            skipped = 0
            # 1) removes: delete the overrides (restore to base) for these sku×depot
            for e in removes:
                sku = (e.get('sku') or '').strip()
                if not sku: continue
                cur.execute("SELECT uuid FROM wim_products WHERE sku=%s AND deleted_at IS NULL", (sku,))
                prow = cur.fetchone()
                if not prow:
                    skipped += 1; continue
                puuid = prow['uuid']
                for did in depot_ids:
                    cur.execute("DELETE FROM wim_product_prices WHERE product_uuid=%s AND depot_id=%s RETURNING price",
                                (puuid, did))
                    row = cur.fetchone()
                    if row:
                        removed.append({'sku': sku, 'depotId': did, 'priceRemoved': float(row['price'])})
            # 2) upserts: set new depot prices
            for e in entries:
                sku = (e.get('sku') or '').strip()
                try: price = float(e.get('price'))
                except: return self._send_json(400, {'error': f'price tidak valid untuk {sku}'})
                eff = (e.get('effective_from') or time.strftime('%Y-%m-%d'))
                if not sku:
                    continue
                cur.execute("SELECT uuid FROM wim_products WHERE sku=%s AND deleted_at IS NULL", (sku,))
                prow = cur.fetchone()
                if not prow:
                    skipped += 1; continue
                puuid = prow['uuid']
                for did in depot_ids:
                    # current price for this depot (for preview summary)
                    cur.execute(
                        "SELECT pp.price, pp.effective_from, d.region_id FROM wim_product_prices pp "
                        "LEFT JOIN wim_depots d ON d.id=pp.depot_id "
                        "WHERE pp.product_uuid=%s AND pp.depot_id=%s", (puuid, did))
                    prev = cur.fetchone()
                    price_before = float(prev['price']) if prev else float(e.get('basePrice', 0))
                    set_date_before = str(prev['effective_from']) if prev and prev['effective_from'] else None
                    dep_region = prev['region_id'] if prev else None
                    # if region unknown, resolve from depot
                    if not dep_region:
                        cur.execute("SELECT region_id FROM wim_depots WHERE id=%s", (did,))
                        dr = cur.fetchone()
                        dep_region = dr['region_id'] if dr else None
                    cur.execute(
                        "INSERT INTO wim_product_prices (product_uuid, depot_id, region_id, price, effective_from) "
                        "VALUES (%s,%s,%s,%s,%s) "
                        "ON CONFLICT (product_uuid, depot_id) WHERE depot_id IS NOT NULL DO UPDATE SET "
                        "price=EXCLUDED.price, effective_from=EXCLUDED.effective_from, region_id=EXCLUDED.region_id",
                        (puuid, did, dep_region, price, eff))
                    changed.append({
                        'sku': sku, 'depotId': did, 'priceBefore': price_before,
                        'setDateBefore': set_date_before, 'priceAfter': price,
                        'effectiveFrom': eff,
                    })
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'prices', f'Bulk depot pricing applied for {len(entries)} sku x {len(depot_ids)} depots')
            self._send_json(200, {
                'status': 'ok', 'changed': changed, 'changedCount': len(changed),
                'removed': removed, 'removedCount': len(removed),
                'skipped': skipped, 'depotIds': depot_ids, 'allDepots': all_depots,
            })
        except Exception as e:
            write_log('ERROR', 'prices', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Promos (from wim_promo)
    # ═══════════════════════════════════════════════════

    def do_PROMOS(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        # Resolve rep's region (user depot -> region)
        rep_region = None
        try:
            conn0 = get_pg()
            if conn0:
                cur0 = conn0.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur0.execute(
                    "SELECT d.region_id FROM wim_user_meta um "
                    "LEFT JOIN wim_depots d ON d.id=um.depot_id WHERE um.user_id=%s LIMIT 1",
                    (user.get('id'),))
                row0 = cur0.fetchone()
                if row0: rep_region = row0.get('region_id')
                cur0.close(); ret_pg(conn0)
        except Exception:
            rep_region = None
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Multi-area applicability: a promo applies if it has NO area rows (global/all areas)
            # OR the rep's region is among its wim_promo_regions, OR legacy single region matches.
            area_cond = ""
            params = []
            if rep_region:
                area_cond = ("AND p.deleted_at IS NULL AND ( EXISTS (SELECT 1 FROM wim_promo_regions wr "
                             "WHERE wr.promo_id=p.id AND wr.region_id=%s) "
                             "OR NOT EXISTS (SELECT 1 FROM wim_promo_regions wr2 WHERE wr2.promo_id=p.id) "
                             "OR p.region_id=%s ) ")
                params = [rep_region, rep_region]
            else:
                area_cond = "AND p.deleted_at IS NULL "
            cur.execute(
                "SELECT p.id, p.promo_ref, p.nama, p.jenis, p.status, p.priority, p.stackable, "
                "p.periode_start, p.periode_end, p.min_transaction_amount, p.max_discount_amount, "
                "p.region_id, r.name AS region_name, "
                "pc.condition_type, pc.condition_value, "
                "pr.reward_type, pr.reward_value, pr.reward_sku_ref, pr.reward_qty "
                "FROM wim_promo p "
                "LEFT JOIN wim_promo_conditions pc ON p.id=pc.promo_id "
                "LEFT JOIN wim_promo_rewards pr ON p.id=pr.promo_id "
                "LEFT JOIN wim_regions r ON p.region_id=r.id "
                f"WHERE p.status='active' AND (p.periode_end IS NULL OR p.periode_end >= CURRENT_DATE) "
                f"{area_cond}"
                f"ORDER BY p.priority, p.id", params)
            promos_dict = {}
            for r in cur.fetchall():
                pid = r['id']
                if pid not in promos_dict:
                    promos_dict[pid] = {
                        'id': pid,
                        'promoRef': r['promo_ref'],
                        'nama': r['nama'],
                        'jenis': r['jenis'],
                        'priority': r['priority'],
                        'stackable': bool(r['stackable']),
                        'periodeStart': str(r['periode_start']) if r['periode_start'] else None,
                        'periodeEnd': str(r['periode_end']) if r['periode_end'] else None,
                        'minTransaction': float(r['min_transaction_amount'] or 0),
                        'maxDiscount': float(r['max_discount_amount'] or 0),
                        'regionId': r.get('region_id'),
                        'regionName': r.get('region_name') or '',
                        'conditions': [],
                        'rewards': [],
                    }
                if r['condition_type']:
                    cv = r['condition_value']
                    if isinstance(cv, str):
                        try: cv = json.loads(cv)
                        except: pass
                    promos_dict[pid]['conditions'].append({'type': r['condition_type'], 'value': cv})
                if r['reward_type']:
                    rv = r['reward_value']
                    if isinstance(rv, str):
                        try: rv = json.loads(rv)
                        except: pass
                    promos_dict[pid]['rewards'].append({
                        'type': r['reward_type'],
                        'value': rv,
                        'skuRef': r['reward_sku_ref'],
                        'qty': r['reward_qty'],
                    })
            # attach the full area (region id) list per promo
            promo_ids = list(promos_dict.keys())
            if promo_ids:
                cur.execute(
                    "SELECT promo_id, region_id FROM wim_promo_regions WHERE promo_id = ANY(%s)",
                    (promo_ids,))
                for wr in cur.fetchall():
                    if wr['promo_id'] in promos_dict:
                        promos_dict[wr['promo_id']].setdefault('regionIds', []).append(wr['region_id'])
                for pdd in promos_dict.values():
                    pdd.setdefault('regionIds', [])
            cur.close(); ret_pg(conn)
            self._send_json(200, {'promos': list(promos_dict.values())})
        except Exception as e:
            write_log('ERROR', 'promos', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PROMOS_ADMIN_PATCH(self, params):
        """PATCH /api/admin/promos/:id — edit promo header fields + status toggle (super_admin/admin)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ('super_admin', 'admin'):
            return self._send_json(403, {'error': 'Hanya super_admin/admin'})
        pid = params.get('id')
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        set_clauses = []
        params_list = []
        for f in ('nama', 'jenis', 'status'):
            if f in data and data[f] is not None:
                v = data[f]
                if f == 'nama':
                    v = str(v).encode('ascii', 'replace').decode('ascii')
                set_clauses.append(f"{f}=%s")
                params_list.append(v)
        if 'priority' in data and data['priority'] is not None:
            set_clauses.append("priority=%s"); params_list.append(int(data['priority']))
        if 'stackable' in data and isinstance(data['stackable'], bool):
            set_clauses.append("stackable=%s"); params_list.append(bool(data['stackable']))
        if 'region_id' in data or 'regionId' in data:
            set_clauses.append("region_id=%s")
            params_list.append(data.get('regionId', data.get('region_id')) or None)
        if 'periode_start' in data:
            set_clauses.append("periode_start=%s"); params_list.append(data['periode_start'] or None)
        if 'periode_end' in data:
            set_clauses.append("periode_end=%s"); params_list.append(data['periode_end'] or None)
        # Redeem limits: treat '' as NULL (unlimited)
        for f, k in (('redeem_limit_per_order', 'redeemLimitPerOrder'),
                     ('redeem_limit_lifetime', 'redeemLimitLifetime')):
            if k in data:
                v = data[k]
                val = int(v) if v not in (None, '', 'null') else None
                set_clauses.append(f"{f}=%s"); params_list.append(val)
        has_reqs = ('requirements' in data or 'reward' in data
                    or 'conditions' in data or 'rewards' in data)
        has_region = ('regionIds' in data or 'allAreas' in data
                      or 'region_id' in data or 'regionId' in data)
        if not set_clauses and not has_reqs and not has_region:
            return self._send_json(400, {'error': 'Belum ada field untuk diperbarui'})
        params_list.append(pid)
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            if set_clauses:
                cur.execute(
                    f"UPDATE wim_promo SET {', '.join(set_clauses)} WHERE id=%s AND deleted_at IS NULL",
                    params_list
                )
                conn.commit()
                ok = cur.rowcount > 0
                if not ok:
                    cur.close(); ret_pg(conn)
                    return self._send_json(404, {'error': 'Promo tidak ditemukan'})
            # Replace conditions/rewards if provided (structured requirements/reward OR legacy arrays)
            if has_reqs:
                cur.execute("SELECT 1 FROM wim_promo WHERE id=%s AND deleted_at IS NULL", (pid,))
                if not cur.fetchone():
                    cur.close(); ret_pg(conn)
                    return self._send_json(404, {'error': 'Promo tidak ditemukan'})
                cur.execute("DELETE FROM wim_promo_conditions WHERE promo_id=%s", (pid,))
                cur.execute("DELETE FROM wim_promo_rewards WHERE promo_id=%s", (pid,))
                reqs = data.get('requirements')
                if isinstance(reqs, list):
                    for idx, rq in enumerate(reqs):
                        sku = (rq.get('sku') or '').strip() or None   # None = Any Product
                        qty = int(rq.get('qty') or 0)
                        and_or = (rq.get('andOr') or 'or') if idx > 0 else None
                        if qty > 0:
                            cur.execute(
                                "INSERT INTO wim_promo_conditions (promo_id, condition_type, condition_value, and_or) "
                                "VALUES (%s,'required_sku',%s,%s)",
                                (pid, json.dumps({'sku': sku, 'qty': qty}), and_or))
                    rw = data.get('reward') or {}
                    rtype = (rw.get('type') or '').strip()
                    if rtype == 'free_sku':
                        cur.execute(
                            "INSERT INTO wim_promo_rewards (promo_id, reward_type, reward_sku_ref, reward_qty) "
                            "VALUES (%s,'free_sku',%s,%s)",
                            (pid, (rw.get('sku') or '').strip(), int(rw.get('qty') or 1)))
                    elif rtype in ('discount_amount', 'flat_discount'):
                        amt = float(rw.get('amount', rw.get('value', 0)) or 0)
                        cur.execute(
                            "INSERT INTO wim_promo_rewards (promo_id, reward_type, reward_value) "
                            "VALUES (%s,%s,%s)",
                            (pid, 'discount_amount', json.dumps({'amount': amt})))
                else:
                    for c in (data.get('conditions') or []):
                        if not c.get('type'): continue
                        val = c.get('value')
                        cur.execute(
                            "INSERT INTO wim_promo_conditions (promo_id, condition_type, condition_value, and_or) "
                            "VALUES (%s,%s,%s,%s)",
                            (pid, c['type'], json.dumps(val) if not isinstance(val, str) else val,
                             (c.get('andOr') or 'or')))
                    for r in (data.get('rewards') or []):
                        if not r.get('type'): continue
                        val = r.get('value')
                        cur.execute(
                            "INSERT INTO wim_promo_rewards (promo_id, reward_type, reward_value, reward_sku_ref, reward_qty) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (pid, r['type'], json.dumps(val) if not isinstance(val, str) else val,
                             r.get('skuRef'), int(r.get('qty', 0))))
            # Multi-area applicability replace
            if has_region and ('regionIds' in data or 'allAreas' in data):
                cur.execute("DELETE FROM wim_promo_regions WHERE promo_id=%s", (pid,))
                region_ids_payload = None
                if bool(data.get('allAreas')):
                    cur.execute("SELECT id FROM wim_regions WHERE is_active IS NOT FALSE")
                    region_ids_payload = [rr['id'] for rr in cur.fetchall()]
                elif isinstance(data.get('regionIds'), list):
                    region_ids_payload = data['regionIds']
                if region_ids_payload:
                    for rid in region_ids_payload:
                        cur.execute(
                            "INSERT INTO wim_promo_regions (promo_id, region_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                            (pid, int(rid)))
            if has_reqs or (has_region and ('regionIds' in data or 'allAreas' in data)):
                conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'promos', f'Promo updated: {pid} by {user["email"]}')
            self._send_json(200, {'status': 'ok'})
        except Exception as e:
            write_log('ERROR', 'promos', f'ADMIN PATCH failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PROMOS_ADMIN_GET(self):
        """GET /api/admin/promos — full promo list incl. headers + conditions + rewards (admin)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ('super_admin', 'admin'):
            return self._send_json(403, {'error': 'Hanya super_admin/admin'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT p.id, p.promo_ref, p.nama, p.jenis, p.status, p.priority, p.stackable, "
                "p.periode_start, p.periode_end, p.min_transaction_amount, p.max_discount_amount, "
                "p.redeem_limit_per_order, p.redeem_limit_lifetime, "
                "u.used_count AS redeem_used, "
                "pc.condition_type, pc.condition_value, pc.and_or, "
                "pr.reward_type, pr.reward_value, pr.reward_sku_ref, pr.reward_qty, "
                "r.id AS region_id, r.name AS region_name "
                "FROM wim_promo p "
                "LEFT JOIN wim_promo_conditions pc ON p.id=pc.promo_id "
                "LEFT JOIN wim_promo_rewards pr ON p.id=pr.promo_id "
                "LEFT JOIN wim_promo_usage u ON p.id=u.promo_id "
                "LEFT JOIN wim_regions r ON p.region_id=r.id "
                "WHERE p.deleted_at IS NULL ORDER BY p.priority, p.id"
            )
            promos_dict = {}
            for r in cur.fetchall():
                pid = r['id']
                if pid not in promos_dict:
                    promos_dict[pid] = {
                        'id': pid, 'promoRef': r['promo_ref'], 'nama': r['nama'],
                        'jenis': r['jenis'], 'status': r['status'], 'priority': r['priority'],
                        'stackable': bool(r['stackable']),
                        'redeemLimitPerOrder': r.get('redeem_limit_per_order'),
                        'redeemLimitLifetime': r.get('redeem_limit_lifetime'),
                        'redeemUsed': int(r.get('redeem_used') or 0),
                        'periodeStart': str(r['periode_start']) if r['periode_start'] else None,
                        'periodeEnd': str(r['periode_end']) if r['periode_end'] else None,
                        'minTransaction': float(r['min_transaction_amount'] or 0),
                        'maxDiscount': float(r['max_discount_amount'] or 0),
                        'regionId': r.get('region_id'),
                        'regionName': r.get('region_name') or '',
                        'conditions': [], 'rewards': [],
                        '_cond_seen': set(), '_rew_seen': set(),
                    }
                if r['condition_type']:
                    cv = r['condition_value']
                    if isinstance(cv, str):
                        try: cv = json.loads(cv)
                        except: pass
                    # dedupe the cartesian LEFT JOIN (N conditions x M rewards) rows
                    sig = f"{r['condition_type']}|{cv}|{r['and_or']}"
                    if sig not in promos_dict[pid]['_cond_seen']:
                        promos_dict[pid]['_cond_seen'].add(sig)
                        promos_dict[pid]['conditions'].append({
                            'type': r['condition_type'], 'value': cv,
                            'andOr': (r['and_or'] or 'or'),
                        })
                if r['reward_type']:
                    rv = r['reward_value']
                    if isinstance(rv, str):
                        try: rv = json.loads(rv)
                        except: pass
                    rsig = f"{r['reward_type']}|{rv}|{r['reward_sku_ref']}|{r['reward_qty']}"
                    if rsig not in promos_dict[pid]['_rew_seen']:
                        promos_dict[pid]['_rew_seen'].add(rsig)
                        promos_dict[pid]['rewards'].append({
                            'type': r['reward_type'], 'value': rv,
                            'skuRef': r['reward_sku_ref'], 'qty': r['reward_qty'],
                        })
            # attach multi-area ids
            promo_ids = list(promos_dict.keys())
            if promo_ids:
                cur.execute(
                    "SELECT wr.promo_id, wr.region_id, r.name "
                    "FROM wim_promo_regions wr LEFT JOIN wim_regions r ON r.id=wr.region_id "
                    "WHERE wr.promo_id = ANY(%s)", (promo_ids,))
                for wr in cur.fetchall():
                    if wr['promo_id'] in promos_dict:
                        promos_dict[wr['promo_id']].setdefault('regionIds', []).append(wr['region_id'])
                for pdd in promos_dict.values():
                    pdd.setdefault('regionIds', [])
            cur.close(); ret_pg(conn)
            self._send_json(200, {'promos': list(promos_dict.values())})
        except Exception as e:
            write_log('ERROR', 'promos', f'ADMIN GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PROMOS_ADMIN_POST(self):
        """POST /api/admin/promos — create a promo (super_admin/admin).
        Body: {nama, jenis(bundling|strata|diskon|bonus), status, priority, stackable,
               periode_start, periode_end, conditions:[{type,value}], rewards:[{type,value,skuRef,qty}]}"""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ('super_admin', 'admin'):
            return self._send_json(403, {'error': 'Hanya super_admin/admin'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        nama = (data.get('nama') or '').strip()
        jenis = (data.get('jenis') or '').strip()
        if not nama or jenis not in ('bundling', 'strata', 'diskon', 'bonus'):
            return self._send_json(400, {'error': 'nama dan jenis (bundling/strata/diskon/bonus) diperlukan'})
        nama = nama.encode('ascii', 'replace').decode('ascii')
        region_id = data.get('regionId') or data.get('region_id') or None
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            promo_ref = data.get('promoRef') or f"PROMO-{time.strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
            # ensure unique
            cur.execute("SELECT 1 FROM wim_promo WHERE promo_ref=%s", (promo_ref,))
            while cur.fetchone():
                promo_ref = f"PROMO-{time.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
                cur.execute("SELECT 1 FROM wim_promo WHERE promo_ref=%s", (promo_ref,))
            cur.execute(
                "INSERT INTO wim_promo (promo_ref, nama, jenis, status, priority, stackable, region_id, "
                "periode_start, periode_end, min_transaction_amount, max_discount_amount, "
                "redeem_limit_per_order, redeem_limit_lifetime) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (promo_ref, nama, jenis,
                 (data.get('status') or 'active'),
                 int(data.get('priority', 0)),
                 bool(data.get('stackable', False)),
                 region_id,
                 data.get('periode_start') or None, data.get('periode_end') or None,
                 float(data.get('minTransaction', 0) or 0),
                 float(data.get('maxDiscount', 0) or 0),
                 data.get('redeemLimitPerOrder') if data.get('redeemLimitPerOrder') not in (None, '') else None,
                 data.get('redeemLimitLifetime') if data.get('redeemLimitLifetime') not in (None, '') else None)
            )
            promo_id = cur.fetchone()['id']
            # Multi-area applicability: write wim_promo_regions when regionIds provided
            region_ids_payload = data.get('regionIds')
            all_areas_payload = bool(data.get('allAreas'))
            if all_areas_payload:
                cur.execute("SELECT id FROM wim_regions WHERE is_active IS NOT FALSE")
                region_ids_payload = [rr['id'] for rr in cur.fetchall()]
            if isinstance(region_ids_payload, list) and region_ids_payload:
                for rid in region_ids_payload:
                    cur.execute(
                        "INSERT INTO wim_promo_regions (promo_id, region_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        (promo_id, int(rid)))
            # Structured builder payload (new): requirements[{sku,qty,andOr}] + reward{type,sku,qty|amount}
            reqs = data.get('requirements')
            if isinstance(reqs, list):
                for idx, rq in enumerate(reqs):
                    sku = (rq.get('sku') or '').strip() or None   # None = Any Product
                    qty = int(rq.get('qty') or 0)
                    and_or = (rq.get('andOr') or 'or') if idx > 0 else None
                    if qty > 0:
                        cur.execute(
                            "INSERT INTO wim_promo_conditions (promo_id, condition_type, condition_value, and_or) "
                            "VALUES (%s,'required_sku',%s,%s)",
                            (promo_id, json.dumps({'sku': sku, 'qty': qty}), and_or))
                rw = data.get('reward') or {}
                rtype = (rw.get('type') or '').strip()
                if rtype == 'free_sku':
                    cur.execute(
                        "INSERT INTO wim_promo_rewards (promo_id, reward_type, reward_sku_ref, reward_qty) "
                        "VALUES (%s,'free_sku',%s,%s)",
                        (promo_id, (rw.get('sku') or '').strip(), int(rw.get('qty') or 1)))
                elif rtype in ('discount_amount', 'flat_discount'):
                    amt = float(rw.get('amount', rw.get('value', 0)) or 0)
                    cur.execute(
                        "INSERT INTO wim_promo_rewards (promo_id, reward_type, reward_value) "
                        "VALUES (%s,%s,%s)",
                        (promo_id, 'discount_amount', json.dumps({'amount': amt})))
            else:
                for c in (data.get('conditions') or []):
                    if not c.get('type'): continue
                    val = c.get('value')
                    cur.execute(
                        "INSERT INTO wim_promo_conditions (promo_id, condition_type, condition_value, and_or) "
                        "VALUES (%s,%s,%s,%s)",
                        (promo_id, c['type'], json.dumps(val) if not isinstance(val, str) else val,
                         (c.get('andOr') or 'or')))
                for r in (data.get('rewards') or []):
                    if not r.get('type'): continue
                    val = r.get('value')
                    cur.execute(
                        "INSERT INTO wim_promo_rewards (promo_id, reward_type, reward_value, reward_sku_ref, reward_qty) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (promo_id, r['type'], json.dumps(val) if not isinstance(val, str) else val,
                         r.get('skuRef'), int(r.get('qty', 0))))
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'promos', f'Promo created: {promo_ref} ({jenis}) by {user["email"]}')
            self._send_json(201, {'status': 'ok', 'promoId': promo_id, 'promoRef': promo_ref})
        except Exception as e:
            write_log('ERROR', 'promos', f'ADMIN POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PROMOS_ADMIN_DELETE(self, params):
        """DELETE /api/admin/promos/:id — soft delete (deleted_at)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ('super_admin', 'admin'):
            return self._send_json(403, {'error': 'Hanya super_admin/admin'})
        pid = params.get('id')
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute("UPDATE wim_promo SET deleted_at=NOW(), status='inactive' WHERE id=%s AND deleted_at IS NULL", (pid,))
            conn.commit()
            ok = cur.rowcount > 0
            cur.close(); ret_pg(conn)
            if not ok:
                return self._send_json(404, {'error': 'Promo tidak ditemukan'})
            write_log('INFO', 'promos', f'Promo deleted: {pid} by {user["email"]}')
            self._send_json(200, {'status': 'ok'})
        except Exception as e:
            write_log('ERROR', 'promos', f'ADMIN DELETE failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Order Management (wim_orders - standalone PostgreSQL)
    # ═══════════════════════════════════════════════════

    def do_ORDER_CALC(self):
        """Server-side promo calculator."""
        user = self._require_auth()
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        items = data.get('items', [])
        if not items:
            return self._send_json(400, {'error': 'items diperlukan'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Resolve rep region so promos apply per-region
            rep_region = None
            try:
                cur.execute(
                    "SELECT d.region_id FROM wim_user_meta um "
                    "LEFT JOIN wim_depots d ON d.id=um.depot_id WHERE um.user_id=%s LIMIT 1",
                    (user.get('id'),))
                r0 = cur.fetchone()
                if r0: rep_region = r0.get('region_id')
            except Exception:
                rep_region = None
            promo_sql = (
                "SELECT p.id, p.promo_ref, p.nama, p.jenis, p.priority, p.stackable, "
                "p.region_id, p.redeem_limit_per_order, p.redeem_limit_lifetime, "
                "u.used_count AS redeem_used, "
                "pc.condition_type, pc.condition_value, pc.and_or, "
                "pr.reward_type, pr.reward_value, pr.reward_sku_ref, pr.reward_qty "
                "FROM wim_promo p "
                "LEFT JOIN wim_promo_conditions pc ON p.id=pc.promo_id "
                "LEFT JOIN wim_promo_rewards pr ON p.id=pr.promo_id "
                "LEFT JOIN wim_promo_usage u ON p.id=u.promo_id "
                "WHERE p.status='active' "
                "AND (p.periode_start IS NULL OR p.periode_start <= CURRENT_DATE) "
                "AND (p.periode_end IS NULL OR p.periode_end >= CURRENT_DATE) "
                "AND p.deleted_at IS NULL "
            )
            promo_params = ()
            if rep_region:
                promo_sql += ("AND ( EXISTS (SELECT 1 FROM wim_promo_regions wr "
                              "WHERE wr.promo_id=p.id AND wr.region_id=%s) "
                              "OR NOT EXISTS (SELECT 1 FROM wim_promo_regions wr2 WHERE wr2.promo_id=p.id) "
                              "OR p.region_id=%s ) ORDER BY p.priority, p.id")
                promo_params = (rep_region, rep_region)
            else:
                promo_sql += "ORDER BY p.priority, p.id"
            cur.execute(promo_sql, promo_params)
            promos_raw = {}
            for r in cur.fetchall():
                pid = r['id']
                if pid not in promos_raw:
                    promos_raw[pid] = {
                        'jenis': r['jenis'], 'priority': r['priority'],
                        'stackable': r['stackable'], 'promoRef': r['promo_ref'],
                        'nama': r['nama'], 'conditions': [], 'rewards': [],
                        'redeemLimitPerOrder': r.get('redeem_limit_per_order'),
                        'redeemLimitLifetime': r.get('redeem_limit_lifetime'),
                        'redeemUsed': int(r.get('redeem_used') or 0),
                        '_cond_seen': set(), '_rew_seen': set(),
                    }
                if r['condition_type']:
                    cv = r['condition_value']
                    if isinstance(cv, str) and cv.startswith('{'):
                        cv = json.loads(cv)
                    # Normalize legacy seed vocabulary -> engine vocabulary
                    ct = r['condition_type']
                    normalized_cv = cv
                    and_or = r.get('and_or') or 'or'
                    if ct in ('min_qty',):
                        # legacy bundling: no sku; engine needs purchase_sku + purchase_qty_min
                        ct = 'legacy_min_qty'
                        normalized_cv = {'qty': cv}
                    elif ct == 'purchase_qty_min' and isinstance(cv, str):
                        normalized_cv = {'qty': int(cv)}
                    elif ct == 'purchase_sku' and isinstance(cv, str):
                        normalized_cv = json.loads(cv)
                    # dedupe condition (cartesian join repeats rows)
                    sig = f"{ct}|{json.dumps(normalized_cv, sort_keys=True, default=str)}|{and_or}"
                    if sig not in promos_raw[pid]['_cond_seen']:
                        promos_raw[pid]['_cond_seen'].add(sig)
                        promos_raw[pid]['conditions'].append(
                            {'type': ct, 'value': normalized_cv, '_raw_type': r['condition_type'],
                             'and_or': and_or})
                if r['reward_type']:
                    rv = r['reward_value']
                    if isinstance(rv, str) and rv.startswith('{'):
                        rv = json.loads(rv)
                    rt = r['reward_type']
                    # legacy seed vocab: free_qty (bundling), percent_discount (strata), flat_discount (diskon)
                    if rt == 'free_qty' and not r['reward_sku_ref']:
                        # rewrite as free_sku on the same sku is unknown; keep legacy marker
                        rt = 'legacy_free_qty'
                    sig = f"{rt}|{json.dumps(rv, sort_keys=True, default=str)}|{r['reward_sku_ref']}|{r['reward_qty']}"
                    if sig not in promos_raw[pid]['_rew_seen']:
                        promos_raw[pid]['_rew_seen'].add(sig)
                        promos_raw[pid]['rewards'].append({
                            'type': rt, 'value': rv, 'skuRef': r['reward_sku_ref'],
                            'qty': r['reward_qty'], '_raw_type': r['reward_type'],
                        })
            cur.close(); ret_pg(conn)

            purchased = [i for i in items if not i.get('is_bonus')]
            bonus = [i for i in items if i.get('is_bonus')]
            applied_promos = []

            # ---- helpers -------------------------------------------------
            def _num(v, d=0.0):
                """Coerce a value (scalar or {'amount':..}/{'pct':..} dict) to float."""
                try:
                    if isinstance(v, dict):
                        return float((v.get('amount', v.get('pct', d))) or d)
                    return float(v if v is not None else d)
                except Exception:
                    return d

            def _sku_qty(sku):
                """Total purchased qty for a sku (bonus lines excluded)."""
                return sum(i['qty'] for i in purchased if i['sku'] == sku)

            def _required_skus(conds, legacy_sku_field=True):
                """Extract required-sku requirements.

                New format: rows of type 'required_sku' with value {"sku":X,"qty":N}
                and and_or in ('and','or'). sku may be None (= Any Product / total mode).
                Legacy format: purchase_sku + purchase_qty_min (single) pairs.

                Returns (reqs, legacy_total_mode, legacy_min_qty) where reqs is a
                list of {'sku':..., 'qty':..., 'and_or':...} dicts (ordered).
                """
                reqs = []
                for c in conds:
                    t, val = c['type'], c['value']
                    and_or = (c.get('and_or') or 'or')
                    if t == 'required_sku' and isinstance(val, dict):
                        try:
                            reqs.append({'sku': val.get('sku'), 'qty': int(val.get('qty', 0) or 0), 'and_or': and_or})
                        except Exception:
                            reqs.append({'sku': val.get('sku'), 'qty': 0, 'and_or': and_or})
                    elif legacy_sku_field and t == 'purchase_sku' and isinstance(val, dict) and val.get('sku'):
                        # legacy single threshold -> qty attached below / defaults 0
                        reqs.append({'sku': val['sku'], 'qty': None, 'and_or': and_or})
                return reqs, False, 0

            def _grant_bonus(promo, free_sku, mult):
                if not free_sku or mult <= 0:
                    return
                existing = next((b for b in bonus if b['sku'] == free_sku), None)
                if existing:
                    existing['qty'] += mult
                else:
                    sku_info = next((i for i in items if i['sku'] == free_sku), {})
                    bonus.append({
                        'sku': free_sku, 'name': sku_info.get('name', ''),
                        'qty': mult, 'is_bonus': True,
                        'promoName': promo['nama'], 'promoRef': promo['promoRef'],
                    })

            # ----------------------------------------------------------------
            # Stacking guard: a non-stackable promo ends the chain — subsequent
            # non-stackable promos are skipped (highest-priority one wins for that
            # product/reward). stackable:true promos always continue.
            _non_stackable_applied = False
            for pid, promo in sorted(promos_raw.items(), key=lambda x: x[1]['priority']):
                jen = promo['jenis']
                conds = promo['conditions']
                rewards = promo['rewards']

                if not promo.get('stackable', True) and _non_stackable_applied:
                    # A non-stackable promo already applied → enforce no stacking.
                    continue
                if not promo.get('stackable', True):
                    _non_stackable_applied = True

                # ============ BUNDLING / BONUS =============================
                # buy N of a SKU / any-product mix / AND-OR chain
                # -> grant M free of an EXPLICIT Bonus SKU per full threshold met.
                if jen in ('bundling', 'bonus'):
                    thresholds, legacy_total_mode, legacy_min_qty = _required_skus(conds)
                    # legacy fallback when no structured rows exist
                    if not [t for t in thresholds if t.get('qty', 0) > 0]:
                        legacy_sku = None
                        for c in conds:
                            t, val = c['type'], c['value']
                            if t == 'purchase_sku' and isinstance(val, dict):
                                legacy_sku = val.get('sku')
                            elif t == 'purchase_qty_min':
                                legacy_min_qty = int(val.get('qty', 0) if isinstance(val, dict) else (val or 0))
                            elif t == 'legacy_min_qty':
                                legacy_total_mode = True
                                legacy_min_qty = int(val.get('qty', 0) if isinstance(val, dict) else (val or 0))
                        if legacy_total_mode:
                            thresholds = [{'sku': None, 'qty': legacy_min_qty, 'and_or': 'or'}]
                        elif legacy_sku:
                            thresholds = [{'sku': legacy_sku, 'qty': legacy_min_qty, 'and_or': 'or'}]

                    def _thr_met(th):
                        """(met, base_multiplier) for one threshold.
                        sku None = Any-Product total mode; else a specific SKU."""
                        q = int(th.get('qty') or 0)
                        if q <= 0:
                            return False, 0
                        if th.get('sku') is None or legacy_total_mode:
                            tot = sum(i['qty'] for i in purchased)
                            return tot >= q, tot // q
                        qty = _sku_qty(th['sku'])
                        return qty >= q, qty // q

                    # left-to-right evaluation of the AND/OR operator chain.
                    # first row opens the chain (its and_or is ignored).
                    fires = False
                    mult = 0
                    for i, th in enumerate(thresholds):
                        met, m = _thr_met(th)
                        op = (th.get('and_or') or 'or')
                        if i == 0:
                            fires, mult = met, (m if met else 0)
                            continue
                        if op == 'and':
                            if not met:
                                fires, mult = False, 0
                            elif fires:
                                mult = min(mult, m)   # conservative: min over met AND
                            else:
                                fires, mult = False, 0
                        else:  # 'or' alternative
                            if met and not fires:
                                fires, mult = True, m
                            # if already fires, keep the dominant multiplier
                    if fires and mult > 0:
                        # ---- redeem caps (decision 2026-09-11): BOTH caps, min ---
                        per_order = promo.get('redeemLimitPerOrder')
                        if per_order not in (None, 0, ''):
                            mult = min(mult, int(per_order))
                        lifetime = promo.get('redeemLimitLifetime')
                        if lifetime not in (None, 0, ''):
                            remaining = int(lifetime) - int(promo.get('redeemUsed') or 0)
                            if remaining <= 0:
                                mult = 0
                            else:
                                mult = min(mult, remaining)
                        if mult > 0:
                            for r in rewards:
                                if r['type'] in ('free_sku', 'legacy_free_qty', 'bonus_qty', 'free_qty'):
                                    # decision 2026-09-11: MUST have an explicit Bonus SKU
                                    free_sku = r['skuRef'] or ''
                                    if isinstance(r['value'], dict) and not free_sku:
                                        free_sku = r['value'].get('sku', '')
                                    if not free_sku:
                                        continue   # explicit Bonus SKU required
                                    _grant_bonus(promo, free_sku, int(r['qty'] or 1) * mult)
                                    applied_promos.append({
                                        'promoRef': promo['promoRef'],
                                        'nama': promo['nama'],
                                        'jenis': jen,
                                        'grantQty': int(r['qty'] or 1) * mult,
                                    })

                # ============ STRATA =======================================
                # percent off when subtotal meets min_amount, or a category
                # qty tier is met.  (legacy strata % / discount_pct)
                elif jen == 'strata':
                    discount_pct = 0
                    subtotal_now = sum(i['qty'] * i.get('unitPrice', 0) for i in purchased)
                    tier_cond = next((c for c in conds if c['type'] == 'eligible_sku_category'), None)
                    if tier_cond is not None:
                        total_qty = sum(i['qty'] for i in purchased)
                        for r in sorted(rewards, key=lambda x: _num(x['value'].get('min_qty', 0)
                                                                    if isinstance(x['value'], dict) else 0),
                                        reverse=True):
                            rv = r['value']
                            if isinstance(rv, dict) and _num(rv.get('min_qty', 0)) <= total_qty:
                                discount_pct = _num(rv.get('pct', 0))
                                break
                    if discount_pct == 0:
                        min_amt = max((_num(c['value']) for c in conds if c['type'] == 'min_amount'),
                                      default=0.0)
                        if subtotal_now >= min_amt:
                            for r in rewards:
                                if r['type'] in ('percent_discount', 'discount_pct'):
                                    discount_pct = _num(r['value'])
                    if discount_pct > 0:
                        applied_promos.append({
                            'promoRef': promo['promoRef'],
                            'nama': promo['nama'],
                            'jenis': 'strata',
                            'discountPct': discount_pct,
                        })

                # ============ DISKON =======================================
                # multi-SKU combo: ALL required_sku rows must be satisfied ->
                # one flat IDR order-level discount, applied ONCE (never per-unit).
                elif jen == 'diskon':
                    reqs, _dtm, _dlq = _required_skus(conds)
                    # diskon = multi-SKU AND: all met -> flat discount once.
                    if reqs and all(th.get('qty') is not None for th in reqs):
                        if all(_sku_qty(th['sku']) >= th['qty'] for th in reqs):
                            amt = 0
                            for r in rewards:
                                if r['type'] in ('discount_amount', 'flat_discount')                                         or r['_raw_type'] in ('discount_amount', 'flat_discount'):
                                    amt = _num(r['value'])
                                    break
                            if amt > 0:
                                # flat order-level discount, tracked via flatOrder
                                applied_promos.append({
                                    'promoRef': promo['promoRef'],
                                    'nama': promo['nama'],
                                    'jenis': 'diskon',
                                    'amount': amt,
                                    'flatOrder': True,
                                })
                    else:
                        # legacy diskon: per-unit discount on the target sku's lines
                        for r in rewards:
                            if r['type'] in ('discount_amount', 'flat_discount')                                     or r['_raw_type'] in ('discount_amount', 'flat_discount'):
                                amt = _num(r['value'])
                                sku = reqs[0].get('sku') if reqs else None
                                targets = [i for i in purchased if not sku or i['sku'] == sku]
                                for i in targets:
                                    i['unitDiscount'] = (i.get('unitDiscount') or 0) + amt
                                if targets:
                                    applied_promos.append({
                                        'promoRef': promo['promoRef'],
                                        'nama': promo['nama'],
                                        'jenis': 'diskon',
                                        'amount': amt,
                                    })
                                break

            subtotal = sum(i['qty'] * (i.get('unitPrice', 0)) for i in purchased)
            total_discount = sum(i.get('unitDiscount', 0) * i['qty'] for i in purchased)
            flat_discount_total = 0  # flat order-level discounts (applied once, not per unit)
            strata_discount = 0
            for ap in applied_promos:
                if ap.get('jenis') == 'strata':
                    pct = ap.get('discountPct', 0)
                    strata_discount = subtotal * pct / 100
                if ap.get('jenis') == 'diskon' and ap.get('flatOrder'):
                    flat_discount_total += ap.get('amount', 0)
            total_discount += strata_discount + flat_discount_total
            grand_total = max(0, subtotal - total_discount)

            bonus_value = 0
            for b in bonus:
                sku_info = next((i for i in items if i['sku'] == b['sku']), None)
                if sku_info:
                    bonus_value += b['qty'] * sku_info.get('unitPrice', 0)

            self._send_json(200, {
                'purchased': [
                    {
                        'sku': i['sku'],
                        'name': i.get('name', ''),
                        'qty': i['qty'],
                        'unitPrice': i.get('unitPrice', 0),
                        'unitDiscount': i.get('unitDiscount', 0),
                        'lineTotal': i['qty'] * (i.get('unitPrice', 0) - i.get('unitDiscount', 0)),
                    }
                    for i in purchased
                ],
                'bonus': bonus,
                'subtotal': subtotal,
                'totalDiscount': total_discount,
                'strataDiscount': strata_discount,
                'grandTotal': grand_total,
                'bonusValue': bonus_value,
                'promosApplied': applied_promos,
            })
        except Exception as e:
            write_log('ERROR', 'ordercalc', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ORDER_POST(self):
        """Create order in wim_orders table."""
        user = self._require_auth()
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        items = data.get('items', [])
        checkin_id = data.get('checkinId', '')
        store_uuid = data.get('storeUuid', '')
        place_name = data.get('storeName', '')
        grand_total = data.get('grandTotal', 0)
        promos = data.get('promosApplied', [])
        sales_channel = data.get('salesChannel', 'app')
        payment_method = (data.get('paymentMethod') or 'cash').strip().lower()
        if payment_method not in ('cash', 'credit', 'cod'):
            payment_method = 'cash'
        off_route_reason = data.get('offRouteType') or data.get('off_route_reason') or None
        source = (data.get('source') or 'route').strip()
        if source not in ('route', 'luar_rute'):
            source = 'route'
        if not checkin_id or not items:
            return self._send_json(400, {'error': 'checkinId dan items diperlukan'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Verify open check-in
            cur.execute(
                "SELECT id, place_uuid FROM wim_visits WHERE id=%s AND user_id=%s AND checkout_at IS NULL",
                (checkin_id, user['id'])
            )
            checkin = cur.fetchone()
            if not checkin:
                cur.close(); ret_pg(conn)
                return self._send_json(400, {'error': 'Check-in tidak valid atau sudah selesai'})

            # Get driver UUID
    
            # Create order
            order_uuid = str(libuuid.uuid4())
            public_id = f"WIM-{time.strftime('%Y%m%d')}-{order_uuid[:8].upper()}"

            cur.execute(
                "INSERT INTO wim_orders "
                "(uuid, order_ref, user_id, visit_id, store_uuid, "
                "items, total, promos_applied, status, source, "
                "sales_channel, payment_method, off_route_reason, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, NOW(), NOW())",
                (
                    order_uuid, public_id, user['id'] or None,
                    checkin.get('id'),
                    store_uuid,
                    json.dumps(items), float(grand_total if grand_total else 0),
                    json.dumps(promos), source,
                    sales_channel, payment_method, off_route_reason,
                )
            )
            # Increment promo-lifetime usage (transactionally with the order insert)
            # for any applied bundling/bonus promo that carried grantQty.
            try:
                promos_list = promos if isinstance(promos, list) else []
                for ap in promos_list:
                    ref = (ap.get('promoRef') or ap.get('ref') or '').strip()
                    gq = int(ap.get('grantQty') or 0)
                    if not ref or gq <= 0:
                        continue
                    cur.execute(
                        "INSERT INTO wim_promo_usage (promo_id, used_count) "
                        "SELECT id, %s FROM wim_promo WHERE promo_ref=%s "
                        "ON CONFLICT (promo_id) DO UPDATE SET "
                        "used_count = wim_promo_usage.used_count + EXCLUDED.used_count, "
                        "updated_at = NOW()",
                        (gq, ref))
            except Exception as e:
                write_log('ERROR', 'orders', f'promo usage increment failed: {e}')
            conn.commit()
            cur.close(); ret_pg(conn)

            write_log('INFO', 'orders', f'Order created: {public_id} by {user["email"]} for store {place_name} (Rp {grand_total})')
            self._send_json(200, {
                'status': 'created',
                'orderId': public_id,
                'orderUuid': order_uuid,
                'grandTotal': grand_total,
                'verificationStatus': 'pending',
            })
        except Exception as e:
            write_log('ERROR', 'orders', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ORDER_GET(self):
        """Get order history from wim_orders."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        store_uuid = (qs.get('store_uuid') or [''])[0].strip()
        date_from = (qs.get('date_from') or [''])[0][:10]
        date_to = (qs.get('date_to') or [''])[0][:10]
        user_filter = (qs.get('user_id') or [None])[0]
        depot_filter = (qs.get('depot_id') or [''])[0].strip()
        region_filter = (qs.get('region_id') or [''])[0].strip()
        status_filter = (qs.get('status') or [''])[0].strip().lower()
        off_route = (qs.get('off_route') or [''])[0].strip().lower() in ('1','true','yes')
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = "WHERE o.deleted_at IS NULL"
            params = []
            # cookie (app) users see only their own orders; API-key requesters see all
            if not user.get('is_api'):
                where += " AND o.user_id=%s"
                params.append(user['id'])
            if store_uuid:
                where += " AND o.store_uuid=%s"
                params.append(store_uuid)
            if date_from:
                where += " AND DATE(o.created_at) >= %s"; params.append(date_from)
            if date_to:
                where += " AND DATE(o.created_at) <= %s"; params.append(date_to)
            if user.get('is_api'):
                if user_filter:
                    where += " AND o.user_id=%s"; params.append(user_filter)
                if depot_filter:
                    where += " AND um.depot_id=%s"; params.append(int(depot_filter))
                if region_filter:
                    where += " AND ud.region_id=%s"; params.append(int(region_filter))
                if status_filter:
                    where += " AND LOWER(o.status)=%s"; params.append(status_filter)
                if off_route:
                    where += " AND (o.off_route_reason IS NOT NULL AND o.off_route_reason <> '')"
            cur.execute(
                f"SELECT o.uuid, o.order_ref AS public_id, o.status, o.total AS grand_total, "
                f"o.items, o.verification_status, o.created_at, s.name AS store_name, u.name AS user_name, "
                f"o.payment_method, o.off_route_reason, o.source, o.promos_applied, "
                f"um.depot_id AS user_depot_id, ud.name AS user_depot_name, r.name AS region_name "
                f"FROM wim_orders o "
                f"LEFT JOIN wim_stores s ON o.store_uuid=s.uuid "
                f"LEFT JOIN wim_users u ON o.user_id=u.id "
                f"LEFT JOIN wim_user_meta um ON um.user_id=o.user_id "
                f"LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
                f"LEFT JOIN wim_regions r ON r.id=ud.region_id "
                f"{where} ORDER BY o.created_at DESC LIMIT 200",
                params
            )
            orders = []
            for r in cur.fetchall():
                items = r['items']
                if isinstance(items, str):
                    try: items = json.loads(items)
                    except: items = []
                bonus = [i for i in (items or []) if isinstance(i, dict) and i.get('is_bonus')]
                paid = [i for i in (items or []) if isinstance(i, dict) and not i.get('is_bonus')]
                pm = r['payment_method'] or 'cod'
                orders.append({
                    'uuid': r['uuid'],
                    'orderId': r['public_id'],
                    'status': r['status'],
                    'storeName': r['store_name'] or '',
                    'userName': r['user_name'] or '',
                    'userDepotName': r.get('user_depot_name') or '',
                    'regionName': r.get('region_name') or '',
                    'grandTotal': float(r['grand_total'] or 0),
                    'paymentMethod': pm,
                    'offRouteType': r.get('off_route_reason') or '',
                    'source': r.get('source') or 'route',
                    'itemCount': sum(i.get('qty') or 0 for i in paid),
                    'bonusQty': sum(i.get('qty') or 0 for i in bonus),
                    'promosApplied': [{'nama': x.get('nama','') if isinstance(x,dict) else str(x)} for x in (r.get('promos_applied') or [])],
                    'verificationStatus': r['verification_status'] or '',
                    'createdAt': str(r['created_at']) if r['created_at'] else '',
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'orders': orders})
        except Exception as e:
            write_log('ERROR', 'orders', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ORDER_DETAIL(self):
        """Get order detail from wim_orders."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        order_uuid = (qs.get('uuid') or [''])[0].strip()
        if not order_uuid:
            return self._send_json(400, {'error': 'uuid parameter required'})
        # Validate it is a plausible UUID before hitting PostgreSQL (avoid 500 on bad input)
        import re as _re
        if not _re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', order_uuid):
            return self._send_json(400, {'error': 'uuid tidak valid'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT o.uuid, o.order_ref AS public_id, o.status, o.items, o.total AS grand_total, "
                "o.verification_status, o.created_at, s.name AS store_name "
                "FROM wim_orders o LEFT JOIN wim_stores s ON o.store_uuid=s.uuid "
                "WHERE o.uuid=%s AND o.deleted_at IS NULL",
                (order_uuid,)
            )
            order = cur.fetchone()
            if not order:
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'Order not found'})
            items = order['items']
            if isinstance(items, str):
                try: items = json.loads(items)
                except: items = []
            cur.close(); ret_pg(conn)
            self._send_json(200, {
                'uuid': order['uuid'],
                'orderId': order['public_id'],
                'status': order['status'],
                'storeName': order['store_name'] or '',
                'grandTotal': float(order['grand_total'] or 0),
                'verificationStatus': order['verification_status'] or '',
                'createdAt': str(order['created_at']),
                'items': items if isinstance(items, list) else [],
            })
        except Exception as e:
            write_log('ERROR', 'orders', f'DETAIL failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ORDER_PUBLIC(self):
        """Public order confirmation (buyer-facing, NO auth).
        Returns order header + items + store/rep for the invoice page.
        This is an order CONFIRMATION (not a tax invoice) — unpaid by default."""
        import re as _re
        qs = parse_qs(urlparse(self.path).query)
        order_uuid = (qs.get('uuid') or [''])[0].strip()
        if not order_uuid:
            return self._send_json(400, {'error': 'uuid parameter required'})
        if not _re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', order_uuid):
            return self._send_json(400, {'error': 'uuid tidak valid'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT o.uuid, o.order_ref AS public_id, o.status, o.items, o.total AS grand_total, "
                "o.verification_status, o.created_at, o.sales_channel, o.payment_method, o.off_route_reason, o.source, "
                "s.name AS store_name, s.address AS store_address, u.name AS rep_name "
                "FROM wim_orders o "
                "LEFT JOIN wim_stores s ON o.store_uuid=s.uuid "
                "LEFT JOIN wim_users u ON o.user_id=u.id "
                "WHERE o.uuid=%s AND o.deleted_at IS NULL",
                (order_uuid,)
            )
            order = cur.fetchone()
            if not order:
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'Order not found'})
            items = order['items']
            if isinstance(items, str):
                try: items = json.loads(items)
                except: items = []
            # Normalise legacy vs new item shape (unit_price vs unitPrice; name may be missing)
            def _norm(it):
                if not isinstance(it, dict): return it
                out = dict(it)
                if 'unitPrice' not in out and 'unit_price' in out:
                    out['unitPrice'] = out['unit_price']
                return out
            items = [_norm(i) for i in items if isinstance(i, dict)]
            cur.close(); ret_pg(conn)
            # derive totals from items for the confirmation
            purchased = [i for i in items if not i.get('is_bonus')]
            bonus = [i for i in items if i.get('is_bonus')]
            subtotal = sum((i.get('qty') or 0) * (i.get('unitPrice') or 0) for i in purchased)
            total_discount = sum((i.get('unitDiscount') or 0) * (i.get('qty') or 0) for i in purchased)
            self._send_json(200, {
                'uuid': order['uuid'], 'orderId': order['public_id'],
                'status': 'CONFIRMED' if order['status'] in ('pending','verified') else order['status'],
                'paymentStatus': 'UNPAID',
                'paymentMethod': order.get('payment_method') or 'cod',
                'offRouteType': order.get('off_route_reason') or '',
                'source': order.get('source') or 'route',
                'verificationStatus': order['verification_status'] or '',
                'createdAt': str(order['created_at']),
                'storeName': order['store_name'] or '', 'storeAddress': order['store_address'] or '',
                'repName': order['rep_name'] or 'WIM Sales',
                'subtotal': float(subtotal), 'totalDiscount': float(total_discount),
                'grandTotal': float(order['grand_total'] or 0),
                'itemCount': sum(i.get('qty') or 0 for i in purchased),
                'items': items if isinstance(items, list) else [],
                'isConfirmation': True,  # order confirmation, not a tax invoice
            })
        except Exception as e:
            write_log('ERROR', 'orders', f'PUBLIC failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ORDER_VERIFY(self):
        """Verify order (QR scan)."""
        user = self._require_auth()
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        order_uuid = (data.get('orderUuid') or '').strip()
        if not order_uuid:
            return self._send_json(400, {'error': 'orderUuid diperlukan'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT uuid, order_ref, status FROM wim_orders WHERE uuid=%s AND deleted_at IS NULL",
                (order_uuid,)
            )
            order = cur.fetchone()
            if not order:
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'Order not found'})
            cur.execute(
                "UPDATE wim_orders SET status='verified', verification_status='verified', "
                "verified_at=NOW() WHERE uuid=%s",
                (order_uuid,)
            )
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'orders', f'Order verified: {order["order_ref"]} by {user["email"]}')
            self._send_json(200, {'status': 'verified', 'orderId': order['order_ref']})
        except Exception as e:
            write_log('ERROR', 'orders', f'VERIFY failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Sync Queue (stub for future Fleetbase/Odoo sync)
    # ═══════════════════════════════════════════════════

    def do_SYNC_QUEUE_POST(self):
        """Stub: accept sync requests and log them."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        entity_type = (data.get('entityType') or data.get('entity_type') or '').strip()
        entity_id = data.get('entityId') or data.get('entity_id')
        action = (data.get('action') or '').strip()
        target = (data.get('target') or '').strip()
        payload = data.get('payload', {})
        # wim_sync_queue.entity_id is INTEGER; coerce string->int safely
        try:
            entity_id = int(entity_id)
        except (TypeError, ValueError):
            entity_id = 0
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            if not entity_type or not entity_id or not action or not target:
                cur.close(); ret_pg(conn)
                return self._send_json(400, {'error': 'entityType, entityId, action, target diperlukan'})
            try:
                cur.execute(
                    "INSERT INTO wim_sync_queue (entity_type, entity_id, action, target, payload, status, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, 'pending', NOW()) RETURNING id",
                    (entity_type, entity_id, action, target, json.dumps(data.get('payload', {})))
                )
                row = cur.fetchone()
                queue_id = row[0] if row else None
            except Exception as ee:
                write_log('ERROR', 'sync_queue', f'POST failed: {ee}')
                cur.close(); ret_pg(conn)
                return self._send_json(500, {'error': str(ee)})
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'sync_queue', f'Sync queued: {entity_type}/{action} by {user["email"]}')
            self._send_json(200, {
                'status': 'queued',
                'queueId': queue_id,
                'message': f'Sync {entity_type}/{action} berhasil diantrikan',
            })
        except Exception as e:
            write_log('ERROR', 'sync_queue', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Users CRUD
    # ═══════════════════════════════════════════════════

    def do_USERS_GET(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        role = user.get('role', '')
        if role not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin yang bisa melihat daftar user'})
        qs = parse_qs(urlparse(self.path).query)
        filter_role = (qs.get('role') or [''])[0].strip()
        filter_jenis = (qs.get('jenis_sales') or [''])[0].strip()
        filter_status = (qs.get('status') or [''])[0].strip()
        depot_id = (qs.get('depot_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = "WHERE u.deleted_at IS NULL"
            params = []
            if filter_role:
                where += " AND u.role=%s"
                params.append(filter_role)
            if filter_jenis:
                where += " AND um.jenis_sales=%s"
                params.append(filter_jenis)
            if filter_status:
                where += " AND u.status=%s"
                params.append(filter_status)
            if depot_id:
                where += " AND um.depot_id=%s"
                params.append(int(depot_id))
            cur.execute(
                "SELECT u.id, u.uuid, u.email, u.name, u.role, u.phone, u.status, u.created_at, "
                "um.jenis_sales, um.depot_id, um.nik, um.npwp, um.npwp_name, um.kendaraan, "
                "um.kode_pos, um.kelurahan, um.kecamatan, d.name AS depot_name "
                "FROM wim_users u "
                "LEFT JOIN wim_user_meta um ON u.id=um.user_id "
                "LEFT JOIN wim_depots d ON d.id=um.depot_id "
                f"{where} ORDER BY u.name",
                params
            )
            rows = []
            for r in cur.fetchall():
                rows.append({
                    'id': r['id'],
                    'uuid': r['uuid'],
                    'email': r['email'],
                    'name': r['name'],
                    'role': r['role'] or 'sales',
                    'phone': r['phone'] or '',
                    'status': r['status'] or 'active',
                    'jenis_sales': r['jenis_sales'] or '',
                    'depot_id': r['depot_id'],
                    'depot_name': r['depot_name'] or '',
                    'nik': r['nik'] or '',
                    'npwp': r['npwp'] or '',
                    'npwp_name': r['npwp_name'] or '',
                    'kendaraan': r['kendaraan'] or '',
                    'kode_pos': r['kode_pos'] or '',
                    'kelurahan': r['kelurahan'] or '',
                    'kecamatan': r['kecamatan'] or '',
                    'created_at': str(r['created_at']) if r['created_at'] else None,
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'data': rows, 'total': len(rows), 'page': 1})
        except Exception as e:
            write_log('ERROR', 'users', f'GET list failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_USER_GET(self, params):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        target_id = params['id']
        role = user.get('role', '')
        if role not in ('admin', 'super_admin') and str(user['id']) != target_id:
            return self._send_json(403, {'error': 'Forbidden'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT u.id, u.uuid, u.email, u.name, u.role, u.phone, u.status, u.created_at, "
                "um.jenis_sales, um.depot_id, um.nik, um.npwp, um.vehicle_id, um.alamat "
                "FROM wim_users u "
                "LEFT JOIN wim_user_meta um ON u.id=um.user_id "
                "WHERE u.id=%s AND u.deleted_at IS NULL",
                (target_id,)
            )
            r = cur.fetchone()
            cur.close(); ret_pg(conn)
            if not r:
                return self._send_json(404, {'error': 'User not found'})
            self._send_json(200, {'data': {
                'id': r['id'], 'uuid': r['uuid'], 'email': r['email'],
                'name': r['name'], 'role': r['role'] or 'sales',
                'phone': r['phone'] or '', 'status': r['status'] or 'active',
                'jenis_sales': r['jenis_sales'] or '', 'depot_id': r['depot_id'],
                'nik': r['nik'] or '', 'npwp': r['npwp'] or '',
                'npwp_name': r.get('npwp_name') or '', 'kendaraan': r.get('kendaraan') or '',
                'kode_pos': r.get('kode_pos') or '', 'kelurahan': r.get('kelurahan') or '',
                'kecamatan': r.get('kecamatan') or '',
                'created_at': str(r['created_at']) if r['created_at'] else None,
            }})
        except Exception as e:
            write_log('ERROR', 'users', f'GET user failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_USERS_POST(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') != 'super_admin':
            return self._send_json(403, {'error': 'Hanya super_admin yang bisa membuat user'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        email = (data.get('email') or '').strip().lower()
        name = data.get('name', '').strip()
        password = data.get('password', '')
        role = data.get('role', 'sales').strip()
        phone = data.get('phone', '')
        jenis_sales = data.get('jenis_sales', '')
        depot_id = data.get('depot_id')
        if not email or not password:
            return self._send_json(400, {'error': 'email dan password diperlukan'})
        try:
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        except Exception as e:
            return self._send_json(500, {'error': f'Hash failed: {e}'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT id FROM wim_users WHERE email=%s AND deleted_at IS NULL", (email,))
            if cur.fetchone():
                cur.close(); ret_pg(conn)
                return self._send_json(409, {'error': 'Email sudah terdaftar'})
            cur.execute(
                "INSERT INTO wim_users (uuid, email, name, password_hash, role, phone, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'active', NOW()) RETURNING id, uuid",
                (str(secrets.token_hex(16)), email, name, pw_hash, role, phone)
            )
            row = cur.fetchone()
            new_id = row['id']
            new_uuid = row['uuid']
            # Optional wim_user_meta (defensive)
            if jenis_sales or depot_id:
                try:
                    cur.execute(
                        "INSERT INTO wim_user_meta (user_id, jenis_sales, depot_id) "
                        "VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET "
                        "jenis_sales=EXCLUDED.jenis_sales, depot_id=EXCLUDED.depot_id",
                        (new_id, jenis_sales, depot_id)
                    )
                except Exception as meta_err:
                    write_log('WARN', 'users', f'wim_user_meta insert failed (table may not exist): {meta_err}')
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'users', f'User created: {email} ({role})')
            self._send_json(201, {'data': {'id': new_id, 'uuid': new_uuid, 'email': email, 'name': name, 'role': role}})
        except Exception as e:
            write_log('ERROR', 'users', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_USER_PATCH(self, params):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        target_id = params['id']
        role = user.get('role', '')
        is_self = str(user['id']) == target_id
        if not is_self and role not in ('admin', 'super_admin'):
            return self._send_json(403, {'error': 'Forbidden'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            set_clauses = []
            params_list = []
            for field in ('name', 'phone', 'status'):
                if field in data:
                    set_clauses.append(f"{field}=%s")
                    params_list.append(data[field])
            if 'role' in data and role == 'super_admin':
                set_clauses.append("role=%s")
                params_list.append(data['role'])
            if set_clauses:
                set_clauses.append("updated_at=NOW()")
                params_list.append(target_id)
                cur.execute(
                    f"UPDATE wim_users SET {', '.join(set_clauses)} WHERE id=%s AND deleted_at IS NULL",
                    params_list
                )
            # Optional wim_user_meta update (defensive)
            meta_fields = {}
            for f in ('jenis_sales', 'nik', 'npwp', 'npwp_name', 'kendaraan', 'kode_pos', 'kelurahan', 'kecamatan'):
                if f in data:
                    meta_fields[f] = data[f]
            if 'depot_id' in data:
                meta_fields['depot_id'] = data['depot_id']
            if meta_fields:
                try:
                    cols = ', '.join(meta_fields.keys())
                    vals = ', '.join(f"%s" for _ in meta_fields)
                    updates = ', '.join(f"{k}=EXCLUDED.{k}" for k in meta_fields)
                    cur.execute(
                        f"INSERT INTO wim_user_meta (user_id, {cols}) "
                        f"VALUES (%s, {vals}) ON CONFLICT (user_id) DO UPDATE SET {updates}",
                        [target_id] + list(meta_fields.values())
                    )
                except Exception as meta_err:
                    write_log('WARN', 'users', f'wim_user_meta patch failed (table may not exist): {meta_err}')
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'users', f'User updated: id={target_id}')
            self._send_json(200, {'status': 'ok', 'message': 'User diperbarui'})
        except Exception as e:
            write_log('ERROR', 'users', f'PATCH failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_USER_DELETE(self, params):
        """DELETE /api/users/:id — soft-delete a user (set deleted_at). Admin/super_admin only."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ('admin', 'super_admin'):
            return self._send_json(403, {'error': 'Hanya admin'})
        target_id = params['id']
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute(
                "UPDATE wim_users SET deleted_at=NOW(), status='inactive', updated_at=NOW() "
                "WHERE id=%s AND deleted_at IS NULL",
                (target_id,))
            conn.commit()
            ok = cur.rowcount > 0
            cur.close(); ret_pg(conn)
            if not ok:
                return self._send_json(404, {'error': 'User tidak ditemukan'})
            write_log('INFO', 'users', f'User deleted: id={target_id} by {user["email"]}')
            self._send_json(200, {'status': 'ok', 'message': 'User dihapus'})
        except Exception as e:
            write_log('ERROR', 'users', f'DELETE failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Password reset / change (admin-initiated, rep-completes; no SMTP)
    # ═══════════════════════════════════════════════════
    def _revoke_user_sessions(self, cur, user_id):
        """Revoke all of a user's sessions: purge the in-memory SESSIONS cache AND the DB rows."""
        global SESSIONS
        with SESSION_LOCK:
            stale = [k for k, v in list(SESSIONS.items()) if v.get('id') == user_id or v.get('user_id') == user_id]
            for k in stale:
                SESSIONS.pop(k, None)
        cur.execute("DELETE FROM wim_sessions WHERE user_id=%s", (user_id,))

    def _issue_reset_token(self, cur, user_id, admin_id):
        """Create a one-time reset token (SHA-256 stored; plaintext returned once)."""
        token = secrets.token_urlsafe(32)
        import hashlib
        th = hashlib.sha256(token.encode()).hexdigest()
        cur.execute(
            "INSERT INTO wim_password_resets (user_id, token_hash, created_by, expires_at) "
            "VALUES (%s,%s,%s, NOW() + interval '24 hours') ",
            (user_id, th, admin_id))
        return token

    def do_PASSWORD_RESET_ISSUE(self, params):
        """POST /api/admin/users/:id/password/reset — admin issues a reset link.
        Returns {link} built from the one-time token (delivered by admin via WhatsApp)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ('super_admin', 'admin', 'depo_admin'):
            return self._send_json(403, {'error': 'Hanya admin'})
        target_id = params['id']
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute("SELECT id FROM wim_users WHERE id=%s AND deleted_at IS NULL", (target_id,))
            if not cur.fetchone():
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'User tidak ditemukan'})
            token = self._issue_reset_token(cur, target_id, user['id'])
            conn.commit(); cur.close(); ret_pg(conn)
            base = getattr(self, 'public_base', '')
            link = f"/reset-password.html?token={token}"
            write_log('INFO', 'password', f'Reset token issued for user {target_id} by {user["email"]}')
            self._send_json(200, {'status':'ok', 'link': link, 'expiresInHours': 24})
        except Exception as e:
            write_log('ERROR', 'password', f'RESET ISSUE failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PASSWORD_SET(self, params):
        """POST /api/admin/users/:id/password/set — admin sets a temp password directly."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ('super_admin', 'admin', 'depo_admin'):
            return self._send_json(403, {'error': 'Hanya admin'})
        target_id = params['id']
        try:
            body = self._read_body(); data = json.loads(body) if body else {}
        except Exception:
            return self._send_json(400, {'error': 'Invalid JSON'})
        new_pass = (data.get('new_password') or '')
        if len(new_pass) < 6:
            return self._send_json(400, {'error': 'Password minimal 6 karakter'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute("SELECT id FROM wim_users WHERE id=%s AND deleted_at IS NULL", (target_id,))
            if not cur.fetchone():
                cur.close(); ret_pg(conn); return self._send_json(404, {'error': 'User tidak ditemukan'})
            pw_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
            cur.execute("UPDATE wim_users SET password_hash=%s, password_changed_at=NOW() WHERE id=%s",
                        (pw_hash, target_id))
            self._revoke_user_sessions(cur, target_id)
            conn.commit(); cur.close(); ret_pg(conn)
            write_log('INFO', 'password', f'Password set for user {target_id} by {user["email"]}')
            self._send_json(200, {'status':'ok', 'message':'Password diperbarui'})
        except Exception as e:
            write_log('ERROR', 'password', f'SET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_RESET_PASSWORD(self):
        """POST /api/reset-password — rep completes: {token, new_password}."""
        try:
            body = self._read_body(); data = json.loads(body) if body else {}
        except Exception:
            return self._send_json(400, {'error': 'Invalid JSON'})
        token = (data.get('token') or '').strip()
        new_pass = (data.get('new_password') or '')
        if len(new_pass) < 6:
            return self._send_json(400, {'error': 'Password minimal 6 karakter'})
        if not token:
            return self._send_json(400, {'error': 'token diperlukan'})
        import hashlib
        th = hashlib.sha256(token.encode()).hexdigest()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM wim_password_resets WHERE token_hash=%s AND used_at IS NULL AND expires_at > NOW()", (th,))
            row = cur.fetchone()
            if not row:
                cur.close(); ret_pg(conn)
                return self._send_json(400, {'error': 'Link tidak valid, sudah dipakai, atau kadaluarsa'})
            uid = row[0]
            pw_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
            cur.execute("UPDATE wim_users SET password_hash=%s, password_changed_at=NOW() WHERE id=%s", (pw_hash, uid))
            cur.execute("UPDATE wim_password_resets SET used_at=NOW() WHERE token_hash=%s", (th,))
            self._revoke_user_sessions(cur, uid)
            conn.commit(); cur.close(); ret_pg(conn)
            write_log('INFO', 'password', f'Password reset completed for user {uid} via token')
            self._send_json(200, {'status':'ok', 'message':'Password berhasil diubah. Silakan login.'})
        except Exception as e:
            write_log('ERROR', 'password', f'RESET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_PASSWORD_CHANGE(self):
        """POST /api/password/change — authenticated user changes own password {old_password,new_password}."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            body = self._read_body(); data = json.loads(body) if body else {}
        except Exception:
            return self._send_json(400, {'error': 'Invalid JSON'})
        old_pw = data.get('old_password') or ''
        new_pw = data.get('new_password') or ''
        if len(new_pw) < 6:
            return self._send_json(400, {'error': 'Password minimal 6 karakter'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute("SELECT password_hash FROM wim_users WHERE id=%s AND deleted_at IS NULL", (user['id'],))
            row = cur.fetchone()
            if not row or not row[0] or not bcrypt.checkpw(old_pw.encode(), row[0].encode()):
                cur.close(); ret_pg(conn)
                return self._send_json(403, {'error': 'Password lama salah'})
            pw_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
            cur.execute("UPDATE wim_users SET password_hash=%s, password_changed_at=NOW() WHERE id=%s", (pw_hash, user['id']))
            conn.commit(); cur.close(); ret_pg(conn)
            write_log('INFO', 'password', f'User {user["email"]} changed own password')
            self._send_json(200, {'status':'ok', 'message':'Password diubah'})
        except Exception as e:
            write_log('ERROR', 'password', f'CHANGE failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # User Meta
    # ═══════════════════════════════════════════════════

    def do_USER_META_GET(self, params):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        target_id = params['id']
        role = user.get('role', '')
        if role not in ('admin', 'super_admin') and str(user['id']) != target_id:
            return self._send_json(403, {'error': 'Forbidden'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute(
                    "SELECT jenis_sales, depot_id, nik, npwp "
                    "kode_pos, kelurahan, kecamatan FROM wim_user_meta WHERE user_id=%s",
                    (target_id,)
                )
                row = cur.fetchone()
            except Exception:
                row = None
            cur.close(); ret_pg(conn)
            if row:
                self._send_json(200, {'data': {
                    'jenis_sales': row['jenis_sales'] or '',
                    'depot_id': row['depot_id'],
                    'nik': row['nik'] or '',
                    'npwp': row['npwp'] or '',
                    'npwp_name': row['npwp_name'] or '',
                    'kendaraan': row.get('kendaraan') or '',
                    'kode_pos': row['kode_pos'] or '',
                    'kelurahan': row['kelurahan'] or '',
                    'kecamatan': row['kecamatan'] or '',
                }})
            else:
                self._send_json(200, {'data': {}})
        except Exception as e:
            write_log('ERROR', 'users', f'META GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_USER_META_PATCH(self, params):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        target_id = params['id']
        role = user.get('role', '')
        if role not in ('admin', 'super_admin') and str(user['id']) != target_id:
            return self._send_json(403, {'error': 'Forbidden'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        valid_fields = ('jenis_sales', 'depot_id', 'nik', 'npwp')
        meta_fields = {k: data[k] for k in data if k in valid_fields}
        if not meta_fields:
            return self._send_json(400, {'error': 'Tidak ada field yang valid untuk diupdate'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            try:
                cols = ', '.join(meta_fields.keys())
                vals = ', '.join(f"%s" for _ in meta_fields)
                updates = ', '.join(f"{k}=EXCLUDED.{k}" for k in meta_fields)
                cur.execute(
                    f"INSERT INTO wim_user_meta (user_id, {cols}) "
                    f"VALUES (%s, {vals}) ON CONFLICT (user_id) DO UPDATE SET {updates}",
                    [target_id] + list(meta_fields.values())
                )
            except Exception as meta_err:
                write_log('WARN', 'users', f'wim_user_meta table may not exist: {meta_err}')
                cur.close(); ret_pg(conn)
                return self._send_json(500, {'error': 'Tabel meta tidak tersedia'})
            conn.commit()
            cur.close(); ret_pg(conn)
            self._send_json(200, {'status': 'ok', 'message': 'Meta diperbarui'})
        except Exception as e:
            write_log('ERROR', 'users', f'META PATCH failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Store / NOO Creation + Detail + Contacts
    # ═══════════════════════════════════════════════════

    def do_STORE_POST(self):
        """POST /api/stores — NOO creation (atomic with contacts + photo + visit_plan)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        name = (data.get('name') or '').strip()
        owner_name = (data.get('owner_name') or '').strip()
        phone = (data.get('phone') or '').strip()
        address = (data.get('address') or '').strip()
        city = (data.get('city') or '').strip()
        province = (data.get('province') or '').strip()
        kecamatan = (data.get('kecamatan') or '').strip()
        kelurahan = (data.get('kelurahan') or '').strip()
        province_id = (data.get('province_id') or data.get('provinsiKode') or '').strip()
        city_id = (data.get('city_id') or data.get('kotaKode') or '').strip()
        kecamatan_id = (data.get('kecamatan_id') or data.get('kecamatanKode') or '').strip()
        kelurahan_id = (data.get('kelurahan_id') or data.get('kelurahanKode') or '').strip()
        kode_pos = (data.get('kode_pos') or '').strip()
        lat = data.get('latitude')
        lng = data.get('longitude')
        # Tolerate nested location:{latitude,longitude} (some clients send object) + top-level
        loc = data.get('location') if isinstance(data.get('location'), dict) else {}
        if lat is None and loc.get('latitude') is not None: lat = loc.get('latitude')
        if lng is None and loc.get('longitude') is not None: lng = loc.get('longitude')
        channel = (data.get('channel') or 'GT').strip()
        category = (data.get('category') or '').strip()
        kendaraan = (data.get('kendaraan') or '').strip()
        nik = (data.get('nik') or '').strip()
        npwp = (data.get('npwp') or '').strip()
        npwp_name = (data.get('npwp_name') or '').strip()
        contacts = data.get('contacts', [])
        photo = data.get('photo', '')
        source = (data.get('source') or 'luar_rute').strip()
        if not name:
            return self._send_json(400, {'error': 'Nama toko diperlukan'})
        store_uuid = str(libuuid.uuid4())
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Insert wim_stores
            cur.execute(
                "INSERT INTO wim_stores (uuid, name, address, city, province, kecamatan, kelurahan, "
                "province_id, city_id, kecamatan_id, kelurahan_id, "
                "kode_pos, latitude, longitude, owner_name, phone, channel, category, kendaraan, "
                "nik, npwp, npwp_name, geofence_radius_m, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, 'active', NOW()) RETURNING id",
                (store_uuid, name, address, city, province, kecamatan, kelurahan,
                 province_id, city_id, kecamatan_id, kelurahan_id,
                 kode_pos, lat, lng, owner_name, phone, channel, category, kendaraan, nik, npwp, npwp_name,
                 data.get('geofence_radius_m') if data.get('geofence_radius_m') not in (None, '') else None)
            )
            store_row = cur.fetchone()
            store_id = store_row['id']
            # Insert wim_store_contacts (defensive)
            for c in contacts:
                try:
                    cur.execute(
                        "INSERT INTO wim_store_contacts (store_id, name, phone, role, is_primary) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (store_id, c.get('name', ''), c.get('phone', ''),
                         c.get('role', 'owner'), bool(c.get('is_primary', False)))
                    )
                except Exception as ce:
                    write_log('WARN', 'stores', f'Contacts insert failed (table may not exist): {ce}')
            # Insert wim_store_photos (defensive)
            if photo:
                try:
                    cur.execute(
                        "INSERT INTO wim_store_photos (store_id, photo_data, description, photo_type) "
                        "VALUES (%s, %s, 'NOO photo', 'store_front')",
                        (store_id, photo)
                    )
                except Exception as pe:
                    write_log('WARN', 'stores', f'Photo insert failed (table may not exist): {pe}')
            # Add to wim_visit_plan
            cur.execute(
                "INSERT INTO wim_visit_plan (user_id, place_uuid, visit_date, source, status) "
                "VALUES (%s, %s, CURRENT_DATE, %s, 'pending') ON CONFLICT DO NOTHING",
                (user['id'], store_uuid, source)
            )
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'stores', f'NOO created: {name} ({store_uuid}) by {user["email"]}')
            self._send_json(201, {
                'uuid': store_uuid,
                'id': store_id,
                'place_uuid': store_uuid,
            })
        except Exception as e:
            write_log('ERROR', 'stores', f'NOO POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_STORE_BY_UUID(self, params):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        uuid_val = params['uuid']
        # Validate plausible UUID before PostgreSQL (avoid 500 on bad path input)
        import re as _re
        if not _re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', uuid_val):
            return self._send_json(400, {'error': 'uuid tidak valid'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, uuid, name, address, city, province, kecamatan, kelurahan, province_id, city_id, kecamatan_id, kelurahan_id, kode_pos, "
                "latitude, longitude, owner_name, phone, channel, category, kendaraan, nik, npwp, "
                "npwp_name, status, geofence_radius_m, created_at "
                "FROM wim_stores WHERE uuid=%s AND (status IS NULL OR status != 'closed')",
                (uuid_val,)
            )
            r = cur.fetchone()
            cur.close(); ret_pg(conn)
            if not r:
                return self._send_json(404, {'error': 'Store not found'})
            self._send_json(200, {'data': {
                'id': r['id'], 'uuid': r['uuid'], 'name': r['name'] or '',
                'address': r['address'] or '', 'city': r['city'] or '',
                'province': r['province'] or '', 'kecamatan': r['kecamatan'] or '',
                'kelurahan': r['kelurahan'] or '', 'kode_pos': r['kode_pos'] or '',
                'latitude': float(r['latitude']) if r['latitude'] else None,
                'longitude': float(r['longitude']) if r['longitude'] else None,
                'owner_name': r['owner_name'] or '', 'phone': r['phone'] or '',
                'channel': r['channel'] or '', 'category': r['category'] or '',
                'kendaraan': r.get('kendaraan') or '', 'nik': r['nik'] or '',
                'npwp': r['npwp'] or '', 'npwp_name': r['npwp_name'] or '',
                'status': r['status'] or 'active',
                'geofence_radius_m': r['geofence_radius_m'],
                'created_at': str(r['created_at']) if r['created_at'] else None,
            }})
        except Exception as e:
            write_log('ERROR', 'stores', f'GET by UUID failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_STORE_PATCH(self, params):
        """PATCH /api/stores/:uuid — update store fields (admin)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ('super_admin', 'admin'):
            return self._send_json(403, {'error': 'Hanya admin'})
        uuid_val = params['uuid']
        import re as _re
        if not _re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', uuid_val):
            return self._send_json(400, {'error': 'uuid tidak valid'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        mapping = {
            'name':'name','address':'address','city':'city','province':'province',
            'kecamatan':'kecamatan','kelurahan':'kelurahan','kode_pos':'kode_pos',
            'owner_name':'owner_name','phone':'phone','channel':'channel','category':'category',
            'kendaraan':'kendaraan','nik':'nik','npwp':'npwp','npwp_name':'npwp_name','status':'status',
            'assigned_salesperson_id':'assigned_salesperson_id','credit_limit':'credit_limit',
            'geofence_radius_m':'geofence_radius_m',
        }
        set_clauses = []; params_list = []
        for key, col in mapping.items():
            if key not in data:
                continue
            # geofence_radius_m: allow explicit clear to NULL (use app default)
            if key == 'geofence_radius_m':
                v = data[key]
                val = int(v) if v not in (None, '', 'null') else None
                set_clauses.append(f"{col}=%s"); params_list.append(val)
                continue
            if data[key] is not None:
                set_clauses.append(f"{col}=%s")
                params_list.append(data[key])
        if 'latitude' in data and data['latitude'] is not None:
            set_clauses.append("latitude=%s"); params_list.append(data['latitude'])
        if 'longitude' in data and data['longitude'] is not None:
            set_clauses.append("longitude=%s"); params_list.append(data['longitude'])
        if not set_clauses:
            return self._send_json(400, {'error': 'Belum ada field untuk diperbarui'})
        params_list.append(uuid_val)
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute(
                f"UPDATE wim_stores SET {', '.join(set_clauses)} WHERE uuid=%s AND deleted_at IS NULL",
                params_list
            )
            conn.commit()
            ok = cur.rowcount > 0
            cur.close(); ret_pg(conn)
            if not ok:
                return self._send_json(404, {'error': 'Store not found'})
            write_log('INFO', 'stores', f'Store updated: {uuid_val} by {user["email"]}')
            self._send_json(200, {'status': 'ok', 'message': 'Toko diperbarui'})
        except Exception as e:
            write_log('ERROR', 'stores', f'PATCH failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_STORE_DELETE(self, params):
        """DELETE /api/stores/:uuid — soft delete (deleted_at). Admin only."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ('super_admin', 'admin'):
            return self._send_json(403, {'error': 'Hanya admin'})
        uuid_val = params['uuid']
        import re as _re
        if not _re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', uuid_val):
            return self._send_json(400, {'error': 'uuid tidak valid'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            cur.execute(
                "UPDATE wim_stores SET deleted_at=NOW(), status='closed' WHERE uuid=%s AND deleted_at IS NULL",
                (uuid_val,)
            )
            conn.commit()
            ok = cur.rowcount > 0
            cur.close(); ret_pg(conn)
            if not ok:
                return self._send_json(404, {'error': 'Store not found'})
            write_log('INFO', 'stores', f'Store deleted (soft): {uuid_val} by {user["email"]}')
            self._send_json(200, {'status': 'ok', 'message': 'Toko hapus'})
        except Exception as e:
            write_log('ERROR', 'stores', f'DELETE failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_STORE_CONTACTS_GET(self, params):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        uuid_val = params['uuid']
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT st.id as store_id FROM wim_stores st WHERE st.uuid=%s", (uuid_val,)
            )
            store = cur.fetchone()
            if not store:
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'Store not found'})
            try:
                cur.execute(
                    "SELECT id, name, phone, role, is_primary FROM wim_store_contacts "
                    "WHERE store_id=%s ORDER BY is_primary DESC, name",
                    (store['store_id'],)
                )
                contacts = [{
                    'id': r['id'], 'name': r['name'] or '', 'phone': r['phone'] or '',
                    'role': r['role'] or '', 'is_primary': bool(r['is_primary']),
                } for r in cur.fetchall()]
            except Exception:
                contacts = []
            cur.close(); ret_pg(conn)
            self._send_json(200, {'data': contacts})
        except Exception as e:
            write_log('ERROR', 'stores', f'Contacts GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_STORE_CONTACTS_POST(self, params):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        uuid_val = params['uuid']
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        name = (data.get('name') or '').strip()
        phone = (data.get('phone') or '').strip()
        role = (data.get('role') or 'contact').strip()
        is_primary = bool(data.get('is_primary', False))
        if not name:
            return self._send_json(400, {'error': 'Nama kontak diperlukan'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT id FROM wim_stores WHERE uuid=%s", (uuid_val,))
            store = cur.fetchone()
            if not store:
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'Store not found'})
            try:
                cur.execute(
                    "INSERT INTO wim_store_contacts (store_id, name, phone, role, is_primary) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (store['id'], name, phone, role, is_primary)
                )
                contact_row = cur.fetchone()
                conn.commit()
                contact_id = contact_row['id']
            except Exception as ce:
                write_log('WARN', 'stores', f'Contacts table may not exist: {ce}')
                cur.close(); ret_pg(conn)
                return self._send_json(500, {'error': 'Tabel kontak tidak tersedia'})
            cur.close(); ret_pg(conn)
            self._send_json(201, {'data': {'id': contact_id, 'name': name, 'phone': phone, 'role': role, 'is_primary': is_primary}})
        except Exception as e:
            write_log('ERROR', 'stores', f'Contacts POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Order Status
    # ═══════════════════════════════════════════════════

    def do_ORDER_STATUS_POST(self):
        """POST /api/orders/status — update order status + insert wim_order_status_log."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        role = user.get('role', '')
        if role not in ADMIN_ROLES and role != 'warehouse':
            return self._send_json(403, {'error': 'Hanya admin/warehouse yang bisa ubah status order'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        order_uuid = (data.get('order_uuid') or '').strip()
        to_status = (data.get('status') or '').strip()
        notes = (data.get('notes') or '').strip()
        if not order_uuid or not to_status:
            return self._send_json(400, {'error': 'order_uuid dan status diperlukan'})
        valid_statuses = ('pending', 'verified', 'processed', 'shipped', 'delivered', 'cancelled')
        if to_status not in valid_statuses:
            return self._send_json(400, {'error': f'Status tidak valid. Pilihan: {", ".join(valid_statuses)}'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, order_ref AS public_id, status FROM wim_orders WHERE uuid=%s AND deleted_at IS NULL",
                (order_uuid,)
            )
            order = cur.fetchone()
            if not order:
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'Order not found'})
            from_status = order['status']
            cur.execute(
                "UPDATE wim_orders SET status=%s, updated_at=NOW() WHERE uuid=%s",
                (to_status, order_uuid)
            )
            # Insert status log (defensive)
            try:
                cur.execute(
                    "INSERT INTO wim_order_status_log (order_id, from_status, to_status, changed_by, notes) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (order['id'], from_status, to_status, user['email'], notes)
                )
            except Exception as sle:
                write_log('WARN', 'orders', f'Status log insert failed (table may not exist): {sle}')
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'orders', f'Status changed: {order["public_id"]} {from_status}->{to_status} by {user["email"]}')
            self._send_json(200, {
                'status': 'ok',
                'order_id': order['public_id'],
                'from_status': from_status,
                'to_status': to_status,
            })
        except Exception as e:
            write_log('ERROR', 'orders', f'STATUS POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ORDER_ADMIN_EDIT(self):
        """POST /api/orders/admin-edit — adjust ordered qty / unit price of NON-BONUS line items.

        Body: {order_uuid, items:[{qty, unitPrice, sku?, name?}]}.
        - Only admin roles or API-key callers may edit.
        - Incoming items are matched to existing non-bonus lines by sku (fallback: position).
        - Bonus (is_bonus) line items are never touched.
        - order total is recomputed as sum(qty*unitPrice) over non-bonus lines and written back.
        - The edit is logged to wim_order_status_log (to_status='edited').
        Returns the updated order (uuid, orderId, status, grandTotal, items)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        role = user.get('role', '')
        if role not in ADMIN_ROLES and not user.get('is_api'):
            return self._send_json(403, {'error': 'Hanya admin / API key yang bisa edit order'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        order_uuid = (data.get('order_uuid') or '').strip()
        incoming = data.get('items')
        if not order_uuid:
            return self._send_json(400, {'error': 'order_uuid diperlukan'})
        if not isinstance(incoming, list):
            return self._send_json(400, {'error': 'items (array) diperlukan'})
        # Normalise incoming edits: by sku map, plus positional fallback list.
        inc_map = {}
        inc_positional = []
        for it in incoming:
            if not isinstance(it, dict):
                continue
            sku = str(it.get('sku') or '')
            try: q = float(it.get('qty'))
            except (TypeError, ValueError): q = 0
            try: up = float(it.get('unitPrice', it.get('unit_price')))
            except (TypeError, ValueError): up = 0
            entry = {'qty': q, 'unitPrice': up}
            if sku:
                inc_map[sku] = entry
            else:
                inc_positional.append(entry)
        changed_by = user.get('email') or user.get('name') or 'admin'
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, order_ref AS public_id, status, items, total AS grand_total "
                "FROM wim_orders WHERE uuid=%s AND deleted_at IS NULL",
                (order_uuid,))
            order = cur.fetchone()
            if not order:
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'Order not found'})
            items = order['items']
            if isinstance(items, str):
                try: items = json.loads(items)
                except: items = []
            if not isinstance(items, list):
                items = []
            # Apply edits only to non-bonus lines.
            pos = 0
            edits = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                if it.get('is_bonus'):
                    continue
                sku = str(it.get('sku') or '')
                entry = None
                if sku and sku in inc_map:
                    entry = inc_map[sku]
                elif pos < len(inc_positional):
                    entry = inc_positional[pos]
                pos += 1
                if entry is not None:
                    old = (float(it.get('qty') or 0) * float(it.get('unitPrice') or 0))
                    it['qty'] = entry['qty']
                    it['unitPrice'] = entry['unitPrice']
                    new = entry['qty'] * entry['unitPrice']
                    edits.append(f"{sku or (it.get('name') or '?')}:qty={entry['qty']},price={entry['unitPrice']}")
            # Recompute total from remaining non-bonus lines only.
            new_total = sum(
                float((it.get('qty') or 0)) * float((it.get('unitPrice') or 0))
                for it in items
                if isinstance(it, dict) and not it.get('is_bonus'))
            items_json = json.dumps(items, ensure_ascii=False, default=str)
            cur.execute(
                "UPDATE wim_orders SET items=%s::jsonb, total=%s, updated_at=NOW() WHERE uuid=%s",
                (items_json, round(new_total, 2), order_uuid))
            # Log the edit (defensive; table may not exist on old deployments)
            try:
                notes = ('Admin edit: ' + ('; '.join(edits) if edits else 'no line changed'))
                cur.execute(
                    "INSERT INTO wim_order_status_log (order_id, from_status, to_status, changed_by, notes) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (order['id'], order['status'], 'edited', changed_by, notes))
            except Exception as sle:
                write_log('WARN', 'orders', f'Order edit log insert failed: {sle}')
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'orders',
                      f'Order edited: {order["public_id"]} ({len(edits)} lines) total->{round(new_total,2)} by {changed_by}')
            self._send_json(200, {
                'status': 'ok',
                'uuid': order_uuid,
                'order_id': order['public_id'],
                'orderId': order['public_id'],
                'status': order['status'],
                'grandTotal': round(new_total, 2),
                'items': items,
            })
        except Exception as e:
            write_log('ERROR', 'orders', f'ADMIN EDIT failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Analytics (basic)
    # ═══════════════════════════════════════════════════

    def do_ANALYTICS_ORDERS(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        role = user.get('role', '')
        if role not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        from_date = (qs.get('from') or [''])[0].strip()
        to_date = (qs.get('to') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = "WHERE deleted_at IS NULL"
            params = []
            if from_date:
                where += " AND created_at >= %s::date"
                params.append(from_date)
            if to_date:
                where += " AND created_at <= %s::date + INTERVAL '1 day'"
                params.append(to_date)
            cur.execute(
                "SELECT COUNT(*) as total_orders, "
                "COALESCE(SUM(total), 0) as total_omset, "
                "CASE WHEN COUNT(*) > 0 THEN COALESCE(SUM(total), 0) / COUNT(*) ELSE 0 END as avg_order_value "
                f"FROM wim_orders {where}",
                params
            )
            summary = cur.fetchone()
            # Unique stores
            cur.execute(
                "SELECT COUNT(DISTINCT store_uuid) as unique_stores "
                f"FROM wim_orders {where}",
                params
            )
            stores_row = cur.fetchone()
            # By day
            cur.execute(
                "SELECT DATE(created_at) as day, COUNT(*) as count, "
                "COALESCE(SUM(total), 0) as omset "
                f"FROM wim_orders {where} "
                "GROUP BY DATE(created_at) ORDER BY day",
                params
            )
            by_day = [{
                'date': str(r['day']),
                'count': r['count'],
                'omset': float(r['omset']),
            } for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {
                'summary': {
                    'total_omset': float(summary['total_omset']),
                    'total_orders': summary['total_orders'],
                    'avg_order_value': float(summary['avg_order_value']),
                    'unique_stores': stores_row['unique_stores'],
                },
                'by_day': by_day,
            })
        except Exception as e:
            write_log('ERROR', 'analytics', f'Orders failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Report aggregation endpoints (mirrors GooVi/KlikOrder admin tables)
    # Each: admin-role gated (ADMIN_ROLES), date/user/depot/region filters,
    # raw wim_* SQL → JSON rows. Added 2026-09-10 (mapping plan Part C).
    # ═══════════════════════════════════════════════════
    def do_ANALYTICS_RECAP(self):
        """Kunjungan rekap harian per sales: #kunjungan, #pesanan, #no-order, EC% (G-V2)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        ffrom = (qs.get('date_from') or [''])[0][:10]
        to = (qs.get('date_to') or [''])[0][:10]
        uid = (qs.get('user_id') or [''])[0].strip()
        dep = (qs.get('depot_id') or [''])[0].strip()
        reg = (qs.get('region_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = ["DATE(v.checkin_at) BETWEEN %s::date AND %s::date"]
            params = [ffrom or time.strftime('%Y-%m-01'), to or time.strftime('%Y-%m-%d')]
            if uid: where.append("v.user_id=%s"); params.append(uid)
            if dep: where.append("ud.id=%s"); params.append(dep)
            if reg: where.append("r.id=%s"); params.append(reg)
            cur.execute(
                f"SELECT v.user_id, u.name AS rep, "
                f"COUNT(DISTINCT v.id) AS kunjungan, "
                f"COUNT(DISTINCT o.id) AS pesanan, "
                f"COUNT(DISTINCT v.id) - COUNT(DISTINCT o.id) AS no_order, "
                f"CASE WHEN COUNT(DISTINCT v.id)>0 "
                f"  THEN ROUND(100.0 * COUNT(DISTINCT o.id) / COUNT(DISTINCT v.id), 1) "
                f"  ELSE 0 END AS ec_pct, "
                f"ud.name AS depo_name, r.name AS region_name "
                f"FROM wim_visits v "
                f"LEFT JOIN wim_users u ON u.id=v.user_id "
                f"LEFT JOIN wim_user_meta um ON um.user_id=v.user_id "
                f"LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
                f"LEFT JOIN wim_regions r ON r.id=ud.region_id "
                f"LEFT JOIN wim_orders o ON o.visit_id=v.id AND o.deleted_at IS NULL "
                f"WHERE {' AND '.join(where)} "
                f"GROUP BY v.user_id, u.name, ud.name, r.name ORDER BY u.name", params)
            rows = [{'userId': r['user_id'], 'rep': r['rep'], 'kunjungan': r['kunjungan'],
                     'pesanan': r['pesanan'], 'noOrder': r['no_order'], 'ecPct': float(r['ec_pct']),
                     'depotName': r['depo_name'] or '', 'regionName': r['region_name'] or ''} for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'analytics', f'Recap failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ANALYTICS_GALLERY(self):
        """Galeri foto kunjungan — selfie + foto tambahan flattened per visit (G-V3)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        ffrom = (qs.get('date_from') or [''])[0][:10]
        to = (qs.get('date_to') or [''])[0][:10]
        uid = (qs.get('user_id') or [''])[0].strip()
        dep = (qs.get('depot_id') or [''])[0].strip()
        reg = (qs.get('region_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = ["DATE(v.checkin_at) BETWEEN %s::date AND %s::date"]
            params = [ffrom or time.strftime('%Y-%m-01'), to or time.strftime('%Y-%m-%d')]
            if uid: where.append("v.user_id=%s"); params.append(uid)
            if dep: where.append("ud.id=%s"); params.append(dep)
            if reg: where.append("r.id=%s"); params.append(reg)
            cur.execute(
                f"SELECT v.id AS visit_id, u.name AS rep, v.place_name AS store_name, "
                f"v.checkin_at, v.photos, "
                f"a.clock_in_photo AS selfie "
                f"FROM wim_visits v "
                f"LEFT JOIN wim_users u ON u.id=v.user_id "
                f"LEFT JOIN wim_user_meta um ON um.user_id=v.user_id "
                f"LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
                f"LEFT JOIN wim_regions r ON r.id=ud.region_id "
                f"LEFT JOIN wim_attendance a ON a.user_id=v.user_id AND a.date=DATE(v.checkin_at) "
                f"WHERE {' AND '.join(where)} ORDER BY v.checkin_at DESC LIMIT 300", params)
            rows = []
            for r in cur.fetchall():
                photos = r['photos'] if isinstance(r['photos'], list) else []
                if isinstance(r['photos'], str):
                    try: photos = json.loads(r['photos'])
                    except: photos = []
                selfie = r['selfie'] or (photos[0] if photos and isinstance(photos[0], str) else '')
                rows.append({'visitId': r['visit_id'], 'rep': r['rep'], 'storeName': r['store_name'],
                             'checkinAt': str(r['checkin_at']), 'selfie': selfie,
                             'photos': [p if isinstance(p, str) else (p.get('url','') if isinstance(p, dict) else '') for p in photos],
                             'photoCount': len(photos)})
            cur.close(); ret_pg(conn)
            self._send_json(200, {'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'analytics', f'Gallery failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ANALYTICS_ORDER_STOCK(self):
        """Analisa order vs stok per SKU/toko — qty order vs last stock check (G-S2)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        ffrom = (qs.get('date_from') or [''])[0][:10]
        to = (qs.get('date_to') or [''])[0][:10]
        dep = (qs.get('depot_id') or [''])[0].strip()
        reg = (qs.get('region_id') or [''])[0].strip()
        uid = (qs.get('user_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = ["o.deleted_at IS NULL", "DATE(o.created_at) BETWEEN %s::date AND %s::date"]
            params = [ffrom or time.strftime('%Y-%m-01'), to or time.strftime('%Y-%m-%d')]
            if dep: where.append("ud.id=%s"); params.append(dep)
            if reg: where.append("r.id=%s"); params.append(reg)
            if uid: where.append("u.id=%s"); params.append(uid)
            # Items are stored inline in wim_orders.items as a JSON array of
            # {sku, name, qty, is_bonus, unitPrice,...}; wim_order_items is a stale stub.
            cur.execute(
                f"SELECT oi->>'sku' AS sku, MAX(oi->>'name') AS product_name, "
                 f"COALESCE(SUM(ROUND((oi->>'qty')::numeric)) FILTER (WHERE NOT COALESCE((oi->>'is_bonus')::boolean,false)),0) AS qty_order, "
                f"sc.qty AS stock_qty, sc.checked_at AS stock_checked_at, "
                f"ud.name AS depo_name, r.name AS region_name "
                f"FROM wim_orders o "
                f"JOIN LATERAL jsonb_array_elements(o.items) oi ON TRUE "
                f"LEFT JOIN wim_users u ON u.id=o.user_id "
                f"LEFT JOIN wim_user_meta um ON um.user_id=o.user_id "
                f"LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
                f"LEFT JOIN wim_regions r ON r.id=ud.region_id "
                f"LEFT JOIN LATERAL (SELECT x.sku, x.qty, x.checked_at FROM wim_stock_check x "
                f"  WHERE x.sku=oi->>'sku' ORDER BY x.checked_at DESC LIMIT 1) sc ON TRUE "
                f"WHERE {' AND '.join(where)} "
                f"GROUP BY oi->>'sku', sc.qty, sc.checked_at, ud.name, r.name "
                f"ORDER BY qty_order DESC LIMIT 500", params)
            rows = [{'sku': r['sku'], 'productName': r['product_name'], 'storeName': '',
                     'qtyOrder': int(r['qty_order'] or 0),
                     'stockResult': int(r['stock_qty']) if r['stock_qty'] is not None else None,
                     'stockCheckedAt': str(r['stock_checked_at']) if r['stock_checked_at'] else None,
                     'depotName': r['depo_name'] or '', 'regionName': r['region_name'] or ''} for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'analytics', f'Order-stock failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ANALYTICS_PACKING_LIST(self):
        """Packing list: orders → SKU quantities over a period (loading sheet) (K-3/K-6)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        ffrom = (qs.get('date_from') or [''])[0][:10]
        to = (qs.get('date_to') or [''])[0][:10]
        dep = (qs.get('depot_id') or [''])[0].strip()
        reg = (qs.get('region_id') or [''])[0].strip()
        uid = (qs.get('user_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = ["o.deleted_at IS NULL", "DATE(o.created_at) BETWEEN %s::date AND %s::date"]
            params = [ffrom or time.strftime('%Y-%m-01'), to or time.strftime('%Y-%m-%d')]
            if dep: where.append("ud.id=%s"); params.append(dep)
            if reg: where.append("r.id=%s"); params.append(reg)
            if uid: where.append("u.id=%s"); params.append(uid)
            # Items are stored inline in wim_orders.items (JSON); wim_order_items is a stale stub.
            cur.execute(
                f"SELECT oi->>'sku' AS sku, MAX(oi->>'name') AS product_name, "
                f"COALESCE(SUM(ROUND((oi->>'qty')::numeric)) FILTER (WHERE (oi->>'is_bonus')::boolean), 0) AS qty_bonus, "
                f"COALESCE(SUM(ROUND((oi->>'qty')::numeric)),0) AS qty_total, "
                f"COUNT(DISTINCT o.id) AS num_orders, "
                f"ud.name AS depo_name, r.name AS region_name "
                f"FROM wim_orders o "
                f"JOIN LATERAL jsonb_array_elements(o.items) oi ON TRUE "
                f"LEFT JOIN wim_users u ON u.id=o.user_id "
                f"LEFT JOIN wim_user_meta um ON um.user_id=o.user_id "
                f"LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
                f"LEFT JOIN wim_regions r ON r.id=ud.region_id "
                f"WHERE {' AND '.join(where)} "
                f"GROUP BY oi->>'sku', ud.name, r.name "
                f"ORDER BY qty_total DESC", params)
            rows = [{'sku': r['sku'], 'productName': r['product_name'],
                     'qtyTotal': int(r['qty_total']), 'qtyBonus': int(r['qty_bonus']),
                     'numOrders': r['num_orders'], 'depotName': r['depo_name'] or '',
                     'regionName': r['region_name'] or ''} for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'analytics', f'Packing list failed: {e}')
            self._send_json(500, {'error': str(e)})

    def _packing_grouped_sql(self, luar_rute=False):
        """Shared per-day dispatch query. luar_rute=True → off-route orders only."""
        qs = parse_qs(urlparse(self.path).query)
        ffrom = (qs.get('date_from') or [''])[0][:10]
        to = (qs.get('date_to') or [''])[0][:10]
        dep = (qs.get('depot_id') or [''])[0].strip()
        reg = (qs.get('region_id') or [''])[0].strip()
        uid = (qs.get('user_id') or [''])[0].strip()
        if luar_rute:
            route_cond = "(o.off_route_reason IS NOT NULL AND o.off_route_reason <> '')"
        else:
            route_cond = "(o.off_route_reason IS NULL OR o.off_route_reason = '')"
        where = ["o.deleted_at IS NULL", route_cond,
                 "DATE(o.created_at) BETWEEN %s::date AND %s::date"]
        params = [ffrom or time.strftime('%Y-%m-01'), to or time.strftime('%Y-%m-%d')]
        if dep: where.append("um.depot_id=%s"); params.append(dep)
        if reg: where.append("ud.region_id=%s"); params.append(reg)
        if uid: where.append("o.user_id=%s"); params.append(uid)
        q = (
            "SELECT u.name AS sales_rep, o.user_id, DATE(o.created_at) AS order_date, "
            "COUNT(DISTINCT o.uuid) AS num_orders, "
            "COALESCE(SUM((it->>'qty')::numeric),0) AS total_qty, "
            "COALESCE(SUM(CASE WHEN (it->>'is_bonus')::text NOT IN ('true','1') "
            "THEN (it->>'qty')::numeric ELSE 0 END),0) AS qty_paid, "
            "MIN(o.created_at) AS oldest_at, MAX(o.created_at) AS newest_at "
            "FROM wim_orders o "
            "JOIN wim_users u ON u.id=o.user_id "
            "LEFT JOIN wim_user_meta um ON um.user_id=o.user_id "
            "LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
            "CROSS JOIN LATERAL jsonb_array_elements(o.items) it "
            "WHERE " + " AND ".join(where) + " "
            "GROUP BY u.name, o.user_id, DATE(o.created_at) "
            "ORDER BY order_date ASC, u.name ASC"
        )
        return q, params

    def do_ANALYTICS_PACKING_GROUPED(self):
        """Dispatch table: per sales rep + order-day, dalam-rute only, oldest first."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            q, params = self._packing_grouped_sql(luar_rute=False)
            cur.execute(q, params)
            today = datetime.date.today()
            rows = []
            for r in cur.fetchall():
                od = r['order_date']
                h = (today - od).days if od else 0
                status_class = 'h-red' if h >= 2 else ('h-yellow' if h == 1 else 'h-green')
                rows.append({
                    'salesRep': r['sales_rep'] or '', 'userId': r['user_id'],
                    'orderDate': od.isoformat() if od else None, 'h': h,
                    'statusClass': status_class,
                    'totalQty': int(r['total_qty'] or 0),
                    'qtyPaid': int(r['qty_paid'] or 0),
                    'numOrders': r['num_orders'],
                    'oldestAt': r['oldest_at'].isoformat() if r.get('oldest_at') else None,
                    'newestAt': r['newest_at'].isoformat() if r.get('newest_at') else None,
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'analytics', f'Packing grouped failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ANALYTICS_PACKING_LUARRUTE(self):
        """Separate dispatch table for luar-rute orders."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            q, params = self._packing_grouped_sql(luar_rute=True)
            cur.execute(q, params)
            today = datetime.date.today()
            rows = []
            for r in cur.fetchall():
                od = r['order_date']
                h = (today - od).days if od else 0
                rows.append({
                    'salesRep': r['sales_rep'] or '', 'userId': r['user_id'],
                    'orderDate': od.isoformat() if od else None, 'h': h,
                    'statusClass': 'h-red' if h >= 2 else ('h-yellow' if h == 1 else 'h-green'),
                    'totalQty': int(r['total_qty'] or 0),
                    'qtyPaid': int(r['qty_paid'] or 0),
                    'numOrders': r['num_orders'],
                    'oldestAt': r['oldest_at'].isoformat() if r.get('oldest_at') else None,
                })
            cur.close(); ret_pg(conn)
            self._send_json(200, {'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'analytics', f'Packing luar-rute failed: {e}')
            self._send_json(500, {'error': str(e)})

    def _packing_day_orders(self, user_id, date_str, luar_rute=False):
        """Return orders for a sales rep on a calendar date, time-ordered.
        luar_rute=True -> off-route orders only; else dalam-rute only."""
        conn = get_pg()
        if not conn: raise RuntimeError('DB connection failed')
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        route_cond = ("(o.off_route_reason IS NOT NULL AND o.off_route_reason <> '')"
                      if luar_rute else
                      "(o.off_route_reason IS NULL OR o.off_route_reason = '')")
        q = (
            "SELECT o.uuid, o.order_ref, o.status, o.created_at, o.total AS grand_total, "
            "o.payment_method, s.name AS store_name, s.address AS store_address, "
            "s.kelurahan AS store_kelurahan, s.kecamatan AS store_kecamatan, "
            "COALESCE(SUM((it->>'qty')::numeric),0) AS items_qty, "
            "COALESCE(SUM(CASE WHEN (it->>'is_bonus')::text NOT IN ('true','1') "
            "THEN (it->>'qty')::numeric ELSE 0 END),0) AS qty_paid, "
            "EXISTS(SELECT 1 FROM wim_invoice wi WHERE wi.order_uuid=o.uuid) AS has_invoice "
            "FROM wim_orders o "
            "LEFT JOIN wim_stores s ON s.uuid=o.store_uuid "
            "CROSS JOIN LATERAL jsonb_array_elements(o.items) it "
            "WHERE o.user_id=%s AND DATE(o.created_at)=%s::date AND o.deleted_at IS NULL "
            "AND " + route_cond + " "
            "GROUP BY o.uuid, o.order_ref, o.status, o.created_at, o.total, o.payment_method, "
            "s.name, s.address, s.kelurahan, s.kecamatan "
            "ORDER BY o.created_at ASC"
        )
        cur.execute(q, (int(user_id), date_str))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); ret_pg(conn)
        return rows

    def do_ANALYTICS_PACKING_DAY_ORDERS(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get('user_id') or [''])[0].strip()
        date_str = (qs.get('date') or [''])[0][:10]
        luar_rute = (qs.get('luar_rute') or [''])[0].strip().lower() in ('1','true','yes')
        if not uid or not date_str:
            return self._send_json(400, {'error': 'user_id and date required'})
        try:
            rows = self._packing_day_orders(uid, date_str, luar_rute=luar_rute)
            # normalize datetimes for JSON
            for r in rows:
                if r.get('created_at'):
                    try: r['created_at'] = r['created_at'].isoformat()
                    except Exception: pass
                r['grandTotal'] = float(r.get('grand_total') or 0)
                r.pop('grand_total', None)
                r['itemsQty'] = int(r.get('items_qty') or 0)
                r['qtyPaid'] = int(r.get('qty_paid') or 0)
            self._send_json(200, {'rows': rows})
        except Exception as e:
            write_log('ERROR', 'analytics', f'Packing day orders failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ANALYTICS_PACKING_SURAT_JALAN(self):
        """Surat Jalan PDF (reportlab) — numbered store route for one sales rep + day."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get('user_id') or [''])[0].strip()
        date_str = (qs.get('date') or [''])[0][:10]
        if not uid or not date_str:
            return self._send_json(400, {'error': 'user_id and date required'})
        try:
            rows = self._packing_day_orders(uid, date_str)
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import ParagraphStyle
            from io import BytesIO
            buf = BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=24, bottomMargin=24,
                                    leftMargin=30, rightMargin=30)
            st = []
            st.append(Paragraph('SURAT JALAN', ParagraphStyle(name='t', alignment=1, fontSize=16, spaceAfter=2)))
            sales_name = rows[0].get('store_name') if False else ''
            st.append(Paragraph('Tanggal: ' + date_str, ParagraphStyle(name='s', alignment=1, fontSize=11, spaceAfter=12)))
            data = [['No', 'Kode/Ref', 'Toko', 'Alamat', 'Kelurahan', 'Qty']]
            for i, r in enumerate(rows, 1):
                data.append([
                    str(i), str(r.get('order_ref') or ''), str(r.get('store_name') or ''),
                    str(r.get('store_address') or ''), str(r.get('store_kelurahan') or ''),
                    str(r.get('itemsQty') or r.get('items_qty') or 0),
                ])
            t = Table(data, colWidths=[28, 88, 120, 150, 90, 40], repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0a7c42')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('FONTSIZE', (0,0), (-1,-1), 8),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f3f6f4')]),
            ]))
            st.append(t)
            st.append(Spacer(1, 18))
            st.append(Paragraph('Total order: %d  |  Total qty: %s' % (
                len(rows), sum(int(r.get('itemsQty') or r.get('items_qty') or 0) for r in rows)),
                ParagraphStyle(name='f', alignment=1, fontSize=10)))
            doc.build(st)
            pdf = buf.getvalue(); buf.close()
            self._send_bytes(200, pdf, 'application/pdf',
                             'surat-jalan-%s-%s.pdf' % (date_str, uid))
        except Exception as e:
            write_log('ERROR', 'analytics', f'Surat jalan PDF failed: {e}')
            self._send_json(500, {'error': str(e)})

    def _order_items(self, order_uuid):
        """Fetch raw items JSON array for one order."""
        conn = get_pg()
        if not conn: raise RuntimeError('DB connection failed')
        cur = conn.cursor()
        cur.execute("SELECT o.items FROM wim_orders o WHERE o.uuid=%s AND o.deleted_at IS NULL", (order_uuid,))
        row = cur.fetchone()
        cur.close(); ret_pg(conn)
        if not row or not row[0]:
            return []
        try:
            items = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return items if isinstance(items, list) else []
        except Exception:
            return []

    def do_ANALYTICS_PACKING_INVOICE_ZIP(self):
        """ZIP of per-order invoice PDFs for one sales rep + day."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get('user_id') or [''])[0].strip()
        date_str = (qs.get('date') or [''])[0][:10]
        if not uid or not date_str:
            return self._send_json(400, {'error': 'user_id and date required'})
        try:
            rows = self._packing_day_orders(uid, date_str)
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import ParagraphStyle
            from io import BytesIO
            import zipfile
            zbuf = BytesIO()
            with zipfile.ZipFile(zbuf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for r in rows:
                    b2 = BytesIO()
                    doc = SimpleDocTemplate(b2, pagesize=A4, topMargin=30, bottomMargin=30,
                                            leftMargin=30, rightMargin=30)
                    elems = [
                        Paragraph('INVOICE / KUPON PESANAN',
                                  ParagraphStyle(name='ti', alignment=1, fontSize=15, spaceAfter=2)),
                        Paragraph('Ref: %s<br/>Toko: %s<br/>Alamat: %s' % (
                            (r.get('order_ref') or ''), (r.get('store_name') or ''),
                            (r.get('store_address') or '')),
                            ParagraphStyle(name='h', fontSize=10, spaceAfter=10)),
                    ]
                    items = self._order_items(r.get('uuid'))
                    idata = [['SKU', 'Produk', 'Qty', 'Harga', 'Subtotal']]
                    for it in items:
                        sku = it.get('sku', '') if isinstance(it, dict) else ''
                        name = it.get('name', it.get('productName', '')) if isinstance(it, dict) else ''
                        qty = it.get('qty', 0) if isinstance(it, dict) else 0
                        up = it.get('unitPrice', 0) if isinstance(it, dict) else 0
                        bonus = it.get('is_bonus') if isinstance(it, dict) else False
                        if bonus:
                            idata.append([sku, name, '+%s' % qty, 'Gratiis', 'Rp 0'])
                        else:
                            idata.append([sku, name, str(qty), 'Rp %s' % fmt_idr(up), 'Rp %s' % fmt_idr(qty * up)])
                    itable = Table(idata, colWidths=[90, 190, 40, 70, 80], repeatRows=1)
                    itable.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0a7c42')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
                        ('FONTSIZE', (0,0), (-1,-1), 8),
                        ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ]))
                    elems.append(itable)
                    elems.append(Spacer(1, 12))
                    elems.append(Paragraph('Grand Total: Rp %s' % fmt_idr(r.get('grandTotal') or 0),
                        ParagraphStyle(name='gt', alignment=2, fontSize=11, spaceBefore=6)))
                    doc.build(elems)
                    fname = '%s.pdf' % (r.get('order_ref') or r.get('uuid'))
                    zf.writestr(fname, b2.getvalue())
                    b2.close()
            zipbytes = zbuf.getvalue(); zbuf.close()
            self._send_bytes(200, zipbytes, 'application/zip',
                             'invoices-%s-%s.zip' % (date_str, uid))
        except Exception as e:
            write_log('ERROR', 'analytics', f'Invoice zip failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ANALYTICS_PERFORMANCE(self):
        """Performa sales-depo: per depo/sales EC, pesanan, kunjungan, omset (G-R1)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        ffrom = (qs.get('date_from') or [''])[0][:10]
        to = (qs.get('date_to') or [''])[0][:10]
        dep = (qs.get('depot_id') or [''])[0].strip()
        reg = (qs.get('region_id') or [''])[0].strip()
        uid = (qs.get('user_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = ["DATE(v.checkin_at) BETWEEN %s::date AND %s::date"]
            params = [ffrom or time.strftime('%Y-%m-01'), to or time.strftime('%Y-%m-%d')]
            if dep: where.append("ud.id=%s"); params.append(dep)
            if reg: where.append("r.id=%s"); params.append(reg)
            if uid: where.append("v.user_id=%s"); params.append(uid)
            cur.execute(
                f"SELECT ud.name AS depo_name, r.name AS region_name, u.name AS rep, "
                f"COUNT(DISTINCT v.id) AS kunjungan, COUNT(DISTINCT o.id) AS pesanan, "
                f"COALESCE(SUM(o.total),0) AS omset, "
                f"CASE WHEN COUNT(DISTINCT v.id)>0 "
                f"  THEN ROUND(100.0 * COUNT(DISTINCT o.id) / COUNT(DISTINCT v.id), 1) "
                f"  ELSE 0 END AS ec_pct "
                f"FROM wim_visits v "
                f"LEFT JOIN wim_users u ON u.id=v.user_id "
                f"LEFT JOIN wim_user_meta um ON um.user_id=v.user_id "
                f"LEFT JOIN wim_depots ud ON ud.id=um.depot_id "
                f"LEFT JOIN wim_regions r ON r.id=ud.region_id "
                f"LEFT JOIN wim_orders o ON o.visit_id=v.id AND o.deleted_at IS NULL "
                f"WHERE {' AND '.join(where)} "
                f"GROUP BY ud.name, r.name, u.name ORDER BY omset DESC", params)
            rows = [{'depotName': r['depo_name'] or '-', 'regionName': r['region_name'] or '',
                     'rep': r['rep'], 'kunjungan': r['kunjungan'], 'pesanan': r['pesanan'],
                     'omset': float(r['omset']), 'ecPct': float(r['ec_pct'])} for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'analytics', f'Performance failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_ANALYTICS_STORE_ORDERS(self):
        """Store order trail — report order per toko (G-R3). Filters store via q/store_uuid."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        store_uuid = (qs.get('store_uuid') or qs.get('q') or [''])[0].strip()
        ffrom = (qs.get('date_from') or [''])[0][:10]
        to = (qs.get('date_to') or [''])[0][:10]
        uid = (qs.get('user_id') or [''])[0].strip()
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = ["o.deleted_at IS NULL"]
            params = []
            if uid: where.append("o.user_id=%s"); params.append(uid)
            if store_uuid: where.append("o.store_uuid=%s"); params.append(store_uuid)
            if ffrom: where.append("DATE(o.created_at) >= %s::date"); params.append(ffrom)
            if to: where.append("DATE(o.created_at) <= %s::date"); params.append(to)
            cur.execute(
                f"SELECT o.uuid, o.order_ref, o.status, o.total, o.created_at, s.name AS store_name, "
                f"u.name AS rep, o.payment_method "
                f"FROM wim_orders o "
                f"LEFT JOIN wim_stores s ON s.uuid=o.store_uuid "
                f"LEFT JOIN wim_users u ON u.id=o.user_id "
                f"WHERE {' AND '.join(where)} ORDER BY o.created_at DESC LIMIT 200", params)
            rows = [{'uuid': r['uuid'], 'orderRef': r['order_ref'], 'status': r['status'],
                     'total': float(r['total'] or 0), 'createdAt': str(r['created_at']),
                     'storeName': r['store_name'] or '', 'rep': r['rep'] or '',
                     'paymentMethod': r['payment_method'] or ''} for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'analytics', f'Store orders failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Post-review additive features (2026-09-10): invoices/receivables + stock on-hand.
    # Reversible: new tables only; no changes to existing flows.
    # ═══════════════════════════════════════════════════
    def do_INVOICES(self):
        """GET /api/admin/invoices — list invoices with optional status/date filter + AR aging."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        status = (qs.get('status') or [''])[0].strip()
        ffrom = (qs.get('date_from') or [''])[0][:10]
        to = (qs.get('date_to') or [''])[0][:10]
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = ["1=1"]; params = []
            if status: where.append("i.status=%s"); params.append(status)
            if ffrom: where.append("DATE(i.issued_at) >= %s::date"); params.append(ffrom)
            if to: where.append("DATE(i.issued_at) <= %s::date"); params.append(to)
            cur.execute(
                f"SELECT i.id, i.invoice_no, i.order_uuid, i.status, i.subtotal, i.discount, "
                f"i.promo_value, i.grand_total, i.customer_name, i.issued_at, o.order_ref, "
                f"u.name AS rep_name "
                f"FROM wim_invoice i "
                f"LEFT JOIN wim_orders o ON o.uuid=i.order_uuid "
                f"LEFT JOIN wim_users u ON u.id=o.user_id "
                f"WHERE {' AND '.join(where)} ORDER BY i.issued_at DESC LIMIT 300", params)
            invoices = [dict(r, grand_total=float(r['grand_total'] or 0),
                             subtotal=float(r['subtotal'] or 0),
                             discount=float(r['discount'] or 0),
                             promo_value=float(r['promo_value'] or 0),
                             issued_at=str(r['issued_at'])) for r in cur.fetchall()]
            # AR aging buckets (unpaid only)
            cur.execute(
                "SELECT "
                "COALESCE(SUM(grand_total) FILTER (WHERE status='unpaid' AND issued_at >= now() - interval '30 days'),0) AS d30, "
                "COALESCE(SUM(grand_total) FILTER (WHERE status='unpaid' AND issued_at < now() - interval '30 days' AND issued_at >= now() - interval '60 days'),0) AS d60, "
                "COALESCE(SUM(grand_total) FILTER (WHERE status='unpaid' AND issued_at < now() - interval '60 days'),0) AS d90 "
                "FROM wim_invoice")
            aging = cur.fetchone()
            cur.close(); ret_pg(conn)
            self._send_json(200, {'invoices': invoices,
                                  'aging': {'d30': float(aging['d30'] or 0), 'd60': float(aging['d60'] or 0),
                                            'd90': float(aging['d90'] or 0)},
                                  'total': len(invoices)})
        except Exception as e:
            write_log('ERROR', 'invoice', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_INVOICES_POST(self):
        """POST /api/admin/invoices — create an invoice for an existing order."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict): return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        order_uuid = data.get('order_uuid', '').strip()
        if not order_uuid:
            return self._send_json(400, {'error': 'order_uuid diperlukan'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Resolve order totals + customer
            cur.execute(
                "SELECT o.uuid, o.id AS order_id, o.total, o.order_ref, s.name AS customer_name "
                "FROM wim_orders o LEFT JOIN wim_stores s ON o.store_uuid=s.uuid "
                "WHERE o.uuid=%s AND o.deleted_at IS NULL", (order_uuid,))
            order = cur.fetchone()
            if not order:
                cur.close(); ret_pg(conn)
                return self._send_json(404, {'error': 'Order tidak ditemukan'})
            grand = float(order['total'] or 0)
            # Dedupe: prevent creating a second invoice for the same order
            cur.execute("SELECT id FROM wim_invoice WHERE order_uuid=%s OR order_id=%s", (order_uuid, order['order_id']))
            if cur.fetchone():
                cur.close(); ret_pg(conn)
                return self._send_json(409, {'error': 'Invois sudah ada untuk order ini'})
            seq_no = f"INV-{time.strftime('%Y%m%d')}-{order['order_id']}"
            cur.execute(
                "INSERT INTO wim_invoice (invoice_no, order_uuid, order_id, status, subtotal, discount, promo_value, grand_total, customer_name, issued_at) "
                "VALUES (%s,%s,%s,'unpaid',%s,0,0,%s,%s,NOW()) RETURNING id",
                (seq_no, order_uuid, order['order_id'], grand, grand, order['customer_name']))
            new_id = cur.fetchone()['id']
            conn.commit(); cur.close(); ret_pg(conn)
            self._send_json(201, {'id': new_id, 'invoice_no': seq_no, 'status': 'unpaid', 'grand_total': grand})
        except Exception as e:
            write_log('ERROR', 'invoice', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_STOCK_BALANCE_GET(self):
        """GET /api/admin/stock-balance — on-hand balance per product/depot (with low-stock)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        qs = parse_qs(urlparse(self.path).query)
        depot = (qs.get('depot_id') or [''])[0].strip()
        low_only = (qs.get('low_only') or [''])[0].strip() in ('1','true','yes')
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            where = ["1=1"]; params = []
            if depot: where.append("sb.depot_id=%s"); params.append(depot)
            if low_only: where.append("sb.qty <= 10")
            cur.execute(
                f"SELECT sb.id, sb.product_id, sb.product_sku, sb.depot_id, d.name AS depot_name, "
                f"sb.qty, sb.updated_at, sb.source, sb.note, p.name AS product_name "
                f"FROM wim_stock_balance sb "
                f"LEFT JOIN wim_depots d ON d.id=sb.depot_id "
                f"LEFT JOIN wim_products p ON p.id=sb.product_id "
                f"WHERE {' AND '.join(where)} ORDER BY sb.updated_at DESC LIMIT 300", params)
            rows = [dict(r, qty=float(r['qty'] or 0), updated_at=str(r['updated_at'])) for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'stock_balance', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_STOCK_BALANCE_POST(self):
        """POST /api/admin/stock-balance — adjust on-hand qty (audited)."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') not in ADMIN_ROLES:
            return self._send_json(403, {'error': 'Hanya admin'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict): return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        product_id = data.get('product_id') or data.get('id')
        product_sku = (data.get('product_sku') or '')[:50]
        depot_id = data.get('depot_id')
        qty = data.get('qty')
        note = (data.get('note') or '')[:255]
        source = (data.get('source') or 'adjustment')[:30]
        if product_id is None and not product_sku:
            return self._send_json(400, {'error': 'product_id atau product_sku diperlukan'})
        if depot_id is None:
            return self._send_json(400, {'error': 'depot_id diperlukan'})
        try:
            qty = float(qty)
        except Exception:
            return self._send_json(400, {'error': 'qty harus angka'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Resolve product_id from sku if not supplied (so JOIN shows product_name in GET)
            if product_id is None and product_sku:
                cur.execute("SELECT id FROM wim_products WHERE sku=%s LIMIT 1", (product_sku,))
                prow = cur.fetchone()
                if prow: product_id = prow['id']
            cur.execute(
                "INSERT INTO wim_stock_balance (product_id, product_sku, depot_id, qty, updated_at, changed_by, source, note) "
                "VALUES (%s,%s,%s,%s,NOW(),%s,%s,%s) RETURNING id",
                (product_id, product_sku, depot_id, qty, user.get('id'), source, note))
            new_id = cur.fetchone()['id']
            conn.commit(); cur.close(); ret_pg(conn)
            self._send_json(201, {'id': new_id, 'status': 'ok'})
        except Exception as e:
            write_log('ERROR', 'stock_balance', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Administrative region lookup (wilayah): /api/wilayah?level=&parent=&q=
    # Serves the locally-imported BPS/Kemendagri dataset (wim_wilayah).
    # level: prov | kab | kec | kel. parent = parent BPS code (e.g. '31' for DKI kota).
    # q = optional case-insensitive prefix search on nama. Auth: any valid session.
    # ═══════════════════════════════════════════════════
    def do_WILAYAH(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        level = (qs.get('level') or ['prov'])[0].strip().lower()
        parent = (qs.get('parent') or [''])[0].strip()
        q = (qs.get('q') or [''])[0].strip().lower()
        if level not in ('prov', 'kab', 'kec', 'kel'):
            return self._send_json(400, {'error': 'level harus prov|kab|kec|kel'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            sql = "SELECT kode, nama, level FROM wim_wilayah WHERE level=%s"
            params = [level]
            if level == 'prov':
                pass  # all provinces
            elif parent:
                sql += " AND parent_kode=%s"; params.append(parent)
            if q:
                sql += " AND LOWER(nama) LIKE %s"; params.append('%' + q + '%')
            sql += " ORDER BY nama LIMIT 2000"
            cur.execute(sql, params)
            rows = [{'kode': r['kode'], 'nama': r['nama']} for r in cur.fetchall()]
            cur.close(); ret_pg(conn)
            self._send_json(200, {'level': level, 'parent': parent, 'rows': rows, 'total': len(rows)})
        except Exception as e:
            write_log('ERROR', 'wilayah', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Config (wim_app_config)
    # ═══════════════════════════════════════════════════

    def do_CONFIG_GET(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute("SELECT config_key, config_value FROM wim_app_config ORDER BY config_key")
                configs = {r['config_key']: r['config_value'] for r in cur.fetchall()}
            except Exception:
                configs = {}
            cur.close(); ret_pg(conn)
            self._send_json(200, {'data': configs})
        except Exception as e:
            write_log('ERROR', 'config', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_CONFIG_KEY_PATCH(self, params):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') != 'super_admin':
            return self._send_json(403, {'error': 'Hanya super_admin'})
        config_key = params['key']
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        value = data.get('value', data.get('config_value', ''))
        description = data.get('description', '')
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO wim_app_config (config_key, config_value, description) "
                    "VALUES (%s, %s::jsonb, %s) "
                    "ON CONFLICT (config_key) DO UPDATE SET config_value=EXCLUDED.config_value, description=EXCLUDED.description",
                    (config_key, json.dumps(value) if not isinstance(value, str) else json.dumps(value), description)
                )
            except Exception as ce:
                write_log('WARN', 'config', f'wim_app_config table may not exist: {ce}')
                cur.close(); ret_pg(conn)
                return self._send_json(500, {'error': 'Tabel konfigurasi tidak tersedia'})
            conn.commit()
            cur.close(); ret_pg(conn)
            self._send_json(200, {'status': 'ok', 'key': config_key, 'value': value})
        except Exception as e:
            write_log('ERROR', 'config', f'PATCH failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # API Keys
    # ═══════════════════════════════════════════════════

    def do_API_KEYS_GET(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') != 'super_admin':
            return self._send_json(403, {'error': 'Hanya super_admin'})
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute(
                    "SELECT id, name, api_key, scope, is_active, created_at "
                    "FROM wim_api_keys ORDER BY created_at DESC"
                )
                keys = [{
                    'id': r['id'], 'name': r['name'], 'api_key': r['api_key'],
                    'scope': r['scope'], 'is_active': bool(r['is_active']),
                    'created_at': str(r['created_at']) if r['created_at'] else None,
                } for r in cur.fetchall()]
            except Exception:
                keys = []
            cur.close(); ret_pg(conn)
            self._send_json(200, {'data': keys, 'total': len(keys)})
        except Exception as e:
            write_log('ERROR', 'api_keys', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    def do_API_KEYS_POST(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        if user.get('role') != 'super_admin':
            return self._send_json(403, {'error': 'Hanya super_admin'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Request body must be a JSON object'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        name = (data.get('name') or '').strip()
        scope = (data.get('scope') or 'orders:read').strip()
        if not name:
            return self._send_json(400, {'error': 'Nama key diperlukan'})
        api_key = f'wim_{secrets.token_hex(24)}'
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute(
                    "INSERT INTO wim_api_keys (name, api_key, scope, is_active) "
                    "VALUES (%s, %s, %s, true) RETURNING id",
                    (name, api_key, scope)
                )
                row = cur.fetchone()
                key_id = row['id']
            except Exception as ce:
                write_log('WARN', 'api_keys', f'Table may not exist: {ce}')
                cur.close(); ret_pg(conn)
                return self._send_json(500, {'error': 'Tabel api_keys tidak tersedia'})
            conn.commit()
            cur.close(); ret_pg(conn)
            write_log('INFO', 'api_keys', f'API key created: {name} by {user["email"]}')
            self._send_json(201, {'data': {'id': key_id, 'name': name, 'api_key': api_key, 'scope': scope}})
        except Exception as e:
            write_log('ERROR', 'api_keys', f'POST failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Sync Queue (worker GET pending jobs)
    # ═══════════════════════════════════════════════════

    def do_SYNC_QUEUE_GET(self):
        """GET /api/sync/queue — worker picks up pending jobs with optional status filter."""
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        qs = parse_qs(urlparse(self.path).query)
        status = (qs.get('status') or ['pending'])[0].strip()
        limit_str = (qs.get('limit') or ['50'])[0].strip()
        try:
            limit = max(1, min(int(limit_str), 200))
        except ValueError:
            limit = 50
        try:
            conn = get_pg()
            if not conn: return self._send_json(500, {'error': 'DB connection failed'})
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute(
                    "SELECT id, entity_type, entity_id, action, target, payload, status, "
                    "error, retry_count, created_at, synced_at "
                    "FROM wim_sync_queue WHERE status=%s ORDER BY created_at ASC LIMIT %s",
                    (status, limit)
                )
                jobs = [{
                    'id': r['id'],
                    'entity_type': r['entity_type'],
                    'entity_id': r['entity_id'],
                    'action': r['action'],
                    'target': r['target'],
                    'payload': r['payload'],
                    'status': r['status'],
                    'error': r['error'],
                    'retry_count': r['retry_count'],
                    'created_at': str(r['created_at']) if r['created_at'] else None,
                    'synced_at': str(r['synced_at']) if r['synced_at'] else None,
                } for r in cur.fetchall()]
            except Exception:
                jobs = []
            cur.close(); ret_pg(conn)
            self._send_json(200, {'data': jobs, 'total': len(jobs)})
        except Exception as e:
            write_log('ERROR', 'sync_queue', f'GET failed: {e}')
            self._send_json(500, {'error': str(e)})

    # ═══════════════════════════════════════════════════
    # Logging
    # ═══════════════════════════════════════════════════

    def do_LOG(self):
        if self.path != '/api/log': return self._send_json(404, {'error': 'Not found'})
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            write_log(data.get('level', 'INFO'), data.get('context', 'client'), data.get('message', ''), data.get('data'))
            self._send_json(200, {'status': 'ok'})
        except:
            self._send_json(200, {'status': 'logged'})

    def do_LOGS(self):
        if self.path.split('?')[0] != '/api/logs': return self._send_json(404, {'error': 'Not found'})
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        try:
            limit = 100
            try:
                if '?limit=' in self.path:
                    limit = min(int(self.path.split('=')[1]), 500)
            except: pass
            entries = []
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try: entries.append(json.loads(line))
                            except: pass
            entries.reverse()
            self._send_json(200, {'logs': entries[:limit]})
        except Exception as e:
            write_log('ERROR', 'server', 'Failed to read logs', str(e))
            self._send_json(200, {'logs': []})

    def do_OPTIONS(self):
        self._send_response_raw(204, [
            ('Access-Control-Allow-Origin', '*'),
            ('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS'),
            ('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept, Customer-Token'),
            ('Access-Control-Max-Age', '86400'),
        ], b'')

    # ═══════════════════════════════════════════════════
    # Routing
    # ═══════════════════════════════════════════════════

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/api/wilayah': return self.do_WILAYAH()
        if p == '/api/logs': return self.do_LOGS()
        if p == '/api/auth/session': return self.do_SESSION()
        if p == '/api/filter-options': return self.do_FILTER_OPTIONS()
        if p == '/api/absensi': return self.do_ABSENSI_GET()
        if p == '/api/depots': return self.do_DEPOTS()
        if p == '/api/stock': return self.do_STOCK_GET()
        if p == '/api/dashboard': return self.do_DASHBOARD()
        if p == '/api/stores': return self.do_MY_STORES()
        if p == '/api/stores/orders': return self.do_STORE_ORDERS()
        if p == '/api/stores/all': return self.do_ALL_STORES()
        if p == '/api/visit_plan': return self.do_VISIT_PLAN_GET()
        if p == '/api/admin/plan/day' or p == '/api/plan/day': return self.do_PLAN_DAY_GET()
        if p == '/api/admin/plan/templates': return self.do_PLAN_TEMPLATES_GET()
        if p == '/api/admin/plan/template': return self.do_PLAN_TEMPLATE_GET()
        if p == '/api/admin/rencana/view' or p == '/api/rencana/view': return self.do_RENCANA_VIEW()
        if p == '/api/visits': return self.do_VISITS_GET()
        if p == '/api/visits/active': return self.do_VISITS_ACTIVE()
        if p == '/api/products': return self.do_PRODUCTS()
        if p == '/api/products/promos': return self.do_PROMOS()
        if p == '/api/admin/promos': return self.do_PROMOS_ADMIN_GET()
        if p == '/api/admin/products/prices' or p == '/api/admin/pricing':
            return self.do_PRODUCTS_PRICES_GET()
        if p == '/api/orders': return self.do_ORDER_GET()
        if p == '/api/orders/detail': return self.do_ORDER_DETAIL()
        if p == '/api/orders/public': return self.do_ORDER_PUBLIC()
        if p == '/api/report': return self.do_REPORT()
        # New endpoints
        if p == '/api/users':
            return self.do_USERS_GET()
        if p == '/api/config':
            return self.do_CONFIG_GET()
        if p == '/api/api-keys':
            return self.do_API_KEYS_GET()
        if p == '/api/sync/queue':
            return self.do_SYNC_QUEUE_GET()
        if p == '/api/analytics/orders':
            return self.do_ANALYTICS_ORDERS()
        if p == '/api/analytics/recap':
            return self.do_ANALYTICS_RECAP()
        if p == '/api/analytics/gallery':
            return self.do_ANALYTICS_GALLERY()
        if p == '/api/analytics/order-stock':
            return self.do_ANALYTICS_ORDER_STOCK()
        if p == '/api/analytics/packing-list':
            return self.do_ANALYTICS_PACKING_LIST()
        if p == '/api/analytics/packing-grouped':
            return self.do_ANALYTICS_PACKING_GROUPED()
        if p == '/api/analytics/packing-day-orders':
            return self.do_ANALYTICS_PACKING_DAY_ORDERS()
        if p == '/api/analytics/packing-surat-jalan':
            return self.do_ANALYTICS_PACKING_SURAT_JALAN()
        if p == '/api/analytics/packing-invoice-zip':
            return self.do_ANALYTICS_PACKING_INVOICE_ZIP()
        if p == '/api/analytics/packing-luarrute':
            return self.do_ANALYTICS_PACKING_LUARRUTE()
        if p == '/api/analytics/sales-performance':
            return self.do_ANALYTICS_PERFORMANCE()
        if p == '/api/analytics/store-orders':
            return self.do_ANALYTICS_STORE_ORDERS()
        if p == '/api/admin/invoices':
            return self.do_INVOICES()
        if p == '/api/admin/stock-balance':
            return self.do_STOCK_BALANCE_GET()
        if p == '/api/positions/latest':
            return self.do_POSITION_GET()
        if p == '/api/positions/all':
            return self.do_POSITIONS_ALL()
        if p == '/api/admin/route-map' or p == '/api/route-map':
            return self.do_ROUTE_MAP()
        # Parameterized GET routes
        m = self._match_path('/api/users/:id/meta')
        if m: return self.do_USER_META_GET(m)
        m = self._match_path('/api/users/:id')
        if m: return self.do_USER_GET(m)
        m = self._match_path('/api/stores/:uuid/contacts')
        if m: return self.do_STORE_CONTACTS_GET(m)
        m = self._match_path('/api/stores/:uuid')
        if m: return self.do_STORE_BY_UUID(m)
        return super().do_GET()

    def do_HEAD(self):
        p = self.path.split('?')[0]
        if p.startswith('/api/'):
            return self._send_json(404, {'error': 'Not found'})
        return super().do_HEAD()

    def do_POST(self):
        p = self.path.split('?')[0]
        if p == '/api/auth/login': return self.do_LOGIN()
        if p == '/api/auth/logout': return self.do_LOGOUT()
        if p == '/api/reset-password': return self.do_RESET_PASSWORD()
        if p == '/api/password/change': return self.do_PASSWORD_CHANGE()
        if p == '/api/depots': return self.do_DEPOTS_POST()
        if p == '/api/positions': return self.do_POSITION_POST()
        if p == '/api/log': return self.do_LOG()
        if p == '/api/absensi': return self.do_ABSENSI_POST()
        if p == '/api/stock': return self.do_STOCK_POST()
        if p == '/api/products': return self.do_PRODUCTS_POST()
        if p == '/api/visit_plan': return self.do_VISIT_PLAN()
        if p == '/api/admin/plan/day' or p == '/api/plan/day': return self.do_PLAN_DAY_POST()
        if p == '/api/admin/plan/template': return self.do_PLAN_TEMPLATE_POST()
        if p == '/api/admin/plan/template/resolve': return self.do_PLAN_TEMPLATE_RESOLVE()
        if p == '/api/orders/calculate':
            return self.do_ORDER_CALC()
        if p == '/api/orders':
            return self.do_ORDER_POST()
        if p == '/api/orders/verify':
            return self.do_ORDER_VERIFY()
        if p == '/api/visits': return self.do_VISITS_POST()
        if p == '/api/sync/queue': return self.do_SYNC_QUEUE_POST()
        # New endpoints
        if p == '/api/users':
            return self.do_USERS_POST()
        if p == '/api/stores':
            return self.do_STORE_POST()
        if p == '/api/orders/status':
            return self.do_ORDER_STATUS_POST()
        if p == '/api/orders/admin-edit':
            return self.do_ORDER_ADMIN_EDIT()
        if p == '/api/api-keys':
            return self.do_API_KEYS_POST()
        if p == '/api/admin/promos':
            return self.do_PROMOS_ADMIN_POST()
        if p == '/api/admin/products/prices' or p == '/api/admin/pricing':
            return self.do_PRODUCTS_PRICES_POST()
        if p == '/api/admin/invoices':
            return self.do_INVOICES_POST()
        if p == '/api/admin/stock-balance':
            return self.do_STOCK_BALANCE_POST()
        # Parameterized POST routes
        m = self._match_path('/api/admin/users/:id/password/reset')
        if m: return self.do_PASSWORD_RESET_ISSUE(m)
        m = self._match_path('/api/admin/users/:id/password/set')
        if m: return self.do_PASSWORD_SET(m)
        m = self._match_path('/api/stores/:uuid/contacts')
        if m: return self.do_STORE_CONTACTS_POST(m)
        return super().do_POST()

    def do_PATCH(self):
        p = self.path.split('?')[0]
        # Parameterized PATCH routes
        m = self._match_path('/api/users/:id/meta')
        if m: return self.do_USER_META_PATCH(m)
        m = self._match_path('/api/users/:id')
        if m: return self.do_USER_PATCH(m)
        m = self._match_path('/api/config/:key')
        if m: return self.do_CONFIG_KEY_PATCH(m)
        m = self._match_path('/api/products/:uuid')
        if m: return self.do_PRODUCTS_PATCH(m)
        m = self._match_path('/api/admin/promos/:id')
        if m: return self.do_PROMOS_ADMIN_PATCH(m)
        m = self._match_path('/api/stores/:uuid')
        if m: return self.do_STORE_PATCH(m)
        m = self._match_path('/api/depots/:id')
        if m: return self.do_DEPOT_PATCH(m)
        return super().do_PATCH()

    def do_DELETE(self):
        p = self.path.split('?')[0]
        m = self._match_path('/api/admin/promos/:id')
        if m: return self.do_PROMOS_ADMIN_DELETE(m)
        m = self._match_path('/api/stores/:uuid')
        if m: return self.do_STORE_DELETE(m)
        m = self._match_path('/api/users/:id')
        if m: return self.do_USER_DELETE(m)
        return super().do_DELETE()

    def log_message(self, fmt, *args):
        if len(args) >= 3:
            write_log('ACCESS', 'httpd', f'{args[0]} {args[1]} {args[2]}')
        else:
            super().log_message(fmt, *args)


write_log('INFO', 'server', 'WIM Online Server starting (PostgreSQL standalone, no Fleetbase)', {
    'port': PORT,
    'pg': f'{PG_HOST}:{PG_PORT}/{PG_DB}',
})

# Start session cleanup daemon thread
threading.Thread(target=session_cleanup, daemon=True).start()

with http.server.ThreadingHTTPServer(('0.0.0.0', PORT), WIMHandler) as httpd:
    try: httpd.serve_forever()
    except KeyboardInterrupt:
        write_log('INFO', 'server', 'Shutting down...')
        httpd.server_close()
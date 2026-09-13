#!/usr/bin/env python3
"""
WIM Fleetbase — Production Frontend Server
Serves static files + API proxy + WIM Auth (against Fleetbase users table)
"""
import http.server
import urllib.request
import urllib.error
import os, sys, json, time, threading, hashlib, secrets
import bcrypt

PORT = int(os.environ.get('PORT', 8080))
API_BASE = os.environ.get('FLEETBASE_API', 'http://localhost:8000')
DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'wim-server.log')
LOG_LOCK = threading.Lock()

# MySQL config
MYSQL_HOST = os.environ.get('WIM_MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(os.environ.get('WIM_MYSQL_PORT', '3306'))
MYSQL_DB = os.environ.get('WIM_MYSQL_DB', 'fleetbase')
MYSQL_USER = os.environ.get('WIM_MYSQL_USER', 'fleetbase')
MYSQL_PASS = os.environ.get('WIM_MYSQL_PASS', '5d75cc664ec15b65fd90aea66e3dd38e3bbbccc0')

os.makedirs(LOG_DIR, exist_ok=True)

# ── Helpers

def write_log(level, context, message, data=None):
    entry = {
        'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'level': level,
        'context': context,
        'message': message,
        'data': data if data else None,
    }
    line = json.dumps(entry, default=str)
    with LOG_LOCK:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 5*1024*1024:
            rotate = LOG_FILE + '.1'
            if os.path.exists(rotate): os.remove(rotate)
            os.rename(LOG_FILE, rotate)
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    print(f"[{entry['ts']}] [{level}] [{context}] {message}")

def generate_session_id():
    return secrets.token_hex(32)

# ── MySQL helper
def get_mysql():
    try:
        import pymysql
        conn = pymysql.connect(
            host=MYSQL_HOST, port=MYSQL_PORT, db=MYSQL_DB,
            user=MYSQL_USER, password=MYSQL_PASS, connect_timeout=5
        )
        return conn
    except Exception as e:
        write_log('ERROR', 'auth', f'MySQL connect failed: {e}')
        return None

def verify_login(email, password):
    """Verify against Fleetbase users table using bcrypt.
       Then look up api_credentials and drivers by user_uuid."""
    conn = get_mysql()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        # Look up user by email
        cur.execute(
            "SELECT id, uuid, email, name, type, password, status FROM users WHERE email=%s AND status='active' AND deleted_at IS NULL",
            (email,))
        row = cur.fetchone()

        if not row:
            write_log('WARN', 'auth', f'User not found: {email}')
            cur.close()
            conn.close()
            return None

        user_id, user_uuid, user_email, user_name, user_type, pw_hash, user_status = row

        # Verify bcrypt password
        if not pw_hash or not pw_hash.startswith('$2'):
            write_log('WARN', 'auth', f'No bcrypt password for: {email}')
            cur.close()
            conn.close()
            return None

        try:
            if not bcrypt.checkpw(password.encode(), pw_hash.encode()):
                write_log('WARN', 'auth', f'Wrong password for: {email}')
                cur.close()
                conn.close()
                return None
        except Exception as e:
            write_log('ERROR', 'auth', f'bcrypt check failed: {e}')
            cur.close()
            conn.close()
            return None

        # Get API key from api_credentials
        cur.execute(
            "SELECT `key` FROM api_credentials WHERE user_uuid=%s AND deleted_at IS NULL ORDER BY id LIMIT 1",
            (user_uuid,))
        api_row = cur.fetchone()
        api_key = api_row[0] if api_row else None

        # Get driver ID if this user is a driver
        cur.execute(
            "SELECT id FROM drivers WHERE user_uuid=%s AND deleted_at IS NULL AND status='active' LIMIT 1",
            (user_uuid,))
        driver_row = cur.fetchone()
        driver_id = driver_row[0] if driver_row else None

        cur.close()
        conn.close()

        # Map Fleetbase user type to our role
        role_map = {'admin': 'admin', 'customer': 'sales'}
        role = role_map.get(user_type, 'sales')

        write_log('INFO', 'auth', f'Login OK: {email} ({user_type})')

        return {
            'id': user_id,
            'uuid': user_uuid,
            'name': user_name or email.split('@')[0],
            'email': user_email,
            'role': role,
            'fleetbase_api_key': api_key,
            'driver_id': driver_id,
        }

    except Exception as e:
        write_log('ERROR', 'auth', f'Login query failed: {e}')
        return None

def create_session(user_id):
    conn = get_mysql()
    if not conn:
        return None
    try:
        session_id = generate_session_id()
        expires_at = time.strftime('%Y-%m-%d %H:%M:%S',
            time.localtime(time.time() + 86400 * 7))
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO wim_auth.sessions (id, user_id, expires_at) VALUES (%s, %s, %s)",
            (session_id, user_id, expires_at))
        conn.commit()
        cur.close()
        conn.close()
        return session_id
    except Exception as e:
        write_log('ERROR', 'auth', f'Create session failed: {e}')
        return None

def get_session(session_id):
    conn = get_mysql()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        # Get user info via session, using Fleetbase users table for role mapping
        cur.execute("""
            SELECT s.user_id, u.email, u.name, u.type, u.uuid
            FROM wim_auth.sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id=%s AND s.expires_at > NOW()
        """, (session_id,))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return None

        user_id, email, name, user_type, user_uuid = row

        # Get API key
        cur.execute(
            "SELECT `key` FROM api_credentials WHERE user_uuid=%s AND deleted_at IS NULL ORDER BY id LIMIT 1",
            (user_uuid,))
        api_row = cur.fetchone()
        api_key = api_row[0] if api_row else None

        # Get driver ID
        cur.execute(
            "SELECT id FROM drivers WHERE user_uuid=%s AND deleted_at IS NULL AND status='active' LIMIT 1",
            (user_uuid,))
        driver_row = cur.fetchone()
        driver_id = driver_row[0] if driver_row else None

        cur.close()
        conn.close()

        role_map = {'admin': 'admin', 'customer': 'sales'}
        role = role_map.get(user_type, 'sales')

        return {
            'id': user_id,
            'name': name or email.split('@')[0],
            'email': email,
            'role': role,
            'fleetbase_api_key': api_key,
            'driver_id': driver_id,
        }
    except Exception as e:
        write_log('ERROR', 'auth', f'Session lookup failed: {e}')
        return None

def delete_session(session_id):
    conn = get_mysql()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM wim_auth.sessions WHERE id=%s", (session_id,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        write_log('ERROR', 'auth', f'Session delete failed: {e}')

# ── HTTP Server (same as before - only auth functions changed)

class WIMHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def _send_json(self, code, obj):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept, Customer-Token')
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def _read_body(self):
        cl = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(cl) if cl else b''

    def _get_session_from_cookie(self):
        cookie_str = self.headers.get('Cookie', '')
        for part in cookie_str.split(';'):
            part = part.strip()
            if part.startswith('wim_session='):
                return part[12:]
        return None

    def do_LOGIN(self):
        body = self._read_body()
        try:
            data = json.loads(body)
        except:
            return self._send_json(400, {'error': 'Invalid JSON'})

        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''

        if not email or not password:
            return self._send_json(400, {'error': 'Email dan password diperlukan'})

        user = verify_login(email, password)
        if not user:
            return self._send_json(401, {'error': 'Email atau password salah'})

        session_id = create_session(user['id'])
        if not session_id:
            return self._send_json(500, {'error': 'Gagal membuat session'})

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        expires = time.strftime('%a, %d-%b-%Y %H:%M:%S GMT',
            time.gmtime(time.time() + 86400 * 7))
        self.send_header('Set-Cookie',
            f'wim_session={session_id}; Path=/; HttpOnly; SameSite=Lax; Expires={expires}')
        self.end_headers()
        self.wfile.write(json.dumps({
            'token': session_id,
            'user': {
                'name': user['name'],
                'email': user['email'],
                'role': user['role'],
                'driver_id': str(user['driver_id']) if user['driver_id'] else '',
            }
        }).encode())

    def do_LOGOUT(self):
        session_id = self._get_session_from_cookie()
        if session_id:
            delete_session(session_id)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Set-Cookie', 'wim_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'ok'}).encode())

    def do_SESSION(self):
        session_id = self._get_session_from_cookie()
        if not session_id:
            return self._send_json(401, {'error': 'Not authenticated'})

        user = get_session(session_id)
        if not user:
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Set-Cookie', 'wim_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Session expired'}).encode())
            return

        self._send_json(200, {
            'user': {
                'name': user['name'],
                'email': user['email'],
                'role': user['role'],
                'driver_id': str(user['driver_id']) if user['driver_id'] else '',
            }
        })

    def do_PROXY(self):
        path = self.path
        target = f"{API_BASE}{path}"
        method = self.command
        body = self._read_body() if self.command in ('POST', 'PATCH', 'PUT') else None

        headers = {}
        for k, v in self.headers.items():
            if k.lower() not in ('host', 'connection', 'transfer-encoding', 'content-length', 'cookie'):
                headers[k] = v

        # Inject API key from session
        session_id = self._get_session_from_cookie()
        if session_id:
            user = get_session(session_id)
            if user and user.get('fleetbase_api_key'):
                headers['Authorization'] = f"Bearer {user['fleetbase_api_key']}"

        write_log('INFO', 'proxy', f'{method} {path}')

        try:
            req = urllib.request.Request(target, data=body or None, headers=headers, method=method)
            resp = urllib.request.urlopen(req, timeout=30)
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                    self.send_header(k, v)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.copyfile(resp, self.wfile)
        except urllib.error.HTTPError as e:
            write_log('ERROR', 'proxy', f'{method} {path} → {e.code}')
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            write_log('ERROR', 'proxy', f'{method} {path} → 502: {e}')
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_LOG(self):
        if self.path != '/api/log':
            return self._send_json(404, {'error': 'Not found'})
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            write_log(data.get('level', 'INFO'), data.get('context', 'client'),
                      data.get('message', ''), data.get('data'))
            self._send_json(200, {'status': 'ok'})
        except:
            self._send_json(200, {'status': 'logged'})

    def do_LOGS(self):
        if self.path.split('?')[0] != '/api/logs':
            return self._send_json(404, {'error': 'Not found'})
        try:
            limit = int(self.path.split('=')[1]) if '?limit=' in self.path else 100
            entries = []
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entries.append(json.loads(line))
                            except:
                                pass
            entries.reverse()
            self._send_json(200, {'logs': entries[:limit]})
        except Exception as e:
            write_log('ERROR', 'server', 'Failed to read logs', str(e))
            self._send_json(200, {'logs': []})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept, Customer-Token')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()

    def do_GET(self):
        p = self.path.split('?')[0]
        if p.startswith('/v1/'): return self.do_PROXY()
        if p == '/api/logs': return self.do_LOGS()
        if p == '/api/auth/session': return self.do_SESSION()
        return super().do_GET()

    def do_POST(self):
        p = self.path.split('?')[0]
        if p == '/api/auth/login': return self.do_LOGIN()
        if p == '/api/auth/logout': return self.do_LOGOUT()
        if p == '/api/log': return self.do_LOG()
        if p.startswith('/v1/'): return self.do_PROXY()
        return super().do_POST()

    def do_PATCH(self):
        if self.path.startswith('/v1/'): return self.do_PROXY()
        return super().do_PATCH()

    def do_DELETE(self):
        if self.path.startswith('/v1/'): return self.do_PROXY()
        return super().do_DELETE()

    def log_message(self, fmt, *args):
        if len(args) >= 3:
            write_log('ACCESS', 'httpd', f'{args[0]} {args[1]} {args[2]}')
        else:
            super().log_message(fmt, *args)

write_log('INFO', 'server', 'WIM Frontend Server starting (Fleetbase auth sync)', {
    'port': PORT, 'api': API_BASE, 'mysql': MYSQL_HOST
})

with http.server.ThreadingHTTPServer(('0.0.0.0', PORT), WIMHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        write_log('INFO', 'server', 'Shutting down...')
        httpd.server_close()
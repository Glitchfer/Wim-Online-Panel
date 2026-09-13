#!/usr/bin/env python3
"""
WIM Online Admin Panel — Backend Server (PostgreSQL / middleware-backed)
Desktop-first admin UI for depo admin, regional managers, and head of sales.

This server is a THIN CLIENT of the WIM middleware (serve.py on the wim-mid container).
It does NOT connect to the database directly. Instead it:
  1. Authenticates users against the middleware /api/auth/login (shared wim_users).
  2. Uses a privileged service Bearer API key to query the middleware's /api/* endpoints
     for team, stores, products, visits, orders, attendance, depots.
  3. Applies RBAC (depo_admin scope) server-side before returning data.

Environment:
  ADMIN_PORT       - this server's port (default 8081, container maps to 8001)
  ADMIN_API_BASE   - middleware base URL (default http://127.0.0.1:8000)
  ADMIN_API_KEY    - privileged Bearer key for middleware /api/* (from wim_api_keys)
"""
import http.server, urllib.request, urllib.error
import os, sys, json, time, threading, secrets, datetime, math
from urllib.parse import urlparse, parse_qs, quote

PORT = int(os.environ.get('ADMIN_PORT', 8081))
DIR = os.path.dirname(os.path.abspath(__file__))

# ── Middleware connection (the only data path) ──
API_BASE = os.environ.get('ADMIN_API_BASE', 'http://127.0.0.1:8000')
API_KEY  = os.environ.get('ADMIN_API_KEY', '')

TOKENS = {}        # admin cookie token -> {id, name, email, role}
TOKEN_LOCK = threading.Lock()
ROLE_LEVEL = {'super_admin': 5, 'head_of_sales': 4, 'regional_manager': 3, 'manager': 3, 'depo_admin': 2}

# ── Logging
LOG_FILE = os.path.join(DIR, '..', 'logs', 'admin-server.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
LOG_LOCK = threading.Lock()

def write_log(level, tag, msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    with LOG_LOCK:
        with open(LOG_FILE, 'a') as f:
            f.write(f'{ts} [{level}] [{tag}] {msg}\n')

# ── Middleware HTTP client ──────────────────────────────
def _mw(method, path, body=None, cookie=None, bearer=None, timeout=20):
    """Call the middleware /api/* endpoint. Returns (status, data)."""
    url = API_BASE + path
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    if cookie: headers['Cookie'] = f'wim_session={cookie}'
    if bearer: headers['Authorization'] = f'Bearer {bearer}'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read()
        try: return r.status, json.loads(raw)
        except: return r.status, {'raw': raw.decode()[:200]}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: return e.code, json.loads(raw)
        except: return e.code, {'raw': raw.decode()[:200]}
    except Exception as e:
        return None, {'error': str(e)}

def _mw_bytes(method, path, bearer=None, timeout=30):
    """Call middleware and return (status, raw_bytes)."""
    url = API_BASE + path
    headers = {'Authorization': f'Bearer {bearer}'} if bearer else {}
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode()

def _api_key():
    """The admin service uses its privileged API key for cross-user reads.
    If none configured, falls back to empty (endpoints that need it will 401)."""
    return API_KEY

class AdminHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def _send_json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def _send_bytes(self, code, body, content_type, filename=None):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="%s"' % filename)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(length).decode('utf-8') if length > 0 else ''

    def _require_auth(self):
        cookie = self.headers.get('Cookie', '')
        token = ''
        for part in cookie.split(';'):
            part = part.strip()
            if part.startswith('wim_admin='):
                token = part[10:]
                break
        if not token:
            auth = self.headers.get('Authorization', '')
            if auth.startswith('Bearer '):
                token = auth[7:]
        with TOKEN_LOCK:
            return TOKENS.get(token)

    def _scoped(self, user, path):
        """Apply depot scoping: if the user is a depo_admin with a depot_id,
        append a depot_id filter to a middleware /api/* path. super_admin sees all."""
        role = user.get('role', '')
        depot_id = user.get('depot_id')
        write_log('DEBUG', 'scoped', f'user={user.get("email")} role={role} depot_id={depot_id} path={path}')
        if role == 'depo_admin' and depot_id:
            sep = '&' if '?' in path else '?'
            return f'{path}{sep}depot_id={depot_id}'
        return path

    def _require_role(self, min_role='depo_admin'):
        """Auth + RBAC gate. Returns user dict or None (after sending 401/403)."""
        user = self._require_auth()
        if not user:
            self._send_json(401, {'error': 'Not authenticated'})
            return None
        lvl = ROLE_LEVEL.get(user.get('role'), 0)
        min_lvl = ROLE_LEVEL.get(min_role, 0)
        if lvl < min_lvl:
            self._send_json(403, {'error': f'Need {min_role}+ role'})
            return None
        return user

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, Cookie')
        self.end_headers()

    def do_GET(self):
        p = self.path.split('?')[0]
        write_log('DEBUG', 'request', f'GET {self.path}')
        if p == '/api/admin/session': return self.do_SESSION()
        if p == '/api/admin/filter-options': return self.do_FILTER_OPTIONS()
        if p == '/api/admin/dashboard': return self.do_DASHBOARD()
        if p == '/api/admin/team': return self.do_TEAM()
        if p == '/api/admin/visits': return self.do_VISITS()
        if p == '/api/admin/orders': return self.do_ORDERS()
        if p == '/api/admin/orders/detail' or p == '/api/admin/order-detail': return self.do_ORDER_DETAIL()
        if p == '/api/admin/attendance': return self.do_ATTENDANCE()
        if p == '/api/admin/depots': return self.do_DEPOTS()
        if p == '/api/admin/today-plan': return self.do_TODAY_PLAN()
        if p == '/api/admin/plan/day' or p == '/api/admin/plan': return self.do_PLAN_DAY_GET()
        if p == '/api/admin/plan/templates': return self.do_PLAN_TEMPLATES_GET()
        if p == '/api/admin/plan/template': return self.do_PLAN_TEMPLATE_GET()
        if p == '/api/admin/wilayah': return self.do_WILAYAH()
        if p == '/api/admin/rencana/view' or p == '/api/admin/rencana': return self.do_RENCANA_VIEW()
        if p == '/api/admin/users': return self.do_USERS()
        if p == '/api/admin/products/prices' or p == '/api/admin/pricing': return self.do_PRODUCTS_PRICES()
        if p == '/api/admin/products': return self.do_PRODUCTS()
        if p == '/api/admin/stores': return self.do_STORES()
        if p == '/api/admin/stock': return self.do_STOCK()
        if p == '/api/admin/positions/all' or p == '/api/admin/positions': return self.do_POSITIONS_ALL()
        if p == '/api/admin/route-map' or p == '/api/admin/route': return self.do_ROUTE_MAP()
        if p == '/api/admin/promos': return self.do_PROMOS_ADMIN()
        if p == '/api/admin/stores/orders' or p == '/api/admin/store-orders': return self.do_STORE_ORDERS()
        if p == '/api/admin/analytics/recap': return self.do_ANALYTICS_RECAP()
        if p == '/api/admin/analytics/gallery': return self.do_ANALYTICS_GALLERY()
        if p == '/api/admin/analytics/order-stock': return self.do_ANALYTICS_ORDER_STOCK()
        if p == '/api/admin/analytics/packing-list': return self.do_ANALYTICS_PACKING_LIST()
        if p == '/api/admin/analytics/packing-grouped': return self.do_ANALYTICS_PACKING_GROUPED()
        if p == '/api/admin/analytics/packing-luarrute': return self.do_ANALYTICS_PACKING_LUARRUTE()
        if p == '/api/admin/analytics/packing-day-orders': return self.do_ANALYTICS_PACKING_DAY_ORDERS()
        if p == '/api/admin/analytics/packing-surat-jalan': return self.do_ANALYTICS_PACKING_SURAT_JALAN()
        if p == '/api/admin/analytics/packing-invoice-zip': return self.do_ANALYTICS_PACKING_INVOICE_ZIP()
        if p == '/api/admin/analytics/sales-performance': return self.do_ANALYTICS_PERFORMANCE()
        if p == '/api/admin/analytics/store-orders': return self.do_ANALYTICS_STORE_ORDERS()
        if p == '/api/admin/invoices': return self.do_INVOICES()
        if p == '/api/admin/stock-balance': return self.do_STOCK_BALANCE()
        m = self._match_path_simple('/api/admin/promos/:id')
        if m: return self.do_PROMOS_ADMIN_DETAIL()
        return super().do_GET()

    def do_POST(self):
        p = self.path.split('?')[0]
        m = self._match_path_simple('/api/admin/users/:id/password/reset')
        if m: return self.do_PASSWORD_RESET_ISSUE()
        m = self._match_path_simple('/api/admin/users/:id/password/set')
        if m: return self.do_PASSWORD_SET()
        if p == '/api/admin/login': return self.do_LOGIN_POST()
        if p == '/api/admin/logout': return self.do_LOGOUT()
        if p == '/api/admin/plan/day' or p == '/api/admin/plan': return self.do_PLAN_DAY_POST()
        if p == '/api/admin/plan/template': return self.do_PLAN_TEMPLATE_POST()
        if p == '/api/admin/plan/template/resolve': return self.do_PLAN_TEMPLATE_RESOLVE()
        if p == '/api/admin/users': return self.do_USERS_POST()
        if p == '/api/admin/orders/status': return self.do_ORDER_STATUS_POST()
        if p == '/api/admin/orders/admin-edit': return self.do_ORDER_ADMIN_EDIT()
        if p == '/api/admin/products/prices' or p == '/api/admin/pricing': return self.do_PRODUCTS_PRICES_POST()
        if p == '/api/admin/products': return self.do_PRODUCTS_POST()
        if p == '/api/admin/promos': return self.do_PROMOS_ADMIN_POST()
        if p == '/api/admin/stores': return self.do_STORES_POST()
        if p == '/api/admin/depots': return self.do_DEPOTS_POST()
        if p == '/api/admin/invoices': return self.do_INVOICES_POST()
        if p == '/api/admin/stock-balance': return self.do_STOCK_BALANCE_POST()

    def do_PATCH(self):
        p = self.path.split('?')[0]
        if p.startswith('/api/admin/products/'):
            return self.do_PRODUCTS_PATCH()
        m = self._match_path_simple('/api/admin/promos/:id')
        if m: return self.do_PROMOS_ADMIN_PATCH()
        if p.startswith('/api/admin/stores/'):
            return self.do_STORES_PATCH()
        if p.startswith('/api/admin/depots/'):
            return self.do_DEPOT_PATCH()
        m = self._match_path_simple('/api/admin/users/:id')
        if m: return self.do_USERS_PATCH()
        return self._send_json(404, {'error': 'Not found'})

    def do_DELETE(self):
        p = self.path.split('?')[0]
        m = self._match_path_simple('/api/admin/promos/:id')
        if m: return self.do_PROMOS_ADMIN_DELETE()
        m = self._match_path_simple('/api/admin/stores/:uuid')
        if m: return self.do_STORES_DELETE()
        m = self._match_path_simple('/api/admin/users/:id')
        if m: return self.do_USERS_DELETE()
        return super().do_DELETE()

    # ── Login: verify against MIDDLEWARE (shared wim_users) ──
    def do_LOGIN_POST(self):
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
        except: return self._send_json(400, {'error': 'Invalid JSON'})
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        # Authenticate with the middleware
        status, d = _mw('POST', '/api/auth/login', {'email': email, 'password': password}, bearer=_api_key())
        if status != 200 or not isinstance(d, dict) or not d.get('token'):
            return self._send_json(401, {'error': d.get('error', 'Email atau password salah')})
        u = d.get('user', {})
        # Only admin-class roles can use the admin panel
        role = u.get('role', '')
        if role not in ROLE_LEVEL:
            return self._send_json(403, {'error': 'Akun ini tidak memiliki akses admin'})
        token = secrets.token_hex(16)
        # Resolve depot_id for depo_admin scoping (login response omits user id; look up by email)
        depot_id = None
        if role == 'depo_admin':
            _, ud = _mw('GET', f"/api/users?email={urllib.parse.quote(email)}", bearer=_api_key())
            matches = ud.get('data', ud.get('users', [])) if isinstance(ud, dict) else []
            matches = matches if isinstance(matches, list) else []
            for m in matches:
                if m.get('email') == email:
                    depot_id = m.get('depot_id')
                    if not depot_id and m.get('depot_ids'):
                        depot_id = m['depot_ids'][0] if isinstance(m['depot_ids'], list) and m['depot_ids'] else None
                    break
        with TOKEN_LOCK:
            TOKENS[token] = {'id': u.get('id'), 'uuid': u.get('uuid'), 'name': u.get('name', email),
                             'email': email, 'role': role, 'depot_id': depot_id}
        write_log('INFO', 'login', f'Admin login: {email} role={role}')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Set-Cookie', f'wim_admin={token}; Path=/; HttpOnly; SameSite=Lax')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(json.dumps({'token': token, 'user': {'name': u.get('name'), 'email': email, 'role': role}}, ensure_ascii=False).encode())

    def do_LOGOUT(self):
        cookie = self.headers.get('Cookie', '')
        for part in cookie.split(';'):
            part = part.strip()
            if part.startswith('wim_admin='):
                token = part[10:]
                with TOKEN_LOCK: TOKENS.pop(token, None)
                break
        self.send_response(200)
        self.send_header('Set-Cookie', 'wim_admin=; Path=/; Max-Age=0; HttpOnly')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_SESSION(self):
        user = self._require_auth()
        if not user: return self._send_json(401, {'error': 'Not authenticated'})
        self._send_json(200, {'user': {'name': user['name'], 'email': user['email'], 'role': user.get('role','')}})

    # ── Dashboard KPIs (from middleware) ──
    def do_DASHBOARD(self):
        user = self._require_role('depo_admin')
        if not user: return
        today = time.strftime('%Y-%m-%d')
        # Fetch from middleware (bearer = admin service key for cross-user reads)
        st, d = _mw('GET', '/api/dashboard', bearer=_api_key())
        rep_st, reps = _mw('GET', '/api/users?role=sales', bearer=_api_key())
        team = reps.get('data', reps.get('users', [])) if isinstance(reps, dict) else []
        total_staff = len(team) if isinstance(team, list) else 0
        attended = d.get('attendance', 0) if isinstance(d, dict) else 0
        visits_today = d.get('visitsToday', 0) if isinstance(d, dict) else 0
        orders_today = d.get('orders', 0) if isinstance(d, dict) else 0
        plan = d.get('plan', {}) if isinstance(d, dict) else {}
        stores_planned = plan.get('total', 0) if isinstance(plan, dict) else 0
        stores_visited = d.get('storesVisited', plan.get('visited', 0)) if isinstance(d, dict) else 0
        completion = round(stores_visited / stores_planned * 100) if stores_planned else 0
        # Geofence compliance (from attendance)
        att_st, att_d = _mw('GET', f'/api/absensi?date={today}', bearer=_api_key())
        gf_total = gf_ok = 0
        att_list = att_d.get('records', att_d.get('data', [])) if isinstance(att_d, dict) else []
        if isinstance(att_list, list):
            for a in att_list:
                if a.get('geofenceStatus'):
                    gf_total += 1
                    if a.get('geofenceStatus') == 'in_depot': gf_ok += 1
        gf_pct = round(gf_ok/gf_total*100) if gf_total else 0
        self._send_json(200, {
            'totalStaff': total_staff, 'attendedToday': attended,
            'visitsToday': visits_today, 'ordersToday': orders_today,
            'geofenceCompliancePct': gf_pct, 'storesPlanned': stores_planned,
            'storesVisited': stores_visited, 'completionPct': completion,
            'role': user['role'],
        })

    # ── Team overview (sales reps) ──
    def do_TEAM(self):
        user = self._require_role('depo_admin')
        if not user: return
        today = time.strftime('%Y-%m-%d')
        st, d = _mw('GET', self._scoped(user, '/api/users?role=sales'), bearer=_api_key())
        team = d.get('data', d.get('users', [])) if isinstance(d, dict) else []
        team = team if isinstance(team, list) else []
        members = []
        for u in team:
            uid = u.get('id')
            att_st, att = _mw('GET', f'/api/absensi?date={today}&user_id={uid}', bearer=_api_key())
            att_record = None
            alist = att.get('records', att.get('data', [])) if isinstance(att, dict) else []
            if isinstance(alist, list) and alist: att_record = alist[0]
            members.append({
                'id': uid, 'name': u.get('name'), 'email': u.get('email',''),
                'clockIn': att_record.get('clockIn') if att_record else None,
                'clockOut': att_record.get('clockOut') if att_record else None,
                'geofenceStatus': att_record.get('geofenceStatus','') if att_record else '',
                'visitsToday': 0, 'depot': '',
            })
        self._send_json(200, {'members': members, 'total': len(members)})

    def do_POSITIONS_ALL(self):
        user = self._require_role('depo_admin')
        if not user: return
        st, d = _mw('GET', '/api/positions/all', bearer=_api_key())
        if isinstance(d, dict):
            self._send_json(st if st else 500, d)
        else:
            self._send_json(st if st else 500, {'error': str(d)})

    def do_ROUTE_MAP(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        date = (qs.get('date') or [''])[0][:10]
        path = '/api/admin/route-map' + (f'?date={quote(date)}' if date else '')
        st, d = _mw('GET', path, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_FILTER_OPTIONS(self):
        """Dropdown sources for report filters: sales users, depots, regions."""
        user = self._require_role('depo_admin')
        if not user: return
        st, d = _mw('GET', '/api/filter-options', bearer=_api_key())
        data = d if isinstance(d, dict) else {}
        self._send_json(200, {
            'users': data.get('users', []), 'depots': data.get('depots', []),
            'regions': data.get('regions', []),
        })

    def _match_path_simple(self, pattern):
        """Match /api/admin/promos/:id returning {'id': 'X'} or None."""
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

    def _report_query(self, allowed=('date','date_from','date_to','user_id','depot_id','region_id')):
        """Build the filter query string from the incoming request query params."""
        qs = parse_qs(urlparse(self.path).query)
        parts = []
        for k in allowed:
            v = (qs.get(k) or [''])[0].strip()
            if v:
                parts.append(f'{k}={urllib.parse.quote(v)}')
        return ('?' + '&'.join(parts)) if parts else ''

    # ── Visit log ──
    def do_VISITS(self):
        user = self._require_role('depo_admin')
        if not user: return
        if user.get('depot_id') and 'depot_id' not in self._report_query():
            qs = self._report_query() + (f"&depot_id={user['depot_id']}" if self._report_query() else f"?depot_id={user['depot_id']}")
        else:
            qs = self._report_query()
        path = f'/api/visits{qs}'
        st, d = _mw('GET', path, bearer=_api_key())
        visits = d.get('visits', d.get('data', [])) if isinstance(d, dict) else []
        visits = visits if isinstance(visits, list) else []
        out = [{
            'id': v.get('id'), 'userId': v.get('user_id') or v.get('userId'),
            'userName': v.get('user_name', v.get('userName', '')),
            'storeName': v.get('placeName', v.get('place_name','')),
            'checkinAt': str(v.get('checkinAt', v.get('checkin_at') or '')),
            'checkoutAt': str(v.get('checkoutAt', v.get('checkout_at') or '')),
            'duration': v.get('durationSeconds', v.get('duration_seconds')),
            'status': v.get('status'), 'lat': v.get('lat', v.get('location_lat')),
            'lng': v.get('lng', v.get('location_lng')),
            'source': v.get('source'),
            'userDepotName': v.get('userDepotName', v.get('user_depot_name','')),
            'regionName': v.get('regionName', v.get('region_name','')),
        } for v in visits]
        self._send_json(200, {'visits': out, 'total': len(out)})

    # ── Order history ──
    def do_ORDERS(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        # map admin's from/to to middleware date_from/date_to
        date_from = (qs.get('from') or qs.get('date_from') or [''])[0].strip()
        date_to = (qs.get('to') or qs.get('date_to') or [''])[0].strip()
        user_id = (qs.get('user_id') or [''])[0].strip()
        depot_id = (qs.get('depot_id') or [''])[0].strip()
        region_id = (qs.get('region_id') or [''])[0].strip()
        status = (qs.get('status') or [''])[0].strip().lower()
        off_route = (qs.get('off_route') or [''])[0].strip().lower() in ('1','true','yes')
        if not date_from and not date_to:
            date_from = time.strftime('%Y-%m-01'); date_to = time.strftime('%Y-%m-%d')
        mw_qs = [f'date_from={date_from}', f'date_to={date_to}']
        if user_id: mw_qs.append(f'user_id={urllib.parse.quote(user_id)}')
        if depot_id: mw_qs.append(f'depot_id={urllib.parse.quote(depot_id)}')
        elif user.get('depot_id'): mw_qs.append(f"depot_id={user['depot_id']}")
        if region_id: mw_qs.append(f'region_id={urllib.parse.quote(region_id)}')
        if status: mw_qs.append(f'status={urllib.parse.quote(status)}')
        if off_route: mw_qs.append('off_route=1')
        st, d = _mw('GET', '/api/orders?' + '&'.join(mw_qs), bearer=_api_key())
        orders = d.get('orders', d.get('data', [])) if isinstance(d, dict) else []
        orders = orders if isinstance(orders, list) else []
        out = [{
            'id': o.get('orderId') or o.get('order_ref') or o.get('uuid','')[:12],
            'uuid': o.get('uuid',''),
            'driverName': o.get('user_name', o.get('userName', '')),
            'storeName': o.get('storeName', o.get('store_name', '')),
            'status': o.get('status',''),
            'itemCount': o.get('itemCount', 0),
            'grandTotal': o.get('grandTotal', o.get('total', 0)),
            'promos': o.get('promosApplied', []),
            'bonusQty': o.get('bonusQty', 0),
            'paymentMethod': o.get('paymentMethod', ''),
            'offRouteType': o.get('offRouteType', ''),
            'createdAt': str(o.get('createdAt', '')),
            'userDepotName': o.get('userDepotName', o.get('user_depot_name','')),
            'regionName': o.get('regionName', o.get('region_name','')),
        } for o in orders]
        self._send_json(200, {'orders': out, 'total': len(out)})

    def do_ORDER_DETAIL(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        order_uuid = (qs.get('uuid') or [''])[0].strip()
        if not order_uuid:
            return self._send_json(400, {'error': 'uuid diperlukan'})
        # Use the public confirmation endpoint so the admin modal shows the same
        # invoice/order-confirmation shape the store scans via QR.
        st, d = _mw('GET', f'/api/orders/public?uuid={quote(order_uuid)}', bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── Attendance log ──
    def do_ATTENDANCE(self):
        user = self._require_role('depo_admin')
        if not user: return
        if user.get('depot_id') and 'depot_id' not in self._report_query():
            qs = self._report_query() + (f"&depot_id={user['depot_id']}" if self._report_query() else f"?depot_id={user['depot_id']}")
        else:
            qs = self._report_query()
        st, d = _mw('GET', f'/api/absensi{qs}', bearer=_api_key())
        records = d.get('records', d.get('data', [])) if isinstance(d, dict) else []
        records = records if isinstance(records, list) else []
        out = [{
            'userId': r.get('user_id'), 'name': r.get('name', r.get('user_name','')),
            'clockIn': r.get('clockIn'), 'clockOut': r.get('clockOut'),
            'duration': r.get('duration'), 'geofenceStatus': r.get('geofenceStatus',''),
            'depotName': r.get('depotName', r.get('depot_name', r.get('userDepotName',''))),
            'regionName': r.get('regionName', r.get('region_name','')),
            'lat': r.get('lat'), 'lng': r.get('lng'),
        } for r in records]
        self._send_json(200, {'records': out, 'total': len(out)})

    # ── Depots ──
    def do_DEPOTS(self):
        user = self._require_role('depo_admin')
        if not user: return
        st, d = _mw('GET', '/api/depots', bearer=_api_key())
        depots = d.get('depots', []) if isinstance(d, dict) else []
        depots = depots if isinstance(depots, list) else []
        out = [{'id': dep.get('id'), 'name': dep.get('name'), 'address': dep.get('address',''),
                'kodeDepo': dep.get('kodeDepo', ''), 'regionId': dep.get('regionId'),
                'lat': dep.get('lat'), 'lng': dep.get('lng'), 'radiusM': dep.get('radiusM')} for dep in depots]
        self._send_json(200, {'depots': out})

    def do_DEPOTS_POST(self):
        """Create a depot. super_admin/admin only. Proxies POST /api/depots."""
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/depots', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_DEPOT_PATCH(self):
        """Edit a depot (name/address/coords/radius/region). Admin only. Proxies PATCH /api/depots/:id."""
        user = self._require_role('depo_admin')
        if not user: return
        dep_id = self.path.split('?')[0].rstrip('/').split('/')[-1]
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('PATCH', f'/api/depots/{dep_id}', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── Today's visit plan ──
    def do_TODAY_PLAN(self):
        user = self._require_role('depo_admin')
        if not user: return
        today = time.strftime('%Y-%m-%d')
        if user.get('depot_id') and 'depot_id' not in self._report_query():
            qs = self._report_query() + (f"&depot_id={user['depot_id']}" if self._report_query() else f"?depot_id={user['depot_id']}")
        else:
            qs = self._report_query()
        if 'date' not in qs and 'date_from' not in qs and 'date_to' not in qs:
            # default to today's plan; if a period is given, use it
            if not qs:
                qs = f'?date={today}'
        st, d = _mw('GET', f'/api/visit_plan{qs}', bearer=_api_key())
        plans = d.get('plans', []) if isinstance(d, dict) else []
        plans = plans if isinstance(plans, list) else []
        out = [{
            'planId': pl.get('id'), 'userId': pl.get('userId'),
            'userName': pl.get('userName', ''),
            'storeName': pl.get('storeName', ''),
            'address': pl.get('address', ''),
            'source': pl.get('source', ''), 'status': pl.get('status', ''),
            'visitDate': pl.get('visitDate', ''),
            'userDepotName': pl.get('userDepotName', ''),
            'regionName': pl.get('regionName', ''),
            'lat': pl.get('lat'), 'lng': pl.get('lng'),
        } for pl in plans]
        self._send_json(200, {'plans': out, 'total': len(out)})

    def do_PLAN_DAY_GET(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get('user_id') or [''])[0]
        date = (qs.get('date') or [''])[0][:10]
        region = (qs.get('region_id') or [''])[0].strip()
        q = (qs.get('q') or [''])[0][:100]
        parts = []
        if uid: parts.append(f'user_id={quote(uid)}')
        if date: parts.append(f'date={quote(date)}')
        if region: parts.append(f'region_id={quote(region)}')
        if q: parts.append(f'q={quote(q)}')
        path = '/api/admin/plan/day' + (('?' + '&'.join(parts)) if parts else '')
        st, d = _mw('GET', path, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PLAN_DAY_POST(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/admin/plan/day', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PLAN_TEMPLATES_GET(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get('user_id') or [''])[0]
        path = '/api/admin/plan/templates' + (('?user_id=' + quote(uid)) if uid else '')
        st, d = _mw('GET', path, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PLAN_TEMPLATE_GET(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        uid = (qs.get('user_id') or [''])[0]
        week = (qs.get('week') or [''])[0]
        day = (qs.get('day') or [''])[0]
        parts = []
        if uid: parts.append('user_id='+quote(uid))
        if week: parts.append('week='+quote(week))
        if day: parts.append('day='+quote(day))
        path = '/api/admin/plan/template' + (('?' + '&'.join(parts)) if parts else '')
        st, d = _mw('GET', path, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PLAN_TEMPLATE_POST(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/admin/plan/template', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PLAN_TEMPLATE_RESOLVE(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/admin/plan/template/resolve', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_WILAYAH(self):
        """GET /api/admin/wilayah — proxy to middleware /api/wilayah (admin session)."""
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        level = (qs.get('level') or [''])[0]
        parent = (qs.get('parent') or [''])[0]
        q = (qs.get('q') or [''])[0]
        parts = []
        if level: parts.append('level='+quote(level))
        if parent: parts.append('parent='+quote(parent))
        if q: parts.append('q='+quote(q))
        path = '/api/wilayah' + (('?' + '&'.join(parts)) if parts else '')
        st, d = _mw('GET', path, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_RENCANA_VIEW(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        date = (qs.get('date') or [''])[0][:10]
        user_filter = (qs.get('user_id') or [''])[0].strip()
        region = (qs.get('region_id') or [''])[0].strip()
        part = '?'
        if date: part += f'date={quote(date)}'
        if user_filter: part += f'&user_id={quote(user_filter)}'
        if region: part += f'&region_id={quote(region)}'
        path = '/api/admin/rencana/view' + (part if part != '?' else '')
        st, d = _mw('GET', path, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── User management (Task C: ex-Fleetbase user mgmt) ──
    def do_USERS(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        role = (qs.get('role') or [''])[0]
        jenis = (qs.get('jenis_sales') or [''])[0]
        status = (qs.get('status') or [''])[0]
        depot_id = (qs.get('depot_id') or [''])[0]
        parts = []
        if role: parts.append(f'role={quote(role)}')
        if jenis: parts.append(f'jenis_sales={quote(jenis)}')
        if status: parts.append(f'status={quote(status)}')
        if depot_id: parts.append(f'depot_id={quote(depot_id)}')
        path = '/api/users' + ('?' + '&'.join(parts) if parts else '')
        st, d = _mw('GET', self._scoped(user, path), bearer=_api_key())
        data = d.get('data', d.get('users', [])) if isinstance(d, dict) else []
        data = data if isinstance(data, list) else []
        out = [{
            'id': u.get('id'), 'uuid': u.get('uuid'), 'email': u.get('email'),
            'name': u.get('name', ''), 'role': u.get('role', ''),
            'phone': u.get('phone', ''), 'status': u.get('status', ''),
            'jenis_sales': u.get('jenis_sales', ''), 'depot_id': u.get('depot_id'),
            'depot_name': u.get('depot_name', ''),
            'nik': u.get('nik', ''), 'npwp': u.get('npwp', ''),
            'npwp_name': u.get('npwp_name', ''), 'kendaraan': u.get('kendaraan', ''),
            'kode_pos': u.get('kode_pos', ''), 'kelurahan': u.get('kelurahan', ''),
            'kecamatan': u.get('kecamatan', ''),
        } for u in data]
        self._send_json(200, {'users': out, 'total': len(out)})

    def do_USERS_PATCH(self):
        """PATCH /api/admin/users/:id — edit a user (admin). Proxies middleware PATCH /api/users/:id."""
        user = self._require_role('depo_admin')
        if not user: return
        uuid = self.path.split('?')[0].rstrip('/').split('/')[-1]
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('PATCH', f'/api/users/{uuid}', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PASSWORD_RESET_ISSUE(self):
        """POST /api/admin/users/:id/password/reset — admin issues a reset link.
        Proxies middleware POST /api/admin/users/:id/password/reset."""
        user = self._require_role('depo_admin')
        if not user: return
        parts = self.path.split('?')[0].rstrip('/').split('/')
        uid = parts[-3]  # /api/admin/users/<id>/password/reset
        st, d = _mw('POST', f'/api/admin/users/{uid}/password/reset', bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PASSWORD_SET(self):
        """POST /api/admin/users/:id/password/set — admin sets a temp password directly."""
        user = self._require_role('depo_admin')
        if not user: return
        parts = self.path.split('?')[0].rstrip('/').split('/')
        uid = parts[-3]
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', f'/api/admin/users/{uid}/password/set', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_USERS_DELETE(self):
        """DELETE /api/admin/users/:id — soft-delete a user (deleted_at). Requires super_admin."""
        user = self._require_role('super_admin')
        if not user: return
        uid = self.path.split('?')[0].rstrip('/').split('/')[-1]
        st, d = _mw('DELETE', f'/api/users/{uid}', bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_USERS_POST(self):
        """Create a user (only super_admin can). Proxies middleware POST /api/users."""
        user = self._require_role('super_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/users', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── Product / price management (Task C) ──
    def do_PRODUCTS(self):
        user = self._require_role('depo_admin')
        if not user: return
        st, d = _mw('GET', '/api/products', bearer=_api_key())
        products = d.get('products', []) if isinstance(d, dict) else []
        products = products if isinstance(products, list) else []
        out = [{
            'uuid': p.get('uuid'), 'sku': p.get('sku'), 'name': p.get('name'),
            'brand': p.get('brand', ''), 'category': p.get('category', ''),
            'unit': p.get('unit', ''), 'price': p.get('price'),
            'description': p.get('description', ''), 'weight': p.get('weight'),
            'weightUnit': p.get('weightUnit', 'pcs'), 'qtyPerUnit': p.get('qtyPerUnit', 1),
            'image': p.get('image', ''),
        } for p in products]
        self._send_json(200, {'products': out, 'total': len(out), 'brands': d.get('brands', []) if isinstance(d, dict) else []})

    def do_PRODUCTS_PRICES(self):
        user = self._require_role('depo_admin')
        if not user: return
        st, d = _mw('GET', '/api/admin/products/prices', bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PRODUCTS_PRICES_POST(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/admin/products/prices', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PRODUCTS_POST(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/products', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PRODUCTS_PATCH(self):
        """Update a product (details/pricing/image). Admin only. Proxies PATCH /api/products/:uuid."""
        user = self._require_role('depo_admin')
        if not user: return
        uuid = self.path.split('?')[0].rstrip('/').split('/')[-1]
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('PATCH', f'/api/products/{uuid}', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── Promo management (admin, super_admin) ──
    def do_PROMOS_ADMIN(self):
        user = self._require_role('depo_admin')
        if not user: return
        m = self._match_path_simple('/api/admin/promos')
        st, d = _mw('GET', '/api/admin/promos', bearer=_api_key())
        promos = d.get('promos', []) if isinstance(d, dict) else []
        self._send_json(200, {'promos': promos, 'total': len(promos)})

    def do_PROMOS_ADMIN_DETAIL(self):
        user = self._require_role('depo_admin')
        if not user: return
        m = self._match_path_simple('/api/admin/promos/:id')
        pid = m.get('id') if m else ''
        st, d = _mw('GET', '/api/admin/promos', bearer=_api_key())
        promos = d.get('promos', []) if isinstance(d, dict) else []
        found = next((p for p in promos if str(p.get('id')) == str(pid)), None)
        if not found:
            return self._send_json(404, {'error': 'Promo tidak ditemukan'})
        self._send_json(200, {'promo': found})

    def do_PROMOS_ADMIN_POST(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/admin/promos', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PROMOS_ADMIN_PATCH(self):
        user = self._require_role('depo_admin')
        if not user: return
        m = self._match_path_simple('/api/admin/promos/:id')
        pid = m.get('id') if m else ''
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('PATCH', f'/api/admin/promos/{pid}', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_PROMOS_ADMIN_DELETE(self):
        user = self._require_role('depo_admin')
        if not user: return
        m = self._match_path_simple('/api/admin/promos/:id')
        pid = m.get('id') if m else ''
        st, d = _mw('DELETE', f'/api/admin/promos/{pid}', bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── Stores (for maps / routes) ──
    def do_STORES(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        q = (qs.get('q') or [''])[0].strip()
        page = (qs.get('page') or ['1'])[0]
        per_page = (qs.get('per_page') or ['100'])[0]
        chan = (qs.get('chan') or [''])[0].strip()
        stat = (qs.get('status') or [''])[0].strip()
        path = '/api/stores/all'
        parts = []
        if q: parts.append(f'q={urllib.parse.quote(q)}')
        if chan: parts.append(f'chan={urllib.parse.quote(chan)}')
        if stat: parts.append(f'status={urllib.parse.quote(stat)}')
        parts.append(f'page={urllib.parse.quote(page)}')
        parts.append(f'per_page={urllib.parse.quote(per_page)}')
        st, d = _mw('GET', path + '?' + '&'.join(parts), bearer=_api_key())
        stores = d.get('stores', []) if isinstance(d, dict) else []
        stores = stores if isinstance(stores, list) else []
        out = [{
            'uuid': s.get('uuid'), 'name': s.get('name', ''),
            'address': s.get('address', ''), 'city': s.get('city', ''),
            'lat': s.get('latitude'), 'lng': s.get('longitude'),
            'latitude': s.get('latitude'), 'longitude': s.get('longitude'),
            'phone': s.get('phone', ''),
            'owner_name': s.get('owner_name', ''), 'channel': s.get('channel', ''),
            'category': s.get('category', ''), 'status': s.get('status', 'active'),
            'assigned_salesperson_id': s.get('assigned_salesperson_id'), 'credit_limit': s.get('credit_limit'),
            'kecamatan': s.get('kecamatan', ''), 'kelurahan': s.get('kelurahan', ''),
            'kode_pos': s.get('kode_pos', ''), 'province': s.get('province', ''),
            'kendaraan': s.get('kendaraan', ''), 'nik': s.get('nik', ''),
            'npwp': s.get('npwp', ''), 'npwp_name': s.get('npwp_name', ''),
            'geofence_radius_m': s.get('geofence_radius_m'),
        } for s in stores]
        self._send_json(200, {'stores': out, 'total': d.get('total', len(out)) if isinstance(d, dict) else len(out)})

    def do_STORES_PATCH(self):
        user = self._require_role('depo_admin')
        if not user: return
        uuid = self.path.split('?')[0].rstrip('/').split('/')[-1]
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('PATCH', f'/api/stores/{uuid}', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_STORES_POST(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/stores', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_STORES_DELETE(self):
        user = self._require_role('depo_admin')
        if not user: return
        uuid = self.path.split('?')[0].rstrip('/').split('/')[-1]
        st, d = _mw('DELETE', f'/api/stores/{uuid}', bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── Stock checks ──
    def do_STOCK(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        place = (qs.get('place_uuid') or [''])[0].strip()
        path = '/api/stock' + (f'?place_uuid={quote(place)}' if place else '')
        st, d = _mw('GET', path, bearer=_api_key())
        stock = d.get('stock', d.get('data', [])) if isinstance(d, dict) else []
        stock = stock if isinstance(stock, list) else []
        self._send_json(200, {'stock': stock, 'total': len(stock)})

    # ── Post-review additive proxies (invoices + stock-balance) ──
    def do_INVOICES(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = self._report_query(('date_from','date_to','status'))
        st, d = _mw('GET', '/api/admin/invoices' + qs, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_INVOICES_POST(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict): return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/admin/invoices', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_STOCK_BALANCE(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        dep = (qs.get('depot_id') or [''])[0].strip()
        low = (qs.get('low_only') or [''])[0].strip().lower() in ('1','true','yes')
        parts = []
        if dep: parts.append(f'depot_id={quote(dep)}')
        if low: parts.append('low_only=1')
        st, d = _mw('GET', '/api/admin/stock-balance' + (('?' + '&'.join(parts)) if parts else ''), bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_STOCK_BALANCE_POST(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict): return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/admin/stock-balance', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    def do_STORE_ORDERS(self):
        user = self._require_role('depo_admin')
        if not user: return
        qs = parse_qs(urlparse(self.path).query)
        place = (qs.get('place_uuid') or [''])[0].strip()
        path = '/api/stores/orders' + (f'?place_uuid={quote(place)}' if place else '')
        st, d = _mw('GET', path, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── Order status update (Task C: order mgmt) ──
    def do_ORDER_STATUS_POST(self):
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/orders/status', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── Order edit (Edit Order feature) proxy ──
    def do_ORDER_ADMIN_EDIT(self):
        """Adjust ordered qty / unit price of an order. depo_admin+ only.
        Proxies middleware POST /api/orders/admin-edit, which recomputes the
        order total from non-bonus line items and logs the edit."""
        user = self._require_role('depo_admin')
        if not user: return
        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                return self._send_json(400, {'error': 'Invalid JSON'})
        except Exception as e:
            return self._send_json(400, {'error': f'Invalid request: {e}'})
        st, d = _mw('POST', '/api/orders/admin-edit', data, bearer=_api_key())
        self._send_json(st if st else 500, d if isinstance(d, dict) else {'error': str(d)})

    # ── Analytics report proxies (mirror GooVi/KlikOrder admin tables) ──
    def _analytics(self, path, filters=('date_from','date_to','user_id','depot_id','region_id')):
        user = self._require_role('depo_admin')
        if not user: return None
        qs = self._report_query(filters)
        mid_path = path + qs
        st, d = _mw('GET', self._scoped(user, mid_path), bearer=_api_key())
        return d if isinstance(d, dict) else {}

    def do_ANALYTICS_RECAP(self):
        d = self._analytics('/api/analytics/recap')
        self._send_json(200, d if d is not None else {'rows': [], 'total': 0})

    def do_ANALYTICS_GALLERY(self):
        d = self._analytics('/api/analytics/gallery')
        self._send_json(200, d if d is not None else {'rows': [], 'total': 0})

    def do_ANALYTICS_ORDER_STOCK(self):
        d = self._analytics('/api/analytics/order-stock')
        self._send_json(200, d if d is not None else {'rows': [], 'total': 0})

    def do_ANALYTICS_PACKING_LIST(self):
        d = self._analytics('/api/analytics/packing-list')
        self._send_json(200, d if d is not None else {'rows': [], 'total': 0})

    def do_ANALYTICS_PACKING_GROUPED(self):
        d = self._analytics('/api/analytics/packing-grouped')
        self._send_json(200, d if d is not None else {'rows': [], 'total': 0})

    def do_ANALYTICS_PACKING_LUARRUTE(self):
        d = self._analytics('/api/analytics/packing-luarrute')
        self._send_json(200, d if d is not None else {'rows': [], 'total': 0})

    def do_ANALYTICS_PACKING_DAY_ORDERS(self):
        d = self._analytics('/api/analytics/packing-day-orders', filters=('user_id','date','luar_rute'))
        self._send_json(200, d if d is not None else {'rows': []})

    def _forward_binary(self, path, ctype, name_prefix):
        user = self._require_role('depo_admin')
        if not user:
            self._send_json(401, {'error': 'Not authenticated'})
            return
        qs = self._report_query(('user_id','date'))
        st, body = _mw_bytes('GET', path + qs, bearer=_api_key())
        if st != 200:
            self._send_json(st or 500, {'error': body.decode(errors='replace')[:300]})
            return
        import time as _t
        filename = '%s-%s.%s' % (name_prefix, _t.strftime('%Y%m%d'), 'pdf' if 'pdf' in ctype else 'zip')
        self._send_bytes(200, body, ctype, filename)

    def do_ANALYTICS_PACKING_SURAT_JALAN(self):
        self._forward_binary('/api/analytics/packing-surat-jalan', 'application/pdf', 'surat-jalan')

    def do_ANALYTICS_PACKING_INVOICE_ZIP(self):
        self._forward_binary('/api/analytics/packing-invoice-zip', 'application/zip', 'invoices')

    def do_ANALYTICS_PERFORMANCE(self):
        d = self._analytics('/api/analytics/sales-performance')
        self._send_json(200, d if d is not None else {'rows': [], 'total': 0})

    def do_ANALYTICS_STORE_ORDERS(self):
        d = self._analytics('/api/analytics/store-orders')
        self._send_json(200, d if d is not None else {'rows': [], 'total': 0})

if __name__ == '__main__':
    write_log('INFO', 'startup', f'Admin server starting on port {PORT} (middleware={API_BASE})')
    server = http.server.HTTPServer(('0.0.0.0', PORT), AdminHandler)
    print(f'Admin Panel running on http://0.0.0.0:{PORT} -> middleware {API_BASE}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Shutting down...')
        server.server_close()
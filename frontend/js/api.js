/* ════════════════════════════════════════════════════
   WIM Online — API Client Module
   Auth is server-side via session cookie (credentials: same-origin)
   ════════════════════════════════════════════════════ */

// ── Error Logger
const WIM_LOGGER = {
  _enabled: true,

  info(context, message, data = null) {
    if (!this._enabled || !WIM_CONFIG.logging.enabled) return;
    const entry = { level: 'INFO', context, message, data, ts: new Date().toISOString() };
    if (WIM_CONFIG.logging.consoleEnabled) console.log(`[WIM ${entry.level}] [${context}] ${message}`, data || '');
    if (WIM_CONFIG.logging.serverEndpoint) this._send(entry);
  },

  warn(context, message, data = null) {
    if (!this._enabled || !WIM_CONFIG.logging.enabled) return;
    const entry = { level: 'WARN', context, message, data, ts: new Date().toISOString() };
    if (WIM_CONFIG.logging.consoleEnabled) console.warn(`[WIM ${entry.level}] [${context}] ${message}`, data || '');
    if (WIM_CONFIG.logging.serverEndpoint) this._send(entry);
  },

  error(context, message, data = null) {
    if (!this._enabled || !WIM_CONFIG.logging.enabled) return;
    const entry = { level: 'ERROR', context, message, data, ts: new Date().toISOString() };
    if (WIM_CONFIG.logging.consoleEnabled) console.error(`[WIM ${entry.level}] [${context}] ${message}`, data || '');
    if (WIM_CONFIG.logging.serverEndpoint) this._send(entry);
  },

  _send(entry) {
    try {
      fetch(WIM_CONFIG.logging.serverEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(entry),
      }).catch(() => {});
    } catch (e) {}
  },
};

const WIM_API = {
  baseURL: '',
  driverId: null,

  init(config) {
    this.baseURL = config?.baseURL || WIM_CONFIG.api.baseURL;
    this.driverId = config?.driverId || WIM_CONFIG.api.driverId;
    WIM_LOGGER.info('API', 'API initialized', { baseURL: this.baseURL });
  },

  async request(method, path, data = null) {
    const url = path.startsWith('/api/') ? path : `${this.baseURL}${path}`;
    const opts = {
      method,
      credentials: 'same-origin',
      headers: {
        'Accept': 'application/json',
      },
    };
    if (data && !(data instanceof FormData)) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(data);
    } else if (data instanceof FormData) {
      opts.body = data;
    }
    try {
      const resp = await fetch(url, opts);
      if (!resp.ok) {
        const errBody = await resp.text().catch(() => '');
        const msg = `API ${resp.status}: ${errBody.slice(0, 200)}`;
        WIM_LOGGER.error('API', msg, { method, path, status: resp.status });
        throw new Error(msg);
      }
      const result = await resp.json();
      WIM_LOGGER.info('API', `${method} ${path} → 200`, { status: 200 });
      return result;
    } catch (e) {
      if (e.name !== 'Error') throw e;
      const msg = `Network error: ${e.message}`;
      WIM_LOGGER.error('API', msg, { method, path });
      throw new Error(msg);
    }
  },

  get(path) { return this.request('GET', path); },
  post(path, data) { return this.request('POST', path, data); },
  patch(path, data) { return this.request('PATCH', path, data); },
  del(path) { return this.request('DELETE', path); },

  // ── Domain helpers — repointed to local /api/* endpoints
  async getPlaces() {
    // Repointed: GET /api/stores/all → local stores endpoint
    try {
      const data = await this.get('/api/stores/all');
      return data.stores || [];
    } catch (e) {
      WIM_LOGGER.error('API', 'getPlaces failed (stores/all)', e.message);
      return [];
    }
  },

  async getEntities(params = '') {
    // Repointed: GET /api/products → local products endpoint
    try {
      const data = await this.get(`/api/products${params}`);
      return Array.isArray(data) ? data : (data.data || []);
    } catch (e) {
      WIM_LOGGER.error('API', 'getEntities failed', e.message);
      return [];
    }
  },

  async getOrders(params = '') {
    // Repointed: GET /api/orders → local orders endpoint
    try {
      const data = await this.get(`/api/orders${params}`);
      return Array.isArray(data) ? data : (data.data || []);
    } catch (e) {
      WIM_LOGGER.error('API', 'getOrders failed', e.message);
      return [];
    }
  },

  async getDrivers() {
    // Repointed: GET /api/users?role=sales (guarded — 404 returns [])
    try {
      const data = await this.get('/api/users?role=sales');
      return data.users || [];
    } catch (e) {
      WIM_LOGGER.warn('API', 'getDrivers (/api/users) not available yet, returning []', e.message);
      return [];
    }
  },

  async getContacts() {
    // No local contacts endpoint yet — admin page expects empty list
    WIM_LOGGER.info('API', 'getContacts — no local endpoint yet, returning []');
    return [];
  },

  async createPlace(placeData) {
    // Repointed: POST /api/stores (NOO creation) — handles contacts inline
    try {
      return await this.post('/api/stores', placeData);
    } catch (e) {
      WIM_LOGGER.error('API', 'createPlace (/api/stores) failed', { error: e.message, placeData });
      throw e;
    }
  },

  async createContact(contactData) {
    // POST /api/stores handles contacts inline; this is a no-op
    WIM_LOGGER.info('API', 'createContact — no-op (contacts handled by POST /api/stores)');
    return { status: 'ok', message: 'Contact handled inline by store creation' };
  },

  async updateOrder(id, updateData) {
    try {
      return await this.patch(`/api/orders/${id}`, updateData);
    } catch (e) {
      WIM_LOGGER.error('API', 'updateOrder failed', { id, error: e.message });
      throw e;
    }
  },

  // ── Per-user endpoints (server-side, session-scoped)
  async getDashboard() {
    try {
      return await this.get('/api/dashboard');
    } catch (e) { return { plan: { total: 0 }, orders: 0, attendance: {}, visitsToday: 0, recentVisits: [] }; }
  },

  async getMyStores() {
    try {
      const data = await this.get('/api/stores');
      return data.stores || [];
    } catch (e) { return []; }
  },

  async getAllStores(q = '') {
    try {
      const data = await this.get(`/api/stores/all${q ? '?q=' + encodeURIComponent(q) : ''}`);
      return data.stores || [];
    } catch (e) { return []; }
  },

  async addOutRouteStore(placeUuid) {
    return await this.post('/api/visit_plan', { place_uuid: placeUuid });
  },

  async visitCheckin(placeUuid, placeName, lat, lng, source = 'route', checkinPhoto = '') {
    return await this.post('/api/visits', { action: 'checkin', place_uuid: placeUuid, place_name: placeName, lat, lng, source, checkin_photo: checkinPhoto });
  },

  async visitCheckout(placeUuid, placeName, photos, notes, durationSeconds, status = 'visited') {
    return await this.post('/api/visits', { action: 'checkout', place_uuid: placeUuid, place_name: placeName, photos, notes, durationSeconds, status });
  },

  async getVisits(date = '') {
    try {
      const data = await this.get(`/api/visits${date ? '?date=' + date : ''}`);
      return data.visits || [];
    } catch (e) { return []; }
  },

  async getReport(period = 'harian') {
    try {
      return await this.get(`/api/report?period=${period}`);
    } catch (e) { return { attendanceDays: 0, visits: 0, storesVisited: 0, orders: 0, daily: [] }; }
  },

};
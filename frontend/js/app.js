/* ════════════════════════════════════════════════════
   WIM Online — Shared App Utilities
   ════════════════════════════════════════════════════ */

// ── Session helpers
const Session = {
  get(key, fallback = null) {
    return sessionStorage.getItem(key) || fallback;
  },
  set(key, value) {
    sessionStorage.setItem(key, value);
  },
  clear() {
    sessionStorage.clear();
  },

  // Check server-side session and init API
  async restoreAPI() {
    try {
      const resp = await fetch(WIM_CONFIG.auth.sessionURL);
      const data = await resp.json();
      if (data.user) {
        const pid = data.user.driver_id || '';
        this.set(WIM_CONFIG.session.userNameKey, data.user.name || '');
        this.set(WIM_CONFIG.session.userRoleKey, data.user.role || '');
        this.set(WIM_CONFIG.session.driverIdKey, pid);
        WIM_API.init({ driverId: pid });
        return data.user;
      }
    } catch (e) {
      // Fallback to sessionStorage
      const pid = this.get(WIM_CONFIG.session.driverIdKey, '');
      WIM_API.init({ driverId: pid });
    }
    // No valid session
    return null;
  },

  async checkOrRedirect() {
    const user = await this.restoreAPI();
    if (!user) {
      window.location.href = 'index.html';
      return false;
    }
    return user;
  },

  async handleLogout() {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    this.clear();
    window.location.href = 'index.html';
  }
};

// ── Active bottom nav
function setActiveNav(page) {
  document.querySelectorAll('.bottom-nav a').forEach(a => a.classList.remove('active'));
  const el = document.querySelector(`.bottom-nav a[href$="${page}"]`);
  if (el) el.classList.add('active');
}

// ── Visit Timer
class VisitTimer {
  constructor(seconds, onTick, onDone) {
    this.total = seconds;
    this.remaining = seconds;
    this.onTick = onTick;
    this.onDone = onDone;
    this.interval = null;
    this.isDone = false;
  }

  get formatted() {
    const m = Math.floor(this.remaining / 60);
    const s = this.remaining % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  start() {
    if (this.interval) return;
    this.interval = setInterval(() => {
      this.remaining--;
      if (this.onTick) this.onTick(this.remaining);
      if (this.remaining <= 0) {
        this.stop();
        this.isDone = true;
        if (this.onDone) this.onDone();
      }
    }, 1000);
  }

  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }
}

// ── Camera capture (with HTTP fallback via file input)
async function capturePhoto(facingMode = 'environment') {
  const canUseGetUserMedia = !!(
    navigator.mediaDevices && navigator.mediaDevices.getUserMedia
  );

  if (canUseGetUserMedia) {
    // HTTPS path — use video stream
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode, width: { ideal: 1280 }, height: { ideal: 720 } },
      });
      const video = document.createElement('video');
      video.srcObject = stream;
      await video.play();

      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 720;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0);
      stream.getTracks().forEach((t) => t.stop());

      return new Promise((resolve) => {
        canvas.toBlob(
          (blob) => {
            const file = new File([blob], `photo_${Date.now()}.jpg`, {
              type: 'image/jpeg',
            });
            resolve(file);
          },
          'image/jpeg',
          0.85
        );
      });
    } catch (e) {
      console.error('Camera error:', e);
      alert('Tidak bisa mengakses kamera. Periksa izin kamera.');
      return null;
    }
  } else {
    // HTTP path — use file input fallback (native camera on mobile)
    return new Promise((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.capture = 'environment';
      input.style.display = 'none';
      document.body.appendChild(input);

      input.addEventListener('change', function () {
        const file = this.files[0];
        document.body.removeChild(input);
        if (file) {
          resolve(file);
        } else {
          resolve(null);
        }
      });

      // Fallback if user cancels
      input.addEventListener('cancel', function () {
        document.body.removeChild(input);
        resolve(null);
      });

      input.click();
    });
  }
}

// ── Download helpers
function downloadJSON(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadCSV(headers, rows, filename) {
  let csv = headers.join(',') + '\n';
  csv += rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ════════════════════════════════════════════════════
// WIM_Geo — shared geolocation util (added 2026-09-10)
// Captures the sales/user's current GPS position, reports it to /api/positions
// (which persists time+coords+user), and computes distances to stores so the
// Kunjungan menu can highlight stores within ~10m.
// ════════════════════════════════════════════════════
const WIM_Geo = {
  lastPosition: null,   // {latitude, longitude, accuracy}
  storeRadiusM: 10,
  // Default geofence radius (m) when a store has no geofence_radius_m override.
  // Matches the sales-app default (10 m). Admin can raise it per store for
  // large stores that keep triggering false "Luar Area".
  defaultRadiusM: 10,

  // Get current position via browser geolocation (with timeout). Some browsers expose
  // navigator.geolocation.getCurrentPosition (webview); else navigator.geolocation.getCurrentPosition
  // vs standard navigator.geolocation.getCurrentPosition / getCurrentPosition.
  async getCurrentPosition({ timeoutMs = 10000 } = {}) {
    if (typeof navigator === 'undefined') return null;
    const getFn = (navigator.geolocation && navigator.geolocation.getCurrentPosition)
      || (navigator.geolocation && navigator.geolocation.getCurrentPosition);
    if (!getFn) return null;
    return new Promise((resolve) => {
      let done = false;
      const timeout = setTimeout(() => { if (!done) { done = true; resolve(null); } }, timeoutMs);
      try {
        getFn.call(
          navigator.geolocation,
          (pos) => { if (done) return; done = true; clearTimeout(timeout); this.lastPosition = { latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy }; resolve(this.lastPosition); },
          (err) => { if (done) return; done = true; clearTimeout(timeout); resolve(null); },
          { maximumAge: 0, timeout: timeoutMs }
        );
      } catch (e) { if (!done) { done = true; clearTimeout(timeout); resolve(null); } }
    });
  },

  // Standard browser navigator.geolocation.getCurrentPosition fallback
  async getBrowserPosition({ timeoutMs = 10000 } = {}) {
    if (!('geolocation' in navigator) || typeof navigator.geolocation.getCurrentPosition !== 'function') return null;
    try {
      return await new Promise((resolve) => {
        let done = false;
        const to = setTimeout(() => { if (!done) { done = true; resolve(null); } }, timeoutMs);
        navigator.geolocation.getCurrentPosition(
          (pos) => { if (done) return; done = true; clearTimeout(to); resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy }); },
          () => { if (!done) { done = true; clearTimeout(to); resolve(null); } },
          { maximumAge: 0, timeout: timeoutMs }
        );
      });
    } catch (e) { return null; }
  },

  // Capture position (tries webview API then browser API), stores in this.lastPosition
  async capture() {
    let p = await this.getCurrentPosition();
    if (!p) p = await this.getBrowserPosition().then(bp => { if (bp) this.lastPosition = bp; return bp; }).catch(() => null);
    if (p) this.lastPosition = p;
    return this.lastPosition;
  },

  // Report current position to server for persistence (no-op if no position)
  // Returns true if a fix was reported, false otherwise.
  async reportPosition() {
    const p = this.lastPosition || await this.capture();
    if (!p || !p.latitude || !p.longitude) return false;
    try {
      await fetch('/api/positions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ latitude: p.latitude, longitude: p.longitude, accuracy: p.accuracy }),
      });
      return true;
    } catch (e) { return false; }
  },

  // Convenience: capture + report (fire-and-forget; used on page load/refresh)
  async track() { await this.capture(); return this.reportPosition(); },

  // Distance in meters between two lat/lng
  distanceM(lat1, lng1, lat2, lng2) {
    if (lat1 == null || lng1 == null || lat2 == null || lng2 == null) return null;
    const R = 6371000;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  },

  // Is a store within the in-range radius of the given position?
  inRange(store, pos = null) {
    if (!store) return false;
    const p = pos || this.lastPosition;
    if (!p || !p.latitude || !p.longitude) return false;
    const lat = store.latitude != null ? store.latitude : store.lat;
    const lng = store.longitude != null ? store.longitude : store.lng;
    const d = this.distanceM(p.latitude, p.longitude, lat, lng);
    return d !== null && d <= this.storeRadiusM;
  },
};
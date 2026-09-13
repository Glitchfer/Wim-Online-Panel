/* ════════════════════════════════════════════════════
   WIM Online — Config File
   Auth is server-side via session.
   ════════════════════════════════════════════════════ */

const WIM_CONFIG = {
  app: {
    name: 'WIM Online',
    version: '1.0',
    environment: 'staging',
    company: 'PT Wahana Inti Mas',
  },

  // ── Auth endpoints (same-origin, server handles)
  auth: {
    loginURL: '/api/auth/login',
    logoutURL: '/api/auth/logout',
    sessionURL: '/api/auth/session',
  },

  // ── API (same-origin, no prefix needed)
  api: {
    baseURL: '',
    driverId: null,
  },

  // ── Session storage keys
  session: {
    userNameKey: 'wim_user_name',
    userEmailKey: 'wim_user_email',
    userRoleKey: 'wim_user_role',
    driverIdKey: 'wim_driver_id',
  },

  logging: {
    enabled: true,
    serverEndpoint: '/api/log',
    consoleEnabled: true,
  },

  features: {
    timerDuration: 180,
    mandatorySelfie: true,
    allowMultiplePhotos: true,
    geofenceRadiusMeters: 10,
  },
};
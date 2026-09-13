/* ============================================================
   WIM Admin — shared header/footer include
   Loaded on every admin page. Fetches the master header + footer
   partials once and injects them into #appHeader / #appFooter,
   then marks the active page, highlights its parent dropdown, and
   restores the logged-in user's identity.

   Dropdown open/close is pure CSS (:hover) — designed for desktop.
   This script only ADDS the active-page highlight + user identity.
   ============================================================ */
(function () {
  if (window.__headerLoaded) return;
  var PAGE = (document.body && document.body.getAttribute('data-page')) || '';
  // Inject shared nav CSS (idempotent)
  if (!document.getElementById('wim-nav-css')) {
    var l = document.createElement('link');
    l.id = 'wim-nav-css'; l.rel = 'stylesheet'; l.href = 'css/nav.css';
    document.head.appendChild(l);
  }
  function fetchText(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) throw new Error('include ' + url + ' -> ' + r.status);
      return r.text();
    });
  }
  Promise.all([
    fetchText('partials/header.html'),
    fetchText('partials/footer.html')
  ]).then(function (parts) {
    var headEl = document.getElementById('appHeader');
    var footEl = document.getElementById('appFooter');
    if (headEl) headEl.innerHTML = parts[0];
    if (footEl) footEl.innerHTML = parts[1];

    // ── Mark active nav link + highlight its parent dropdown trigger ──
    if (PAGE) {
      document.querySelectorAll('#appHeader nav a[data-page]').forEach(function (a) {
        if (a.getAttribute('data-page') === PAGE) {
          a.className = 'active';
          var dd = a.closest('.nav-drop');
          if (dd) dd.classList.add('has-active');
        }
      });
    }

    // ── Restore user identity ──
    try {
      var u = JSON.parse(sessionStorage.getItem('admin_user') || '{}');
      var un = document.getElementById('userName');
      var ur = document.getElementById('userRole');
      if (un && u.name) un.textContent = u.name;
      if (ur && u.role) ur.textContent = u.role;
    } catch (e) {}

    window.__headerLoaded = true;
    window.dispatchEvent && window.dispatchEvent(new Event('wim-header-loaded'));
  }).catch(function (e) {
    console.error('header include failed', e);
  });
})();
/**
 * EduSphere — ThemeManager (Final)
 *
 * HOW IT WORKS:
 *
 *   On login: server sets cookie  es_theme=dark  (or light)
 *   ThemeManager reads cookie → applies theme → writes to localStorage
 *   From that point: localStorage is the single source of truth
 *   Every toggle: updates localStorage + cookie + DB (async)
 *   Logout: session cleared, but localStorage & cookie remain → login page
 *           shows the same theme the user last used
 *
 * RESOLUTION ORDER (runs synchronously before CSS paints):
 *   1. es_theme cookie  — written by server on login, by JS on every toggle
 *   2. localStorage     — written by JS on every toggle
 *   3. Default: light   — first-ever visit, no preference stored anywhere
 *
 * WHY NO data-server-theme:
 *   If server-injected value is in priority #1, it overrides every toggle
 *   until the DB write completes AND a full page reload happens.
 *   That causes the "change theme on page A, page B still shows old theme" bug.
 *   The cookie solves the login→dashboard gap without this side-effect.
 *
 * LOAD ORDER required in every template:
 *   <html>  ← no data-server-theme needed
 *   <head>
 *     <script src="theme-manager.js">  ← runs sync, sets data-theme before CSS
 *     <link rel="stylesheet" ...>
 */

(function (global) {
  'use strict';

  var LS_KEY  = 'edusphere_theme';
  var CK_KEY  = 'es_theme';
  var ATTR    = 'data-theme';
  var DEFAULT = 'light';

  function valid(t) { return t === 'light' || t === 'dark'; }

  /* ── read sources ─────────────────────────────────────────────────────── */

  function fromCookie() {
    try {
      var m = document.cookie.match(/(?:^|;\s*)es_theme=([^;]+)/);
      return m ? decodeURIComponent(m[1]) : null;
    } catch (_) { return null; }
  }

  function fromStorage() {
    try { return localStorage.getItem(LS_KEY); } catch (_) { return null; }
  }

  /* ── write ────────────────────────────────────────────────────────────── */

  function toStorage(t) {
    try { localStorage.setItem(LS_KEY, t); } catch (_) {}
  }

  function toCookie(t) {
    try {
      document.cookie = CK_KEY + '=' + t + ';path=/;max-age=' + (60*60*24*365) + ';samesite=Lax';
    } catch (_) {}
  }

  /* ── resolve initial theme ────────────────────────────────────────────── */

  function resolve() {
    var c = fromCookie();
    if (valid(c)) return c;
    var l = fromStorage();
    if (valid(l)) return l;
    return DEFAULT;
  }

  /* ── apply ────────────────────────────────────────────────────────────── */

  function apply(theme) {
    if (!valid(theme)) theme = DEFAULT;
    TM._current = theme;
    document.documentElement.setAttribute(ATTR, theme);
    toStorage(theme);
    toCookie(theme);
    syncIcon(theme);
    try { global.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: theme } })); } catch (_) {}
  }

  function syncIcon(theme) {
    var els = document.querySelectorAll('#themeIcon');
    for (var i = 0; i < els.length; i++) {
      els[i].className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars';
    }
  }

  /* ── server sync (fire-and-forget) ───────────────────────────────────── */

  function pushToServer(theme) {
    try {
      fetch('/toggle_theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: theme })
      }).catch(function () {});
    } catch (_) {}
  }

  /* ── public API ───────────────────────────────────────────────────────── */

  var TM = {
    _current: DEFAULT,
    getTheme:    function ()      { return TM._current; },
    toggleTheme: function ()      { var n = TM._current === 'dark' ? 'light' : 'dark'; apply(n); pushToServer(n); },
    setTheme:    function (theme) { if (valid(theme)) { apply(theme); pushToServer(theme); } }
  };

  /* ── BOOT — runs synchronously at script-parse time, before CSS ──────── */
  apply(resolve());

  /* ── re-sync icon after DOM is ready (icon element not in DOM yet) ───── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { syncIcon(TM._current); });
  }

  global.themeManager = TM;

}(window));

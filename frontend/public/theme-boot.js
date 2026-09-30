/*
 * Apply the saved theme and motion choice before the first paint, so a
 * reload never flashes the other theme. Mirrors initialTheme() in
 * src/settingsModel.ts: an explicit choice wins, otherwise light.
 */
(function () {
  var root = document.documentElement, theme = 'light', motion = '';
  try {
    var chosen = localStorage.getItem('themeChoice'), legacy = localStorage.getItem('theme');
    theme = /^(dark|light|system)$/.test(chosen || '') ? chosen : /^(dark|light|system)$/.test(legacy || '') ? legacy : 'light';
    motion = localStorage.getItem('motion') || '';
  } catch (e) { /* storage unavailable */ }
  if (theme === 'system') theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  root.setAttribute('data-theme', theme);
  document.querySelector('meta[name="theme-color"]').setAttribute('content', theme === 'dark' ? '#0d1220' : '#f6f3ee');
  if (motion === 'reduced') root.setAttribute('data-motion', 'reduced');
})();

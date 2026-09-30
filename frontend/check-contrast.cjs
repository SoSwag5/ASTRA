/**
 * #47 visual revision: verify the palette in src/tokens.css meets WCAG 2.2 AA
 * contrast in both themes. Text pairs need 4.5:1; control boundaries, focus
 * rings and data marks need 3:1 (1.4.11). The values are read from the CSS
 * itself, so a palette edit cannot drift from this check.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const css = fs.readFileSync(path.join(__dirname, 'src', 'tokens.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

function block(selector) {
  const start = css.indexOf(selector + ' {');
  assert.ok(start >= 0, `tokens.css has a ${selector} block`);
  const end = css.indexOf('\n}', start);
  const vars = {};
  for (const match of css.slice(start, end).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars[match[1]] = match[2].trim();
  return vars;
}

const light = block(':root');
const dark = {...light, ...block('[data-theme=dark]')};

function resolve(vars, name, seen = new Set()) {
  assert.ok(!seen.has(name), `no cycle at ${name}`);
  seen.add(name);
  const value = vars[name];
  assert.ok(value, `${name} is defined`);
  const alias = /^var\((--[\w-]+)\)$/.exec(value);
  return alias ? resolve(vars, alias[1], seen) : value;
}

function rgb(hex) {
  const match = /^#([0-9a-f]{6})$/i.exec(hex);
  assert.ok(match, `${hex} is a 6-digit hex colour`);
  return [0, 2, 4].map(i => parseInt(match[1].slice(i, i + 2), 16) / 255);
}
function luminance(hex) {
  const [r, g, b] = rgb(hex).map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}

const surfaces = ['--surface-page', '--surface-sidebar', '--surface-1', '--surface-2', '--surface-raised', '--surface-input'];
const TEXT = 4.5, UI = 3;
const pairs = [];
for (const surface of surfaces) {
  for (const ink of ['--ink-1', '--ink-2', '--ink-3', '--action-text']) pairs.push([ink, surface, TEXT]);
  pairs.push(['--warm', surface, TEXT]);
  pairs.push(['--focus-ring', surface, UI]);
  pairs.push(['--control-border', surface, UI]);
  pairs.push(['--viz-series', surface, UI]);
}
pairs.push(['--viz-series', '--viz-track', UI]);
for (const mark of ['--viz-series-2', '--viz-series-3', '--viz-muted']) {
  pairs.push([mark, '--surface-1', UI], [mark, '--viz-track', UI]);
}
pairs.push(['--on-action', '--action', TEXT], ['--on-action', '--action-hover', TEXT], ['--on-action', '--action-press', TEXT]);
pairs.push(['--ink-1', '--action-soft', TEXT], ['--action-text', '--action-soft', TEXT], ['--ink-2', '--action-soft', TEXT]);
pairs.push(['--ink-1', '--surface-sunken', TEXT], ['--ink-2', '--surface-sunken', TEXT], ['--ink-3', '--surface-sunken', TEXT]);
pairs.push(['--warm', '--warm-soft', TEXT]);
pairs.push(['--danger-fg', '--danger-bg', TEXT], ['--danger-fg', '--danger-bg-hover', TEXT]);
pairs.push(['--ink-inverse', '--surface-inverse', TEXT]);
for (const tone of ['good', 'warn', 'bad', 'info', 'neutral']) {
  pairs.push([`--status-${tone}-fg`, `--status-${tone}-bg`, TEXT]);
  pairs.push([`--status-${tone}-fg`, '--surface-1', TEXT]);
}

let checks = 0;
const failures = [];
for (const [theme, vars] of [['light', light], ['dark', dark]]) {
  for (const [fg, bg, min] of pairs) {
    const value = ratio(resolve(vars, fg), resolve(vars, bg));
    checks += 1;
    if (value < min) failures.push(`${theme}: ${fg} on ${bg} is ${value.toFixed(2)}:1, needs ${min}:1`);
  }
}
assert.deepEqual(failures, [], failures.join('\n'));
console.log(`Palette contrast checks passed (${checks} pairs, light and dark).`);

/** Evidence rules for the visual rails and preservation of browser choices. */
const assert = require('node:assert/strict');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const fs = require('node:fs');
const vm = require('node:vm');

(async () => {
  const {createServer} = await import('vite');
  const server = await createServer({configFile: false, optimizeDeps: {noDiscovery: true, include: []}, server: {middlewareMode: true}, appType: 'custom', logLevel: 'error'});
  let checks = 0;
  const ok = (value, message) => { assert.ok(value, message); checks++; };
  try {
    const M = await server.ssrLoadModule('/src/progressModel.ts');
    const S = await server.ssrLoadModule('/src/settingsModel.ts');
    const V = await server.ssrLoadModule('/src/Progress.tsx');
    const motion = await server.ssrLoadModule('/src/motion.ts');
    const weekly = {weekly: [{week_start: '2026-09-21', submitted: 9}, {week_start: '2026-09-28', submitted: 3}], submission_date_not_recorded: 2};
    ok(!M.weeklyTargetRail(weekly, null).available, 'no saved target is not a fabricated goal');
    ok(!M.weeklyTargetRail(weekly, undefined).available, 'failed settings read is unavailable');
    for (const target of [0, -1, 2.5, NaN, '4']) ok(!M.weeklyTargetRail(weekly, {weekly_target: target}).available, 'invalid denominator unavailable');
    ok(!M.weeklyTargetRail(null, {weekly_target: 4}).available, 'missing submissions are not zero');
    const target = M.weeklyTargetRail(weekly, {weekly_target: 2});
    ok(target.value === 3 && target.max === 2 && /2 submissions without/.test(target.note), 'current week and excluded undated submissions are explicit');
    const bar = renderToStaticMarkup(React.createElement(V.RailBar, {rail: target, kind: 'progress', labelledBy: 'week'}));
    ok(/aria-valuenow="2"/.test(bar) && /3 applications submitted/.test(bar), 'over-target visual is bounded; actual count remains accessible');
    ok(M.weeklyTargetRail({weekly: [{submitted: 0}]}, {weekly_target: 2}).value === 0, 'recorded zero stays zero');
    const current = {total: 3, applications_total: 3, states: {APPLIED: 2, INTERVIEW: 1}, complete: true};
    const stages = M.stageRail(current);
    ok(stages.available && stages.segments.reduce((n, s) => n + s.count, 0) === 3, 'composition reconciles to recorded total');
    ok(!M.stageRail({...current, complete: false, pending_initialization: 1}).available, 'incomplete reads cannot claim every application');
    ok(!M.stageRail({...current, applications_total: 4}).available, 'missing state denominator is unavailable');
    ok(!M.stageRail({...current, total: 2}).available, 'inconsistent stages are unavailable');
    ok(!M.stageRail({...current, states: {APPLIED: 2}}).available, 'missing stage counts are not invented');
    const scan = {active: {progress: {sources_total: 4, sources_done: 2, current_source: 'Fictional board'}}};
    ok(M.scanRail(scan, null).value === 2, 'active progress uses recorded source completions');
    ok(!M.scanRail({active: {}}, null).available, 'starting scan has no invented percentage');
    ok(!M.scanRail({active: {progress: {sources_total: 1, sources_done: 2}}}, null).available, 'impossible progress is unavailable');
    const latest = {run: {telemetry: {funnel: {}, sources_attempted: 4, sources_succeeded: 2, sources_partial: 1, sources_failed: 1}}};
    const finished = M.scanRail({active: null}, latest);
    ok(!finished.live && finished.segments.reduce((n, s) => n + s.count, 0) === 4, 'finished telemetry stops live treatment');
    ok(!M.scanRail(null, latest).available, 'failed status read does not silently show stale completion');
    ok(!M.scanRail({}, {run: {telemetry: {funnel: {}, sources_attempted: 4}}}).available, 'missing source outcomes cannot claim zero successes');
    ok(!M.scanRail({}, {status: 'NO_DATA'}).available, 'no scan is not zero completion');
    for (const [values, expected] of [[{}, 'light'], [{theme: 'dark'}, 'dark'], [{theme: 'light'}, 'light'], [{theme: 'system'}, 'system'], [{theme: 'dark', themeChoice: 'light'}, 'light'], [{themeChoice: 'invalid'}, 'light']]) {
      const storage = {getItem: key => values[key] ?? null};
      ok(S.initialTheme(storage) === expected, 'saved preference preserved or new browser light');
      const attrs = {}, meta = {};
      vm.runInNewContext(fs.readFileSync('public/theme-boot.js', 'utf8'), {localStorage: storage, window: {matchMedia: () => ({matches: false})}, document: {documentElement: {setAttribute: (k, v) => attrs[k] = v}, querySelector: () => ({setAttribute: (k, v) => meta[k] = v})}});
      ok(attrs['data-theme'] === (expected === 'system' ? 'dark' : expected), 'first paint matches React');
      ok(meta.content === (attrs['data-theme'] === 'dark' ? '#0d1220' : '#f6f3ee'), 'browser chrome matches explicit choice');
    }
    ok(S.initialTheme({getItem: () => {throw Error('disabled')}}) === 'light', 'storage failure falls back safely');
    ok(motion.directionBetween(['Today', 'Progress', 'Jobs'], 'Jobs', 'Today') === 'back', 'backward navigation has backward motion');
    console.log(`${checks} visual evidence and preference checks passed.`);
  } finally { await server.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });

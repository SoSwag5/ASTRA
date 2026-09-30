/** #47 follow-up A: unsaved-change rules, save wording and dialog markup, with fictional values. */
const assert = require('node:assert/strict');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

(async () => {
  const {createServer} = await import('vite');
  const server = await createServer({configFile: false, optimizeDeps: {noDiscovery: true, include: []}, server: {middlewareMode: true}, appType: 'custom', logLevel: 'error'});
  let checks = 0;
  const ok = (value, message) => { assert.ok(value, message); checks += 1; };
  try {
    const S = await server.ssrLoadModule('/src/settingsModel.ts');
    const U = await server.ssrLoadModule('/src/ui.tsx');
    const html = (component, props) => renderToStaticMarkup(React.createElement(component, props));

    // Formatting-only edits are not unsaved changes; real edits are.
    ok(!S.isDirty({roles: 'SOC Analyst\nGRC Analyst'}, {roles: 'SOC Analyst\nGRC Analyst\n\n'}, ['roles']), 'a trailing blank line is not a change');
    ok(!S.isDirty({roles: ['SOC Analyst']}, {roles: '  SOC Analyst  '}, ['roles']), 'list vs text of the same items is not a change');
    ok(S.isDirty({roles: 'SOC Analyst\nGRC Analyst'}, {roles: 'GRC Analyst\nSOC Analyst'}, ['roles']), 'reordering is a change');
    ok(S.isDirty({minimum_score: 70}, {minimum_score: 65}, ['minimum_score']), 'a number change is a change');
    ok(!S.isDirty({weights: {skills: 1, location: 2}}, {weights: {location: 2, skills: 1}}, ['weights']), 'key order in an object is not a change');
    ok(S.isDirty({weights: {skills: 1}}, {weights: {skills: 3}}, ['weights']), 'a nested value change is a change');
    ok(!S.isDirty({a: 1, b: 2}, {a: 1, b: 9}, ['a']), 'only the card’s own keys count');
    ok(S.changedKeys({a: 'x', b: 'y'}, {a: 'x', b: 'z'}, ['a', 'b']).join() === 'b', 'changed keys are named');
    ok(JSON.stringify(S.payload({roles: 'A\n\nB', limit: 3}, ['roles', 'limit'], ['roles'])) === JSON.stringify({roles: ['A', 'B'], limit: 3}), 'list fields are sent as arrays');

    // Save wording never claims a save that did not happen.
    ok(S.saveStatusText('saving', true) === 'Saving…', 'saving is stated');
    ok(S.saveStatusText('error', true, '', 'Invalid scoring weights') === 'Not saved: Invalid scoring weights', 'a server refusal is reported');
    ok(S.saveStatusText('idle', true) === 'Unsaved changes', 'unsaved changes are stated');
    ok(S.saveStatusText('saved', true) === 'Unsaved changes', 'a later edit after saving is unsaved again');
    ok(/^Saved at \d\d:\d\d$/.test(S.saveStatusText('saved', false, '2026-09-30T10:05:00Z')), 'a completed save shows its time');
    ok(S.saveStatusText('idle', false) === 'All changes saved', 'the resting state is stated');

    // Appearance and the leave warning.
    ok(S.resolveTheme('system', true) === 'light' && S.resolveTheme('system', false) === 'dark', 'match system follows the OS');
    ok(S.resolveTheme('light', false) === 'light', 'an explicit theme wins');
    const leave = S.leaveWarning(['Ranking thresholds']);
    ok(/Ranking thresholds/.test(leave.body) && /discards those changes/.test(leave.body), 'the leave warning names what would be lost');
    ok(S.SECTIONS.map(s => s.id).join() === 'focus,profile,sources,permissions,appearance,privacy,workspace', 'sections are in task order');

    // The save bar in each state.
    const noop = () => {};
    const state = extra => ({draft: {}, dirty: false, status: 'idle', error: '', savedAt: '', set: noop, discard: noop, save: async () => true, ...extra});
    const idle = html(U.SaveBar, {state: state({}), onSave: noop});
    ok(/All changes saved/.test(idle) && /disabled=""/.test(idle) && !/Discard/.test(idle), 'at rest: saved, save disabled, no discard');
    const dirty = html(U.SaveBar, {state: state({dirty: true}), onSave: noop});
    ok(/is-active/.test(dirty) && /Unsaved changes/.test(dirty) && /Discard/.test(dirty), 'dirty: visible, with discard');
    const saving = html(U.SaveBar, {state: state({dirty: true, status: 'saving'}), onSave: noop});
    ok(/aria-busy="true"/.test(saving) && /Saving…/.test(saving), 'saving: busy and labelled');
    const failed = html(U.SaveBar, {state: state({dirty: true, status: 'error', error: 'Choose scans every 3, 6, 12 or 24 hours'}), onSave: noop});
    ok(/role="alert"/.test(failed) && /Not saved: Choose scans/.test(failed) && /Discard/.test(failed), 'failure: announced, input kept, discard offered');

    // A consequential action: specific title, action-named buttons, safe choice first.
    const dialog = html(U.ConfirmDialog, {onClose: noop, request: {title: 'Disconnect Gmail?', body: 'Your applications are kept.', confirmLabel: 'Disconnect Gmail', cancelLabel: 'Keep connected', tone: 'danger', onConfirm: noop}});
    ok(/role="alertdialog"/.test(dialog) && /aria-modal="true"/.test(dialog), 'the dialog is a modal alert dialog');
    ok(/aria-labelledby=/.test(dialog) && /aria-describedby=/.test(dialog), 'the dialog is labelled and described');
    ok(dialog.indexOf('Keep connected') < dialog.indexOf('Disconnect Gmail</button>'), 'the safe choice comes first');
    ok(!/>Yes</.test(dialog) && !/>No</.test(dialog), 'buttons name actions, not yes/no');
    ok(html(U.ConfirmDialog, {onClose: noop, request: null}) === '', 'nothing renders without a request');

    // Action status tones.
    ok(/role="alert"/.test(html(U.ActionStatus, {status: {tone: 'bad', text: 'Board link not recognised'}})), 'errors are announced assertively');
    ok(/role="status"/.test(html(U.ActionStatus, {status: {tone: 'good', text: 'Source added.'}})), 'success is announced politely');
    console.log(`${checks} fictional Settings, save-state and dialog checks passed.`);
  } finally {
    await server.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});

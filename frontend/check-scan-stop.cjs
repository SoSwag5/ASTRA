/** Render the real scan controls with fictional active-run states. */
const assert = require('node:assert/strict');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

function buttonIn(node, label) {
  if (Array.isArray(node)) return node.map(child => buttonIn(child, label)).find(Boolean);
  if (!React.isValidElement(node)) return undefined;
  if (node.type === 'button' && node.props.children === label) return node;
  return buttonIn(node.props.children, label);
}

(async () => {
  const {createServer} = await import('vite');
  const server = await createServer({configFile: false, optimizeDeps: {noDiscovery: true, include: []}, server: {middlewareMode: true}, appType: 'custom', logLevel: 'error'});
  try {
    const {ScanProgress} = await server.ssrLoadModule('/src/SearchWorkspace.tsx');
    const progress = {sources_total: 2, sources_done: 1, current_source: 'Fictional beta', postings_seen: 4};
    const run = {id: 42, progress};
    let stopCalls = 0;
    const onStop = () => { stopCalls += 1; };
    const props = (activeScan, cancellable, stopSaving = false) =>
      ({activeScan, cancellable, stopSaving, onStop});
    const html = p => renderToStaticMarkup(React.createElement(ScanProgress, p));

    const running = props(run, true);
    assert.match(html(running), />RUNNING</);
    assert.match(html(running), />Stop scan</);
    assert.equal(buttonIn(ScanProgress(running), 'Stop scan').props.disabled, false);

    const durable = props({...run, cancel_requested_at: '2026-09-26T10:00:00Z', stop_durable: true}, false);
    assert.match(html(durable), />STOPPING</);
    assert.doesNotMatch(html(durable), /Retry saving Stop|>Stop scan</);

    const uncertain = props({...run, cancel_requested_at: '2026-09-26T10:00:00Z', stop_durable: false}, false);
    assert.match(html(uncertain), />STOP NEEDS RETRY</);
    assert.match(html(uncertain), /could not confirm it was saved/);
    const retry = buttonIn(ScanProgress(uncertain), 'Retry saving Stop');
    assert.ok(retry, 'uncertain Stop must retain its retry control');
    assert.equal(retry.props.disabled, false, 'retry must work even when cancellable is false');
    retry.props.onClick();
    assert.equal(stopCalls, 1, 'retry must use the Stop action');

    const saving = props(uncertain.activeScan, false, true);
    assert.equal(buttonIn(ScanProgress(saving), 'Saving Stop…').props.disabled, true);
    console.log('4 fictional scan Stop UI states passed.');
  } finally {
    await server.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});

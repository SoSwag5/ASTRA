/** Discovery polling runs one round at a time, and the preview states its estimate honestly. */
const assert = require('node:assert/strict');

(async () => {
  const {createServer} = await import('vite');
  const server = await createServer({configFile: false, optimizeDeps: {noDiscovery: true, include: []}, server: {middlewareMode: true}, appType: 'custom', logLevel: 'error'});
  try {
    const {singleFlight, estimateText} = await server.ssrLoadModule('/src/SearchWorkspace.tsx');

    // A slow round is never joined by a second one; the next tick after it ends runs.
    let release, calls = 0;
    const tick = singleFlight(() => { calls += 1; return new Promise(resolve => { release = resolve; }); });
    const first = tick();
    assert.equal(await tick(), false, 'a tick while a round is pending must be skipped');
    assert.equal(calls, 1);
    release(); assert.equal(await first, true);
    const second = tick(); assert.equal(calls, 2); release(); await second;

    // A failed round does not wedge polling.
    const failing = singleFlight(() => Promise.reject(new Error('fictional outage')));
    await assert.rejects(failing(), /fictional outage/);
    await assert.rejects(failing(), /fictional outage/, 'the round after a failure must run');

    assert.equal(estimateText({estimated_seconds: null}), 'Unknown — no finished scan on this device yet');
    assert.equal(estimateText({estimated_seconds: 30, estimated_seconds_slowest: 40}), 'Under a minute');
    assert.equal(estimateText({estimated_seconds: 120, estimated_seconds_slowest: 150}), 'About 2 minutes');
    assert.equal(estimateText({estimated_seconds: 120, estimated_seconds_slowest: 440}),
                 'About 2 minutes; up to about 7 minutes at the slowest recent pace');
    assert.equal(estimateText({estimated_seconds: 20, estimated_seconds_slowest: 45}), 'Under a minute');
    console.log('Discovery single-flight polling and 5 estimate texts passed.');
  } finally {
    await server.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});

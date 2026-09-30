/** #47 follow-up B: Gmail check-and-match wording for every fictional outcome. */
const assert = require('node:assert/strict');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

(async () => {
  const {createServer} = await import('vite');
  const server = await createServer({configFile: false, optimizeDeps: {noDiscovery: true, include: []}, server: {middlewareMode: true}, appType: 'custom', logLevel: 'error'});
  let checks = 0;
  const ok = (value, message) => { assert.ok(value, message); checks += 1; };
  try {
    const G = await server.ssrLoadModule('/src/gmailOpsModel.ts');
    const V = await server.ssrLoadModule('/src/GmailOperations.tsx');

    // Connection states.
    ok(G.connectionState(null).connected === false, 'unknown status is not connected');
    const disconnected = G.connectionState({status: 'OK', connection: 'DISCONNECTED', coverage: {connected: false, sync_state: 'NONE'}});
    ok(!disconnected.connected && /Connect Gmail/.test(disconnected.detail), 'disconnected says how to connect');
    ok(/up to/.test(G.connectionState({status: 'OK', connection: 'CONNECTED', coverage: {connected: true, sync_state: 'COMPLETE', checked_through: '2026-09-30T08:00:00+00:00'}}).detail), 'last complete check is dated');
    const broken = G.connectionState({status: 'OK', connection: 'DISCONNECTED_INCONSISTENT', coverage: {connected: true, sync_state: 'COMPLETE'}});
    ok(!broken.connected && /Reconnect/.test(broken.label), 'a record without its credential is not treated as connected');
    ok(/stopped before finishing/.test(G.connectionState({status: 'OK', connection: 'CONNECTED', coverage: {connected: true, sync_state: 'INCOMPLETE'}}).detail), 'an unfinished check is stated');
    ok(/not been checked/.test(G.connectionState({status: 'OK', connection: 'CONNECTED', coverage: {connected: true, sync_state: 'NONE'}}).detail), 'never checked is stated');

    // Step 1 outcomes.
    const busy = G.syncOutcome(null, {status: 409, code: 'SYNC_ALREADY_RUNNING', detail: 'A Gmail sync is already running.'});
    ok(busy.tone === 'warn' && /not checked/.test(busy.title) && /Nothing was read/.test(busy.lines[0]), 'busy reads nothing and says so');
    const expired = G.syncOutcome(null, {status: 400, code: 'TOKEN_REFRESH_FAILED', detail: 'ASTRA could not renew access with the stored connection. Reconnect Gmail.'});
    ok(expired.action === 'reconnect' && /reconnected/.test(expired.title), 'an expired connection asks to reconnect');
    const failed = G.syncOutcome(null, {status: 400, code: 'GMAIL_READ_RATE_LIMITED', detail: 'Gmail is rate limiting requests. Try the sync again later.'});
    ok(failed.tone === 'bad' && /rate limiting/.test(failed.lines[0]), 'a read failure shows the authored reason');
    const base = {messages_listed: 6, messages_fetched: 6, skipped_already_recorded: 0, not_confirmation: 2, messages_skipped_unreadable: 0, by_confidence: {HIGH: 1, MEDIUM: 3, LOW: 0}, limits_reached: [], complete: true};
    const success = G.syncOutcome({...base, confirmations_recorded: 4}, null);
    ok(success.tone === 'good' && /4 new confirmations saved/.test(success.title), 'success counts what was saved');
    ok(success.lines.some(l => /not linked to applications until you match/.test(l)), 'reading never implies matching');
    ok(success.action === 'match', 'success offers the matching step');
    ok(/1 high confidence, 3 medium confidence/.test(success.lines.join(' ')), 'confidence split is shown');
    const repeated = G.syncOutcome({...base, confirmations_recorded: 0, skipped_already_recorded: 4, by_confidence: {}}, null);
    ok(/No new confirmations/.test(repeated.title) && repeated.action === undefined, 'a repeated check says nothing new');
    ok(repeated.lines.some(l => /4 messages already recorded/.test(l)), 'already recorded messages are counted');
    const partial = G.syncOutcome({...base, confirmations_recorded: 1, complete: false, limits_reached: ['MESSAGE_LIMIT_REACHED', 'BODY_TRUNCATED']}, null);
    ok(partial.tone === 'warn' && /100-message limit/.test(partial.title), 'a partial check names its limit');
    ok(partial.lines.some(l => /continue from where it stopped/.test(l)), 'a partial check says how to continue');
    ok(partial.lines.some(l => /read only in part/.test(l)), 'content limits are noted separately');

    // Step 2 outcomes.
    const matched = G.matchOutcome({processed: 3, considered: 3, revisited: 0, revisits_changed: 0, skipped: 0, linked: 1, needs_review: 2, no_action: 0, limit: 200}, null);
    ok(/Matched 3 new confirmations/.test(matched.title) && matched.action === 'review', 'matching routes to review');
    ok(matched.lines.some(l => /1 application marked Applied/.test(l)) && matched.lines.some(l => /2 of these are waiting/.test(l)), 'matching reports each outcome');
    const mixed = G.matchOutcome({processed: 3, considered: 1, revisited: 2, revisits_changed: 0, skipped: 0, linked: 0, needs_review: 3, no_action: 0, limit: 200}, null);
    ok(/Looked at 1 new confirmation and re-checked 2 messages already waiting \(0 changed\)/.test(mixed.lines[0]), 're-checked items are not presented as new');
    ok(mixed.lines.some(l => /3 of these are waiting/.test(l)), 'waiting counts are scoped to what this run looked at');
    ok(/Nothing new to match/.test(G.matchOutcome({processed: 0, considered: 0, limit: 200}, null).title), 'an empty run says so');
    ok(/stopped at its 2-item limit/.test(G.matchOutcome({processed: 2, considered: 2, limit: 2, linked: 0, needs_review: 2}, null).lines.join(' ')), 'a capped run says to continue');
    ok(/Re-checked/.test(G.matchOutcome({processed: 1, considered: 0, revisited: 1, revisits_changed: 0, limit: 200}, null).title), 'a revisit-only run is not called new');
    ok(/nothing was matched/.test(G.matchOutcome(null, {status: 409, code: '', detail: 'Wait for the current scan or task to finish'}).title), 'busy matching changes nothing');

    // Limits text is specific and truthful.
    const limits = G.limitsText({first_check_days: 30, overlap_days: 1, max_window_days: 90, max_messages_per_check: 100, max_seconds_per_check: 120, max_matched_per_run: 200});
    ok(limits.some(l => /Read-only/.test(l)) && limits.some(l => /no background or scheduled check/.test(l)) && limits.some(l => /second Gmail account is not enabled/.test(l)), 'limits cover scope, schedule and the second account');

    // Initial render: nothing can be pressed before status is known.
    const html = renderToStaticMarkup(React.createElement(V.GmailOperations, {api: async () => ({})}));
    ok(/Check Gmail now/.test(html) && /disabled=""/.test(html), 'checking is unavailable until connected');
    ok(/Unavailable/.test(html) && !/Matched/.test(html), 'no outcome is claimed before anything ran');
    console.log(`${checks} fictional Gmail check-and-match checks passed.`);
  } finally {
    await server.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});

/** #47: render the real Progress components with fictional data and check the wording rules. */
const assert = require('node:assert/strict');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const noop = () => {};
const period = {key: 'this_week', label: 'This week', first_day: '2026-09-14', last_day: '2026-09-20'};
function report(overrides = {}) {
  return {
    generated_at: '2026-09-16T10:00:00+00:00', period,
    applications: {
      submitted: {count: 2, by_source: {USER_ACTION: 1, USER_CONFIRMED_GMAIL_EVIDENCE: 1}, submission_date_not_recorded: 1,
        items: [{application_id: 1, job_id: 11, company: 'Northwind Analytics', title: 'SOC Analyst',
          occurred_at: '2026-09-15T05:00:00+00:00', source_category: 'USER_ACTION'}], truncated: false},
      stage_changes: {count: 1, by_state: {SAVED: 0, VIEWED: 0, ASSESSMENT: 0, INTERVIEW: 1, OFFER: 0, REJECTED: 0, CLOSED: 0},
        date_not_recorded: 0, items: [], truncated: false},
      current: {states: {DISCOVERED: 4, SAVED: 1, APPLIED: 2, VIEWED: 0, ASSESSMENT: 0, INTERVIEW: 1, OFFER: 0, REJECTED: 0, CLOSED: 0},
        total: 8, applications_total: 8, pending_initialization: 0, complete: true},
    },
    gmail: {status: 'NOT_CONNECTED', coverage: {status: 'NOT_CONNECTED', connected: false, sync_state: 'NONE', checked_through: null},
      messages: null, applications: null, by_outcome: {}, low_confidence_not_used: null, not_reconciled_total: null, items: []},
    review: {status: 'OK', total: 0, excluded_other_confidence: 0},
    actions: {followups: {due_now: 0, overdue: 0, next_7_days: 0, date_not_recorded: 0, items: []}, next_actions: {next_7_days: 0, items: []}},
    discovery: {status: 'NOT_RECORDED', new_relevant: null, lower_bound: false, runs_in_period: 1, runs_counted: 0,
      runs_incomplete: 0, runs_unavailable: 1, runs_in_progress: 0, runs_telemetry_error: 0, history_truncated: false,
      retention_days: 90, runs: [{run_id: 7, run_created_at: '2026-09-15T08:00:00+00:00', telemetry_status: 'TELEMETRY_UNAVAILABLE', new: null}]},
    outcomes: {submitted_total: 3, submission_date_not_recorded: 1, rate_minimum: 10,
      interview: {count: 1, of: 3, rate: null, enough_data: false}, offer: {count: 0, of: 3, rate: null, enough_data: false},
      rejected: {count: 0, of: 3, rate: null, enough_data: false}, replies: {count: 0, of: 3, rate: null, enough_data: false},
      weekly: [], by_source: [], by_cv_version: []},
    ...overrides,
  };
}

(async () => {
  const {createServer} = await import('vite');
  const server = await createServer({configFile: false, optimizeDeps: {noDiscovery: true, include: []}, server: {middlewareMode: true}, appType: 'custom', logLevel: 'error'});
  let checks = 0;
  const ok = (value, message) => { assert.ok(value, message); checks += 1; };
  try {
    const M = await server.ssrLoadModule('/src/progressModel.ts');
    const V = await server.ssrLoadModule('/src/Progress.tsx');
    const html = (component, props) => renderToStaticMarkup(React.createElement(component, props));

    // Null is never zero.
    ok(M.countOr(null) === 'Not recorded' && M.countOr(undefined) === 'Not recorded', 'null must not render as a number');
    ok(M.countOr(0) === '0', 'a recorded zero stays zero');
    ok(M.discoveryFigure({status: 'NO_SCANS', runs_in_period: 0}).value === 'No scans', 'no scans is not zero jobs');
    ok(M.discoveryFigure({status: 'NOT_RECORDED', runs_in_period: 2}).value === 'Not recorded', 'unavailable telemetry is not zero');
    const partial = M.discoveryFigure({status: 'INCOMPLETE', new_relevant: 4, runs_in_period: 2, runs_incomplete: 1});
    ok(partial.value === 'At least 4' && /1 incomplete scan/.test(partial.note), 'partial scans are a lower bound');
    ok(M.rateText({count: 1, of: 3, rate: null, enough_data: false}).main === 'Not enough data', 'small samples get no percentage');
    ok(M.rateText({count: 1, of: 10, rate: 0.1, enough_data: true}).main === '10%', 'enough data shows a rate');
    ok(M.gmailFigure({status: 'NOT_CONNECTED'}).value === 'Not connected', 'Gmail absence is stated');

    // Asia/Dubai dates: 20:00 UTC Sunday is Monday in Dubai.
    ok(/^Mon 14 Sep/.test(M.formatDay('2026-09-13T20:00:00+00:00')), 'dates format in Asia/Dubai');
    ok(/^Mon 14 Sep/.test(M.formatDay('2026-09-14')), 'calendar days stay on their Dubai day');
    ok(M.formatDateTime('garbage') === 'Not recorded', 'invalid dates are not invented');

    // Discovery source outcomes: failed, skipped and partial are never "0 jobs".
    ok(M.sourceOutcome({attempted: true, fetch_outcome: 'FAILED', attempt_outcome: 'FAILED'}).countsShown === false, 'failed sources hide counts');
    ok(/^Skipped/.test(M.sourceOutcome({attempted: false, attempt_state: 'SKIPPED_CANCELLED'}).label), 'skipped sources say so');
    ok(/^Incomplete/.test(M.sourceOutcome({attempted: true, fetch_outcome: 'PARTIAL', attempt_outcome: 'PARTIAL', counts_complete: false, incomplete_reason: 'DETAIL_BUDGET_EXHAUSTED'}).label), 'partial sources say so');
    const rows = M.funnelRows({funnel: {NEW: 1, FETCHED: 5, RELEVANT: 2, STRUCTURALLY_VALID: 4, CANONICAL_UNIQUE: 3, LOCATION_COMPATIBLE: 3, ELIGIBILITY_NOT_INCOMPATIBLE: 2},
      funnel_basis: {FETCHED: 'PROVIDER_OBSERVATIONS', STRUCTURALLY_VALID: 'PROVIDER_OBSERVATIONS'},
      funnel_aggregation: {observation_stages: ['FETCHED', 'STRUCTURALLY_VALID'], canonical_stages: ['CANONICAL_UNIQUE', 'LOCATION_COMPATIBLE', 'ELIGIBILITY_NOT_INCOMPATIBLE', 'RELEVANT', 'NEW']}});
    ok(rows.map(r => r.stage).join() === 'FETCHED,STRUCTURALLY_VALID,CANONICAL_UNIQUE,LOCATION_COMPATIBLE,ELIGIBILITY_NOT_INCOMPATIBLE,RELEVANT,NEW', 'funnel follows the payload stage order');
    ok(rows[0].basis === 'observations' && rows[2].basis === 'canonical jobs', 'funnel shows its counting basis');

    // Review outcomes are reported from the #46 response alone.
    const applied = M.reviewOutcome('confirm', {ok: true, applied: true, state: {current_state: 'APPLIED'}}, 'SOC Analyst · Northwind Analytics');
    ok(applied.resolved && /is now Applied/.test(applied.title), 'an applied confirmation says so');
    const stays = M.reviewOutcome('confirm', {ok: true, applied: false, state: {current_state: 'INTERVIEW', reason_code: 'TRANSITION_NOT_PERMITTED'}}, 'Threat Analyst · Litware Defence');
    ok(stays.resolved && /stays at Interview/.test(stays.title) && /did not change/.test(stays.detail), 'a resolved but refused transition is truthful');
    const rejected = M.reviewOutcome('reject', {ok: true, applied: false}, 'x');
    ok(rejected.resolved && /No application was changed/.test(rejected.title), 'reject never claims a change');
    const repeat = M.reviewOutcome('confirm', {ok: false, reason_code: 'LINK_NOT_IN_REVIEW_STATE'}, 'x');
    ok(repeat.resolved && /already resolved/.test(repeat.title), 'repeated resolution is explained');
    const stale = M.reviewOutcome('confirm', {ok: false, reason_code: 'NO_SUFFICIENTLY_STRONG_MATCH'}, 'x');
    ok(!stale.resolved && stale.refresh && /Nothing changed/.test(stale.detail), 'a refused confirmation keeps the item');
    const lost = M.reviewOutcome('confirm', null, 'x', 'The workspace is offline.');
    ok(!lost.resolved && /unknown/.test(lost.title), 'a failed request never claims success');

    // Review item rendering: text only, no raw markup, fail closed without a candidate.
    const hostile = '<img src=x onerror=alert(1)>';
    const base = {link_id: 5, confidence: 'MEDIUM', reason_code: 'NO_CANDIDATE_APPLICATION', received_at: '2026-09-15T05:04:00+00:00',
      platform: 'GREENHOUSE', detected_company: hostile, detected_role: 'SOC Analyst', matched_fields: [], candidates: [],
      proposed_application_id: null, default_application_id: null};
    const itemProps = extra => ({item: {...base, ...extra}, pending: null, busy: false, selected: null, onSelect: noop, onAct: noop, openJob: noop, refCallback: noop});
    const none = html(V.ReviewItem, itemProps({}));
    ok(!none.includes('<img') && none.includes('&lt;img'), 'email-derived text is rendered as text');
    ok(!/Confirm application/.test(none) && /Not my application/.test(none), 'no candidate means no confirm, reject still available');
    ok(/No tracked application matches this message\./.test(none) && /track the application from its job page/.test(none), 'the missing candidate is explained');
    ok(/Medium confidence/.test(none) && /Greenhouse confirmation/.test(none), 'confidence and platform are shown');
    const candidates = [{application_id: 1, job_id: 11, company: 'Northwind Analytics', title: 'SOC Analyst', current_state: 'SAVED', matched_fields: ['COMPANY', 'ROLE', 'DATE_PROXIMITY'], conflicting_fields: [], proposed: false},
      {application_id: 2, job_id: 12, company: 'Northwind Analytics', title: 'SOC Analyst', current_state: 'DISCOVERED', matched_fields: ['COMPANY', 'ROLE', 'SOURCE_PLATFORM'], conflicting_fields: ['APPLICATION_URL'], proposed: false}];
    const ambiguous = html(V.ReviewItem, itemProps({reason_code: 'AMBIGUOUS_MULTIPLE_STRONG_MATCHES', candidates}));
    ok(!/checked=""/.test(ambiguous), 'an ambiguous item pre-selects nothing');
    ok(/Which application does this message confirm\?/.test(ambiguous) && /differs on posting link/.test(ambiguous), 'candidates explain agreement and conflict');
    const proposed = html(V.ReviewItem, {...itemProps({reason_code: 'MEDIUM_CONFIDENCE_NEEDS_USER_REVIEW', candidates: [{...candidates[0], proposed: true}], proposed_application_id: 1, default_application_id: 1}), selected: 1});
    ok((proposed.match(/checked=""/g) || []).length === 1 && /proposed by ASTRA/.test(proposed), 'only the backend proposal is pre-selected');
    for (const forbidden of ['subject', 'sender', 'gmail_message_id', 'noreply@']) ok(!proposed.includes(forbidden), 'no raw message fields: ' + forbidden);

    // Period figures and discovery health: unavailable states are words, not zeros.
    const figures = html(V.PeriodFigures, {data: report(), openJob: noop});
    ok(/Not connected/.test(figures) && /Not recorded/.test(figures), 'absent Gmail and discovery are written out');
    ok(/1 you recorded and 1 confirmed by you from Gmail/.test(figures), 'submissions show their sources');
    ok(/1 application with no recorded submission date/.test(figures), 'undated submissions are disclosed');
    const journey = html(V.Journey, {data: report(), goTo: noop});
    ok(/<caption/.test(journey) && /Not an event/.test(journey), 'the journey is a captioned table; Discovered is not an event');
    const health = html(V.DiscoveryHealth, {data: report(), latestFailed: false, goTo: noop, latest: {status: 'OK', run: {run_created_at: '2026-09-15T08:00:00+00:00', telemetry: {
      funnel: {FETCHED: 5, STRUCTURALLY_VALID: 4, CANONICAL_UNIQUE: 3, LOCATION_COMPATIBLE: 3, ELIGIBILITY_NOT_INCOMPATIBLE: 2, RELEVANT: 2, NEW: 1},
      funnel_basis: {}, counts_complete: false, sources_attempted: 2, sources_succeeded: 1, sources_failed: 1, sources_partial: 0, sources_skipped: 0,
      sources: [{source_id: 1, source_name: 'Fictional board', attempted: true, attempt_outcome: 'OK', fetch_outcome: 'SUCCEEDED', counts_complete: true, funnel: {FETCHED: 5, RELEVANT: 2, NEW: 1}},
        {source_id: 2, source_name: 'Broken fictional board', attempted: true, attempt_outcome: 'FAILED', fetch_outcome: 'FAILED', counts_complete: false, funnel: {FETCHED: 0, RELEVANT: 0, NEW: 0}}]}}}});
    ok(/Run incomplete/.test(health) && /No counts — this source did not finish/.test(health), 'a failed source is not reported as zero jobs');
    ok(/Jobs shown to you: not recorded/.test(health), 'DISPLAYED is unavailable, not zero');
    const next = html(V.NextAction, {data: report({review: {status: 'OK', total: 3}}), goTo: noop});
    ok(/3 Gmail messages/.test(next) && /Review now/.test(next), 'the next action leads with Needs Review');
    console.log(`${checks} fictional Progress wording, privacy and rendering checks passed.`);
  } finally {
    await server.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});

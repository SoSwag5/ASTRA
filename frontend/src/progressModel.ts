/**
 * Pure presentation rules for the #47 Progress, Today and Applications views.
 *
 * Nothing here computes a figure: every number comes from the backend
 * projection (`/api/progress*`) or `/api/search/telemetry`. This module only
 * turns recorded values and bounded codes into words, and decides how an
 * absent, partial or unavailable value is written. Null is never rendered
 * as zero. See docs/architecture/PROGRESS_DASHBOARD.md.
 */
export type Row = Record<string, any>;
export type Tone = 'good' | 'warn' | 'bad' | 'info' | 'neutral';

export const TIMEZONE = 'Asia/Dubai';
export const NOT_RECORDED = 'Not recorded';
export const NOT_ENOUGH_DATA = 'Not enough data';

export const PERIODS: {key: string; label: string}[] = [
  {key: 'this_week', label: 'This week'},
  {key: 'last_week', label: 'Last week'},
  {key: 'last_30_days', label: 'Last 30 days'},
  {key: 'last_90_days', label: 'Last 90 days'},
];

/** Canonical states in progression order (#46 `application_state.STATES`). */
export const STATES = ['DISCOVERED', 'SAVED', 'APPLIED', 'VIEWED', 'ASSESSMENT', 'INTERVIEW',
  'OFFER', 'REJECTED', 'CLOSED'];

export const STATE_LABELS: Record<string, string> = {
  DISCOVERED: 'Discovered', SAVED: 'Saved', APPLIED: 'Applied', VIEWED: 'Viewed',
  ASSESSMENT: 'Assessment', INTERVIEW: 'Interview', OFFER: 'Offer', REJECTED: 'Rejected',
  CLOSED: 'Closed',
};

export const SOURCE_LABELS: Record<string, string> = {
  USER_ACTION: 'you recorded',
  USER_CONFIRMED_GMAIL_EVIDENCE: 'confirmed by you from Gmail',
  GMAIL_PARSER: 'linked from Gmail (high confidence)',
  LEGACY_MIGRATION: 'imported record',
  BROWSER_CONFIRMATION: 'browser confirmation',
  FUTURE_INTEGRATION: 'integration',
};

export const FIELD_LABELS: Record<string, string> = {
  COMPANY: 'Employer', ROLE: 'Role', DATE_PROXIMITY: 'Date within 14 days',
  APPLICATION_URL: 'Posting link', SOURCE_PLATFORM: 'Platform',
};

export const PLATFORM_LABELS: Record<string, string> = {
  GREENHOUSE: 'Greenhouse', LEVER: 'Lever', WORKDAY: 'Workday',
};

/** Why an item is waiting for the user, from #46's bounded reason codes. */
export const REVIEW_REASONS: Record<string, string> = {
  MEDIUM_CONFIDENCE_NEEDS_USER_REVIEW:
    'One tracked application matches, but this message is only medium confidence. Confirm it only if it is about that application.',
  AMBIGUOUS_MULTIPLE_STRONG_MATCHES:
    'More than one tracked application matches equally well. Choose the one this message confirms.',
  CONTRADICTORY_APPLICATION_URL_IDENTITY:
    'The posting link in this message differs from the tracked application’s link. Confirm only if they are the same application.',
  SINGLE_FIELD_AGREEMENT_ONLY:
    'Only one detail matches a tracked application, which is not enough to link them.',
  NO_SUFFICIENTLY_STRONG_MATCH:
    'Some details match a tracked application, but not enough to link them.',
  NO_CANDIDATE_APPLICATION: 'No tracked application matches this message.',
};

export const CONFIDENCE_LABELS: Record<string, string> = {
  HIGH: 'High confidence', MEDIUM: 'Medium confidence',
};

export function stateLabel(state: string | null | undefined): string {
  return state ? STATE_LABELS[state] || state.replaceAll('_', ' ').toLowerCase() : NOT_RECORDED;
}

export function reviewReason(code: string): string {
  return REVIEW_REASONS[code] || 'ASTRA could not link this message by itself.';
}

function validDate(value: unknown): Date | null {
  if (typeof value !== 'string' || !value) return null;
  const date = new Date(value.length === 10 ? value + 'T00:00:00+04:00' : value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "Mon 14 Sep" in Asia/Dubai, or "Not recorded". */
export function formatDay(value: unknown): string {
  const date = validDate(value);
  if (!date) return NOT_RECORDED;
  return new Intl.DateTimeFormat('en-GB', {timeZone: TIMEZONE, weekday: 'short', day: 'numeric',
    month: 'short'}).format(date);
}

/** "14 Sep, 13:04" in Asia/Dubai, or "Not recorded". */
export function formatDateTime(value: unknown): string {
  const date = validDate(value);
  if (!date) return NOT_RECORDED;
  return new Intl.DateTimeFormat('en-GB', {timeZone: TIMEZONE, day: 'numeric', month: 'short',
    hour: '2-digit', minute: '2-digit', hour12: false}).format(date);
}

/** "Mon 14 Sep – Sun 20 Sep" for a projection period. */
export function periodRange(period: Row | null | undefined): string {
  if (!period) return '';
  return `${formatDay(period.first_day)} – ${formatDay(period.last_day)}`;
}

export function plural(count: number, one: string, many = one + 's'): string {
  return `${count.toLocaleString('en-GB')} ${count === 1 ? one : many}`;
}

/** A number, or the words for why there is none. Never turns null into 0. */
export function countOr(value: unknown, absent = NOT_RECORDED): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-GB') : absent;
}

export function joinList(parts: string[]): string {
  const kept = parts.filter(Boolean);
  if (kept.length <= 1) return kept[0] || '';
  return kept.slice(0, -1).join(', ') + ' and ' + kept[kept.length - 1];
}

/** "3 you recorded and 1 confirmed by you from Gmail". */
export function sourceBreakdown(bySource: Row | null | undefined): string {
  return joinList(Object.entries(bySource || {}).filter(([, n]) => Number(n) > 0)
    .map(([source, n]) => `${n} ${SOURCE_LABELS[source] || source.toLowerCase()}`));
}

/** Rates are "n of N"; a percentage only when the backend says N is enough. */
export function rateText(rate: Row | null | undefined): {main: string; detail: string} {
  if (!rate || typeof rate.of !== 'number') return {main: NOT_RECORDED, detail: ''};
  const detail = `${rate.count} of ${plural(rate.of, 'submitted application')}`;
  if (!rate.enough_data || typeof rate.rate !== 'number') return {main: NOT_ENOUGH_DATA, detail};
  return {main: `${Math.round(rate.rate * 100)}%`, detail};
}

/** How the period's discovery figure is written. */
export function discoveryFigure(discovery: Row | null | undefined): {value: string; note: string; tone: Tone} {
  if (!discovery) return {value: NOT_RECORDED, note: '', tone: 'neutral'};
  const runs = plural(discovery.runs_in_period || 0, 'scan');
  switch (discovery.status) {
    case 'NO_SCANS':
      return {value: 'No scans', note: 'No discovery scan ran in this period.', tone: 'neutral'};
    case 'NOT_RECORDED':
      return {value: NOT_RECORDED, note: `${runs} ran, but none has usable telemetry.`, tone: 'warn'};
    case 'INCOMPLETE': {
      const gaps = [
        discovery.runs_incomplete ? plural(discovery.runs_incomplete, 'incomplete scan') : '',
        discovery.runs_unavailable ? plural(discovery.runs_unavailable, 'scan') + ' without telemetry' : '',
        discovery.runs_telemetry_error ? plural(discovery.runs_telemetry_error, 'scan') + ' with a telemetry error' : '',
        discovery.runs_in_progress ? plural(discovery.runs_in_progress, 'scan') + ' still running' : '',
        discovery.history_truncated ? 'older scans beyond the read limit' : '',
      ];
      return {value: `At least ${countOr(discovery.new_relevant)}`,
        note: `${runs}; not counted in full: ${joinList(gaps)}.`, tone: 'warn'};
    }
    default:
      return {value: countOr(discovery.new_relevant), note: `${runs}, all complete.`, tone: 'neutral'};
  }
}

/** How the period's Gmail figure is written. */
export function gmailFigure(gmail: Row | null | undefined): {value: string; note: string} {
  if (!gmail || gmail.status === 'UNAVAILABLE') return {value: 'Unavailable', note: 'Gmail evidence could not be read.'};
  if (gmail.status === 'NOT_CONNECTED') return {value: 'Not connected', note: 'Connect Gmail under Privacy & Local Data to detect confirmations.'};
  const coverage = gmail.coverage || {};
  const covered = coverage.sync_state === 'COMPLETE'
    ? `Checked through ${formatDateTime(coverage.checked_through)}.`
    : coverage.sync_state === 'INCOMPLETE' ? 'The last Gmail sync did not finish, so messages may be missing.'
      : 'Gmail has not completed a sync, so messages may be missing.';
  return {value: countOr(gmail.messages), note: covered};
}

/** Latest-run headline for discovery health. */
export function runHeadline(latest: Row | null | undefined): {label: string; tone: Tone; detail: string} {
  if (!latest) return {label: 'Unavailable', tone: 'neutral', detail: 'Discovery telemetry could not be read.'};
  if (latest.status === 'NO_DATA') return {label: 'No scans yet', tone: 'neutral', detail: 'No discovery scan is recorded in the last 90 days.'};
  const run = latest.run || {};
  if (latest.status === 'RUN_IN_PROGRESS') return {label: 'Scan running', tone: 'info', detail: `Started ${formatDateTime(run.run_created_at)}.`};
  if (latest.status === 'TELEMETRY_UNAVAILABLE') return {label: 'Telemetry unavailable', tone: 'warn', detail: `The latest scan (${formatDateTime(run.run_created_at)}) has no funnel telemetry.`};
  const t = run.telemetry || {};
  if (!t.funnel) return {label: 'Telemetry error', tone: 'bad', detail: 'This scan’s counts could not be finalized, so none are shown.'};
  const failed = t.sources_failed || 0, partial = t.sources_partial || 0, skipped = t.sources_skipped || 0;
  const detail = joinList([
    `${t.sources_succeeded || 0} of ${plural(t.sources_attempted || 0, 'source')} complete`,
    failed ? `${failed} failed` : '', partial ? `${partial} partial` : '', skipped ? `${skipped} skipped` : '']);
  if (t.counts_complete) return {label: 'Complete', tone: 'good', detail};
  return {label: 'Run incomplete', tone: 'warn', detail: detail + '. Counts are a lower bound.'};
}

const STAGE_ORDER = ['FETCHED', 'STRUCTURALLY_VALID', 'CANONICAL_UNIQUE', 'LOCATION_COMPATIBLE',
  'ELIGIBILITY_NOT_INCOMPATIBLE', 'RELEVANT', 'NEW'];
export const STAGE_LABELS: Record<string, string> = {
  FETCHED: 'Fetched', STRUCTURALLY_VALID: 'Valid postings', CANONICAL_UNIQUE: 'Unique jobs',
  LOCATION_COMPATIBLE: 'Location fits', ELIGIBILITY_NOT_INCOMPATIBLE: 'Eligibility not ruled out',
  RELEVANT: 'Relevant', NEW: 'New to ASTRA',
};

/** Funnel rows keyed off the payload's own stage order (#43 `FUNNEL_STAGES`). */
export function funnelRows(t: Row | null | undefined): {stage: string; label: string; value: number; basis: string}[] {
  if (!t || !t.funnel) return [];
  const aggregation = t.funnel_aggregation || {};
  const declared = [...(aggregation.observation_stages || []), ...(aggregation.canonical_stages || [])];
  const order = declared.length ? declared : STAGE_ORDER;
  return order.filter(stage => typeof t.funnel[stage] === 'number').map(stage => ({
    stage, label: STAGE_LABELS[stage] || stage, value: t.funnel[stage],
    basis: (t.funnel_basis || {})[stage] === 'PROVIDER_OBSERVATIONS' ? 'observations' : 'canonical jobs',
  }));
}

const SKIP_LABELS: Record<string, string> = {
  SKIPPED_NOT_DUE: 'not due', SKIPPED_NOT_TARGETED: 'not in this scan', SKIPPED_DISABLED: 'disabled',
  SKIPPED_CANCELLED: 'cancelled', SKIPPED_SCOPE_CHANGED: 'changed after confirmation',
};

/** One source's outcome. A failed, skipped or partial source is never "0 jobs". */
export function sourceOutcome(source: Row): {label: string; tone: Tone; countsShown: boolean} {
  if (!source.attempted) {
    return {label: 'Skipped — ' + (SKIP_LABELS[source.attempt_state] || 'not attempted'), tone: 'neutral', countsShown: false};
  }
  if (source.attempt_outcome === 'INGESTION_FAILED') return {label: 'Failed while saving — nothing kept', tone: 'bad', countsShown: false};
  if (source.fetch_outcome === 'FAILED' || source.attempt_outcome === 'FAILED') return {label: 'Failed', tone: 'bad', countsShown: false};
  if (!source.counts_complete) {
    const reason = String(source.incomplete_reason || '').replaceAll('_', ' ').toLowerCase();
    return {label: 'Incomplete' + (reason ? ' — ' + reason : ''), tone: 'warn', countsShown: true};
  }
  return {label: source.health === 'EMPTY' ? 'Complete — no postings' : 'Complete', tone: 'good', countsShown: true};
}

export type ReviewAction = 'confirm' | 'reject';
export type ReviewOutcome = {tone: Tone; title: string; detail: string; resolved: boolean; refresh: boolean};

/**
 * What the user is told after confirm/reject, from the #46 response alone.
 * `label` is the chosen application's "Role · Employer".
 */
export function reviewOutcome(action: ReviewAction, response: Row | null, label: string, failure?: string): ReviewOutcome {
  if (!response) {
    return {tone: 'bad', resolved: false, refresh: true,
      title: 'The request did not complete, so the result is unknown.',
      detail: (failure ? failure + ' ' : '') + 'The queue has been refreshed; check this message before trying again.'};
  }
  if (response.ok !== true) {
    switch (response.reason_code) {
      case 'LINK_NOT_IN_REVIEW_STATE':
        return {tone: 'warn', resolved: true, refresh: true, title: 'This message was already resolved.',
          detail: 'It may have been handled in another window. Nothing changed here.'};
      case 'NO_SUFFICIENTLY_STRONG_MATCH':
        return {tone: 'warn', resolved: false, refresh: true, title: 'That application no longer matches this message.',
          detail: 'Nothing changed. The choices have been refreshed.'};
      default:
        return {tone: 'bad', resolved: false, refresh: true, title: 'ASTRA could not use this message.',
          detail: 'Nothing changed. The evidence is incomplete or of an unsupported kind.'};
    }
  }
  if (action === 'reject') {
    return {tone: 'neutral', resolved: true, refresh: false, title: 'Rejected. No application was changed.',
      detail: 'The message stays in Gmail evidence but will not be linked to an application.'};
  }
  const state = response.state || {};
  if (response.applied) {
    return {tone: 'good', resolved: true, refresh: false,
      title: `Confirmed. ${label} is now ${stateLabel(state.current_state)}.`,
      detail: 'Recorded as your confirmation, with this Gmail message as its evidence.'};
  }
  return {tone: 'info', resolved: true, refresh: false,
    title: `Confirmed. ${label} stays at ${stateLabel(state.current_state)}.`,
    detail: 'It was already at that stage or later, so its state did not change. The message is resolved.'};
}

export function candidateLabel(candidate: Row | null | undefined): string {
  if (!candidate) return 'The application';
  const parts = [candidate.title, candidate.company].filter(Boolean);
  return parts.length ? parts.join(' · ') : `Application #${candidate.application_id}`;
}

export function readStored(key: string, fallback: string, allowed: string[]): string {
  try {
    const value = window.localStorage.getItem(key);
    return value && allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

export function writeStored(key: string, value: string): void {
  try { window.localStorage.setItem(key, value); } catch { /* storage unavailable */ }
}

// ---------------------------------------------------------------------------
// "No reply for 90 days" (#47 follow-up C)
// ---------------------------------------------------------------------------
export const NO_REPLY_RULE = [
  'Shown when an application was submitted on a recorded date at least 90 days ago (Asia/Dubai calendar days), its recorded stage is still Applied, and no employer reply has been recorded.',
  'Automated receipts and Gmail confirmations are not replies. An imported application counts only if its record carries an applied date.',
  'It is an inference, not something the employer said, so ASTRA never records it as a rejection. Closing it is your decision and is never counted as a rejection either.',
];

/** What an application row says about a missing reply, if anything. */
export function noReplyText(status: Row | null | undefined): {badge: string; tone: Tone; line: string} | null {
  if (!status) return null;
  if (status.status === 'NO_REPLY_90_DAYS') {
    return {badge: 'No reply for 90 days', tone: 'warn',
      line: `${status.days_since_submission} days since you applied, with no employer reply recorded.`};
  }
  if (status.status === 'CLOSED_NO_RESPONSE') {
    return {badge: 'Closed by you: no response', tone: 'neutral',
      line: `${status.closed_on ? 'Closed ' + formatDay(status.closed_on) + '. ' : ''}Its recorded stage is unchanged and it is not counted as a rejection. Set a new stage from the job’s detail view to reopen it.`};
  }
  if (status.status === 'REPLY_AFTER_CLOSE') {
    return {badge: 'Reply recorded after you closed it', tone: 'info',
      line: 'Set its new stage from the job’s detail view to reopen it.'};
  }
  return null;
}

export function closeNoReplyNote(status: Row): string {
  return `Closed as No response: no employer reply recorded ${status.days_since_submission} days after submission on ${status.submitted_on}.`;
}

// ---------------------------------------------------------------------------
// Progress rails (#47 visual revision)
// ---------------------------------------------------------------------------
/**
 * A rail is drawn only from a recorded numerator and a recorded or saved
 * denominator. When either is missing the rail is unavailable and says why;
 * it never shows an estimated or partial fill.
 */
export type RailTone = 'series' | 'series-2' | 'series-3' | 'good' | 'warn' | 'bad' | 'neutral' | 'muted';
export type RailSegment = {key: string; label: string; count: number; tone: RailTone};
export type Rail = {
  available: boolean;
  /** Recorded numerator and denominator; null when unavailable. */
  value: number | null;
  max: number | null;
  /** Filled parts in order; together they never exceed `max`. */
  segments: RailSegment[];
  headline: string;
  /** Visible copy saying what the bar measures. */
  meaning: string;
  note: string;
  /** Text for assistive technology, stating the numbers. */
  valueText: string;
  tone: Tone;
  live?: boolean;
};

const whole = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value) && value >= 0;

function unavailable(headline: string, meaning: string, note = ''): Rail {
  return {available: false, value: null, max: null, segments: [], headline, meaning, note, valueText: headline, tone: 'neutral'};
}

/**
 * This week's submissions against the weekly target saved in the Campaign
 * plan. `savedCampaign` must be the stored plan (`/api/settings` → campaign),
 * which exists only once the person has saved it, never the defaults: null
 * means no plan is saved, undefined means the settings could not be read.
 */
export function weeklyTargetRail(outcomes: Row | null | undefined, savedCampaign: Row | null | undefined): Rail {
  const meaning = 'Applications recorded as submitted this week (Monday to Sunday, Asia/Dubai), against the weekly target saved in your Campaign plan.';
  if (savedCampaign === undefined) return unavailable('Unavailable', meaning, 'Your Campaign plan could not be read.');
  const target = savedCampaign?.weekly_target;
  if (!whole(target) || target === 0) {
    return unavailable('No weekly target saved', meaning,
      'Save a weekly target in Settings › Career focus › Campaign plan to measure this week against it.');
  }
  const weeks: Row[] = Array.isArray(outcomes?.weekly) ? outcomes!.weekly : [];
  const week = weeks[weeks.length - 1];
  if (!week || !whole(week.submitted)) return unavailable('Not recorded', meaning, 'This week’s submissions could not be read.');
  const done = week.submitted;
  const undated = whole(outcomes?.submission_date_not_recorded) ? outcomes!.submission_date_not_recorded : 0;
  const status = done > target ? `${done - target} more than your target` : done === target ? 'Target reached' : `${target - done} to reach your target`;
  return {
    available: true, value: done, max: target,
    segments: done ? [{key: 'submitted', label: 'Submitted this week', count: Math.min(done, target), tone: 'series'}] : [],
    headline: `${done} of ${target}`, meaning,
    note: status + '.' + (undated ? ` ${plural(undated, 'submission')} without a recorded date ${undated === 1 ? 'is' : 'are'} not counted.` : ''),
    valueText: `${plural(done, 'application')} submitted this week, of a target of ${target}`,
    tone: done >= target ? 'good' : 'neutral',
  };
}

const STAGE_TONES: Record<string, RailTone> = {
  DISCOVERED: 'muted', SAVED: 'neutral', APPLIED: 'series', VIEWED: 'series', ASSESSMENT: 'series-2',
  INTERVIEW: 'series-2', OFFER: 'good', REJECTED: 'series-3', CLOSED: 'series-3',
};

/** Tracked applications by their recorded current stage. Segments add up to the total. */
export function stageRail(current: Row | null | undefined): Rail {
  const meaning = 'Each part is the number of tracked applications at that recorded stage now. Together the parts make up every tracked application.';
  if (!current || !whole(current.total)) return unavailable('Unavailable', meaning, 'Application stages could not be read.');
  if (current.complete === false || (whole(current.pending_initialization) && current.pending_initialization > 0)) {
    return unavailable('Unavailable', meaning, 'Some application stages have not been read yet. Refresh to retry; a partial total is not shown as the whole.');
  }
  if (current.total === 0) return unavailable('No applications tracked', meaning, 'Track a job from its detail view and it will appear here with its stage.');
  const states: Row = current.states || {};
  const segments: RailSegment[] = STATES.filter(state => whole(states[state]) && states[state] > 0)
    .map(state => ({key: state, label: STATE_LABELS[state], count: states[state], tone: STAGE_TONES[state] || 'neutral'}));
  const counted = segments.reduce((sum, s) => sum + s.count, 0);
  if (counted !== current.total || (whole(current.applications_total) && current.applications_total !== current.total)) return unavailable('Unavailable', meaning, 'The recorded stage counts do not match the total, so none are drawn.');
  const summary = joinList(segments.map(s => `${s.count} ${s.label.toLowerCase()}`));
  return {
    available: true, value: current.total, max: current.total, segments,
    headline: plural(current.total, 'application'), meaning,
    note: '',
    valueText: `${plural(current.total, 'tracked application')}: ${summary}`,
    tone: 'neutral',
  };
}

/**
 * Sources finished by the running scan (from /api/scan/status), or how each
 * source in the latest finished scan ended (from its telemetry).
 */
export function scanRail(status: Row | null | undefined, latest: Row | null | undefined): Rail {
  if (!status) return unavailable('Unavailable', 'Sources finished by the running or latest scan.', 'Current scan status could not be read. Refresh to retry.');
  const active = status?.active;
  const progress = active?.progress;
  if (active && progress && whole(progress.sources_total) && progress.sources_total > 0 && whole(progress.sources_done)) {
    if (progress.sources_done > progress.sources_total) return unavailable('Unavailable', 'Sources finished by the running scan.', 'Recorded source counts are inconsistent.');
    const done = progress.sources_done, total = progress.sources_total;
    return {
      available: true, live: true, value: done, max: total,
      segments: done ? [{key: 'done', label: 'Finished', count: done, tone: 'series'}] : [],
      headline: `${done} of ${plural(total, 'source')}`,
      meaning: 'Sources the running scan has finished, out of the sources it confirmed when it started.',
      note: active.cancel_requested_at ? 'Stopping: no new source will start.'
        : progress.current_source ? `Now checking ${progress.current_source}.` : 'Running.',
      valueText: `Scan running: ${done} of ${plural(total, 'source')} finished`, tone: 'info',
    };
  }
  if (active) return {...unavailable('Scan starting', 'Sources the running scan has finished.', 'Source counts are not recorded yet.'), live: true, tone: 'info'};
  const meaning = 'How each source in the latest finished scan ended, out of the sources it tried.';
  if (!latest) return unavailable('Unavailable', meaning, 'Discovery telemetry could not be read.');
  if (latest.status === 'NO_DATA') return unavailable('No scans yet', meaning, 'No discovery scan is recorded in the last 90 days.');
  const t = latest.run?.telemetry;
  if (!t || !t.funnel || !whole(t.sources_attempted)) return unavailable('Not recorded', meaning, 'The latest scan has no source telemetry.');
  const attempted = t.sources_attempted;
  if (attempted === 0) return unavailable('No sources tried', meaning, 'The latest scan did not try any source.');
  if (![t.sources_succeeded, t.sources_partial, t.sources_failed].every(whole)) {
    return unavailable('Unavailable', meaning, 'The latest scan has incomplete source outcome counts.');
  }
  const count = (value: unknown) => whole(value) ? value : 0;
  const ok = count(t.sources_succeeded), partial = count(t.sources_partial), failed = count(t.sources_failed);
  if (ok + partial + failed > attempted) return unavailable('Not recorded', meaning, 'The recorded source outcomes do not add up, so none are drawn.');
  const segments: RailSegment[] = ([
    {key: 'ok', label: 'Complete', count: ok, tone: 'series'},
    {key: 'partial', label: 'Partial', count: partial, tone: 'warn'},
    {key: 'failed', label: 'Failed', count: failed, tone: 'bad'},
  ] as RailSegment[]).filter(s => s.count > 0);
  const other = attempted - ok - partial - failed;
  if (other > 0) segments.push({key: 'other', label: 'Outcome not recorded', count: other, tone: 'muted'});
  const skipped = count(t.sources_skipped);
  return {
    available: true, value: ok, max: attempted, segments,
    headline: `${ok} of ${plural(attempted, 'source')} complete`, meaning,
    note: `Started ${formatDateTime(latest.run?.run_created_at)}.` + (skipped ? ` ${plural(skipped, 'source')} not tried in this scan.` : ''),
    valueText: `Latest scan: ${ok} of ${plural(attempted, 'source')} complete` + (partial ? `, ${partial} partial` : '') + (failed ? `, ${failed} failed` : ''),
    tone: failed ? 'bad' : partial || other ? 'warn' : 'good',
  };
}

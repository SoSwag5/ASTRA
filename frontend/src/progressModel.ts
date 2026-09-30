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

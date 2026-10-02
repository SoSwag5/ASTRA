/**
 * Wording for the Gmail check-and-match controls (#47 follow-up B). Pure, so
 * every outcome - disconnected, busy, partial, failed, repeated, successful -
 * is testable. The two steps are reported separately: reading Gmail never
 * implies that anything was matched to an application.
 */
export type Row = Record<string, any>;
export type Tone = 'good' | 'warn' | 'bad' | 'info' | 'neutral';
export type Outcome = {tone: Tone; title: string; lines: string[]; action?: 'reconnect' | 'connect' | 'review' | 'match'};
export type Failure = {status: number; code: string; detail: string};

const count = (n: number, one: string, many = one + 's') => `${n.toLocaleString('en-GB')} ${n === 1 ? one : many}`;

function day(value: unknown): string {
  const date = typeof value === 'string' ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return 'an unrecorded date';
  return new Intl.DateTimeFormat('en-GB', {timeZone: 'Asia/Dubai', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false}).format(date);
}

/** Why the controls are or are not available, from `/api/progress/gmail`. */
export function connectionState(status: Row | null): {connected: boolean; label: string; detail: string; tone: Tone} {
  if (!status || status.status === 'UNAVAILABLE') {
    return {connected: false, label: 'Unavailable', tone: 'neutral', detail: 'Gmail evidence has not been set up in this workspace.'};
  }
  const coverage = status.coverage || {};
  if (status.connection === 'DISCONNECTED_INCONSISTENT') {
    return {connected: false, label: 'Reconnect needed', tone: 'warn', detail: 'A saved connection has no stored credential, so ASTRA treats Gmail as disconnected. Reconnect it in Settings › Gmail & permissions.'};
  }
  if (status.connection !== 'CONNECTED') {
    return {connected: false, label: 'Not connected', tone: 'neutral', detail: 'Connect Gmail (read-only) in Settings › Gmail & permissions before checking for confirmations.'};
  }
  const detail = coverage.sync_state === 'COMPLETE' ? `Last complete check covered mail up to ${day(coverage.checked_through)}.`
    : coverage.sync_state === 'INCOMPLETE' ? 'The last check stopped before finishing. The next check continues from where it stopped.'
      : 'Gmail has not been checked yet. The first check looks back up to 30 days.';
  return {connected: true, label: 'Connected, read-only', tone: 'good', detail};
}

const STOP_REASONS: Record<string, string> = {
  TIME_LIMIT_REACHED: 'the two-minute time limit',
  MESSAGE_LIMIT_REACHED: 'the 100-message limit',
  PAGE_LIMIT_REACHED: 'the page limit',
  INCOMPLETE: 'an unfinished page',
};
const CONTENT_NOTES: Record<string, string> = {
  BODY_TRUNCATED: 'a long message was read only in part',
  MALFORMED_PART_SKIPPED: 'a malformed part of a message was skipped',
  MIME_DEPTH_EXCEEDED: 'a deeply nested message was read only in part',
  MIME_PART_LIMIT_REACHED: 'a message with many parts was read only in part',
  UNSAFE_LINKS_DROPPED: 'unsafe links in a message were ignored',
};

/** What happened when Gmail was read. Never mentions matching as done. */
export function syncOutcome(result: Row | null, failure: Failure | null): Outcome {
  if (failure) {
    if (failure.status === 409 || failure.code === 'SYNC_ALREADY_RUNNING') {
      return {tone: 'warn', title: 'Another task is running, so Gmail was not checked.',
        lines: ['A scan, export, deletion or another Gmail check holds ASTRA’s task lock. Nothing was read. Try again when it finishes.']};
    }
    if (['ACCOUNT_NOT_CONNECTED', 'TOKEN_REFRESH_FAILED', 'GMAIL_READ_UNAUTHORIZED', 'AUTHORIZATION_EXPIRED'].includes(failure.code)) {
      return {tone: 'bad', title: 'Gmail needs to be reconnected.', action: 'reconnect',
        lines: [failure.detail || 'ASTRA could not use the stored connection.', 'Nothing was read and nothing changed.']};
    }
    return {tone: 'bad', title: 'Gmail could not be checked.',
      lines: [failure.detail || 'The check did not finish.', 'Confirmations saved before the failure are kept; the next check continues safely.']};
  }
  if (!result) return {tone: 'neutral', title: '', lines: []};
  const saved = result.confirmations_recorded || 0;
  const confidence = result.by_confidence || {};
  const parts = ['HIGH', 'MEDIUM', 'LOW'].filter(level => confidence[level]).map(level => `${confidence[level]} ${level.toLowerCase()} confidence`);
  const lines = [`Read ${count(result.messages_fetched || 0, 'message')} matching ASTRA’s confirmation search (${count(result.messages_listed || 0, 'result')} listed).`];
  if (saved) lines.push(`Saved ${count(saved, 'new confirmation')}${parts.length ? ` (${parts.join(', ')})` : ''}. They are not linked to applications until you match them.`);
  if (result.skipped_already_recorded) lines.push(`${count(result.skipped_already_recorded, 'message')} already recorded, so ${result.skipped_already_recorded === 1 ? 'it was' : 'they were'} skipped.`);
  if (result.not_confirmation) lines.push(`${count(result.not_confirmation, 'message')} did not look like an application confirmation and ${result.not_confirmation === 1 ? 'was' : 'were'} not kept.`);
  if (result.messages_skipped_unreadable) lines.push(`${count(result.messages_skipped_unreadable, 'message')} could not be read and ${result.messages_skipped_unreadable === 1 ? 'was' : 'were'} skipped.`);
  const notes = (result.limits_reached || []).filter((token: string) => token in CONTENT_NOTES).map((token: string) => CONTENT_NOTES[token]);
  if (notes.length) lines.push(`Note: ${notes.join('; ')}.`);
  if (!result.complete) {
    const stops = (result.limits_reached || []).filter((token: string) => token in STOP_REASONS).map((token: string) => STOP_REASONS[token]);
    return {tone: 'warn', title: `Stopped at ${stops.length ? stops.join(' and ') : 'a limit'} before finishing.`,
      lines: [...lines, 'Check again to continue from where it stopped.'], action: saved ? 'match' : undefined};
  }
  if (!saved) return {tone: 'good', title: 'Gmail checked. No new confirmations.', lines};
  return {tone: 'good', title: `Gmail checked. ${count(saved, 'new confirmation')} saved.`, lines, action: 'match'};
}

/** What happened when confirmations were matched to applications. */
export function matchOutcome(result: Row | null, failure: Failure | null): Outcome {
  if (failure) {
    if (failure.status === 409) {
      return {tone: 'warn', title: 'Another task is running, so nothing was matched.',
        lines: ['A scan, export, deletion or Gmail check holds ASTRA’s task lock. Nothing changed. Try again when it finishes.']};
    }
    return {tone: 'bad', title: 'Matching did not run.', lines: [failure.detail || 'Nothing changed.']};
  }
  if (!result) return {tone: 'neutral', title: '', lines: []};
  // Every count below covers exactly the items this run looked at: new
  // confirmations plus already-waiting items it re-checked.
  const lines: string[] = [];
  const are = (n: number) => (n === 1 ? 'is' : 'are');
  lines.push(`Looked at ${count(result.considered || 0, 'new confirmation')}${result.revisited ? ` and re-checked ${count(result.revisited, 'message')} already waiting (${result.revisits_changed || 0} changed)` : ''}.`);
  if (result.linked) lines.push(`${count(result.linked, 'application')} marked Applied from a high-confidence confirmation with one clear match.`);
  if (result.needs_review) lines.push(`${result.needs_review} of these ${are(result.needs_review)} waiting for your decision.`);
  if (result.no_action) lines.push(`${result.no_action} of these ${are(result.no_action)} not used (low confidence, already recorded on the application, or unusable).`);
  if (result.skipped) lines.push(`${count(result.skipped, 'item')} had already been settled and ${result.skipped === 1 ? 'was' : 'were'} skipped.`);
  if (!result.processed) return {tone: 'good', title: 'Nothing new to match.', lines: ['Every saved confirmation already has a decision.']};
  const more = result.processed >= result.limit;
  if (more) lines.push(`This run stopped at its ${result.limit}-item limit; match again to continue.`);
  const title = result.considered ? `Matched ${count(result.considered, 'new confirmation')}.` : 'Re-checked the messages waiting for review.';
  return {tone: result.needs_review ? 'info' : 'good', title,
    lines, action: result.needs_review ? 'review' : undefined};
}

export function limitsText(limits: Row | undefined): string[] {
  const l = limits || {};
  return [
    'Read-only: ASTRA never sends, deletes, archives or changes email.',
    'Only messages matching ASTRA’s application-confirmation search are read; bodies are read in memory and never stored.',
    `The first check looks back ${l.first_check_days ?? 30} days; later checks continue from the last complete check with a ${l.overlap_days ?? 1}-day overlap, never more than ${l.max_window_days ?? 90} days back.`,
    `Each check reads at most ${l.max_messages_per_check ?? 100} messages in about ${Math.round((l.max_seconds_per_check ?? 120) / 60)} minutes; matching handles up to ${l.max_matched_per_run ?? 200} items per run.`,
    'Checks run only when you press the button. There is no background or scheduled check, and the second Gmail account is not enabled.',
  ];
}

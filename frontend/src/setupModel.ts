/**
 * Setup and search-focus rules (beta 3), kept apart from the components so
 * the checks can exercise every success and failure path.
 */
export type Row = Record<string, any>;
export type Outcome = {tone: 'good' | 'bad' | 'warn' | 'info'; title: string; text?: string};

export const errorText = (error: any) =>
  (error && typeof error.message === 'string' && error.message.trim()) || 'That did not finish. Try again.';

export const lines = (text: string) => text.split('\n').map(line => line.trim()).filter(Boolean);

/** Unsaved search-focus choices, compared with what the server last saved. */
export function isFocusDirty(selected: string[], custom: string, cfg: Row): boolean {
  return selected.join('\n') !== (cfg.career_tracks || []).join('\n')
    || lines(custom).join('\n') !== (cfg.custom_target_roles || []).join('\n');
}

/** The saved focus in words, as the server last reported it. */
export function focusSummary(cfg: Row, tracks: Row[]): string {
  return [...(cfg.custom_target_roles || []), ...(cfg.career_tracks || []).map((id: string) => tracks.find(t => t.id === id)?.label || id)].join(', ');
}

/** Why Continue is unavailable, in words; '' when it is available. */
export function continueHint(step: number, profile: Row | null, cfg: Row, focusDirty: boolean): string {
  if (step === 1 && !profile) return 'Import your CV to continue.';
  if (step === 2 && !profile?.confirmed) return 'Confirm your CV facts to continue. If something is wrong, correct your profile first.';
  if (step === 4 && focusDirty) return 'You have unsaved choices. Save your search focus to continue.';
  if (step === 4 && !cfg.search_focus_confirmed) return 'Choose at least one job and save your search focus to continue.';
  return '';
}

/**
 * One write, then a refresh of the workspace. Success is reported only when
 * both finished. A write that succeeded before the refresh failed is reported
 * as saved but unconfirmed, so the next step is a refresh, never a second
 * write. A failed write reports the server's reason and claims nothing.
 */
export type StepWords = {failed: string; saved: (result: any) => Outcome; unconfirmed: string; failureHint?: string};
export async function writeThenRefresh<T>(write: () => Promise<T>, reload: () => Promise<any>, words: StepWords):
  Promise<{written: boolean; refreshed: boolean; result?: T; outcome: Outcome}> {
  let result: T;
  try { result = await write(); }
  catch (error) {
    return {written: false, refreshed: false, outcome: {tone: 'bad', title: words.failed, text: [errorText(error), words.failureHint].filter(Boolean).join(' ')}};
  }
  try { await reload(); }
  catch (error) {
    return {written: true, refreshed: false, result, outcome: {tone: 'warn', title: words.unconfirmed,
      text: `${errorText(error)} Use Refresh to check again. Nothing needs to be saved twice.`}};
  }
  return {written: true, refreshed: true, result, outcome: words.saved(result)};
}

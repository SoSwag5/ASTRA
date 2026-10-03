/**
 * Pure rules for Settings and appearance (#47 follow-up A). No React, no I/O,
 * so the unsaved-change and wording rules are testable on their own.
 */
export type Row = Record<string, any>;
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';
export type ThemePreference = 'dark' | 'light' | 'system';
export type MotionPreference = 'system' | 'reduced' | 'full';

export const SECTIONS: {id: string; label: string; summary: string}[] = [
  {id: 'focus', label: 'Career focus', summary: 'What ASTRA searches for and how it ranks what it finds.'},
  {id: 'profile', label: 'Profile & CV', summary: 'Your master CV, confirmed career facts and application answers.'},
  {id: 'sources', label: 'Discovery sources', summary: 'The public company boards a scan checks.'},
  {id: 'permissions', label: 'Gmail & permissions', summary: 'What ASTRA may read, send or prepare on your behalf.'},
  {id: 'appearance', label: 'Appearance', summary: 'Theme and motion in this browser.'},
  {id: 'privacy', label: 'Privacy & local data', summary: 'Where your data lives, backups, export and deletion.'},
  {id: 'workspace', label: 'Workspace', summary: 'Setup, the Excel tracker and application limits.'},
];

export function sectionLabel(id: string): string {
  return SECTIONS.find(section => section.id === id)?.label || 'Settings';
}

/** One list item per non-empty line, trimmed. */
export function linesToList(text: unknown): string[] {
  if (Array.isArray(text)) return text.map(item => String(item).trim()).filter(Boolean);
  return String(text ?? '').split('\n').map(line => line.trim()).filter(Boolean);
}

export function listToLines(list: unknown): string {
  return linesToList(list).join('\n');
}

/**
 * The comparable form of a settings value, so formatting-only edits (a
 * trailing blank line, whitespace around a list item) are not "unsaved".
 */
export function normalizeValue(value: unknown): unknown {
  if (Array.isArray(value)) return linesToList(value).join('\n');
  if (typeof value === 'string') return value.includes('\n') ? linesToList(value).join('\n') : value.trim();
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value as Row).sort().map(key => [key, normalizeValue((value as Row)[key])]));
  }
  return value ?? null;
}

export function changedKeys(saved: Row, draft: Row, keys: string[]): string[] {
  return keys.filter(key => JSON.stringify(normalizeValue(saved?.[key])) !== JSON.stringify(normalizeValue(draft?.[key])));
}

export function isDirty(saved: Row, draft: Row, keys: string[]): boolean {
  return changedKeys(saved, draft, keys).length > 0;
}

/** Only the named keys, as they would be sent. List fields become arrays. */
export function payload(draft: Row, keys: string[], listKeys: string[] = []): Row {
  return Object.fromEntries(keys.map(key => [key, listKeys.includes(key) ? linesToList(draft[key]) : draft[key]]));
}

function clock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-GB', {hour: '2-digit', minute: '2-digit', hour12: false}).format(date);
}

/** The words beside a save button. Never claims a save that did not happen. */
export function saveStatusText(status: SaveStatus, dirty: boolean, savedAt = '', error = ''): string {
  if (status === 'saving') return 'Saving…';
  if (status === 'error') return error ? `Not saved: ${error}` : 'Not saved. Your changes are kept here; try again.';
  if (dirty) return 'Unsaved changes';
  if (status === 'saved') return savedAt ? `Saved at ${clock(savedAt)}` : 'Saved';
  return 'All changes saved';
}

export function resolveTheme(preference: ThemePreference, prefersLight: boolean): 'dark' | 'light' {
  if (preference === 'system') return prefersLight ? 'light' : 'dark';
  return preference;
}

/** Where an explicit theme choice is stored (#47 visual revision). */
export const THEME_CHOICE_KEY = 'themeChoice';

/**
 * Preserve valid legacy preferences too: an automatically stored dark value
 * cannot be distinguished from a deliberate choice. Only a new browser with
 * no valid preference defaults to light. theme-boot.js mirrors this rule.
 */
export function initialTheme(storage: Pick<Storage, 'getItem'> | null | undefined): ThemePreference {
  try {
    const chosen = storage?.getItem(THEME_CHOICE_KEY);
    if (chosen === 'dark' || chosen === 'light' || chosen === 'system') return chosen;
    const legacy = storage?.getItem('theme');
    if (legacy === 'dark' || legacy === 'light' || legacy === 'system') return legacy;
  } catch { /* storage unavailable */ }
  return 'light';
}

export function readPreference<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  try {
    const value = window.localStorage.getItem(key) as T | null;
    return value && allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

export function writePreference(key: string, value: string): void {
  try { window.localStorage.setItem(key, value); } catch { /* storage unavailable */ }
}

/** Wording for leaving a section or page with unsaved edits. */
export function leaveWarning(labels: string[]): {title: string; body: string} {
  const where = labels.length === 1 ? labels[0] : `${labels.length} settings cards`;
  return {title: 'Leave with unsaved changes?',
    body: `You changed ${where} but have not saved. Leaving discards those changes; nothing else is affected.`};
}

/**
 * Shared interaction primitives (#47 follow-up A): an accessible confirmation
 * dialog, a save bar with truthful states, a per-card draft hook and a
 * registry of unsaved cards. Styling lives in interaction.css.
 */
import React, {createContext, useCallback, useContext, useEffect, useId, useRef, useState} from 'react';
import {AlertTriangle, Check, CircleAlert, LoaderCircle} from 'lucide-react';
import * as S from './settingsModel';

type Row = S.Row;

// ---------------------------------------------------------------------------
// Confirmation dialog
// ---------------------------------------------------------------------------
export type ConfirmRequest = {
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  tone?: 'danger' | 'default';
  onConfirm: () => void | Promise<void>;
};

/**
 * A modal dialog for consequential actions only. Focus starts on the safe
 * choice, Tab stays inside, Escape cancels, and focus returns to the control
 * that opened it. The rest of the workspace is inert while it is open.
 */
export function ConfirmDialog({request, onClose}: {request: ConfirmRequest | null; onClose: () => void}) {
  const panel = useRef<HTMLDivElement>(null);
  const safe = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [busy, setBusy] = useState(false);
  const titleId = useId(), bodyId = useId();

  useEffect(() => {
    if (!request) return;
    opener.current = document.activeElement as HTMLElement | null;
    const background = Array.from(document.querySelectorAll('.app>main,.app>aside'));
    background.forEach(element => element.setAttribute('inert', ''));
    requestAnimationFrame(() => safe.current?.focus());
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      if (event.key === 'Tab' && panel.current) {
        const items = Array.from(panel.current.querySelectorAll<HTMLElement>('button:not(:disabled)'));
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      background.forEach(element => element.removeAttribute('inert'));
      opener.current?.focus?.();
    };
  }, [request, onClose]);

  if (!request) return null;
  const confirm = async () => {
    setBusy(true);
    try { await request.onConfirm(); } finally { setBusy(false); onClose(); }
  };
  return <div className="confirm-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className={'confirm-dialog' + (request.tone === 'danger' ? ' danger' : '')} role="alertdialog" aria-modal="true"
      aria-labelledby={titleId} aria-describedby={bodyId} ref={panel}>
      <div className="confirm-head">{request.tone === 'danger' && <AlertTriangle size={20} aria-hidden/>}<h2 id={titleId}>{request.title}</h2></div>
      <div id={bodyId} className="confirm-body">{request.body}</div>
      <div className="confirm-actions">
        <button className="secondary" ref={safe} onClick={onClose} disabled={busy}>{request.cancelLabel}</button>
        <button className={request.tone === 'danger' ? 'danger-button' : 'primary'} onClick={confirm} aria-busy={busy} disabled={busy}>
          {busy && <LoaderCircle size={16} className="spin" aria-hidden/>}{request.confirmLabel}</button>
      </div>
    </div>
  </div>;
}

/** Open a confirmation from anywhere below `ConfirmProvider`. */
const ConfirmContext = createContext<(request: ConfirmRequest) => void>(() => {});
export function ConfirmProvider({children}: {children: React.ReactNode}) {
  const [request, setRequest] = useState<ConfirmRequest | null>(null);
  const close = useCallback(() => setRequest(null), []);
  return <ConfirmContext.Provider value={setRequest}>{children}<ConfirmDialog request={request} onClose={close}/></ConfirmContext.Provider>;
}
export const useConfirm = () => useContext(ConfirmContext);

// ---------------------------------------------------------------------------
// Unsaved-card registry
// ---------------------------------------------------------------------------
type Registry = {report: (id: string, label: string, dirty: boolean) => void};
const DirtyContext = createContext<Registry>({report: () => {}});

/** Tracks which cards hold unsaved edits and tells the page about it. */
export function DirtyRegistry({onChange, children}: {onChange: (labels: Row) => void; children: React.ReactNode}) {
  const dirty = useRef<Record<string, string>>({});
  const report = useCallback((id: string, label: string, isDirty: boolean) => {
    const had = id in dirty.current;
    if (isDirty) dirty.current[id] = label; else delete dirty.current[id];
    if (had !== isDirty) onChange({...dirty.current});
  }, [onChange]);
  return <DirtyContext.Provider value={{report}}>{children}</DirtyContext.Provider>;
}

// ---------------------------------------------------------------------------
// Drafts and saving
// ---------------------------------------------------------------------------
export type Draft<T extends Row> = {
  draft: T; dirty: boolean; status: S.SaveStatus; error: string; savedAt: string;
  set: (key: keyof T & string, value: unknown) => void;
  discard: () => void;
  save: (write: (draft: T) => Promise<Row | void>) => Promise<boolean>;
};

/**
 * A local copy of one card's saved values. `dirty` compares the named keys
 * only, after normalization, so formatting-only edits are not "unsaved".
 * A failed save keeps the draft and reports the server's message.
 */
export function useDraft<T extends Row>(id: string, label: string, saved: T, keys: string[]): Draft<T> {
  const [base, setBase] = useState<T>(saved);
  const [draft, setDraft] = useState<T>(saved);
  const [status, setStatus] = useState<S.SaveStatus>('idle');
  const [error, setError] = useState('');
  const [savedAt, setSavedAt] = useState('');
  const {report} = useContext(DirtyContext);
  const dirty = S.isDirty(base, draft, keys);
  const incoming = JSON.stringify(keys.map(key => S.normalizeValue(saved?.[key])));

  // Newer saved values replace the draft only when nothing is being edited.
  useEffect(() => {
    if (!dirty) { setBase(saved); setDraft(saved); }
  }, [incoming]);
  useEffect(() => { report(id, label, dirty); return () => report(id, label, false); }, [dirty]);

  return {
    draft, dirty, status, error, savedAt,
    set: (key, value) => { setDraft(current => ({...current, [key]: value})); setStatus(s => s === 'saving' ? s : 'idle'); },
    discard: () => { setDraft(base); setStatus('idle'); setError(''); },
    save: async write => {
      setStatus('saving'); setError('');
      try {
        const result = await write(draft);
        const next = {...draft, ...(result && typeof result === 'object'
          ? Object.fromEntries(keys.filter(key => key in result).map(key => [key, (result as Row)[key]])) : {})} as T;
        setBase(next); setDraft(next); setStatus('saved'); setSavedAt(new Date().toISOString());
        return true;
      } catch (e: any) {
        setStatus('error'); setError(e?.message || 'The change could not be saved.');
        return false;
      }
    },
  };
}

/** Save and discard for one card, with its state spelled out. */
export function SaveBar({state, onSave, saveLabel = 'Save changes'}: {state: Draft<any>; onSave: () => void; saveLabel?: string}) {
  const text = S.saveStatusText(state.status, state.dirty, state.savedAt, state.error);
  const visible = state.dirty || state.status === 'saving' || state.status === 'error';
  const tone = state.status === 'error' ? 'bad' : state.dirty || state.status === 'saving' ? 'pending' : 'good';
  const statusId = useId();
  return <div className={'save-bar' + (visible ? ' is-active' : '')} data-tone={tone}>
    <p className="save-status" id={statusId} role={state.status === 'error' ? 'alert' : 'status'} aria-live={state.status === 'error' ? 'assertive' : 'polite'}>
      {state.status === 'saving' ? <LoaderCircle size={16} className="spin" aria-hidden/>
        : state.status === 'error' ? <CircleAlert size={16} aria-hidden/>
          : !state.dirty && state.status === 'saved' ? <Check size={16} aria-hidden/> : null}
      <span>{text}</span>
    </p>
    <div className="save-actions">
      {(state.dirty || state.status === 'error') && <button type="button" className="secondary compact" onClick={state.discard} disabled={state.status === 'saving'}>Discard</button>}
      <button type="button" className="primary compact" onClick={onSave} disabled={!state.dirty || state.status === 'saving'}
        aria-busy={state.status === 'saving'} aria-describedby={statusId}>{state.status === 'saving' ? 'Saving…' : saveLabel}</button>
    </div>
  </div>;
}

/** A one-off action's outcome, announced and shown beside the control. */
export function ActionStatus({status}: {status: {tone: 'good' | 'bad' | 'info'; text: string} | null}) {
  if (!status) return <p className="action-status" role="status" aria-live="polite"/>;
  const Icon = status.tone === 'good' ? Check : status.tone === 'bad' ? CircleAlert : LoaderCircle;
  return <p className={'action-status ' + status.tone} role={status.tone === 'bad' ? 'alert' : 'status'}
    aria-live={status.tone === 'bad' ? 'assertive' : 'polite'}>
    <Icon size={16} className={status.tone === 'info' ? 'spin' : ''} aria-hidden/><span>{status.text}</span></p>;
}

/** Run one action with busy and outcome state. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{tone: 'good' | 'bad' | 'info'; text: string} | null>(null);
  /** `success` may depend on the server's answer, so the message is truthful. */
  const run = async (fn: () => Promise<any>, success: string | ((result: any) => string), pending = 'Working…') => {
    if (busy) return false;
    setBusy(true); setStatus({tone: 'info', text: pending});
    try { const result = await fn(); setStatus({tone: 'good', text: typeof success === 'function' ? success(result) : success}); return true; }
    catch (e: any) { setStatus({tone: 'bad', text: e?.message || 'That did not work. Nothing was changed.'}); return false; }
    finally { setBusy(false); }
  };
  return {busy, status, run, clear: () => setStatus(null)};
}

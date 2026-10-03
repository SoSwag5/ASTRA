/**
 * In-app Gmail check and match (#47 follow-up B). Two explicit steps on the
 * existing endpoints: 1) read Gmail for confirmations (primary account only,
 * read-only, bounded), 2) match saved confirmations to applications. Each
 * step reports its own actual outcome; neither runs on its own or on a timer.
 */
import React, {useEffect, useState} from 'react';
import {ArrowRight, ChevronDown, LoaderCircle, MailSearch, Link2} from 'lucide-react';
import {Disclosure, useCollapsible} from './ui';
import * as G from './gmailOpsModel';
import {StatusBadge} from './Progress';

type Row = G.Row;
type Api = (path: string, method?: string, data?: any) => Promise<any>;

/** POST that keeps the bounded error code, which `api()` would discard. */
async function post(path: string, body: Row = {}): Promise<{result: Row | null; failure: G.Failure | null}> {
  let response: Response;
  try {
    // Loaded on use: the session module reads browser storage when it loads.
    const {privateFetch} = await import('./access');
    response = await privateFetch('/api' + path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  } catch {
    return {result: null, failure: {status: 0, code: 'OFFLINE', detail: 'ASTRA did not respond. Check that the app is running, then try again.'}};
  }
  let data: Row = {};
  try { data = await response.json(); } catch { /* unreadable body */ }
  if (!response.ok) {
    return {result: null, failure: {status: response.status, code: typeof data.code === 'string' ? data.code : '', detail: typeof data.detail === 'string' ? data.detail : ''}};
  }
  return {result: data, failure: null};
}

function OutcomeBlock({outcome, busy, onMatch, onReview}: {outcome: G.Outcome; busy: boolean; onMatch?: () => void; onReview?: () => void}) {
  if (!outcome.title) return null;
  const tone = outcome.tone === 'neutral' ? 'neutral' : outcome.tone;
  return <div className={'op-outcome callout ' + tone} role={tone === 'bad' ? 'alert' : 'status'} aria-live={tone === 'bad' ? 'assertive' : 'polite'}>
    <div><p className="callout-title">{outcome.title}</p>
      {outcome.lines.length > 0 && <ul>{outcome.lines.map((line, i) => <li key={i}>{line}</li>)}</ul>}
      {outcome.action === 'match' && onMatch && <button className="textbtn" onClick={onMatch} disabled={busy}>Match them to applications now<ArrowRight size={15} aria-hidden/></button>}
      {outcome.action === 'review' && onReview && <button className="textbtn" onClick={onReview}>Review the waiting messages<ArrowRight size={15} aria-hidden/></button>}
    </div>
  </div>;
}

export function GmailOperations({api, onReview, onChanged, onConnect, compact = false}: {
  api: Api; onReview?: () => void; onChanged?: () => void; onConnect?: () => void; compact?: boolean;
}) {
  const [status, setStatus] = useState<Row | null>(null), [loadError, setLoadError] = useState('');
  const [syncing, setSyncing] = useState(false), [matching, setMatching] = useState(false);
  const [sync, setSync] = useState<G.Outcome>({tone: 'neutral', title: '', lines: []});
  const [match, setMatch] = useState<G.Outcome>({tone: 'neutral', title: '', lines: []});
  const collapse = useCollapsible(!compact);
  const open = collapse.open;
  const load = () => api('/progress/gmail').then(value => { setStatus(value); setLoadError(''); }).catch(e => setLoadError(e.message));
  useEffect(() => { load(); }, []);

  const connection = G.connectionState(status);
  const busy = syncing || matching;
  const check = async () => {
    if (busy) return;
    setSyncing(true); setMatch({tone: 'neutral', title: '', lines: []});
    const {result, failure} = await post('/gmail/accounts/primary/sync');
    setSync(G.syncOutcome(result, failure));
    setSyncing(false);
    await load();
  };
  const runMatch = async () => {
    if (busy) return;
    setMatching(true);
    const {result, failure} = await post('/applications/state/reconcile', {limit: status?.limits?.max_matched_per_run ?? 200});
    setMatch(G.matchOutcome(result, failure));
    setMatching(false);
    await load();
    if (result) onChanged?.();
  };

  const waiting = status?.unmatched_total ?? null, review = status?.review?.total ?? null;
  return <section className={'panel gmail-ops' + (compact ? ' compact' : '')} aria-labelledby="gmail-ops-title">
    <div className="gmail-ops-head">
      <MailSearch size={20} aria-hidden/>
      <div><h3 id="gmail-ops-title">Check Gmail for application confirmations</h3>
        <p><StatusBadge tone={connection.tone}>{connection.label}</StatusBadge> {connection.detail}</p></div>
      {compact && <button className="icon gmail-ops-toggle" aria-expanded={open} aria-controls="gmail-ops-body" onClick={collapse.toggle}
        aria-label={open ? 'Hide Gmail check details' : 'Show Gmail check details'}><ChevronDown size={18} aria-hidden/></button>}
    </div>
    {loadError && <div role="alert" className="errorbar"><span>Gmail status could not load. {loadError}</span><button className="secondary" onClick={load}>Retry</button></div>}
    <div ref={collapse.ref} id="gmail-ops-body" hidden={collapse.initialHidden}>
      <dl className="gmail-ops-counts">
        <div><dt>Saved, not yet matched</dt><dd>{waiting === null ? 'Not recorded' : waiting}</dd></div>
        <div><dt>Waiting for your decision</dt><dd>{review === null ? 'Not recorded' : review}</dd></div>
      </dl>
      <ol className="gmail-ops-steps">
        <li>
          <div className="step-copy"><strong>1. Read Gmail</strong><span>Looks for new application confirmations in the connected account and saves minimal evidence. Nothing is linked yet.</span></div>
          <button className="primary" onClick={check} disabled={!connection.connected || busy} aria-busy={syncing}
            aria-describedby={!connection.connected ? 'gmail-ops-why' : undefined}>
            {syncing ? <><LoaderCircle size={16} className="spin" aria-hidden/>Reading Gmail…</> : 'Check Gmail now'}</button>
          {!connection.connected && <small id="gmail-ops-why">{connection.detail}{onConnect && <> <button className="textbtn" onClick={onConnect}>Open Gmail settings</button></>}</small>}
          {syncing && <p className="muted-line" role="status">Reading up to {status?.limits?.max_messages_per_check ?? 100} messages; this can take up to {Math.round((status?.limits?.max_seconds_per_check ?? 120) / 60)} minutes.</p>}
          <OutcomeBlock outcome={sync} busy={busy} onMatch={runMatch}/>
        </li>
        <li>
          <div className="step-copy"><strong>2. Match to applications</strong><span>Compares saved confirmations with your tracked applications. High confidence with one clear match is marked Applied; anything uncertain waits for your decision.</span></div>
          <button className="secondary" onClick={runMatch} disabled={busy} aria-busy={matching}>
            {matching ? <><LoaderCircle size={16} className="spin" aria-hidden/>Matching…</> : <><Link2 size={16} aria-hidden/>Match saved confirmations</>}</button>
          <OutcomeBlock outcome={match} busy={busy} onReview={onReview}/>
        </li>
      </ol>
      {review ? onReview && <button className="textbtn" onClick={onReview}>{review} {review === 1 ? 'message is' : 'messages are'} waiting for your decision<ArrowRight size={15} aria-hidden/></button> : null}
      <Disclosure className="gmail-ops-limits" summary="What this reads, and its limits"><ul>{G.limitsText(status?.limits).map(line => <li key={line}>{line}</li>)}</ul></Disclosure>
    </div>
  </section>;
}

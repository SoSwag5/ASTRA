import React, {useCallback, useEffect, useRef, useState} from 'react';
import {AlertTriangle, ArrowRight, CalendarCheck, CheckCircle2, CircleDashed, Clock3, ExternalLink, Info, Layers, MailCheck, Radar, RefreshCw, Search, Send, XCircle} from 'lucide-react';
import * as M from './progressModel';
import {GmailOperations} from './GmailOperations';
import './tokens.css';
import './progress.css';

type Row = M.Row;
type Api = (path: string, method?: string, data?: any) => Promise<any>;
type Props = {api: Api; openJob: (job: Row) => void; goTo: (page: string) => void};

const TONE_ICON: Record<M.Tone, React.ComponentType<{size?: number; 'aria-hidden'?: boolean}>> = {
  good: CheckCircle2, warn: AlertTriangle, bad: XCircle, info: Info, neutral: CircleDashed,
};

export function StatusBadge({tone, children}: {tone: M.Tone; children: React.ReactNode}) {
  const Icon = TONE_ICON[tone];
  return <span className={'status-badge ' + tone}><Icon size={14} aria-hidden/>{children}</span>;
}

function Callout({tone, title, children}: {tone: M.Tone; title?: string; children?: React.ReactNode}) {
  const Icon = TONE_ICON[tone];
  return <div className={'callout ' + tone}><Icon size={18} aria-hidden/><div>{title && <p className="callout-title">{title}</p>}{children}</div></div>;
}

/** A single-series bar: length encodes the value, the number is always printed. */
function Bar({value, max, label}: {value: number; max: number; label: string}) {
  const width = max > 0 ? Math.max(value > 0 ? 3 : 0, Math.round((value / max) * 100)) : 0;
  return <span className="bar" aria-hidden title={label}><span className="bar-fill" style={{width: width + '%'}}/></span>;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export function Progress({api, openJob, goTo}: Props) {
  const periodKeys = M.PERIODS.map(p => p.key);
  const [period, setPeriod] = useState(() => M.readStored('progressPeriod', 'this_week', periodKeys));
  const [data, setData] = useState<Row | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [latest, setLatest] = useState<Row | null>(null);
  const [latestFailed, setLatestFailed] = useState(false);
  // The saved Campaign plan: null when none is saved, undefined when unread.
  const [savedCampaign, setSavedCampaign] = useState<Row | null | undefined>(undefined);
  const [scanStatus, setScanStatus] = useState<Row | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const request = useRef(0);
  const refresh = () => { setRefreshToken(t => t + 1); load(period); };

  const load = useCallback(async (which: string) => {
    const ticket = ++request.current;
    setLoading(true);
    try {
      // The projection runs #46's read-repair first, so candidates and the
      // journey read complete canonical state.
      const report = await api('/progress?period=' + which);
      if (ticket !== request.current) return;
      setData(report);
      setError('');
    } catch (e: any) {
      if (ticket === request.current) setError(e.message);
    }
    const [telemetry, settings, status] = await Promise.allSettled([api('/search/telemetry'), api('/settings'), api('/scan/status')]);
    if (ticket !== request.current) return;
    setLatest(telemetry.status === 'fulfilled' ? telemetry.value : null);
    setLatestFailed(telemetry.status === 'rejected');
    setSavedCampaign(settings.status === 'fulfilled' ? settings.value?.campaign ?? null : undefined);
    setScanStatus(status.status === 'fulfilled' ? status.value : null);
    setLoading(false);
  }, [api]);

  useEffect(() => { load(period); M.writeStored('progressPeriod', period); }, [period, load]);

  // While a scan runs, follow its recorded source progress (a read-only
  // status poll); when it ends, reload so the latest run's outcome shows.
  const scanning = Boolean(scanStatus?.active);
  useEffect(() => {
    if (!scanning) return;
    let live = true;
    const timer = window.setInterval(() => {
      api('/scan/status').then(next => {
        if (!live) return;
        setScanStatus(next);
        if (!next?.active) load(period);
      }).catch(() => { if (live) setScanStatus(null); });
    }, 4000);
    return () => { live = false; window.clearInterval(timer); };
  }, [scanning, api, load, period]);

  if (!data) {
    return <div className="progress">
      <PeriodPicker period={period} onChange={setPeriod} data={null} loading={loading} onRefresh={() => load(period)}/>
      {error
        ? <div className="errorbar" role="alert"><span>Progress could not load. {error}</span><button className="secondary" onClick={() => load(period)}>Retry</button></div>
        : <ProgressSkeleton/>}
    </div>;
  }

  return <div className="progress">
    <PeriodPicker period={period} onChange={setPeriod} data={data} loading={loading} onRefresh={refresh}/>
    {error && <div className="errorbar" role="alert"><span>Could not refresh. Showing the figures loaded at {M.formatDateTime(data.generated_at)}. {error}</span><button className="secondary" onClick={() => load(period)}>Retry</button></div>}
    <div className={'progress-body' + (loading ? ' is-refreshing' : '')} aria-busy={loading}>
      <Glance data={data} savedCampaign={savedCampaign} scanStatus={scanStatus} latest={latestFailed ? null : latest} goTo={goTo}/>
      <NextAction data={data} goTo={goTo}/>
      <GmailOperations api={api} compact onChanged={refresh} onConnect={() => goTo('Settings/permissions')}
        onReview={() => { const heading = document.getElementById('needs-review-title'); heading?.scrollIntoView({block: 'start'}); heading?.focus({preventScroll: true}); }}/>
      <ReviewQueue api={api} openJob={openJob} data={data} refreshToken={refreshToken} onChanged={() => load(period)}/>
      <PeriodFigures data={data} openJob={openJob}/>
      <Journey data={data} goTo={goTo}/>
      <DiscoveryHealth data={data} latest={latest} latestFailed={latestFailed} goTo={goTo}/>
      <Outcomes data={data}/>
    </div>
  </div>;
}

function PeriodPicker({period, onChange, data, loading, onRefresh}: {period: string; onChange: (p: string) => void; data: Row | null; loading: boolean; onRefresh: () => void}) {
  return <div className="progress-toolbar">
    <fieldset className="segmented">
      <legend className="visually-hidden">Reporting period</legend>
      {M.PERIODS.map(p => <label key={p.key} className={period === p.key ? 'selected' : ''}>
        <input type="radio" name="progress-period" value={p.key} checked={period === p.key} onChange={() => onChange(p.key)}/>
        <span>{p.label}</span>
      </label>)}
    </fieldset>
    <p className="progress-range">{data ? <>{M.periodRange(data.period)} <span>· Asia/Dubai</span></> : ' '}</p>
    <div className="progress-refresh">
      {data && <span className="progress-updated">Updated {M.formatDateTime(data.generated_at)}</span>}
      <button className="secondary compact" onClick={onRefresh} disabled={loading} aria-busy={loading} aria-label="Refresh progress"><RefreshCw size={16} className={loading ? 'spin' : ''} aria-hidden/><span>{loading ? 'Refreshing…' : 'Refresh'}</span></button>
    </div>
  </div>;
}

// ---------------------------------------------------------------------------
// At a glance: three rails, each from recorded numbers only
// ---------------------------------------------------------------------------
export function Glance({data, savedCampaign, scanStatus, latest, goTo}: {data: Row; savedCampaign: Row | null | undefined; scanStatus: Row | null; latest: Row | null; goTo: (page: string) => void}) {
  const weekly = M.weeklyTargetRail(data.outcomes, savedCampaign);
  const stages = M.stageRail(data.applications?.current);
  const scan = M.scanRail(scanStatus, latest);
  return <section className="glance" aria-labelledby="glance-title">
    <h2 id="glance-title" className="visually-hidden">Progress at a glance</h2>
    <RailCard id="rail-stages" icon={<Layers size={18} aria-hidden/>} title="Where tracked applications stand" rail={stages} kind="composition"/>
    <RailCard id="rail-week" icon={<CalendarCheck size={18} aria-hidden/>} title="This week’s applications" rail={weekly} kind="progress"
      action={!weekly.available && savedCampaign !== undefined ? <button className="textbtn" onClick={() => goTo('Settings/focus')}>Open Campaign plan<ArrowRight size={15} aria-hidden/></button> : null}/>
    <RailCard id="rail-scan" icon={<Radar size={18} aria-hidden/>} title={scan.live ? 'Scan in progress' : 'Latest discovery scan'} rail={scan} kind={scan.live ? 'progress' : 'composition'}/>
  </section>;
}

function RailCard({id, icon, title, rail, kind, action}: {id: string; icon: React.ReactNode; title: string; rail: M.Rail; kind: 'progress' | 'composition'; action?: React.ReactNode}) {
  return <section className={'rail-card tone-' + rail.tone + (rail.available ? '' : ' is-unavailable')} aria-labelledby={id}>
    <div className="rail-top">{icon}<h3 id={id}>{title}</h3>{rail.live && <span className="live-chip"><i aria-hidden/>Live</span>}</div>
    <p className={'rail-headline' + (rail.available ? '' : ' is-words')}>{rail.headline}</p>
    <RailBar rail={rail} kind={kind} labelledBy={id}/>
    {rail.available && rail.segments.length > 1 && <ul className="rail-legend">{rail.segments.map(segment =>
      <li key={segment.key}><i className={'swatch ' + segment.tone} aria-hidden/>{segment.label}<strong>{segment.count}</strong></li>)}</ul>}
    <p className="rail-meaning">{rail.meaning}</p>
    {rail.note && <p className="rail-note">{rail.note}</p>}
    {action}
  </section>;
}

/**
 * The bar itself. Lengths are proportional to the recorded counts (each part
 * grows by its count, the unfilled rest by max minus the filled total); only
 * its appearance is animated, never the numbers.
 */
export function RailBar({rail, kind, labelledBy}: {rail: M.Rail; kind: 'progress' | 'composition'; labelledBy: string}) {
  if (!rail.available || !rail.max) return <div className="rail is-empty" aria-hidden/>;
  const filled = rail.segments.reduce((sum, s) => sum + s.count, 0);
  const rest = Math.max(0, rail.max - filled);
  const a11y = kind === 'progress'
    ? {role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': rail.max, 'aria-valuenow': Math.min(rail.value ?? 0, rail.max), 'aria-valuetext': rail.valueText, 'aria-labelledby': labelledBy}
    : {role: 'img', 'aria-label': rail.valueText};
  return <div className={'rail' + (rail.live ? ' is-live' : '')} {...a11y}>
    <span className="rail-fill">
      {rail.segments.map(segment => <span key={segment.key} className={'rail-seg ' + segment.tone} style={{flexGrow: segment.count}}/>)}
      {rest > 0 && <span className="rail-rest" style={{flexGrow: rest}}/>}
    </span>
  </div>;
}

function ProgressSkeleton() {
  return <div className="progress-skeleton" role="status" aria-live="polite">
    <span className="visually-hidden">Loading verified progress…</span>
    <div className="glance" aria-hidden>{[0, 1, 2].map(i => <div key={i} className="rail-card skeleton-card"><span className="skeleton-line short"/><span className="skeleton-line tall"/><span className="skeleton-line bar"/><span className="skeleton-line"/></div>)}</div>
    <div className="skeleton-card wide" aria-hidden><span className="skeleton-line short"/><span className="skeleton-line"/><span className="skeleton-line"/></div>
  </div>;
}

export function NextAction({data, goTo}: {data: Row; goTo: (page: string) => void}) {
  const review = data.review?.total;
  const due = data.actions?.followups?.due_now || 0;
  const unmatched = data.gmail?.not_reconciled_total || 0;
  let icon = <CheckCircle2 size={20} aria-hidden/>, text: React.ReactNode = 'Nothing needs your decision right now.', action: React.ReactNode = null;
  if (typeof review === 'number' && review > 0) {
    icon = <MailCheck size={20} aria-hidden/>;
    text = <>Start with <strong>{M.plural(review, 'Gmail message')}</strong> that {review === 1 ? 'needs' : 'need'} your decision.</>;
    action = <button className="primary compact" onClick={() => { const heading = document.getElementById('needs-review-title'); heading?.scrollIntoView({block: 'start'}); heading?.focus({preventScroll: true}); }}>Review now<ArrowRight size={16} aria-hidden/></button>;
  } else if (due > 0) {
    icon = <Clock3 size={20} aria-hidden/>;
    text = <><strong>{M.plural(due, 'follow-up')}</strong> {due === 1 ? 'is' : 'are'} due today or overdue.</>;
    action = <button className="primary compact" onClick={() => goTo('Today')}>Open Today<ArrowRight size={16} aria-hidden/></button>;
  } else if (unmatched > 0) {
    icon = <Info size={20} aria-hidden/>;
    text = <>{M.plural(unmatched, 'Gmail confirmation')} {unmatched === 1 ? 'has' : 'have'} not been matched to an application yet.</>;
  }
  const followupNote = typeof review === 'number' && review > 0 && due > 0 ? ` ${M.plural(due, 'follow-up')} also due — see Today.` : '';
  return <div className="next-action">{icon}<p>{text}{followupNote}</p>{action}</div>;
}

// ---------------------------------------------------------------------------
// Needs Review
// ---------------------------------------------------------------------------
type Entry = {item: Row; outcome?: M.ReviewOutcome & {label: string; badge: string}};
const PAGE = 3;

function ReviewQueue({api, openJob, data, refreshToken, onChanged}: {api: Api; openJob: (job: Row) => void; data: Row; refreshToken: number; onChanged: () => void}) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable' | 'error'>('loading');
  const [loadingMore, setLoadingMore] = useState(false);
  const [pending, setPending] = useState<number | null>(null);
  const [selection, setSelection] = useState<Record<number, number>>({});
  const [problems, setProblems] = useState<Record<number, M.ReviewOutcome>>({});
  const [polite, setPolite] = useState('');
  const headingRef = useRef<HTMLHeadingElement>(null);
  const itemRefs = useRef<Record<number, HTMLElement | null>>({});

  const fetchPage = useCallback(async (offset: number, limit: number) => {
    const page = await api(`/progress/needs-review?limit=${limit}&offset=${offset}`);
    if (page.status !== 'OK') { setStatus('unavailable'); return null; }
    setTotal(page.total);
    setStatus('ready');
    return page.items as Row[];
  }, [api]);

  const reload = useCallback(async (keepResolved = true) => {
    try {
      const open = entries.filter(e => !e.outcome).length;
      const items = await fetchPage(0, Math.min(20, Math.max(PAGE, open)));
      if (!items) return;
      setEntries(prev => [...items.map(item => ({item})), ...(keepResolved ? prev.filter(e => e.outcome) : [])]);
    } catch {
      setStatus(s => s === 'ready' ? s : 'error');
    }
  }, [entries, fetchPage]);

  // First load, and a fresh queue (without this session's receipts) on Refresh.
  useEffect(() => { reload(false); }, [refreshToken]);

  const unresolved = entries.filter(e => !e.outcome);
  const remaining = total === null ? 0 : Math.max(0, total - unresolved.length);

  async function more() {
    setLoadingMore(true);
    try {
      const items = await fetchPage(unresolved.length, PAGE);
      if (items) {
        const known = new Set(entries.map(e => e.item.link_id));
        setEntries(prev => [...prev.filter(e => !e.outcome), ...items.filter(i => !known.has(i.link_id)).map(item => ({item})), ...prev.filter(e => e.outcome)]);
        if (items[0]) requestAnimationFrame(() => itemRefs.current[items[0].link_id]?.focus());
      }
    } catch {
      setPolite('More messages could not be loaded. Try again.');
    } finally {
      setLoadingMore(false);
    }
  }

  function focusAfter(linkId: number) {
    const open = entries.filter(e => !e.outcome && e.item.link_id !== linkId);
    const index = entries.findIndex(e => e.item.link_id === linkId);
    const next = open.find(e => entries.indexOf(e) > index) || open[open.length - 1];
    requestAnimationFrame(() => (next ? itemRefs.current[next.item.link_id] : headingRef.current)?.focus());
  }

  async function act(item: Row, action: M.ReviewAction) {
    if (pending !== null) return;
    const id = item.link_id;
    const chosen = selection[id] ?? item.default_application_id ?? null;
    if (action === 'confirm' && !chosen) {
      setProblems(p => ({...p, [id]: {tone: 'warn', resolved: false, refresh: false,
        title: 'Choose which application this message confirms.', detail: ''}}));
      requestAnimationFrame(() => (document.getElementById(`review-${id}-choices`)?.querySelector('input') as HTMLElement | null)?.focus());
      return;
    }
    setPending(id);
    setProblems(p => { const next = {...p}; delete next[id]; return next; });
    let response: Row | null = null, failure = '';
    try {
      response = await api(`/applications/state/needs-review/${id}/${action}`, 'POST',
        action === 'confirm' ? {application_id: chosen} : {});
    } catch (e: any) {
      failure = e.message || '';
    }
    const candidate = (item.candidates || []).find((c: Row) => c.application_id === chosen);
    const outcome = M.reviewOutcome(action, response, M.candidateLabel(candidate), failure);
    setPending(null);
    if (outcome.resolved) {
      const badge = response?.ok === true ? (action === 'confirm' ? 'Confirmed' : 'Rejected') : 'Already resolved';
      setEntries(prev => prev.map(e => e.item.link_id === id ? {...e, outcome: {...outcome, label: M.candidateLabel(candidate), badge}} : e));
      setTotal(t => t === null ? t : Math.max(0, t - 1));
      setPolite(`${outcome.title} ${outcome.detail}`);
      focusAfter(id);
      onChanged();
    } else {
      setProblems(p => ({...p, [id]: outcome}));
      if (outcome.refresh) reload();
    }
  }

  const count = total ?? 0;
  return <section id="needs-review" className="panel progress-section review-queue" aria-labelledby="needs-review-title">
    <div className="section-head">
      <div>
        <h2 id="needs-review-title" ref={headingRef} tabIndex={-1}>Needs your decision{status === 'ready' && <span className="count-chip" aria-label={`${count} waiting`}>{count}</span>}</h2>
        <p>Gmail confirmations ASTRA could not link to an application on its own. Confirming records the application as <em>Applied</em> on your authority, with the message as evidence. Rejecting never changes an application.</p>
      </div>
    </div>
    <p className="visually-hidden" role="status" aria-live="polite">{polite}</p>
    {status === 'loading' && <p className="muted-line" role="status">Loading messages…</p>}
    {status === 'unavailable' && <Callout tone="neutral" title="Review is unavailable">Gmail evidence has not been set up in this workspace yet.</Callout>}
    {status === 'error' && <div className="errorbar" role="alert"><span>The review queue could not load.</span><button className="secondary" onClick={() => reload(false)}>Retry</button></div>}
    {status === 'ready' && !entries.length && <div className="empty-inline"><CheckCircle2 size={20} aria-hidden/><div><p className="empty-title">No Gmail messages need your decision.</p><p>{gmailCoverageText(data.gmail)}</p></div></div>}
    <ol className="review-list">
      {entries.map(entry => <li key={entry.item.link_id}>
        {entry.outcome
          ? <Receipt entry={entry} refCallback={el => { itemRefs.current[entry.item.link_id] = el; }}/>
          : <ReviewItem item={entry.item} pending={pending} busy={pending !== null}
            selected={selection[entry.item.link_id] ?? entry.item.default_application_id ?? null}
            onSelect={value => setSelection(s => ({...s, [entry.item.link_id]: value}))}
            problem={problems[entry.item.link_id]} onAct={act} openJob={openJob}
            refCallback={el => { itemRefs.current[entry.item.link_id] = el; }}/>}
      </li>)}
    </ol>
    {status === 'ready' && (remaining > 0 || unresolved.length > 0) && <div className="queue-footer">
      <p className="muted-line">{unresolved.length ? `Showing ${unresolved.length} of ${count} waiting` : `${count} more waiting`}{entries.length > unresolved.length ? ` · ${entries.length - unresolved.length} resolved just now` : ''}.</p>
      {remaining > 0 && <button className="secondary" onClick={more} disabled={loadingMore}>{loadingMore ? 'Loading…' : `Show ${Math.min(PAGE, remaining)} more`}</button>}
    </div>}
    {(data.gmail?.not_reconciled_total || 0) > 0 && <div className="queue-note"><Callout tone="info">{M.plural(data.gmail.not_reconciled_total, 'Gmail confirmation')} {data.gmail.not_reconciled_total === 1 ? 'has' : 'have'} not been matched yet, so {data.gmail.not_reconciled_total === 1 ? 'it is' : 'they are'} not in this queue. Matching runs only when reconciliation is started.</Callout></div>}
  </section>;
}

function gmailCoverageText(gmail: Row | undefined) {
  if (!gmail || gmail.status === 'NOT_CONNECTED') return 'Gmail is not connected, so no confirmations have been checked.';
  return M.gmailFigure(gmail).note;
}

export function ReviewItem({item, pending, busy, selected, onSelect, problem, onAct, openJob, refCallback}: {
  item: Row; pending: number | null; busy: boolean; selected: number | null; onSelect: (id: number) => void;
  problem?: M.ReviewOutcome; onAct: (item: Row, action: M.ReviewAction) => void; openJob: (job: Row) => void;
  refCallback: (el: HTMLElement | null) => void;
}) {
  const id = item.link_id;
  const candidates: Row[] = item.candidates || [];
  const mine = pending === id;
  const title = [item.detected_role || 'Role not detected', item.detected_company || 'employer not detected'].join(' at ');
  const confidenceTone: M.Tone = item.confidence === 'MEDIUM' ? 'warn' : 'info';
  return <article className="review-item" aria-labelledby={`review-${id}-title`} aria-busy={mine}>
    <div className="review-head">
      <h3 id={`review-${id}-title`} ref={refCallback} tabIndex={-1}>{title}</h3>
      <StatusBadge tone={confidenceTone}>{M.CONFIDENCE_LABELS[item.confidence] || item.confidence}</StatusBadge>
    </div>
    <p className="review-meta">{M.PLATFORM_LABELS[item.platform] || 'Unknown platform'} confirmation · received {M.formatDateTime(item.received_at)}</p>
    <p className="review-reason">{M.reviewReason(item.reason_code)}</p>
    {item.proposed_application_id && item.proposed_confirmable === false && <Callout tone="warn">The application ASTRA proposed no longer matches this message, so it cannot be confirmed against it.</Callout>}
    {candidates.length ? <fieldset className="choices" id={`review-${id}-choices`} aria-describedby={problem ? `review-${id}-problem` : undefined}>
      <legend>{candidates.length === 1 ? 'Application this message would confirm' : 'Which application does this message confirm?'}</legend>
      {candidates.map(candidate => <div key={candidate.application_id} className={'choice' + (selected === candidate.application_id ? ' selected' : '')}>
        <label className="choice-label">
          <input type="radio" name={`review-${id}`} value={candidate.application_id} checked={selected === candidate.application_id} onChange={() => onSelect(candidate.application_id)} disabled={busy}/>
          <span className="choice-body">
            <span className="choice-title">{M.candidateLabel(candidate)}</span>
            <span className="choice-meta">Now {M.stateLabel(candidate.current_state)}{candidate.proposed ? ' · proposed by ASTRA’s matching' : ''}</span>
            <span className="choice-fields">Agrees on {M.joinList((candidate.matched_fields || []).map((f: string) => M.FIELD_LABELS[f] || f)).toLowerCase() || 'no field'}{candidate.conflicting_fields?.length ? ` · differs on ${M.joinList(candidate.conflicting_fields.map((f: string) => M.FIELD_LABELS[f] || f)).toLowerCase()}` : ''}</span>
          </span>
        </label>
        {candidate.job_id && <button type="button" className="textbtn choice-open" onClick={() => openJob({id: candidate.job_id})} aria-label={`View job: ${M.candidateLabel(candidate)}`}><ExternalLink size={15} aria-hidden/>View job</button>}
      </div>)}
      {item.candidates_truncated && <p className="muted-line">Only the first matches are shown.</p>}
    </fieldset> : <p className="no-candidate">{item.reason_code === 'NO_CANDIDATE_APPLICATION' ? '' : 'No tracked application can be confirmed against this message yet. '}If you applied, track the application from its job page and it will appear here. You can still reject the message.</p>}
    {problem && <div id={`review-${id}-problem`} role="alert"><Callout tone={problem.tone} title={problem.title}>{problem.detail && <p>{problem.detail}</p>}</Callout></div>}
    <div className="review-actions">
      {candidates.length > 0 && <button className="primary" onClick={() => onAct(item, 'confirm')} aria-disabled={busy} disabled={mine}>{mine ? 'Saving…' : 'Confirm application'}</button>}
      <button className="secondary" onClick={() => onAct(item, 'reject')} aria-disabled={busy} disabled={mine}>Not my application — reject</button>
    </div>
  </article>;
}

function Receipt({entry, refCallback}: {entry: Entry; refCallback: (el: HTMLElement | null) => void}) {
  const outcome = entry.outcome!;
  return <div className={'receipt ' + outcome.tone} ref={refCallback} tabIndex={-1}>
    <StatusBadge tone={outcome.tone}>{outcome.badge}</StatusBadge>
    <div><p className="receipt-title">{outcome.title}</p>{outcome.detail && <p>{outcome.detail}</p>}</div>
  </div>;
}

// ---------------------------------------------------------------------------
// Period figures
// ---------------------------------------------------------------------------
function Figure({id, icon, title, value, note, children}: {id: string; icon: React.ReactNode; title: string; value: string; note: React.ReactNode; children: React.ReactNode}) {
  return <section className="figure" aria-labelledby={id}>
    <div className="figure-top">{icon}<h3 id={id}>{title}</h3></div>
    <p className={'figure-value' + (/\d/.test(value) ? '' : ' is-words')}>{value}</p>
    <p className="figure-note">{note}</p>
    <details className="evidence">
      <summary>How this is counted</summary>
      <div className="evidence-body">{children}</div>
    </details>
  </section>;
}

function ItemList({items, empty, render}: {items: Row[]; empty: string; render: (item: Row) => React.ReactNode}) {
  if (!items?.length) return <p className="muted-line">{empty}</p>;
  return <ul className="evidence-list">{items.map((item, i) => <li key={i}>{render(item)}</li>)}</ul>;
}

export function PeriodFigures({data, openJob}: {data: Row; openJob: (job: Row) => void}) {
  const period = data.period.label.toLowerCase();
  const submitted = data.applications.submitted, stages = data.applications.stage_changes;
  const gmail = data.gmail, discovery = M.discoveryFigure(data.discovery);
  const gmailText = M.gmailFigure(gmail);
  const jobLink = (item: Row) => item.job_id
    ? <button className="textbtn" onClick={() => openJob({id: item.job_id})}>{[item.title, item.company].filter(Boolean).join(' · ') || 'Application #' + item.application_id}</button>
    : <span>{[item.title, item.company].filter(Boolean).join(' · ') || M.NOT_RECORDED}</span>;
  const stageSummary = M.joinList(Object.entries(stages.by_state || {}).filter(([, n]) => Number(n) > 0).map(([state, n]) => `${n} ${M.stateLabel(state).toLowerCase()}`));
  return <section className="progress-section" aria-labelledby="period-title">
    <div className="section-head plain"><h2 id="period-title">What happened {period === 'this week' || period === 'last week' ? period : 'in the ' + period}</h2></div>
    <div className="figures">
      <Figure id="fig-submitted" icon={<Send size={18} aria-hidden/>} title="Applications submitted" value={M.countOr(submitted.count)}
        note={submitted.count ? M.sourceBreakdown(submitted.by_source) : 'None recorded in this period.'}>
        <p>Applications whose recorded history entered <em>Applied</em> in this period (Asia/Dubai dates). An application counts once, whoever recorded it.</p>
        <ItemList items={submitted.items} empty="No submissions in this period." render={item => <>{jobLink(item)}<small>{M.formatDateTime(item.occurred_at)} · {M.SOURCE_LABELS[item.source_category] || item.source_category}</small></>}/>
        {submitted.truncated && <p className="muted-line">Showing the most recent {submitted.items.length}.</p>}
        {submitted.submission_date_not_recorded > 0 && <p className="muted-line">Not counted in any period: {M.plural(submitted.submission_date_not_recorded, 'application')} with no recorded submission date.</p>}
      </Figure>
      <Figure id="fig-stages" icon={<ArrowRight size={18} aria-hidden/>} title="Other stage changes" value={M.countOr(stages.count)}
        note={stages.count ? stageSummary : 'None recorded in this period.'}>
        <p>Saved, viewed, assessment, interview, offer, rejected and closed changes recorded in this period. Only you can record these today: Gmail detection covers initial application confirmations only.</p>
        <ItemList items={stages.items} empty="No stage changes in this period." render={item => <>{jobLink(item)}<small>{M.stateLabel(item.previous_state)} → {M.stateLabel(item.state)} · {M.formatDateTime(item.occurred_at)}</small></>}/>
        {stages.date_not_recorded > 0 && <p className="muted-line">Not counted: {M.plural(stages.date_not_recorded, 'change')} with no valid date.</p>}
      </Figure>
      <Figure id="fig-gmail" icon={<MailCheck size={18} aria-hidden/>} title="Gmail confirmations received" value={gmailText.value}
        note={gmail.status === 'OK' ? `${gmailText.note}` : gmailText.note}>
        <p>Medium- and high-confidence application confirmations received in this period, counted once per message.</p>
        {gmail.status === 'OK' && <ul className="evidence-facts">
          <li>Linked automatically: {gmail.by_outcome.LINKED}</li>
          <li>Confirmed by you: {gmail.by_outcome.USER_CONFIRMED}</li>
          <li>Waiting for your decision: {gmail.by_outcome.NEEDS_REVIEW}</li>
          <li>Rejected by you: {gmail.by_outcome.USER_REJECTED}</li>
          <li>Not used: {gmail.by_outcome.NO_ACTION}</li>
          <li>Not matched yet: {gmail.by_outcome.NOT_RECONCILED}</li>
          <li>Low confidence, never used: {gmail.low_confidence_not_used}</li>
        </ul>}
        {gmail.status === 'OK' && <ItemList items={gmail.items} empty="No confirmation was linked to an application in this period." render={item => <>{jobLink(item)}<small>{M.formatDateTime(item.received_at)} · {item.decision === 'USER_CONFIRMED' ? 'confirmed by you' : 'linked automatically'}{item.advanced_state ? '' : ' · state already at or past Applied'}</small></>}/>}
      </Figure>
      <Figure id="fig-discovery" icon={<Search size={18} aria-hidden/>} title="New relevant jobs from scans" value={discovery.value} note={discovery.note}>
        <p>Jobs a scan created for the first time and did not hard-reject, counted once per scan across all sources. This measures what your configured sources returned, not the job market.</p>
        <ItemList items={data.discovery.runs} empty="No scans in this period." render={run => <><span>Scan started {M.formatDateTime(run.run_created_at)}</span><small>{run.new === null ? runStatusText(run) : `${run.new} new · ${run.counts_complete ? 'complete' : 'incomplete'}`}</small></>}/>
      </Figure>
    </div>
  </section>;
}

function runStatusText(run: Row) {
  if (run.telemetry_status === 'RUN_IN_PROGRESS') return 'still running';
  if (run.telemetry_error) return 'telemetry error, no counts';
  return 'no telemetry recorded';
}

// ---------------------------------------------------------------------------
// Journey (current state), discovery health, outcomes
// ---------------------------------------------------------------------------
export function Journey({data, goTo}: {data: Row; goTo: (page: string) => void}) {
  const current = data.applications.current;
  const entered = (state: string) => state === 'APPLIED' ? data.applications.submitted.count
    : state === 'DISCOVERED' ? null : (data.applications.stage_changes.by_state || {})[state] ?? 0;
  const max = Math.max(0, ...M.STATES.map(s => current.states[s] || 0));
  const summary = M.joinList(M.STATES.filter(s => current.states[s]).map(s => `${current.states[s]} ${M.stateLabel(s).toLowerCase()}`));
  return <section className="panel progress-section" aria-labelledby="journey-title">
    <div className="section-head">
      <div><h2 id="journey-title">Where applications stand now</h2>
        <p>{current.total ? `${M.plural(current.total, 'application')}: ${summary}. “Entered” counts changes recorded in the selected period.` : 'No applications are tracked yet.'}</p></div>
      <button className="secondary compact" onClick={() => goTo('Applications')}>Open Applications<ArrowRight size={16} aria-hidden/></button>
    </div>
    {current.total === 0 && current.complete ? <div className="empty-inline neutral"><Info size={20} aria-hidden/><div><p className="empty-title">No applications yet.</p><p>Track a job from its detail view, or confirm a Gmail confirmation above, and it will appear here with its stage.</p></div></div> : <>
    {!current.complete && <Callout tone="warn">{M.plural(current.pending_initialization, 'application')} could not be read yet, so these counts are incomplete.</Callout>}
    <table className="journey">
      <caption className="visually-hidden">Applications by current stage, with changes entered in {data.period.label.toLowerCase()}</caption>
      <thead><tr><th scope="col">Stage</th><th scope="col">Now</th><th scope="col">Entered</th></tr></thead>
      <tbody>{M.STATES.map(state => {
        const now = current.states[state] || 0, moved = entered(state);
        return <tr key={state} className={now ? '' : 'is-zero'}>
          <th scope="row">{M.stateLabel(state)}</th>
          <td><span className="bar-cell"><Bar value={now} max={max} label={`${now} now`}/><span className="bar-value">{now}</span></span></td>
          <td className="num">{moved === null ? <span aria-label="Not an event">—</span> : moved ? `+${moved}` : '0'}</td>
        </tr>;
      })}</tbody>
    </table></>}
  </section>;
}

export function DiscoveryHealth({data, latest, latestFailed, goTo}: {data: Row; latest: Row | null; latestFailed: boolean; goTo: (page: string) => void}) {
  const head = M.runHeadline(latestFailed ? null : latest);
  const t = latest?.run?.telemetry || null;
  const rows = M.funnelRows(t);
  const max = Math.max(0, ...rows.map(r => r.value));
  const sources: Row[] = t?.sources || [];
  return <section className="panel progress-section" aria-labelledby="discovery-title">
    <div className="section-head">
      <div><h2 id="discovery-title">Discovery health</h2>
        <p>{latest?.run?.run_created_at ? `The latest scan, started ${M.formatDateTime(latest.run.run_created_at)}. ` : ''}<StatusBadge tone={head.tone}>{head.label}</StatusBadge> {head.detail}</p></div>
      <button className="secondary compact" onClick={() => goTo('Discovery')}>Open Discovery<ArrowRight size={16} aria-hidden/></button>
    </div>
    {rows.length > 0 && <div className="discovery-grid">
      <table className="funnel">
        <caption>Where postings were filtered in this scan</caption>
        <thead><tr><th scope="col">Stage</th><th scope="col">Count</th><th scope="col">Unit</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.stage}>
          <th scope="row">{row.label}<small className="unit-inline">{row.basis}</small></th>
          <td><span className="bar-cell"><Bar value={row.value} max={max} label={`${row.value} ${row.basis}`}/><span className="bar-value">{row.value.toLocaleString('en-GB')}</span></span></td>
          <td className="unit">{row.basis}</td>
        </tr>)}</tbody>
      </table>
      <div>
        <h3 className="subhead">Sources in this scan</h3>
        <ul className="source-list">{sources.map((source, i) => {
          const outcome = M.sourceOutcome(source);
          return <li key={source.source_id ?? i}>
            <span className="source-name">{source.source_name}</span>
            <StatusBadge tone={outcome.tone}>{outcome.label}</StatusBadge>
            <span className="source-counts">{outcome.countsShown ? `${source.funnel?.FETCHED ?? '—'} fetched · ${source.funnel?.RELEVANT ?? '—'} relevant · ${source.funnel?.NEW ?? '—'} new` : 'No counts — this source did not finish'}</span>
          </li>;
        })}</ul>
        {t?.sources_truncated > 0 && <p className="muted-line">{M.plural(t.sources_truncated, 'more source')} not listed.</p>}
      </div>
    </div>}
    {rows.length > 0 && <p className="muted-line">Jobs shown to you: not recorded — ASTRA keeps no display event. Unique-job stages count each job once across sources, so source rows do not add up to the scan total. Telemetry is kept for {data.discovery.retention_days} days.</p>}
  </section>;
}

export function Outcomes({data}: {data: Row}) {
  const o = data.outcomes;
  const weekly: Row[] = o.weekly || [];
  const max = Math.max(0, ...weekly.map(w => w.submitted));
  const total = weekly.reduce((sum, w) => sum + w.submitted, 0);
  const busiest = weekly.reduce<Row | null>((best, w) => !best || w.submitted > best.submitted ? w : best, null);
  const rates: [string, Row][] = [['Reached interview', o.interview], ['Received an offer', o.offer], ['Rejected', o.rejected], ['Replies you recorded', o.replies]];
  return <section className="panel progress-section" aria-labelledby="outcomes-title">
    <div className="section-head"><div><h2 id="outcomes-title">Outcomes across all applications</h2>
      <p>{o.submitted_total ? `Out of ${M.plural(o.submitted_total, 'submitted application')}. Percentages appear once there are at least ${o.rate_minimum}; small samples describe your activity, not what works.` : 'No submitted applications are recorded yet, so there are no outcomes, rates or weekly totals to show.'}</p></div></div>
    {o.submitted_total > 0 && <>
    <dl className="rates">{rates.map(([label, rate]) => {
      const text = M.rateText(rate);
      return <div key={label}><dt>{label}</dt><dd><strong>{text.main}</strong><span>{text.detail}</span></dd></div>;
    })}</dl>
    {(data.actions?.no_reply?.closed_by_you || 0) > 0 && <p className="muted-line">Closed by you as no response: {data.actions.no_reply.closed_by_you}. Their recorded stage is unchanged and they are not counted as rejections{data.actions.no_reply.reply_after_close ? `; ${data.actions.no_reply.reply_after_close} later received a reply` : ''}.</p>}
    <h3 className="subhead">Submissions by week</h3>
    <p className="muted-line">{total ? `${M.plural(total, 'dated submission')} in the last ${weekly.length} weeks; the busiest week began ${M.formatDay(busiest?.week_start)} with ${busiest?.submitted}.` : `No dated submissions in the last ${weekly.length} weeks.`}{o.submission_date_not_recorded ? ` ${M.plural(o.submission_date_not_recorded, 'submission')} without a recorded date ${o.submission_date_not_recorded === 1 ? 'is' : 'are'} not shown.` : ''}</p>
    <div className="columns" aria-hidden>
      {weekly.map(w => <div className="column" key={w.week_start}>
        <span className="column-value">{w.submitted || ''}</span>
        <span className="column-track"><span className="column-fill" style={{height: max ? `${Math.round((w.submitted / max) * 100)}%` : '0%'}}/></span>
        <span className="column-label">{M.formatDay(w.week_start).replace(/^\w+ /, '')}</span>
      </div>)}
    </div>
    <details className="evidence">
      <summary>Weekly submissions as a table</summary>
      <table className="plain-table"><thead><tr><th scope="col">Week beginning (Monday)</th><th scope="col">Submitted</th></tr></thead>
        <tbody>{weekly.map(w => <tr key={w.week_start}><td>{M.formatDay(w.week_start)}</td><td className="num">{w.submitted}</td></tr>)}</tbody></table>
    </details>
    <div className="breakdowns">
      <Breakdown title="By job source" rows={o.by_source}/>
      <Breakdown title="By CV version you recorded" rows={o.by_cv_version}/>
    </div></>}
  </section>;
}

function Breakdown({title, rows}: {title: string; rows: Row[]}) {
  return <div className="breakdown">
    <h3 className="subhead">{title}</h3>
    {rows?.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label={title}><table className="plain-table">
      <thead><tr><th scope="col">Name</th><th scope="col">Submitted</th><th scope="col">Interview</th><th scope="col">Offer</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.name}><th scope="row">{row.name}</th><td className="num">{row.submitted}</td><td className="num">{row.interview}</td><td className="num">{row.offer}</td></tr>)}</tbody>
    </table></div> : <p className="muted-line">No submitted applications yet.</p>}
  </div>;
}

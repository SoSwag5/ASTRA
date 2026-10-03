/**
 * Settings (#47 follow-up A): one page, organised by what a person is trying
 * to do. Each card keeps a local draft, shows unsaved changes in a save bar,
 * and reports the server's actual result. Every value is saved through the
 * existing routes and their existing validation; nothing new is stored.
 */
import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Briefcase, CircleUser, Download, ExternalLink, Lock, Monitor, Moon, Palette, Plus, Radar, RefreshCw, ShieldCheck, Sun, Target, Upload, Wrench} from 'lucide-react';
import * as S from './settingsModel';
import {ActionStatus, DirtyRegistry, Disclosure, SaveBar, useAction, useConfirm, useDraft, useSystemReducedMotion} from './ui';
import {AiAssistance, ApplicationAnswers, CareerFacts, DeleteLocalData, GmailPermissions, LocalDataCard, PlatformCapabilities, SecurityCheck} from './PrivacyPanel';
import {Reliability} from './Campaign';
import {GmailOperations} from './GmailOperations';
import {directionBetween, transition, motionMode} from './motion';
import './settings.css';

type Row = S.Row;
type Api = (path: string, method?: string, data?: any) => Promise<any>;
export type Appearance = {theme: S.ThemePreference; setTheme: (t: S.ThemePreference) => void; motion: S.MotionPreference; setMotion: (m: S.MotionPreference) => void};
type Props = {
  api: Api; cfg: Row; reload: () => Promise<any>; section: string; onSection: (id: string) => void;
  openWizard: () => void; download: (path: string) => void; editRecord: (kind: string, row: Row) => void;
  appearance: Appearance; onDirtyChange: (labels: Row) => void; goTo: (page: string) => void;
};

const ICONS: Record<string, React.ComponentType<{size?: number; 'aria-hidden'?: boolean}>> = {
  focus: Target, profile: CircleUser, sources: Radar, permissions: ShieldCheck, appearance: Palette, privacy: Lock, workspace: Wrench,
};

export function SettingsPage(props: Props) {
  const {section, onSection, onDirtyChange} = props;
  const confirm = useConfirm();
  const [dirty, setDirty] = useState<Row>({});
  const heading = useRef<HTMLHeadingElement>(null);
  const report = useCallback((labels: Row) => { setDirty(labels); onDirtyChange(labels); }, [onDirtyChange]);
  const current = S.SECTIONS.find(item => item.id === section) || S.SECTIONS[0];

  const choose = (id: string) => {
    if (id === current.id) return;
    const go = () => transition('section', () => onSection(id), directionBetween(S.SECTIONS.map(item => item.id), current.id, id),
      () => heading.current?.focus());
    const labels = Object.values(dirty) as string[];
    if (!labels.length) { go(); return; }
    const warning = S.leaveWarning(labels);
    confirm({title: warning.title, body: <p>{warning.body}</p>, confirmLabel: 'Discard changes', cancelLabel: 'Keep editing', tone: 'danger', onConfirm: go});
  };

  return <div className="settings">
    <nav className="settings-nav" aria-label="Settings sections">
      <label className="settings-select">Section
        <select value={current.id} onChange={event => choose(event.target.value)}>
          {S.SECTIONS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
      </label>
      <ul>{S.SECTIONS.map(item => {
        const Icon = ICONS[item.id];
        return <li key={item.id}><button aria-current={item.id === current.id ? 'page' : undefined} onClick={() => choose(item.id)}>
          {item.id === current.id && <i className="nav-indicator" aria-hidden/>}<Icon size={18} aria-hidden/><span>{item.label}</span></button></li>;
      })}</ul>
    </nav>
    <section className="settings-body page-enter" key={current.id} aria-labelledby="settings-section-title">
      <div className="settings-head">
        <h2 id="settings-section-title" ref={heading} tabIndex={-1}>{current.label}</h2>
        <p>{current.summary}</p>
      </div>
      <DirtyRegistry onChange={report}>
        {current.id === 'focus' && <FocusSection {...props}/>}
        {current.id === 'profile' && <ProfileSection {...props}/>}
        {current.id === 'sources' && <SourcesSection {...props}/>}
        {current.id === 'permissions' && <PermissionsSection {...props}/>}
        {current.id === 'appearance' && <AppearanceSection {...props}/>}
        {current.id === 'privacy' && <PrivacySection {...props}/>}
        {current.id === 'workspace' && <WorkspaceSection {...props}/>}
      </DirtyRegistry>
    </section>
  </div>;
}

// ---------------------------------------------------------------------------
// Career focus
// ---------------------------------------------------------------------------
function FocusSection({api, cfg, reload}: Props) {
  return <>
    <CareerTracksCard api={api} cfg={cfg} reload={reload}/>
    <RolesCard cfg={cfg} api={api} reload={reload}/>
    <RankingCard cfg={cfg} api={api} reload={reload}/>
    <CampaignPlanCard api={api}/>
  </>;
}

function CareerTracksCard({api, cfg, reload}: {api: Api; cfg: Row; reload: () => Promise<any>}) {
  const [tracks, setTracks] = useState<Row[]>([]), [suggestions, setSuggestions] = useState<Row[]>([]), [loaded, setLoaded] = useState(false);
  const card = useDraft<Row>('career-tracks', 'Career tracks', {career_tracks: cfg.career_tracks || [], custom_target_roles: S.listToLines(cfg.custom_target_roles)}, ['career_tracks', 'custom_target_roles']);
  useEffect(() => {
    Promise.all([api('/career-tracks'), api('/profile/career-suggestions').catch(() => [])])
      .then(([t, s]) => { setTracks(t); setSuggestions(s); setLoaded(true); }).catch(() => setLoaded(true));
  }, []);
  const selected: string[] = card.draft.career_tracks || [];
  const toggle = (id: string) => card.set('career_tracks', selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]);
  const save = () => card.save(async draft => {
    const result = await api('/settings/career-focus', 'POST', {career_tracks: draft.career_tracks, custom_target_roles: S.linesToList(draft.custom_target_roles)});
    await reload();
    return {career_tracks: result.career_tracks, custom_target_roles: S.listToLines(result.custom_target_roles)};
  });
  return <section className="panel settings-card"><h3>Career tracks</h3>
    <p>Choose the jobs you want to search for. These six built-in tracks cover technical careers. For business, finance, international relations or other fields, leave them unchecked and enter custom job titles below. CV signals are suggestions, not qualifications.</p>
    {!loaded ? <p className="muted-line" role="status">Loading career tracks…</p> : <div className="track-grid">{tracks.map(track => {
      const signals = suggestions.find(s => s.id === track.id);
      const on = selected.includes(track.id);
      return <label key={track.id} className={'track-option' + (on ? ' selected' : '')}>
        <input type="checkbox" checked={on} onChange={() => toggle(track.id)}/>
        <span><strong>{track.label}</strong>{(signals?.signal_count ?? 0) > 0 && <em className="status-badge">{signals?.signal_count} CV signals</em>}<small>{track.description}</small></span>
      </label>;
    })}</div>}
    <label>Custom target job titles, one per line<textarea value={card.draft.custom_target_roles} onChange={e => card.set('custom_target_roles', e.target.value)} placeholder={'Financial Analyst\nBusiness Analyst\nPolicy Research Assistant'}/></label>
    <button className="secondary" disabled={!selected.length} onClick={() => card.set('career_tracks', [])}>Clear technical choices</button>
    <SaveBar state={card} onSave={save} saveLabel="Save career focus"/>
  </section>;
}

const ROLE_FIELDS: [string, string, string][] = [
  ['target_roles', 'Target role titles', 'Generated from your career tracks; edit to fine-tune.'],
  ['excluded_roles', 'Excluded role titles', 'Roles never treated as a match.'],
  ['locations', 'Locations', 'Places a scan treats as compatible.'],
  ['blocked_companies', 'Blocked employers', 'Never shown as matches.'],
  ['blocked_domains', 'Blocked website domains', 'Links on these domains are never followed.'],
];

function RolesCard({api, cfg, reload}: {api: Api; cfg: Row; reload: () => Promise<any>}) {
  const keys = ROLE_FIELDS.map(([key]) => key);
  const card = useDraft<Row>('roles', 'Roles and places', Object.fromEntries(keys.map(key => [key, S.listToLines(cfg[key])])), keys);
  const save = () => card.save(async draft => {
    const result = await api('/settings', 'PUT', S.payload(draft, keys, keys));
    await reload();
    return Object.fromEntries(keys.map(key => [key, S.listToLines(result[key])]));
  });
  return <section className="panel settings-card"><h3>Roles, places and exclusions</h3><p>One entry per line.</p>
    <div className="formgrid">{ROLE_FIELDS.map(([key, label, hint]) => <label key={key}>{label}<textarea value={card.draft[key]} onChange={e => card.set(key, e.target.value)}/><small>{hint}</small></label>)}</div>
    <SaveBar state={card} onSave={save}/>
  </section>;
}

const RANK_FIELDS: [string, string, string][] = [
  ['minimum_score', 'Minimum priority to keep', 'Jobs below this index are not kept as matches.'],
  ['high_priority', 'High-priority threshold', 'At or above this index, a job is marked high priority.'],
  ['maybe_score', '“Maybe” threshold', 'Between this and high priority, a job is a maybe.'],
  ['salary_minimum', 'Salary floor', 'Only applied when a posting states a salary.'],
  ['followup_days', 'Days before a follow-up', 'Used when you mark an application as applied.'],
];

function RankingCard({api, cfg, reload}: {api: Api; cfg: Row; reload: () => Promise<any>}) {
  const keys = [...RANK_FIELDS.map(([key]) => key), 'weights'];
  const card = useDraft<Row>('ranking', 'Ranking thresholds', Object.fromEntries(keys.map(key => [key, cfg[key] ?? (key === 'weights' ? {} : 0)])), keys);
  const save = () => card.save(async draft => {
    const body = Object.fromEntries(RANK_FIELDS.map(([key]) => [key, Number(draft[key])]));
    const result = await api('/settings', 'PUT', {...body, weights: Object.fromEntries(Object.entries(draft.weights || {}).map(([k, v]) => [k, Number(v)]))});
    await reload();
    return result;
  });
  return <section className="panel settings-card"><h3>Ranking thresholds</h3>
    <p>The priority index orders jobs for review. It is a heuristic, not a probability of success.</p>
    <div className="formgrid">{RANK_FIELDS.map(([key, label, hint]) => <label key={key}>{label}<input type="number" value={card.draft[key]} onChange={e => card.set(key, e.target.value === '' ? '' : Number(e.target.value))}/><small>{hint}</small></label>)}</div>
    <Disclosure summary="Scoring weights"><p>How much each part of a job contributes to its priority index. At least one must be above zero.</p>
      <div className="formgrid">{Object.entries(card.draft.weights || {}).map(([key, value]) => <label key={key}>{key[0].toUpperCase() + key.slice(1).replaceAll('_', ' ')}<input type="number" min={0} value={value as any} onChange={e => card.set('weights', {...card.draft.weights, [key]: e.target.value === '' ? '' : Number(e.target.value)})}/></label>)}</div>
    </Disclosure>
    <SaveBar state={card} onSave={save}/>
  </section>;
}

function CampaignPlanCard({api}: {api: Api}) {
  const [saved, setSaved] = useState<Row | null>(null), [error, setError] = useState('');
  const load = () => api('/campaign').then(data => { setSaved(data.campaign); setError(''); }).catch(e => setError(e.message));
  useEffect(() => { load(); }, []);
  const keys = saved ? Object.keys(saved) : [];
  const listKeys = keys.filter(key => Array.isArray(saved?.[key]));
  const card = useDraft<Row>('campaign-plan', 'Campaign plan', saved ? Object.fromEntries(keys.map(key => [key, listKeys.includes(key) ? S.listToLines(saved[key]) : saved[key]])) : {}, keys);
  if (!saved) return <section className="panel settings-card"><h3>Campaign plan</h3>{error ? <div role="alert" className="errorbar"><span>The campaign plan could not load. {error}</span><button className="secondary" onClick={load}>Retry</button></div> : <p className="muted-line" role="status">Loading…</p>}</section>;
  const save = () => card.save(async draft => {
    const result = await api('/campaign/settings', 'PUT', S.payload(draft, keys, listKeys));
    return Object.fromEntries(keys.map(key => [key, listKeys.includes(key) ? S.listToLines(result[key]) : result[key]]));
  });
  return <section className="panel settings-card"><h3>Campaign plan</h3>
    <p>Adjacent roles and target country affect discovery; primary cities affect sorting. The other values record your plan and do not filter anything. Your CV is never sent to portals.</p>
    <div className="formgrid">{keys.map(key => {
      const value = card.draft[key];
      const label = key.replaceAll('_', ' ');
      return <label key={key}>{label[0].toUpperCase() + label.slice(1)}{listKeys.includes(key)
        ? <textarea value={value} onChange={e => card.set(key, e.target.value)}/>
        : <input type={typeof saved[key] === 'number' ? 'number' : key.includes('date') ? 'date' : 'text'} value={value ?? ''}
          onChange={e => card.set(key, typeof saved[key] === 'number' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value)}/>}</label>;
    })}</div>
    <SaveBar state={card} onSave={save} saveLabel="Save plan"/>
  </section>;
}

// ---------------------------------------------------------------------------
// Profile & CV
// ---------------------------------------------------------------------------
function ProfileSection({api, reload}: Props) {
  const [profile, setProfile] = useState<Row | null | undefined>(undefined), [error, setError] = useState('');
  const load = () => api('/profile').then(value => { setProfile(value); setError(''); }).catch(e => setError(e.message));
  useEffect(() => { load(); }, []);
  const refresh = async () => { await load(); await reload(); };
  return <>
    <MasterCvCard api={api} profile={profile} refresh={refresh} error={error} retry={load}/>
    {profile && <CandidateCard profile={profile} api={api} refresh={refresh}/>}
    <CareerFacts api={api} refresh={reload}/>
    <ApplicationAnswers api={api} refresh={reload}/>
  </>;
}

function MasterCvCard({api, profile, refresh, error, retry}: {api: Api; profile: Row | null | undefined; refresh: () => Promise<any>; error: string; retry: () => void}) {
  const confirm = useConfirm();
  const action = useAction();
  const input = useRef<HTMLInputElement>(null);
  const upload = (file: File) => action.run(async () => {
    const form = new FormData(); form.append('file', file);
    await api('/import/cv', 'POST', form);
    await refresh();
  }, 'Master CV imported. Review the extracted facts below and confirm them before generating documents.', 'Reading your CV…');
  const chosen = (file?: File) => {
    if (!file) return;
    if (!profile) { upload(file); return; }
    confirm({title: 'Replace your master CV?', tone: 'danger', confirmLabel: 'Replace master CV', cancelLabel: 'Keep current CV',
      body: <><p>ASTRA will read <strong>{file.name}</strong> and replace the facts extracted from your current master CV.</p><ul><li>Corrections you made to extracted facts are replaced.</li><li>You will need to review and confirm the new facts before generating documents.</li><li>If reading the new file fails, your current CV is kept.</li></ul></>,
      onConfirm: () => { upload(file); }});
  };
  return <section className="panel settings-card"><div className="card-head"><Briefcase size={20} aria-hidden/><div><h3>Master CV</h3>
    <p>{profile === undefined ? (error ? '' : 'Checking your CV…') : profile ? (profile.confirmed ? 'Imported and confirmed by you.' : 'Imported. The extracted facts still need your confirmation.') : 'No master CV has been imported yet.'}</p></div></div>
    {error && <div role="alert" className="errorbar"><span>Your profile could not load. {error}</span><button className="secondary" onClick={retry}>Retry</button></div>}
    <input ref={input} type="file" accept=".pdf" className="visually-hidden" tabIndex={-1} aria-hidden onChange={e => { chosen(e.target.files?.[0]); e.target.value = ''; }}/>
    <button className="secondary" disabled={action.busy || profile === undefined} aria-busy={action.busy} onClick={() => input.current?.click()}>
      <Upload size={16} aria-hidden/>{action.busy ? 'Reading your CV…' : profile ? 'Replace master CV (PDF)' : 'Import master CV (PDF)'}</button>
    <ActionStatus status={action.status}/>
  </section>;
}

function CandidateCard({profile, api, refresh}: {profile: Row; api: Api; refresh: () => Promise<any>}) {
  const declarations = Object.fromEntries(Object.entries(profile.declarations || {}).filter(([key, value]) => typeof value !== 'object' && !['extraction_state', 'field_sources'].includes(key)));
  const keys = ['name', 'email', 'phone', 'location', 'summary', 'declarations', 'confirmed'];
  const card = useDraft<Row>('candidate', 'Candidate profile', {name: profile.name, email: profile.email, phone: profile.phone, location: profile.location, summary: profile.summary, declarations, confirmed: profile.confirmed}, keys);
  const save = () => card.save(async draft => {
    const result = await api('/profile', 'PUT', {...draft, declarations: {...profile.declarations, ...draft.declarations}});
    await refresh();
    return {...result, declarations: draft.declarations};
  });
  const needsReconfirm = card.status === 'saved' && profile.confirmed === false;
  return <section className="panel settings-card"><h3>Candidate profile</h3><p>Used on generated documents. Changing a field clears your confirmation unless you confirm again here.</p>
    <div className="formgrid">{['name', 'email', 'phone', 'location'].map(key => <label key={key}>{key[0].toUpperCase() + key.slice(1)}<input dir="auto" value={card.draft[key] || ''} onChange={e => card.set(key, e.target.value)}/></label>)}</div>
    <label>Professional summary<textarea dir="auto" value={card.draft.summary || ''} onChange={e => card.set('summary', e.target.value)}/></label>
    {Object.keys(declarations).length > 0 && <Disclosure summary="Declarations"><div className="formgrid">{Object.keys(declarations).map(key => <label key={key}>{key.replaceAll('_', ' ')}<input value={String(card.draft.declarations?.[key] ?? '')} onChange={e => card.set('declarations', {...card.draft.declarations, [key]: e.target.value})}/></label>)}</div></Disclosure>}
    <label className="check"><input type="checkbox" checked={!!card.draft.confirmed} onChange={e => card.set('confirmed', e.target.checked)}/>I reviewed and confirm this profile</label>
    {needsReconfirm && <p className="callout warn" role="status">Saved. Because a field changed, the profile now needs your confirmation before documents are generated.</p>}
    <SaveBar state={card} onSave={save} saveLabel="Save profile"/>
  </section>;
}

// ---------------------------------------------------------------------------
// Discovery sources
// ---------------------------------------------------------------------------
function SourcesSection({api, goTo}: Props) {
  const [sources, setSources] = useState<Row[] | null>(null), [error, setError] = useState(''), [pending, setPending] = useState<number | null>(null);
  const [name, setName] = useState(''), [url, setUrl] = useState('');
  const toggle = useAction(), add = useAction();
  const load = () => api('/records/sources').then(rows => { setSources(rows.filter((s: Row) => s.adapter !== 'manual')); setError(''); }).catch(e => setError(e.message));
  useEffect(() => { load(); }, []);
  const setEnabled = (source: Row, enabled: boolean) => {
    setPending(source.id);
    toggle.run(async () => { await api('/records/sources', 'POST', {id: source.id, enabled}); await load(); },
      `${source.name} ${enabled ? 'will be checked by your next scan' : 'is paused; scans skip it until you turn it back on'}.`, 'Saving…')
      .finally(() => setPending(null));
  };
  return <>
    <section className="panel settings-card"><h3>Configured sources</h3>
      <p>Public company boards a scan checks. Turning a source off skips it without deleting it. Scans still start only when you press Start Scan in Discovery.</p>
      {error && <div role="alert" className="errorbar"><span>Sources could not load. {error}</span><button className="secondary" onClick={load}>Retry</button></div>}
      {!sources && !error && <p className="muted-line" role="status">Loading sources…</p>}
      {sources && !sources.length && <p className="muted-line">No company boards yet. Add one below.</p>}
      {sources && sources.length > 0 && <ul className="source-rows">{sources.map(source => <li key={source.id}>
        <div><strong>{source.name}</strong><small>{source.adapter} · {source.board || source.url}</small></div>
        <button role="switch" className="switch" aria-checked={!!source.enabled} disabled={pending !== null} aria-busy={pending === source.id}
          aria-label={`Include ${source.name} in scans`} onClick={() => setEnabled(source, !source.enabled)}>
          <span className="switch-track" aria-hidden/><span>{source.enabled ? 'On' : 'Paused'}</span></button>
      </li>)}</ul>}
      <ActionStatus status={toggle.status}/>
      <button className="textbtn" onClick={() => goTo('Discovery')}><ExternalLink size={15} aria-hidden/>Scan or review sources in Discovery</button>
    </section>
    <section className="panel settings-card"><h3>Add a company board</h3>
      <p>Paste a public Greenhouse, Lever, Ashby or SmartRecruiters board link. ASTRA works out the connection details. SmartRecruiters scans UAE listings only.</p>
      <form className="add-source" onSubmit={e => { e.preventDefault(); add.run(async () => { const result = await api('/search/sources', 'POST', {name, url}); if (result.exists) throw Error(`${result.name} is already configured.`); setName(''); setUrl(''); await load(); }, 'Source added. It will be checked by your next scan.', 'Adding source…'); }}>
        <label>Company name<input required value={name} onChange={e => setName(e.target.value)} placeholder="Northwind Analytics"/></label>
        <label>Board link<input required type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://jobs.lever.co/company"/></label>
        <button className="primary" disabled={add.busy} aria-busy={add.busy}><Plus size={16} aria-hidden/>{add.busy ? 'Adding…' : 'Add source'}</button>
      </form>
      <ActionStatus status={add.status}/>
    </section>
  </>;
}

// ---------------------------------------------------------------------------
// Gmail & permissions
// ---------------------------------------------------------------------------
function PermissionsSection({api, cfg, reload, editRecord, goTo}: Props) {
  return <>
    <GmailPermissions api={api}/>
    <GmailOperations api={api} onReview={() => goTo('Progress')}/>
    <AiAssistance api={api} cfg={cfg} reload={reload}/>
    <PreparationCard api={api} cfg={cfg} reload={reload}/>
    <DomainPermissions api={api} editRecord={editRecord}/>
    <PlatformCapabilities api={api}/>
  </>;
}

function PreparationCard({api, cfg, reload}: {api: Api; cfg: Row; reload: () => Promise<any>}) {
  const keys = ['autopilot', 'daily_limit', 'cover_letter'];
  const card = useDraft<Row>('preparation', 'Application preparation', {autopilot: cfg.autopilot || 'PREPARE_ONLY', daily_limit: cfg.daily_limit ?? 10, cover_letter: cfg.cover_letter || 'required'}, keys);
  const save = () => card.save(async draft => { const result = await api('/settings', 'PUT', {...draft, daily_limit: Number(draft.daily_limit)}); await reload(); return result; });
  return <section className="panel settings-card"><h3>Application preparation</h3>
    <p className="callout info">External form filling and automatic submission are disabled in this release. ASTRA prepares documents; you review and submit in your own browser. Dry run is always on.</p>
    <div className="formgrid">
      <label>Preparation mode<select value={card.draft.autopilot} onChange={e => card.set('autopilot', e.target.value)}><option value="PREPARE_ONLY">Prepare only</option><option value="OFF">Off</option></select><small>Off stops scheduled preparation tasks.</small></label>
      <label>Daily preparation limit<input type="number" min={0} max={100} value={card.draft.daily_limit} onChange={e => card.set('daily_limit', e.target.value === '' ? '' : Number(e.target.value))}/></label>
      <label>Cover letters<select value={card.draft.cover_letter} onChange={e => card.set('cover_letter', e.target.value)}><option value="required">Only when a posting requires one</option><option value="always">Always prepare one</option></select></label>
    </div>
    <SaveBar state={card} onSave={save}/>
  </section>;
}

function DomainPermissions({api, editRecord}: {api: Api; editRecord: (kind: string, row: Row) => void}) {
  const [sites, setSites] = useState<Row[] | null>(null);
  useEffect(() => {
    const load = () => api('/records/sites').then(setSites).catch(() => setSites([]));
    load();
    window.addEventListener('records-updated', load);
    return () => window.removeEventListener('records-updated', load);
  }, []);
  return <section className="panel settings-card"><h3>Legacy domain settings</h3>
    <p>External form automation and arbitrary page imports are disabled. These older per-domain settings cannot grant permission to submit anything.</p>
    {sites && sites.length > 0 ? <ul className="source-rows">{sites.map(site => <li key={site.id}><div><strong>{site.domain}</strong><small>{site.enabled ? 'Enabled' : 'Disabled'} · automatic submit {site.auto_submit ? 'recorded as on (not used)' : 'off'}</small></div><button className="secondary compact" onClick={() => editRecord('sites', site)}>Edit</button></li>)}</ul> : <p className="muted-line">{sites ? 'No domains are configured.' : 'Loading…'}</p>}
    <button className="secondary" onClick={() => editRecord('sites', {domain: '', kind: 'generic', enabled: false, permitted: false, auto_submit: false, config: {submit_selector: 'button[type="submit"]', success_selector: '', resource_domains: []}})}>Configure a domain</button>
  </section>;
}

// ---------------------------------------------------------------------------
// Appearance
// ---------------------------------------------------------------------------
function AppearanceSection({appearance}: Props) {
  const systemReduced = useSystemReducedMotion();
  const mode = motionMode(appearance.motion, systemReduced);
  const themes: [S.ThemePreference, string, string, React.ComponentType<{size?: number; 'aria-hidden'?: boolean}>][] = [
    ['light', 'Porcelain', 'Warm light surfaces. The default.', Sun], ['dark', 'Midnight', 'Deep blue surfaces for low light.', Moon], ['system', 'Match system', 'Follows your operating system.', Monitor]];
  const motions: [S.MotionPreference, string, string][] = [
    ['system', 'Match system', 'Brief transitions, unless your operating system asks for reduced motion.'],
    ['full', 'Full motion', 'Choose this to use animations in ASTRA, even if Windows reduces them. You can return to Match system or Reduce motion anytime.'],
    ['reduced', 'Reduce motion', 'No transitions or animated feedback in ASTRA. Every state still shows in colour, icon and text.']];
  return <>
    <section className="panel settings-card"><h3>Theme</h3>
      <fieldset className="radio-cards three"><legend className="visually-hidden">Theme</legend>{themes.map(([value, label, help, Icon]) =>
        <label key={value} className={'radio-card' + (appearance.theme === value ? ' selected' : '')}>
          <input type="radio" name="theme" value={value} checked={appearance.theme === value} onChange={() => appearance.setTheme(value)}/>
          <span className={'theme-swatch ' + value} aria-hidden><Icon size={18}/></span><span><strong>{label}</strong><small>{help}</small></span></label>)}</fieldset>
      <p className="muted-line" role="status">Applied immediately and remembered in this browser only.</p>
    </section>
    <section className="panel settings-card"><h3>Motion</h3>
      <fieldset className="radio-cards"><legend className="visually-hidden">Motion</legend>{motions.map(([value, label, help]) =>
        <label key={value} className={'radio-card' + (appearance.motion === value ? ' selected' : '')}>
          <input type="radio" name="motion" value={value} checked={appearance.motion === value} onChange={() => appearance.setMotion(value)}/>
          <span><strong>{label}</strong><small>{help}</small></span></label>)}</fieldset>
      <div className="motion-preview"><p role="status">{mode === "full" ? "Motion is on. Open the preview below to see it." : mode === "reduced-by-system" ? "Your operating system asks for reduced motion, so ASTRA stays still." : "Reduced motion is on in ASTRA. All feedback remains visible."}</p><Disclosure summary="Preview opening and closing"><p>This panel slides open and closed when motion is on. Page switches and reporting-period changes use the same brief, interruptible movement.</p></Disclosure></div>
    </section>
  </>;
}

// ---------------------------------------------------------------------------
// Privacy & local data
// ---------------------------------------------------------------------------
function PrivacySection({api, reload}: Props) {
  return <>
    <SecurityCheck api={api}/>
    <LocalDataCard api={api}/>
    <Reliability api={api}/>
    <DeleteLocalData api={api} refresh={reload}/>
  </>;
}

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------
function WorkspaceSection({api, cfg, reload, openWizard, download}: Props) {
  const card = useDraft<Row>('workspace', 'Excel tracker', {auto_sync: !!cfg.auto_sync, max_retries: cfg.max_retries ?? 0}, ['auto_sync', 'max_retries']);
  const save = () => card.save(async draft => { const result = await api('/settings', 'PUT', {auto_sync: draft.auto_sync, max_retries: Number(draft.max_retries)}); await reload(); return result; });
  const sync = useAction();
  return <>
    <section className="panel settings-card"><h3>Setup</h3><p>Walk through the first-run steps again: CV, profile, tracker, focus and rules. Nothing is changed until you save a step.</p>
      <button className="secondary" onClick={openWizard}>Open setup wizard</button></section>
    <section className="panel settings-card"><h3>Excel tracker</h3>
      <div className="actions">
        <button className="secondary" onClick={() => download('tracker.xlsx')}><Download size={16} aria-hidden/>Download tracker</button>
        <button className="secondary" disabled={sync.busy} aria-busy={sync.busy} onClick={() => sync.run(() => api('/sync', 'POST'), (result: Row) => result?.pending ? (result.message || 'Your data is saved. The Excel file will update once it is closed.') : 'Excel tracker updated.', 'Updating the tracker…')}>
          <RefreshCw size={16} aria-hidden className={sync.busy ? 'spin' : ''}/>{sync.busy ? 'Updating…' : 'Update tracker now'}</button>
      </div>
      <ActionStatus status={sync.status}/>
      <label className="check"><input type="checkbox" checked={card.draft.auto_sync} onChange={e => card.set('auto_sync', e.target.checked)}/>Keep the tracker updated on a schedule while ASTRA is running</label>
      <label className="narrow-field">Retries for a failed update<input type="number" min={0} max={5} value={card.draft.max_retries} onChange={e => card.set('max_retries', e.target.value === '' ? '' : Number(e.target.value))}/></label>
      <SaveBar state={card} onSave={save}/>
    </section>
    <section className="panel settings-card"><h3>Access</h3><p>Optional access-key protection is configured on this computer. The browser keeps only an expiring session in memory; closing the workspace ends it.</p></section>
  </>;
}

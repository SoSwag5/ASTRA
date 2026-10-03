import React, {useEffect, useRef, useState} from 'react';
import {Check, ChevronLeft, ChevronRight, CircleDashed, Info, LoaderCircle, RefreshCw, Upload, X} from 'lucide-react';
import {CareerFocus} from './CareerFocus';
import {Disclosure, OutcomeRegion} from './ui';
import {continueHint, focusSummary, writeThenRefresh, type Outcome, type StepWords} from './setupModel';
import './setup.css';

export {continueHint} from './setupModel';
type Row = Record<string, any>;
export const setupTitles = ['Upload your CV', 'Check your CV facts', 'Bring an existing tracker (optional)', 'Choose the jobs you want', 'Ready to find jobs'];
// Preserve the stored completion marker; old advanced steps become the finish page.
export function setupStep(value: number) { return Math.max(1, Math.min(5, Number(value) || 1)); }
export function mayContinue(step: number, profile: Row | null, cfg: Row) {
  return step === 1 ? !!profile : step === 2 ? !!profile?.confirmed : step === 4 ? !!cfg.search_focus_confirmed : true;
}

/**
 * What a step shows when nothing was attempted in this session: success that
 * the server already confirmed stays visible when someone returns.
 */
export function savedOutcome(step: number, profile: Row | null): Outcome | null {
  if (step === 1 && profile) return {tone: 'good', title: 'Your CV is imported.', text: `${profile.name ? 'ASTRA read the CV for ' + profile.name + '. ' : ''}Continue to check its facts, or replace it with another PDF.`};
  if (step === 2 && profile?.confirmed) return {tone: 'good', title: 'Facts confirmed.', text: 'Your CV facts are confirmed. Check them again after making corrections.'};
  return null;
}

type Props = {
  step: number; profile: Row | null; cfg: Row; tracks?: Row[];
  api: (path: string, method?: string, data?: any) => Promise<any>;
  reload: () => Promise<any>; editProfile: () => void;
  close: () => void; back: () => void; next: () => Promise<any>;
};
type Busy = '' | 'cv' | 'facts' | 'tracker' | 'refresh' | 'next';

export function SetupWizard({step, profile, cfg, tracks = [], api, reload, editProfile, close, back, next}: Props) {
  const [busy, setBusy] = useState<Busy>('');
  const [outcomes, setOutcomes] = useState<Record<number, Outcome | null>>({});
  // A write that succeeded while the refresh failed: the step offers Refresh, not a second write.
  const [unconfirmed, setUnconfirmed] = useState<Record<number, Outcome>>({});
  const [nextError, setNextError] = useState<Outcome | null>(null);
  const [tracker, setTracker] = useState<Row | null>(null);
  const [focusDirty, setFocusDirty] = useState(false);
  const [focusPending, setFocusPending] = useState(false);
  const [focusBusy, setFocusBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  // Direction of travel, fixed for the life of each step's content.
  const travel = useRef({step, dir: 'forward'});
  if (travel.current.step !== step) travel.current = {step, dir: step < travel.current.step ? 'back' : 'forward'};
  useEffect(() => {heading.current?.closest('section')?.scrollTo(0, 0); heading.current?.focus(); setNextError(null);}, [step]);

  const report = (at: number, outcome: Outcome | null) => setOutcomes(all => ({...all, [at]: outcome}));
  async function attempt(kind: Busy, at: number, write: () => Promise<any>, words: StepWords) {
    if (busy || unconfirmed[at]) return;
    setBusy(kind); report(at, null);
    const done = await writeThenRefresh(write, reload, words);
    setUnconfirmed(all => { const rest = {...all}; delete rest[at]; return done.written && !done.refreshed ? {...rest, [at]: words.saved(done.result)} : rest; });
    report(at, done.outcome);
    setBusy('');
    return done;
  }
  async function refresh(at: number) {
    if (busy) return;
    setBusy('refresh');
    try { await reload(); report(at, unconfirmed[at]); setUnconfirmed(all => { const rest = {...all}; delete rest[at]; return rest; }); }
    catch (e: any) { report(at, {tone: 'warn', title: 'ASTRA still could not refresh.', text: `${e?.message || ''} What you saved is kept. Try Refresh again.`}); }
    finally { setBusy(''); }
  }
  const form = (file: File) => { const data = new FormData(); data.append('file', file); return data; };
  const importCv = (file: File) => attempt('cv', 1, () => api('/import/cv', 'POST', form(file)), {
    failed: 'Your CV was not imported.',
    failureHint: (profile ? 'Your previously imported CV is still in use. ' : '') + 'Choose a PDF with selectable text and try again.',
    unconfirmed: 'Your CV was imported, but ASTRA could not refresh to show it.',
    saved: () => ({tone: 'good', title: 'CV imported.', text: `ASTRA read ${file.name}. Next, check the facts it found.`})});
  const confirmFacts = () => attempt('facts', 2, () => api('/profile', 'PUT', {confirmed: true}), {
    failed: 'Your facts were not confirmed.',
    unconfirmed: 'Your facts were confirmed, but ASTRA could not refresh to show it.',
    saved: () => savedOutcome(2, {confirmed: true})!});
  const importTracker = (file: File) => attempt('tracker', 3, () => api('/import/tracker', 'POST', form(file)), {
    failed: 'The tracker was not imported.',
    failureHint: 'It needs Company and Job Title columns. Nothing from this file was added.',
    unconfirmed: 'The tracker was imported, but ASTRA could not refresh to show it.',
    saved: (result: Row) => ({tone: 'good', title: 'Tracker imported.', text: trackerText(file.name, result)})}).then(done => { if (done?.written) setTracker({name: file.name, ...(done.result || {})}); });
  async function goOn() {
    if (busy || pending || hint) return;
    setBusy('next'); setNextError(null);
    try { await next(); }
    catch (e: any) { setNextError({tone: 'bad', title: 'Your progress was not saved.', text: `${e?.message || 'Try again.'} You are still on this step.`}); }
    finally { setBusy(''); }
  }

  // Closing with a failed refresh still asks once more, so reopening setup shows the latest saved state.
  const leave = () => { if (working) return; if (pending || Object.keys(unconfirmed).length) reload().catch(() => {}); close(); };
  const shown = outcomes[step] ?? savedOutcome(step, profile);
  const refreshAction = unconfirmed[step] ? <button className="secondary compact" disabled={!!busy} aria-busy={busy === 'refresh'} onClick={() => refresh(step)}>
    <RefreshCw size={15} className={busy === 'refresh' ? 'spin' : ''} aria-hidden/>{busy === 'refresh' ? 'Refreshing…' : 'Refresh'}</button> : undefined;
  // A write in flight cannot be dismissed. A saved-but-unrefreshed state can: leaving never repeats a write.
  const working = !!busy || (step === 4 && focusBusy);
  const pending = !!unconfirmed[step] || (step === 4 && focusPending);
  const hint = pending ? 'Refresh to confirm your saved changes before continuing.' : continueHint(step, profile, cfg, focusDirty);
  const facts: [string, string][] = [['employments', 'Experience'], ['projects', 'Projects'], ['education', 'Education'], ['certifications', 'Certifications and courses']];
  const uploadLabel = (kind: Busy, idle: React.ReactNode, working: string) => busy === kind ? <><LoaderCircle size={16} className="spin" aria-hidden/>{working}</> : <><Upload size={16} aria-hidden/>{idle}</>;
  return <div className="overlay"><section className="dialog wizard" role="dialog" aria-modal="true" aria-labelledby="setup-heading" aria-busy={working}>
    <div className="eyebrow">SET UP YOUR WORKSPACE · STEP {step} OF 5</div>
    <button className="close icon" disabled={working} aria-label="Close setup" onClick={leave}><X size={20} aria-hidden/></button>
    <ol className="steps" aria-label="Setup progress">{setupTitles.map((title, i) =>
      <li key={title} className={i < step - 1 ? 'filled done' : i === step - 1 ? 'filled current' : ''} aria-current={i === step - 1 ? 'step' : undefined}>
        <span className="visually-hidden">{title}{i < step - 1 ? ' (passed)' : ''}</span></li>)}</ol>
    <div className="wizard-step" data-dir={travel.current.dir} key={step}>
    <h2 id="setup-heading" ref={heading} tabIndex={-1}>{setupTitles[step - 1]}</h2>
    {step === 1 && <><p>Choose the PDF version of your CV. ASTRA reads the text on this computer; it does not search your folders or send your CV to an AI service.</p>
      <label className={(profile ? 'secondary' : 'primary') + ' upload setup-upload'} aria-busy={busy === 'cv'}>{uploadLabel('cv', profile ? 'Replace CV (PDF)' : 'Choose CV (PDF)', 'Reading your CV…')}
        <input aria-label={profile ? 'Replace CV PDF' : 'Choose CV PDF'} disabled={!!busy || pending} type="file" accept=".pdf" onChange={e => {const file = e.target.files?.[0]; e.target.value = ''; if (file) importCv(file);}}/></label>
      <p className="muted-line">Use a PDF with selectable text. A photo or scanned CV may not work. You will check the extracted facts next.</p></>}
    {step === 2 && <><p>Check what ASTRA actually extracted below. Correct anything missing or inaccurate before confirming.</p>
      <div className="setup-facts" tabIndex={0} role="region" aria-label="Facts extracted from your CV"><h3>{profile?.name || 'Name not found'}</h3><p>{profile?.summary || 'No summary found. You can add it in your profile.'}</p>
        <h3>Skills</h3><p>{profile?.skills?.map((s: Row) => s.text).join(', ') || 'No skills found. Add your skills before matching jobs.'}</p>
        {facts.map(([key, title]) => <div key={key}><h3>{title}</h3>{profile?.[key]?.length ? profile[key].map((f: Row) => <p key={f.id}>{f.text}</p>) : <p>No facts extracted for this section.</p>}</div>)}</div>
      <Disclosure summary="See the extracted CV text"><pre className="source">{profile?.raw_text}</pre></Disclosure>
      <div className="actions"><button className="secondary" disabled={!!busy || pending} onClick={editProfile}>Correct my profile</button>
        <button className="primary" disabled={!!busy || pending || !profile || !!profile?.confirmed} aria-busy={busy === 'facts'} onClick={confirmFacts}>
          {busy === 'facts' ? <><LoaderCircle size={16} className="spin" aria-hidden/>Confirming…</> : <><Check size={16} aria-hidden/>{profile?.confirmed ? 'Facts confirmed' : 'These facts are correct'}</>}</button></div></>}
    {step === 3 && <><p>Already tracking applications in an Excel spreadsheet? You can import an XLSX tracker here. If you do not have one, skip this step. ASTRA will keep your new applications for you.</p>
      <label className="secondary upload setup-upload" aria-busy={busy === 'tracker'}>{uploadLabel('tracker', tracker ? 'Import another XLSX tracker' : 'Choose an XLSX tracker', 'Importing your tracker…')}
        <input aria-label="Choose optional XLSX tracker" disabled={!!busy || pending} type="file" accept=".xlsx" onChange={e => {const file = e.target.files?.[0]; e.target.value = ''; if (file) importTracker(file);}}/></label>
      <p className="muted-line">This is optional. Nothing is imported unless you choose a file.</p></>}
    {[1, 2, 3].includes(step) && <OutcomeRegion outcome={shown} action={refreshAction}/>}
    {step === 4 && <CareerFocus api={api} cfg={cfg} onSaved={reload} onDirtyChange={setFocusDirty} onPendingChange={(pending, working) => {setFocusPending(pending); setFocusBusy(working);}}/>}
    {step === 5 && <><p><strong>Rule-based matching is the recommended starting point.</strong> It works without an AI account or subscription. AI is optional, under Settings → Gmail &amp; permissions → Optional AI assistance; it is not needed to find or prepare jobs.</p>
      {cfg.provider && cfg.provider !== 'rules' && <p className="notice">You previously selected an optional AI provider. You can return to rule-based in Settings. Your saved choice has been kept.</p>}
      <h3 className="setup-subhead">Your setup</h3>
      <ul className="setup-summary">
        <SummaryItem done={!!profile} label="CV" text={profile ? 'Imported' : 'Not imported yet. Go back to step 1.'}/>
        <SummaryItem done={!!profile?.confirmed} label="CV facts" text={profile?.confirmed ? 'Confirmed by you' : 'Not confirmed yet. Go back to step 2.'}/>
        <SummaryItem done={!!tracker} optional label="Existing tracker" text={tracker ? `Imported from ${tracker.name}` : 'Optional. You can import one later from Jobs.'}/>
        <SummaryItem done={!!cfg.search_focus_confirmed} label="Search focus" text={cfg.search_focus_confirmed ? focusSummary(cfg, tracks) || 'Saved' : 'Not saved yet. Go back to step 4.'}/>
      </ul>
      <h3 className="setup-subhead">Next steps</h3>
      <ol className="setup-next"><li>Open <strong>Start scanning</strong> on the left.</li><li>Three public starter feeds are included. You can add more boards, or use <strong>Search elsewhere</strong> for manual job sites.</li><li>Press <strong>Start scanning now</strong>, check the preview, then <strong>Confirm and start scan</strong>.</li><li>Review a job, prepare and check your documents, then apply on the employer's website yourself.</li></ol>
      <p>Scanning starts only after your confirmation. Opening ASTRA does not start a scan or submit an application.</p></>}
    </div>
    {nextError && <OutcomeRegion outcome={nextError}/>}
    <div className="actions setup-actions">
      <button className="secondary" disabled={!!busy || pending || step === 1} onClick={back}><ChevronLeft size={16} aria-hidden/>Back</button>
      <div className="setup-continue">
        {hint && <p className="setup-hint" id="setup-continue-hint"><Info size={16} aria-hidden/>{hint}</p>}
        <button className="primary" disabled={!!busy || !!hint} aria-busy={busy === 'next'} aria-describedby={hint ? 'setup-continue-hint' : undefined} onClick={goOn}>
          {busy === 'next' ? <><LoaderCircle size={16} className="spin" aria-hidden/>Saving…</> : step === 5 ? 'Open Start scanning' : step === 3 && !tracker ? 'Skip for now' : 'Continue'}<ChevronRight size={16} aria-hidden/></button>
      </div>
    </div>
  </section></div>;
}

function trackerText(name: string, result: Row) {
  const added = Number(result?.imported) || 0, skipped = Number(result?.duplicates) || 0;
  return `${name}: ${added} ${added === 1 ? 'job' : 'jobs'} added${skipped ? `, ${skipped} already in ASTRA left unchanged` : ''}. Continue to choose the jobs you want.`;
}

function SummaryItem({done, optional = false, label, text}: {done: boolean; optional?: boolean; label: string; text: string}) {
  return <li className={done ? 'done' : optional ? 'optional' : 'todo'}>
    {done ? <Check size={16} aria-hidden/> : <CircleDashed size={16} aria-hidden/>}
    <span><strong>{label}:</strong> {text}</span></li>;
}

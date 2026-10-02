import React, {useEffect, useRef, useState} from 'react';
import {Check, ChevronRight, X} from 'lucide-react';
import {CareerFocus} from './CareerFocus';

type Row = Record<string, any>;
export const setupTitles = ['Upload your CV', 'Check your CV facts', 'Bring an existing tracker (optional)', 'Choose the jobs you want', 'Ready to find jobs'];
// Preserve the stored completion marker; old advanced steps become the finish page.
export function setupStep(value: number) { return Math.max(1, Math.min(5, Number(value) || 1)); }
export function mayContinue(step: number, profile: Row | null, cfg: Row) {
  return step === 1 ? !!profile : step === 2 ? !!profile?.confirmed : step === 4 ? !!cfg.search_focus_confirmed : true;
}
type Props = {
  step: number; profile: Row | null; cfg: Row;
  api: (path: string, method?: string, data?: any) => Promise<any>;
  reload: () => Promise<any>; upload: (file: File, kind: string) => Promise<any>;
  confirmProfile: () => Promise<any>; editProfile: () => void;
  close: () => void; back: () => void; next: () => Promise<any>;
};
export function SetupWizard({step, profile, cfg, api, reload, upload, confirmProfile, editProfile, close, back, next}: Props) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [trackerImported, setTrackerImported] = useState(false);
  const [focusDirty, setFocusDirty] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {heading.current?.closest('section')?.scrollTo(0, 0); heading.current?.focus(); setError('');}, [step]);
  async function run(task: () => Promise<any>) {
    if (busy) return;
    setBusy(true); setError('');
    try { await task(); } catch (e: any) { setError(e.message || 'That step did not finish. Please try again.'); }
    finally { setBusy(false); }
  }
  const facts: [string, string][] = [['employments', 'Experience'], ['projects', 'Projects'], ['education', 'Education'], ['certifications', 'Certifications and courses']];
  return <div className="overlay"><section className="dialog wizard">
    <div className="eyebrow">SET UP YOUR WORKSPACE · STEP {step} OF 5</div>
    <button className="close icon" aria-label="Close setup" onClick={close}><X size={20} aria-hidden/></button>
    <h2 ref={heading} tabIndex={-1}>{setupTitles[step - 1]}</h2>
    <div className="steps" aria-label={`Step ${step} of 5`}>{setupTitles.map((title, i) => <span key={title} className={i < step ? 'filled' : ''}/>)}</div>
    {step === 1 && <><p>Choose the PDF version of your CV. ASTRA reads the text on this computer; it does not search your folders or send your CV to an AI service.</p>
      <label className="secondary upload">{profile ? 'Replace CV (PDF)' : 'Choose CV (PDF)'}<input aria-label="Choose CV PDF" disabled={busy} type="file" accept=".pdf" onChange={e => {const file = e.target.files?.[0]; if (file) run(() => upload(file, 'cv'));}}/></label>
      <p className="muted-line">Use a PDF with selectable text. A photo or scanned CV may not work. You will check the extracted facts next.</p>{profile && <p role="status">CV imported. Continue to check its facts.</p>}</>}
    {step === 2 && <><p>Check what ASTRA actually extracted below. Correct anything missing or inaccurate before confirming.</p>
      <div className="setup-facts"><h3>{profile?.name || 'Name not found'}</h3><p>{profile?.summary || 'No summary found. You can add it in your profile.'}</p>
        <h3>Skills</h3><p>{profile?.skills?.map((s: Row) => s.text).join(', ') || 'No skills found. Add your skills before matching jobs.'}</p>
        {facts.map(([key, title]) => <div key={key}><h3>{title}</h3>{profile?.[key]?.length ? profile[key].map((f: Row) => <p key={f.id}>{f.text}</p>) : <p>No facts extracted for this section.</p>}</div>)}</div>
      <details><summary>See the extracted CV text</summary><pre className="source">{profile?.raw_text}</pre></details>
      <div className="actions"><button className="secondary" disabled={busy} onClick={editProfile}>Correct my profile</button><button className="primary" disabled={busy || !profile} onClick={() => run(confirmProfile)}><Check size={16} aria-hidden/>{profile?.confirmed ? 'Facts confirmed' : 'These facts are correct'}</button></div></>}
    {step === 3 && <><p>Already tracking applications in an Excel spreadsheet? You can import an XLSX tracker here. If you do not have one, skip this step. ASTRA will keep your new applications for you.</p>
      <label className="secondary upload">Choose an XLSX tracker<input aria-label="Choose optional XLSX tracker" disabled={busy} type="file" accept=".xlsx" onChange={e => {const file = e.target.files?.[0]; if (file) run(async () => {await upload(file, 'tracker'); setTrackerImported(true);});}}/></label>
      <p className="muted-line">This is optional. Nothing is imported unless you choose a file.</p>{trackerImported && <p role="status">Tracker imported.</p>}</>}
    {step === 4 && <CareerFocus api={api} cfg={cfg} onSaved={reload} onDirtyChange={setFocusDirty}/>}
    {step === 5 && <><p><strong>Rule-based matching is the recommended starting point.</strong> It works without an AI account or subscription. AI is optional, under Settings → Gmail &amp; permissions → Optional AI assistance; it is not needed to find or prepare jobs.</p>
      {cfg.provider && cfg.provider !== 'rules' && <p className="notice">You previously selected an optional AI provider. You can return to rule-based in Settings. Your saved choice has been kept.</p>}
      <ol className="setup-next"><li>Open <strong>Start scanning</strong> on the left.</li><li>Add a supported company board, or use <strong>Search elsewhere</strong> for manual job sites.</li><li>Press <strong>Start scanning now</strong>, check the preview, then <strong>Confirm and start scan</strong>.</li><li>Review a job, prepare and check your documents, then apply on the employer's website yourself.</li></ol>
      <p>Scanning starts only after your confirmation. Opening ASTRA does not start a scan or submit an application.</p></>}
    {error && <p role="alert" className="notice">{error}</p>}
    <div className="actions setup-actions"><button className="secondary" disabled={busy || step === 1} onClick={back}>Back</button><button className="primary" disabled={busy || (step === 4 && focusDirty) || !mayContinue(step, profile, cfg)} onClick={() => run(next)}>{busy ? 'Saving…' : step === 5 ? 'Open Start scanning' : step === 3 && !trackerImported ? 'Skip for now' : 'Continue'}<ChevronRight size={16} aria-hidden/></button></div>
  </section></div>;
}

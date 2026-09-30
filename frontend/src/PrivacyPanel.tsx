import {safeLink} from './safeLink';
import {privateFetch,privateBlob} from './access';
import React,{useEffect,useState} from 'react';
import {Download,ShieldCheck,Trash2} from 'lucide-react';
import {GmailConnection} from './GmailConnection';
import {ActionStatus,SaveBar,useAction,useDraft} from './ui';
type Row=Record<string,any>;
type Api=(path:string,method?:string,data?:any)=>Promise<any>;

/** `/api/privacy` once per card that needs it. */
function usePrivacyInfo(api:Api){
 const [info,setInfo]=useState<Row|null>(null),[error,setError]=useState('');
 const load=()=>api('/privacy').then(value=>{setInfo(value);setError('')}).catch(e=>setError(e.message));
 useEffect(()=>{load()},[]);
 return {info,error,load};
}
function Loading({error,retry,what}:{error:string,retry:()=>void,what:string}){
 return error?<div role="alert" className="errorbar"><span>{what} could not load. {error}</span><button className="secondary" onClick={retry}>Retry</button></div>:<p role="status" className="muted-line">Loading {what.toLowerCase()}…</p>;
}

export function SecurityCheck({api}:{api:Api}){
 const [checks,setChecks]=useState<Row|null>(null),[events,setEvents]=useState<Row[]>([]);
 const action=useAction();
 const run=()=>action.run(async()=>{const [c,e]=await Promise.all([api('/privacy/self-check'),api('/privacy/security-events')]);setChecks(c);setEvents(e.events)},'Security check finished.','Checking this installation…');
 return <section className="panel settings-card"><div className="card-head"><ShieldCheck size={20} aria-hidden/><div><h3>Privacy & security check</h3><p>Checks the local server, credential storage, runtime, data permissions and backups. It reads this computer only.</p></div></div>
  <button className="secondary" disabled={action.busy} aria-busy={action.busy} onClick={run}>{action.busy?'Checking…':'Run security check'}</button><ActionStatus status={action.status}/>
  {checks&&<><p className="check-overall">Overall: <strong>{checks.overall}</strong></p><ul className="check-list">{checks.checks.map((c:Row)=><li key={c.check}><strong>{c.check.replaceAll('_',' ')}: {c.status}</strong> — {c.detail}{c.remediation&&<> · {c.remediation}</>}</li>)}</ul></>}
  {!!events.length&&<details><summary>Recent security events ({Math.min(events.length,10)})</summary><ul className="check-list">{events.slice(-10).reverse().map((e:Row,i:number)=><li key={i}>{e.ts} · {e.event.replaceAll('_',' ').toLowerCase()}</li>)}</ul></details>}
 </section>
}

export function LocalDataCard({api}:{api:Api}){
 const {info,error,load}=usePrivacyInfo(api);const action=useAction();
 async function exportData(){const response=await privateFetch('/api/privacy/export');if(!response.ok){const data=await response.json();throw Error(data.detail||'Export failed')}const url=await privateBlob(response);const a=document.createElement('a');a.href=url;a.download='job-search-private-export.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000)}
 if(!info)return <section className="panel settings-card"><h3>Where your data lives</h3><Loading error={error} retry={load} what="Local data details"/></section>;
 return <section className="panel settings-card"><h3>Where your data lives</h3><p>Stored on this computer: <code dir="ltr">{info.storage_path}</code></p>{Object.entries(info.copy).map(([name,value])=><p key={name}>{String(value)}</p>)}
  <button className="secondary" disabled={action.busy} aria-busy={action.busy} onClick={()=>action.run(exportData,'Private export downloaded. It contains unencrypted personal information; keep it somewhere safe.','Preparing your export…')}><Download size={16} aria-hidden/>{action.busy?'Preparing export…':'Export my data'}</button><ActionStatus status={action.status}/></section>
}

const APPLICATION_KEYS=['preferred_name','legal_name','residence_country','target_countries','ui_locale','cv_language','timezone','relocation','travel','notice_period','languages','salary_amount','salary_currency','salary_period','portfolio','github','linkedin','work_modes','work_authorisation','sponsorship'];

export function ApplicationAnswers({api,refresh}:{api:Api,refresh:()=>Promise<any>}){
 const {info,error,load}=usePrivacyInfo(api);
 const card=useDraft<Row>('application-answers','Application answers',info?.application_profile||{},APPLICATION_KEYS);
 const p=card.draft;
 if(!info)return <section className="panel settings-card"><h3>Application answers</h3><Loading error={error} retry={load} what="Application answers"/></section>;
 const text=(name:string,label:string,hint='')=> <label key={name}>{label}<input dir="auto" value={p[name]||''} maxLength={1000} onChange={e=>card.set(name,e.target.value)}/>{hint&&<small>{hint}</small>}</label>;
 const choices=(name:string,label:string,options:string[])=> <label key={name}>{label}<select value={p[name]||'UNKNOWN'} onChange={e=>card.set(name,e.target.value)}>{options.map(v=><option key={v} value={v}>{v.replaceAll('_',' ')}</option>)}</select></label>;
 const save=()=>card.save(async draft=>{const result=await api('/privacy/application-profile','PUT',draft);try{localStorage.setItem('uiLocale',draft.ui_locale);localStorage.setItem('uiTimeZone',draft.timezone)}catch{/* storage unavailable */}document.documentElement.dir=/^(ar|he|fa|ur)(-|$)/i.test(draft.ui_locale)?'rtl':'ltr';await refresh();return result});
 return <section className="panel settings-card"><h3>Application answers</h3><p>Your own answers, separate from extracted CV text. Blank means unknown. They never become matching variables or automatically submitted answers.</p>
  <div className="formgrid">
   {text('preferred_name','Preferred name')}{text('legal_name','Legal name (only if needed)')}{text('residence_country','Residence country code','For example AE')}
   <label>Target employment country codes<input dir="ltr" value={(p.target_countries||[]).join(', ')} onChange={e=>card.set('target_countries',e.target.value.split(',').map(s=>s.trim().toUpperCase()).filter(Boolean))}/><small>Comma-separated, for example AE, DE</small></label>
   {text('ui_locale','Formatting locale','For example en-GB, ar-AE, de-DE. Interface text stays English.')}{text('cv_language','CV language','Separate from the formatting locale')}{text('timezone','Timezone','For example Asia/Dubai')}
   {choices('relocation','Willing to relocate',['UNKNOWN','YES','NO'])}{choices('travel','Willing to travel',['UNKNOWN','YES','NO'])}{text('notice_period','Notice period')}
   <label>Languages you explicitly provide<input dir="auto" value={(p.languages||[]).join(', ')} onChange={e=>card.set('languages',e.target.value.split(',').map(s=>s.trim()).filter(Boolean))}/></label>
   {text('salary_amount','Salary preference (your notation)')}{text('salary_currency','Salary currency code','For example AED')}{choices('salary_period','Salary period',['UNKNOWN','hour','day','week','month','year'])}
   {text('portfolio','Portfolio HTTPS link')}{text('github','GitHub HTTPS link')}{text('linkedin','LinkedIn HTTPS link')}
  </div>
  <fieldset><legend>Preferred work arrangement</legend>{['remote','hybrid','on-site'].map(mode=><label className="check" key={mode}><input type="checkbox" checked={(p.work_modes||[]).includes(mode)} onChange={e=>card.set('work_modes',e.target.checked?[...(p.work_modes||[]),mode]:(p.work_modes||[]).filter((m:string)=>m!==mode))}/>{mode}</label>)}</fieldset>
  {(p.target_countries||[]).map((country:string)=><fieldset key={country}><legend>{country}: answers apply only to this country</legend><div className="formgrid">{[['work_authorisation','Authorised to work'],['sponsorship','Require sponsorship']].map(([name,label])=><label key={name}>{label}<select value={p[name]?.[country]||'UNKNOWN'} onChange={e=>card.set(name,{...(p[name]||{}),[country]:e.target.value})}>{['UNKNOWN','YES','NO'].map(v=><option key={v}>{v}</option>)}</select></label>)}</div><p>Local CV and legal guidance has not been verified for this market. Follow the employer’s instructions; no sensitive details or photograph are added automatically.</p></fieldset>)}
  <SaveBar state={card} onSave={save} saveLabel="Save answers"/>
 </section>
}

export function CareerFacts({api,refresh}:{api:Api,refresh:()=>Promise<any>}){
 const [candidate,setCandidate]=useState<Row|null>(null),[error,setError]=useState(''),[loaded,setLoaded]=useState(false);
 const action=useAction();
 const load=()=>api('/profile').then(value=>{setCandidate(value);setError('');setLoaded(true)}).catch(e=>setError(e.message));
 useEffect(()=>{load()},[]);
 if(error||!loaded)return <section className="panel settings-card"><h3>Career facts</h3><Loading error={error} retry={load} what="Career facts"/></section>;
 if(!candidate)return <section className="panel settings-card"><h3>Career facts</h3><p className="muted-line">No master CV has been imported, so there are no extracted facts yet.</p></section>;
 return <section className="panel settings-card"><h3>Career facts and where they came from</h3><p><strong>{candidate.confirmed?'Confirmed by you.':'Extracted — needs your confirmation.'}</strong> Review each source block. A correction is recorded as provided by you and needs confirming again before documents are generated.</p>
  {['skills','employments','education','certifications','projects'].map(kind=>(candidate[kind]||[]).length>0&&<details key={kind}><summary>{kind[0].toUpperCase()+kind.slice(1)} ({candidate[kind].length})</summary>{(candidate[kind]||[]).map((fact:Row)=><form className="fact" key={fact.id} onSubmit={e=>{e.preventDefault();action.run(async()=>{await api('/profile/facts/'+kind+'/'+fact.id,'PUT',{text:fact.text});await load();await refresh()},'Fact corrected. Confirm your career facts again before generating documents.','Saving the correction…')}}><label>Source fact #{fact.id}<textarea dir="auto" value={fact.text} maxLength={20000} onChange={e=>setCandidate({...candidate,[kind]:candidate[kind].map((f:Row)=>f.id===fact.id?{...f,text:e.target.value}:f)})}/></label><small>{fact.provenance}</small><button className="secondary compact" disabled={action.busy}>Save correction</button></form>)}</details>)}
  <div className="actions spaced"><button className="primary" disabled={action.busy||candidate.confirmed} onClick={()=>action.run(async()=>{await api('/profile','PUT',{confirmed:true});await load();await refresh()},'Career facts confirmed by you.','Confirming…')}>{candidate.confirmed?'Facts confirmed':'I reviewed and confirm these facts'}</button></div>
  <ActionStatus status={action.status}/>
 </section>
}

export function AiAssistance({api,cfg,reload}:{api:Api,cfg:Row,reload:()=>Promise<any>}){
 const card=useDraft<Row>('ai-assistance','AI assistance',{provider:cfg.provider||'rules',ai_daily_limit:cfg.ai_daily_limit??0},['provider','ai_daily_limit']);
 const [key,setKey]=useState(''),[usage,setUsage]=useState<Row|null>(null);const keyAction=useAction();
 useEffect(()=>{api('/privacy/ai-usage').then(setUsage).catch(()=>{})},[card.savedAt]);
 const save=()=>card.save(async draft=>{const result=await api('/settings','PUT',{provider:draft.provider,ai_daily_limit:Number(draft.ai_daily_limit)});await reload();return result});
 const options=[['rules','Rule-based','Works offline. No key and no data leaves this computer.'],['ollama','Local Ollama','Uses a model running on this computer. Nothing is sent to a cloud service.'],['openai','OpenAI','Optional, unverified advice. Each request asks for your approval before any text leaves this computer.']];
 return <section className="panel settings-card"><h3>AI assistance</h3>
  <fieldset className="radio-cards"><legend>Where model commentary comes from</legend>{options.map(([value,label,help])=><label key={value} className={'radio-card'+(card.draft.provider===value?' selected':'')}><input type="radio" name="ai-provider" value={value} checked={card.draft.provider===value} onChange={()=>card.set('provider',value)}/><span><strong>{label}</strong><small>{help}</small></span></label>)}</fieldset>
  <label className="narrow-field">Daily OpenAI request limit<input type="number" min={0} max={100} value={card.draft.ai_daily_limit} onChange={e=>card.set('ai_daily_limit',e.target.value===''?'':Number(e.target.value))}/><small>0 turns remote requests off. Failed attempts count toward the limit.{usage?` Used today (UTC): ${usage.requests} requests.`:''}</small></label>
  <SaveBar state={card} onSave={save}/>
  <form className="key-form" onSubmit={e=>{e.preventDefault();keyAction.run(async()=>{await api('/privacy/credentials/openai','PUT',{key});setKey('')},'Key saved in your operating system’s credential store. No cloud request was made.','Saving key…')}}>
   <label>OpenAI API key<input type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)} minLength={10} maxLength={1000} required/><small>Stored only in your operating system’s credential manager, never in ASTRA’s database. Saving a key does not send anything.</small></label>
   <button className="secondary" disabled={keyAction.busy||key.length<10} aria-describedby="key-hint">{keyAction.busy?'Saving…':'Save key securely'}</button><small id="key-hint">{key.length<10?'Enter the full key (at least 10 characters) to save it.':'Ready to save.'}</small>
  </form><ActionStatus status={keyAction.status}/>
 </section>
}

/** Gmail connection controls, kept in this module by the #44 wiring check. */
export function GmailPermissions({api}:{api:Api}){
 return <GmailConnection api={api}/>;
}

export function PlatformCapabilities({api}:{api:Api}){
 const {info,error,load}=usePrivacyInfo(api);
 if(!info)return <section className="panel settings-card"><h3>What ASTRA does on each platform</h3><Loading error={error} retry={load} what="Platform capabilities"/></section>;
 return <section className="panel settings-card"><h3>What ASTRA does on each platform</h3><ul className="check-list">{info.platforms.map((p:Row)=><li key={p.platform}><strong>{p.platform}</strong>: {p.discovery.toLowerCase()}; application submission is manual. {p.source.startsWith('https:')&&<a href={safeLink(p.source)} target="_blank" rel="noreferrer">Integration reference</a>}</li>)}</ul></section>
}

export function DeleteLocalData({api,refresh}:{api:Api,refresh:()=>Promise<any>}){
 const [scope,setScope]=useState('cv'),[confirmation,setConfirmation]=useState('');const action=useAction();
 const expected:Record<string,string>={cv:'DELETE CV',history:'DELETE APPLICATION HISTORY',all:'DELETE ALL LOCAL DATA'};
 const ready=confirmation===expected[scope];
 return <section className="panel settings-card danger-zone"><div className="card-head"><Trash2 size={20} aria-hidden/><div><h3>Delete local data</h3><p>This cannot be undone. Export first if you need a copy.</p></div></div>
  <ul className="check-list"><li><strong>CV:</strong> also removes generated materials, approved answers, the application profile, notes, app tracker copies and backups.</li><li><strong>Application history:</strong> keeps the master CV and candidate profile; removes application records, documents, notes, tracker copies and backups.</li><li><strong>All local data:</strong> also removes saved jobs and sources and pauses scanning.</li></ul><p>Original files and exports outside the app remain.</p>
  <form onSubmit={e=>{e.preventDefault();if(!ready)return;action.run(async()=>{await api('/privacy/delete','POST',{scope,confirmation});setConfirmation('');await refresh()},'The selected app-managed data was deleted. Copies outside this app remain under your control.','Deleting…')}}>
   <div className="formgrid"><label>What to delete<select value={scope} onChange={e=>{setScope(e.target.value);setConfirmation('')}}><option value="cv">Delete CV and derived private material</option><option value="history">Delete application history</option><option value="all">Delete all local data</option></select></label>
   <label>Type <code>{expected[scope]}</code> to confirm<input autoComplete="off" value={confirmation} onChange={e=>setConfirmation(e.target.value)} aria-describedby="delete-hint"/></label></div>
   <button className="danger-button" disabled={action.busy||!ready} aria-describedby="delete-hint">{action.busy?'Deleting…':'Delete selected local data'}</button>
   <small id="delete-hint">{ready?'Ready. This deletes immediately and cannot be undone.':`The delete button stays unavailable until you type ${expected[scope]} exactly.`}</small>
  </form><ActionStatus status={action.status}/>
 </section>
}

/** The complete set, for any caller that still wants one panel. */
export function PrivacyPanel({api,refresh}:{api:Api,refresh:()=>Promise<any>}){
 return <div className="privacy-panel">
  <SecurityCheck api={api}/><LocalDataCard api={api}/><ApplicationAnswers api={api} refresh={refresh}/><CareerFacts api={api} refresh={refresh}/>
  <GmailPermissions api={api}/><PlatformCapabilities api={api}/><DeleteLocalData api={api} refresh={refresh}/>
 </div>
}

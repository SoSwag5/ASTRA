import React, {useEffect, useState} from 'react';
import {ArrowUpRight, Check, RefreshCw, Search} from 'lucide-react';
import {safeLink} from './safeLink';
import {ActionStatus, Disclosure, useAction} from './ui';
type Row = Record<string, any>;
type Api = (path:string, method?:string, data?:any)=>Promise<any>;
export function SourceDirectory({api,compact=false}:{api:Api;compact?:boolean}) {
  const [data,setData]=useState<Row|null>(null),[feeds,setFeeds]=useState<Row[]>([]),[error,setError]=useState('');
  const [query,setQuery]=useState(''),[group,setGroup]=useState('All sources'),[limit,setLimit]=useState(20);
  const action=useAction();
  const [name,setName]=useState(''),[url,setUrl]=useState('');
  async function load() {
    try {const [manual,overview]=await Promise.all([api('/campaign/portals'),api('/search/overview')]);setData(manual);setFeeds(overview.sources);setError('');}
    catch(e:any){setError(e.message || 'The source directory could not load. Try again.');}
  }
  useEffect(()=>{load();},[]);
  if(!data)return <section className="panel spaced source-directory"><h2>Included sources</h2>{error?<p role="alert">{error}</p>:<p role="status">Loading included sources…</p>}<button className="secondary" onClick={load}>Retry</button></section>;
  const rows=compact?data.daily:[...feeds,...data.sources];
  const groups=['All sources',...Array.from(new Set<string>(rows.map((r:Row)=>r.details?.group || 'Your added sources')))];
  const filtered=rows.filter((r:Row)=>(group==='All sources'||(r.details?.group||'Your added sources')===group)&&(`${r.name} ${r.details?.group||''}`).toLowerCase().includes(query.toLowerCase()));
  const checked=rows.filter((r:Row)=>['REACHABLE_PAGE','PUBLIC_FEED_OK'].includes(r.details?.route_status)).length;
  return <section className="panel spaced source-directory">
    <div className="sectiontitle"><div><h2>{compact?'Today’s manual search pack':'Included sources & websites'}</h2>
      <p>{compact?'A small selection for today. Browse the complete directory in Today → Search elsewhere.':`${rows.length} destinations included or added · ${checked} successful route/feed checks recorded.`}</p></div>
      <button className="secondary compact" onClick={load}><RefreshCw size={16} aria-hidden/>Refresh directory</button></div>
    <p>ASTRA scans supported public feeds after you confirm. For other sites, open the website, find a job and use <strong>Add job</strong> to bring it into ASTRA. You submit applications yourself.</p>
    {!compact&&<><div className="directory-controls"><label><Search size={15} aria-hidden/> Search sources<input value={query} placeholder="Government, hospital or company" onChange={e=>{setQuery(e.target.value);setLimit(20);}}/></label>
      <label>Source group<select value={group} onChange={e=>{setGroup(e.target.value);setLimit(20);}}>{groups.map(g=><option key={g}>{g}</option>)}</select></label></div>
      <p className="muted-line">A successful check means the careers page or feed responded on the recorded date. It does not guarantee an open vacancy or a suitable match. Sites requiring a browser check are labelled below.</p></>}
    {!compact&&<Disclosure summary="Add another website"><p>Paste an official careers link. This adds a manual link; it does not scrape the website. For a supported automatic board, use Start scanning → Your sources to scan.</p><form className="directory-controls" onSubmit={e=>{e.preventDefault();action.run(async()=>{await api('/campaign/portals','POST',{name,url});setName('');setUrl('');await load();},'Website saved. It is a user-added link, not independently verified.');}}><label>Website name<input required maxLength={200} value={name} onChange={e=>setName(e.target.value)}/></label><label>Careers website URL<input required type="url" value={url} onChange={e=>setUrl(e.target.value)}/></label><button className="primary" disabled={action.busy}>{action.busy?'Adding…':'Add website'}</button></form></Disclosure>}<ActionStatus status={action.status}/>{error&&<p role="alert">{error}</p>}
    <div className="portal-list">{filtered.slice(0,compact?8:limit).map((source:Row)=>{
      const detail=source.details||{},feed=source.adapter!=='manual',good=['REACHABLE_PAGE','PUBLIC_FEED_OK'].includes(detail.route_status);
      return <div className="portal-row" key={source.id}><div><strong>{source.name}</strong>
        <small className="source-mode">{feed?`Scan in ASTRA · ${source.enabled?'Ready':'Paused'}`:'Open website · manual search'}</small>
        <small>{detail.group||'Your added source'} · {detail.route_checked_at?`Route checked ${detail.route_checked_at.slice(0,10)}`:'User-added; not verified'}</small>
        <small>{good?'Destination responded; review available jobs.':detail.route_status==='BROWSER_CHECK_REQUIRED'?'Browser check required; automated route check was inconclusive.':'No independent route check recorded.'}</small>
      </div><div className="actions"><a className="secondary compact" href={safeLink(source.url)} target="_blank" rel="noopener noreferrer" aria-label={`Open ${source.name} website`}>Open website<ArrowUpRight size={15} aria-hidden/></a>
        {!feed&&<button className="secondary compact" disabled={action.busy} onClick={()=>action.run(async()=>{await api(`/campaign/portals/${source.id}/checked`,'POST',{});await load();},`${source.name} marked checked. This records your review; it does not verify vacancies.`)}><Check size={15} aria-hidden/>Mark checked</button>}
      </div></div>;
    })}</div>
    {!filtered.length&&<p>No sources match. Try another name or choose All sources.</p>}
    {!compact&&filtered.length>limit&&<button className="secondary" onClick={()=>setLimit(n=>n+20)}>Show {Math.min(20,filtered.length-limit)} more sources</button>}
  </section>;
}

import React,{useEffect,useState} from 'react';
type Row=Record<string,any>;
type Api=(path:string,method?:string,data?:any)=>Promise<any>;
export function CareerFocus({api,cfg,onSaved,onDirtyChange}:{api:Api,cfg:Row,onSaved:()=>Promise<any>;onDirtyChange?:(dirty:boolean)=>void}){
 const [tracks,setTracks]=useState<Row[]>([]),[suggestions,setSuggestions]=useState<Row[]>([]),[selected,setSelected]=useState<string[]>(cfg.career_tracks||[]),[custom,setCustom]=useState<string>((cfg.custom_target_roles||[]).join('\n')),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[loaded,setLoaded]=useState(false);
 useEffect(()=>{let live=true;Promise.all([api('/career-tracks'),api('/profile/career-suggestions').catch(()=>[])]).then(([t,s])=>{if(live){setTracks(t);setSuggestions(s);setLoaded(true)}}).catch(()=>{if(live){setMessage('Career choices could not load. Close setup and retry, or open Settings.');setLoaded(true)}});return()=>{live=false}},[]);
 const evidence=(id:string)=>suggestions.find(s=>s.id===id);
 const toggle=(id:string)=>setSelected(selected.includes(id)?selected.filter(x=>x!==id):[...selected,id]);
 useEffect(()=>{const roles=custom.split('\n').map(x=>x.trim()).filter(Boolean);onDirtyChange?.(selected.join('\n')!==(cfg.career_tracks||[]).join('\n')||roles.join('\n')!==(cfg.custom_target_roles||[]).join('\n'))},[selected,custom,cfg.career_tracks,cfg.custom_target_roles,onDirtyChange]);
 async function save(){
  setBusy(true);setMessage('');
  try{await api('/settings/career-focus','POST',{career_tracks:selected,custom_target_roles:custom.split('\n').map((x:string)=>x.trim()).filter(Boolean)});setMessage('Search focus saved.');await onSaved()}
  catch(e:any){setMessage(e.message)}
  finally{setBusy(false)}
 }
 if(!loaded)return <p>Loading career tracks…</p>;
 return <div className="career-focus">
  <p>Choose jobs you actually want. CV words below are suggestions, not selected careers or proof that you qualify. Nothing is chosen automatically.</p>
  <label>Custom target jobs (one title per line)<textarea value={custom} onChange={e=>setCustom(e.target.value)} placeholder={'Financial Analyst\nBusiness Analyst\nPolicy Research Assistant'}/></label>
  <p className="muted-line">Studied business, finance, international relations or another field? Enter your job titles above and leave the technical boxes below empty. You can use custom roles on their own.</p>
  <div className="formgrid setup-tracks">{tracks.map(t=>{const sig=evidence(t.id);return <div key={t.id} className="trackoption"><label className="check"><input type="checkbox" checked={selected.includes(t.id)} onChange={()=>toggle(t.id)}/><span><strong>{t.label}</strong><small>{t.description}</small></span></label>{sig&&sig.signal_count>0&&<details><summary>{sig.signal_count} CV words found</summary><div className="tags">{Array.from(new Set<string>(sig.evidence)).map(w=><span key={w} className="tag">{w}</span>)}</div></details>}</div>})}</div>
  {selected.length>0&&<button className="secondary" onClick={()=>setSelected([])}>Clear technical choices</button>}
  <button className="primary" disabled={busy} onClick={save}>Save search focus</button>
  {cfg.search_focus_confirmed&&<p className="muted-line">Saved focus: {[...(cfg.custom_target_roles||[]),...(cfg.career_tracks||[]).map((id:string)=>tracks.find(t=>t.id===id)?.label||id)].join(' · ')}</p>}
  <p role="status">{message}</p>
 </div>;
}

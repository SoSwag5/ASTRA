import React,{useEffect,useState} from 'react';
type Row=Record<string,any>;
type Api=(path:string,method?:string,data?:any)=>Promise<any>;
export function CareerFocus({api,cfg,onSaved}:{api:Api,cfg:Row,onSaved:()=>Promise<any>}){
 const [tracks,setTracks]=useState<Row[]>([]),[suggestions,setSuggestions]=useState<Row[]>([]),[selected,setSelected]=useState<string[]>(cfg.career_tracks||[]),[custom,setCustom]=useState((cfg.custom_target_roles||[]).join('\n')),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[loaded,setLoaded]=useState(false);
 useEffect(()=>{Promise.all([api('/career-tracks'),api('/profile/career-suggestions').catch(()=>[])]).then(([t,s])=>{setTracks(t);setSuggestions(s);if(!cfg.search_focus_confirmed&&!(cfg.career_tracks||[]).length){const strong=s.filter((x:Row)=>x.signal_count>=3).map((x:Row)=>x.id);if(strong.length)setSelected(strong)}setLoaded(true)})},[]);
 const evidence=(id:string)=>suggestions.find(s=>s.id===id);
 const toggle=(id:string)=>setSelected(selected.includes(id)?selected.filter(x=>x!==id):[...selected,id]);
 async function save(){
  setBusy(true);setMessage('');
  try{await api('/settings/career-focus','POST',{career_tracks:selected,custom_target_roles:custom.split('\n').map((x:string)=>x.trim()).filter(Boolean)});setMessage('Search focus saved.');await onSaved()}
  catch(e:any){setMessage(e.message)}
  finally{setBusy(false)}
 }
 if(!loaded)return <p>Loading career tracks…</p>;
 return <div className="career-focus">
  <p>Choose the fields you want this workspace to search for. Selections shape which roles count as a match, which manual portal searches are suggested, and which skills are checked against your CV. You can change this anytime.</p>
  <div className="formgrid">{tracks.map(t=>{const sig=evidence(t.id);return <label key={t.id} className="check trackoption"><input type="checkbox" checked={selected.includes(t.id)} onChange={()=>toggle(t.id)}/><span><strong>{t.label}</strong>{sig&&sig.signal_count>0&&<em className="pill">{sig.signal_count} CV signals</em>}<small>{t.description}</small>{sig&&sig.evidence.length>0&&<div className="tags">{sig.evidence.map((w:string)=><span key={w} className="tag">{w}</span>)}</div>}</span></label>})}</div>
  <label>Additional target role titles (one per line)<textarea value={custom} onChange={e=>setCustom(e.target.value)} placeholder={'e.g. Graduate Trainee — Technology'}/></label>
  <button className="primary" disabled={busy} onClick={save}>Save search focus</button>
  <p role="status">{message}</p>
 </div>;
}

import React,{useEffect,useState} from 'react';
import {LoaderCircle,RotateCcw} from 'lucide-react';
import {Disclosure,OutcomeRegion} from './ui';
import {focusSummary,isFocusDirty,lines,writeThenRefresh,type Outcome} from './setupModel';
type Row=Record<string,any>;
type Api=(path:string,method?:string,data?:any)=>Promise<any>;
/**
 * Setup step 4. Choices are local until saved; unsaved choices are named and
 * block Continue with a reason. "Saved" is shown only after the server
 * accepted the focus and the workspace reloaded it, and stays visible when
 * someone returns to this step.
 */
export function CareerFocus({api,cfg,onSaved,onDirtyChange,onPendingChange}:{api:Api,cfg:Row,onSaved:()=>Promise<any>;onDirtyChange?:(dirty:boolean)=>void;onPendingChange?:(pending:boolean,busy:boolean)=>void}){
 const [tracks,setTracks]=useState<Row[]>([]),[suggestions,setSuggestions]=useState<Row[]>([]),[selected,setSelected]=useState<string[]>(cfg.career_tracks||[]),[custom,setCustom]=useState<string>((cfg.custom_target_roles||[]).join('\n')),[busy,setBusy]=useState(false),[outcome,setOutcome]=useState<Outcome|null>(null),[loaded,setLoaded]=useState(false),[loadError,setLoadError]=useState(false),[unconfirmed,setUnconfirmed]=useState<Row|null>(null);
 const load=()=>{let live=true;setLoadError(false);Promise.all([api('/career-tracks'),api('/profile/career-suggestions').catch(()=>[])]).then(([t,s])=>{if(live){setTracks(t);setSuggestions(s);setLoaded(true)}}).catch(()=>{if(live){setLoadError(true);setLoaded(true)}});return()=>{live=false}};
 useEffect(load,[]);
 const evidence=(id:string)=>suggestions.find(s=>s.id===id);
 const toggle=(id:string)=>setSelected(selected.includes(id)?selected.filter(x=>x!==id):[...selected,id]);
 // Saved but not yet reloaded: compare with what the server returned, so the
 // next action is a refresh rather than a second write.
 const base=unconfirmed||cfg;
 const dirty=isFocusDirty(selected,custom,base);
 useEffect(()=>{onDirtyChange?.(dirty)},[dirty,onDirtyChange]);
 useEffect(()=>{onPendingChange?.(busy||!!unconfirmed,busy)},[busy,unconfirmed,onPendingChange]);
 const undo=()=>{setSelected(base.career_tracks||[]);setCustom((base.custom_target_roles||[]).join('\n'));setOutcome(null)};
 async function save(){
  if(busy)return;
  if(!selected.length&&!lines(custom).length){setOutcome({tone:'bad',title:'Choose at least one job first.',text:'Type a job title or tick a career track, then save.'});return}
  setBusy(true);setOutcome(null);
  const {result,refreshed,outcome:next}=await writeThenRefresh<Row>(()=>api('/settings/career-focus','POST',{career_tracks:selected,custom_target_roles:lines(custom)}),onSaved,{
   failed:'Your search focus was not saved.',unconfirmed:'Your search focus was saved, but setup could not refresh to confirm it.',
   saved:saved=>({tone:'good',title:'Search focus saved.',text:`ASTRA will look for: ${focusSummary(saved,tracks)}. Continue when you are ready.`})});
  // Keep exactly what the server stored, so a normalized title is not "unsaved".
  if(result){setSelected(result.career_tracks||[]);setCustom((result.custom_target_roles||[]).join('\n'))}
  setUnconfirmed(result&&!refreshed?result:null);setOutcome(next);setBusy(false);
 }
 async function refresh(){
  if(busy)return;
  setBusy(true);
  try{await onSaved();setUnconfirmed(null);setOutcome({tone:'good',title:'Search focus saved.',text:'Setup refreshed. Continue when you are ready.'})}
  catch(e:any){setOutcome({tone:'warn',title:'Setup still could not refresh.',text:(e?.message||'')+' Your saved focus is kept. Try Refresh again.'})}
  finally{setBusy(false)}
 }
 if(!loaded)return <p className="muted-line" role="status">Loading career choices…</p>;
 const saved=unconfirmed||cfg.search_focus_confirmed?focusSummary(base,tracks):'';
 // A failed save stays on screen; otherwise unsaved choices outrank an older success.
 const shown:Outcome|null=outcome?.tone==='bad'||outcome?.tone==='warn'?outcome
  :dirty?{tone:'warn',title:'You have unsaved choices.',text:saved?`Save to replace your saved focus (${saved}), or undo your changes.`:'Save your search focus to keep these choices and continue.'}
  :outcome||(saved?{tone:'good',title:'Search focus saved.',text:`ASTRA will look for: ${saved}.`}:null);
 return <div className="career-focus">
  <p>Choose jobs you actually want. CV words below are suggestions, not selected careers or proof that you qualify. Nothing is chosen automatically.</p>
  {loadError&&<div className="errorbar" role="alert"><span>The built-in career tracks could not load. You can still type job titles below.</span><button className="secondary" onClick={()=>{load()}}>Retry</button></div>}
  <label className="focus-custom">Custom target jobs (one title per line)<textarea disabled={busy} value={custom} onChange={e=>setCustom(e.target.value)} placeholder={'Financial Analyst\nBusiness Analyst\nPolicy Research Assistant'}/>
   <small>Studied business, finance, international relations or another field? Enter your job titles here and leave the technical tracks below empty. Custom titles work on their own.</small></label>
  {tracks.length>0&&<fieldset className="track-fieldset"><legend>Technical career tracks (optional)</legend>
   <div className="track-cards">{tracks.map(t=>{const sig=evidence(t.id),on=selected.includes(t.id);return <div key={t.id} className={'trackoption'+(on?' selected':'')}>
    <label className="check"><input disabled={busy} type="checkbox" checked={on} onChange={()=>toggle(t.id)}/><span><strong>{t.label}</strong><small>{t.description}</small></span></label>
    {sig&&sig.signal_count>0&&<Disclosure summary={`${sig.signal_count} CV words found`} className="track-evidence"><div className="tags">{Array.from(new Set<string>(sig.evidence)).map(w=><span key={w} className="tag">{w}</span>)}</div></Disclosure>}
   </div>})}</div>
   {selected.length>0&&<button type="button" disabled={busy} className="secondary compact" onClick={()=>setSelected([])}>Clear technical choices</button>}
  </fieldset>}
  <div className="focus-save">
   <button className="primary" disabled={busy||(!dirty&&!!cfg.search_focus_confirmed&&!unconfirmed)} aria-busy={busy} onClick={unconfirmed&&!dirty?refresh:save}>{busy?<><LoaderCircle size={16} className="spin" aria-hidden/>Saving…</>:unconfirmed&&!dirty?'Refresh':'Save search focus'}</button>
   {dirty&&<button type="button" className="secondary" disabled={busy} onClick={undo}><RotateCcw size={16} aria-hidden/>Undo changes</button>}
  </div>
  <OutcomeRegion outcome={shown}/>
 </div>;
}

import React,{useEffect,useState} from 'react';
import {flushSync} from 'react-dom';

let token='';
let active=false;
let generation=0;
let terminated:()=>void=()=>{};
const requests=new Set<AbortController>();
const urls=new Set<string>();
let idleTimer:ReturnType<typeof setTimeout>|undefined;
let maximumTimer:ReturnType<typeof setTimeout>|undefined;
// Remove the previous release's persistent static credential on first load.
sessionStorage.removeItem('token');

export function endWorkspace(){
 const previous=token;
 token='';active=false;generation++;
 clearTimeout(idleTimer);clearTimeout(maximumTimer);
 sessionStorage.removeItem('token');
 requests.forEach(c=>c.abort());requests.clear();
 urls.forEach(url=>URL.revokeObjectURL(url));urls.clear();
 flushSync(()=>terminated());
 if(previous)void fetch('/api/access/lock',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+previous},body:'{}',keepalive:true}).catch(()=>{});
}
window.addEventListener('pagehide',endWorkspace);
window.addEventListener('offline',endWorkspace);
window.addEventListener('pageshow',e=>{if(e.persisted)endWorkspace()});
function resetIdle(){if(active&&token){clearTimeout(idleTimer);idleTimer=setTimeout(endWorkspace,15*60*1000)}}
window.addEventListener('pointerdown',resetIdle);
window.addEventListener('keydown',resetIdle);

export async function privateFetch(path:string,options:RequestInit={}){
 if(!active)throw Error('Open your workspace to continue.');
 const current=generation,controller=new AbortController();requests.add(controller);
 try{
  const headers=new Headers(options.headers);if(token)headers.set('Authorization','Bearer '+token);
  const response=await fetch(path,{...options,headers,signal:controller.signal,cache:'no-store'});
  if(current!==generation)throw Error('Workspace closed.');
  if(response.status===401){endWorkspace();throw Error('Your session ended. Unlock the workspace again.');}
  return response;
 }catch(error){if(current===generation)endWorkspace();throw error;}
 finally{requests.delete(controller);}
}
export async function privateBlob(response:Response){
 const current=generation,blob=await response.blob();
 if(!active||current!==generation)throw Error('Workspace closed.');
 const url=URL.createObjectURL(blob);urls.add(url);return url;
}

export function AccessBoundary({children}:{children:React.ReactNode}){
 const [open,setOpen]=useState(false),[required,setRequired]=useState<boolean|null>(null),[key,setKey]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
  const started=generation;
  terminated=()=>{setOpen(false);setKey('');setError('Workspace closed. Unsaved browser edits were cleared.');};
  fetch('/api/access',{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error('Workspace unavailable.');return r.json()}).then(info=>{setRequired(info.required);if(!info.required&&generation===started){active=true;setOpen(true)}}).catch(()=>setError('Start ASTRA, then try opening the workspace.'));
  return()=>{terminated=()=>{}};
 },[]);
 async function unlock(e:React.FormEvent){
  e.preventDefault();setBusy(true);setError('');
  try{
   const status=await fetch('/api/access',{cache:'no-store'});if(!status.ok)throw Error('Workspace unavailable.');
   const info=await status.json();setRequired(info.required);
   if(info.required){
    if(!key)throw Error('Enter the access key configured for this installation.');
    const r=await fetch('/api/access',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key}),cache:'no-store'});
    const result=await r.json();if(!r.ok)throw Error(result.detail||'Could not unlock the workspace.');token=result.token;
   }
   setKey('');active=true;resetIdle();if(token)maximumTimer=setTimeout(endWorkspace,8*60*60*1000);setOpen(true);
  }catch(e:any){setKey('');setError(e.message||'Could not reach ASTRA.');}finally{setBusy(false)}
 }
 if(open)return <>{children}</>;
 return <main className="panel" style={{maxWidth:520,margin:'10vh auto'}}><h1>Open ASTRA</h1><p>Your records stay in this installation. Opening the workspace loads them into this tab.</p><form onSubmit={unlock}>{required&&<label>Access key<input type="password" autoComplete="off" value={key} maxLength={1000} onChange={e=>setKey(e.target.value)} required/></label>}<button className="primary" disabled={busy}>{busy?'Opening…':'Open workspace'}</button></form>{error&&<p role="alert">{error}</p>}</main>;
}

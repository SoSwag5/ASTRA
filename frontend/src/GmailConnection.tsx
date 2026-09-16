import {safeLink} from './safeLink';
import React,{useEffect,useRef,useState} from 'react';
/**
 * Minimal Gmail connection controls (issue #44): show connected/disconnected,
 * start the primary account's authorization, show the actual authorized
 * address Google reported, cancel a pending attempt, disconnect, and show the
 * secondary slot as not yet enabled.
 *
 * Security rules this component follows:
 * - It never renders a token, an authorization code, a PKCE value, a `state`
 *   value, a raw Google response, a callback URL, or a stack trace. The only
 *   strings shown come from `MESSAGES` below, keyed by the backend's bounded
 *   codes, plus the authorized address the backend reports for confirmation.
 * - It never writes OAuth state to localStorage, sessionStorage or IndexedDB.
 *   The pending authorization URL lives in component state only, so closing
 *   the tab or reloading clears every transient frontend OAuth value.
 * - The consent URL is opened through `safeLink` with `noopener,noreferrer`;
 *   it is held only until it is opened or the attempt ends.
 * - "Connected" is rendered only when the backend says CONNECTED, which it
 *   does only after both the credential write and the metadata write
 *   succeeded.
 */
type Row=Record<string,any>;
type Api=(path:string,method?:string,data?:any)=>Promise<any>;

/** Bounded backend codes mapped to text. An unknown code falls back to a
 *  generic line rather than being rendered raw. */
const MESSAGES:Record<string,string>={
 AWAITING_GOOGLE:'Waiting for you to approve access in your browser.',
 CONNECTED:'Connected.',
 CANCELLED:'The connection attempt was cancelled.',
 EXPIRED:'The connection attempt expired. Start again.',
 SUPERSEDED:'A newer connection attempt replaced this one.',
 INVALIDATED:'The connection attempt is no longer valid.',
 INVALIDATED_BY_DISCONNECT:'The connection attempt ended because the account was disconnected.',
 CONNECTION_FAILED:'The connection could not be completed. Nothing was stored. Try again.',
 CALLBACK_INVALID:'The response from Google was not accepted. Start again.',
 CALLBACK_STATE_MISSING:'The response from Google was not accepted. Start again.',
 CALLBACK_STATE_MISMATCH:'The response from Google did not match this attempt and was rejected.',
 CALLBACK_MISSING_CODE:'The response from Google was incomplete. Start again.',
 CALLBACK_DUPLICATE_PARAMETER:'The response from Google was malformed and was rejected.',
 CALLBACK_UNEXPECTED_PARAMETER:'The response from Google was malformed and was rejected.',
 CALLBACK_PROVIDER_ERROR:'Google reported that access was not granted.',
 CALLBACK_REPLAYED:'That response was already used and cannot be reused.',
 ATTEMPT_EXPIRED:'The connection attempt expired. Start again.',
 TOKEN_EXCHANGE_FAILED:'Google did not complete the token exchange. Start again.',
 TOKEN_RESPONSE_INVALID:'Google returned an unexpected response. Nothing was stored.',
 ACCESS_TOKEN_MISSING:'Google returned an unexpected response. Nothing was stored.',
 REFRESH_TOKEN_NOT_RETURNED:'Google did not issue a durable token, so nothing was stored. Remove ASTRA from your Google account permissions, then connect again and approve access.',
 SCOPE_MISSING_REQUIRED:'Gmail read-only access was not granted, so nothing was stored. Connect again and approve the read-only permission.',
 SCOPE_BROADER_THAN_REQUESTED:'Google granted more access than ASTRA asked for, so nothing was stored. Remove ASTRA from your Google account permissions, then connect again.',
 IDENTITY_LOOKUP_FAILED:'ASTRA could not confirm which account was authorized, so nothing was stored.',
 IDENTITY_RESPONSE_INVALID:'ASTRA could not confirm which account was authorized, so nothing was stored.',
 IDENTITY_ALREADY_CONNECTED:'That Gmail account is already connected to another slot. Nothing was stored.',
 CREDENTIAL_STORE_UNAVAILABLE:'A native operating-system credential store is unavailable. ASTRA never stores a Gmail token in plaintext.',
 CREDENTIAL_STORE_FAILED:'The token could not be saved to the credential store. The account was not connected.',
 PERSISTENCE_FAILED:'The connection could not be saved, so the stored token was removed again. Nothing was connected.',
 CLIENT_NOT_CONFIGURED:'Set up a Gmail OAuth client for your own Google Cloud project first.',
 CLIENT_ID_INVALID:'The configured Gmail OAuth client ID is not valid. Re-copy it from your Google Cloud project.',
 SECONDARY_NOT_ENABLED:'The second Gmail account is not enabled yet.',
 LISTENER_UNAVAILABLE:'A local callback port could not be opened. Close other applications and try again.',
};
const describe=(code?:string)=>(code&&MESSAGES[code])||'';

export function GmailConnection({api}:{api:Api}){
 const [info,setInfo]=useState<Row|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 // Pending-attempt values are component state only -- never persisted to any
 // browser storage, so a reload or a closed tab discards them.
 const [pendingUrl,setPendingUrl]=useState('');
 const timer=useRef<number|undefined>(undefined);
 const load=async()=>setInfo(await api('/gmail/status'));
 useEffect(()=>{load().catch(e=>setError(e.message));return ()=>{if(timer.current)window.clearInterval(timer.current)}},[]);
 const primary=info?.accounts?.PRIMARY,secondary=info?.accounts?.SECONDARY;
 const attempt=primary?.pending_attempt;
 // Poll only while an attempt is actually pending.
 useEffect(()=>{
  if(timer.current){window.clearInterval(timer.current);timer.current=undefined}
  if(attempt?.status!=='PENDING')return;
  timer.current=window.setInterval(()=>{load().catch(()=>{})},3000);
  return ()=>{if(timer.current)window.clearInterval(timer.current)};
 },[attempt?.status,attempt?.attempt_id]);
 useEffect(()=>{if(attempt&&attempt.status!=='PENDING')setPendingUrl('')},[attempt?.status]);

 const run=async(fn:()=>Promise<any>)=>{
  if(busy)return;setBusy(true);setError('');
  try{await fn();await load()}
  catch(e:any){setError(e.message)}
  finally{setBusy(false)}
 };
 const connect=()=>run(async()=>{
  const started=await api('/gmail/accounts/primary/authorize','POST',{});
  const url=safeLink(started.authorization_url);
  if(!url){setError('The authorization link was rejected by the local link check.');return}
  setPendingUrl(url);
  window.open(url,'_blank','noopener,noreferrer');
 });
 const cancel=()=>run(async()=>{setPendingUrl('');await api('/gmail/accounts/primary/authorize/cancel','POST',{})});
 const disconnect=()=>run(async()=>{setPendingUrl('');await api('/gmail/accounts/primary/disconnect','POST',{})});

 if(!info)return <section className="panel spaced"><h2>Gmail connection</h2>{error?<p role="alert" className="errorbar">{error}</p>:<p role="status">Loading Gmail connection status…</p>}</section>;
 const configured=info.configuration?.state==='CONFIGURED';
 const storeReady=info.credential_store?.state==='OS_SECURE_STORE';
 const connected=primary?.status==='CONNECTED';
 return <section className="panel spaced">
  <h2>Gmail connection</h2>
  <p>ASTRA asks Google for <strong>read-only</strong> Gmail access ({info.requested_scopes?.join(' ')}) so it can later detect application confirmations. It never sends, deletes, archives or changes email. Your connection token is kept in your operating system’s credential store, never in the ASTRA database, an export, a backup or a log.</p>
  {error&&<p role="alert" className="errorbar">{error}</p>}
  {!configured&&<p className="notice">{describe(info.configuration?.detail_code)||'A Gmail OAuth client is not configured yet.'} Set <code dir="ltr">{info.configuration?.environment_variable}</code> to the client ID of a Desktop App OAuth client in your own Google Cloud project, then restart ASTRA. See the Gmail OAuth setup guide in the documentation.</p>}
  {configured&&!storeReady&&<p className="notice">{describe(info.credential_store?.detail_code)}</p>}
  <h3>Primary account</h3>
  <p role="status">
   {connected?<>Connected as <strong dir="ltr">{primary.authorized_email}</strong> — the address Google confirmed was authorized. Read-only access granted {primary.connected_at?'on '+primary.connected_at.slice(0,10):''}.</>
    :primary?.status==='DISCONNECTED_INCONSISTENT'?<>Not connected. A stored connection was found without its credential, so ASTRA treats this account as disconnected. Connect again.</>
    :<>Not connected.</>}
  </p>
  {attempt&&<p role="status" className="notice">{describe(attempt.result_code)||'Connection attempt in progress.'}{attempt.status==='PENDING'&&attempt.expires_in_seconds>0&&<> This attempt expires in about {Math.ceil(attempt.expires_in_seconds/60)} minute(s).</>}</p>}
  {pendingUrl&&attempt?.status==='PENDING'&&<p><a href={pendingUrl} target="_blank" rel="noopener noreferrer">Continue to Google ↗</a> — if the consent page did not open automatically.</p>}
  <div className="actions spaced">
   {!connected&&<button className="secondary" disabled={busy||!configured||!storeReady||attempt?.status==='PENDING'} onClick={connect}>Connect Gmail (read-only)</button>}
   {attempt?.status==='PENDING'&&<button className="secondary" disabled={busy} onClick={cancel}>Cancel connection attempt</button>}
   {connected&&<button className="secondary" disabled={busy} onClick={disconnect}>Disconnect Gmail</button>}
  </div>
  {connected&&<p>Disconnecting deletes ASTRA’s local token and this account’s Gmail sync state, and asks Google to revoke the access. Your applications, their history and anything already saved are kept.</p>}
  {primary?.last_remote_revocation&&<p className="notice">Last disconnect: local access removed; Google revocation reported <strong>{primary.last_remote_revocation.replaceAll('_',' ').toLowerCase()}</strong>.</p>}
  <h3>Second account</h3>
  <p role="status">Not enabled yet. ASTRA is built for two Gmail accounts, and the second one is switched on only after the primary account is validated end to end.{secondary?.gate_code&&<> ({secondary.gate_code.replaceAll('_',' ').toLowerCase()})</>}</p>
 </section>
}

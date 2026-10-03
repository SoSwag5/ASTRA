const assert = require('node:assert/strict');
(async()=>{
 const {createServer}=await import('vite');
 const server=await createServer({configFile:false,optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true},appType:'custom',logLevel:'error'});
 try {
  const S=await server.ssrLoadModule('/src/setupModel.ts');
  let writes=0,refreshes=0;
  const words={failed:'Save failed',saved:()=>({tone:'good',title:'Saved'}),unconfirmed:'Saved; refresh needed'};
  let result=await S.writeThenRefresh(async()=>{writes++;throw Error('Fictional failure')},async()=>refreshes++,words);
  assert.equal(result.outcome.tone,'bad');assert.equal(refreshes,0);assert.equal(result.written,false);
  result=await S.writeThenRefresh(async()=>{writes++;return 7},async()=>{refreshes++;throw Error('Fictional offline')},words);
  assert.equal(result.outcome.tone,'warn');assert.equal(result.written,true);assert.equal(result.refreshed,false);assert.equal(writes,2);
  result=await S.writeThenRefresh(async()=>7,async()=>{},words);assert.equal(result.outcome.title,'Saved');
  assert.equal(S.isFocusDirty([], ' Business Analyst\n', {career_tracks:[],custom_target_roles:['Business Analyst']}),false);
  assert.equal(S.isFocusDirty([], 'Policy Analyst', {custom_target_roles:['Business Analyst']}),true);
  assert.match(S.continueHint(4,null,{search_focus_confirmed:true},true),/unsaved/);
  assert.equal(S.continueHint(4,null,{search_focus_confirmed:true},false),'');
  const M=await server.ssrLoadModule('/src/motion.ts');
  const gate=M.latestGate();const first=gate.begin();const last=gate.begin();assert.equal(gate.isCurrent(first),false);assert.equal(gate.isCurrent(last),true);
  assert.equal(M.motionMode('system',true),'reduced-by-system');assert.equal(M.motionMode('reduced',false),'reduced-by-astra');assert.equal(M.motionMode('system',false),'full');assert.equal(M.motionMode('full',true),'full');
  const D=await server.ssrLoadModule('/src/disclosure.ts');
  global.document={activeElement:null};
  let shown=false,height=0;const animations=[];
  const body={style:{},inert:false,scrollHeight:100,contains:()=>false,getBoundingClientRect:()=>({height}),animate:(_,options)=>{const a={cancelled:false,cancel(){this.cancelled=true;},options,onfinish:null};animations.push(a);return a;}};
  const controller=D.createDisclosure({shown:()=>shown,show:value=>{shown=value;},body},{reduced:()=>false});
  controller.toggle();assert.equal(shown,true);assert.equal(controller.open,true);
  height=40;controller.toggle();assert.equal(controller.open,false);assert.equal(body.inert,true);assert.equal(animations[0].cancelled,true);
  animations[0].onfinish();assert.equal(shown,true);assert.equal(controller.animating,true);
  height=20;controller.toggle();assert.equal(controller.open,true);animations[2].onfinish();assert.equal(body.inert,false);assert.equal(shown,true);
  const quiet=D.createDisclosure({shown:()=>shown,show:value=>{shown=value;},body},{reduced:()=>true});quiet.toggle(false);assert.equal(shown,false);assert.equal(animations.length,3);
  delete global.document;
  // Source-level guards (not browser runs): pending/busy wizard state blocks duplicate writes and stale advances.
  const fs=require('node:fs');const wizard=fs.readFileSync('src/SetupWizard.tsx','utf8'),main=fs.readFileSync('src/main.tsx','utf8'),focus=fs.readFileSync('src/CareerFocus.tsx','utf8');
  assert.match(wizard,/if \(busy \|\| unconfirmed\[at\]\) return;/);
  assert.match(wizard,/const hint = pending \?/);assert.match(wizard,/disabled=\{!!busy \|\| !!hint\}/);
  assert.match(wizard,/className="close icon" disabled=\{working\}/);
  assert.match(main,/panel\.getAttribute\('aria-busy'\)==='true'\)return/);
  assert.match(main,/updateCfg\(\{wizard_step:next\}\)/);
  assert.match(focus,/<textarea disabled=\{busy\}/);assert.match(focus,/onClick=\{undo\}/);assert.match(focus,/disabled=\{busy\} onClick=\{undo\}|disabled=\{busy\}><RotateCcw|onClick=\{undo\}><RotateCcw/);
  console.log('Setup write/refresh failures, dirty choices, latest-request gate, motion preferences and rapid disclosure interruption passed (model checks; browser checks separate).');
 }finally{await server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

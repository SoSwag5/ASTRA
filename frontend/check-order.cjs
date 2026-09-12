const ts=require('typescript');
const fs=require('fs');
const vm=require('vm');
const assert=require('node:assert/strict');
const js=ts.transpile(fs.readFileSync('src/jobOrder.ts','utf8'),{module:ts.ModuleKind.CommonJS});
const context={exports:{}};vm.runInNewContext(js,context);
const compare=context.exports.compareJobs;
const jobs=[{id:1,location:'Remote',match_score:99,date_found:'2026-09-11'},
{id:2,location:'Dubai',match_score:80,date_found:'2026-09-09'},
{id:3,location:'Abu Dhabi, UAE',match_score:80,date_found:'2026-09-10'},
{id:4,location:'Sharjah',match_score:90,date_found:'2026-09-08'}];
assert.deepEqual([...jobs].sort((a,b)=>compare(a,b,'uae_first')).map(x=>x.id),[4,3,2,1]);
assert.deepEqual([...jobs].sort((a,b)=>compare(a,b,'date_found')).map(x=>x.id),[1,3,2,4]);
assert.deepEqual([...jobs].sort((a,b)=>compare(a,b,'match_score')).map(x=>x.id),[1,4,3,2]);
console.log('All three job sorting modes passed.');

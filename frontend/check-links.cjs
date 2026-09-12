const ts=require('typescript'),fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const context={exports:{},URL};
vm.runInNewContext(ts.transpile(fs.readFileSync('src/safeLink.ts','utf8'),{module:ts.ModuleKind.CommonJS}),context);
const safe=context.exports.safeLink;
for(const bad of ['javascript:alert(1)','data:text/html,hi','file:///private','//example.com','https://user:pass@example.com','relative',null])assert.equal(safe(bad),undefined);
assert.equal(safe('https://example.com/jobs?q=a b'),'https://example.com/jobs?q=a%20b');
assert.equal(safe('http://example.com'),'http://example.com/');
console.log('9 external-link safety scenarios passed.');

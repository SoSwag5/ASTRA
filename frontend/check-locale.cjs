const fs=require('fs'),ts=require('typescript'),vm=require('vm'),assert=require('node:assert/strict');
const compiled=ts.transpileModule(fs.readFileSync('src/locale.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const context={exports:{},Intl,Date,Number,localStorage:{getItem:()=>null}};vm.runInNewContext(compiled,context);
const cases=[['en-GB','Europe/London','GBP'],['ar-AE','Asia/Dubai','AED'],['de-DE','Europe/Berlin','EUR'],['en-CA','America/Toronto','CAD'],['ja-JP','Asia/Tokyo','JPY']];
for(const [locale,zone,currency] of cases){
 const date=context.exports.formatDateTime('2026-01-15T12:30:00Z',locale,zone);
 assert.equal(date,new Intl.DateTimeFormat(locale,{timeZone:zone,dateStyle:'medium',timeStyle:'short'}).format(new Date('2026-01-15T12:30:00Z')));
 assert.ok(context.exports.formatSalary(1234.5,currency,'month',locale).endsWith(' / month'));
}
assert.equal(context.exports.formatDateTime('not a date'),'Date unknown');
assert.equal(context.exports.formatDateTime('2026-01-15T12:30:00Z','bad_!','bad/zone'),'Locale or timezone unavailable');
console.log('5 locale/date/currency scenarios and invalid-input fallbacks passed; formatting checks do not certify translation or accessibility.');

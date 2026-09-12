export function locale(){return localStorage.getItem('uiLocale')||'en-GB'}
export function timeZone(){return localStorage.getItem('uiTimeZone')||'Asia/Dubai'}
export function formatDateTime(value:string,lang=locale(),zone=timeZone()){
 const date=new Date(value);if(Number.isNaN(date.valueOf()))return 'Date unknown';
 try{return new Intl.DateTimeFormat(lang,{timeZone:zone,dateStyle:'medium',timeStyle:'short'}).format(date)}catch{return 'Locale or timezone unavailable'}
}
export function formatDate(value:string,lang=locale()){
 const date=new Date(value);return Number.isNaN(date.valueOf())?'Date unknown':new Intl.DateTimeFormat(lang,{dateStyle:'medium'}).format(date);
}
export function formatSalary(amount:number,currency:string,period:string,lang=locale()){
 return `${new Intl.NumberFormat(lang,{style:'currency',currency}).format(amount)} / ${period}`;
}

// External listing links are data, including links in legacy local records.
export function safeLink(value:unknown):string|undefined{
 if(typeof value!=='string'||value.length>2000)return undefined;
 try{const url=new URL(value);if(!['https:','http:'].includes(url.protocol)||url.username||url.password)return undefined;return url.href}catch{return undefined}
}

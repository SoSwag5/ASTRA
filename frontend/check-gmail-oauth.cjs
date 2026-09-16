/**
 * Issue #44 frontend guarantees for the Gmail OAuth controls.
 *
 * 1. No OAuth value is written to localStorage, sessionStorage or IndexedDB,
 *    so closing the tab or reloading clears every transient frontend OAuth
 *    value.
 * 2. Only bounded, authored strings are rendered -- an unknown backend code
 *    falls back to a generic line and is never echoed into the page.
 * 3. The consent URL is opened through safeLink with noopener/noreferrer.
 * 4. No token, code, PKCE value, state value or callback URL is referenced.
 */
const ts = require('typescript'), fs = require('fs'), vm = require('vm');
const assert = require('node:assert/strict');

const raw = fs.readFileSync('src/GmailConnection.tsx', 'utf8');
/** Executable code only: the file's own documentation names the storage APIs
 *  it promises not to use, so comments must not be scanned. */
const source = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
let checks = 0;
const check = (condition, message) => { assert.ok(condition, message); checks += 1; };

// --- 1. No browser storage of OAuth state -------------------------------
for (const api of ['localStorage', 'sessionStorage', 'indexedDB', 'IndexedDB',
                   'document.cookie', 'window.name', 'openDatabase']) {
  check(!source.includes(api),
        `GmailConnection.tsx must never use ${api} for OAuth state`);
}

// --- 2. No secret-bearing field is read or rendered ---------------------
for (const field of ['refresh_token', 'access_token', 'code_verifier',
                     'code_challenge', 'authorization_code',
                     'oauth_state', 'callback_url', 'redirect_uri', 'stack',
                     'credential_key', 'client_id']) {
  check(!source.includes(field),
        `GmailConnection.tsx must never reference ${field}`);
}

// --- 2b. The client secret is console-only, never a UI input ------------
// The panel may report WHETHER one is configured, but must never accept,
// hold or display a value. A password field would put it in page state and
// in a request body; a hidden console prompt keeps it in one process.
check(!/type=["']password["']/.test(source),
      'the Gmail panel must never render a secret input');
for (const forbidden of ['setSecret', 'client_secret:', 'clientSecret']) {
  check(!source.includes(forbidden),
        `GmailConnection.tsx must never hold a client secret (${forbidden})`);
}
check(source.includes('client_secret?.state'),
      'the panel should report only the bounded client-secret state');

// --- 3. The consent URL is opened safely --------------------------------
check(source.includes("safeLink(started.authorization_url)"),
      'the consent URL must pass through safeLink before it is opened');
check(source.includes("window.open(url,'_blank','noopener,noreferrer')"),
      'the consent URL must be opened with noopener,noreferrer');
check(source.includes('rel="noopener noreferrer"'),
      'the fallback consent link must carry rel="noopener noreferrer"');
check(!/window\.open\((?!url,)/.test(source),
      'only the validated consent URL may be opened');

// --- 4. Bounded message mapping is total and never echoes input ---------
const context = { exports: {}, module: { exports: {} }, require: () => ({}) };
const mapOnly = source.slice(source.indexOf('const MESSAGES'),
                             source.indexOf('export function'))
  + '\nexports.MESSAGES=MESSAGES;exports.describe=describe;';
vm.runInNewContext(ts.transpile(mapOnly, { module: ts.ModuleKind.CommonJS }), context);
const { MESSAGES, describe } = context.exports;
check(typeof describe === 'function', 'the message mapper must be loadable');
check(Object.keys(MESSAGES).length >= 25, 'every bounded backend code needs a message');

// An unknown or hostile code is never reflected into the rendered string.
for (const hostile of ['<script>alert(1)</script>', 'UNKNOWN_CODE',
                       'astra-sentinel-refresh-4f9c2a71b0e83d5647fa19cb8e2d70a3',
                       '', undefined, null]) {
  const rendered = describe(hostile);
  check(rendered === '', `an unknown code must render nothing, got ${rendered}`);
}
for (const [code, text] of Object.entries(MESSAGES)) {
  check(describe(code) === text, `${code} must map to its authored message`);
  check(!text.includes('<') && !text.includes('{'),
        `${code}'s message must be plain authored text`);
}

// The component must be wired into the privacy panel.
const panel = fs.readFileSync('src/PrivacyPanel.tsx', 'utf8');
check(panel.includes("import {GmailConnection} from './GmailConnection'"),
      'the Gmail controls must be reachable from the privacy panel');
check(panel.includes('<GmailConnection api={api}/>'),
      'the Gmail controls must be rendered in the privacy panel');

console.log(`${checks} Gmail OAuth frontend safety checks passed.`);

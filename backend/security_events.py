"""Local, structured security-event telemetry.

A small, honest detection layer: preventive controls elsewhere in the codebase
call record() when they block something. Events are appended as one JSON object
per line to DATA/security-events.log. This is NOT a SIEM and makes no network
call. Only safe, non-PII fields are recorded; free-text reasons are length-capped
and control characters are stripped to prevent log injection.

Taxonomy (event -> CWE / control):
  INVALID_ORIGIN_BLOCKED       CWE-352  cross-origin request rejected by Origin allowlist
  CSRF_REJECTED                CWE-352  browser Sec-Fetch-Site=cross-site rejected
  PEER_BLOCKED                 CWE-668  non-loopback network peer rejected
  UPLOAD_REJECTED              CWE-434  upload failed structural/type validation
  UPLOAD_ACTIVE_CONTENT_BLOCKED CWE-434 PDF active/embedded content rejected
  SSRF_DESTINATION_BLOCKED     CWE-918  outbound fetch to private/loopback/blocked target
  SECRET_STORAGE_UNAVAILABLE   CWE-522  native credential store missing (fail-closed)

Gmail OAuth taxonomy (issue #44 / ADR-0007):
  GMAIL_OAUTH_ATTEMPT_STARTED     CWE-1021 authorization attempt opened for a slot
  GMAIL_OAUTH_CALLBACK_REJECTED   CWE-352  loopback callback failed state/PKCE/shape checks
  GMAIL_OAUTH_ATTEMPT_ENDED       CWE-613  attempt cancelled, expired or superseded
  GMAIL_OAUTH_CONNECTED           CWE-522  credential stored and metadata persisted
  GMAIL_OAUTH_SCOPE_MISMATCH      CWE-269  granted scope was missing or broader than requested
  GMAIL_OAUTH_IDENTITY_CONFLICT   CWE-863  credential would attach to a conflicting account
  GMAIL_ACCOUNT_DISCONNECTED      CWE-522  local credential and sync state removed
  GMAIL_REMOTE_REVOCATION_FAILED  CWE-613  Google-side revocation did not succeed
  GMAIL_CREDENTIAL_STORE_FAILED   CWE-522  OS credential store unavailable or write/read failed

Bounded fields: `record()` normally discards every caller-supplied field,
because free text, URLs and filenames can carry PII or secrets. BOUNDED_FIELDS
is the one narrow exception: a field is persisted only when the event declares
it AND the value is a member of that field's fixed token set. Anything else --
an unknown field name, a value outside the set, a non-string -- is dropped.
So a slot and a bounded outcome can be recorded without ever admitting an
arbitrary string, and no token, code, verifier, state, callback URL, email
address, client ID or raw Google message can reach the log through this path.
"""
import json, re, threading
from collections import deque
from datetime import datetime, timezone

_LOCK = threading.Lock()
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
MAX_BYTES = 1_000_000

SEVERITY = {
    'ACCESS_REJECTED': 'WARNING',
    'INVALID_ORIGIN_BLOCKED': 'WARNING',
    'CSRF_REJECTED': 'WARNING',
    'PEER_BLOCKED': 'WARNING',
    'UPLOAD_REJECTED': 'NOTICE',
    'UPLOAD_ACTIVE_CONTENT_BLOCKED': 'WARNING',
    'SSRF_DESTINATION_BLOCKED': 'WARNING',
    'SECRET_STORAGE_UNAVAILABLE': 'ERROR',
    'GMAIL_OAUTH_ATTEMPT_STARTED': 'NOTICE',
    'GMAIL_OAUTH_CALLBACK_REJECTED': 'WARNING',
    'GMAIL_OAUTH_ATTEMPT_ENDED': 'NOTICE',
    'GMAIL_OAUTH_CONNECTED': 'NOTICE',
    'GMAIL_OAUTH_SCOPE_MISMATCH': 'WARNING',
    'GMAIL_OAUTH_IDENTITY_CONFLICT': 'WARNING',
    'GMAIL_ACCOUNT_DISCONNECTED': 'NOTICE',
    'GMAIL_REMOTE_REVOCATION_FAILED': 'WARNING',
    'GMAIL_CREDENTIAL_STORE_FAILED': 'ERROR',
}

#: Authored, fixed reason text per event. Events without an entry keep the
#: original constant, so every pre-existing event records byte-identically.
DEFAULT_REASON = 'Security control blocked an operation'
REASONS = {
    'GMAIL_OAUTH_ATTEMPT_STARTED': 'Gmail authorization attempt started',
    'GMAIL_OAUTH_CALLBACK_REJECTED': 'Gmail OAuth callback rejected',
    'GMAIL_OAUTH_ATTEMPT_ENDED': 'Gmail authorization attempt ended without connecting',
    'GMAIL_OAUTH_CONNECTED': 'Gmail account connected',
    'GMAIL_OAUTH_SCOPE_MISMATCH': 'Gmail granted scope did not match the request',
    'GMAIL_OAUTH_IDENTITY_CONFLICT': 'Gmail authorized identity conflicted with an existing account',
    'GMAIL_ACCOUNT_DISCONNECTED': 'Gmail account disconnected locally',
    'GMAIL_REMOTE_REVOCATION_FAILED': 'Gmail remote revocation did not succeed',
    'GMAIL_CREDENTIAL_STORE_FAILED': 'Gmail credential store operation failed',
}

_SLOTS = frozenset({'PRIMARY', 'SECONDARY'})
#: Every bounded outcome token any Gmail OAuth event may record. Keeping one
#: shared set makes the complete vocabulary reviewable in one place; a value
#: outside it is dropped rather than written.
_GMAIL_RESULTS = frozenset({
    'STARTED', 'CONNECTED', 'CANCELLED', 'EXPIRED', 'SUPERSEDED', 'INVALIDATED',
    'INVALIDATED_BY_DISCONNECT', 'CONNECTION_FAILED',
    'CALLBACK_INVALID', 'CALLBACK_STATE_MISSING', 'CALLBACK_STATE_MISMATCH',
    'CALLBACK_MISSING_CODE', 'CALLBACK_DUPLICATE_PARAMETER',
    'CALLBACK_UNEXPECTED_PARAMETER', 'CALLBACK_PROVIDER_ERROR',
    'CALLBACK_REPLAYED', 'ATTEMPT_EXPIRED',
    'TOKEN_EXCHANGE_FAILED', 'TOKEN_RESPONSE_INVALID', 'ACCESS_TOKEN_MISSING',
    'REFRESH_TOKEN_NOT_RETURNED', 'SCOPE_MISSING_REQUIRED',
    'SCOPE_BROADER_THAN_REQUESTED', 'IDENTITY_LOOKUP_FAILED',
    'IDENTITY_RESPONSE_INVALID', 'IDENTITY_ALREADY_CONNECTED',
    'CREDENTIAL_STORE_UNAVAILABLE', 'CREDENTIAL_STORE_FAILED',
    'PERSISTENCE_FAILED', 'STORE_UNAVAILABLE', 'STORE_NOT_NATIVE',
    'WRITE_FAILED', 'READ_FAILED', 'DELETE_FAILED',
    'SUCCEEDED', 'FAILED', 'NOT_ATTEMPTED_NO_LOCAL_CREDENTIAL',
})
_GMAIL_BOUNDED = {'slot': _SLOTS, 'result': _GMAIL_RESULTS}
BOUNDED_FIELDS = {event: _GMAIL_BOUNDED for event in SEVERITY
                  if event.startswith('GMAIL_')}


def _bounded(event, fields):
    """Keep only allowlisted field names whose values are allowlisted tokens."""
    allowed = BOUNDED_FIELDS.get(event)
    if not allowed:
        return {}
    return {name: value for name, value in fields.items()
            if name in allowed and isinstance(value, str) and value in allowed[name]}

def _clean(value, limit=200):
    """Neutralize log injection: strip control chars/newlines, cap length."""
    return _CONTROL.sub(' ', str(value))[:limit]

def record(event, reason='', **fields):
    """Append one security event. Never raises into the calling control path."""
    try:
        from .models import DATA
        if event not in SEVERITY:
            return
        entry = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'event': event,
            'severity': SEVERITY.get(event, 'NOTICE'),
            # Free text, URLs, filenames and request paths can contain PII/secrets.
            # Persist only our fixed taxonomy, never attacker-supplied strings.
            'reason': REASONS.get(event, DEFAULT_REASON),
            # Only allowlisted field names carrying allowlisted enum tokens
            # survive; see BOUNDED_FIELDS in the module docstring.
            'fields': _bounded(event, fields),
        }
        path = DATA / 'security-events.log'
        line = json.dumps(entry, ensure_ascii=True)
        with _LOCK:
            if path.exists() and path.stat().st_size + len(line) > MAX_BYTES:
                path.replace(path.with_suffix('.log.1'))
            with open(path, 'a', encoding='utf-8') as handle:
                handle.write(line + '\n')
    except Exception:
        # Telemetry must never break or delay a security control.
        pass

def tail(limit=200):
    """Read back recent events for the self-check / UI. Local only."""
    try:
        from .models import DATA
        path = DATA / 'security-events.log'
        if not path.exists():
            return []
        with open(path, encoding='utf-8') as handle:
            lines = deque(handle, maxlen=min(max(limit, 1), 500))
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
    except Exception:
        return []

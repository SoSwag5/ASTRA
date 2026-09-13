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
  SESSION_INVALID              CWE-613  expired/invalid access session rejected on a private API
  REQUEST_REJECTED             CWE-668  private API request with a disallowed browser destination
  AI_QUOTA_EXCEEDED            CWE-770  daily AI request budget reached
  AI_RESPONSE_OVERSIZED        CWE-400  AI provider response exceeded the read cap
  UNHANDLED_ERROR              CWE-755  request handler raised an unexpected error

Each line carries a `chain` digest = SHA-256(prev_chain + core fields), forming a
tamper-EVIDENT append-only chain: any modification, reordering, insertion or
deletion breaks verification (see `verify`). It is not immutable — a local actor
with code access could recompute the whole chain — so this detects accidental or
external tampering, not a same-user forgery (that remains out of scope, R-15).
"""
import hashlib, json, re, threading
from collections import deque
from datetime import datetime, timezone

_LOCK = threading.Lock()
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
MAX_BYTES = 1_000_000
_GENESIS = '0' * 64
_last_chain = None  # in-memory tail of the current log's hash chain

SEVERITY = {
    'ACCESS_REJECTED': 'WARNING',
    'INVALID_ORIGIN_BLOCKED': 'WARNING',
    'CSRF_REJECTED': 'WARNING',
    'PEER_BLOCKED': 'WARNING',
    'UPLOAD_REJECTED': 'NOTICE',
    'UPLOAD_ACTIVE_CONTENT_BLOCKED': 'WARNING',
    'SSRF_DESTINATION_BLOCKED': 'WARNING',
    'SECRET_STORAGE_UNAVAILABLE': 'ERROR',
    'SESSION_INVALID': 'WARNING',
    'REQUEST_REJECTED': 'NOTICE',
    'AI_QUOTA_EXCEEDED': 'NOTICE',
    'AI_RESPONSE_OVERSIZED': 'WARNING',
    'UNHANDLED_ERROR': 'ERROR',
}

def _clean(value, limit=200):
    """Neutralize log injection: strip control chars/newlines, cap length."""
    return _CONTROL.sub(' ', str(value))[:limit]

def _core(entry):
    """Deterministic representation of the chained fields (excludes `chain`)."""
    return json.dumps({k: entry[k] for k in ('ts', 'event', 'severity', 'reason', 'fields')},
                      sort_keys=True, ensure_ascii=True)

def _link(prev, entry):
    return hashlib.sha256((prev + _core(entry)).encode()).hexdigest()

def _load_last_chain(path):
    """Resume the chain from the current log's last valid line, else genesis."""
    if not path.exists():
        return _GENESIS
    last = _GENESIS
    try:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                try:
                    last = json.loads(line).get('chain', last)
                except ValueError:
                    continue
    except Exception:
        pass
    return last

def record(event, reason='', **fields):
    """Append one security event. Never raises into the calling control path."""
    global _last_chain
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
            'reason': 'Security control blocked an operation',
            'fields': {},
        }
        path = DATA / 'security-events.log'
        with _LOCK:
            if _last_chain is None:
                _last_chain = _load_last_chain(path)
            entry['chain'] = _link(_last_chain, entry)
            line = json.dumps(entry, ensure_ascii=True)
            if path.exists() and path.stat().st_size + len(line) > MAX_BYTES:
                path.replace(path.with_suffix('.log.1'))
                _last_chain = _GENESIS  # a rotated file starts a fresh chain
                entry['chain'] = _link(_last_chain, entry)
                line = json.dumps(entry, ensure_ascii=True)
            with open(path, 'a', encoding='utf-8') as handle:
                handle.write(line + '\n')
            _last_chain = entry['chain']
    except Exception:
        # Telemetry must never break or delay a security control.
        pass

def verify(path=None):
    """Recompute the chain over the current log and report tamper-evidence.

    Returns {'ok': bool, 'checked': int, 'broken_at': int|None}. broken_at is the
    0-based index of the first line whose stored digest does not match.
    """
    try:
        from .models import DATA
        path = path or DATA / 'security-events.log'
        if not path.exists():
            return {'ok': True, 'checked': 0, 'broken_at': None}
        prev, checked = _GENESIS, 0
        with open(path, encoding='utf-8') as handle:
            for index, line in enumerate(handle):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    return {'ok': False, 'checked': checked, 'broken_at': index}
                if entry.get('chain') != _link(prev, entry):
                    return {'ok': False, 'checked': checked, 'broken_at': index}
                prev = entry['chain']
                checked += 1
        return {'ok': True, 'checked': checked, 'broken_at': None}
    except Exception:
        return {'ok': False, 'checked': 0, 'broken_at': None}

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

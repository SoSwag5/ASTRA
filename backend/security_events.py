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
"""
import json, re, threading
from datetime import datetime, timezone

_LOCK = threading.Lock()
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')

SEVERITY = {
    'INVALID_ORIGIN_BLOCKED': 'WARNING',
    'CSRF_REJECTED': 'WARNING',
    'PEER_BLOCKED': 'WARNING',
    'UPLOAD_REJECTED': 'NOTICE',
    'UPLOAD_ACTIVE_CONTENT_BLOCKED': 'WARNING',
    'SSRF_DESTINATION_BLOCKED': 'WARNING',
    'SECRET_STORAGE_UNAVAILABLE': 'ERROR',
}

def _clean(value, limit=200):
    """Neutralize log injection: strip control chars/newlines, cap length."""
    return _CONTROL.sub(' ', str(value))[:limit]

def record(event, reason='', **fields):
    """Append one security event. Never raises into the calling control path."""
    try:
        from .models import DATA
        entry = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'event': event,
            'severity': SEVERITY.get(event, 'NOTICE'),
            'reason': _clean(reason),
            'fields': {k: _clean(v, 120) for k, v in fields.items()},
        }
        path = DATA / 'security-events.log'
        line = json.dumps(entry, ensure_ascii=True)
        with _LOCK:
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
            lines = handle.readlines()[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
    except Exception:
        return []

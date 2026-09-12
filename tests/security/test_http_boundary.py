"""HTTP-boundary security regression tests: Host, Origin, CSRF, headers, traversal,
content bounds, injection-as-data. Runs the real app via an isolated TestClient in a
subprocess so DATABASE_URL points at a throwaway DB and never the user's data.

Codifies the dynamic verification performed during the 2026-09 security review.
"""
import os, subprocess, sys
from pathlib import Path

HARNESS = r'''
import json, sys
from fastapi.testclient import TestClient
from backend.main import app

fails = []
def expect(name, cond, detail=''):
    if not cond:
        fails.append(f"{name} :: {detail}")

with TestClient(app) as c:
    expect('health', c.get('/api/health').status_code == 200)

    # Origin allowlist (CWE-352)
    expect('origin_evil_blocked', c.get('/api/settings', headers={'Origin': 'https://evil.example'}).status_code == 403)
    expect('origin_absent_allowed', c.get('/api/settings').status_code == 200)
    expect('origin_local_allowed', c.get('/api/settings', headers={'Origin': 'http://localhost:8787'}).status_code == 200)

    # Sec-Fetch-Site CSRF guard (CWE-352)
    expect('csrf_cross_site_blocked', c.get('/api/settings', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403)

    # Host allowlist / DNS-rebinding (CWE-350) via TrustedHostMiddleware
    expect('bad_host_blocked', c.get('/api/health', headers={'Host': 'attacker.example'}).status_code == 400)
    expect('good_host_allowed', c.get('/api/health', headers={'Host': '127.0.0.1'}).status_code == 200)

    # Path traversal on file download (CWE-22)
    for p in ['../.env', '..%2f..%2f.env', '../../backend/main.py', '..\\..\\backend\\main.py']:
        expect(f'traversal[{p}]', c.get('/api/files/' + p).status_code == 404)

    # Security headers at runtime (not just middleware config)
    h = c.get('/api/health').headers
    expect('csp', "default-src 'self'" in h.get('content-security-policy', ''))
    expect('frame_ancestors', "frame-ancestors 'none'" in h.get('content-security-policy', ''))
    expect('script_src_self', "script-src 'self'" in h.get('content-security-policy', ''))
    expect('xfo', h.get('x-frame-options') == 'DENY')
    expect('nosniff', h.get('x-content-type-options') == 'nosniff')
    expect('referrer', h.get('referrer-policy') == 'no-referrer')
    expect('cache', h.get('cache-control') == 'no-store')
    expect('permissions_policy', 'geolocation=()' in h.get('permissions-policy', ''))

    # Autopilot cannot be set to auto-submit (structural PREPARE-ONLY)
    expect('autopilot_auto_rejected', c.put('/api/settings', json={'autopilot': 'AUTO_ALLOWED'}).status_code == 400)

    # Arbitrary URL import disabled (SSRF surface reduction)
    expect('import_url_disabled', c.post('/api/import/url', json={'url': 'https://example.com/x'}).status_code == 400)
    expect('linkedin_blocked', c.post('/api/import/url', json={'url': 'https://linkedin.com/jobs/1'}).status_code == 400)

    # XSS-as-data: untrusted job content stored verbatim (React escapes at render)
    payload = '<script>window.__pwned=1</script>'
    r = c.post('/api/jobs', json={'company': payload, 'title': '<img src=x onerror=alert(1)>', 'description': 'x', 'location': 'Dubai'})
    expect('xss_stored_as_data', r.status_code == 200 and r.json()['company'] == payload)

    # SQL injection has no effect (parameterized ORM)
    r = c.post('/api/jobs', json={'company': "'; DROP TABLE jobs;--", 'title': "1' OR '1'='1", 'description': 'x', 'location': 'Dubai'})
    expect('sqli_created', r.status_code == 200)
    expect('sqli_table_intact', c.get('/api/jobs').status_code == 200 and len(c.get('/api/jobs').json()) >= 2)

    # Content-length bound (DoS)
    r = c.post('/api/jobs', content=b'{}', headers={'Content-Type': 'application/json', 'Content-Length': '99999999'})
    expect('content_length_bound', r.status_code == 413)

    # Non-JSON mutation rejected
    expect('bad_content_type', c.post('/api/jobs', content=b'x', headers={'Content-Type': 'text/plain'}).status_code in (400, 415))

print(json.dumps({'fails': fails}))
sys.exit(1 if fails else 0)
'''


def test_http_security_boundary(tmp_path):
    env = {**os.environ,
           'DATABASE_URL': f'sqlite:///{tmp_path / "sec.db"}',
           'HUNTER_DATA_DIR': str(tmp_path / 'data'),
           'APP_TOKEN': '',
           'PYTHONPATH': str(Path(__file__).resolve().parents[2])}
    (tmp_path / 'data').mkdir(parents=True, exist_ok=True)
    result = subprocess.run([sys.executable, '-c', HARNESS], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr

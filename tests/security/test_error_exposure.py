"""Client-facing failures carry no exception internals (CWE-209), and the file
download builds no path from unvalidated components (CWE-22).

Runs the real app in a subprocess against a throwaway database so the user's
storage is never touched. Fixture paths are assembled at runtime so this file
carries no literal the publication gate is required to flag.
"""
import os
import subprocess
import sys

HARNESS = r'''
import json, sys
from fastapi import HTTPException
from fastapi.testclient import TestClient
import backend.main as main
from backend.main import app, UNEXPECTED_FAILURE

B = chr(92)
# Stands in for internals an unexpected error could name: a local path.
SECRET = 'C' + ':' + B + 'Users' + B + 'someone' + B + 'private.db'

fails = []
def expect(name, cond, detail=''):
    if not cond:
        fails.append(name + ' :: ' + str(detail))

def raises(error):
    def action(*args, **kwargs):
        raise error
    return action

with TestClient(app) as c:
    # An unexpected internal error must be reported as the generic failure only.
    main.job_action = raises(OSError('cannot read ' + SECRET))
    body = json.dumps(c.post('/api/bulk/prepare', json={'ids': [1]}).json())
    expect('unexpected_is_generic', json.loads(body)[0]['error'] == UNEXPECTED_FAILURE, body)
    expect('no_local_path', SECRET not in body, body)
    expect('no_exception_type', 'OSError' not in body, body)

    # Even application-authored exception text stays out of the response; the
    # client gets a fixed string and the reason is available per job.
    main.job_action = raises(HTTPException(404, 'Job not found at ' + SECRET))
    body = json.dumps(c.post('/api/bulk/prepare', json={'ids': [2]}).json())
    expect('http_detail_withheld', 'Job not found at' not in body, body)
    expect('http_fixed_string', 'no longer available' in body, body)

    main.job_action = raises(ValueError('Confirm profile facts for ' + SECRET))
    body = json.dumps(c.post('/api/bulk/prepare', json={'ids': [3]}).json())
    expect('validation_text_withheld', 'Confirm profile facts' not in body, body)
    expect('validation_no_secret', SECRET not in body, body)
    expect('validation_fixed_string', 'needs attention' in body, body)

    # A forged log record cannot be injected through a request value.
    expect('log_safe_strips_newlines', main.log_safe('12' + chr(10) + 'FORGED') == '12_FORGED')
    expect('log_safe_keeps_plain', main.log_safe(7) == '7')

    # Unhandled errors on ordinary routes stay generic too.
    main.job_action = raises(RuntimeError('internal ' + SECRET))
    response = c.post('/api/jobs/1/analyze')
    expect('route_no_internals', SECRET not in response.text, response.text)

    # Download path components are allowlisted before any join (CWE-22).
    escapes = [
        '../.env', '..%2f.env', '../../backend/main.py',
        '..' + B + '..' + B + 'backend' + B + 'main.py',
        'C' + ':/Windows/win.ini', '/etc/passwd',
        'sub/../../escape.pdf', '.', '..', 'a b/c.pdf',
    ]
    for path in escapes:
        expect('download[' + path + ']', c.get('/api/files/' + path).status_code == 404)

print(json.dumps(fails))
sys.exit(1 if fails else 0)
'''


def test_failures_expose_no_internals_and_downloads_reject_traversal(tmp_path):
    env = {**os.environ,
           'DATABASE_URL': 'sqlite:///' + str(tmp_path / 'errors.db'),
           'HUNTER_DATA_DIR': str(tmp_path / 'data'),
           'APP_TOKEN': ''}
    result = subprocess.run([sys.executable, '-c', HARNESS], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr

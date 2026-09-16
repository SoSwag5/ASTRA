"""Issue #44 negative regressions: Gmail OAuth secrets must not escape.

Every test here drives a real connect/disconnect cycle with high-entropy
synthetic sentinels and then proves those sentinels are absent from each
place a secret could plausibly surface: application logs, the
security-event file, the SQLite database bytes, the private export, a
daily backup, diagnostic output, API response bodies, and exception
strings.  It also proves the API stays behind ASTRA's existing loopback,
Host, Origin, CSRF and session controls, and that the existing OpenAI
credential path is unchanged.

Storage is isolated: `tests/conftest.py` points the data directory and
database at a temporary location, and the credential store is the
in-memory double from `tests/gmail_fixtures.py`.  No test reads the
user's real Gmail account, real credential store, or normal ASTRA
database.
"""
import io
import json
import logging
import sqlite3
import zipfile

import pytest
from sqlalchemy import select

from backend import gmail_accounts as accounts
from backend import gmail_oauth as oauth
from backend.models import Session
from tests.gmail_fixtures import (OTHER_EMAIL, SENTINEL_ACCESS, SENTINEL_CODE,
                                  SENTINEL_REFRESH, SYNTHETIC_CLIENT_ID,
                                  SYNTHETIC_EMAIL, FakeListener, gmail_env,
                                  install_google_double, keyring_backend,
                                  token_response)

pytestmark = pytest.mark.usefixtures('gmail_env')

#: A synthetic OAuth *client* secret. Owner-authorized for issue #44 after
#: live evidence proved this Desktop client enforces client authentication
#: at the token endpoint. It is the same class of secret as a refresh token
#: for leakage purposes, so it joins the sentinel set.
SENTINEL_CLIENT_SECRET = 'astra-sentinel-clientsecret-6d3f81b904ae572c1fb8'

#: Every value that must never appear in any persisted or returned artifact.
SENTINELS = (SENTINEL_REFRESH, SENTINEL_ACCESS, SENTINEL_CODE,
             SENTINEL_CLIENT_SECRET)


def connect(monkeypatch, **double):
    """Drive one full synthetic connection and return its transient values.

    `state` and `verifier` are captured here so the assertions can prove
    they never appear anywhere afterwards. A client secret is configured
    first, so every artifact scanned below was produced by a run that
    actually held one.
    """
    accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    install_google_double(monkeypatch, **double)
    attempt, url = oauth.attempts.start('PRIMARY', accounts._finalize,
                                        listener_factory=FakeListener)
    listener = FakeListener.instances[-1]
    state, verifier = attempt.state.reveal(), attempt.verifier.reveal()
    accepted = listener.on_callback({'code': [SENTINEL_CODE], 'state': [state]})
    return {'accepted': accepted, 'state': state, 'verifier': verifier, 'url': url}


def assert_clean(blob, label, extra=()):
    """Assert no sentinel or transient OAuth value appears in `blob`."""
    if isinstance(blob, bytes):
        haystack = blob
        needles = [value.encode() for value in list(SENTINELS) + list(extra)]
    else:
        haystack = str(blob)
        needles = list(SENTINELS) + list(extra)
    for needle in needles:
        assert needle not in haystack, f'a secret leaked into {label}'


# ---------------------------------------------------------------------------
# Logs and security events
# ---------------------------------------------------------------------------
def test_no_secret_reaches_application_logs(monkeypatch, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    logging.getLogger('astra').setLevel(logging.DEBUG)
    session = connect(monkeypatch)
    assert session['accepted'] is True
    install_google_double(monkeypatch, revoke_status=200)
    accounts.disconnect('PRIMARY')
    captured = capsys.readouterr()
    transient = (session['state'], session['verifier'])
    for label, blob in (('caplog.text', caplog.text),
                        ('captured stdout', captured.out),
                        ('captured stderr', captured.err),
                        ('log records', json.dumps([r.getMessage() for r in caplog.records]))):
        assert_clean(blob, label, extra=transient)


def test_no_secret_reaches_the_security_event_file(monkeypatch, tmp_path):
    import backend.models as models
    monkeypatch.setattr(models, 'DATA', tmp_path)
    session = connect(monkeypatch)
    install_google_double(monkeypatch, revoke_status=400)
    accounts.disconnect('PRIMARY')
    written = ''.join(path.read_text(encoding='utf-8') for path in tmp_path.iterdir()
                      if path.is_file())
    assert written, 'the Gmail flow must record security events'
    assert_clean(written, 'the security-event file',
                 extra=(session['state'], session['verifier'], SYNTHETIC_EMAIL,
                        SYNTHETIC_CLIENT_ID))


def test_security_events_record_only_bounded_taxonomy_fields(monkeypatch, tmp_path):
    import backend.models as models
    import backend.security_events as events
    monkeypatch.setattr(models, 'DATA', tmp_path)
    connect(monkeypatch)
    install_google_double(monkeypatch, revoke_status=200)
    accounts.disconnect('PRIMARY')
    recorded = events.tail(200)
    codes = {entry['event'] for entry in recorded}
    assert 'GMAIL_OAUTH_ATTEMPT_STARTED' in codes
    assert 'GMAIL_OAUTH_CONNECTED' in codes
    assert 'GMAIL_ACCOUNT_DISCONNECTED' in codes
    for entry in recorded:
        assert entry['event'] in events.SEVERITY
        assert entry['severity'] in ('NOTICE', 'WARNING', 'ERROR')
        assert set(entry['fields']) <= {'slot', 'result'}
        if 'slot' in entry['fields']:
            assert entry['fields']['slot'] in ('PRIMARY', 'SECONDARY')
        if 'result' in entry['fields']:
            assert entry['fields']['result'] in events._GMAIL_RESULTS


def test_arbitrary_event_fields_are_still_discarded(monkeypatch, tmp_path):
    """The bounded allowlist must not become a general field channel."""
    import backend.models as models
    import backend.security_events as events
    monkeypatch.setattr(models, 'DATA', tmp_path)
    events.record('GMAIL_OAUTH_CONNECTED', 'free text reason', slot='PRIMARY',
                  result='CONNECTED', refresh_token=SENTINEL_REFRESH,
                  email=SYNTHETIC_EMAIL, callback_url='http://127.0.0.1/x?code=abc',
                  result_detail='arbitrary string', slot_extra='PRIMARY')
    entry = events.tail(5)[-1]
    assert entry['fields'] == {'slot': 'PRIMARY', 'result': 'CONNECTED'}
    assert entry['reason'] == events.REASONS['GMAIL_OAUTH_CONNECTED']
    assert_clean(json.dumps(entry), 'a security event', extra=(SYNTHETIC_EMAIL,))
    # A value outside the fixed set is dropped rather than written.
    events.record('GMAIL_OAUTH_CONNECTED', slot='TERTIARY', result=SENTINEL_REFRESH)
    assert events.tail(5)[-1]['fields'] == {}


def test_existing_event_taxonomy_still_records_a_constant_reason(monkeypatch, tmp_path):
    import backend.models as models
    import backend.security_events as events
    monkeypatch.setattr(models, 'DATA', tmp_path)
    events.record('SSRF_DESTINATION_BLOCKED', 'evil\n\rFAKE LOG LINE\x00',
                  host='127.0.0.1')
    entry = events.tail(5)[-1]
    assert entry['reason'] == 'Security control blocked an operation'
    assert entry['fields'] == {}
    assert entry['severity'] == 'WARNING'
    assert '\n' not in entry['reason']


# ---------------------------------------------------------------------------
# Database, export, backup
# ---------------------------------------------------------------------------
def _database_bytes():
    from backend.models import engine
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
    path = __import__('pathlib').Path(engine.url.database)
    blob = b''
    for candidate in (path, path.with_name(path.name + '-wal'),
                      path.with_name(path.name + '-shm')):
        if candidate.exists():
            blob += candidate.read_bytes()
    return blob


def test_no_secret_is_present_in_the_sqlite_database_bytes(monkeypatch):
    session = connect(monkeypatch)
    assert session['accepted'] is True
    assert_clean(_database_bytes(), 'the SQLite database',
                 extra=(session['state'], session['verifier']))
    # The authorized address is legitimate non-secret metadata and IS stored.
    assert SYNTHETIC_EMAIL.encode() in _database_bytes()


def test_no_gmail_column_can_ever_hold_a_secret():
    columns = accounts.GmailAccount.__table__.columns
    names = set(columns.keys())
    assert names == {
        'id', 'created_at', 'updated_at', 'slot', 'status', 'authorized_email',
        'identity_key', 'identity_kind', 'granted_scopes', 'credential_key',
        'connected_at', 'last_validated_at', 'disconnected_at',
        'last_remote_revocation', 'sync_state'}


def test_the_private_export_contains_no_secret_and_no_credential(monkeypatch, tmp_path):
    import backend.privacy as privacy
    session = connect(monkeypatch)
    monkeypatch.setattr(privacy, 'DATA', tmp_path)
    response = privacy._export_data()
    assert_clean(response.body, 'the private export',
                 extra=(session['state'], session['verifier']))
    archive = zipfile.ZipFile(io.BytesIO(response.body))
    records = json.loads(archive.read('records.json'))
    assert 'gmail_accounts' in records, 'the metadata table is exported'
    exported = json.dumps(records['gmail_accounts'])
    assert_clean(exported, 'the exported gmail_accounts rows')
    assert SYNTHETIC_EMAIL in exported, 'only non-secret metadata is exported'
    # No keyring entry or namespace is ever copied into the archive.
    assert accounts.CREDENTIAL_SERVICE not in response.body.decode('latin-1')
    assert 'Gmail connection tokens are excluded' in privacy.PRIVACY_COPY['export']


def test_a_daily_backup_contains_no_secret(monkeypatch, tmp_path):
    import backend.reliability as reliability
    session = connect(monkeypatch)
    monkeypatch.setattr(reliability, 'DATA', tmp_path)
    name = reliability.backup_database(force=True)
    assert name, 'a backup snapshot must be produced'
    snapshot = tmp_path / 'backups' / name
    assert_clean(snapshot.read_bytes(), 'a daily backup',
                 extra=(session['state'], session['verifier']))
    # The backup really does contain the account row -- just no secret in it.
    with sqlite3.connect(snapshot) as copy:
        rows = copy.execute('SELECT authorized_email, credential_key FROM gmail_accounts').fetchall()
    assert rows and rows[0][0] == SYNTHETIC_EMAIL
    assert_clean(json.dumps(rows), 'the backed-up account row')


def test_diagnostics_report_only_bounded_connection_state(monkeypatch):
    from backend.doctor import run_checks
    session = connect(monkeypatch)
    checks = run_checks()
    payload = json.dumps(checks)
    assert_clean(payload, 'diagnostic output',
                 extra=(session['state'], session['verifier'], SYNTHETIC_EMAIL,
                        SYNTHETIC_CLIENT_ID))
    gmail = next(check for check in checks if check['check'] == 'gmail_integration')
    assert 'primary=CONNECTED' in gmail['detail']
    assert gmail['status'] in ('PASS', 'WARNING')


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import backend.main as main
    with TestClient(main.app) as made:
        yield made


def test_no_api_response_body_contains_a_secret(monkeypatch, client):
    session = connect(monkeypatch)
    install_google_double(monkeypatch, revoke_status=200)
    bodies = []
    for method, path in (('GET', '/api/gmail/status'),
                         ('GET', '/api/gmail/accounts/primary/authorize'),
                         ('GET', '/api/gmail/accounts/secondary/authorize'),
                         ('POST', '/api/gmail/accounts/primary/authorize/cancel'),
                         ('POST', '/api/gmail/accounts/secondary/authorize'),
                         ('POST', '/api/gmail/accounts/primary/disconnect'),
                         ('GET', '/api/privacy'),
                         ('GET', '/api/privacy/self-check'),
                         ('GET', '/api/privacy/security-events')):
        response = client.request(method, path, json={} if method == 'POST' else None)
        bodies.append(response.text)
        assert response.headers.get('cache-control') == 'no-store'
    assert_clean('\n'.join(bodies), 'an API response body',
                 extra=(session['state'], session['verifier'], SYNTHETIC_CLIENT_ID))


def test_the_status_endpoint_returns_no_secret_and_reports_the_secondary_gate(client):
    payload = client.get('/api/gmail/status').json()
    assert payload['accounts']['SECONDARY']['enabled'] is False
    assert payload['accounts']['SECONDARY']['gate_code'] == 'SECONDARY_NOT_ENABLED'
    assert payload['read_only'] is True
    assert 'authorization_url' not in json.dumps(payload)


def test_an_invalid_account_slot_is_rejected(client):
    for slug in ('tertiary', 'PRIMARY%20', 'x' * 40, 'admin', '1'):
        assert client.post(f'/api/gmail/accounts/{slug}/authorize',
                           json={}).status_code == 404
        assert client.get(f'/api/gmail/accounts/{slug}/authorize').status_code == 404
        assert client.post(f'/api/gmail/accounts/{slug}/disconnect',
                           json={}).status_code == 404


def test_the_secondary_slot_reports_not_enabled_through_the_api(client):
    response = client.post('/api/gmail/accounts/secondary/authorize', json={})
    assert response.status_code == 409
    assert response.json()['code'] == 'SECONDARY_NOT_ENABLED'


def test_state_changing_routes_are_never_reachable_by_get(client):
    # 404 (no GET route at that path) or 405 (method not allowed) -- either
    # way a GET cannot start, cancel or disconnect anything.
    for path in ('/api/gmail/accounts/primary/authorize/cancel',
                 '/api/gmail/accounts/primary/disconnect'):
        assert client.get(path).status_code in (404, 405)
    # Starting an attempt is a POST; the same path under GET is the
    # read-only status route and must not create an attempt.
    before = oauth.attempts.pending_slots()
    assert client.get('/api/gmail/accounts/primary/authorize').status_code == 200
    assert oauth.attempts.pending_slots() == before


def test_gmail_routes_stay_behind_the_existing_origin_csrf_and_host_controls(client):
    paths = ('/api/gmail/status', '/api/gmail/accounts/primary/authorize')
    for path in paths:
        cross_origin = client.get(path, headers={'Origin': 'https://evil.example'})
        assert cross_origin.status_code == 403
        cross_site = client.get(path, headers={'Sec-Fetch-Site': 'cross-site'})
        assert cross_site.status_code == 403
        navigated = client.get(path, headers={'Sec-Fetch-Dest': 'document'})
        assert navigated.status_code == 403
        bad_host = client.get(path, headers={'Host': 'evil.example'})
        assert bad_host.status_code == 400


def test_gmail_routes_require_a_session_when_an_access_key_is_configured(monkeypatch, client):
    from backend.access import sessions
    monkeypatch.setenv('APP_TOKEN', 'synthetic-local-access-key')
    sessions.sessions.clear()
    try:
        assert client.get('/api/gmail/status').status_code == 401
        assert client.post('/api/gmail/accounts/primary/authorize',
                           json={}).status_code == 401
        assert client.post('/api/gmail/accounts/primary/disconnect',
                           json={}).status_code == 401
        token = client.post('/api/access', json={'key': 'synthetic-local-access-key'}).json()['token']
        unlocked = client.get('/api/gmail/status',
                              headers={'Authorization': 'Bearer ' + token})
        assert unlocked.status_code == 200
    finally:
        sessions.sessions.clear()


def test_a_caller_cannot_choose_an_endpoint_scope_or_credential_key(client):
    """The slot is the only caller input the router accepts."""
    import backend.gmail_api as api
    for route in ('/api/gmail/status', '/api/gmail/accounts/primary/authorize'):
        response = client.get(route) if 'status' in route else client.post(
            route, json={'token_endpoint': 'https://evil.example/token',
                         'scope': 'https://mail.google.com/',
                         'redirect_uri': 'http://evil.example/cb',
                         'credential_key': 'chosen-by-caller',
                         'client_id': 'attacker-client'})
        assert 'evil.example' not in response.text
        assert 'mail.google.com' not in response.text
    # No handler takes any parameter other than the slot slug.
    for handler in (api.start_authorization, api.authorization_status,
                    api.cancel_authorization, api.disconnect_account):
        assert handler.__code__.co_varnames[:handler.__code__.co_argcount] == ('slug',)


def test_concurrent_start_and_disconnect_are_safe(monkeypatch, client):
    import threading
    connect(monkeypatch)
    install_google_double(monkeypatch, revoke_status=200)
    results = []
    barrier = threading.Barrier(2)

    def start():
        barrier.wait()
        try:
            results.append(('start', accounts.start_authorization('PRIMARY')['status']))
        except oauth.OAuthError as error:
            results.append(('start', error.code))

    def stop():
        barrier.wait()
        results.append(('disconnect', accounts.disconnect('PRIMARY')['local_disconnected']))

    threads = [threading.Thread(target=start), threading.Thread(target=stop)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 2
    # Whatever the interleaving, the account is never left reported as
    # connected with no credential behind it.
    state = accounts.status()['accounts']['PRIMARY']['status']
    assert state in ('DISCONNECTED', 'CONNECTED')
    if state == 'CONNECTED':
        assert accounts.read_credential(
            next(row.credential_key for row in _rows() if row.slot == 'PRIMARY')) is not None


def _rows():
    with Session() as db:
        return list(db.scalars(select(accounts.GmailAccount)))


# ---------------------------------------------------------------------------
# Exception strings
# ---------------------------------------------------------------------------
def test_no_exception_string_or_traceback_carries_a_secret(monkeypatch):
    import traceback
    failures = []

    install_google_double(monkeypatch, token=token_response(
        scope=f'{oauth.GMAIL_READONLY_SCOPE} https://mail.google.com/'))
    for double in ({'token': token_response(scope='')},
                   {'token': token_response(refresh=None)},
                   {'profile': {'emailAddress': 'malformed'}},
                   {'token': oauth.OAuthError('TOKEN_EXCHANGE_FAILED', 'rejected')}):
        install_google_double(monkeypatch, **double)
        try:
            accounts._finalize(attempt_id='synthetic', slot='PRIMARY',
                               code=oauth.Secret(SENTINEL_CODE),
                               verifier=oauth.generate_code_verifier(),
                               redirect_uri='http://127.0.0.1:1/cb')
        except Exception as error:
            failures.append(str(error))
            failures.append(repr(error))
            failures.append(''.join(traceback.format_exception(error)))
    assert failures, 'the failure paths must actually raise'
    assert_clean('\n'.join(failures), 'an exception string')


def test_a_keyring_failure_message_never_carries_the_token(monkeypatch, gmail_env):
    gmail_env.fail_set = True
    with pytest.raises(oauth.OAuthError) as raised:
        accounts.write_credential('primary-synthetic', oauth.Secret(SENTINEL_REFRESH))
    assert_clean(str(raised.value), 'a credential-store error')
    assert_clean(repr(raised.value), 'a credential-store error repr')
    assert raised.value.code == 'CREDENTIAL_STORE_FAILED'


# ---------------------------------------------------------------------------
# Deletion scope and compatibility
# ---------------------------------------------------------------------------
def test_full_local_deletion_removes_gmail_credential_access(monkeypatch, tmp_path):
    import backend.privacy as privacy
    connect(monkeypatch)
    assert _stored(), 'the connect step must have stored a credential'
    monkeypatch.setattr(privacy, 'DATA', tmp_path)
    monkeypatch.setattr(privacy, 'delete_credential', lambda name: None)
    result = privacy.delete_data(privacy.DeleteRequest(
        scope='all', confirmation='DELETE ALL LOCAL DATA'))
    assert result['deleted'] == 'all'
    assert _stored() == {}, 'Delete All Local Data removes Gmail credentials'
    assert _rows() == []


def test_disconnect_is_not_a_data_erasure(monkeypatch):
    """Disconnect removes credential access and sync state, nothing else."""
    from backend.models import Application, Job
    with Session.begin() as db:
        job = Job(company='Synthetic Employer', title='Security Analyst')
        db.add(job)
        db.flush()
        db.add(Application(job_id=job.id, status='INTERVIEW',
                           tracking={'stage': 'INTERVIEW'}))
        job_id = job.id
    connect(monkeypatch)
    install_google_double(monkeypatch, revoke_status=200)
    accounts.disconnect('PRIMARY')
    with Session() as db:
        application = db.scalar(select(Application).where(Application.job_id == job_id))
        assert application.status == 'INTERVIEW'
        assert application.tracking == {'stage': 'INTERVIEW'}
    with Session.begin() as db:
        from sqlalchemy import delete
        db.execute(delete(Application).where(Application.job_id == job_id))
        db.execute(delete(Job).where(Job.id == job_id))


def test_the_client_secret_never_reaches_any_persisted_artifact(monkeypatch, tmp_path):
    """The full sweep, repeated specifically for the client credential."""
    import backend.models as models
    import backend.privacy as privacy
    import backend.reliability as reliability
    from backend.doctor import run_checks

    monkeypatch.setattr(models, 'DATA', tmp_path)
    session = connect(monkeypatch)
    assert session['accepted'] is True
    assert accounts.client_secret_status()['state'] == 'CONFIGURED'

    # Database bytes, including the WAL.
    assert_clean(_database_bytes(), 'the SQLite database')
    # Diagnostics.
    assert_clean(json.dumps(run_checks()), 'diagnostic output')
    # Security events written during a run that held a client secret.
    written = ''.join(path.read_text(encoding='utf-8', errors='replace')
                      for path in tmp_path.rglob('*') if path.is_file())
    assert written, 'the run must have recorded security events'
    assert_clean(written, 'the security-event file')
    # The private export.
    monkeypatch.setattr(privacy, 'DATA', tmp_path)
    assert_clean(privacy._export_data().body, 'the private export')
    # A daily backup.
    monkeypatch.setattr(reliability, 'DATA', tmp_path)
    name = reliability.backup_database(force=True)
    assert_clean((tmp_path / 'backups' / name).read_bytes(), 'a daily backup')
    # Whole-integration status and the setup command's own output.
    assert_clean(json.dumps(accounts.status()), 'the status payload')


def test_the_client_secret_is_absent_from_the_repository_and_git_history():
    """No fixture, test, doc or committed file may carry a real secret.

    The sentinel is synthetic, so finding it in the test files themselves
    is expected; what must not appear anywhere is a value shaped like a
    real Google client secret.
    """
    import re
    import subprocess
    root = __import__('pathlib').Path('.')
    # Google client secrets are conventionally prefixed GOCSPX-.
    pattern = re.compile(rb'GOCSPX-[A-Za-z0-9_-]{10,}')
    tracked = subprocess.check_output(['git', 'ls-files']).decode().split('\n')
    for relative in tracked:
        relative = relative.strip()
        if not relative:
            continue
        path = root / relative
        if path.is_file() and path.stat().st_size < 4_000_000:
            assert not pattern.search(path.read_bytes()), \
                f'a Google-shaped client secret appears in {relative}'
    # And nothing in the branch's own diff against master either.
    diff = subprocess.run(['git', 'diff', 'origin/master...HEAD'],
                          capture_output=True).stdout
    assert not pattern.search(diff)


def test_the_client_secret_is_never_exposed_through_the_api(monkeypatch, client):
    connect(monkeypatch)
    bodies = []
    for method, path in (('GET', '/api/gmail/status'),
                         ('GET', '/api/gmail/accounts/primary/authorize'),
                         ('GET', '/api/privacy'),
                         ('GET', '/api/privacy/self-check'),
                         ('GET', '/api/privacy/security-events')):
        response = client.request(method, path)
        bodies.append(response.text)
    joined = '\n'.join(bodies)
    assert_clean(joined, 'an API response body')
    # The status endpoint reports only bounded state for the secret.
    payload = client.get('/api/gmail/status').json()
    assert set(payload['client_secret']) <= {'state', 'detail_code', 'setup_command'}
    assert payload['client_secret']['state'] == 'CONFIGURED'


def test_no_frontend_file_can_hold_or_request_a_client_secret():
    """The secret is console-only: the UI never accepts or stores it."""
    import pathlib
    source = pathlib.Path('frontend/src/GmailConnection.tsx').read_text(encoding='utf-8')
    executable = __import__('re').sub(r'/\*[\s\S]*?\*/', '', source)
    executable = __import__('re').sub(r'^\s*//.*$', '', executable, flags=__import__('re').M)
    # It may render whether one is configured, but never a value or an input.
    assert 'client_secret?.state' in executable or 'client_secret' in executable
    for forbidden in ('type="password"', 'setSecret', 'client_secret:',
                      'localStorage', 'sessionStorage', 'indexedDB'):
        assert forbidden not in executable, \
            f'the Gmail panel must not contain {forbidden}'


def test_the_existing_openai_credential_path_is_unchanged(monkeypatch, gmail_env):
    import backend.privacy as privacy
    gmail_env.set_password('LocalJobHunter', 'openai', 'synthetic-openai-key-value')
    connect(monkeypatch)
    # A Gmail connect/disconnect cycle never touches the OpenAI entry.
    install_google_double(monkeypatch, revoke_status=200)
    accounts.disconnect('PRIMARY')
    assert gmail_env.get_password('LocalJobHunter', 'openai') == 'synthetic-openai-key-value'
    assert privacy.read_credential('openai') == 'synthetic-openai-key-value'
    assert accounts.CREDENTIAL_SERVICE != 'LocalJobHunter'
    accounts.delete_all_credentials()
    assert gmail_env.get_password('LocalJobHunter', 'openai') == 'synthetic-openai-key-value'


def test_oauth_attempts_are_memory_only_and_never_serialized(monkeypatch, tmp_path):
    import backend.models as models
    monkeypatch.setattr(models, 'DATA', tmp_path)
    attempt, _url = oauth.attempts.start('PRIMARY', lambda **kwargs: 'CONNECTED',
                                         listener_factory=FakeListener)
    state, verifier = attempt.state.reveal(), attempt.verifier.reveal()
    assert_clean(_database_bytes(), 'the database', extra=(state, verifier))
    written = ''.join(path.read_text(encoding='utf-8', errors='replace')
                      for path in tmp_path.rglob('*') if path.is_file())
    assert_clean(written, 'any file in the data directory', extra=(state, verifier))
    # No table anywhere models an OAuth attempt.
    assert 'oauth' not in ' '.join(models.Base.metadata.tables).lower()
    assert 'attempt' not in ' '.join(models.Base.metadata.tables).lower()


def _stored():
    from backend.privacy import credential_backend
    return {name: value for (service, name), value in credential_backend().store.items()
            if service == accounts.CREDENTIAL_SERVICE}

"""Non-retention, boundaries and transport tests using fictional messages only."""
import ast
import gzip
import io
import json
import logging
from pathlib import Path
import ssl
import time
import traceback
import zipfile

import httpx
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from backend import gmail_accounts as accounts, gmail_oauth as oauth
from backend import gmail_messages as messages, gmail_sync as sync
from backend.models import Session, engine, Application
from tests.gmail_fixtures import gmail_env, keyring_backend, SENTINEL_ACCESS, SENTINEL_REFRESH
from tests.gmail_confirmation_fixtures import message, BODY_SENTINEL, HTML_SENTINEL, RAW_SENTINEL, AUTH_SENTINEL
from tests.test_gmail_sync import clean_confirmations, connect, install_messages, mock_transport

pytestmark = pytest.mark.usefixtures('gmail_env', 'clean_confirmations', 'no_unexpected_network')
FORBIDDEN = (BODY_SENTINEL, HTML_SENTINEL, RAW_SENTINEL, AUTH_SENTINEL, SENTINEL_ACCESS, SENTINEL_REFRESH)


def clean(blob):
    if not isinstance(blob, bytes): blob = str(blob).encode()
    for sentinel in FORBIDDEN:
        assert sentinel.encode() not in blob


def test_nonretention_across_storage_and_public_outputs(monkeypatch,tmp_path,caplog,capsys):
    from backend import main, privacy, reliability, doctor, models
    caplog.set_level(logging.DEBUG)
    for module in (privacy,reliability,models): monkeypatch.setattr(module,'DATA',tmp_path)
    connect(monkeypatch)
    install_messages(monkeypatch,{'a1':message()})
    with Session() as db:
        before = [dict(row) for row in db.execute(select(Application.__table__)).mappings()]
    result = sync.sync_account()
    assert result['confirmations_recorded'] == 1
    with Session() as db:
        assert [dict(row) for row in db.execute(select(Application.__table__)).mappings()] == before
    # Inspect live SQLite sidecars BEFORE checkpoint as well as after it.
    for suffix in ('','-wal','-shm','-journal'):
        path = Path(engine.url.database+suffix)
        if path.exists(): clean(path.read_bytes())
    exported = privacy._export_data()
    with zipfile.ZipFile(io.BytesIO(exported.body)) as archive:
        records = json.loads(archive.read('records.json'))
        assert records['gmail_confirmations'][0]['gmail_message_id'] == 'a1'
        for name in archive.namelist(): clean(archive.read(name))
    backup = reliability.backup_database(force=True)
    clean((tmp_path/'backups'/backup).read_bytes())
    clean(doctor.run_checks())
    with TestClient(main.app) as client:
        for path in ('/api/gmail/confirmations','/api/gmail/sync/status','/api/privacy/security-events'):
            response = client.get(path)
            assert response.status_code == 200 and response.headers['cache-control']=='no-store'
            clean(response.content)
    clean(result)
    clean(caplog.text)
    clean(capsys.readouterr())
    for path in tmp_path.rglob('*'):
        if path.is_file(): clean(path.read_bytes())
    clean(sync.list_confirmations())
    # Account identity is permitted only in #44 connection metadata, never
    # in #45 evidence rows or summaries.
    assert 'tester@example.com' not in json.dumps(sync.list_confirmations())


def test_no_body_or_auth_columns_and_unique_message_constraint():
    from sqlalchemy import inspect
    sync.initialize_sync_schema()
    sync.initialize_sync_schema()
    columns = {c['name'] for c in inspect(engine).get_columns('gmail_confirmations')}
    assert columns == {'id','created_at','updated_at','account_slot','gmail_account_id',
        'gmail_message_id','sender','subject','received_at','detected_company','detected_role',
        'detected_state','confidence','parser_id','evidence_signals','application_url'}
    indexes = inspect(engine).get_indexes('gmail_confirmations')
    assert any(i['unique'] and i['column_names']==['gmail_account_id','gmail_message_id'] for i in indexes)


def test_disconnect_preserves_evidence_but_full_erase_removes_it(monkeypatch,tmp_path):
    from backend import privacy
    connect(monkeypatch)
    install_messages(monkeypatch,{'a1':message()})
    sync.sync_account()
    old_account = sync.list_confirmations()['confirmations'][0]['gmail_account_id']
    accounts.disconnect('PRIMARY')
    assert sync.list_confirmations()['count'] == 1
    assert not accounts.read_sync_state('PRIMARY')
    connect(monkeypatch)
    sync.sync_account()
    identities = {r['gmail_account_id'] for r in sync.list_confirmations()['confirmations']}
    assert len(identities)==2 and old_account in identities
    monkeypatch.setattr(privacy,'DATA',tmp_path)
    privacy.delete_data(privacy.DeleteRequest(scope='all',confirmation='DELETE ALL LOCAL DATA'))
    assert sync.list_confirmations()['count']==0


@pytest.mark.parametrize('path', ['/api/gmail/sync/status','/api/gmail/confirmations','/api/gmail/accounts/primary/sync'])
@pytest.mark.parametrize('headers', [{'origin':'https://evil.example'}, {'sec-fetch-site':'cross-site'}, {'host':'evil.example'}, {'sec-fetch-dest':'document'}])
def test_new_routes_inherit_browser_guards(path,headers):
    from backend.main import app
    with TestClient(app) as client:
        response = client.post(path,json={},headers=headers) if path.endswith('/sync') else client.get(path,headers=headers)
        assert response.status_code in (400,403)


def test_sync_api_and_account_gate(monkeypatch):
    from backend.main import app
    connect(monkeypatch)
    install_messages(monkeypatch,{'a1':message()})
    with TestClient(app) as client:
        assert client.get('/api/gmail/accounts/primary/sync').status_code in (404,405)
        assert client.post('/api/gmail/accounts/secondary/sync',json={}).json()['code']=='SECONDARY_NOT_ENABLED'
        response=client.post('/api/gmail/accounts/primary/sync',json={})
        assert response.status_code==200 and response.json()['confirmations_recorded']==1
        assert client.get('/api/gmail/confirmations?limit=201').status_code==422
        assert client.get('/api/gmail/confirmations?limit=1').json()['count']==1
        monkeypatch.setenv('APP_TOKEN','fictional-access-key')
        assert client.get('/api/gmail/confirmations').status_code==401
        monkeypatch.setenv('ASTRA_DEMO_ONLY','1')
        assert client.get('/api/gmail/sync/status').status_code==404


@pytest.mark.parametrize('compressed', [False,True])
def test_wire_and_decoded_caps_and_error_privacy(monkeypatch,compressed,caplog):
    caplog.set_level(logging.DEBUG)
    payload = ('{"body":"'+BODY_SENTINEL+'x'*messages.MAX_MESSAGE_RESPONSE_BYTES+'"}').encode()
    headers = {'content-type':'application/json'}
    if compressed:
        payload=gzip.compress(payload)
        headers['content-encoding']='gzip'
    mock_transport(monkeypatch,lambda req:httpx.Response(200,content=iter([payload]),headers=headers))
    with pytest.raises(messages.GmailReadError) as caught:
        messages.fetch_message(oauth.Secret(SENTINEL_ACCESS),'a1')
    assert caught.value.code=='GMAIL_MESSAGE_TOO_LARGE'
    clean(''.join(traceback.format_exception(caught.value)))
    clean(caplog.text)


def test_transport_debug_headers_suppressed_only_during_request(monkeypatch,caplog):
    caplog.set_level(logging.DEBUG)
    def handler(req):
        logging.getLogger('httpcore.http11').debug('response headers %s',BODY_SENTINEL)
        return httpx.Response(200,content=iter([json.dumps(message()).encode()]),headers={'content-type':'application/json'})
    mock_transport(monkeypatch,handler)
    messages.fetch_message(oauth.Secret(SENTINEL_ACCESS),'a1')
    clean(caplog.text)
    logging.getLogger('httpcore.http11').debug('ordinary public trace')
    assert 'ordinary public trace' in caplog.text


def test_actual_dial_pinned_deadline_and_tls(monkeypatch):
    from backend.job_providers import transport
    calls = []
    class Socket:
        def getpeername(self): return ('8.8.8.8',443)
    class Stream:
        def get_extra_info(self,name): return Socket()
        def close(self): pass
    backend = oauth._FixedHostBackend(transport.Budget(1))
    monkeypatch.setattr(transport,'_resolve_and_pin',lambda host,port,timeout: calls.append(('resolve',host,timeout)) or '8.8.8.8')
    monkeypatch.setattr(backend._inner,'connect_tcp',lambda host,port,**kw:calls.append(('dial',host,kw['timeout'])) or Stream())
    stream = backend.connect_tcp('gmail.googleapis.com',443)
    assert calls[0][1]=='gmail.googleapis.com' and calls[1][1]=='8.8.8.8'
    assert 0 < calls[1][2] <= 1 and isinstance(stream,transport._DeadlineStream)
    client=oauth._client(1)
    try:
        assert client.trust_env is False and client.follow_redirects is False
        context=client._transport._pool._ssl_context
        assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
    finally: client.close()


def test_no_message_mutation_or_content_io_capabilities():
    tree=ast.parse(Path('backend/gmail_messages.py').read_text())
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='_request']
    assert len(calls)==1 and calls[0].args[0].value=='GET'
    for filename in ('gmail_content.py','gmail_confirmations.py'):
        source=ast.parse(Path('backend',filename).read_text(encoding='utf-8'))
        imports={node.names[0].name.split('.')[0] for node in ast.walk(source) if isinstance(node,ast.Import)}
        assert not imports & {'httpx','requests','socket','subprocess','openai'}


def test_parser_failure_is_counted_without_exception_or_content_leak(monkeypatch,caplog):
    connect(monkeypatch)
    install_messages(monkeypatch,{'a1':message()})
    def fail(**kw): raise RuntimeError(BODY_SENTINEL)
    monkeypatch.setattr(sync.confirmations,'parse',fail)
    result=sync.sync_account()
    assert result['messages_skipped_unreadable']==1 and result['confirmations_recorded']==0
    clean(result)
    clean(caplog.text)


def test_mailbox_tls_cannot_write_session_keys_from_environment(monkeypatch, tmp_path):
    destination = tmp_path / 'forbidden-session-keys.log'
    monkeypatch.setenv('SSLKEYLOGFILE', str(destination))
    with oauth._client(1) as client:
        context = client._transport._pool._ssl_context
        assert context.keylog_filename is None
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert not destination.exists()


@pytest.mark.parametrize('route', ['sync', 'confirmations', 'status'])
def test_storage_failures_never_reach_generic_traceback_log(monkeypatch, caplog, route):
    from backend.main import app
    connect(monkeypatch)
    install_messages(monkeypatch, {'a1': message()})
    def broken(*args, **kwargs):
        raise RuntimeError(BODY_SENTINEL + ' private-address@example.com')
    with TestClient(app) as client:
        if route == 'sync':
            monkeypatch.setattr(sync, '_store', broken)
            response = client.post('/api/gmail/accounts/primary/sync', json={})
        else:
            monkeypatch.setattr(sync, 'list_confirmations' if route == 'confirmations' else 'sync_status', broken)
            response = client.get('/api/gmail/confirmations' if route == 'confirmations' else '/api/gmail/sync/status')
        assert response.json()['code'] == 'GMAIL_SYNC_FAILED'
        clean(response.content)
        clean(caplog.text)
        assert 'private-address@example.com' not in caplog.text + response.text

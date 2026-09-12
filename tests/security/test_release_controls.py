import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import pytest

@pytest.fixture
def usage(tmp_path, monkeypatch):
    import backend.ai_usage as module
    from backend.models import initialize
    initialize()
    monkeypatch.setattr(module, 'DATA', tmp_path)
    return module

def test_ai_limit_failure_restart_and_rollover(usage, monkeypatch):
    for i in range(20):
        with pytest.raises(RuntimeError):
            with usage.reserve('synthetic', {}):
                raise RuntimeError('provider failed')
        with usage.connect() as c: c.execute('DELETE FROM lease')
    with pytest.raises(ValueError, match='limit reached'):
        with usage.reserve('synthetic', {}): pass
    import importlib
    # A new connection reads the persisted counter, as a restarted process does.
    assert usage.snapshot()['requests'] == 20
    monkeypatch.setattr(usage,'day',lambda:'2099-01-02')
    with usage.reserve('synthetic', {}) as date:
        usage.record_tokens(date, {'prompt_tokens':12,'completion_tokens':4})
    assert usage.snapshot()['requests'] == 1
    assert usage.snapshot()['input_tokens'] == 12

def test_ai_concurrency_and_duplicate_click(usage):
    # Warm schema before competing across independent SQLite connections.
    usage.snapshot()
    def attempt(_):
        try:
            with usage.reserve('synthetic', {}): return True
        except ValueError: return False
    with ThreadPoolExecutor(max_workers=5) as pool:
        assert sum(pool.map(attempt,range(5))) == 1
    assert usage.snapshot()['requests'] == 1

def test_ai_oversized_and_disabled_do_not_spend(usage):
    from backend.providers import RuleBasedProvider, OpenAIProvider
    with pytest.raises(ValueError):
        with usage.reserve('x'*40001, {}): pass
    with pytest.raises(ValueError): OpenAIProvider().advise('job',{})
    RuleBasedProvider().advise('job',{})
    assert usage.snapshot()['requests'] == 0

def test_telemetry_never_retains_free_text_and_rotates(tmp_path, monkeypatch):
    import backend.models as models
    import backend.security_events as events
    monkeypatch.setattr(models,'DATA',tmp_path)
    monkeypatch.setattr(events,'MAX_BYTES',300)
    private='person@example.com secret CV content'
    for _ in range(10): events.record('UPLOAD_REJECTED',private,filename=private,path=private,authorization=private)
    assert (tmp_path/'security-events.log.1').exists()
    assert private not in ''.join(p.read_text() for p in tmp_path.iterdir())
    assert len(events.tail(2)) <= 2

def test_managed_files_accept_telemetry(tmp_path, monkeypatch):
    import backend.privacy as privacy
    monkeypatch.setattr(privacy,'DATA',tmp_path)
    for name in ('security-events.log','security-events.log.1','ai-usage.db'):
        (tmp_path/name).write_text('synthetic')
    assert len(privacy.managed_files()) == 3

def test_parser_memory_limit_runs_in_child():
    result=subprocess.run([sys.executable,'-c',
        'from backend.pdf_worker import limit_memory; h=limit_memory(); x=bytearray(900*1024*1024)'],
        capture_output=True,timeout=25)
    assert result.returncode != 0
    assert b'MemoryError' in result.stderr

def test_redirect_private_destination_never_requested(monkeypatch):
    import httpx
    import backend.adapters as adapters
    monkeypatch.setattr('socket.getaddrinfo',lambda host,*_: [(2,1,6,'',('127.0.0.1' if host=='127.0.0.1' else '8.8.8.8',443))])
    requests=[]
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(302,headers={'location':'http://127.0.0.1/private'})
    original=httpx.Client
    monkeypatch.setattr(adapters.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(ValueError,match='Private network'): adapters.fetch('https://example.com/job')
    assert requests == ['https://example.com/job']

def test_demo_only_denies_every_private_route(tmp_path):
    import os
    script='''
from fastapi.testclient import TestClient
from backend.main import app
with TestClient(app) as c:
    for route in ('/api/profile','/api/jobs','/api/applications','/api/settings','/api/privacy/export','/api/privacy/security-events','/api/files/tracker.xlsx','/api/files/backups/private.db'):
        assert c.get(route).status_code == 404, route
    assert c.put('/api/privacy/credentials/openai',json={'key':'synthetic'}).status_code == 404
'''
    env={**os.environ,'ASTRA_DEMO_ONLY':'1','HUNTER_DATA_DIR':str(tmp_path),'DATABASE_URL':'sqlite:///'+str(tmp_path/'demo.db')}
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert not (tmp_path/'demo.db').exists()

"""Candidate boundary verification against disposable application storage."""
import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path
import pytest
from backend.document_security import validate_document
from backend.policy import validate_url


def test_runtime_tls_context():
    import ssl
    from httpx import create_ssl_context
    context=create_ssl_context(trust_env=False)
    assert context.minimum_version>=ssl.TLSVersion.TLSv1_2
    assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
    assert ssl.HAS_TLSv1_3


@pytest.mark.parametrize('url', ['http://example.com/', 'https://example.com:80/'])
def test_external_transport_rejects_plaintext_before_dns(url, monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo', lambda *a: pytest.fail('DNS must not run'))
    with pytest.raises(ValueError): validate_url(url)


@pytest.mark.parametrize('encoding', ['utf-8','utf-16','utf-32'])
def test_workbook_entity_declarations_cannot_hide_in_unicode(encoding):
    data=io.BytesIO()
    xml='<!DOCTYPE x [<!ENTITY e SYSTEM "file:///synthetic-fixture">]><x>&e;</x>'
    with zipfile.ZipFile(data,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('xl/workbook.xml',xml.encode(encoding))
    with pytest.raises(ValueError):validate_document(data.getvalue(),'fixture.xlsx','xlsx')


HARNESS = r'''
import os
from fastapi.testclient import TestClient
from backend.main import app
from backend.access import sessions
key='synthetic-fixture-access-key-not-a-real-secret'
with TestClient(app) as c:
    assert c.get('/api/access').json()=={'required':True}
    assert c.get('/api/jobs').status_code==401
    assert c.get('/api/jobs',headers={'Authorization':'Bearer '+key}).status_code==401
    assert c.post('/api/access',json={'key':key},headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post('/api/access',json={'key':key},headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert c.get('/api/access',params={'key':key}).json()=={'required':True}
    r=c.post('/api/access',json={'key':key}); assert r.status_code==200
    token=r.json()['token']; headers={'Authorization':'Bearer '+token}
    assert c.get('/api/jobs',headers=headers).status_code==200
    assert key not in r.text
    r=c.post('/api/access/lock',headers=headers,json={})
    assert r.status_code==200 and 'storage' in r.headers['clear-site-data']
    assert c.get('/api/jobs',headers=headers).status_code==401
    responses=[c.get('/api/jobs'),c.get('/api/health',headers={'Host':'evil.example'}),c.get('/api/access',headers={'Origin':'https://evil.example'}),c.post('/api/access',content='x',headers={'Content-Type':'text/plain'})]
    for r in responses:
        assert r.headers['cache-control']=='no-store'
        assert r.headers['x-content-type-options']=='nosniff'
        assert "frame-ancestors 'none'" in r.headers['content-security-policy']
        assert r.headers['content-type'].startswith(('application/json','text/plain'))
    for destination in ('document','image','iframe','script'):
        assert c.get('/api/jobs',headers={**headers,'Sec-Fetch-Dest':destination}).status_code==403
    fresh=c.post('/api/access',json={'key':key}).json()['token']
    auth={'Authorization':'Bearer '+fresh}
    for destination in ('document','image','iframe','script'):
        assert c.get('/api/jobs',headers={**auth,'Sec-Fetch-Dest':destination}).status_code==403
    for path in ('/.git/config','/.env','/backend/main.py'):
        assert c.get(path).status_code==404
    for _ in range(5):assert c.post('/api/access',json={'key':'wrong'}).status_code==401
    r=c.post('/api/access',json={'key':key})
    assert r.status_code==429 and int(r.headers['retry-after'])<=61
    os.environ['ASTRA_DEMO_ONLY']='1'
    assert c.get('/api/access').status_code==404
    assert c.post('/api/access',json={'key':key}).status_code==404
print('Access exchange, revocation, throttling, headers and demo boundary passed')
'''


def test_access_http_contract(tmp_path):
    env={**os.environ,'HUNTER_DATA_DIR':str(tmp_path/'data'),
         'DATABASE_URL':'sqlite:///'+str(tmp_path/'test.db'),
         'APP_TOKEN':'synthetic-fixture-access-key-not-a-real-secret',
         'PYTHONPATH':str(Path(__file__).resolve().parents[2])}
    result=subprocess.run([sys.executable,'-c',HARNESS],env=env,text=True,capture_output=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('changes',[
    {'minimum_score':-1},{'high_priority':101},{'followup_days':-1},
    {'wizard_step':100},{'target_roles':['x'*501]},{'discovery_enabled':'true'},
    {'schedule':{}},{'weights':{'skills':float('nan')}},
])
def test_security_settings_reject_invalid_decision_inputs(changes):
    from backend.input_rules import settings_input
    from backend.models import DEFAULTS
    with pytest.raises(ValueError):settings_input({**DEFAULTS,**changes},DEFAULTS)


@pytest.mark.parametrize('kind,data',[
    ('sources',{'name':'Fixture','adapter':'untrusted'}),
    ('sources',{'name':'Fixture','enabled':'yes'}),
    ('sources',{'name':'Fixture','url':'javascript:alert(1)'}),
    ('answers',{'question':'Fixture','approved':'true'}),
    ('interviews',{'application_id':-1,'date':'2026-09-12'}),
    ('interviews',{'application_id':1,'date':'invalid'}),
    ('followups',{'application_id':1,'due_date':'invalid'}),
])
def test_legacy_record_inputs_cannot_bypass_validation(kind,data):
    from backend.input_rules import record_input
    from backend.main import COLLECTIONS
    with pytest.raises(ValueError):record_input(kind,data,COLLECTIONS[kind])

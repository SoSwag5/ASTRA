import os,subprocess,sys

def test_isolated_api_workflow(tmp_path):
    script=r'''
from fastapi.testclient import TestClient
from backend.main import app
with TestClient(app) as c:
    assert c.get('/api/health').status_code==200
    assert c.get('/api/settings').json()['dry_run'] is True
    assert c.put('/api/settings',json={'autopilot':'INVALID'}).status_code==400
    assert c.post('/api/jobs',json={'company':'Synthetic','title':'SOC Analyst','description':'SOC monitoring','location':'Dubai'}).status_code==200
    assert len(c.get('/api/jobs').json())==1
    assert c.post('/api/import/url',json={'url':'https://linkedin.com/jobs/1'}).status_code==400
    assert c.get('/api/settings',headers={'Origin':'https://malicious.invalid'}).status_code==403
    assert c.get('/api/files/../.env').status_code==404
'''
    env={**os.environ,'DATABASE_URL':f'sqlite:///{tmp_path / "test.db"}','APP_TOKEN':''}
    result=subprocess.run([sys.executable,'-c',script],env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr

def test_offline_rehearsal():
    from backend.rehearsal import rehearse
    result=rehearse()
    assert result['ok'] and not result['submitted'] and result['external_requests']==0

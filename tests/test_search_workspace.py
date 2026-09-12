import os,subprocess,sys

def test_discovery_and_tracking(tmp_path):
    script=r'''
from fastapi.testclient import TestClient
from sqlalchemy import select
import backend.main as main
from backend.models import *
with TestClient(main.app) as c:
    with Session.begin() as db:
        db.add(CandidateProfile(raw_text='Computer Science SOC SIEM Python Linux',confirmed=True))
    assert c.put('/api/settings',json={'discovery_interval_hours':1}).status_code==400
    assert c.put('/api/settings',json={'discovery_interval_hours':6}).status_code==200
    assert c.post('/api/search/sources',json={'name':'Bad','url':'https://localhost/feed'}).status_code==400
    source=c.post('/api/search/sources',json={'name':'Fixture','url':'https://jobs.lever.co/fixture'}).json()
    assert source['enabled']
    assert c.post('/api/search/sources',json={'name':'Fixture','url':'https://jobs.lever.co/fixture'}).json()['exists']
    assert len(c.get('/api/search/overview').json()['sources'])==1
    main.discover=lambda *args:[{'company':'Fixture','title':'SOC Analyst','location':'Dubai','description':'SOC SIEM Python','source':'Lever','source_job_id':'fixture1','job_url':'https://jobs.lever.co/fixture/one'}, {'company':'Fixture','title':'Accountant','location':'Dubai'}]
    r=main.task('discover')
    assert r['report']['discovered']==1 and r['report']['filtered']==1
    job=c.get('/api/jobs').json()[0]
    assert job['match_score']>0 and job['analysis']['discovery']['source_id']==source['id']
    assert c.post(f"/api/search/jobs/{job['id']}/save",json={'saved':True}).status_code==200
    assert c.post(f"/api/jobs/{job['id']}/analyze").status_code==200
    assert c.get('/api/jobs').json()[0]['analysis']['saved']
    app=c.post(f"/api/jobs/{job['id']}/status",json={'status':'APPLIED'}).json()
    r=main.task('discover')
    assert r['report']['duplicates']==1 and r['report']['discovered']==0
    assert c.get('/api/jobs').json()[0]['status']=='APPLIED'
    assert c.get('/api/search/overview').json()['sources'][0]['result']['duplicates']==1
    assert c.post(f"/api/search/jobs/{job['id']}/notes",json={'notes':'Contact next week'}).status_code==200
    assert c.post(f"/api/search/tracking/{app['id']}/followup",json={'due_date':'2020-01-01T09:00:00+04:00'}).status_code==200
    tracked=c.get('/api/search/tracking').json()[0]
    assert tracked['due'] and tracked['job']['notes']=='Contact next week'
    assert c.post(f"/api/search/tracking/{app['id']}/followup",json={'due_date':'not a date'}).status_code==400
    assert c.post(f"/api/search/tracking/{app['id']}/followup",json={'due_date':'2020-01-01','done':True}).status_code==200
    assert not c.get('/api/search/tracking').json()[0]['due']
    def broken(*args): raise ValueError('Source unavailable')
    main.discover=broken
    r=main.task('discover')
    assert r['status']=='PARTIAL' and r['report']['failures']==1
    assert c.get('/api/jobs').json()[0]['status']=='APPLIED'
    assert c.put('/api/settings',json={'discovery_enabled':False}).status_code==200
    assert c.get('/api/search/overview').json()['next_scan'] is None
'''
    env={**os.environ,'DATABASE_URL':f'sqlite:///{tmp_path / "workspace.db"}','APP_TOKEN':''}
    result=subprocess.run([sys.executable,'-c',script],env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr

def test_lever_multiple_locations(monkeypatch):
    from backend import adapters
    from backend.discovery import discovery_reason
    from backend.models import DEFAULTS
    class Response:
        def json(self): return [{'id':'1','text':'SOC Analyst','hostedUrl':'https://jobs.lever.co/example/1','categories':{'location':'Singapore','allLocations':['Singapore','UAE, Dubai']},'createdAt':1700000000000,'workplaceType':'remote'}]
    monkeypatch.setattr(adapters,'fetch',lambda url:Response())
    job=adapters.discover('lever','example')[0]
    assert 'Dubai' in job['location'] and discovery_reason(job,DEFAULTS) is None
    assert job['date_posted'] and job['remote_status']=='remote'

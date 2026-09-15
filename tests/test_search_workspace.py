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
    # Issue #41 Owner Decision 1: 'Accountant' is a structurally valid
    # posting that is hard-rejected (DOMAIN_INCOMPATIBLE) but still
    # persisted (hidden via the existing SKIP status), not silently
    # filtered before persistence -- so both items are discovered here, and
    # both carry a real native id (as any genuine Lever posting would) so
    # they are correctly recognized as duplicates on the rescan below.
    main.discover=lambda *args:[{'company':'Fixture','title':'SOC Analyst','location':'Dubai','description':'SOC SIEM Python','source':'Lever','source_job_id':'fixture1','job_url':'https://jobs.lever.co/fixture/one'}, {'company':'Fixture','title':'Accountant','location':'Dubai','source':'Lever','source_job_id':'fixture2','job_url':'https://jobs.lever.co/fixture/two'}]
    r=main.task('discover')
    assert r['report']['discovered']==2 and r['report']['filtered']==0
    jobs=c.get('/api/jobs').json()
    job=next(j for j in jobs if j['title']=='SOC Analyst')
    rejected=next(j for j in jobs if j['title']=='Accountant')
    assert job['match_score']>0 and job['analysis']['discovery']['source_id']==source['id']
    assert rejected['status']=='SKIP' and rejected['analysis']['fit_assessment']['hard_reject']['code']=='DOMAIN_INCOMPATIBLE'
    assert c.post(f"/api/search/jobs/{job['id']}/save",json={'saved':True}).status_code==200
    assert c.post(f"/api/jobs/{job['id']}/analyze").status_code==200
    assert next(j for j in c.get('/api/jobs').json() if j['id']==job['id'])['analysis']['saved']
    app=c.post(f"/api/jobs/{job['id']}/status",json={'status':'APPLIED'}).json()
    r=main.task('discover')
    assert r['report']['duplicates']==2 and r['report']['discovered']==0
    assert next(j for j in c.get('/api/jobs').json() if j['id']==job['id'])['status']=='APPLIED'
    assert c.get('/api/search/overview').json()['sources'][0]['result']['duplicates']==2
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
    assert next(j for j in c.get('/api/jobs').json() if j['id']==job['id'])['status']=='APPLIED'
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
    import backend.job_providers.lever as lever_mod
    # Issue #39: Lever discovery moved from adapters.fetch to the shared
    # job-provider transport (transport.fetch_json via lever.py), same as
    # Greenhouse's own migration required updating its equivalent test.
    payload = [{'id':'1','text':'SOC Analyst','hostedUrl':'https://jobs.lever.co/example/1','categories':{'location':'Singapore','allLocations':['Singapore','UAE, Dubai']},'createdAt':1700000000000,'workplaceType':'remote'}]
    monkeypatch.setattr(lever_mod,'fetch_json',lambda url,budget,**kw:payload)
    job=adapters.discover('lever','example')[0]
    assert 'Dubai' in job['location'] and discovery_reason(job,DEFAULTS) is None
    # Codex remediation round, finding 5: createdAt is undocumented by
    # Lever, so it is never promoted to the authoritative date_posted.
    assert job['date_posted']=='' and job['remote_status']=='remote'

import pytest
from datetime import datetime,timezone
from backend.recall import evaluate,experience,role,funnel,eligibility
from backend.models import DEFAULTS
P={'raw_text':'SOC SIEM Linux Python Splunk security monitoring risk assessment vulnerability network security incident response','declarations':{}}
def job(**kw):return {'title':'SOC Analyst L1','company':'Synthetic','location':'Dubai','description':'SOC SIEM Linux security monitoring','job_url':'https://example.com/job',**kw}
@pytest.mark.parametrize('text,minimum,maximum,preferred',[
 ('0-2 years experience',0,2,False),('1–3 years of experience',1,3,False),('3+ years required',3,None,False),('5 to 8 years experience',5,8,False),('5 years experience preferred',0,None,True),('Our company has 20 years of experience. Candidates need 1 year experience',1,None,False)])
def test_experience_evidence(text,minimum,maximum,preferred):
 r=experience(text);assert r['minimum']==minimum;assert r['requirements'][-1]['maximum']==maximum;assert r['requirements'][-1]['preferred']==preferred
@pytest.mark.parametrize('title',['SOC Analyst L1','SIEM Analyst','IAM Analyst','PAM Analyst','IT Risk Analyst','Cyber Defence Analyst','Cyber Defense Analyst','DFIR Analyst','Junior Security Analyst','أخصائي أمن المعلومات','DevSecOps Engineer','Cyber Analytics Analyst','Detection Engineering Analyst'])
def test_role_family_synonyms(title):assert role(title)['kind']=='DIRECT'
@pytest.mark.parametrize('policy,years,excluded,band',[('STRICT',1,True,'EXCLUDED'),('BALANCED',1,False,'STRETCH'),('BALANCED',3,False,'STRETCH'),('BALANCED',5,True,'EXCLUDED'),('EXPLORATORY',4,False,'STRETCH'),('EXPLORATORY',8,True,'EXCLUDED')])
def test_policies(policy,years,excluded,band):
 r=evaluate(job(description=f'Minimum {years} years experience. SOC SIEM Linux'),{**DEFAULTS,'discovery_policy':policy},P);assert r['excluded']==excluded;assert r['fit_band']==band
@pytest.mark.parametrize('text',['UAE National only','Required Nationality: UAE Only','Emirati graduate','UAE citizens required'])
def test_unknown_citizenship_not_dropped(text):
 r=evaluate(job(description=text+'\nSOC SIEM'),DEFAULTS,P);assert not r['excluded'];assert r['eligibility']['state']=='UNKNOWN';assert r['fit_band']!='STRONG'
def test_explicit_eligibility_and_preference():
 p={**P,'declarations':{'uae_citizen':False,'uae_citizenship_confirmed':True}}
 assert evaluate(job(title='SOC Analyst UAE National'),DEFAULTS,p)['excluded']
 assert eligibility('All nationalities, priority for UAE nationals',p)['state']=='ELIGIBLE'
 assert eligibility('UAE nationals preferred',p)['state']=='ELIGIBLE'
 assert eligibility('UAE national only',{'declarations':{'uae_citizen':False}})['state']=='UNKNOWN'
@pytest.mark.parametrize('kwargs,code',[
 ({'location':'London'},'NON_UAE'),({'location':'United States - Remote'},'REMOTE_NOT_UAE_COMPATIBLE'),({'title':'Senior SOC Analyst'},'TOO_SENIOR'),({'title':'Staff Security Engineer'},'TOO_SENIOR'),({'title':'Security Guard'},'ROLE_NOT_RELEVANT'),({'title':'Backend Engineer'},'ROLE_NOT_RELEVANT'),({'closing_date':'2020-01-01'},'EXPIRED'),({'company':'Blocked'},'BLOCKED_COMPANY'),({'title':'Security Analyst sales'},'EXCLUDED_ROLE')])
def test_hard_exclusions(kwargs,code):
 r=evaluate(job(**kwargs),{**DEFAULTS,'blocked_companies':['Blocked']},P);assert code in [x['code'] for x in r['hard']];assert not r['near_miss']
def test_soft_near_miss_freshness_and_adjacent():
 d=evaluate(job(description='1-3 years experience. SOC SIEM Linux'),DEFAULTS,P);assert d['near_miss'] and d['fit_band']=='STRETCH'
 adjacent=evaluate(job(title='IT support',description='Responsible for SIEM and incident response'),DEFAULTS,P);assert adjacent['role']['kind']=='ADJACENT';assert adjacent['priority']<evaluate(job(),DEFAULTS,P)['priority']
 old=evaluate(job(date_posted='2020-01-01'),DEFAULTS,P);assert not old['excluded'] and not old['daily']
 future=evaluate(job(date_posted='2999-01-01'),DEFAULTS,P);assert future['freshness']=='DATE_UNKNOWN'
def test_funnel_partition():
 rows=[{'decision':evaluate(job(),DEFAULTS,P),'disposition':'NEW'},{'decision':evaluate(job(title='Director SOC'),DEFAULTS,P),'disposition':'EXCLUDED'},{'decision':evaluate(job(),DEFAULTS,P),'disposition':'DUPLICATE','already_seen':True}]
 f=funnel(rows);c=f['counts'];assert c['plausible']+c['excluded']==c['fetched']==3;assert c['excluded']==sum(f['primary_exclusions'].values())==1;assert c['new']==c['duplicates']==c['already_seen']==1
 assert list(f['stages'].values())==sorted(f['stages'].values(),reverse=True)

def test_greenhouse_escaped_location_and_bounded_fallback(monkeypatch):
 import backend.adapters as a
 import backend.job_providers.greenhouse as gh
 from backend.job_providers.transport import TransportError
 import html
 calls=[]
 row={'id':123,'title':'Network Security Engineer','location':{'name':'Hybrid'},'absolute_url':'https://job-boards.greenhouse.io/example/jobs/123','updated_at':'2026-09-11'}
 def fetch_json(url,budget,**kw):
  calls.append(url)
  if url.endswith('?content=true'):raise TransportError('RESPONSE_TOO_LARGE','Response exceeded the size cap')
  if url.endswith('/123'):return {**row,'content':html.escape('<p>Available Locations: Lisbon, Portugal</p><p>SIEM security monitoring</p>')}
  return {'jobs':[row]}
 monkeypatch.setattr(gh,'fetch_json',fetch_json)
 result=a.discover('greenhouse','example')[0]
 assert result['location']=='Lisbon, Portugal / Hybrid'
 assert '<p>' not in result['description'] and not result['date_posted']
 assert evaluate(result,DEFAULTS,P)['excluded']
 assert len(calls)==3

def test_unquantified_professional_experience_is_not_strong():
 r=evaluate(job(title='SOC Security Engineer',description='SOC SIEM Linux. Production-quality scripts and hands-on experience required'),DEFAULTS,P)
 assert r['fit_band']=='POSSIBLE' and 'EXPERIENCE_SCOPE_UNKNOWN' in [x['code'] for x in r['soft']]

def test_marketing_data_years_and_mixed_preferred_requirements():
 assert experience('The platform leverages 15-years of behavioral data. BS plus 2 years experience')['minimum']==2
 parsed=experience('More than 6 years of application security experience, more than 10 years is preferred')
 assert parsed['minimum']==6 and parsed['preferred_minimum']==10

def test_general_nationality_and_unknown_office_location():
 assert eligibility('Nationality\nSri Lankan, Any Arab National',P)['state']=='UNKNOWN'
 r=evaluate(job(location='In-Office'),DEFAULTS,P)
 assert not r['excluded'] and r['fit_band']=='POSSIBLE'

@pytest.mark.parametrize('location',['Sharjah','Ajman','Ras Al Khaimah','Fujairah','Umm Al Quwain','Al Ain','Abu Dhabi Emirate'])
def test_secondary_emirates_are_not_excluded(location):
 r=evaluate(job(location=location),DEFAULTS,P);assert r['uae'] and not r['excluded']

def test_failed_source_audits_every_row_and_rolls_back(tmp_path):
 from tests.test_campaign_reliability import isolated
 isolated(tmp_path,r'''
from backend.models import *
import backend.main as m
from backend.recall_api import overview
initialize()
with Session.begin() as db:db.add(JobSource(name='Synthetic failure',adapter='lever',board='fixture',enabled=True))
m.discover=lambda *args:[{'title':'SOC Analyst','location':'Dubai','description':'SIEM','job_url':'https://example.com/1'},{'title':'SOC Analyst','location':'Dubai','description':'SIEM','job_url':'file://invalid'},{'title':'Director SOC','location':'Dubai','description':'10 years experience'}]
r=m.task('discover');assert r['status']=='PARTIAL',r
assert r['report']['funnel']['counts']['fetched']==3
assert r['report']['funnel']['counts']['new']==0
assert [x['disposition'] for x in r['report']['decisions']]==['SOURCE_ERROR','SOURCE_ERROR','EXCLUDED']
with Session() as db:assert db.query(Job).count()==db.query(Application).count()==0
score=overview()['scorecards'][0];assert score['health']=='ERROR' and score['error_runs']==1
''')

def test_backpack_pause_idempotence_and_no_applications(tmp_path):
 from tests.test_campaign_reliability import isolated
 isolated(tmp_path,r'''
from backend.models import *
from scripts.migrate_recall import migrate
initialize()
with Session.begin() as db:db.add(JobSource(name='Backpack',adapter='ashby',board='backpack',enabled=True))
migrate();migrate()
with Session() as db:
 b=db.query(JobSource).filter_by(board='backpack').one();assert not b.enabled and b.details['disposition']=='PAUSED_NOT_FOUND'
 assert db.query(JobSource).filter_by(board='cloudflare').count()==1
 assert db.query(Job).count()==db.query(Application).count()==0
''')

def test_app_catchup_and_headless_offline_pause(tmp_path):
 from tests.test_campaign_reliability import isolated
 isolated(tmp_path,r'''
from backend.models import *
from datetime import datetime,timedelta,timezone
import backend.main as m
import sys
from scripts.discovery_once import main
initialize()
old=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
with Session.begin() as db:
 cfg=db.get(Settings,1);cfg.value={**cfg.value,'discovery_enabled':True,'autopilot':'REVIEW_FIRST','discovery_interval_hours':6}
 db.add(AutomationRun(task='discover',status='COMPLETED',report={'source_id':None},updated_at=old))
calls=[];m.task=lambda *args,**kwargs:calls.append(kwargs)
m.scheduled('discover');assert len(calls)==1 and calls[0]['trigger']=='CATCHUP'
with Session.begin() as db:
 cfg=db.get(Settings,1);cfg.value={**cfg.value,'discovery_enabled':False}
sys.argv=['discovery_once.py'];assert main()==0
assert len(calls)==1
''')

def test_schedule_is_visible_opt_in_and_never_wakes_pc():
 from pathlib import Path
 text=(Path(__file__).parents[1]/'scripts/schedule-discovery.ps1').read_text(encoding='utf-8-sig')
 for required in ['-StartWhenAvailable','-RunOnlyIfNetworkAvailable','IgnoreNew','WakeToRun=$false','-LogonType Interactive','-RunLevel Limited','Disable-ScheduledTask','Unregister-ScheduledTask','LastTaskResult','--trigger SCHEDULED']:
  assert required in text
 assert "if ($Action -eq 'Enable')" in text

def test_failed_task_keeps_history_and_releases_lock(tmp_path):
 from tests.test_campaign_reliability import isolated
 isolated(tmp_path,r'''
from backend.models import initialize
import backend.main as m
initialize()
r=m.task('invalid',trigger='MANUAL')
assert r['status']=='FAILED'
assert r['report']['trigger']=='MANUAL' and r['report']['started_at'] and r['report']['finished_at']
assert r['report']['duration_seconds']>=0 and not m.task_lock.locked()
''')

def test_headless_offline_run_has_meaningful_exit(tmp_path):
 from tests.test_campaign_reliability import isolated
 isolated(tmp_path,r'''
from backend.models import *
import backend.main as m
import scripts.discovery_once as h
import sys
initialize()
with Session.begin() as db:
 cfg=db.get(Settings,1);cfg.value={**cfg.value,'discovery_enabled':True,'autopilot':'PREPARE_ONLY'}
 db.add(JobSource(name='Offline fixture',adapter='lever',board='fixture',enabled=True))
def offline(*args):raise ConnectionError('Synthetic offline condition')
m.discover=offline
sys.argv=['discovery_once.py','--force','--trigger','MANUAL']
assert h.main()==2
with Session() as db:
 run=db.query(AutomationRun).one();assert run.status=='PARTIAL' and run.report['failures']==1
 assert run.report['sources_successful']==0 and run.report['submitted']==0
 assert db.query(Job).count()==db.query(Application).count()==0
assert not m.task_lock.locked()
''')

def test_isolated_flow_and_no_network_paste(tmp_path):
 from tests.test_campaign_reliability import isolated
 isolated(tmp_path,r'''
from fastapi.testclient import TestClient
from backend.main import app
import backend.main as m
from backend.models import *
from sqlalchemy import select
with TestClient(app) as c:
 with Session.begin() as db:
  db.add(CandidateProfile(name='Synthetic',raw_text='SOC SIEM Linux'))
  db.add(JobSource(name='Synthetic',adapter='lever',board='fixture',enabled=True))
 m.discover=lambda *args:[{'title':'SOC Analyst L1','company':'Synthetic','location':'Dubai','description':'1-3 years experience. SOC SIEM','job_url':'https://example.com/1'},{'title':'Director SOC','location':'Dubai','description':'10 years experience'}]
 run=m.task('discover');assert run['status']=='COMPLETED',run
 assert run['report']['funnel']['counts']['fetched']==2
 assert len(c.get('/api/recall').json()['near_misses'])==1
 assert len(c.get('/api/recall/audit/'+str(run['id'])).json()['rows'])==2
 assert c.post('/api/recall/paste-preview',json={'text':'Job title: SOC Analyst\nCompany: العربية\nLocation: Sharjah\nhttps://linkedin.com/jobs/1'}).json()['network_requests']==0
 jid=c.get('/api/jobs').json()[0]['id']
 assert c.post(f'/api/recall/jobs/{jid}/feedback',json={'decision':'NOT_FOR_ME','reason':'too senior'}).status_code==200
 assert c.get('/api/recall').json()['near_misses']==[]
 assert c.put('/api/recall/policy',json={'policy':'STRICT'}).status_code==200
 assert m.task('discover')['report']['discovered']==0
 with Session() as db:assert db.query(Application).count()==0
''')

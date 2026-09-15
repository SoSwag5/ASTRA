import pytest
from datetime import datetime,timezone
from backend.recall import evaluate,evaluate_legacy,experience,role,funnel,eligibility
from backend.models import DEFAULTS
P={'raw_text':'SOC SIEM Linux Python Splunk security monitoring risk assessment vulnerability network security incident response','declarations':{}}
def job(**kw):return {'title':'SOC Analyst L1','company':'Synthetic','location':'Dubai','description':'SOC SIEM Linux security monitoring','job_url':'https://example.com/job',**kw}
@pytest.mark.parametrize('text,minimum,maximum,preferred',[
 ('0-2 years experience',0,2,False),('1–3 years of experience',1,3,False),('3+ years required',3,None,False),('5 to 8 years experience',5,8,False),('5 years experience preferred',0,None,True),('Our company has 20 years of experience. Candidates need 1 year experience',1,None,False)])
def test_experience_evidence(text,minimum,maximum,preferred):
 r=experience(text);assert r['minimum']==minimum;assert r['requirements'][-1]['maximum']==maximum;assert r['requirements'][-1]['preferred']==preferred
@pytest.mark.parametrize('title',['SOC Analyst L1','SIEM Analyst','IAM Analyst','PAM Analyst','IT Risk Analyst','Cyber Defence Analyst','Cyber Defense Analyst','DFIR Analyst','Junior Security Analyst','أخصائي أمن المعلومات','DevSecOps Engineer','Cyber Analytics Analyst','Detection Engineering Analyst'])
def test_role_family_synonyms(title):assert role(title)['kind']=='DIRECT'
@pytest.mark.parametrize('policy,years',[('STRICT',1),('BALANCED',1),('BALANCED',3),('BALANCED',5),('EXPLORATORY',4),('EXPLORATORY',8)])
def test_policies_never_hard_reject_on_experience_alone(policy,years):
 """Issue #41 non-negotiable outcome: experience is a ranking signal, never
 a hard-rejection reason, regardless of policy or how large the gap is."""
 r=evaluate(job(description=f'Minimum {years} years experience. SOC SIEM Linux'),{**DEFAULTS,'discovery_policy':policy},P)
 assert not r['excluded'];assert r['fit_band']!='EXCLUDED'
@pytest.mark.parametrize('policy,years,excluded,band',[('STRICT',1,True,'EXCLUDED'),('BALANCED',1,False,'STRETCH'),('BALANCED',3,False,'STRETCH'),('BALANCED',5,True,'EXCLUDED'),('EXPLORATORY',4,False,'STRETCH'),('EXPLORATORY',8,True,'EXCLUDED')])
def test_policies_legacy_characterization(policy,years,excluded,band):
 """Documents the pre-#41 defect this issue retires: evaluate_legacy() hard-
 rejected a relevant posting purely for an experience gap under STRICT/
 BALANCED/EXPLORATORY policy. See test_policies_never_hard_reject_on_experience_alone."""
 r=evaluate_legacy(job(description=f'Minimum {years} years experience. SOC SIEM Linux'),{**DEFAULTS,'discovery_policy':policy},P);assert r['excluded']==excluded;assert r['fit_band']==band
@pytest.mark.parametrize('text',['UAE National only','Required Nationality: UAE Only','Emirati graduate','UAE citizens required'])
def test_unknown_citizenship_not_dropped(text):
 r=evaluate(job(description=text+'\nSOC SIEM'),DEFAULTS,P);assert not r['excluded'];assert r['eligibility']['state']=='UNKNOWN'
def test_explicit_eligibility_and_preference():
 p={**P,'declarations':{'uae_citizen':False,'uae_citizenship_confirmed':True}}
 assert evaluate(job(title='SOC Analyst UAE National'),DEFAULTS,p)['excluded']
 assert eligibility('All nationalities, priority for UAE nationals',p)['state']=='ELIGIBLE'
 assert eligibility('UAE nationals preferred',p)['state']=='ELIGIBLE'
 assert eligibility('UAE national only',{'declarations':{'uae_citizen':False}})['state']=='UNKNOWN'
@pytest.mark.parametrize('kwargs,code',[
 ({'location':'London'},'GEO_INCOMPATIBLE'),({'location':'United States - Remote'},'GEO_INCOMPATIBLE'),
 ({'title':'Security Guard','description':'Patrol premises and monitor access gates'},'DOMAIN_INCOMPATIBLE'),
 ({'title':'Mechanical Engineer','description':'Design HVAC systems for commercial buildings'},'DOMAIN_INCOMPATIBLE'),
 ({'company':'Blocked'},'USER_BLOCKED'),({'title':'Security Analyst sales'},'USER_BLOCKED')])
def test_hard_exclusions(kwargs,code):
 r=evaluate(job(**kwargs),{**DEFAULTS,'blocked_companies':['Blocked']},P);assert code in [x['code'] for x in r['hard']];assert not r['near_miss']
@pytest.mark.parametrize('kwargs',[{'title':'Senior SOC Analyst'},{'title':'Staff Security Engineer'},{'title':'Backend Engineer'}])
def test_seniority_and_ambiguous_titles_never_hard_reject_alone(kwargs):
 """Non-negotiable outcomes #3/#4: 'Senior'/'Staff' alone must never hard-
 reject, and an ambiguous out-of-track title with no strong unrelated-
 profession evidence must not be forced into DOMAIN_INCOMPATIBLE either
 (it ranks LOW/uncertain instead -- see test_domain_ambiguous_is_rankable)."""
 r=evaluate(job(**kwargs),DEFAULTS,P);assert not r['excluded']
def test_expired_posting_is_soft_not_hard():
 r=evaluate(job(closing_date='2020-01-01'),DEFAULTS,P)
 assert not r['excluded'];assert 'EXPIRED' in [x['code'] for x in r['soft']]
def test_soft_near_miss_freshness_and_adjacent():
 # Non-negotiable outcome #1: a relevant 0-3 year requirement is normal
 # early-career territory, not a stretch/near-miss (pre-#41 evaluate_legacy
 # treated any nonzero gap as a near-miss -- exactly the pattern this issue
 # retires; see test_policies_legacy_characterization).
 d=evaluate(job(description='1-3 years experience. SOC SIEM Linux'),DEFAULTS,P);assert not d['excluded'];assert d['fit_band'] in ('STRONG',)
 adjacent=evaluate(job(title='IT support',description='Responsible for SIEM and incident response'),DEFAULTS,P);assert adjacent['role']['kind']=='ADJACENT';assert adjacent['priority']<evaluate(job(),DEFAULTS,P)['priority']
 # Freshness is now a bounded 5-point ranking signal (not a hard "daily"
 # gate): an old posting stays visible and rankable, with the staleness
 # surfaced as an uncertainty note rather than suppression.
 old=evaluate(job(date_posted='2020-01-01'),DEFAULTS,P);assert not old['excluded']
 future=evaluate(job(date_posted='2999-01-01'),DEFAULTS,P);assert future['freshness']=='DATE_UNKNOWN'
def test_funnel_partition():
 rows=[{'decision':evaluate(job(),DEFAULTS,P),'disposition':'NEW'},{'decision':evaluate(job(company='Blocked'),{**DEFAULTS,'blocked_companies':['Blocked']},P),'disposition':'EXCLUDED'},{'decision':evaluate(job(),DEFAULTS,P),'disposition':'DUPLICATE','already_seen':True}]
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

def test_unquantified_professional_experience_is_neutral_not_penalized():
 # Issue #41: prose that requests "hands-on experience" without stating a
 # number is a genuine unknown, not a proxy penalty -- a strong domain/skill
 # match with no explicit year requirement can legitimately be STRONG.
 r=evaluate(job(title='SOC Security Engineer',description='SOC SIEM Linux. Production-quality scripts and hands-on experience required'),DEFAULTS,P)
 assert not r['excluded'];assert r['experience']['minimum']==0

def test_marketing_data_years_and_mixed_preferred_requirements():
 assert experience('The platform leverages 15-years of behavioral data. BS plus 2 years experience')['minimum']==2
 parsed=experience('More than 6 years of application security experience, more than 10 years is preferred')
 assert parsed['minimum']==6 and parsed['preferred_minimum']==10

def test_general_nationality_and_unknown_office_location():
 assert eligibility('Nationality\nSri Lankan, Any Arab National',P)['state']=='UNKNOWN'
 r=evaluate(job(location='In-Office'),DEFAULTS,P)
 assert not r['excluded'];assert r['fit_assessment']['geography']['compatibility']=='UNKNOWN'

@pytest.mark.parametrize('location',['Sharjah','Ajman','Ras Al Khaimah','Fujairah','Umm Al Quwain','Al Ain','Abu Dhabi Emirate'])
def test_secondary_emirates_are_not_excluded(location):
 r=evaluate(job(location=location),DEFAULTS,P);assert r['uae'] and not r['excluded']

def test_invalid_item_is_isolated_and_does_not_abort_the_source(tmp_path):
 # Issue #41 Phase 9 exception clause: a structurally invalid/unidentifiable
 # record (one that cannot safely satisfy #40's persistence contract, e.g.
 # an unusable job_url) becomes a bounded INVALID_JOB result instead of
 # crashing the whole source and rolling back every other legitimate item
 # in the batch -- the pre-#41 behavior this test used to characterize (one
 # bad row nuking an entire scan's real results) is exactly the kind of
 # pipeline fragility #41 was written to retire. 'Director SOC' is also no
 # longer hard-excluded (non-negotiable outcomes #3/#4: a management-shaped
 # title with no responsibility evidence is a ranking penalty, not a
 # rejection) so it is persisted like any other structurally valid posting
 # (Owner Decision 1).
 from tests.test_campaign_reliability import isolated
 isolated(tmp_path,r'''
from backend.models import *
import backend.main as m
initialize()
with Session.begin() as db:db.add(JobSource(name='Synthetic failure',adapter='lever',board='fixture',enabled=True))
m.discover=lambda *args:[{'title':'SOC Analyst','location':'Dubai','description':'SIEM','job_url':'https://example.com/1','source':'Lever','source_job_id':'1'},{'title':'SOC Analyst','location':'Dubai','description':'SIEM','job_url':'file://invalid','source':'Lever','source_job_id':'2'},{'title':'Director SOC','location':'Dubai','description':'10 years experience','source':'Lever','source_job_id':'3'}]
r=m.task('discover');assert r['status']=='COMPLETED',r
assert r['report']['funnel']['counts']['fetched']==3
assert r['report']['discovered']==2
assert [x['disposition'] for x in r['report']['decisions']]==['NEW','INVALID_JOB','NEW']
assert r['report']['filtered']==1
with Session() as db:assert db.query(Job).count()==2 and db.query(Application).count()==0
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
 m.discover=lambda *args:[{'title':'SOC Analyst L1','company':'Synthetic','location':'Dubai','description':'1-3 years experience. SOC SIEM','job_url':'https://example.com/1','source':'Lever','source_job_id':'1'},{'title':'Director SOC','location':'Dubai','description':'10 years experience','source':'Lever','source_job_id':'2'}]
 run=m.task('discover');assert run['status']=='COMPLETED',run
 assert run['report']['funnel']['counts']['fetched']==2
 # Issue #41: both postings are structurally valid and neither is hard-
 # rejected (a 1-3 year requirement is normal early-career territory, and
 # a management-shaped title alone is not an extreme-leadership mismatch),
 # so both are persisted and rank STRONG -- 0 near-misses (STRETCH only),
 # both appear in the daily recommendations shortlist.
 assert len(c.get('/api/recall').json()['near_misses'])==0
 assert len(c.get('/api/recall').json()['recommendations'])==2
 assert len(c.get('/api/recall/audit/'+str(run['id'])).json()['rows'])==2
 assert c.post('/api/recall/paste-preview',json={'text':'Job title: SOC Analyst\nCompany: العربية\nLocation: Sharjah\nhttps://linkedin.com/jobs/1'}).json()['network_requests']==0
 jid=c.get('/api/jobs').json()[0]['id']
 assert c.post(f'/api/recall/jobs/{jid}/feedback',json={'decision':'NOT_FOR_ME','reason':'too senior'}).status_code==200
 assert len(c.get('/api/recall').json()['recommendations'])==1
 assert c.put('/api/recall/policy',json={'policy':'STRICT'}).status_code==200
 assert m.task('discover')['report']['discovered']==0
 with Session() as db:assert db.query(Application).count()==0
''')

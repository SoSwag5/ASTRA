"""Regressions for PR #59's independently reproduced #41 blockers."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from backend.models import Application, Base, DEFAULTS, Settings
from backend.recall import evaluate
from backend.services import add_job, analyze


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with OrmSession(engine, expire_on_commit=False) as session:
        session.add(Settings(id=1, value=DEFAULTS))
        session.commit()
        yield session


def test_saved_application_and_manual_workflow_state_is_preserved(db):
    rejected = {'company': 'Synthetic', 'title': 'Security Officer', 'location': 'Dubai',
                'description': 'Patrol premises and guard access gates.', 'source': 'Company',
                'job_url': 'https://example.com/jobs/saved'}
    saved, _ = add_job(db, rejected)
    saved.analysis = {'saved': True}
    saved.status = 'FOUND'
    analyze(db, saved, profile={}, cfg=DEFAULTS)
    assert saved.analysis['fit_assessment']['bucket'] == 'REJECTED'
    assert saved.status == 'FOUND'

    linked, _ = add_job(db, {**rejected, 'job_url': 'https://example.com/jobs/linked', 'source_job_id': 'linked'})
    linked.status = 'INTERVIEW'
    db.add(Application(job_id=linked.id, status='INTERVIEW', tracking={'fit_at_application': {'bucket': 'GOOD'}}))
    db.flush()
    analyze(db, linked, profile={}, cfg=DEFAULTS)
    assert linked.analysis['fit_assessment']['bucket'] == 'REJECTED'
    assert linked.status == 'INTERVIEW'

    manual, _ = add_job(db, {**rejected, 'job_url': 'https://example.com/jobs/manual', 'source': 'Manual'})
    manual.status = 'FOUND'
    analyze(db, manual, profile={}, cfg=DEFAULTS)
    assert manual.status == 'FOUND'


def test_shadow_is_bounded_and_categorized():
    decision = evaluate({'company': 'Synthetic', 'title': 'Senior SOC Analyst', 'location': 'Dubai',
                         'description': 'SIEM monitoring'}, DEFAULTS, {})
    shadow = decision['assessment_shadow']
    assert set(shadow) == {'legacy_excluded', 'legacy_primary_reason', 'legacy_priority', 'new_bucket',
                           'new_priority', 'new_hard_reject', 'comparison_category'}
    assert shadow['legacy_excluded'] is True
    assert shadow['new_hard_reject'] is None
    assert shadow['comparison_category'].startswith('LEGACY_REJECTED_NEW_')


def test_post_persistence_reassessment_and_no_profile(tmp_path):
    from tests.test_campaign_reliability import isolated
    isolated(tmp_path, r'''
from backend.models import *
import backend.main as main
from tests.scan_harness import confirmed_discover
initialize()
with Session.begin() as db:
    cfg=db.get(Settings,1);cfg.value={**DEFAULTS,'career_tracks':['CYBERSECURITY'],'custom_target_roles':[],'search_focus_confirmed':True}
    db.add(JobSource(name='Synthetic employer',adapter='smartrecruiters',board='synthetic',enabled=True))
item={'title':'Security Officer','location':'Dubai','description':'Patrol premises and guard access gates.',
      'job_url':'https://example.com/jobs/41','source':'SmartRecruiters','source_job_id':'41'}
main.discover=lambda *args:[dict(item)]

first=confirmed_discover()
assert first['report']['checked']==1 and first['report']['buckets']['REJECTED']==1
assert first['report']['rejected']==1 and first['report']['hard_reasons']=={'DOMAIN_INCOMPATIBLE':1}
with Session() as db:
    job=db.query(Job).one();job_id=job.id
    assert job.status=='SKIP' and job.analysis['fit_assessment']['bucket']=='REJECTED'
    assert job.analysis['recall']['fit_assessment']==job.analysis['fit_assessment']
    assert db.query(JobObservation).count()==1
    audit=first['report']['decisions'][0]
    assert audit['decision']['fit_assessment']==job.analysis['fit_assessment']

with Session.begin() as db:
    cfg=db.get(Settings,1);cfg.value={**cfg.value,'custom_target_roles':['Security Officer']}
second=confirmed_discover()
with Session() as db:
    job=db.query(Job).one()
    assert job.id==job_id and db.query(JobObservation).count()==1
    assert job.analysis['fit_assessment']['bucket']=='STRONG'
    assert job.analysis['recall']['fit_assessment']==job.analysis['fit_assessment']
    assert job.status!='SKIP'
    assert second['report']['duplicates']==1 and second['report']['checked']==1
    assert second['report']['buckets']['STRONG']==1
    assert second['report']['strong']==1 and second['report']['rejected']==0
    assert second['report']['decisions'][0]['decision']['fit_assessment']==job.analysis['fit_assessment']
    assert sum(second['report']['assessment_comparisons'].values())==1

with Session.begin() as db:
    cfg=db.get(Settings,1);cfg.value={**cfg.value,'custom_target_roles':[]}
third=confirmed_discover()
with Session() as db:
    job=db.query(Job).one()
    assert job.id==job_id and job.status=='SKIP'
    assert job.analysis['fit_assessment']['bucket']=='REJECTED'
    assert third['report']['buckets']['REJECTED']==1
''')


def test_stored_application_profile_drives_discovery_eligibility(tmp_path):
    from tests.test_campaign_reliability import isolated
    isolated(tmp_path, r'''
from backend.models import *
import backend.main as main
from tests.scan_harness import confirmed_discover
initialize()
with Session.begin() as db:
    cfg=db.get(Settings,1);cfg.value={**DEFAULTS,'application_profile':{
        'work_authorisation':{'US':'NO'},'sponsorship':{'US':'UNKNOWN'}}}
    db.add(JobSource(name='Synthetic employer',adapter='smartrecruiters',board='synthetic',enabled=True))
main.discover=lambda *args:[{'title':'SOC Analyst','location':'Remote','description':'US work authorization required. Sponsorship unavailable.',
    'job_url':'https://example.com/jobs/auth','source':'SmartRecruiters','source_job_id':'auth'}]
run=confirmed_discover()
with Session() as db:
    job=db.query(Job).one();fa=job.analysis['fit_assessment']
    assert fa['hard_reject']['code']=='CONFIRMED_ELIGIBILITY_CONFLICT'
    assert fa['eligibility']['requirements'][0]['country']=='US'
    assert job.status=='SKIP' and run['report']['buckets']['REJECTED']==1
''')

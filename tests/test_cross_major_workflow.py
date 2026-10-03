"""Five fictional PDF -> confirmed focus -> mocked provider scan workflows.

Self-authored regression scenarios, not a blind relevance benchmark or evidence
that live source coverage supports every career. No real postings or network.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.test_beta_review_fixes import text_cv

CASES = json.loads((Path(__file__).parent/'fixtures/beta_cross_major.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_fictional_major_import_and_confirmed_scan(case, tmp_path):
    lines = ['Fictional '+case['major']+' Graduate', 'Fictional City, UAE | fictional.example',
             'Professional Summary', 'Recent graduate in '+case['major']+' seeking '+case['role']+' roles.',
             case['heading'], ', '.join(case['skills'][:3]), '; '.join(case['skills'][3:]),
             'Work Experience', case['internship']+' - 4 months', 'Fictional Employer | Fictional City',
             'Completed a fictional internship and documented its tasks.', 'Projects', case['project'],
             'Education', 'Bachelor degree in '+case['major']+' at Fictional University',
             'Courses', 'Fictional introductory course related to '+case['major']]
    cv = tmp_path/'fictional.pdf'
    cv.write_bytes(text_cv(lines, delayed_summary=True))
    result = run_case(case, cv, tmp_path)
    assert result.returncode==0,result.stdout+result.stderr


def run_case(case, cv, workspace):
    """Exercise either a generated fixture or a separately rendered fictional CV."""
    script = r'''
import json,socket
from pathlib import Path
from fastapi.testclient import TestClient
case=json.loads(__CASE_JSON__)
def blocked(*a,**kw): raise AssertionError('Product test attempted network access')
socket.getaddrinfo=blocked;socket.create_connection=blocked
import backend.main as main
import backend.job_providers.lever as lever
from tests.scan_harness import confirmed_discover
role=case['role'];skills=', '.join(case['skills'])
descriptions=[
 ('Graduate '+role,'Dubai','Graduate role. Bachelor degree in '+case['major']+'. '+skills+'. No prior full-time experience required.'),
 ('Junior '+role,'Abu Dhabi','Entry-level role. '+skills+'. Internship experience welcome.'),
 ('Senior '+role,'Dubai','Senior position. Minimum 7 years of professional experience required. '+skills),
 (role,'London','This position requires residence in the United Kingdom. '+skills),
 ('Dental Surgeon','Dubai','Licensed dental surgeon. Dentistry degree and 5 years of clinical practice required.'),
 (role+' - UAE Nationals Only','Dubai','UAE nationals only. '+skills),
]
payload=[]
for i,(title,location,description) in enumerate(descriptions):
    native=f'00000000-0000-4000-8000-{i+1:012d}'
    payload.append({'id':native,'text':title,'description':'<p>'+description+'</p>',
                    'categories':{'location':location,'commitment':'Full-time'},
                    'hostedUrl':'https://jobs.lever.co/fictional-beta/'+native,'workplaceType':'on-site'})
lever.fetch_json=lambda *a,**kw:payload
with TestClient(main.app) as client:
    initial=client.get('/api/settings').json()
    assert initial['provider']=='rules' and not initial['search_focus_confirmed']
    response=client.post('/api/import/cv',files={'file':('fictional.pdf',Path(__CV_PATH__).read_bytes(),'application/pdf')})
    assert response.status_code==200,response.text
    profile=client.get('/api/profile').json()
    assert profile['confirmed'] is False
    assert case['major'] in profile['summary'] and case['role'] in profile['summary']
    assert {s['text'] for s in profile['skills']}==set(case['skills'])
    assert len(profile['employments'])==len(profile['projects'])==len(profile['education'])==len(profile['certifications'])==1
    assert all(s['provenance'].startswith('CV SHA256 ') for s in profile['skills'])
    assert client.put('/api/profile',json={'confirmed':True}).status_code==200
    focus=client.post('/api/settings/career-focus',json={'career_tracks':[],'custom_target_roles':[role]})
    assert focus.status_code==200 and focus.json()['career_tracks']==[]
    assert focus.json()['target_roles']==[role]
    assert client.post('/api/search/sources',json={'name':'Fictional board','url':'https://jobs.lever.co/fictional-beta'}).status_code==200
    result=confirmed_discover()
    assert result['status']=='COMPLETED',result['status']
    assert result['report']['scanned']==6,result['report']['scanned']
    jobs=client.get('/api/jobs').json()
    matching=[j for j in jobs if j['title'] in ('Graduate '+role,'Junior '+role)]
    assert len(matching)==2,jobs
    assert all(j['status']!='SKIP' for j in matching),matching
    dental=[j for j in jobs if j['title']=='Dental Surgeon']
    # Unknown professions are retained for review by the existing conservative
    # policy. They must rank below matching targets and disclose uncertainty.
    assert len(dental)==1
    dental_fit=dental[0]['analysis']['fit_assessment']
    assert dental_fit['match_type']=='OUTSIDE',dental_fit
    assert dental[0]['match_score']<min(j['match_score'] for j in matching)
    assert 'Domain relevance could not be confirmed from title/description' in dental_fit['uncertainty']
    assert all(j['status']=='SKIP' for j in jobs if j['title']==role and j['location']=='London')
    senior=next(j for j in jobs if j['title']=='Senior '+role)
    assert senior['match_score']<max(j['match_score'] for j in matching)
    national=next(j for j in jobs if 'Nationals Only' in j['title'])
    assert national['analysis']['fit_assessment']['eligibility']['state']!='ELIGIBLE',national
    assert client.get('/api/records/applications').json()==[]
    assert client.get('/api/settings').json()['provider']=='rules'
    print(json.dumps({'major':case['id'],'skills_extracted':len(profile['skills']),
                      'postings_checked':6,'relevant_roles_retained':len(matching),
                      'matching_scores':[j['match_score'] for j in matching],
                      'outside_role_score':dental[0]['match_score'],
                      'outside_role_retained_for_review':True,
                      'eligibility_not_inferred':True,'provider':'rules','network_calls':0}))
'''.replace('__CASE_JSON__',repr(json.dumps(case))).replace('__CV_PATH__',repr(str(cv)))
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(workspace/'fictional.db'),
         'HUNTER_DATA_DIR':str(workspace/'data'),'APP_TOKEN':'','ASTRA_DEMO_ONLY':'0',
         'PYTHON_KEYRING_BACKEND':'keyring.backends.fail.Keyring'}
    script = 'from backend import starter_catalog\nstarter_catalog.catalog = lambda: []\n' + script
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=90)
    return result

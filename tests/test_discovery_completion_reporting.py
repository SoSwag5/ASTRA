"""Codex round-2 finding F5: a failing source's per-source report must
never be left showing completion: COMPLETE. Exercises the real
backend.main.task('discover') loop (not just the provider layer) since
F5 was specifically about propagation through backend/main.py's
per-source try/except into JobSource.details/source_report.
"""
from tests.test_campaign_reliability import isolated


def test_real_provider_outcomes_replace_all_stale_source_telemetry(tmp_path):
    isolated(tmp_path, r'''
import json
from unittest.mock import patch
from sqlalchemy import select
import httpx
from backend.models import *
from backend.job_providers import transport as t
import backend.main as m
initialize()
stale = {'last_metrics':{'requests_succeeded':99}, 'last_completion':'OLD',
         'last_completion_reason':'OLD', 'last_health':'OLD',
         'last_error_code':'OLD', 'last_structured_error':{'code':'OLD'}}
with Session.begin() as db:
    for board in ('good', 'bad', 'empty', 'partial', 'mixed'):
        db.add(JobSource(name=board, adapter='greenhouse', board=board,
                         enabled=True, details=dict(stale)))
    db.add(Job(title='Existing job', company='bad', status='FOUND',
               job_url='https://example.com/old'))
class Raw(httpx.SyncByteStream):
    def __init__(self, body): self.body=body
    def __iter__(self): yield self.body
row={'id':1,'title':'SOC Analyst','location':{'name':'Dubai'},
     'absolute_url':'https://example.com/1','content':'SIEM'}
def handler(request):
    url=str(request.url)
    if '/bad/' in url: raise httpx.ReadTimeout('private diagnostic')
    if '/partial/' in url:
        if 'content=true' in url: body=b' '*501
        elif url.endswith('/1'): raise httpx.RemoteProtocolError('private diagnostic')
        else: body=json.dumps({'jobs':[row]}).encode()
    else:
        rows=[] if '/empty/' in url else [row, {'id':{}}] if '/mixed/' in url else [row]
        body=json.dumps({'jobs':rows}).encode()
    return httpx.Response(200,headers={'content-type':'application/json'},stream=Raw(body))
with patch.object(t,'_PinnedTransport',lambda budget:httpx.MockTransport(handler)), patch.object(t,'MAX_ENCODED_BYTES',500):
    result=m.task('discover')
reports={s['name']:s for s in result['report']['sources']}
assert result['status']=='PARTIAL'
assert reports['good']['imported']==1
expected={'good':('COMPLETE','HEALTHY',None),
          'bad':('FAILED','UNAVAILABLE','TRANSPORT_ERROR'),
          'empty':('COMPLETE','EMPTY',None),
          'partial':('PARTIAL','PARTIAL','DETAIL_FETCH_INCOMPLETE'),
          'mixed':('COMPLETE','PARTIAL','SOME_RECORDS_REJECTED')}
with Session() as db:
    assert db.scalar(select(Job).where(Job.title=='Existing job')).status=='FOUND'
    assert db.scalar(select(Job).where(Job.title=='SOC Analyst')) is not None
    for source in db.scalars(select(JobSource)):
        report=reports[source.name]
        assert (report['completion'],report['health'],report['completion_reason'])==expected[source.name]
        for field in ('completion','completion_reason','health','metrics','structured_error','error_code'):
            assert source.details['last_'+field]==report[field], (source.name,field)
        assert report['metrics']['requests_succeeded']!=99
        if source.name=='bad':
            assert report['error_code']=='READ_TIMEOUT'
            assert report['structured_error']['code']=='READ_TIMEOUT'
            assert 'private' not in report['structured_error']['message']
            assert report['metrics']['errors_count']==1
        else:
            assert report['structured_error'] is None
            assert report['error_code'] is None
assert reports['mixed']['metrics']['records_rejected']==1
assert reports['mixed']['metrics']['errors_count']==1
assert reports['partial']['metrics']['errors_count']==2
''')


def test_one_source_failing_is_reported_failed_while_the_other_stays_complete(tmp_path):
    isolated(tmp_path, r'''
from backend.models import *
import backend.main as m
initialize()
with Session.begin() as db:
    db.add(JobSource(name='Good source', adapter='lever', board='fixture', enabled=True))
    db.add(JobSource(name='Bad source', adapter='greenhouse', board='fixture', enabled=True))

def fake_discover(kind, board, url, cfg=None):
    if kind == 'lever':
        return [{'title': 'SOC Analyst', 'location': 'Dubai', 'description': 'SIEM', 'job_url': 'https://example.com/1'}]
    raise ValueError('Source unavailable')

m.discover = fake_discover
r = m.task('discover')
sources = {s['name']: s for s in r['report']['sources']}
assert sources['Good source']['completion'] == 'COMPLETE', sources['Good source']
assert sources['Bad source']['completion'] == 'FAILED', sources['Bad source']
assert not sources['Bad source']['error'] == ''
assert r['report']['discovered'] == 1
assert r['status'] == 'PARTIAL'
''')


def test_provider_framework_partial_completion_reaches_source_report(tmp_path):
    """A Greenhouse fetch that succeeds but only PARTIALLY (detail-budget
    exhausted) must show completion: PARTIAL in the per-source report,
    not the pre-set default of COMPLETE.
    """
    isolated(tmp_path, r'''
from backend.models import *
from backend.job_providers.compatibility import ProviderItems
import backend.main as m
initialize()
with Session.begin() as db:
    db.add(JobSource(name='Partial source', adapter='greenhouse', board='fixture', enabled=True))

def fake_discover(kind, board, url, cfg=None):
    items = ProviderItems([{'title': 'SOC Analyst', 'location': 'Dubai', 'description': 'SIEM', 'job_url': 'https://example.com/1', 'source': 'Greenhouse', 'source_job_id': '1'}])
    items.health = {'completion': 'PARTIAL', 'health': 'PARTIAL', 'completion_reason': 'DETAIL_BUDGET_EXHAUSTED', 'metrics': {'content_cap_reached': True}, 'error': None}
    return items

m.discover = fake_discover
r = m.task('discover')
source_report = r['report']['sources'][0]
assert source_report['completion'] == 'PARTIAL', source_report
assert source_report['completion_reason'] == 'DETAIL_BUDGET_EXHAUSTED'
assert r['status'] == 'COMPLETED'  # a truthful PARTIAL source is not itself a run failure
''')

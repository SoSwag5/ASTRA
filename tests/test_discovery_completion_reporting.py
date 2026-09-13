"""Codex round-2 finding F5: a failing source's per-source report must
never be left showing completion: COMPLETE. Exercises the real
backend.main.task('discover') loop (not just the provider layer) since
F5 was specifically about propagation through backend/main.py's
per-source try/except into JobSource.details/source_report.
"""
from tests.test_campaign_reliability import isolated


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

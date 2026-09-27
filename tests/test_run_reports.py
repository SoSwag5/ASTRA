"""Polled scan views read run summaries, never the per-posting decision audit.

Each test runs in a fresh process with its own fictional database
(tests.test_campaign_reliability.isolated). A statement recorder proves the
performance property directly: after a run's summary has been read once,
polling /search/overview and /scan/status or opening a preview selects no raw
report column, and every response equals what the full reports would give.
"""
from tests.test_campaign_reliability import isolated

PRELUDE = r'''
import json, socket, threading
socket.getaddrinfo = lambda *a, **k: (_ for _ in ()).throw(OSError('network disabled in this test'))
from fastapi.testclient import TestClient
from sqlalchemy import event, select
import backend.main as m
from backend.models import *
from backend import run_reports, scan_control as sc

m.discover = lambda *a, **k: (_ for _ in ()).throw(AssertionError('no scan may start in this test'))
statements = []
event.listen(engine, 'before_cursor_execute',
             lambda conn, cursor, statement, params, *rest: statements.append((statement, tuple(params or ()))))

def raw_report_reads():
    # A read restricted to RUNNING runs is the unchanged Stop/progress path; its report stays small.
    return [s for s, p in statements if s.lstrip().upper().startswith('SELECT') and 'automation_runs.report' in s
            and 'json_remove(automation_runs.report' not in s
            and not ('automation_runs.status = ?' in s and 'RUNNING' in p)]

def summary_loads():
    return [s for s, p in statements if 'json_remove(automation_runs.report' in s]

def decision(n):
    return {'source_id': 1, 'item': {'title': 'Fictional role %d' % n, 'description': 'x' * 2000},
            'disposition': 'DUPLICATE', 'decision': {'priority': n, 'fit_assessment': {'bucket': 'LOW'}}}

def finished(n, **extra):
    return AutomationRun(task='discover', status='COMPLETED', report={
        'discovered': n, 'duplicates': 5, 'failures': 0, 'duration_seconds': 10.0 * n, 'sources_attempted': 2,
        'scanned': 5 * n, 'sources': [{'id': 1, 'name': 'Fictional alpha', 'scanned': n, 'imported': 1,
                                       'duplicates': 4, 'filtered': {}, 'error': ''}],
        'decisions': [decision(i) for i in range(40)], 'discovery_telemetry': {'schema': 'fictional'}, **extra})

def reference_overview():
    """/search/overview exactly as the pre-fix code built it: full reports, audit dropped at the end."""
    with Session() as db:
        runs = list(db.scalars(select(AutomationRun).where(AutomationRun.task == 'discover')
                               .order_by(AutomationRun.id.desc()).limit(100)))
        sources = []
        for source in db.scalars(select(JobSource).where(JobSource.adapter != 'manual').order_by(JobSource.name)):
            result = checked = None
            for run in runs:
                result = next((s for s in run.report.get('sources', []) if s.get('id') == source.id
                               or ('id' not in s and s.get('name') == source.name)), None)
                if result is not None:
                    checked = run.updated_at
                    break
            sources.append({**serialize(source), 'last_scan': checked, 'result': result})
        return json.loads(json.dumps({'sources': sources, 'runs': [
            {**serialize(r), 'report': {k: v for k, v in r.report.items() if k != 'decisions'}} for r in runs[:20]]}))

def reference_last():
    with Session() as db:
        last = db.scalars(select(AutomationRun).where(AutomationRun.task == 'discover', AutomationRun.status != 'RUNNING')
                          .order_by(AutomationRun.id.desc())).first()
        return json.loads(json.dumps(sc._view(last))) if last else None

def overview(c):
    body = c.get('/api/search/overview').json()
    return {'sources': body['sources'], 'runs': body['runs']}
'''


def test_polled_views_equal_full_reports_and_skip_the_audit_after_first_read(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
initialize()
with Session.begin() as db:
    db.add_all([JobSource(name='Fictional alpha', adapter='lever', board='alpha', enabled=True),
                JobSource(name='Fictional beta', adapter='ashby', board='beta', enabled=True)])
    db.add_all([finished(n) for n in range(1, 25)])
    db.add(AutomationRun(task='report', status='COMPLETED', report={'decisions': ['not a discovery run']}))
with TestClient(m.app) as c:
    assert overview(c) == reference_overview()
    assert all('decisions' not in r['report'] for r in overview(c)['runs'])
    assert len(overview(c)['runs']) == 20
    assert c.get('/api/scan/status').json()['last'] == reference_last()
    statements.clear()
    for _ in range(3):
        overview(c); c.get('/api/scan/status')
    assert raw_report_reads() == [] and summary_loads() == [], statements
    with Session.begin() as db:
        db.add(AutomationRun(task='discover', status='RUNNING', report={'progress': {'sources_done': 0}}))
    statements.clear()
    body = c.get('/api/search/overview').json()
    assert body['runs'][0]['status'] == 'RUNNING' and body['runs'][0]['report']['progress'] == {'sources_done': 0}
    assert len(summary_loads()) == 1 and raw_report_reads() == []     # only the running run is read
    assert overview(c) == reference_overview()
''')


def test_cached_summaries_follow_every_committed_change(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
from datetime import datetime, timedelta, timezone
from backend import discovery_telemetry
initialize()
with Session.begin() as db:
    db.add(JobSource(name='Fictional alpha', adapter='lever', board='alpha', enabled=True))
    old = finished(1); db.add(old); db.add(finished(2))
with Session() as db:
    old_id, new_id = sorted(db.scalars(select(AutomationRun.id).where(AutomationRun.task == 'discover')))
with TestClient(m.app) as c:
    assert overview(c) == reference_overview()
    # A status-preserving rewrite: telemetry retention drops the audit and the telemetry.
    with Session.begin() as db:
        db.get(AutomationRun, old_id).created_at = '2020-01-01T00:00:00+00:00'
    with Session.begin() as db:
        assert discovery_telemetry.prune_expired(db)['runs_pruned'] == 1
    runs = {r['id']: r for r in overview(c)['runs']}
    assert 'discovery_telemetry' not in runs[old_id]['report'] and runs[old_id]['created_at'].startswith('2020')
    assert overview(c) == reference_overview()
    # A status change and an ordinary report edit.
    with Session.begin() as db:
        run = db.get(AutomationRun, new_id); run.status = 'INTERRUPTED'; run.report = {**run.report, 'error': 'fictional'}
    assert c.get('/api/scan/status').json()['last'] == reference_last()
    assert c.get('/api/scan/status').json()['last']['status'] == 'INTERRUPTED'
    # A rolled-back edit leaves the committed summary in place.
    with Session() as db:
        db.get(AutomationRun, new_id).report = {'discovered': 999}; db.flush(); db.rollback()
    assert overview(c) == reference_overview()
    # A read that races a commit is returned but not cached.
    run_reports.clear()
    racing = lambda conn, cursor, statement, *rest: 'json_remove' in statement and run_reports._generation.__setitem__(0, run_reports._generation[0] + 1)
    event.listen(engine, 'before_cursor_execute', racing)
    assert overview(c) == reference_overview()
    event.remove(engine, 'before_cursor_execute', racing)
    assert run_reports._cache == {}
''')


def test_estimate_uses_posting_volume_and_reports_the_slowest_recent_pace(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
initialize()
with Session.begin() as db:
    db.add_all([JobSource(name='Fictional alpha', adapter='lever', board='alpha', enabled=True, details={'jobs_fetched': 100}),
                JobSource(name='Fictional beta', adapter='ashby', board='beta', enabled=True, details={'jobs_fetched': 200})])
    for duration in (60, 300):   # 0.1 and 0.5 s per posting over 600 postings; 30 and 150 s per source
        db.add(AutomationRun(task='discover', status='COMPLETED', report={
            'duration_seconds': duration, 'sources_attempted': 2, 'scanned': 600, 'decisions': [decision(1)] * 30}))
with TestClient(m.app) as c:
    statements.clear()
    w = c.post('/api/scan/preview', json={}).json()['workload']
    assert raw_report_reads() == [], statements
    assert (w['estimated_seconds'], w['estimated_seconds_slowest']) == (90, 150)       # 0.3 and 0.5 s x 300 postings
    assert 'per posting' in w['estimate_basis'] and w['postings_last_seen'] == 300
    # A source with no posting count: the per-posting basis would undercount, so per source is used.
    with Session.begin() as db:
        db.add(JobSource(name='Fictional gamma', adapter='lever', board='gamma', enabled=True))
    w = c.post('/api/scan/preview', json={}).json()['workload']
    assert (w['estimated_seconds'], w['estimated_seconds_slowest']) == (270, 450)      # 90 and 150 s x 3 sources
    assert 'per source' in w['estimate_basis'] and w['sources_without_history'] == 1
''')


def test_today_overview_reads_only_the_last_finished_run(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
initialize()
with Session.begin() as db:
    db.add(JobSource(name='Fictional alpha', adapter='lever', board='alpha', enabled=True))
    db.add_all([finished(n) for n in range(1, 6)])
with Session() as db:
    latest = max(db.scalars(select(AutomationRun.id).where(AutomationRun.status == 'COMPLETED')))
with TestClient(m.app) as c:
    with Session.begin() as db:      # after startup, so restart handling leaves it RUNNING
        db.add(AutomationRun(task='discover', status='RUNNING', report={}))
    statements.clear()
    health = c.get('/api/campaign').json()['discovery_health']
    reads = [s for s in raw_report_reads() if 'FROM automation_runs' in s]
    assert reads and all('LIMIT' in s for s in reads), reads
    with Session() as db:
        assert health['last'] == db.get(AutomationRun, latest).updated_at and health['new'] == 5
''')

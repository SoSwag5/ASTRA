"""Manual-only scanning: nothing starts discovery except an explicit, confirmed
Start Scan.

Every test runs in a fresh Python process against its own throwaway data
directory (tests.test_campaign_reliability.isolated), so each one exercises a
real application startup -- lifespan, scheduler, restart handling -- rather
than a long-lived shared app. No test touches a live database, workbook or
network: provider fetches are replaced by fixtures, and the startup tests fail
if anything resolves a hostname or opens an outbound connection.
"""
from tests.test_campaign_reliability import isolated

# Shared prelude: network tripwires, a fixture-only discovery function, and
# small helpers. Installed BEFORE the application module is imported.
PRELUDE = r'''
import socket, threading, time
network_calls = []
_real_getaddrinfo, _real_connect = socket.getaddrinfo, socket.create_connection
def _no_dns(host, *a, **k):
    network_calls.append(('dns', host)); raise OSError('network disabled in this test')
def _no_connect(address, *a, **k):
    network_calls.append(('connect', address)); raise OSError('network disabled in this test')
socket.getaddrinfo = _no_dns
socket.create_connection = _no_connect

from fastapi.testclient import TestClient
from sqlalchemy import select
import backend.main as m
from backend.models import *

fetches = []
fetch_locations = []
gate = threading.Event(); gate.set()
def fixture_discover(adapter, board, url='', cfg=None):
    fetches.append(board)
    fetch_locations.append(list((cfg or {}).get('locations', [])))
    assert gate.wait(20), 'fixture gate never released'
    return []
m.discover = fixture_discover

def wait_for(predicate, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if predicate(): return True
        time.sleep(0.05)
    return False

def discover_runs():
    with Session() as db:
        return list(db.scalars(select(AutomationRun).where(AutomationRun.task=='discover').order_by(AutomationRun.id)))

def add_sources(*boards):
    with Session.begin() as db:
        for board in boards:
            db.add(JobSource(name='Fixture '+board, adapter='lever', board=board, enabled=True))
'''


def test_fresh_install_startup_schedules_and_fetches_nothing(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
with TestClient(m.app) as c:
    jobs = m.scheduler.get_jobs()
    assert m.scheduler.running
    assert m.scheduler.get_job('discover') is None
    assert not any(job.args == ['discover'] or job.args == ('discover',) for job in jobs), jobs
    time.sleep(1.0)
    overview = c.get('/api/search/overview').json()
    assert overview['scan_mode'] == 'MANUAL_ONLY' and overview['enabled'] is False
    assert overview['next_scan'] is None and overview['running'] is False
    status = c.get('/api/scan/status').json()
    assert status['manual_only'] is True and status['active'] is None
assert discover_runs() == [] and fetches == [] and network_calls == []
''')


def test_legacy_automatic_settings_become_manual_without_losing_data(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
from datetime import datetime, timedelta, timezone
initialize()
long_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
legacy = {'discovery_enabled': True, 'discovery_interval_hours': 3, 'autopilot': 'PREPARE_ONLY',
          'auto_sync': True, 'schedule': {'discover': '00:00', 'analyze': '01:15', 'prepare': '01:30',
                                          'process': '02:00', 'sync': '03:00', 'report': '07:30'}}
with Session.begin() as db:
    row = db.get(Settings, 1); row.value = {**row.value, **legacy}
    db.add(JobSource(name='Fixture legacy', adapter='lever', board='legacy', enabled=True))
    # A last scan long enough ago that the old code fired an automatic CATCHUP.
    db.add(AutomationRun(task='discover', status='COMPLETED', report={'source_id': None},
                         created_at=long_ago, updated_at=long_ago))
    db.add(Job(title='SOC Analyst', company='Fixture Co', location='Dubai',
               job_url='https://jobs.lever.co/legacy/1', source='Lever'))
with Session() as db:
    runs_before = db.query(AutomationRun).count(); jobs_before = db.query(Job).count()

started = []
real_task = m.task
m.task = lambda *a, **k: started.append((a, k))
with TestClient(m.app) as c:
    assert m.scheduler.get_job('discover') is None
    # The legacy scheduled/catch-up entry point starts nothing.
    m.scheduled('discover')
    assert started == []
    # Non-discovery scheduled work is still registered and unchanged.
    assert {j.id for j in m.scheduler.get_jobs()} >= {'analyze', 'prepare', 'process', 'sync', 'report'}
    assert c.get('/api/search/overview').json()['enabled'] is False
    time.sleep(1.0)
m.task = real_task

with Session() as db:
    cfg = settings(db)
    for key, value in legacy.items():
        assert cfg[key] == value, (key, cfg[key])        # stored settings untouched
    assert db.query(AutomationRun).count() == runs_before  # no run created
    assert db.query(Job).count() == jobs_before            # job history intact
assert fetches == [] and network_calls == []

# The command the old Windows task ran is now a harmless no-op, whatever its flags.
import sys, scripts.discovery_once as headless
for argv in (['discovery_once.py'], ['discovery_once.py', '--trigger', 'SCHEDULED'],
             ['discovery_once.py', '--force', '--trigger', 'MANUAL']):
    sys.argv = argv; assert headless.main() == 0
with Session() as db:
    assert db.query(AutomationRun).count() == runs_before
assert fetches == []
''')


def test_legacy_start_paths_cannot_start_discovery(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
initialize(); add_sources('one')
with TestClient(m.app) as c:
    assert c.post('/api/search/scan', json={}).status_code == 400
    assert c.post('/api/search/scan', json={'source_id': 1}).status_code == 400
    assert c.post('/api/tasks/discover').status_code == 400
    for action in ('Enable', 'RunNow'):
        r = c.post('/api/campaign/windows-schedule', json={'action': action, 'hours': 6})
        assert r.status_code == 400 and 'Start Scan' in r.json()['detail']
    # Non-discovery tasks still run from their own buttons.
    assert c.post('/api/tasks/report').json()['status'] == 'COMPLETED'
    time.sleep(0.5)
assert discover_runs() == [] and fetches == []
''')


def test_preview_then_one_confirmation_starts_exactly_one_run(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
initialize(); add_sources('alpha', 'beta')
gate.clear()
with TestClient(m.app) as c:
    preview = c.post('/api/scan/preview', json={}).json()
    assert preview['manual_only'] is True
    assert [s['name'] for s in preview['scope']['sources']] == ['Fixture alpha', 'Fixture beta']
    assert preview['workload']['sources'] == 2
    assert preview['workload']['estimated_seconds'] is None      # no history yet: stated, not guessed
    assert fetches == [] and discover_runs() == []                # a preview fetches nothing

    first = c.post('/api/scan/start', json={'token': preview['token']})
    assert first.status_code == 200 and first.json()['started']
    run_id = first.json()['run_id']
    # A repeated click with the same confirmation cannot start a second run.
    again = c.post('/api/scan/start', json={'token': preview['token']})
    assert again.status_code == 409 and again.json()['already_started'] and again.json()['run_id'] == run_id
    # Nor can a fresh preview or an unknown token while one is running.
    assert c.post('/api/scan/preview', json={}).status_code == 409
    assert c.post('/api/scan/start', json={'token': 'x' * 43}).status_code == 409

    # Progress is visible while the scan runs.
    assert wait_for(lambda: len(fetches) == 1)
    active = c.get('/api/scan/status').json()['active']
    assert active['id'] == run_id and active['trigger'] == 'MANUAL_START'
    assert active['progress']['sources_total'] == 2 and active['progress']['current_source'] == 'Fixture alpha'
    assert c.get('/api/search/overview').json()['running'] is True

    gate.set()
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
    last = c.get('/api/scan/status').json()['last']
    assert last['id'] == run_id and last['status'] == 'COMPLETED'
    assert last['progress']['sources_done'] == 2
runs = discover_runs()
assert [r.id for r in runs] == [run_id] and sorted(fetches) == ['alpha', 'beta']
assert not m.task_lock.locked() and network_calls == []
''')


def test_single_source_preview_scopes_the_run(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
initialize(); add_sources('alpha', 'beta')
with TestClient(m.app) as c:
    with Session() as db:
        beta = db.scalar(select(JobSource).where(JobSource.board == 'beta')).id
    preview = c.post('/api/scan/preview', json={'source_id': beta}).json()
    assert preview['scope']['single_source'] and preview['scope']['source_ids'] == [beta]
    run_id = c.post('/api/scan/start', json={'token': preview['token']}).json()['run_id']
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
assert fetches == ['beta'] and [r.id for r in discover_runs()] == [run_id]
''')


def test_stop_prevents_any_further_source_fetch(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
initialize(); add_sources('alpha', 'beta', 'gamma')
gate.clear()
with TestClient(m.app) as c:
    run_id = c.post('/api/scan/start',
                    json={'token': c.post('/api/scan/preview', json={}).json()['token']}).json()['run_id']
    assert wait_for(lambda: len(fetches) == 1)          # first source is mid-fetch
    assert c.get('/api/scan/status').json()['cancellable'] is True
    stop = c.post('/api/scan/cancel', json={'run_id': run_id})
    assert stop.status_code == 200 and stop.json()['cancelling']
    assert c.get('/api/scan/status').json()['active']['cancel_requested_at']
    gate.set()                                            # let the in-flight source finish
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
    assert c.post('/api/scan/cancel', json={'run_id': run_id}).status_code == 409
assert fetches == ['alpha'], fetches                    # no further source was fetched
with Session() as db:
    run = db.get(AutomationRun, run_id)
    assert run.status == 'CANCELLED'
    assert run.report['cancelled'] == {'sources_not_fetched': 2}
    assert run.report['cancel_requested_at']
    from backend import discovery_telemetry as t
    states = [s['attempt_state'] for s in run.report[t.REPORT_KEY]['sources']]
    assert states.count(t.SKIPPED_CANCELLED) == 2 and states.count(t.ATTEMPTED) == 1
assert not m.task_lock.locked() and network_calls == []
''')


def test_restart_marks_interrupted_runs_and_never_restarts_them(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
initialize(); add_sources('alpha')
with Session.begin() as db:
    db.add(AutomationRun(task='discover', status='RUNNING',
                         report={'trigger': 'MANUAL_START', 'scope': {'source_ids': [1]}}))
    db.add(AutomationRun(task='discover', status='RUNNING',
                         report={'trigger': 'MANUAL_START', 'cancel_requested_at': '2026-09-22T00:00:00+00:00'}))
with TestClient(m.app) as c:
    time.sleep(1.0)
    runs = discover_runs()
    assert [r.status for r in runs] == ['INTERRUPTED', 'CANCELLED']
    assert all(r.report['restart'] == 'NOT_RESTARTED' for r in runs)
    assert 'not restarted' in runs[0].report['error']
    status = c.get('/api/scan/status').json()
    assert status['active'] is None and status['last']['status'] == 'CANCELLED'
    # A confirmation from before the restart cannot start anything now.
    assert c.post('/api/scan/start', json={'token': 'y' * 43}).status_code == 409
    assert m.scheduler.get_job('discover') is None
assert fetches == [] and len(discover_runs()) == 2 and network_calls == []
''')


def test_estimate_uses_this_installations_history(tmp_path):
    isolated(tmp_path, PRELUDE + r'''
initialize(); add_sources('alpha', 'beta')
with Session.begin() as db:
    for s in db.scalars(select(JobSource)): s.details = {**s.details, 'jobs_fetched': 40}
    db.add(AutomationRun(task='discover', status='COMPLETED',
                         report={'duration_seconds': 30, 'sources_attempted': 2}))
with TestClient(m.app) as c:
    w = c.post('/api/scan/preview', json={}).json()['workload']
assert w['postings_last_seen'] == 80 and w['sources_without_history'] == 0
assert w['estimated_seconds'] == 30 and 'median' in w['estimate_basis']
assert fetches == []
''')


def test_confirmation_refuses_sources_or_settings_changed_after_preview(tmp_path):
    isolated(tmp_path, PRELUDE + r"""
initialize(); add_sources('alpha', 'beta')
with TestClient(m.app) as c:
    # A source definition edited after the preview: the confirmation is refused.
    token = c.post('/api/scan/preview', json={}).json()['token']
    with Session.begin() as db:
        db.scalar(select(JobSource).where(JobSource.board == 'beta')).board = 'beta-renamed'
    r = c.post('/api/scan/start', json={'token': token})
    assert r.status_code == 409 and r.json()['scope_changed'] is True
    # The refused token is spent; it cannot be retried after the change.
    assert c.post('/api/scan/start', json={'token': token}).status_code == 409

    # Settings shown in the preview changed afterwards: refused as well.
    token = c.post('/api/scan/preview', json={}).json()['token']
    with Session.begin() as db:
        row = db.get(Settings, 1); row.value = {**row.value, 'locations': ['Riyadh']}
    r = c.post('/api/scan/start', json={'token': token})
    assert r.status_code == 409 and r.json()['scope_changed'] is True

    # Disabling a previewed source counts as a change too.
    token = c.post('/api/scan/preview', json={}).json()['token']
    with Session.begin() as db:
        db.scalar(select(JobSource).where(JobSource.board == 'alpha')).enabled = False
    assert c.post('/api/scan/start', json={'token': token}).status_code == 409
    time.sleep(0.5)
assert discover_runs() == [] and fetches == [] and network_calls == []
""")


def test_run_uses_the_confirmed_scope_even_if_things_change_mid_run(tmp_path):
    isolated(tmp_path, PRELUDE + r"""
initialize(); add_sources('alpha', 'beta')
with Session.begin() as db:
    row = db.get(Settings, 1); row.value = {**row.value, 'locations': ['Abu Dhabi', 'Al Ain']}
gate.clear()
with TestClient(m.app) as c:
    preview = c.post('/api/scan/preview', json={}).json()
    assert preview['scope']['locations'] == ['Abu Dhabi', 'Al Ain']
    run_id = c.post('/api/scan/start', json={'token': preview['token']}).json()['run_id']
    assert wait_for(lambda: len(fetches) == 1)            # alpha is mid-fetch
    with Session.begin() as db:                           # both changes happen after confirmation
        row = db.get(Settings, 1); row.value = {**row.value, 'locations': ['Riyadh']}
        db.scalar(select(JobSource).where(JobSource.board == 'beta')).url = 'https://changed.example/feed'
    gate.set()
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
assert fetches == ['alpha'], fetches                      # the edited source was not fetched
assert fetch_locations == [['Abu Dhabi', 'Al Ain']]       # the confirmed settings were used
with Session() as db:
    run = db.get(AutomationRun, run_id)
    beta = db.scalar(select(JobSource).where(JobSource.board == 'beta'))
    alpha = db.scalar(select(JobSource).where(JobSource.board == 'alpha'))
    assert run.report['scope_changed_sources'] == [beta.id]
    assert run.report['scope']['locations'] == ['Abu Dhabi', 'Al Ain']
    assert alpha.details['mode'] == 'MANUAL'              # a manual run is recorded as manual
assert network_calls == []
""")

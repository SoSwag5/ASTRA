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


def test_stop_during_progress_update_skips_the_next_source(tmp_path):
    """A Stop accepted while progress is being saved must not start that source."""
    isolated(tmp_path, PRELUDE + r'''
initialize(); add_sources('alpha', 'beta')
reached_beta = threading.Event()
continue_beta = threading.Event()
real_record_progress = m._record_progress

def paused_progress(db, run_id, report, total, done, current):
    if current == 'Fixture beta':
        reached_beta.set()
        assert continue_beta.wait(20)
    return real_record_progress(db, run_id, report, total, done, current)

m._record_progress = paused_progress
with TestClient(m.app) as c:
    token = c.post('/api/scan/preview', json={}).json()['token']
    run_id = c.post('/api/scan/start', json={'token': token}).json()['run_id']
    assert reached_beta.wait(20)
    stop = c.post('/api/scan/cancel', json={'run_id': run_id})
    assert stop.status_code == 200 and stop.json()['cancelling']
    continue_beta.set()
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
    last = c.get('/api/scan/status').json()['last']

assert fetches == ['alpha'], fetches
assert last['status'] == 'CANCELLED'
assert last['cancel_requested_at']
assert last['progress']['current_source'] is None
assert not m.task_lock.locked() and network_calls == []
''')


def test_stop_during_source_setup_skips_provider_call(tmp_path):
    """A Stop received after progress but before provider entry skips the source."""
    isolated(tmp_path, PRELUDE + r'''
from backend import discovery_telemetry as telemetry
initialize(); add_sources('alpha', 'beta')
reached_beta = threading.Event()
continue_beta = threading.Event()
real_attempt = telemetry.RunTelemetry.attempt

def paused_attempt(self, source):
    if source.name == 'Fixture beta':
        reached_beta.set()
        assert continue_beta.wait(20)
    return real_attempt(self, source)

telemetry.RunTelemetry.attempt = paused_attempt
with TestClient(m.app) as c:
    token = c.post('/api/scan/preview', json={}).json()['token']
    run_id = c.post('/api/scan/start', json={'token': token}).json()['run_id']
    assert reached_beta.wait(20)
    stop = c.post('/api/scan/cancel', json={'run_id': run_id})
    assert stop.status_code == 200 and stop.json()['cancelling']
    continue_beta.set()
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
    last = c.get('/api/scan/status').json()['last']

assert fetches == ['alpha'], fetches
assert last['status'] == 'CANCELLED'
assert last['cancel_requested_at']
with Session() as db:
    source = db.query(JobSource).filter_by(board='beta').one()
    assert 'last_attempted' not in source.details
    run = db.get(AutomationRun, run_id)
    assert [e['outcome'] for e in run.report['scope_accounting']] == ['FETCHED', 'NOT_FETCHED_CANCELLED']
    states = [s['attempt_state'] for s in run.report[telemetry.REPORT_KEY]['sources']]
    assert states == [telemetry.ATTEMPTED, telemetry.SKIPPED_CANCELLED]
assert not m.task_lock.locked() and network_calls == []
''')


def test_stop_timestamp_survives_concurrent_progress_write(tmp_path):
    """Progress and Stop must serialize their writes to the active run report."""
    isolated(tmp_path, PRELUDE + r'''
initialize(); add_sources('alpha', 'beta')
in_refresh = threading.Event()
continue_progress = threading.Event()
beta_gate = threading.Event()
real_record_progress = m._record_progress

def paused_progress(db, run_id, report, total, done, current):
    if current == 'Fixture beta':
        real_refresh = db.refresh
        def paused_refresh(row, *args, **kwargs):
            result = real_refresh(row, *args, **kwargs)
            if isinstance(row, AutomationRun):
                in_refresh.set()
                assert continue_progress.wait(20)
            return result
        db.refresh = paused_refresh
        try:
            return real_record_progress(db, run_id, report, total, done, current)
        finally:
            db.refresh = real_refresh
    return real_record_progress(db, run_id, report, total, done, current)

def bounded_discover(adapter, board, url='', cfg=None):
    fetches.append(board)
    if board == 'beta':
        assert beta_gate.wait(20)
    return []

m._record_progress = paused_progress
m.discover = bounded_discover
with TestClient(m.app) as c:
    token = c.post('/api/scan/preview', json={}).json()['token']
    run_id = c.post('/api/scan/start', json={'token': token}).json()['run_id']
    assert in_refresh.wait(20)
    responses = []
    stopping = threading.Thread(target=lambda: responses.append(c.post('/api/scan/cancel', json={'run_id': run_id})))
    stopping.start()
    time.sleep(0.1)
    continue_progress.set()
    assert wait_for(lambda: bool(responses))
    beta_gate.set()
    stopping.join(20)
    assert responses[0].status_code == 200, responses[0].text
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
    last = c.get('/api/scan/status').json()['last']

assert last['cancel_requested_at'], last
assert last['status'] in ('CANCELLED', 'COMPLETED')
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
    assert run.report['scope_changed_sources'] == [{'id': beta.id, 'name': 'Fixture beta', 'change': 'EDITED'}]
    assert run.status == 'PARTIAL'                        # the confirmed scope was not completed
    assert [e['outcome'] for e in run.report['scope_accounting']] == ['FETCHED', 'NOT_FETCHED_SCOPE_CHANGED']
    assert run.report['scope']['locations'] == ['Abu Dhabi', 'Al Ain']
    assert alpha.details['mode'] == 'MANUAL'              # a manual run is recorded as manual
assert network_calls == []
""")


# --- Independent review remediation (A1-A3) --------------------------------

def test_preview_display_and_token_binding_come_from_one_snapshot(tmp_path):
    """A1: a concurrent edit landing while the preview is being built can
    never make the page show one scope while the token binds another."""
    isolated(tmp_path, PRELUDE + r"""
import backend.scan_control as sc
initialize(); add_sources('alpha')
with Session.begin() as db:
    row = db.get(Settings, 1); row.value = {**row.value, 'locations': ['Dubai']}
real_settings = sc.settings
calls = []
def settings_then_concurrent_edit(db):
    value = real_settings(db)
    calls.append(1)
    # Another request commits right after the settings were read and before
    # the sources are read: a new source and a different location.
    with Session.begin() as other:
        row = other.get(Settings, 1); row.value = {**row.value, 'locations': ['Riyadh']}
        other.add(JobSource(name='Fixture late', adapter='lever', board='late', enabled=True))
    return value
sc.settings = settings_then_concurrent_edit
with TestClient(m.app) as c:
    preview = c.post('/api/scan/preview', json={}).json()
    sc.settings = real_settings
    bound = sc._previews[preview['token']]
    assert calls == [1]                                   # settings read exactly once
    assert preview['scope']['locations'] == ['Dubai'] == bound['cfg']['locations']
    # The late source is invisible to the whole preview snapshot, display and binding alike.
    assert [s['name'] for s in preview['scope']['sources']] == ['Fixture alpha']
    assert sorted(bound['source_defs']) == preview['scope']['source_ids']
    # The concurrent edit is caught at confirmation.
    r = c.post('/api/scan/start', json={'token': preview['token']})
    assert r.status_code == 409 and r.json()['scope_changed'] is True
assert discover_runs() == [] and fetches == [] and network_calls == []
""")


def test_every_confirmed_source_is_accounted_for_when_disabled_or_deleted_after_start(tmp_path):
    """A2: a confirmed source disabled or deleted just after confirmation is
    not fetched, and progress and the final report name it."""
    isolated(tmp_path, PRELUDE + r"""
import backend.scan_control as sc
from backend import discovery_telemetry as t
initialize(); add_sources('alpha', 'beta', 'gamma')
with TestClient(m.app) as c:
    token = c.post('/api/scan/preview', json={}).json()['token']
    confirmation = sc.confirm(token)                      # exactly what /start does first
    assert isinstance(confirmation, sc.ScanConfirmation)
    with Session.begin() as db:                           # "just after /start", before the worker runs
        db.scalar(select(JobSource).where(JobSource.board == 'beta')).enabled = False
        db.delete(db.scalar(select(JobSource).where(JobSource.board == 'gamma')))
    result = m.task('discover', confirmation=confirmation)
assert fetches == ['alpha'], fetches
report = result['report']
assert result['status'] == 'PARTIAL'
assert report['scope_changed_sources'] == [
    {'id': 2, 'name': 'Fixture beta', 'change': 'DISABLED'},
    {'id': 3, 'name': 'Fixture gamma', 'change': 'DELETED'}]
assert [(e['id'], e['outcome']) for e in report['scope_accounting']] == [
    (1, 'FETCHED'), (2, 'NOT_FETCHED_SCOPE_CHANGED'), (3, 'NOT_FETCHED_SCOPE_CHANGED')]
assert report['confirmed_scope'] == {'sources_confirmed': 3, 'sources_fetched': 1,
                                     'sources_failed': 0, 'sources_not_fetched': 2}
assert report['progress']['sources_total'] == 3 and report['progress']['sources_not_fetched'] == 2
states = {s['source_name']: s['attempt_state'] for s in report[t.REPORT_KEY]['sources']}
assert states == {'Fixture alpha': t.ATTEMPTED, 'Fixture beta': t.SKIPPED_SCOPE_CHANGED,
                  'Fixture gamma': t.SKIPPED_SCOPE_CHANGED}, states
t.validate(report[t.REPORT_KEY])
assert not m.task_lock.locked() and network_calls == []
""")


def test_disabled_mid_run_is_named_in_live_progress(tmp_path):
    isolated(tmp_path, PRELUDE + r"""
initialize(); add_sources('alpha', 'beta')
gate.clear()
with TestClient(m.app) as c:
    run_id = c.post('/api/scan/start',
                    json={'token': c.post('/api/scan/preview', json={}).json()['token']}).json()['run_id']
    assert wait_for(lambda: len(fetches) == 1)
    with Session.begin() as db:
        db.scalar(select(JobSource).where(JobSource.board == 'beta')).enabled = False
    gate.set()
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
    last = c.get('/api/scan/status').json()['last']
assert last['status'] == 'PARTIAL' and fetches == ['alpha']
assert last['progress']['sources_total'] == 2 and last['progress']['sources_done'] == 1
assert last['progress']['scope_changed_sources'] == [{'id': 2, 'name': 'Fixture beta', 'change': 'DISABLED'}]
assert last['scope_changed_sources'] == last['progress']['scope_changed_sources']
""")


def test_task_discover_requires_a_valid_single_use_confirmation(tmp_path):
    """A3: the internal task('discover') boundary enforces the Owner's rule."""
    isolated(tmp_path, PRELUDE + r"""
import backend.scan_control as sc
initialize(); add_sources('alpha')
# No confirmation, a look-alike object, and a hand-built confirmation are all refused.
assert m.task('discover')['refused'] is True
assert m.task('discover', scheduled_run=True)['refused'] is True
class Fake:
    run_id = 1; source_ids = (1,)
    def claim(self): return True
assert m.task('discover', confirmation=Fake())['refused'] is True
try:
    sc.ScanConfirmation(object(), 1, [1], {}, {}, threading.Event(), False)
    raise SystemExit('a confirmation was created outside confirm()')
except PermissionError:
    pass
assert discover_runs() == [] and fetches == [] and not m.task_lock.locked()

# A real confirmation runs once; replaying it is refused and cannot release the lock twice.
token = sc.preview(sc.PreviewRequest())['token']
confirmation = sc.confirm(token)
assert m.task_lock.locked()                               # confirm() holds the lock for the run
first = m.task('discover', confirmation=confirmation)
assert first['status'] == 'COMPLETED' and not m.task_lock.locked()
assert m.task('discover', confirmation=confirmation)['refused'] is True
assert fetches == ['alpha'] and len(discover_runs()) == 1
# A confirmation cannot be used to run a different task.
try:
    m.task('report', confirmation=confirmation); raise SystemExit('accepted')
except ValueError:
    pass
assert not m.task_lock.locked() and network_calls == []
""")


def test_expired_token_is_refused(tmp_path):
    isolated(tmp_path, PRELUDE + r"""
import backend.scan_control as sc
from datetime import timedelta
initialize(); add_sources('alpha')
with TestClient(m.app) as c:
    token = c.post('/api/scan/preview', json={}).json()['token']
    real = sc._utc
    sc._utc = lambda: real() + sc.PREVIEW_TTL + timedelta(seconds=1)
    r = c.post('/api/scan/start', json={'token': token})
    sc._utc = real
    assert r.status_code == 409 and 'expired' in r.json()['detail']
    assert c.post('/api/scan/start', json={'token': token}).status_code == 409   # pruned, not revived
assert discover_runs() == [] and fetches == [] and not m.task_lock.locked()
""")


def test_two_concurrent_starts_start_exactly_one_run(tmp_path):
    isolated(tmp_path, PRELUDE + r"""
initialize(); add_sources('alpha')
gate.clear()
with TestClient(m.app) as c:
    same = c.post('/api/scan/preview', json={}).json()['token']
    other = c.post('/api/scan/preview', json={}).json()['token']
    barrier = threading.Barrier(3)
    results = []
    def press(token):
        barrier.wait(); results.append(c.post('/api/scan/start', json={'token': token}))
    threads = [threading.Thread(target=press, args=(tok,)) for tok in (same, same, other)]
    for th in threads: th.start()
    for th in threads: th.join(20)
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409, 409], codes
    assert wait_for(lambda: len(fetches) == 1)
    gate.set()
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
assert len(discover_runs()) == 1 and fetches == ['alpha'] and not m.task_lock.locked()
""")


def test_start_is_refused_while_another_process_holds_the_lock(tmp_path):
    isolated(tmp_path, PRELUDE + r"""
import subprocess, sys
initialize(); add_sources('alpha')
holder = subprocess.Popen([sys.executable, '-c',
    'import sys\nfrom backend.reliability import ProcessLock\n'
    'p=ProcessLock(); assert p.acquire(False); print("held", flush=True); sys.stdin.readline()'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
assert holder.stdout.readline().strip() == 'held'
try:
    with TestClient(m.app) as c:
        token = c.post('/api/scan/preview', json={}).json()['token']
        r = c.post('/api/scan/start', json={'token': token})
        assert r.status_code == 409 and r.json()['busy'] is True
        assert discover_runs() == [] and fetches == []
        holder.stdin.write('\n'); holder.stdin.flush(); holder.wait(20)
        # The same confirmation can be used once the other process has finished.
        r = c.post('/api/scan/start', json={'token': token})
        assert r.status_code == 200, r.json()
        assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
finally:
    if holder.poll() is None: holder.kill()
assert len(discover_runs()) == 1 and fetches == ['alpha'] and not m.task_lock.locked()
""")


def test_worker_that_fails_to_start_leaves_nothing_stuck(tmp_path):
    """If Thread.start() raises after confirm() created a RUNNING run, the run,
    token, cancel state and lock are all cleaned up and a new scan can start."""
    isolated(tmp_path, PRELUDE + r"""
import backend.scan_control as sc
initialize(); add_sources('alpha')
real_thread = sc.threading.Thread
class BrokenThread:
    def __init__(self, *a, **k): pass
    def start(self): raise RuntimeError('cannot start new thread')
with TestClient(m.app) as c:
    token = c.post('/api/scan/preview', json={}).json()['token']
    sc.threading.Thread = BrokenThread
    r = c.post('/api/scan/start', json={'token': token})
    sc.threading.Thread = real_thread
    assert r.status_code == 500 and r.json()['start_failed'] is True, r.text
    run_id = r.json()['run_id']
    # Nothing is left RUNNING, cancellable or locked.
    runs = discover_runs()
    assert [(x.id, x.status) for x in runs] == [(run_id, 'FAILED')]
    assert 'could not start' in runs[0].report['error']
    assert not m.task_lock.locked()
    assert run_id not in sc._cancel and token not in sc._previews
    status = c.get('/api/scan/status').json()
    assert status['active'] is None and status['cancellable'] is False and status['last']['status'] == 'FAILED'
    # The failed confirmation cannot be replayed.
    assert c.post('/api/scan/start', json={'token': token}).status_code == 409
    # A fresh preview is not blocked, and a new scan runs normally.
    preview = c.post('/api/scan/preview', json={})
    assert preview.status_code == 200, preview.text
    again = c.post('/api/scan/start', json={'token': preview.json()['token']})
    assert again.status_code == 200
    assert wait_for(lambda: c.get('/api/scan/status').json()['active'] is None)
assert fetches == ['alpha'] and [r.status for r in discover_runs()] == ['FAILED', 'COMPLETED']
assert not m.task_lock.locked() and network_calls == []
""")

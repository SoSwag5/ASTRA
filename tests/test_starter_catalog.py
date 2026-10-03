"""Bundled source checks use fictional databases; no network or real accounts."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from backend.models import Base, JobSource, Job, Application
from backend.starter_catalog import catalog, seed_starter_catalog


def test_catalog_has_truthful_separate_modes():
    rows = catalog()
    assert len(rows) == 77
    assert sum(r['mode'] == 'PUBLIC_FEED' for r in rows) == 3
    assert sum(r['route_status'] in ('REACHABLE_PAGE', 'PUBLIC_FEED_OK') for r in rows) == 52
    assert sum(r['route_status'] == 'BROWSER_CHECK_REQUIRED' for r in rows) == 25
    assert any(r['group'] == 'Government' for r in rows)
    assert any(r['group'] == 'Hospitals & healthcare' for r in rows)


def test_fresh_catalog_idempotent_without_jobs_or_applications():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_starter_catalog(db, fresh_install=True)
        db.flush()
        first = [(s.id,s.name,s.adapter,s.url,s.enabled) for s in db.scalars(select(JobSource))]
        seed_starter_catalog(db)
        db.flush()
        assert first == [(s.id,s.name,s.adapter,s.url,s.enabled) for s in db.scalars(select(JobSource))]
        assert len(first) == 77
        assert sum(s.enabled for s in db.scalars(select(JobSource))) == 3
        assert not list(db.scalars(select(Job)))
        assert not list(db.scalars(select(Application)))
        assert all(not s.enabled for s in db.scalars(select(JobSource).where(JobSource.adapter=='manual')))


def test_existing_pause_custom_link_and_user_preferences_preserved():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        paused=JobSource(name='My board',adapter='greenhouse',board='cloudflare',url='https://job-boards.greenhouse.io/cloudflare',enabled=False,details={'interval_hours':72})
        edited=JobSource(name='LinkedIn',adapter='manual',url='https://careers.example.org/custom',enabled=False,details={'watching':False,'cadence':'WEEKLY','verification':'My custom destination'})
        manual=JobSource(name='Mediclinic Middle East',adapter='manual',url='https://www.mediclinic.ae/en/corporate/jobs-and-careers.html',enabled=False,details={'watching':False,'cadence':'WEEKLY','last_checked':'2026-10-01'})
        db.add_all([paused,edited,manual]);db.flush()
        ids=[s.id for s in (paused,edited,manual)]
        seed_starter_catalog(db);db.flush()
        assert [s.id for s in (paused,edited,manual)] == ids
        assert paused.enabled is False and paused.name == 'My board' and paused.details['interval_hours'] == 72
        assert edited.url == 'https://careers.example.org/custom' and edited.details == {'watching':False,'cadence':'WEEKLY','verification':'My custom destination'}
        assert manual.details['watching'] is False and manual.details['cadence'] == 'WEEKLY' and manual.details['last_checked'] == '2026-10-01'
        assert len(list(db.scalars(select(JobSource)))) == 77


STARTUP = r'''
import socket
def blocked(*args, **kwargs): raise AssertionError('Startup attempted network access')
socket.getaddrinfo = blocked
socket.create_connection = blocked
from fastapi.testclient import TestClient
from sqlalchemy import select, inspect
from backend.models import *
import backend.main as m
'''


def test_real_startup_and_process_restart_are_additive_and_offline(tmp_path):
    from tests.test_campaign_reliability import isolated
    script = STARTUP + r'''
with TestClient(m.app) as client:
    with Session() as db:
        rows = list(db.scalars(select(JobSource)))
        assert len(rows) == 77 and sum(r.enabled for r in rows) == 3
        assert db.query(Job).count() == db.query(Application).count() == 0
        ids = [(r.id, r.name, r.url, r.enabled) for r in rows]
    assert m.scheduler.get_job('discover') is None
    assert client.get('/api/scan/status').json()['active'] is None
    import json
    saved = DATA / 'catalog-identifiers.json'
    if saved.exists(): assert json.loads(saved.read_text()) == [list(r) for r in ids]
    else: saved.write_text(json.dumps(ids))
'''
    isolated(tmp_path, script, bundled_sources=True)
    isolated(tmp_path, script, bundled_sources=True)


def test_existing_workspace_without_sources_gets_only_paused_feeds(tmp_path):
    from tests.test_campaign_reliability import isolated
    isolated(tmp_path, STARTUP + r'''
initialize()
with Session.begin() as db:
    db.add(CandidateProfile(name='Fictional Graduate', raw_text='Fictional finance', confirmed=True))
    cfg = db.get(Settings, 1); cfg.value = {**cfg.value, 'custom_target_roles':['Financial Analyst'], 'search_focus_confirmed':True}
    job = Job(title='Fictional Analyst', company='Fictional Employer'); db.add(job); db.flush()
    db.add(Application(job_id=job.id, status='APPLIED'))
with TestClient(m.app) as client:
    with Session() as db:
        rows = list(db.scalars(select(JobSource)))
        assert len(rows) == 77 and not any(r.enabled for r in rows)
        assert db.query(Job).count() == db.query(Application).count() == 1
        assert db.query(CandidateProfile).one().confirmed is True
        assert db.get(Settings, 1).value['custom_target_roles'] == ['Financial Analyst']
    assert client.get('/api/scan/status').json()['active'] is None
''', bundled_sources=True)


def test_demo_startup_does_not_seed_a_workspace(tmp_path):
    from tests.test_campaign_reliability import isolated
    isolated(tmp_path, "import os\nos.environ['ASTRA_DEMO_ONLY']='1'\n" + STARTUP + r'''
with TestClient(m.app):
    assert not inspect(engine).has_table(Settings.__tablename__)
''', bundled_sources=True)


def _installer(tmp_path):
    """Run the real installer step (scripts/initialize.py) in its own process, as setup.bat does."""
    import os, subprocess, sys
    from pathlib import Path
    data = tmp_path / 'data'
    env = {**os.environ, 'HUNTER_DATA_DIR': str(data), 'DATABASE_URL': f'sqlite:///{data / "isolated.db"}', 'APP_TOKEN': ''}
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'scripts' / 'initialize.py')], capture_output=True, text=True, env=env, timeout=90, cwd=root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_installer_then_startup_enables_exactly_the_starter_feeds_and_preserves_choices(tmp_path):
    from tests.test_campaign_reliability import isolated
    _installer(tmp_path)
    isolated(tmp_path, STARTUP + r'''
with TestClient(m.app) as client:
    with Session() as db:
        rows = list(db.scalars(select(JobSource)))
        assert len(rows) == 77, len(rows)
        assert sorted(r.name for r in rows if r.enabled) == sorted(r.name for r in rows if r.adapter != 'manual')
        assert sum(r.enabled for r in rows) == 3
        assert db.query(Job).count() == db.query(Application).count() == db.query(AutomationRun).count() == 0
    assert m.scheduler.get_job('discover') is None
    assert client.get('/api/scan/status').json()['active'] is None
# The user pauses a starter feed and edits a manual destination.
with Session.begin() as db:
    feed = db.scalars(select(JobSource).where(JobSource.adapter == 'greenhouse')).first(); feed.enabled = False
    manual = db.scalars(select(JobSource).where(JobSource.adapter == 'manual')).first()
    manual.url = 'https://careers.example.org/mine'; manual.details = {**manual.details, 'watching': False}
    snapshot = sorted((r.id, r.name, r.url, r.enabled) for r in db.scalars(select(JobSource)))
    import json; (DATA / 'snapshot.json').write_text(json.dumps(snapshot))
''', bundled_sources=True)
    _installer(tmp_path)  # repeated setup
    isolated(tmp_path, STARTUP + r'''
import json
with TestClient(m.app):
    with Session() as db:
        now = sorted((r.id, r.name, r.url, r.enabled) for r in db.scalars(select(JobSource)))
        assert [list(r) for r in now] == json.loads((DATA / 'snapshot.json').read_text())
        assert sum(r.enabled for r in db.scalars(select(JobSource))) == 2
''', bundled_sources=True)


def test_installer_on_existing_zero_source_workspace_adds_only_paused_feeds(tmp_path):
    from tests.test_campaign_reliability import isolated
    isolated(tmp_path, STARTUP + r'''
initialize()
with Session.begin() as db:
    cfg = db.get(Settings, 1); cfg.value = {**cfg.value, 'custom_target_roles': ['Financial Analyst']}
''', bundled_sources=True)
    _installer(tmp_path)
    isolated(tmp_path, STARTUP + r'''
with Session() as db:
    rows = list(db.scalars(select(JobSource)))
    assert len(rows) == 77 and not any(r.enabled for r in rows)
    assert db.get(Settings, 1).value['custom_target_roles'] == ['Financial Analyst']
''', bundled_sources=True)

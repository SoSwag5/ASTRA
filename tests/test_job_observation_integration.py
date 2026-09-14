"""Issue #40 end-to-end integration: migration/backfill, privacy export/
delete, and provenance mapping for each discovery path (Greenhouse/Lever/
Ashby ProviderRecord, SmartRecruiters legacy wrapper, manual input). Runs
in isolated subprocesses with synthetic storage, matching tests/
test_privacy_review.py's pattern, because backend.models module-level
`engine`/`Session` are bound once at import time from HUNTER_DATA_DIR/
DATABASE_URL.
"""
import os
import subprocess
import sys

from sqlalchemy import select

from backend.job_providers.contracts import ProviderRecord, VERSION as PROVIDER_VERSION
from backend.job_providers.compatibility import LegacyJobDict, to_legacy_items
from backend.models import Base, Job, JobObservation, JobSource, now
from backend.services import add_job


def isolated(tmp_path, script):
    data = tmp_path / 'data'
    env = {**os.environ, 'HUNTER_DATA_DIR': str(data),
           'DATABASE_URL': f'sqlite:///{data / "current.db"}', 'APP_TOKEN': ''}
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


# ---- migration / backfill (subprocess: exercises the real initialize()) ----

def test_legacy_jobs_get_exactly_one_backfilled_observation(tmp_path):
    isolated(tmp_path, r'''
from sqlalchemy import select
from backend.models import initialize, Session, Job, JobObservation
initialize()
with Session.begin() as db:
    db.add(Job(company='Acme', title='SOC Analyst', location='Dubai', source='Greenhouse',
                source_job_id='777', job_url='https://boards.greenhouse.io/acme/jobs/777',
                date_posted='2026-01-01T00:00:00Z', date_found='2026-01-02T00:00:00Z'))
    db.add(Job(company='Manual Co', title='Analyst', source='Manual'))
# A second startup (initialize() again) must not duplicate the backfill.
initialize()
with Session() as db:
    obs = list(db.scalars(select(JobObservation)))
    assert len(obs) == 2, obs
    by_company = {o.employer_name_observed: o for o in obs}
    gh = by_company['Acme']
    assert gh.identity_kind == 'legacy_incomplete'
    assert gh.provider_family == 'greenhouse'
    assert gh.provider_job_id == '777'
    assert gh.posted_at == '2026-01-01T00:00:00Z'
    assert gh.posted_at_authority == 'legacy_carried_forward'
    manual = by_company['Manual Co']
    assert manual.identity_kind == 'legacy_incomplete'
    assert manual.provider_family == 'legacy'
''')


def test_backfill_never_touches_a_job_that_already_has_an_observation(tmp_path):
    isolated(tmp_path, r'''
from sqlalchemy import select, func
from backend.models import initialize, Session, Job, JobObservation
from backend.services import add_job
initialize()
with Session.begin() as db:
    add_job(db, {'company': 'Fresh Co', 'title': 'SOC Analyst'})
with Session() as db:
    count_before = db.scalar(select(func.count()).select_from(JobObservation))
initialize()  # re-running startup must not add a legacy_incomplete row for this already-observed job
with Session() as db:
    count_after = db.scalar(select(func.count()).select_from(JobObservation))
    assert count_after == count_before
    row = db.scalar(select(JobObservation))
    assert row.identity_kind != 'legacy_incomplete'
''')


# ---- privacy: JobObservation shares Job's export/delete lifecycle ----

def test_privacy_counts_include_job_observations(tmp_path):
    isolated(tmp_path, r'''
from backend.models import initialize, Session
from backend.services import add_job
import backend.privacy as privacy
initialize()
with Session.begin() as db:
    add_job(db, {'company': 'Acme', 'title': 'SOC Analyst'})
info = privacy.privacy_info()
assert info['counts']['job_observations'] == 1
''')


def test_delete_all_removes_job_observations(tmp_path):
    isolated(tmp_path, r'''
from sqlalchemy import select, func
from backend.models import initialize, Session, JobObservation
from backend.services import add_job
import backend.privacy as privacy
initialize()
privacy.delete_credential = lambda name: None
with Session.begin() as db:
    add_job(db, {'company': 'Acme', 'title': 'SOC Analyst'})
result = privacy.delete_data(privacy.DeleteRequest(scope='all', confirmation='DELETE ALL LOCAL DATA'))
assert result['deleted'] == 'all'
with Session() as db:
    assert db.scalar(select(func.count()).select_from(JobObservation)) == 0
''')


def test_delete_history_scope_preserves_job_observations(tmp_path):
    isolated(tmp_path, r'''
from sqlalchemy import select, func
from backend.models import initialize, Session, JobObservation
from backend.services import add_job
import backend.privacy as privacy
initialize()
with Session.begin() as db:
    add_job(db, {'company': 'Acme', 'title': 'SOC Analyst'})
result = privacy.delete_data(privacy.DeleteRequest(scope='history', confirmation='DELETE APPLICATION HISTORY'))
assert result['deleted'] == 'history'
with Session() as db:
    assert db.scalar(select(func.count()).select_from(JobObservation)) == 1
''')


# ---- provenance mapping: ProviderRecord -> JobObservation (in-process, no subprocess needed) ----

def _record(**overrides):
    fields = dict(provider='lever', source_board='acme', provider_job_id='1', title='SOC Analyst',
                  location='Dubai', description='x' * 60, apply_url='https://jobs.lever.co/acme/1/apply',
                  source_url='https://jobs.lever.co/acme/1', posted_at='', closing_at='',
                  remote_status='Remote', retrieved_at=now(), provider_version=PROVIDER_VERSION, raw_fields={})
    fields.update(overrides)
    return ProviderRecord(**fields)


class _DB:
    """Minimal throwaway session for these in-process provenance checks."""


def _session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as OrmSession
    e = create_engine('sqlite://')
    Base.metadata.create_all(e)
    return OrmSession(e, expire_on_commit=False)


def test_lever_created_at_never_becomes_authoritative_posted_at():
    record = _record(provider='lever', posted_at='', raw_fields={'createdAt_observed': '2026-01-01T00:00:00Z',
                                                                    'posted_at_provenance': 'undocumented_createdAt_field_not_promoted_to_date_posted'})
    item = LegacyJobDict({'company': 'acme', 'title': record.title, 'location': record.location,
                           'job_url': record.source_url, 'description': record.description, 'source': 'Lever',
                           'source_job_id': record.provider_job_id, 'date_posted': record.posted_at,
                           'closing_date': '', 'remote_status': record.remote_status}, record)
    with _session() as db:
        job, dup = add_job(db, item)
        assert job.date_posted == ''
        row = db.scalar(select(JobObservation).where(JobObservation.job_id == job.id))
        assert row.posted_at_authority == 'none'
        assert row.provider_facts.get('createdAt_observed') == '2026-01-01T00:00:00Z'


def test_ashby_url_fallback_identity_kind_is_preserved():
    record = _record(provider='ashby', provider_job_id='https://jobs.ashbyhq.com/acme/soc-analyst',
                      raw_fields={'identity_fallback': 'jobUrl'})
    item = LegacyJobDict({'company': 'acme', 'title': record.title, 'location': record.location,
                           'job_url': record.source_url, 'description': record.description, 'source': 'Ashby',
                           'source_job_id': record.provider_job_id, 'date_posted': '', 'closing_date': '',
                           'remote_status': record.remote_status}, record)
    with _session() as db:
        job, dup = add_job(db, item)
        row = db.scalar(select(JobObservation).where(JobObservation.job_id == job.id))
        assert row.identity_kind == 'url_fallback'


def test_source_and_apply_url_stay_separate_through_add_job():
    record = _record(source_url='https://jobs.lever.co/acme/1', apply_url='https://jobs.lever.co/acme/1/apply')
    item = LegacyJobDict({'company': 'acme', 'title': record.title, 'location': record.location,
                           'job_url': record.source_url, 'description': record.description, 'source': 'Lever',
                           'source_job_id': record.provider_job_id, 'date_posted': '', 'closing_date': '',
                           'remote_status': record.remote_status}, record)
    with _session() as db:
        job, dup = add_job(db, item)
        assert job.job_url == 'https://jobs.lever.co/acme/1'
        assert job.apply_url == 'https://jobs.lever.co/acme/1/apply'
        row = db.scalar(select(JobObservation).where(JobObservation.job_id == job.id))
        assert row.source_url == 'https://jobs.lever.co/acme/1'
        assert row.apply_url == 'https://jobs.lever.co/acme/1/apply'


def test_manual_job_entry_produces_a_manual_observation():
    with _session() as db:
        job, dup = add_job(db, {'company': 'Acme', 'title': 'SOC Analyst', 'description': 'x' * 60})
        row = db.scalar(select(JobObservation).where(JobObservation.job_id == job.id))
        assert row.identity_kind == 'manual'
        assert row.provider_family == 'manual'


def test_smartrecruiters_legacy_dict_produces_a_native_observation_scoped_to_its_source():
    with _session() as db:
        source = JobSource(name='Acme SmartRecruiters', adapter='smartrecruiters', board='acme', enabled=True)
        db.add(source); db.flush()
        item = {'company': 'Acme', 'title': 'SOC Analyst', 'location': 'Dubai', 'job_url': 'https://jobs.smartrecruiters.com/acme/1',
                'description': 'x' * 60, 'source': 'SmartRecruiters', 'source_job_id': '1', 'date_posted': '2026-01-01',
                'remote_status': 'UNKNOWN'}
        job, dup = add_job(db, item, job_source=source)
        row = db.scalar(select(JobObservation).where(JobObservation.job_id == job.id))
        assert row.identity_kind == 'native'
        assert row.provider_family == 'smartrecruiters'
        assert row.job_source_id == source.id


def test_provider_batch_flows_through_compatibility_seam_into_observations(monkeypatch):
    """Full seam: FetchBatch -> to_legacy_items() -> add_job() carries the
    ProviderRecord all the way through, not just a hand-built LegacyJobDict.
    """
    from backend.job_providers.contracts import FetchBatch, FetchCompletion, SourceHealth, SourceMetrics
    record = _record()
    batch = FetchBatch('lever', 'acme', FetchCompletion.COMPLETE, SourceHealth.HEALTHY, [record], SourceMetrics())
    items = to_legacy_items(batch)
    with _session() as db:
        job, dup = add_job(db, items[0])
        row = db.scalar(select(JobObservation).where(JobObservation.job_id == job.id))
        assert row.provider_family == 'lever'
        assert row.provider_job_id == record.provider_job_id

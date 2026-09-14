"""Regression tests for independent-review findings D40-01 through D40-06."""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session as OrmSession

from backend import deduplication
from backend.job_providers.compatibility import LegacyJobDict
from backend.job_providers.contracts import ProviderRecord, VERSION as PROVIDER_VERSION
from backend.models import Base, Job, JobObservation, JobSource, now
from backend.normalization import JobObservationInput, employer_key
from backend.services import add_job

CORPUS = json.loads((Path(__file__).parent / 'fixtures' / 'job_dedupe_corpus.json').read_text())


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with OrmSession(engine, expire_on_commit=False) as session:
        yield session


def _provider_item(source_url, apply_url, provider_job_id='provider-1', company='Fictional Corp',
                   title='SOC Analyst', description='x' * 80, provider='lever'):
    record = ProviderRecord(
        provider=provider, source_board='fictional-board', provider_job_id=provider_job_id,
        title=title, location='Dubai', description=description,
        apply_url=apply_url, source_url=source_url, posted_at='', closing_at='',
        remote_status='On-site', retrieved_at=now(), provider_version=PROVIDER_VERSION,
        raw_fields={},
    )
    return LegacyJobDict({
        'company': company, 'title': record.title, 'location': record.location,
        'job_url': source_url, 'description': record.description,
        'source': {'greenhouse': 'Greenhouse', 'ashby': 'Ashby', 'lever': 'Lever'}[provider],
        'source_job_id': provider_job_id, 'date_posted': '', 'closing_date': '',
        'remote_status': record.remote_status,
    }, record)


@pytest.mark.parametrize('root_url', CORPUS['generated_attacks']['generic_ats_roots'])
def test_generic_ats_root_never_destructively_merges_distinct_jobs(db, root_url):
    first = {'company': 'Fictional Corp', 'title': 'SOC Analyst', 'location': 'Dubai',
             'description': 'First role has monitoring and incident response responsibilities.' * 2,
             'job_url': root_url}
    second = {'company': 'Fictional Corp', 'title': 'Security Engineer', 'location': 'Dubai',
              'description': 'Second role has platform engineering and automation responsibilities.' * 2,
              'job_url': root_url}
    assert add_job(db, first)[1] is None
    assert add_job(db, second)[1] is None
    assert len(list(db.scalars(select(Job)))) == 2


def test_cross_provider_fingerprint_alone_is_candidate_not_match(db):
    description = 'Copied evergreen security monitoring template used for several separate vacancies at one employer.'
    first = JobObservationInput(
        provider_family='greenhouse', identity_kind='native', provider_job_id='gh-1',
        job_source_id=1, employer_name='Fictional Corp', title='SOC Analyst',
        location='Dubai', description=description,
        source_url='https://boards.greenhouse.io/fictional/jobs/gh-1',
    )
    second = JobObservationInput(
        provider_family='lever', identity_kind='native', provider_job_id='lever-2',
        job_source_id=2, employer_name='Fictional Corp', title='SOC Analyst',
        location='Dubai', description=description,
        source_url='https://jobs.lever.co/fictional/lever-2',
    )
    fingerprint = deduplication.composite_fingerprint(first)
    job = Job(company='Fictional Corp', title='SOC Analyst', location='Dubai',
              description=description, dedupe_fingerprint=fingerprint,
              normalized_employer_key=employer_key('Fictional Corp') or '')
    db.add(job); db.flush()
    decision = deduplication.resolve(db, second)
    assert decision.decision == deduplication.CANDIDATE
    assert decision.method == 'cross_provider_fingerprint_candidate'
    assert decision.candidate_job_ids == (job.id,)


def test_generated_corpus_long_description_tail_remains_identity_significant():
    from backend.normalization import content_fingerprint
    attack = CORPUS['generated_attacks']['long_description_tail']
    prefix = 'a' * attack['common_prefix_length']
    assert content_fingerprint(prefix + attack['tail_a']) != content_fingerprint(prefix + attack['tail_b'])


def test_repeated_strong_identity_recomputes_fingerprint_from_canonical_fields(db):
    source = JobSource(name='Fictional Lever', adapter='lever', board='fictional-board', enabled=True)
    db.add(source); db.flush()
    source_url = 'https://jobs.lever.co/fictional/provider-1'
    original = _provider_item(source_url, source_url + '/apply', company='Alpha Fictional',
                              title='Security Engineer', description='Alpha canonical content ' * 5)
    canonical, duplicate = add_job(db, original, job_source=source)
    assert duplicate is None
    original_fingerprint = deduplication.canonical_fingerprint(canonical)

    changed_observation = _provider_item(
        source_url, source_url + '/apply', company='Beta Fictional', title='SOC Analyst',
        description='Beta observation content that must not become canonical identity ' * 3,
    )
    matched, duplicate = add_job(db, changed_observation, job_source=source)
    assert duplicate and matched.id == canonical.id
    assert matched.company == 'Alpha Fictional'
    assert matched.title == 'Security Engineer'
    assert matched.description == 'Alpha canonical content ' * 5
    assert matched.dedupe_fingerprint == original_fingerprint
    assert matched.dedupe_fingerprint == deduplication.canonical_fingerprint(matched)
    incoming = JobObservationInput(
        employer_name='Beta Fictional', title='SOC Analyst',
        description='Beta observation content that must not become canonical identity ' * 3,
    )
    assert matched.dedupe_fingerprint != deduplication.composite_fingerprint(incoming)


def test_repeated_provider_observation_updates_one_observation(db):
    source = JobSource(name='Fictional Lever', adapter='lever', board='fictional-board', enabled=True)
    db.add(source); db.flush()
    item = _provider_item('https://jobs.lever.co/fictional/repeat-1',
                          'https://apply.fictional.example/repeat-1', provider_job_id='repeat-1')
    first, duplicate = add_job(db, item, job_source=source)
    assert duplicate is None
    second, duplicate = add_job(db, item, job_source=source)
    assert duplicate and second.id == first.id
    assert len(list(db.scalars(select(Job)))) == 1
    assert len(list(db.scalars(select(JobObservation)))) == 1


def test_distinct_cross_provider_evergreen_postings_persist_separately(db):
    description = 'Copied evergreen monitoring, incident triage, escalation, and reporting template. ' * 2
    greenhouse = JobSource(name='Fictional Greenhouse', adapter='greenhouse', board='fictional-board', enabled=True)
    lever = JobSource(name='Fictional Lever', adapter='lever', board='fictional-board', enabled=True)
    db.add_all((greenhouse, lever)); db.flush()
    first = _provider_item('https://boards.greenhouse.io/fictional/jobs/evergreen-1',
                           'https://apply.fictional.example/evergreen-1', provider_job_id='evergreen-1',
                           description=description, provider='greenhouse')
    second = _provider_item('https://jobs.lever.co/fictional/evergreen-2',
                            'https://apply.fictional.example/evergreen-2', provider_job_id='evergreen-2',
                            description=description, provider='lever')
    assert add_job(db, first, job_source=greenhouse)[1] is None
    assert add_job(db, second, job_source=lever)[1] is None
    assert len(list(db.scalars(select(Job)))) == 2
    assert len(list(db.scalars(select(JobObservation)))) == 2


@pytest.mark.parametrize('order', CORPUS['generated_attacks']['transitive_bridge_orders'])
def test_transitive_bridge_never_collapses_in_any_insertion_order(db, order):
    shared_url = 'https://careers.fictional.example/postings/shared-url'
    rows = {
        'A': {'company': 'Alpha Fictional', 'title': 'Security Engineer', 'location': 'Dubai',
              'description': 'Alpha-specific engineering duties and platform ownership ' * 2,
              'job_url': shared_url},
        'B': {'company': 'Beta Fictional', 'title': 'SOC Analyst', 'location': 'Dubai',
              'description': 'Copied SOC monitoring, triage, escalation, and reporting template ' * 2,
              'job_url': shared_url},
        'C': {'company': 'Beta Fictional', 'title': 'SOC Analyst', 'location': 'Dubai',
              'description': 'Copied SOC monitoring, triage, escalation, and reporting template ' * 2,
              'job_url': 'https://careers.fictional.example/postings/different-url'},
    }
    outcomes = [add_job(db, rows[label])[1] for label in order]
    assert all(outcome is None for outcome in outcomes)
    assert len(list(db.scalars(select(Job)))) == 3


@pytest.mark.parametrize('size', (200, 1000, 5000))
def test_normalized_employer_candidate_lookup_uses_index_not_table_scan(db, size):
    for i in range(size):
        db.add(Job(company=f'Unrelated {i}', normalized_employer_key=f'unrelated {i}', title='Barista'))
    db.add(Job(company='Fictional Corp', normalized_employer_key='fictional corp', title='Analyst'))
    db.flush()
    plan = list(db.execute(text(
        'EXPLAIN QUERY PLAN SELECT * FROM jobs WHERE normalized_employer_key = :key LIMIT 10'
    ), {'key': 'fictional corp'}))
    detail = ' | '.join(str(row[-1]) for row in plan).upper()
    assert 'USING INDEX IX_JOBS_NORMALIZED_EMPLOYER_KEY' in detail, detail
    assert 'SCAN JOBS' not in detail, detail


def test_manual_empty_original_url_is_filled_by_matched_provider_evidence(db):
    source_url = 'https://jobs.lever.co/fictional/provider-1'
    apply_url = 'https://apply.fictional.example/provider-1'
    canonical, duplicate = add_job(db, {
        'company': 'Fictional Corp', 'title': 'SOC Analyst', 'location': 'Dubai',
        'remote_status': 'On-site', 'description': 'x' * 80, 'job_url': source_url,
    })
    assert duplicate is None
    canonical.job_url = ''  # reproduces the reviewed empty-original/canonical-identity state
    source = JobSource(name='Fictional Lever', adapter='lever', board='fictional-board', enabled=True)
    db.add(source); db.flush()
    matched, duplicate = add_job(db, _provider_item(source_url, apply_url), job_source=source)
    assert duplicate and matched.id == canonical.id
    assert matched.job_url == source_url
    assert matched.canonical_url == source_url
    assert matched.apply_url == apply_url
    observations = list(db.scalars(select(JobObservation).where(JobObservation.job_id == canonical.id)))
    assert len(observations) == 2
    provider_observation = next(row for row in observations if row.provider_family == 'lever')
    assert provider_observation.source_url == source_url
    assert provider_observation.apply_url == apply_url


def test_known_original_url_is_not_overwritten_and_apply_url_stays_distinct(db):
    original = 'https://jobs.lever.co/fictional/provider-1?utm_source=manual'
    observed = 'https://jobs.lever.co/fictional/provider-1?utm_source=provider'
    apply_url = 'https://apply.fictional.example/provider-1'
    canonical = Job(company='Fictional Corp', title='SOC Analyst', location='Dubai',
                    remote_status='On-site', description='x' * 80, job_url=original,
                    canonical_url='https://jobs.lever.co/fictional/provider-1',
                    normalized_employer_key='fictional corp')
    db.add(canonical)
    source = JobSource(name='Fictional Lever', adapter='lever', board='fictional-board', enabled=True)
    db.add(source); db.flush()
    matched, duplicate = add_job(db, _provider_item(observed, apply_url), job_source=source)
    assert duplicate and matched.id == canonical.id
    assert matched.job_url == original
    assert matched.apply_url == apply_url

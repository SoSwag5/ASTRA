"""Issue #40 deduplication tests: corpus-driven (tests/fixtures/job_dedupe_
corpus.json) plus targeted regressions for the non-transitive-bridge
invariant and indexed (non-quadratic) candidate lookup.
"""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session as OrmSession

from backend.models import Base, Job, JobObservation, now
from backend.normalization import JobObservationInput, canonical_view, NORMALIZATION_VERSION
from backend import deduplication
from backend.deduplication import DedupeDecision, MATCH, CANDIDATE, DISTINCT, composite_fingerprint
from backend.services import apply_canonical_updates

CORPUS = json.loads((Path(__file__).parent / 'fixtures' / 'job_dedupe_corpus.json').read_text())


@pytest.fixture
def db():
    e = create_engine('sqlite://')
    Base.metadata.create_all(e)
    with OrmSession(e, expire_on_commit=False) as db:
        yield db


def _observation(fields):
    return JobObservationInput(**fields)


def _seed_job(db, observation):
    """Mirrors backend.services.add_job()'s DISTINCT-path Job/JobObservation
    construction using the same helper functions under test, without going
    through the dict-based ingestion layer (that seam is covered by
    tests/test_core.py and tests/test_job_providers.py).
    """
    view = canonical_view(observation)
    job = Job(company=view.company, title=view.title, location=view.location, remote_status=view.remote_status,
              job_url=view.job_url, canonical_url=view.canonical_url, apply_url=view.apply_url,
              date_posted=view.date_posted, closing_date=view.closing_date, description=view.description,
              source=observation.provider_family, source_job_id=observation.provider_job_id,
              dedupe_fingerprint=composite_fingerprint(observation), normalization_version=NORMALIZATION_VERSION)
    db.add(job); db.flush()
    row = JobObservation(job_id=job.id, job_source_id=observation.job_source_id, provider_family=observation.provider_family,
                          identity_kind=observation.identity_kind, provider_job_id=observation.provider_job_id,
                          requisition_id=observation.requisition_id, requisition_id_authority=observation.requisition_id_authority,
                          employer_name_observed=observation.employer_name, title_observed=observation.title,
                          location_observed=observation.location, workplace_observed=observation.workplace,
                          description_observed=observation.description, source_url=observation.source_url,
                          apply_url=observation.apply_url, first_seen_at=now(), last_seen_at=now())
    db.add(row); db.flush()
    return job


# ---- MUST_COLLAPSE: every pair, tested in both input orders ----

@pytest.mark.parametrize('group', CORPUS['must_collapse'], ids=lambda g: g['id'])
def test_must_collapse_forward_order(db, group):
    obs = [_observation(o) for o in group['observations']]
    job = _seed_job(db, obs[0])
    for later in obs[1:]:
        decision = deduplication.resolve(db, later)
        assert decision.decision == MATCH, f'{group["id"]}: expected MATCH, got {decision.decision} ({decision.method})'
        assert decision.selected_job_id == job.id


@pytest.mark.parametrize('group', CORPUS['must_collapse'], ids=lambda g: g['id'])
def test_must_collapse_reverse_order(db, group):
    """Order-independence: seeding with the LAST observation first and
    resolving the earlier one(s) against it must collapse identically.
    """
    obs = [_observation(o) for o in group['observations']]
    job = _seed_job(db, obs[-1])
    for earlier in reversed(obs[:-1]):
        decision = deduplication.resolve(db, earlier)
        assert decision.decision == MATCH, f'{group["id"]} (reversed): expected MATCH, got {decision.decision}'
        assert decision.selected_job_id == job.id


# ---- MUST_NOT_COLLAPSE: never MATCH ----

@pytest.mark.parametrize('group', CORPUS['must_not_collapse'], ids=lambda g: g['id'])
def test_must_not_collapse(db, group):
    if group['id'] == 'MN15_three_record_transitive_bridge':
        pytest.skip('covered by test_three_record_transitive_bridge_never_collapses')
    obs = [_observation(o) for o in group['observations']]
    _seed_job(db, obs[0])
    decision = deduplication.resolve(db, obs[1])
    assert decision.decision != MATCH, f'{group["id"]}: must never auto-merge, got {decision.decision} ({decision.method})'


# ---- CANDIDATE_ONLY: never MATCH (CANDIDATE or DISTINCT both acceptable) ----

@pytest.mark.parametrize('group', CORPUS['candidate_only'], ids=lambda g: g['id'])
def test_candidate_only_never_auto_merges(db, group):
    obs = [_observation(o) for o in group['observations']]
    _seed_job(db, obs[0])
    decision = deduplication.resolve(db, obs[1])
    assert decision.decision != MATCH, f'{group["id"]}: weak evidence must never auto-merge, got {decision.decision}'


# ---- Non-transitive bridge: the actual production merge path (resolve + apply_canonical_updates) ----

def test_three_record_transitive_bridge_never_collapses(db):
    """A matches B (same source URL), B matches into Job_A without changing
    its already-known location, and C would match Job_A's fingerprint but
    genuinely conflicts with Job_A's (still A's own) location -- proving a
    connection made THROUGH B never lets C silently join a cluster it
    actually conflicts with.
    """
    desc = 'Monitor SIEM alerts, triage incidents, and escalate confirmed threats to the response team during business hours.'
    a = _observation(dict(provider_family='manual', identity_kind='manual', employer_name='Acme Corp',
                           title='SOC Analyst', location='Dubai', description=desc,
                           source_url='https://acme.example.com/jobs/one'))
    b = _observation(dict(provider_family='manual', identity_kind='manual', employer_name='Acme Corp',
                           title='SOC Analyst', location='UNKNOWN', description=desc,
                           source_url='https://acme.example.com/jobs/one'))
    c = _observation(dict(provider_family='manual', identity_kind='manual', employer_name='Acme Corp',
                           title='SOC Analyst', location='Berlin', description=desc,
                           source_url='https://acme.example.com/jobs/three'))

    job_a = _seed_job(db, a)

    decision_b = deduplication.resolve(db, b)
    assert decision_b.decision == MATCH and decision_b.selected_job_id == job_a.id
    apply_canonical_updates(job_a, b)  # the real merge side-effect add_job() applies
    assert job_a.location == 'Dubai'  # B never overwrote A's already-known location

    decision_c = deduplication.resolve(db, c)
    assert decision_c.decision != MATCH, 'C must not silently join the A/B cluster despite conflicting with A'
    if decision_c.decision == CANDIDATE:
        assert 'location_conflict' in decision_c.hard_conflicts


# ---- Indexed candidate lookup: bounded query count regardless of table size ----

def test_resolve_does_not_scan_every_job(db):
    """Phase 14: candidate lookup must be indexed equality lookups, not an
    all-Job scan. Seeds many unrelated Jobs, then asserts the number of SQL
    statements resolve() issues does not grow with table size.
    """
    for i in range(200):
        db.add(Job(company=f'Unrelated {i}', title='Barista', location='Nowhere'))
    db.flush()
    observation = _observation(dict(provider_family='greenhouse', identity_kind='native', provider_job_id='42',
                                     job_source_id=1, employer_name='Acme Corp', title='SOC Analyst', location='Dubai'))
    statements = []
    def _count(conn, cursor, statement, *a, **kw):
        statements.append(statement)
    event.listen(db.get_bind(), 'before_cursor_execute', _count)
    try:
        deduplication.resolve(db, observation)
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', _count)
    assert len(statements) < 10, f'expected a handful of indexed lookups, saw {len(statements)}'


# ---- DedupeDecision / versioning ----

def test_decision_carries_reviewable_reason_and_version():
    decision = DedupeDecision(DISTINCT, 'no_match')
    assert decision.version == deduplication.DEDUPE_VERSION
    assert decision.method
    assert decision.decision in (MATCH, DISTINCT, CANDIDATE)


def test_resolve_on_empty_db_is_distinct_with_a_reason(db):
    observation = _observation(dict(provider_family='manual', identity_kind='manual', employer_name='Acme Corp', title='SOC Analyst'))
    decision = deduplication.resolve(db, observation)
    assert decision.decision == DISTINCT
    assert decision.method == 'no_match'
    assert decision.version == deduplication.DEDUPE_VERSION


def test_composite_fingerprint_requires_all_three_signals():
    partial = _observation(dict(employer_name='Acme Corp', title='SOC Analyst', description=''))
    assert composite_fingerprint(partial) == ''
    full = _observation(dict(employer_name='Acme Corp', title='SOC Analyst',
                              description='Monitor SIEM alerts, triage incidents, and escalate confirmed threats during business hours.'))
    assert composite_fingerprint(full) != ''

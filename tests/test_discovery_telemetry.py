"""Issue #43: discovery funnel telemetry.

Covers the versioned contract itself (stage definitions, monotonicity,
failure-versus-zero, run aggregation, engagement outcomes, version metadata,
privacy bounds), the real backend.main.task('discover') integration (through a confirmed Start Scan), the
90-day retention boundary, and the read-only local API.

Every integration case drives the REAL discovery loop through
`tests.test_campaign_reliability.isolated` (a separate process with its own
temporary database) so nothing here depends on, or writes to, live records.
All job data is synthetic.
"""
import json

import pytest

from backend import discovery_telemetry as telemetry
from tests.test_campaign_reliability import isolated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def decision(hard=(), location_compatible=True, eligibility='ELIGIBLE'):
    return {'hard': [{'code': code, 'evidence': 'synthetic'} for code in hard],
            'soft': [], 'excluded': bool(hard),
            'location_compatible': location_compatible,
            'eligibility': {'state': eligibility, 'scope': 'synthetic', 'evidence': []}}


class FakeSource:
    def __init__(self, id, name='Synthetic board', adapter='greenhouse'):
        self.id = id
        self.name = name
        self.adapter = adapter


def attempt(source_id=1, name='Synthetic board', adapter='greenhouse'):
    return telemetry.SourceAttempt(source_id, name, adapter)


COMPLETE = {'completion': 'COMPLETE', 'health': 'HEALTHY', 'completion_reason': None,
            'metrics': None, 'error': None}
EMPTY = {'completion': 'COMPLETE', 'health': 'EMPTY', 'completion_reason': None,
         'metrics': None, 'error': None}
PARTIAL = {'completion': 'PARTIAL', 'health': 'PARTIAL',
           'completion_reason': 'DETAIL_BUDGET_EXHAUSTED', 'metrics': None, 'error': None}
FAILED = {'completion': 'FAILED', 'health': 'UNAVAILABLE', 'completion_reason': 'TRANSPORT_ERROR',
          'metrics': None, 'error': {'code': 'READ_TIMEOUT', 'message': 'private diagnostic'}}


class FakeRun:
    def __init__(self, report, status='COMPLETED', id=1):
        self.id = id
        self.report = report
        self.status = status
        self.created_at = '2026-09-16T00:00:00+00:00'
        self.updated_at = '2026-09-16T00:00:01+00:00'


def run_payload(*attempts, run_status='COMPLETED'):
    run = telemetry.RunTelemetry(run_id=7, trigger='MANUAL',
                                 started_at='2026-09-16T00:00:00+00:00')
    for item in attempts:
        run.sources.append(item)

    class NoEngagement:
        def execute(self, *a, **kw):
            return []
    return run.finalize(NoEngagement(), run_status, finished_at='2026-09-16T00:00:05+00:00',
                        duration_seconds=5.0)


# ---------------------------------------------------------------------------
# 1-4. Source outcomes: complete, truthful zero, failure, partial
# ---------------------------------------------------------------------------

def test_complete_source_represents_every_funnel_stage():
    source = attempt()
    source.record_fetch(COMPLETE)
    for index in range(5):
        source.observed()
        source.persisted(100 + index, created=True)
        source.assessed(100 + index, decision())
    funnel = source.funnel()
    assert funnel == {telemetry.FETCHED: 5, telemetry.STRUCTURALLY_VALID: 5,
                      telemetry.CANONICAL_UNIQUE: 5, telemetry.LOCATION_COMPATIBLE: 5,
                      telemetry.ELIGIBILITY_NOT_INCOMPATIBLE: 5, telemetry.RELEVANT: 5,
                      telemetry.NEW: 5}
    assert source.attempt_outcome() == telemetry.ATTEMPT_OK
    assert source.counts_complete() is True


def test_successful_source_with_zero_observations_is_not_a_failure():
    source = attempt()
    source.record_fetch(EMPTY)
    assert source.fetch_outcome == telemetry.FETCH_SUCCEEDED
    assert source.health == 'EMPTY'
    assert source.attempt_outcome() == telemetry.ATTEMPT_OK
    assert source.error_code is None and source.error_class is None
    assert all(value == 0 for value in source.funnel().values())
    assert source.counts_complete() is True


def test_source_failure_before_results_is_distinguishable_from_a_truthful_zero():
    failed = attempt()
    failed.failed(FAILED)
    empty = attempt()
    empty.record_fetch(EMPTY)
    assert failed.funnel() == empty.funnel()          # both all-zero ...
    assert failed.fetch_outcome == telemetry.FETCH_FAILED   # ... yet never conflated
    assert empty.fetch_outcome == telemetry.FETCH_SUCCEEDED
    assert failed.attempt_outcome() == telemetry.ATTEMPT_FAILED
    assert failed.error_code == 'READ_TIMEOUT'
    assert failed.error_class == 'SOURCE_UNAVAILABLE'
    assert failed.counts_complete() is False
    assert failed.incomplete_reason == 'TRANSPORT_ERROR'
    assert empty.counts_complete() is True and empty.incomplete_reason is None


def test_partial_source_completion_marks_counts_incomplete():
    source = attempt()
    source.record_fetch(PARTIAL)
    source.observed(); source.persisted(1, created=True); source.assessed(1, decision())
    assert source.fetch_outcome == telemetry.FETCH_PARTIAL
    assert source.attempt_outcome() == telemetry.ATTEMPT_PARTIAL
    assert source.counts_complete() is False
    assert source.incomplete_reason == 'DETAIL_BUDGET_EXHAUSTED'
    assert source.funnel()[telemetry.NEW] == 1


def test_valid_partial_results_then_ingestion_failure_is_its_own_state():
    source = attempt()
    source.record_fetch(PARTIAL)
    source.observed(); source.persisted(1, created=True); source.assessed(1, decision())
    source.failed({'completion': 'FAILED', 'health': 'UNAVAILABLE',
                   'completion_reason': None, 'metrics': None,
                   'error': {'code': 'SOURCE_REQUEST_FAILED', 'message': 'x'}})
    assert source.fetch_outcome == telemetry.FETCH_PARTIAL      # the fetch itself did return
    assert source.attempt_outcome() == telemetry.ATTEMPT_INGESTION_FAILED
    assert source.rolled_back is True
    assert source.incomplete_reason == 'SOURCE_TRANSACTION_ROLLED_BACK'
    assert source.funnel()[telemetry.CANONICAL_UNIQUE] == 0     # rolled back, so not persisted
    assert source.funnel()[telemetry.FETCHED] == 1              # but truthfully observed


# ---------------------------------------------------------------------------
# 5-8. Structural validity, duplicates, cross-provider, reobservation
# ---------------------------------------------------------------------------

def test_structurally_invalid_observations_never_enter_structurally_valid():
    source = attempt()
    source.record_fetch(COMPLETE)
    source.observed(); source.invalid_observation()
    source.observed(); source.persisted(1, created=True); source.assessed(1, decision())
    funnel = source.funnel()
    assert funnel[telemetry.FETCHED] == 2
    assert funnel[telemetry.STRUCTURALLY_VALID] == 1
    assert source.to_dict(set(), set(), 'now')['diagnostics']['invalid_observations'] == 1


def test_same_source_duplicate_observations_collapse_to_one_canonical_job():
    source = attempt()
    source.record_fetch(COMPLETE)
    source.observed(); source.persisted(42, created=True)
    source.observed(); source.persisted(42, created=False)
    source.assessed(42, decision())
    funnel = source.funnel()
    assert funnel[telemetry.STRUCTURALLY_VALID] == 2
    assert funnel[telemetry.CANONICAL_UNIQUE] == 1
    assert funnel[telemetry.NEW] == 1
    assert source.to_dict(set(), set(), 'now')['diagnostics'][
        'duplicate_observations_same_source'] == 1


def test_existing_canonical_job_reobserved_is_unique_but_not_new():
    source = attempt()
    source.record_fetch(COMPLETE)
    source.observed(); source.persisted(9, created=False); source.assessed(9, decision())
    funnel = source.funnel()
    assert funnel[telemetry.CANONICAL_UNIQUE] == 1
    assert funnel[telemetry.RELEVANT] == 1
    assert funnel[telemetry.NEW] == 0


def test_cross_provider_duplicate_counts_once_at_run_level_but_once_per_source():
    first = attempt(1, 'Board A', 'greenhouse')
    first.record_fetch(COMPLETE)
    first.observed(); first.persisted(500, created=True); first.assessed(500, decision())
    second = attempt(2, 'Board B', 'lever')
    second.record_fetch(COMPLETE)
    second.observed(); second.persisted(500, created=False); second.assessed(500, decision())
    payload = run_payload(first, second)
    assert payload['funnel'][telemetry.FETCHED] == 2               # observation semantics
    assert payload['funnel'][telemetry.STRUCTURALLY_VALID] == 2
    assert payload['funnel'][telemetry.CANONICAL_UNIQUE] == 1      # canonical semantics
    assert payload['funnel'][telemetry.RELEVANT] == 1
    assert payload['funnel'][telemetry.NEW] == 1
    assert [s['funnel'][telemetry.CANONICAL_UNIQUE] for s in payload['sources']] == [1, 1]
    assert payload['funnel_basis'][telemetry.FETCHED] == 'PROVIDER_OBSERVATIONS'
    assert payload['funnel_basis'][telemetry.CANONICAL_UNIQUE] == 'CANONICAL_JOBS'


# ---------------------------------------------------------------------------
# 9-15. Stage definitions against the real #41 decision contract
# ---------------------------------------------------------------------------

def test_new_relevant_job_reaches_the_final_stage():
    result = telemetry.classify(decision())
    assert result['relevant'] is True and result['exit_stage'] is None


def test_hard_rejected_new_job_is_never_counted_as_new():
    source = attempt()
    source.record_fetch(COMPLETE)
    source.observed(); source.persisted(3, created=True)
    source.assessed(3, decision(hard=('DOMAIN_INCOMPATIBLE',)))
    funnel = source.funnel()
    assert funnel[telemetry.CANONICAL_UNIQUE] == 1
    assert funnel[telemetry.RELEVANT] == 0
    assert funnel[telemetry.NEW] == 0
    detail = source.to_dict(set(), set(), 'now')
    # The canonical row genuinely was created -- reported as a diagnostic, never as NEW.
    assert detail['diagnostics']['canonical_jobs_created_all_dispositions'] == 1
    assert detail['stage_exits'][telemetry.RELEVANT] == {'DOMAIN_INCOMPATIBLE': 1}


def test_location_incompatible_job_exits_at_location_stage():
    result = telemetry.classify(decision(hard=('GEO_INCOMPATIBLE',), location_compatible=False))
    assert result['location_compatible'] is False
    assert result['eligibility_not_incompatible'] is False
    assert result['relevant'] is False
    assert result['exit_stage'] == telemetry.LOCATION_COMPATIBLE
    assert result['exit_reason'] == 'GEO_INCOMPATIBLE'


def test_confirmed_eligibility_incompatible_job_exits_at_eligibility_stage():
    result = telemetry.classify(decision(hard=('CONFIRMED_ELIGIBILITY_CONFLICT',),
                                          eligibility='INELIGIBLE'))
    assert result['location_compatible'] is True
    assert result['eligibility_not_incompatible'] is False
    assert result['exit_stage'] == telemetry.ELIGIBILITY_NOT_INCOMPATIBLE


def test_unknown_eligibility_remains_not_confirmed_incompatible():
    result = telemetry.classify(decision(eligibility='UNKNOWN'))
    assert result['eligibility_not_incompatible'] is True
    assert result['relevant'] is True
    assert result['exit_stage'] is None


def test_unknown_geography_remains_location_compatible():
    """UNKNOWN evidence follows existing #41 semantics and is never silently
    converted into incompatible.
    """
    from backend import recall
    item = {'title': 'SOC Analyst', 'description': 'SIEM monitoring', 'location': '',
            'remote_status': 'Remote'}
    real = recall.evaluate(item, {'assessment_mode': 'NEW', 'locations': ['Dubai']}, {})
    assert real['fit_assessment']['geography']['compatibility'] == 'UNKNOWN'
    assert real['location_compatible'] is True
    assert telemetry.classify(real)['location_compatible'] is True


def test_unrelated_role_is_excluded_at_the_relevant_stage_by_the_real_engine():
    from backend import recall
    from backend.models import DEFAULTS
    item = {'title': 'Corporate Counsel', 'description': 'Contract law and litigation.',
            'location': 'Dubai', 'remote_status': 'On-site'}
    real = recall.evaluate(item, {**DEFAULTS, 'assessment_mode': 'NEW'}, {})
    result = telemetry.classify(real)
    assert result['location_compatible'] is True
    assert result['eligibility_not_incompatible'] is True
    assert result['relevant'] is False
    assert result['exit_stage'] == telemetry.RELEVANT


def test_experience_gap_job_follows_issue_41_behaviour_and_stays_relevant():
    from backend import recall
    from backend.models import DEFAULTS
    item = {'title': 'SOC Analyst', 'location': 'Dubai', 'remote_status': 'On-site',
            'description': 'SIEM monitoring and incident response. 5+ years of experience '
                           'required in a security operations centre.'}
    real = recall.evaluate(item, {**DEFAULTS, 'assessment_mode': 'NEW'}, {})
    assert real['excluded'] is False, 'issue #41 ranks an experience gap, never rejects it'
    result = telemetry.classify(real)
    assert result['relevant'] is True and result['exit_stage'] is None


# ---------------------------------------------------------------------------
# 16-18. Aggregation, invariants, malformed rejection
# ---------------------------------------------------------------------------

def test_every_monotonic_invariant_holds_for_a_mixed_run():
    first = attempt(1, 'A', 'greenhouse')
    first.record_fetch(COMPLETE)
    for index, dec in enumerate([decision(), decision(hard=('GEO_INCOMPATIBLE',),
                                                      location_compatible=False),
                                 decision(hard=('CONFIRMED_ELIGIBILITY_CONFLICT',),
                                          eligibility='INELIGIBLE'),
                                 decision(hard=('DOMAIN_INCOMPATIBLE',))]):
        first.observed(); first.persisted(index, created=True); first.assessed(index, dec)
    first.observed(); first.invalid_observation()
    second = attempt(2, 'B', 'lever')
    second.failed(FAILED)
    payload = run_payload(first, second)
    counts = [payload['funnel'][stage] for stage in telemetry.FUNNEL_STAGES]
    assert counts == [5, 4, 4, 3, 2, 1, 1]
    assert counts == sorted(counts, reverse=True)
    assert all(isinstance(value, int) and value >= 0 for value in counts)
    telemetry.validate(payload)


@pytest.mark.parametrize('mutate,message', [
    (lambda p: p['funnel'].update({telemetry.NEW: 99}), 'not monotonic'),
    (lambda p: p['funnel'].update({telemetry.RELEVANT: -1}), 'non-negative integer'),
    (lambda p: p['funnel'].pop(telemetry.CANONICAL_UNIQUE), 'non-negative integer'),
    (lambda p: p['funnel'].update({'DISPLAYED': 1}), 'unknown stages'),
    (lambda p: p.update({'schema_version': 'nope'}), 'Unsupported telemetry schema'),
    (lambda p: p['sources'][0].update({'attempt_state': 'INVENTED'}), 'attempt state'),
    (lambda p: p['sources'][0]['funnel'].update({telemetry.FETCHED: 5,
                                                 telemetry.STRUCTURALLY_VALID: 5}),
     'must equal the sum'),
    (lambda p: p['funnel'].update({stage: 0 for stage in telemetry.CANONICAL_STAGES}),
     'must lie between'),
    (lambda p: p['retention'].update({'retention_days': 365}), 'exactly 90 days'),
    (lambda p: p['engagement'][telemetry.DISPLAYED].update({'count': 3}),
     'must not carry a count'),
    (lambda p: p['engagement'].update({telemetry.RELEVANT: 1}), 'outside the discovery funnel'),
    (lambda p: p['sources'][0].update({'error_class': 'SOMETHING ELSE'}), 'error class'),
    (lambda p: p['sources'][0].update({'description': 'private text'}),
     'must not carry'),
])
def test_impossible_or_malformed_funnel_is_rejected(mutate, message):
    source = attempt()
    source.record_fetch(COMPLETE)
    source.observed(); source.persisted(1, created=True); source.assessed(1, decision())
    payload = run_payload(source)
    mutate(payload)
    with pytest.raises(telemetry.TelemetryError, match=message):
        telemetry.validate(payload)


def test_a_skipped_source_can_never_carry_funnel_counts():
    skipped = attempt()
    skipped.skipped(telemetry.SKIPPED_NOT_DUE)
    payload = run_payload(skipped)
    assert payload['sources'][0]['funnel'][telemetry.FETCHED] == 0
    assert payload['sources'][0]['fetch_outcome'] == telemetry.FETCH_NOT_ATTEMPTED
    assert payload['sources'][0]['incomplete_reason'] == telemetry.SKIPPED_NOT_DUE
    payload['sources'][0]['funnel'][telemetry.FETCHED] = 3
    with pytest.raises(telemetry.TelemetryError, match='not attempted'):
        telemetry.validate(payload)


def test_invariant_violation_is_reported_as_a_bounded_error_not_fabricated_counts():
    class Broken(telemetry.SourceAttempt):
        def funnel(self):
            return {**super().funnel(), telemetry.NEW: 99}
    broken = Broken(1, 'A', 'greenhouse')
    broken.record_fetch(COMPLETE)
    payload = run_payload(broken)
    assert payload['status'] == 'TELEMETRY_ERROR'
    assert payload['telemetry_error_code'] == 'TELEMETRY_FINALIZATION_FAILED'
    assert payload['funnel'] is None
    telemetry.validate(payload)


# ---------------------------------------------------------------------------
# 21-24. Engagement outcomes
# ---------------------------------------------------------------------------

def test_displayed_is_never_inferred():
    source = attempt()
    source.record_fetch(COMPLETE)
    source.observed(); source.persisted(1, created=True); source.assessed(1, decision())
    payload = run_payload(source)
    displayed = payload['engagement'][telemetry.DISPLAYED]
    assert displayed['state'] == telemetry.ENGAGEMENT_UNAVAILABLE
    assert displayed['count'] is None
    assert displayed['authority'] is None
    assert payload['funnel'][telemetry.RELEVANT] == 1   # relevance did not become a display


def test_saved_and_applied_are_counted_only_from_authoritative_state():
    source = attempt()
    source.record_fetch(COMPLETE)
    for job_id in (1, 2, 3):
        source.observed(); source.persisted(job_id, created=True)
        source.assessed(job_id, decision())
    engagement = telemetry._engagement({1, 2, 3}, saved_ids={2, 99}, applied_ids={3},
                                        measured_at='2026-09-16T00:00:00+00:00')
    assert engagement[telemetry.SAVED]['count'] == 1        # 99 is not in this run
    assert engagement[telemetry.SAVED]['authority'] == 'Job.analysis.saved'
    assert engagement[telemetry.APPLIED]['count'] == 1
    assert engagement[telemetry.APPLIED]['authority'] == 'Application.applied_date'
    assert engagement['basis'] == telemetry.ENGAGEMENT_BASIS


def test_engagement_outcomes_live_outside_the_funnel():
    source = attempt()
    source.record_fetch(COMPLETE)
    payload = run_payload(source)
    assert not set(payload['funnel']) & set(telemetry.ENGAGEMENT_OUTCOMES)
    assert set(payload['funnel']) == set(telemetry.FUNNEL_STAGES)
    for outcome in telemetry.ENGAGEMENT_OUTCOMES:
        assert outcome in payload['engagement']
        assert outcome in payload['sources'][0]['engagement']


# ---------------------------------------------------------------------------
# 38-39. Provider metrics and version metadata
# ---------------------------------------------------------------------------

def test_provider_metrics_never_overwrite_funnel_semantics():
    source = attempt()
    source.record_fetch({**COMPLETE, 'metrics': {
        'records_received': 238, 'records_accepted': 193, 'records_rejected': 45,
        'requests_attempted': 240, 'requests_succeeded': 239, 'errors_count': 45,
        'content_cap_reached': False, 'elapsed_seconds': 3.5,
        'title': 'should be dropped', 'raw_fields': {'x': 1}}})
    for index in range(3):
        source.observed(); source.persisted(index, created=True)
        source.assessed(index, decision())
    detail = source.to_dict(set(), set(), 'now')
    assert detail['funnel'][telemetry.FETCHED] == 3        # orchestration truth, not 238/193
    assert detail['provider_metrics']['records_received'] == 238
    assert detail['provider_metrics']['records_accepted'] == 193
    assert 'title' not in detail['provider_metrics']
    assert 'raw_fields' not in detail['provider_metrics']
    assert not set(detail['provider_metrics']) & set(telemetry.FUNNEL_STAGES)


def test_version_metadata_is_present_stable_and_distinguishes_evaluation_evidence():
    from backend import assessment, career_tracks, deduplication, normalization, recall
    from backend import experience as experience_module
    from backend.job_providers import contracts
    versions = telemetry.versions({'assessment_mode': 'NEW'})
    assert versions['telemetry_schema_version'] == 'discovery-telemetry-v1'
    assert versions['assessment_schema_version'] == assessment.SCHEMA_VERSION
    assert versions['assessment_ruleset_version'] == assessment.RULESET_VERSION
    assert versions['recall_version'] == recall.VERSION
    assert versions['taxonomy_version'] == career_tracks.VERSION
    assert versions['experience_parser_version'] == experience_module.VERSION
    assert versions['normalization_version'] == normalization.NORMALIZATION_VERSION
    assert versions['dedupe_version'] == deduplication.DEDUPE_VERSION
    assert versions['provider_contract_version'] == contracts.VERSION
    reference = versions['evaluation_reference']
    assert reference['authority'] == 'OFFLINE_EVALUATION_EVIDENCE_ONLY'
    assert reference['quality_gate_status'] == 'INSUFFICIENT_DATA'
    assert 'PASS' not in reference['quality_gate_status']


def test_evaluation_reference_metadata_cannot_drift_from_issue_42():
    """Production discovery must not import or rerun the #42 harness, so the
    evaluation reference is declared as literals. This test -- not production
    code -- is what keeps those literals honest.
    """
    from pathlib import Path
    from backend import evaluation
    reference = telemetry.EVALUATION_REFERENCE
    assert reference['report_schema_version'] == evaluation.REPORT_SCHEMA_VERSION
    assert reference['corpus_schema_version'] == evaluation.CORPUS_SCHEMA_VERSION
    assert reference['human_label_version'] == evaluation.HUMAN_LABEL_VERSION
    assert reference['quality_gate_schema_version'] == evaluation.QUALITY_GATE_SCHEMA_VERSION
    committed = json.loads((Path(__file__).resolve().parents[1] /
                            'docs/evaluation/fit_evaluation_report.json').read_text('utf-8'))
    gate = committed['quality_gate']
    assert reference['quality_gate_status'] == gate['gate_status'] == evaluation.INSUFFICIENT_DATA
    assert reference['quality_gate_approval_state'] == gate['approval_state']


def test_production_discovery_does_not_import_the_evaluation_harness():
    import inspect
    source = inspect.getsource(telemetry)
    assert 'import evaluation' not in source and 'from .evaluation' not in source


# ---------------------------------------------------------------------------
# Privacy bounds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('key', ['description', 'title', 'job_url', 'raw_fields', 'evidence',
                                 'decisions', 'email', 'raw_text', 'token', 'traceback'])
def test_private_content_keys_are_rejected_anywhere_in_the_payload(key):
    source = attempt()
    source.record_fetch(COMPLETE)
    payload = run_payload(source)
    payload['sources'][0]['diagnostics'][key] = 'private'
    with pytest.raises(telemetry.TelemetryError, match='must not carry'):
        telemetry.validate(payload)


def test_external_error_text_is_normalized_away():
    source = attempt()
    source.failed(FAILED)
    detail = source.to_dict(set(), set(), 'now')
    assert detail['error_code'] == 'READ_TIMEOUT'
    assert 'private diagnostic' not in json.dumps(detail)
    assert 'message' not in json.dumps(detail)


def test_an_unbounded_or_invented_provider_error_code_is_not_copied_through():
    source = attempt()
    source.failed({'completion': 'FAILED', 'health': 'MALFORMED', 'completion_reason': None,
                   'metrics': None,
                   'error': {'code': 'X' * 5000, 'message': 'attacker controlled'}})
    assert source.error_code == telemetry.ERROR_CLASS_UNCLASSIFIED
    assert source.error_class == 'MALFORMED_RESPONSE'


def test_source_name_is_bounded():
    source = telemetry.SourceAttempt(1, 'A' * 5000, 'greenhouse')
    assert len(source.source_name) == 200
    assert telemetry._bounded_family('../../etc/passwd') == 'unknown'


# ---------------------------------------------------------------------------
# Retention (31-35) -- exercised against the real database
# ---------------------------------------------------------------------------

def test_retention_boundary_idempotency_and_malformed_reports(tmp_path):
    isolated(tmp_path, r'''
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from backend.models import *
from backend import discovery_telemetry as telemetry
initialize()
clock = datetime(2026, 9, 16, tzinfo=timezone.utc)
cutoff = clock - timedelta(days=90)
payload = {'schema_version': telemetry.TELEMETRY_SCHEMA_VERSION, 'funnel': {}}
def add(created, report, task='discover'):
    with Session.begin() as db:
        run = AutomationRun(task=task, status='COMPLETED', report=report)
        db.add(run); db.flush(); run.created_at = created; return run.id
just_before = add((cutoff + timedelta(seconds=1)).isoformat(), {'decisions': [1], 'discovery_telemetry': dict(payload)})
exact = add(cutoff.isoformat(), {'decisions': [1], 'discovery_telemetry': dict(payload)})
just_after = add((cutoff - timedelta(seconds=1)).isoformat(), {'decisions': [1], 'discovery_telemetry': dict(payload), 'discovered': 4})
malformed = add((cutoff - timedelta(days=5)).isoformat(), None)
other_task = add((cutoff - timedelta(days=5)).isoformat(), {'decisions': [1]}, task='report')
# Records that must never be touched by telemetry retention.
with Session.begin() as db:
    job = Job(company='Synthetic', title='SOC Analyst'); db.add(job); db.flush()
    db.add(Application(job_id=job.id, status='APPLIED', applied_date='2026-01-01'))
    db.add(JobObservation(job_id=job.id, provider_family='manual'))

with Session.begin() as db:
    first = telemetry.prune_expired(db, clock=clock)
assert first['runs_pruned'] == 1, first
assert first['retention_days'] == 90

with Session() as db:
    assert 'discovery_telemetry' in db.get(AutomationRun, just_before).report
    assert 'decisions' in db.get(AutomationRun, just_before).report
    # Strictly older than the cutoff: a run exactly at the boundary is preserved.
    assert 'discovery_telemetry' in db.get(AutomationRun, exact).report
    assert 'decisions' in db.get(AutomationRun, exact).report
    after = db.get(AutomationRun, just_after).report
    assert 'discovery_telemetry' not in after and 'decisions' not in after
    assert after['discovered'] == 4, 'non-telemetry operational fields survive'
    assert db.get(AutomationRun, malformed).report in (None, {})
    assert 'decisions' in db.get(AutomationRun, other_task).report
    assert db.query(Job).count() == 1
    assert db.query(Application).count() == 1
    assert db.query(JobObservation).count() == 1

with Session.begin() as db:
    second = telemetry.prune_expired(db, clock=clock)
assert second['runs_pruned'] == 0, 'cleanup must be idempotent'
with Session.begin() as db:
    third = telemetry.prune_expired(db, clock=clock)
assert third['runs_pruned'] == 0
''')


# ---------------------------------------------------------------------------
# Integration against the real discover loop
# ---------------------------------------------------------------------------

def test_real_discovery_run_produces_a_truthful_cross_source_funnel(tmp_path):
    isolated(tmp_path, r'''
from backend.models import *
from backend import discovery_telemetry as telemetry
import backend.main as m
from tests.scan_harness import confirmed_discover
initialize()
# Two boards for the SAME employer (a real cross-provider case), plus an empty
# board, a failing board and a disabled board.
boards = {}
with Session.begin() as db:
    for name, adapter, board, enabled in (
            ('Acme Security', 'greenhouse', 'alpha', True),
            ('Acme Security', 'lever', 'beta', True),
            ('Quiet Board', 'ashby', 'empty', True),
            ('Broken Board', 'greenhouse', 'broken', True),
            ('Paused Board', 'lever', 'paused', False)):
        row = JobSource(name=name, adapter=adapter, board=board, enabled=enabled)
        db.add(row); db.flush(); boards[board] = row.id

shared = {'title': 'SOC Analyst', 'location': 'Dubai', 'description': 'SIEM monitoring',
          'job_url': 'https://example.com/roles/soc-analyst-l1', 'source': 'Greenhouse',
          'source_job_id': 's1'}
def fake_discover(kind, board, url, cfg=None):
    if board == 'broken': raise ValueError('Source unavailable')
    if board == 'empty': return []
    if board == 'alpha':
        return [dict(shared),
                {'title': 'Corporate Counsel', 'location': 'Dubai', 'description': 'Litigation.',
                 'job_url': 'https://example.com/legal', 'source': 'Greenhouse', 'source_job_id': 'a2'},
                {'title': 'Security Analyst', 'location': 'Berlin, Germany', 'description': 'On-site SOC.',
                 'job_url': 'https://example.com/berlin', 'source': 'Greenhouse', 'source_job_id': 'a3'},
                {'title': 'SOC Analyst', 'location': 'Abu Dhabi', 'description': 'Blue team.',
                 'job_url': 'not a url', 'source': 'Greenhouse', 'source_job_id': 'a4'}]
    return [dict(shared, source='Lever', source_job_id='b1')]

m.discover = fake_discover
result = confirmed_discover()
payload = result['report'][telemetry.REPORT_KEY]
telemetry.validate(payload)
assert payload['schema_version'] == 'discovery-telemetry-v1'
assert payload['run_status'] == 'PARTIAL'
assert payload['trigger'] == 'MANUAL_START'   # discovery runs only from a confirmed Start Scan
assert payload['source_filter'] is None

sources = {s['source_id']: s for s in payload['sources']}
assert set(sources) == set(boards.values())
alpha, beta = sources[boards['alpha']], sources[boards['beta']]

assert alpha['funnel'][telemetry.FETCHED] == 4
assert alpha['funnel'][telemetry.STRUCTURALLY_VALID] == 3, alpha
assert alpha['funnel'][telemetry.CANONICAL_UNIQUE] == 3
assert alpha['funnel'][telemetry.LOCATION_COMPATIBLE] == 2, 'Berlin on-site is geo-incompatible'
assert alpha['funnel'][telemetry.ELIGIBILITY_NOT_INCOMPATIBLE] == 2
assert alpha['funnel'][telemetry.RELEVANT] == 1, 'the legal role is not a relevant match'
assert alpha['funnel'][telemetry.NEW] == 1
assert alpha['stage_exits'][telemetry.LOCATION_COMPATIBLE] == {'GEO_INCOMPATIBLE': 1}
assert alpha['stage_exits'][telemetry.RELEVANT] == {'DOMAIN_INCOMPATIBLE': 1}
assert alpha['diagnostics']['invalid_observations'] == 1
assert alpha['provider_family'] == 'greenhouse'

# The shared posting is observed by two sources; each reports it, the run counts it once.
assert beta['funnel'][telemetry.CANONICAL_UNIQUE] == 1
assert beta['funnel'][telemetry.NEW] == 0, 'the greenhouse board created the canonical row'
assert payload['funnel'][telemetry.FETCHED] == 5
assert payload['funnel'][telemetry.STRUCTURALLY_VALID] == 4
assert payload['funnel'][telemetry.CANONICAL_UNIQUE] == 3, payload['funnel']
assert payload['funnel'][telemetry.RELEVANT] == 1
assert payload['funnel'][telemetry.NEW] == 1

# Failure, truthful zero and disabled are three visibly different outcomes.
broken, empty, paused = sources[boards['broken']], sources[boards['empty']], sources[boards['paused']]
assert broken['fetch_outcome'] == 'FAILED'
assert broken['attempt_outcome'] == 'FAILED'
assert broken['counts_complete'] is False
assert empty['fetch_outcome'] == 'SUCCEEDED'
assert empty['health'] == 'EMPTY'
assert empty['counts_complete'] is True
assert all(v == 0 for v in empty['funnel'].values())
assert paused['attempt_state'] == telemetry.SKIPPED_DISABLED
assert paused['attempted'] is False
assert payload['sources_attempted'] == 4 and payload['sources_skipped'] == 1
assert payload['sources_failed'] == 1 and payload['counts_complete'] is False

# Production #41 behaviour is untouched: every structurally valid posting is still
# persisted, including the hard-rejected ones.
with Session() as db:
    assert db.query(Job).count() == 3
    assert result['report']['discovered'] == 3
    assert result['report']['duplicates'] == 1
''')


def test_targeted_single_source_run_marks_other_sources_not_targeted(tmp_path):
    isolated(tmp_path, r'''
from backend.models import *
from backend import discovery_telemetry as telemetry
import backend.main as m
from tests.scan_harness import confirmed_discover
initialize()
with Session.begin() as db:
    for name, board in (('Alpha', 'alpha'), ('Beta', 'beta')):
        db.add(JobSource(name=name, adapter='greenhouse', board=board, enabled=True))
    target = db.scalar(__import__('sqlalchemy').select(JobSource).where(JobSource.name == 'Alpha')).id

m.discover = lambda kind, board, url, cfg=None: [
    {'title': 'SOC Analyst', 'location': 'Dubai', 'description': 'SIEM',
     'job_url': 'https://example.com/1', 'source': 'Greenhouse', 'source_job_id': '1'}]
result = confirmed_discover(source_id=target)
payload = result['report'][telemetry.REPORT_KEY]
telemetry.validate(payload)
sources = {s['source_name']: s for s in payload['sources']}
assert payload['source_filter'] == target
assert sources['Alpha']['attempted'] is True
assert sources['Beta']['attempt_state'] == telemetry.SKIPPED_NOT_TARGETED
assert sources['Beta']['fetch_outcome'] == 'NOT_ATTEMPTED'
assert all(v == 0 for v in sources['Beta']['funnel'].values())
assert payload['sources_attempted'] == 1 and payload['sources_skipped'] == 1
''')


def test_a_scheduled_discovery_call_is_refused_and_records_nothing(tmp_path):
    """Discovery is manual-only, so the old scheduled path (and its NOT_DUE
    skip) can no longer run: a scheduled call without a Start Scan
    confirmation is refused before any source is touched. SKIPPED_NOT_DUE
    stays a valid telemetry state so historical reports still validate."""
    isolated(tmp_path, r'''
from datetime import datetime, timezone
from backend.models import *
from backend import discovery_telemetry as telemetry
import backend.main as m
initialize()
with Session.begin() as db:
    db.add(JobSource(name='Recent', adapter='greenhouse', board='recent', enabled=True,
                     details={'last_success': datetime.now(timezone.utc).isoformat(),
                              'interval_hours': 24}))
calls = []
m.discover = lambda *a, **kw: calls.append(a) or []
result = m.task('discover', scheduled_run=True)
assert result.get('refused') is True, result
assert calls == []
with Session() as db:
    assert db.query(AutomationRun).count() == 0
assert telemetry.SKIPPED_NOT_DUE in telemetry.ATTEMPT_STATES
assert not m.task_lock.locked()
''')


def test_saved_and_applied_are_read_from_persisted_state_during_a_real_run(tmp_path):
    isolated(tmp_path, r'''
from backend.models import *
from backend import discovery_telemetry as telemetry
import backend.main as m
from tests.scan_harness import confirmed_discover
initialize()
with Session.begin() as db:
    db.add(JobSource(name='Alpha', adapter='greenhouse', board='alpha', enabled=True))
    saved = Job(company='Alpha', title='SOC Analyst', location='Dubai',
                description='SIEM monitoring', job_url='https://example.com/saved',
                source='Greenhouse', source_job_id='keep', canonical_url='https://example.com/saved',
                analysis={'saved': True})
    db.add(saved); db.flush()
    db.add(Application(job_id=saved.id, status='APPLIED', applied_date='2026-09-01'))

m.discover = lambda kind, board, url, cfg=None: [
    {'title': 'SOC Analyst', 'location': 'Dubai', 'description': 'SIEM monitoring',
     'job_url': 'https://example.com/saved', 'source': 'Greenhouse', 'source_job_id': 'keep'}]
result = confirmed_discover()
payload = result['report'][telemetry.REPORT_KEY]
telemetry.validate(payload)
engagement = payload['engagement']
assert engagement[telemetry.SAVED]['count'] == 1
assert engagement[telemetry.APPLIED]['count'] == 1
assert engagement[telemetry.DISPLAYED]['state'] == 'UNAVAILABLE'
assert engagement['basis'] == telemetry.ENGAGEMENT_BASIS
assert payload['funnel'][telemetry.NEW] == 0, 'a pre-existing canonical job is not NEW'
''')


def test_production_issue_41_assessment_results_are_unchanged_by_telemetry(tmp_path):
    isolated(tmp_path, r'''
from backend.models import *
from backend.recall import evaluate
from backend import discovery_telemetry as telemetry
import backend.main as m
from tests.scan_harness import confirmed_discover
initialize()
with Session.begin() as db:
    db.add(JobSource(name='Alpha', adapter='greenhouse', board='alpha', enabled=True))
item = {'title': 'SOC Analyst', 'location': 'Dubai', 'description': 'SIEM monitoring',
        'job_url': 'https://example.com/1', 'source': 'Greenhouse', 'source_job_id': '1'}
m.discover = lambda kind, board, url, cfg=None: [dict(item)]
with Session() as db:
    cfg = settings(db)
expected = evaluate(dict(item), cfg, {})
result = confirmed_discover()
with Session() as db:
    job = db.query(Job).one()
    assert job.analysis['fit_assessment']['bucket'] == expected['fit_assessment']['bucket']
    assert job.analysis['fit_assessment']['score'] == expected['fit_assessment']['score']
    assert job.analysis['recall']['excluded'] == expected['excluded']
    assert job.match_score == expected['fit_assessment']['score']
    assert job.recommendation == m.score(job, {}, cfg)['recommendation']
telemetry.validate(result['report'][telemetry.REPORT_KEY])
# The pre-#43 compatibility funnel still exists and still reports the same shape.
assert result['report']['funnel']['counts']['fetched'] == 1
assert result['report']['funnel']['schema'] == 'legacy-discovery-funnel-compat-1'
''')


# ---------------------------------------------------------------------------
# API contract (25-30)
# ---------------------------------------------------------------------------

def test_telemetry_api_contract(tmp_path):
    isolated(tmp_path, r'''
from fastapi.testclient import TestClient
from backend.models import *
from backend import discovery_telemetry as telemetry
import backend.main as m
from tests.scan_harness import confirmed_discover
initialize()
client = TestClient(m.app)

empty = client.get('/api/search/telemetry')
assert empty.status_code == 200 and empty.json()['status'] == 'NO_DATA'
assert empty.json()['run'] is None

with Session.begin() as db:
    db.add(JobSource(name='Alpha', adapter='greenhouse', board='alpha', enabled=True))
m.discover = lambda kind, board, url, cfg=None: [
    {'title': 'SOC Analyst', 'location': 'Dubai', 'description': 'Secret SIEM description',
     'job_url': 'https://example.com/private', 'source': 'Greenhouse', 'source_job_id': '1'}]
first = confirmed_discover()
second = confirmed_discover()

latest = client.get('/api/search/telemetry').json()
assert latest['status'] == 'OK'
assert latest['schema_version'] == 'discovery-telemetry-v1'
assert latest['run']['run_id'] == second['id']
run_view = latest['run']['telemetry']
assert run_view['funnel'][telemetry.FETCHED] == 1
assert run_view['sources'][0]['source_name'] == 'Alpha'
assert run_view['versions']['telemetry_schema_version'] == 'discovery-telemetry-v1'
assert run_view['retention']['retention_days'] == 90

# Verbose decisions and private job content never leave through this endpoint.
body = __import__('json').dumps(latest)
for forbidden in ('Secret SIEM description', 'example.com/private', 'SOC Analyst',
                  '"decisions"', '"item"', '"description"'):
    assert forbidden not in body, forbidden

history = client.get('/api/search/telemetry/runs?limit=1').json()
assert history['returned'] == 1 and history['limit'] == 1
assert history['runs'][0]['run_id'] == second['id']
assert history['maximum_runs'] == 20
capped = client.get('/api/search/telemetry/runs?limit=9999').json()
assert capped['limit'] == 20
assert client.get('/api/search/telemetry/runs?limit=0').status_code == 400

one = client.get(f'/api/search/telemetry/runs/{first["id"]}').json()
assert one['status'] == 'OK' and one['run']['run_id'] == first['id']

missing = client.get('/api/search/telemetry/runs/999999')
assert missing.status_code == 404
assert 'sqlite' not in missing.text.lower() and 'Traceback' not in missing.text
assert client.get('/api/search/telemetry/runs/0').status_code == 404
assert client.get('/api/search/telemetry/runs/abc').status_code == 422

# A legacy run without telemetry, and a run still in progress.
with Session.begin() as db:
    legacy = AutomationRun(task='discover', status='COMPLETED',
                           report={'discovered': 3, 'sources': [], 'decisions': [{'x': 1}]})
    db.add(legacy)
    running = AutomationRun(task='discover', status='RUNNING', report={})
    db.add(running); db.flush(); legacy_id, running_id = legacy.id, running.id

legacy_view = client.get(f'/api/search/telemetry/runs/{legacy_id}').json()
assert legacy_view['status'] == 'TELEMETRY_UNAVAILABLE'
assert legacy_view['run']['telemetry'] is None
assert '"decisions"' not in __import__('json').dumps(legacy_view)
assert client.get('/api/search/telemetry').json()['run']['run_id'] == second['id']

running_view = client.get(f'/api/search/telemetry/runs/{running_id}').json()
assert running_view['status'] == 'RUN_IN_PROGRESS'
assert running_view['run']['telemetry'] is None
''')


def test_public_view_drops_unknown_fields_from_a_foreign_payload():
    run = FakeRun({telemetry.REPORT_KEY: {
        'schema_version': telemetry.TELEMETRY_SCHEMA_VERSION,
        'run_id': 1, 'funnel': {stage: 0 for stage in telemetry.FUNNEL_STAGES},
        'description': 'private job text', 'decisions': [{'item': {'title': 'x'}}],
        'sources': [{'source_id': 1, 'source_name': 'Alpha', 'job_url': 'https://leak',
                     'funnel': {stage: 0 for stage in telemetry.FUNNEL_STAGES}}],
    }, 'decisions': [{'item': {'title': 'x'}}]})
    view = telemetry.public_view(run)
    serialized = json.dumps(view)
    assert 'private job text' not in serialized
    assert 'https://leak' not in serialized
    assert 'decisions' not in serialized
    assert view['telemetry']['funnel'][telemetry.FETCHED] == 0
    assert view['telemetry']['sources'][0]['source_name'] == 'Alpha'


def test_public_view_reports_legacy_and_running_runs_without_crashing():
    assert telemetry.public_view(FakeRun({'discovered': 2}))['telemetry_status'] == \
        telemetry.TELEMETRY_UNAVAILABLE
    assert telemetry.public_view(FakeRun(None))['telemetry_status'] == \
        telemetry.TELEMETRY_UNAVAILABLE
    assert telemetry.public_view(FakeRun({}, status='RUNNING'))['telemetry_status'] == \
        telemetry.RUN_IN_PROGRESS
    older = telemetry.public_view(FakeRun({telemetry.REPORT_KEY: {'schema_version': 'v0'}}))
    assert older['telemetry_status'] == telemetry.TELEMETRY_UNAVAILABLE

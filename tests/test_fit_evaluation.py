"""Issue #42: backend.evaluation / scripts/evaluate_fit.py tests.

Network-free, deterministic. Uses the shipped corpus
(tests/fixtures/fit_evaluation_v1.json) plus small inline fixtures for
corpus-validation edge cases.
"""
import json
import copy
import subprocess
import sys
from pathlib import Path

import pytest

from backend import evaluation as ev

CORPUS_PATH = 'tests/fixtures/fit_evaluation_v1.json'
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def corpus():
    return ev.load_corpus(CORPUS_PATH)


@pytest.fixture(scope='module')
def results(corpus):
    return ev.run_corpus(corpus, engine='compare')


def _minimal_corpus(**overrides):
    base = {
        'corpus_schema_version': ev.CORPUS_SCHEMA_VERSION, 'corpus_content_version': '2026-09-15.99',
        'human_label_version': ev.HUMAN_LABEL_VERSION, 'metric_definition_version': ev.METRIC_DEFINITION_VERSION,
        'fixed_assessment_clock': '2026-09-15T00:00:00+00:00',
        'cases': [{
            'id': 'case-1', 'query_id': 'q1', 'source_kind': 'manual', 'reference_opportunity_id': 'opp-1',
            'split': 'development',
            'job': {'title': 'SOC Analyst', 'description': 'SIEM monitoring', 'location': 'Dubai'},
            'candidate_profile_fixture': {}, 'career_config': {}, 'reference_label': 'MUST_SHOW',
            'reference_status': 'PROPOSED', 'human_reason': 'core match', 'allowed_hard_reasons': [],
            'reference_link_state': 'LIKELY_LIVE', 'tags': {},
        }],
    }
    base.update(overrides)
    return base


def _write(tmp_path, data, name='corpus.json'):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


# ---------------------------------------------------------------------------
# Corpus validation
# ---------------------------------------------------------------------------

def test_shipped_corpus_loads(corpus):
    assert len(corpus['cases']) >= 60
    assert len(corpus['_query_index']) >= 10


def test_shipped_corpus_covers_every_reference_label(corpus):
    labels = {c['reference_label'] for c in corpus['cases']}
    assert labels == set(ev.LABELS)


def test_rejects_bad_json(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{not json', encoding='utf-8')
    with pytest.raises(ev.CorpusError, match='not valid JSON'):
        ev.load_corpus(str(path))


def test_rejects_unsupported_schema_version(tmp_path):
    with pytest.raises(ev.CorpusError, match='Unsupported corpus_schema_version'):
        ev.load_corpus(_write(tmp_path, _minimal_corpus(corpus_schema_version='fit-eval-corpus-99')))


def test_rejects_duplicate_ids(tmp_path):
    data = _minimal_corpus()
    data['cases'].append(dict(data['cases'][0]))
    with pytest.raises(ev.CorpusError, match='Duplicate case id'):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_invalid_label(tmp_path):
    data = _minimal_corpus()
    data['cases'][0]['reference_label'] = 'DEFINITELY_SHOW'
    with pytest.raises(ev.CorpusError, match='invalid reference_label'):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_allowed_hard_reasons_on_non_rejection(tmp_path):
    data = _minimal_corpus()
    data['cases'][0]['allowed_hard_reasons'] = ['DOMAIN_INCOMPATIBLE']
    with pytest.raises(ev.CorpusError, match='only meaningful for GENUINE_REJECTION'):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_invalid_link_state(tmp_path):
    data = _minimal_corpus()
    data['cases'][0]['reference_link_state'] = 'PROBABLY_FINE'
    with pytest.raises(ev.CorpusError, match='invalid reference_link_state'):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_missing_top_level_key(tmp_path):
    data = _minimal_corpus()
    del data['fixed_assessment_clock']
    with pytest.raises(ev.CorpusError, match='missing required top-level key'):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_empty_cases(tmp_path):
    with pytest.raises(ev.CorpusError, match='non-empty list'):
        ev.load_corpus(_write(tmp_path, _minimal_corpus(cases=[])))


def test_rejects_unstable_id_format(tmp_path):
    data = _minimal_corpus()
    data['cases'][0]['id'] = 'Case With Spaces!'
    with pytest.raises(ev.CorpusError, match='stable lowercase-kebab'):
        ev.load_corpus(_write(tmp_path, data))


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def test_run_corpus_covers_every_case(corpus, results):
    assert len(results) == len(corpus['cases'])
    assert {r.id for r in results} == {c['id'] for c in corpus['cases']}


def test_run_case_engine_new_has_no_legacy_fields(corpus):
    case = corpus['cases'][0]
    r = ev.run_case(case, corpus, engine='new')
    assert r.new_bucket is not None
    assert r.legacy_excluded is None and r.comparison_category is None


def test_run_case_engine_legacy_has_no_new_fields(corpus):
    case = corpus['cases'][0]
    r = ev.run_case(case, corpus, engine='legacy')
    assert r.new_bucket is None
    assert r.legacy_excluded is not None


def test_run_case_engine_compare_has_both(corpus):
    case = corpus['cases'][0]
    r = ev.run_case(case, corpus, engine='compare')
    assert r.new_bucket is not None and r.legacy_excluded is not None and r.comparison_category is not None


def test_case_filter_by_id(corpus):
    target = corpus['cases'][5]['id']
    results = ev.run_corpus(corpus, case_filter=lambda c: c['id'] == target)
    assert len(results) == 1 and results[0].id == target


def test_slice_by_tag(corpus):
    results = ev.run_corpus(corpus, case_filter=lambda c: c.get('tags', {}).get('domain') == 'cloud_security')
    assert results
    assert all(r.tags.get('domain') == 'cloud_security' for r in results)


def test_fixed_clock_is_used_not_wall_clock(corpus):
    r1 = ev.run_case(corpus['cases'][0], corpus, engine='new')
    r2 = ev.run_case(corpus['cases'][0], corpus, engine='new')
    # Same case, same fixed clock -> identical bucket/score every time.
    assert r1.new_bucket == r2.new_bucket and r1.new_score == r2.new_score


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def test_must_show_false_rejection_zero_denominator():
    m = ev.must_show_false_rejection([])
    assert m['status'] == ev.INSUFFICIENT_DATA and m['value'] is None


def test_must_show_false_rejection_counts_correctly():
    a = ev.CaseResult(id='a', query_id='q', split='development', source_kind='manual', reference_label='MUST_SHOW',
                      reference_status='PROPOSED', allowed_hard_reasons=[], reference_link_state='LIKELY_LIVE',
                      tags={}, new_bucket='REJECTED', new_score=None, new_hard_reason='DOMAIN_INCOMPATIBLE')
    b = ev.CaseResult(id='b', query_id='q', split='development', source_kind='manual', reference_label='MUST_SHOW',
                      reference_status='PROPOSED', allowed_hard_reasons=[], reference_link_state='LIKELY_LIVE',
                      tags={}, new_bucket='STRONG', new_score=90, new_hard_reason=None)
    m = ev.must_show_false_rejection([a, b])
    assert m == {'numerator': 1, 'denominator': 2, 'value': 0.5, 'status': ev.OK, 'failing_case_ids': ['a']}


def test_unclear_excluded_from_scored_denominators():
    unclear = ev.CaseResult(id='u', query_id='q', split='development', source_kind='manual', reference_label='UNCLEAR',
                            reference_status='PROPOSED', allowed_hard_reasons=[], reference_link_state='LIKELY_LIVE',
                            tags={}, new_bucket='REJECTED', new_score=None, new_hard_reason='DOMAIN_INCOMPATIBLE')
    m = ev.must_show_false_rejection([unclear])
    assert m['status'] == ev.INSUFFICIENT_DATA
    m2 = ev.useful_false_rejection([unclear])
    assert m2['status'] == ev.INSUFFICIENT_DATA


def test_unclear_never_becomes_negative_example(corpus, results):
    unclear = [r for r in results if r.reference_label == 'UNCLEAR']
    assert unclear
    report = ev.build_report(corpus, CORPUS_PATH, unclear)
    assert report['coverage']['total_cases'] == len(unclear)
    assert report['coverage']['unclear_count'] == len(unclear)
    assert report['coverage']['reference_label_distribution'] == {'UNCLEAR': len(unclear)}
    for metric in report['primary_metrics'].values():
        if 'low_only' in metric:
            assert metric['low_only']['status'] == ev.INSUFFICIENT_DATA
        assert metric['status'] == ev.INSUFFICIENT_DATA
        assert metric['value'] is None
    assert report['ranking_metrics']['precision_at_k']['status'] == ev.INSUFFICIENT_DATA
    assert report['ranking_metrics']['ndcg_at_k']['status'] == ev.INSUFFICIENT_DATA


def test_hard_reason_precision_shape(results):
    out = ev.hard_reason_precision(results)
    assert set(out) == set(ev.HARD_REASONS_EVALUATED)
    for m in out.values():
        assert {'numerator', 'denominator', 'value', 'status', 'failing_case_ids', 'predicted_count',
                'human_allowed_count'} <= set(m)


def test_legacy_new_transitions_shape(results):
    out = ev.legacy_new_transitions(results)
    assert set(out) == {'category_counts', 'recoveries_by_bucket', 'recovered_case_ids_reference_useful',
                        'new_regression_case_ids', 'new_regression_case_ids_reference_useful'}
    assert sum(out['category_counts'].values()) == len(results)


def test_precision_recall_ndcg_all_unclear_query_set_is_skipped():
    unclear = ev.CaseResult(id='u', query_id='qu', split='development', source_kind='manual', reference_label='UNCLEAR',
                            reference_status='PROPOSED', allowed_hard_reasons=[], reference_link_state='LIKELY_LIVE',
                            tags={}, new_bucket='LOW', new_score=30, new_hard_reason=None)
    out = ev.precision_recall_ndcg_at_k({'qu': [unclear]}, k=10)
    assert out['per_query_set'] == {}
    assert out['precision_at_k']['status'] == ev.INSUFFICIENT_DATA


def test_precision_recall_ndcg_score_ties_are_deterministic():
    tied = [ev.CaseResult(id=f'c{i}', query_id='q', split='development', source_kind='manual',
                          reference_label='MUST_SHOW', reference_status='PROPOSED', allowed_hard_reasons=[],
                          reference_link_state='LIKELY_LIVE', tags={}, new_bucket='STRONG', new_score=80,
                          new_hard_reason=None) for i in range(3)]
    ranked1 = ev.rank_query_set(tied)
    ranked2 = ev.rank_query_set(list(reversed(tied)))
    assert [r.id for r in ranked1] == [r.id for r in ranked2] == ['c0', 'c1', 'c2']


def test_rejected_candidates_rank_below_low():
    low = ev.CaseResult(id='low', query_id='q', split='development', source_kind='manual', reference_label='LOW_BUT_USEFUL',
                        reference_status='PROPOSED', allowed_hard_reasons=[], reference_link_state='LIKELY_LIVE',
                        tags={}, new_bucket='LOW', new_score=10, new_hard_reason=None)
    rejected = ev.CaseResult(id='rej', query_id='q', split='development', source_kind='manual', reference_label='GENUINE_REJECTION',
                             reference_status='PROPOSED', allowed_hard_reasons=[], reference_link_state='LIKELY_LIVE',
                             tags={}, new_bucket='REJECTED', new_score=None, new_hard_reason='DOMAIN_INCOMPATIBLE')
    ranked = ev.rank_query_set([rejected, low])
    assert [r.id for r in ranked] == ['low', 'rej']


def test_pairwise_ordering_agreement_zero_denominator():
    same_label = [ev.CaseResult(id=f'c{i}', query_id='q', split='development', source_kind='manual',
                                reference_label='MUST_SHOW', reference_status='PROPOSED', allowed_hard_reasons=[],
                                reference_link_state='LIKELY_LIVE', tags={}, new_bucket='STRONG', new_score=80,
                                new_hard_reason=None) for i in range(3)]
    m = ev.pairwise_ordering_agreement({'q': same_label})
    assert m['status'] == ev.INSUFFICIENT_DATA


def test_duplicate_rate_against_real_40_corpus():
    result = ev.duplicate_rate()
    assert result['dedupe_recall_rate']['status'] == ev.OK
    assert result['dedupe_recall_rate']['value'] == 1.0
    assert result['false_merge_rate']['value'] == 0.0


def test_stale_link_rate_shape(results):
    m = ev.stale_link_rate(results)
    assert m['status'] == ev.OK
    assert 'unknown_count' in m


# ---------------------------------------------------------------------------
# Candidate calibration
# ---------------------------------------------------------------------------

def test_candidate_policy_never_changes_hard_reject(corpus):
    case = next(c for c in corpus['cases'] if c['reference_label'] == 'GENUINE_REJECTION')
    from backend import assessment
    policy = ev.CandidatePolicy(schema_version=ev.CANDIDATE_POLICY_SCHEMA_VERSION, id='test-policy', description='t',
                                weights={'domain': 50, 'career_track': 10, 'profile_evidence': 10,
                                        'experience': 10, 'seniority': 10, 'geography': 5, 'freshness': 5})
    item, cfg, profile = case['job'], {**case.get('career_config', {})}, case.get('candidate_profile_fixture', {})
    from backend.models import DEFAULTS
    full_cfg = {**DEFAULTS, **cfg}
    fa = assessment.assess(item, full_cfg, profile, ev._clock(corpus))
    score, bucket = ev.apply_candidate_policy(fa, policy)
    if fa['hard_reject']:
        assert bucket == 'REJECTED' and score is None


def test_candidate_policy_rejects_bad_weights(tmp_path):
    path = tmp_path / 'policy.json'
    path.write_text(json.dumps({'policy_schema_version': ev.CANDIDATE_POLICY_SCHEMA_VERSION,
                                'id': 'candidate-x', 'description': 'x', 'weights': {'domain': 200}}), encoding='utf-8')
    with pytest.raises(ev.CorpusError):
        ev.load_candidate_policy(str(path))


def test_candidate_policy_rejects_weights_not_summing_to_100(tmp_path):
    path = tmp_path / 'policy.json'
    weights = {'domain': 50, 'career_track': 15, 'profile_evidence': 20, 'experience': 15, 'seniority': 10,
              'geography': 10, 'freshness': 5}  # sums to 125
    path.write_text(json.dumps({'policy_schema_version': ev.CANDIDATE_POLICY_SCHEMA_VERSION,
                                'id': 'candidate-x', 'description': 'x', 'weights': weights}), encoding='utf-8')
    with pytest.raises(ev.CorpusError, match='sum to 100'):
        ev.load_candidate_policy(str(path))


def test_evaluate_candidate_policies_never_picks_a_production_winner(corpus):
    policy = ev.load_candidate_policy('tests/fixtures/candidate_policies/domain_heavier.json')
    out = ev.evaluate_candidate_policies(corpus, [policy])
    assert 'production' not in out['note'].lower() or 'no candidate is adopted' in out['note'].lower()
    assert len(out['entries']) == 2  # baseline + one candidate


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_determinism_byte_identical_output(corpus, results):
    report1 = ev.build_report(corpus, CORPUS_PATH, results)
    report2 = ev.build_report(corpus, CORPUS_PATH, results)
    assert ev.report_to_json(report1) == ev.report_to_json(report2)


def test_determinism_cli_byte_identical(tmp_path):
    def run():
        return subprocess.run([sys.executable, 'scripts/evaluate_fit.py', '--format', 'json'],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    r1, r2 = run(), run()
    assert r1.returncode == 0 and r2.returncode == 0
    assert r1.stdout == r2.stdout


def test_report_json_has_no_absolute_paths(corpus, results):
    report = ev.build_report(corpus, CORPUS_PATH, results)
    text = ev.report_to_json(report)
    assert str(ROOT).replace('\\', '/') not in text.replace('\\', '/')


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_query_returns_no_results(corpus):
    results = ev.run_corpus(corpus, case_filter=lambda c: c['query_id'] == 'does-not-exist')
    assert results == []


def test_unknown_ruleset_version_in_case_cfg_does_not_crash(corpus):
    # career_config only carries selection/exclusion lists -- an unrelated
    # unknown key must be ignored by DEFAULTS-merge, not crash the run.
    case = dict(corpus['cases'][0])
    case['career_config'] = {**case.get('career_config', {}), 'unknown_future_key': 'x'}
    ev.run_case(case, corpus, engine='new')


def test_cli_unknown_ruleset_fails_clearly(tmp_path):
    data = _minimal_corpus(corpus_schema_version='not-a-real-version')
    path = _write(tmp_path, data)
    result = subprocess.run([sys.executable, 'scripts/evaluate_fit.py', '--corpus', path],
                            cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert 'Unsupported corpus_schema_version' in result.stderr


def test_cli_bad_candidate_policy_fails_clearly(tmp_path):
    bad = tmp_path / 'bad_policy.json'
    bad.write_text(json.dumps({'id': 'x', 'description': 'x', 'weights': {'domain': 1}}), encoding='utf-8')
    result = subprocess.run([sys.executable, 'scripts/evaluate_fit.py', '--candidate-policy', str(bad)],
                            cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    assert result.returncode == 2


def test_cli_no_matching_cases_fails_clearly():
    result = subprocess.run([sys.executable, 'scripts/evaluate_fit.py', '--case', 'no-such-case'],
                            cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Security / privacy
# ---------------------------------------------------------------------------

def test_report_contains_no_job_description_text(corpus, results):
    report = ev.build_report(corpus, CORPUS_PATH, results)
    text = ev.report_to_json(report)
    for case in corpus['cases']:
        desc = case['job'].get('description', '')
        if len(desc) > 20:  # skip trivially short/shared fragments
            assert desc not in text


def test_report_per_case_is_bounded_dict(results):
    for r in results[:5]:
        d = r.to_public_dict()
        assert set(d) == {'id', 'query_id', 'split', 'source_kind', 'reference_label', 'reference_status',
                          'reference_link_state', 'tags', 'new_bucket', 'new_score', 'new_hard_reason',
                          'legacy_excluded', 'legacy_priority', 'comparison_category', 'candidate_bucket',
                          'candidate_score'}


def test_corpus_fixture_has_no_disallowed_pii_markers():
    text = Path(CORPUS_PATH).read_text(encoding='utf-8')
    for marker in ('@gmail.com', '@yahoo.com', '@hotmail.com', '+971', '+1-'):
        assert marker not in text


def test_corpus_fixture_is_bounded_size():
    assert Path(CORPUS_PATH).stat().st_size < 200_000


def test_evaluation_module_makes_no_network_calls(monkeypatch, corpus):
    import socket

    def blocked(*a, **kw):
        raise AssertionError('backend.evaluation must never touch the network')
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)
    ev.run_corpus(corpus, engine='compare')


# ---------------------------------------------------------------------------
# Independent-review remediation regressions (F-02 through F-10)
# ---------------------------------------------------------------------------

def test_calibration_baseline_is_the_real_split_report(corpus):
    policies = [ev.load_candidate_policy('tests/fixtures/candidate_policies/domain_heavier.json')]
    calibration = ev.evaluate_candidate_policies(corpus, policies)
    baseline = calibration['entries'][0]
    for split in ('development', 'holdout'):
        split_results = ev.run_corpus(corpus, engine='compare', case_filter=lambda c, s=split: c['split'] == s)
        report = ev.build_report(corpus, CORPUS_PATH, split_results, split_filter=split)
        assert baseline[split]['must_show_false_rejection_rate'] == report['primary_metrics']['must_show_false_rejection_rate']
        assert baseline[split]['useful_false_rejection_rate'] == report['primary_metrics']['useful_false_rejection_rate']
        assert baseline[split]['high_priority_irrelevant_leakage'] == report['primary_metrics']['high_priority_irrelevant_leakage']
        assert baseline[split]['ndcg_at_k'] == report['ranking_metrics']['ndcg_at_k']


def test_candidate_policy_controls_headline_metric_view(corpus):
    policy = ev.load_candidate_policy('tests/fixtures/candidate_policies/geography_heavier.json')
    candidate_results = ev.run_corpus(corpus, engine='compare', candidate_policy=policy)
    report = ev.build_report(corpus, CORPUS_PATH, candidate_results, candidate_policy=policy, engine='compare')
    summary = ev.summarize_candidate(candidate_results)
    assert report['evaluation_view'] == ev.CANDIDATE_VIEW
    assert report['primary_metrics']['useful_false_rejection_rate'] == summary['useful_false_rejection_rate']
    assert report['ranking_metrics']['ndcg_at_k'] == summary['ndcg_at_k']
    assert any(row['candidate_score'] != row['new_score'] for row in report['per_case']
               if row['candidate_score'] is not None)


def test_quality_gate_targets_candidate_view(corpus):
    policy = ev.load_candidate_policy('tests/fixtures/candidate_policies/geography_heavier.json')
    candidate_results = ev.run_corpus(corpus, engine='compare', candidate_policy=policy)
    report = ev.build_report(corpus, CORPUS_PATH, candidate_results, candidate_policy=policy, engine='compare')
    gate = copy.deepcopy(ev.load_quality_gate('tests/fixtures/quality_gate_proposed_v1.json'))
    gate['target_view'] = ev.CANDIDATE_VIEW
    result = ev.evaluate_quality_gate(report, gate)
    assert result['target_view'] == ev.CANDIDATE_VIEW
    assert result['checks'][1]['observed'] == report['primary_metrics']['useful_false_rejection_rate']['value']


@pytest.mark.parametrize(('field', 'value', 'message'), [
    ('metric_definition_version', 'metrics-v999', 'Unsupported metric_definition_version'),
    ('human_label_version', 'labels-v999', 'Unsupported human_label_version'),
])
def test_rejects_unknown_corpus_governance_versions(tmp_path, field, value, message):
    data = _minimal_corpus()
    data[field] = value
    with pytest.raises(ev.CorpusError, match=message):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_non_proposed_reference_status(tmp_path):
    data = _minimal_corpus()
    data['cases'][0]['reference_status'] = 'OWNER_APPROVED'
    with pytest.raises(ev.CorpusError, match='invalid reference_status'):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_invalid_split(tmp_path):
    data = _minimal_corpus()
    data['cases'][0]['split'] = 'secret-test'
    with pytest.raises(ev.CorpusError, match='invalid split'):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_duplicate_reference_opportunity_ids(tmp_path):
    data = _minimal_corpus()
    duplicate = copy.deepcopy(data['cases'][0])
    duplicate['id'] = 'case-2'
    data['cases'].append(duplicate)
    with pytest.raises(ev.CorpusError, match='Duplicate reference_opportunity_id'):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_malformed_query_id(tmp_path):
    data = _minimal_corpus()
    data['cases'][0]['query_id'] = 'Bad Query!'
    with pytest.raises(ev.CorpusError, match='query_id'):
        ev.load_corpus(_write(tmp_path, data))


def test_rejects_unknown_allowed_hard_reason(tmp_path):
    data = _minimal_corpus()
    data['cases'][0]['reference_label'] = 'GENUINE_REJECTION'
    data['cases'][0]['allowed_hard_reasons'] = ['MADE_UP_REASON']
    with pytest.raises(ev.CorpusError, match='invalid allowed_hard_reasons'):
        ev.load_corpus(_write(tmp_path, data))


def _valid_policy_data():
    return {'policy_schema_version': ev.CANDIDATE_POLICY_SCHEMA_VERSION, 'id': 'candidate-test',
            'description': 'test candidate', 'weights': dict(ev.assessment.WEIGHTS)}


def test_rejects_negative_candidate_weight(tmp_path):
    data = _valid_policy_data()
    data['weights']['domain'] = -1
    data['weights']['career_track'] += 26
    with pytest.raises(ev.CorpusError, match='nonnegative'):
        ev.load_candidate_policy(_write(tmp_path, data, 'policy.json'))


def test_rejects_nonnumeric_candidate_weight(tmp_path):
    data = _valid_policy_data()
    data['weights']['domain'] = '25'
    with pytest.raises(ev.CorpusError, match='finite number'):
        ev.load_candidate_policy(_write(tmp_path, data, 'policy.json'))


def test_rejects_unknown_candidate_component(tmp_path):
    data = _valid_policy_data()
    data['weights']['surprise'] = data['weights'].pop('domain')
    with pytest.raises(ev.CorpusError, match='cover exactly'):
        ev.load_candidate_policy(_write(tmp_path, data, 'policy.json'))


@pytest.mark.parametrize('floors', [
    [[80, 'SUPER'], [65, 'GOOD'], [45, 'STRETCH'], [0, 'LOW']],
    [[65, 'GOOD'], [80, 'STRONG'], [45, 'STRETCH'], [0, 'LOW']],
    [['high', 'STRONG'], [65, 'GOOD'], [45, 'STRETCH'], [0, 'LOW']],
])
def test_rejects_invalid_candidate_bucket_floors(tmp_path, floors):
    data = _valid_policy_data()
    data['bucket_floors'] = floors
    with pytest.raises(ev.CorpusError):
        ev.load_candidate_policy(_write(tmp_path, data, 'policy.json'))


def test_rejects_unsupported_candidate_policy_schema(tmp_path):
    data = _valid_policy_data()
    data['policy_schema_version'] = 'fit-candidate-policy-999'
    with pytest.raises(ev.CorpusError, match='Unsupported policy_schema_version'):
        ev.load_candidate_policy(_write(tmp_path, data, 'policy.json'))


def test_empty_quality_gate_is_rejected():
    with pytest.raises(ev.CorpusError, match='missing required field'):
        ev.validate_quality_gate({})


@pytest.mark.parametrize(('mutation', 'message'), [
    (lambda g: g.update(gate_schema_version='fit-quality-gate-999'), 'Unsupported gate_schema_version'),
    (lambda g: g.update(target_engine='legacy'), 'target_engine'),
    (lambda g: g.update(target_view='ANY'), 'target_view'),
    (lambda g: g['required_checks'][0].update(metric='primary_metrics.made_up'), 'unsupported metric'),
    (lambda g: g['required_checks'][0].update(operator='~='), 'unsupported operator'),
    (lambda g: g['required_checks'][0].update(threshold='zero'), 'finite number'),
    (lambda g: g['required_checks'][0].update(min_denominator=-1), 'nonnegative integer'),
])
def test_rejects_invalid_quality_gate_fields(mutation, message):
    gate = copy.deepcopy(ev.load_quality_gate('tests/fixtures/quality_gate_proposed_v1.json'))
    mutation(gate)
    with pytest.raises(ev.CorpusError, match=message):
        ev.validate_quality_gate(gate)


def test_all_required_insufficient_gate_is_not_pass(corpus):
    report = ev.build_report(corpus, CORPUS_PATH, [])
    gate = ev.load_quality_gate('tests/fixtures/quality_gate_proposed_v1.json')
    result = ev.evaluate_quality_gate(report, gate)
    assert result['gate_status'] == ev.INSUFFICIENT_DATA
    assert all(check['status'] == ev.INSUFFICIENT_DATA for check in result['checks'])


def test_quality_gate_rejects_wrong_report_view(corpus):
    policy = ev.load_candidate_policy('tests/fixtures/candidate_policies/geography_heavier.json')
    results = ev.run_corpus(corpus, candidate_policy=policy)
    report = ev.build_report(corpus, CORPUS_PATH, results, candidate_policy=policy)
    baseline_gate = ev.load_quality_gate('tests/fixtures/quality_gate_proposed_v1.json')
    with pytest.raises(ev.CorpusError, match='targets view'):
        ev.evaluate_quality_gate(report, baseline_gate)


def test_legacy_engine_marks_new_metrics_unavailable(corpus):
    legacy = ev.run_corpus(corpus, engine='legacy')
    report = ev.build_report(corpus, CORPUS_PATH, legacy, engine='legacy')
    assert report['evaluation_view'] == ev.LEGACY_VIEW
    assert all(metric['status'] == ev.UNAVAILABLE for metric in report['primary_metrics'].values())
    assert report['ranking_metrics']['ndcg_at_k']['status'] == ev.UNAVAILABLE
    assert report['pairwise_ordering_agreement']['status'] == ev.UNAVAILABLE


def test_ndcg_zero_ideal_gain_is_insufficient():
    rejection = ev.CaseResult(id='genuine-only', query_id='q1', split='development', source_kind='manual',
                              reference_label='GENUINE_REJECTION', reference_status='PROPOSED',
                              allowed_hard_reasons=['DOMAIN_INCOMPATIBLE'], reference_link_state='LIKELY_LIVE',
                              tags={}, new_bucket='REJECTED', new_score=None,
                              new_hard_reason='DOMAIN_INCOMPATIBLE')
    result = ev.precision_recall_ndcg_at_k({'q1': [rejection]})
    assert result['per_query_set']['q1']['ndcg'] is None
    assert result['ndcg_at_k']['value'] is None
    assert result['ndcg_at_k']['status'] == ev.INSUFFICIENT_DATA


def test_report_provenance_identifies_exact_commit_and_tree(corpus, results):
    report = ev.build_report(corpus, CORPUS_PATH, results)
    expected_commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                     text=True, check=True).stdout.strip()
    expected_tree = subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], cwd=ROOT, capture_output=True,
                                   text=True, check=True).stdout.strip()
    assert report['provenance']['evaluated_commit'] == expected_commit
    assert report['provenance']['evaluated_tree_hash'] == expected_tree
    assert report['git_commit'] == expected_commit


def test_cli_text_includes_requested_extended_sections():
    result = subprocess.run([
        sys.executable, 'scripts/evaluate_fit.py', '--dedupe',
        '--calibration', 'tests/fixtures/candidate_policies/domain_heavier.json',
        '--gate', 'tests/fixtures/quality_gate_proposed_v1.json', '--format', 'text'],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert 'Duplicate / stale-link:' in result.stdout
    assert 'Calibration candidates (PROPOSED, not adopted):' in result.stdout
    assert 'Quality gate quality-gate-proposed-v1' in result.stdout


@pytest.mark.parametrize(('option', 'kind'), [
    ('--corpus', 'Corpus error:'),
    ('--candidate-policy', 'Candidate policy error:'),
    ('--gate', 'Quality gate error:'),
])
def test_cli_malformed_json_is_bounded(tmp_path, option, kind):
    bad = tmp_path / 'bad.json'
    bad.write_text('{bad json', encoding='utf-8')
    result = subprocess.run([sys.executable, 'scripts/evaluate_fit.py', option, str(bad)],
                            cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert result.returncode == 2
    assert kind in result.stderr
    assert 'Traceback' not in result.stderr

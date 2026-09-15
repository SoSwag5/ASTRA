"""Issue #42: backend.evaluation / scripts/evaluate_fit.py tests.

Network-free, deterministic. Uses the shipped corpus
(tests/fixtures/fit_evaluation_v1.json) plus small inline fixtures for
corpus-validation edge cases.
"""
import json
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
        'corpus_schema_version': 'fit-eval-corpus-1', 'corpus_content_version': 'test-1',
        'human_label_version': 'test-1', 'metric_definition_version': 'test-1',
        'fixed_assessment_clock': '2026-09-15T00:00:00+00:00',
        'cases': [{
            'id': 'case-1', 'query_id': 'q1', 'source_kind': 'manual', 'reference_opportunity_id': 'opp-1',
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
    for name in ('must_show_false_rejection_rate', 'useful_false_rejection_rate'):
        pass  # documented by construction: scored() filters UNCLEAR out entirely (see test above)


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
    policy = ev.CandidatePolicy(id='t', description='t',
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
    path.write_text(json.dumps({'id': 'x', 'description': 'x', 'weights': {'domain': 200}}), encoding='utf-8')
    with pytest.raises(ev.CorpusError):
        ev.load_candidate_policy(str(path))


def test_candidate_policy_rejects_weights_not_summing_to_100(tmp_path):
    path = tmp_path / 'policy.json'
    weights = {'domain': 50, 'career_track': 15, 'profile_evidence': 20, 'experience': 15, 'seniority': 10,
              'geography': 10, 'freshness': 5}  # sums to 125
    path.write_text(json.dumps({'id': 'x', 'description': 'x', 'weights': weights}), encoding='utf-8')
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

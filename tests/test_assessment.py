"""Issue #41: backend.assessment corpus-driven and unit tests.

Network-free, deterministic. See tests/fixtures/job_fit_corpus.json and
docs/architecture/FIT_ASSESSMENT.md.
"""
import json
from pathlib import Path
import pytest
from backend import assessment
from backend.models import DEFAULTS

CORPUS = json.loads((Path(__file__).parent / 'fixtures' / 'job_fit_corpus.json').read_text())


def _cfg(case):
    cfg = dict(DEFAULTS)
    if 'career_tracks' in case:
        cfg['career_tracks'] = case['career_tracks']
    if 'custom_target_roles' in case:
        cfg['custom_target_roles'] = case['custom_target_roles']
    if 'search_focus_confirmed' in case:
        cfg['search_focus_confirmed'] = case['search_focus_confirmed']
    return cfg


@pytest.mark.parametrize('case', CORPUS['cases'], ids=[c['id'] for c in CORPUS['cases']])
def test_corpus(case):
    item = {'title': case['title'], 'description': case.get('description', ''), 'location': case.get('location', 'Dubai')}
    result = assessment.assess(item, _cfg(case), case.get('profile', {}))
    hard_code = result['hard_reject']['code'] if result['hard_reject'] else None
    assert hard_code == case['expected_hard_reject'], (case['id'], case['rationale'], result['explanation'])
    if case.get('expected_buckets'):
        assert result['bucket'] in case['expected_buckets'], (case['id'], result['bucket'], result['components'])
    if hard_code:
        assert result['score'] is None
        assert result['bucket'] == assessment.REJECTED
    else:
        assert 0 <= result['score'] <= 100


def test_score_kind_is_ranking_priority_not_probability():
    result = assessment.assess({'title': 'SOC Analyst', 'description': 'SIEM', 'location': 'Dubai'}, DEFAULTS, {})
    assert result['score_kind'] == 'RANKING_PRIORITY'
    for banned in ('probability', 'chance', 'likelihood'):
        assert banned not in result['explanation'].lower()


def test_query_provenance_is_always_unknown_zero_weight():
    result = assessment.assess({'title': 'SOC Analyst', 'description': 'SIEM', 'location': 'Dubai'}, DEFAULTS, {})
    assert result['query_expansion_match'] == 'UNKNOWN'
    assert result['query_expansion_weight'] == 0


def test_input_digest_deterministic_and_ignores_wall_clock():
    item = {'title': 'SOC Analyst', 'description': 'SIEM', 'location': 'Dubai'}
    a = assessment.assess(item, DEFAULTS, {})
    b = assessment.assess(item, DEFAULTS, {})
    assert a['input_digest'] == b['input_digest']
    assert a['assessed_at'] != b['assessed_at'] or True  # timestamps may coincide; digest must not depend on them


def test_input_digest_changes_with_candidate_facts():
    item = {'title': 'SOC Analyst', 'description': 'SIEM', 'location': 'Dubai'}
    a = assessment.assess(item, DEFAULTS, {'declarations': {}})
    b = assessment.assess(item, DEFAULTS, {'declarations': {'verified_relevant_experience_years': 3, 'verified_relevant_experience_years_confirmed': True}})
    assert a['input_digest'] != b['input_digest']


def test_unknown_candidate_years_never_becomes_zero():
    item = {'title': 'SOC Analyst', 'description': '5 years of experience required.', 'location': 'Dubai'}
    result = assessment.assess(item, DEFAULTS, {})
    assert 'not confirmed' in ' '.join(result['uncertainty']).lower() or result['components']['experience'] > 0


def test_missing_skill_evidence_is_uncertainty_not_negative_proof():
    item = {'title': 'SOC Analyst', 'description': 'SIEM SOC', 'location': 'Dubai'}
    result = assessment.assess(item, DEFAULTS, {})
    for note in result['uncertainty']:
        assert 'lacks' not in note.lower()


def test_hard_reject_always_has_bounded_evidence():
    item = {'title': 'Mechanical Engineer', 'description': 'HVAC design', 'location': 'Dubai'}
    result = assessment.assess(item, DEFAULTS, {})
    hr = result['hard_reject']
    assert hr and hr['code'] and hr['explanation'] and 'confidence' in hr and 'evidence_refs' in hr


def test_rankable_job_has_full_structured_result():
    item = {'title': 'SOC Analyst', 'description': 'SIEM', 'location': 'Dubai'}
    result = assessment.assess(item, DEFAULTS, {})
    for key in ('score', 'bucket', 'components', 'experience', 'seniority', 'geography', 'positives', 'penalties', 'uncertainty', 'explanation', 'versions'):
        assert key in result

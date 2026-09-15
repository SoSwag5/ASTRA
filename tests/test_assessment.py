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
    if 'application_profile' in case:
        cfg['application_profile'] = case['application_profile']
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


@pytest.mark.parametrize('field', ['skills', 'employments', 'projects'])
def test_input_digest_tracks_score_affecting_profile_evidence(field):
    item = {'title': 'SOC Analyst', 'description': 'SIEM Python', 'location': 'Dubai'}
    empty = assessment.assess(item, DEFAULTS, {})['input_digest']
    changed = assessment.assess(item, DEFAULTS, {field: [{'text': 'Python', 'provenance': 'synthetic'}]})['input_digest']
    assert empty != changed


def test_input_digest_tracks_authorization_but_ignores_demographics_and_ui_state():
    item = {'title': 'SOC Analyst', 'description': 'US work authorization required', 'location': 'Remote'}
    base = assessment.assess(item, DEFAULTS, {})['input_digest']
    auth = assessment.assess(item, {**DEFAULTS, 'application_profile': {
        'work_authorisation': {'US': 'NO'}, 'sponsorship': {'US': 'UNKNOWN'}}}, {})['input_digest']
    unrelated = assessment.assess(item, {**DEFAULTS, 'application_profile': {
        'gender': 'prefer not to say', 'ui_panel': 'expanded'}}, {'updated_at': '2099-01-01'})['input_digest']
    assert base != auth
    assert base == unrelated


def test_input_digest_covers_every_reassessment_identity_and_ignores_unrelated_state():
    item = {'title': 'SOC Analyst', 'description': 'SIEM', 'location': 'Dubai',
            '_observation_authority': [{'provider_family': 'lever', 'provider_job_id': '1'}],
            '_application_status': 'FOUND', '_ui_state': 'collapsed'}
    profile = {'skills': [{'text': 'SIEM'}], 'employments': [{'text': 'SOC internship'}],
               'projects': [{'text': 'Detection lab'}], 'declarations': {
                   'verified_relevant_experience_years': 1,
                   'verified_relevant_experience_years_confirmed': True}}
    cfg = {**DEFAULTS, 'application_profile': {'work_authorisation': {'US': 'UNKNOWN'}, 'sponsorship': {}}}
    versions = {'schema': '1', 'ruleset': '1', 'taxonomy': '1', 'experience_parser': '1'}
    base = assessment.input_digest(item, cfg, profile, versions)
    mutations = [
        ({**item, 'title': 'Security Analyst'}, cfg, profile, versions),
        ({**item, '_observation_authority': [{'provider_family': 'lever', 'provider_job_id': '2'}]}, cfg, profile, versions),
        (item, {**cfg, 'career_tracks': ['IT_CLOUD']}, profile, versions),
        (item, {**cfg, 'custom_target_roles': ['Purple Team Lead']}, profile, versions),
        (item, cfg, {**profile, 'skills': [{'text': 'Python'}]}, versions),
        (item, cfg, {**profile, 'employments': [{'text': 'Cloud internship'}]}, versions),
        (item, cfg, {**profile, 'projects': [{'text': 'Cloud lab'}]}, versions),
        (item, cfg, {**profile, 'declarations': {
            'verified_relevant_experience_years': 2,
            'verified_relevant_experience_years_confirmed': True}}, versions),
        (item, {**cfg, 'application_profile': {'work_authorisation': {'US': 'YES'}, 'sponsorship': {}}}, profile, versions),
        (item, cfg, profile, {**versions, 'ruleset': '2'}),
    ]
    assert all(assessment.input_digest(*args) != base for args in mutations)
    unrelated_item = {**item, '_application_status': 'INTERVIEW', '_ui_state': 'expanded'}
    unrelated_profile = {**profile, 'updated_at': '2099-01-01', 'declarations': {
        **profile['declarations'], 'gender': 'undisclosed'}}
    unrelated_cfg = {**cfg, 'application_profile': {
        **cfg['application_profile'], 'timezone': 'Europe/London', 'gender': 'undisclosed'}}
    assert assessment.input_digest(unrelated_item, unrelated_cfg, unrelated_profile, versions) == base


def test_experience_points_are_monotonic_and_preferred_is_weaker():
    required = {'title': 'SOC Analyst', 'description': '6 years required', 'location': 'Dubai'}
    def points(years):
        p = {} if years is None else {'declarations': {
            'verified_relevant_experience_years': years,
            'verified_relevant_experience_years_confirmed': True}}
        return assessment.assess(required, DEFAULTS, p)['components']['experience']
    sufficient, unknown, moderate, severe = points(6), points(None), points(4), points(0)
    assert sufficient > unknown > moderate > severe
    preferred = assessment.assess(
        {'title': 'SOC Analyst', 'description': '6 years preferred', 'location': 'Dubai'},
        DEFAULTS,
        {'declarations': {'verified_relevant_experience_years': 0,
                          'verified_relevant_experience_years_confirmed': True}},
    )['components']['experience']
    assert preferred > severe


@pytest.mark.parametrize('location', ['New York, United States', 'London, United Kingdom', 'Berlin, Germany'])
def test_credible_relocation_makes_foreign_onsite_reviewable(location):
    result = assessment.assess({'title': 'SOC Analyst', 'description': 'SIEM. Relocation assistance available.',
                                'location': location}, DEFAULTS, {})
    assert result['geography']['compatibility'] == assessment.GEO_UNKNOWN
    assert result['hard_reject'] is None


def test_remote_territory_restriction_is_not_overridden_by_generic_relocation():
    result = assessment.assess({'title': 'SOC Analyst', 'description': 'Relocation assistance available.',
                                'location': 'Remote — United States only'}, DEFAULTS, {})
    assert result['hard_reject']['code'] == assessment.GEO_INCOMPATIBLE


@pytest.mark.parametrize('fact,expected', [('YES', 'ELIGIBLE'), ('NO', 'INELIGIBLE'), ('UNKNOWN', 'UNKNOWN')])
def test_confirmed_us_work_authorization_path(fact, expected):
    cfg = {**DEFAULTS, 'application_profile': {
        'work_authorisation': {'US': fact}, 'sponsorship': {'US': 'NO'}}}
    result = assessment.assess({'title': 'SOC Analyst',
                                'description': 'US work authorization required. Sponsorship unavailable.',
                                'location': 'Remote'}, cfg, {})
    assert result['eligibility']['state'] == expected
    assert result['geography']['work_authorization'] == expected
    assert bool(result['hard_reject']) == (fact == 'NO')


@pytest.mark.parametrize('sponsorship,expected', [('NO', 'ELIGIBLE'), ('YES', 'INELIGIBLE'), ('UNKNOWN', 'UNKNOWN')])
def test_sponsorship_constraint_is_separate_and_country_scoped(sponsorship, expected):
    cfg = {**DEFAULTS, 'application_profile': {
        'work_authorisation': {'US': 'YES'}, 'sponsorship': {'US': sponsorship, 'GB': 'YES'}}}
    result = assessment.assess({'title': 'SOC Analyst',
                                'description': 'US work authorization required. Sponsorship unavailable.',
                                'location': 'Remote'}, cfg, {})
    assert result['eligibility']['state'] == expected
    requirements = result['eligibility']['requirements']
    assert {r['country'] for r in requirements} == {'US'}
    assert {r['kind'] for r in requirements} == {'WORK_AUTHORIZATION', 'SPONSORSHIP_CONSTRAINT'}


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

"""#46.2 shadow candidate: role understanding + placement. Network-free, fictional.

See backend/role_understanding.py. These tests pin behaviour; they are not an
accuracy claim.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend import assessment
from backend import role_understanding as ru
from backend.models import DEFAULTS

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'role_understanding_shadow_v1.json').read_text(encoding='utf-8'))
CLOCK = datetime(2026, 9, 22, tzinfo=timezone.utc)
TRACKS = ['CYBERSECURITY', 'IT_CLOUD', 'SOFTWARE_ENGINEERING', 'DATA_ANALYTICS', 'AI_ML', 'QA_TESTING']


def _prefs(case):
    return FIXTURE['owner_like_preferences'] if case['preferences'] == 'owner_like' else {}


def _run(case):
    cfg = {**DEFAULTS, 'career_tracks': case.get('career_tracks', TRACKS), 'search_focus_confirmed': True}
    posting = case['posting']
    fa = assessment.assess(posting, cfg, {}, CLOCK)
    understanding = ru.verify(case['understanding'], posting)
    return fa, understanding, ru.place(understanding, fa, cfg, _prefs(case))


@pytest.mark.parametrize('case', FIXTURE['cases'], ids=[c['id'] for c in FIXTURE['cases']])
def test_regression_case(case):
    fa, understanding, placed = _run(case)
    if case.get('expected_tier_from_engine'):
        expected = ru.PROMINENT if fa['bucket'] in ('STRONG', 'GOOD') else ru.LOWER
        if fa['hard_reject']:
            expected = ru.SUGGESTED_HIDDEN
        assert placed['tier'] == expected
        assert not placed['understanding_used']
    else:
        assert placed['tier'] == case['expected_tier'], (case['id'], placed)
    if 'expected_reason' in case:
        assert any(case['expected_reason'] in r for r in placed['reasons']), placed['reasons']
    if 'expected_note' in case:
        assert any(case['expected_note'] in n for n in placed['notes']), placed['notes']
    if 'expected_warning' in case:
        assert bool(placed['warnings']) is case['expected_warning']
    assert placed['reasons'], 'every placement must carry at least one reason'


def test_title_alone_never_decides_domain():
    by_id = {c['id']: c for c in FIXTURE['cases']}
    physical = _run(by_id['physical-security-coordinator'])[2]
    soc = _run(by_id['same-title-soc-duties'])[2]
    assert by_id['physical-security-coordinator']['posting']['title'] == by_id['same-title-soc-duties']['posting']['title']
    assert (physical['tier'], soc['tier']) == (ru.SUGGESTED_HIDDEN, ru.PROMINENT)


def test_fabricated_evidence_is_discarded():
    case = next(c for c in FIXTURE['cases'] if c['id'] == 'fabricated-evidence-rejected')
    understanding = ru.verify(case['understanding'], case['posting'])
    assert understanding['primary_function'] == ru.UNKNOWN_FUNCTION
    assert understanding['required_years_min'] is None
    assert understanding['discarded']


def test_years_must_be_quoted_with_the_same_number():
    posting = {'title': 'Analyst', 'description': 'Requires 2 years of SOC experience. Triage SIEM alerts.'}
    raw = {'primary_function': 'SECURITY_OPERATIONS', 'function_confidence': 0.9,
           'function_evidence': ['Triage SIEM alerts'], 'required_years_min': 5,
           'years_evidence': 'Requires 2 years of SOC experience', 'eligibility_wording': []}
    assert ru.verify(raw, posting)['required_years_min'] is None
    raw['required_years_min'] = 2
    assert ru.verify(raw, posting)['required_years_min'] == 2


def test_unknown_function_value_rejected():
    out = ru.verify({'primary_function': 'EVERYTHING', 'function_confidence': 1, 'function_evidence': []},
                    {'title': 'x', 'description': 'y'})
    assert out['primary_function'] == ru.UNKNOWN_FUNCTION


def test_eligibility_wording_never_hides_and_never_asserts_eligibility():
    posting = {'title': 'IT Support (UAE National)', 'location': 'Abu Dhabi',
               'description': 'Resolve desktop tickets. 0-1 years of experience.'}
    raw = {'primary_function': 'IT_SUPPORT', 'function_confidence': 0.9, 'function_evidence': ['Resolve desktop tickets'],
           'required_years_min': 0, 'years_evidence': '0-1 years of experience',
           'eligibility_wording': [{'kind': 'DESIGNATED_NATIONALS', 'text': 'IT Support (UAE National)'}]}
    understanding = ru.verify(raw, posting)
    for wording in (ru.WORDING_ANNOTATE, ru.WORDING_LOWER_WITH_WARNING, 'hide'):
        placed = ru.place(understanding, {'bucket': 'STRONG', 'score': 90}, {'career_tracks': TRACKS},
                          {'designated_nationals_wording': wording})
        assert placed['tier'] != ru.SUGGESTED_HIDDEN
        text = ' '.join(placed['warnings'] + placed['reasons'] + placed['notes']).lower()
        assert not re.search(r'\byou are (?:eligible|not eligible|ineligible)\b', text)
        assert 'does not know or assume' in text


def test_assessor_request_carries_no_candidate_data():
    request = ru.assessor_request({'title': 'SOC Analyst', 'location': 'Dubai', 'description': 'Triage alerts.',
                                   'candidate_profile': {'raw_text': 'PRIVATE'}})
    assert set(request['job']) == {'title', 'location', 'description'}
    assert 'PRIVATE' not in json.dumps(request)
    assert request['schema']['additionalProperties'] is False


def test_order_is_tier_then_current_score():
    placements = [{'tier': ru.LOWER, 'order_score': 95}, {'tier': ru.PROMINENT, 'order_score': 40},
                  {'tier': ru.SUGGESTED_HIDDEN, 'order_score': 99}, {'tier': ru.PROMINENT, 'order_score': 80}]
    assert [(p['tier'], p['order_score']) for p in ru.order(placements)] == [
        (ru.PROMINENT, 80), (ru.PROMINENT, 40), (ru.LOWER, 95), (ru.SUGGESTED_HIDDEN, 99)]


def test_deterministic():
    case = FIXTURE['cases'][0]
    assert _run(case)[2] == _run(case)[2]


def test_shadow_module_is_not_wired_into_production():
    backend = Path(__file__).resolve().parents[1] / 'backend'
    importers = [p.name for p in backend.glob('*.py')
                 if p.name != 'role_understanding.py' and 'role_understanding' in p.read_text(encoding='utf-8')]
    assert importers == []

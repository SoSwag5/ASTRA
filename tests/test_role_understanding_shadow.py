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
               'description': 'Resolve desktop tickets for office users. 0-1 years of experience.'}
    raw = {'primary_function': 'IT_SUPPORT', 'function_confidence': 0.9,
           'function_evidence': ['Resolve desktop tickets for office users'],
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


# --- Adversarial tests for the independently reproduced defects -------------

OWNER_LIKE = FIXTURE['owner_like_preferences']
CFG = {**DEFAULTS, 'career_tracks': TRACKS, 'search_focus_confirmed': True}


def _answer(function, confidence, evidence, years=None, years_evidence=None, wording=()):
    return {'primary_function': function, 'function_confidence': confidence, 'function_evidence': list(evidence),
            'required_years_min': years, 'years_evidence': years_evidence, 'eligibility_wording': list(wording)}


def _placed(posting, answer, prefs=OWNER_LIKE):
    fa = assessment.assess(posting, CFG, {}, CLOCK)
    return fa, ru.place(ru.verify(answer, posting), fa, CFG, prefs)


SOC_JOB = {'title': 'Junior SOC Analyst', 'location': 'Abu Dhabi, United Arab Emirates',
           'description': 'Role: Junior SOC Analyst. Triage SIEM alerts and escalate confirmed incidents to the '
                          'incident response team. 0-2 years of experience.'}


@pytest.mark.parametrize('evidence', [['Junior SOC Analyst'], ['Role: Junior SOC Analyst'], ['a'], ['.'],
                                      ['SIEM'], []])
@pytest.mark.parametrize('confidence', [0.0, 0.95])
def test_title_only_or_tiny_evidence_cannot_hide_a_relevant_job(evidence, confidence):
    fa, placed = _placed(SOC_JOB, _answer('PHYSICAL_SECURITY', confidence, evidence))
    assert placed['tier'] != ru.SUGGESTED_HIDDEN
    assert placed['tier'] == (ru.PROMINENT if fa['bucket'] in ('STRONG', 'GOOD') else ru.LOWER)
    assert not placed['understanding_used']


def test_zero_confidence_reading_with_real_duty_evidence_cannot_hide():
    span = 'Triage SIEM alerts and escalate confirmed incidents to the incident response team'
    _, placed = _placed(SOC_JOB, _answer('PHYSICAL_SECURITY', 0.0, [span]))
    assert placed['tier'] != ru.SUGGESTED_HIDDEN and 'below the 0.7 confidence' in placed['reasons'][0]


GUARD_JOB = {'title': 'Security Guard', 'location': 'Dubai, United Arab Emirates',
             'description': 'Patrol the premises and monitor CCTV at the main gate. Security guard licence required.'}


@pytest.mark.parametrize('evidence,confidence', [
    (['Security Guard'], 0.99),                      # title only
    (['a'], 0.99),                                   # one character
    (['Patrol the premises and monitor CCTV at the main gate'], 0.0),   # real span, zero confidence
    (['Patrol the premises and monitor CCTV at the main gate'], 0.6),   # real span, low confidence
])
def test_weak_reading_cannot_override_domain_incompatible(evidence, confidence):
    fa, placed = _placed(GUARD_JOB, _answer('SECURITY_OPERATIONS', confidence, evidence))
    assert fa['hard_reject'] and fa['hard_reject']['code'] == 'DOMAIN_INCOMPATIBLE'
    assert placed['tier'] == ru.SUGGESTED_HIDDEN
    assert 'current engine rejection kept: DOMAIN_INCOMPATIBLE' in placed['reasons'][0]


def test_only_a_confident_duty_reading_supersedes_domain_incompatible():
    """The one move a verified reading may make against the engine: replace its
    keyword DOMAIN_INCOMPATIBLE when duties show an enabled technical field."""
    posting = {'title': 'Operations Officer', 'location': 'Dubai, United Arab Emirates',
               'description': 'Triage SIEM alerts from the monitoring console and escalate incidents every shift.'}
    keyword_rejection = {'hard_reject': {'code': 'DOMAIN_INCOMPATIBLE'}, 'bucket': 'REJECTED', 'score': None}
    span = 'Triage SIEM alerts from the monitoring console and escalate incidents every shift'
    confident = ru.place(ru.verify(_answer('SECURITY_OPERATIONS', 0.9, [span]), posting), keyword_rejection, CFG, OWNER_LIKE)
    assert confident['tier'] == ru.PROMINENT and confident['understanding_used']
    for weak in (_answer('SECURITY_OPERATIONS', 0.69, [span]), _answer('SECURITY_OPERATIONS', 0.9, ['Operations Officer'])):
        placed = ru.place(ru.verify(weak, posting), keyword_rejection, CFG, OWNER_LIKE)
        assert placed['tier'] == ru.SUGGESTED_HIDDEN and not placed['understanding_used']


@pytest.mark.parametrize('description,span,expected', [
    ('Build ETL pipelines in Python and SQL every day. 5 years preferred.', '5 years preferred', None),
    ('Build ETL pipelines in Python and SQL every day. 5 years of experience preferred.', '5 years of experience', None),
    ('Build ETL pipelines in Python and SQL every day. Preferably 5 years in data roles.', 'Preferably 5 years in data roles', None),
    ('Build ETL pipelines in Python and SQL every day. 5+ years in data engineering (desirable).', '5+ years in data engineering', None),
    ('Build ETL pipelines in Python and SQL every day. Required qualifications: degree. '
     'Preferred qualifications: 5 years in data engineering.', '5 years in data engineering', None),
    ('Build ETL pipelines in Python and SQL every day. Desired experience: 5 years in data engineering.',
     '5 years in data engineering', None),
    ('Build ETL pipelines in Python and SQL every day. Required experience: 5 years in data engineering.',
     '5 years in data engineering', 5),
    ('Build ETL pipelines in Python and SQL every day. Minimum 5 years in data engineering. '
     'Preferred qualifications: cloud certification.', 'Minimum 5 years in data engineering', 5),
])
def test_preferred_experience_is_never_required(description, span, expected):
    posting = {'title': 'Data Engineer', 'description': description}
    answer = _answer('DATA_ENGINEERING', 0.9, ['Build ETL pipelines in Python and SQL every day'], 5, span)
    assert ru.verify(answer, posting)['required_years_min'] == expected


def test_preferred_years_never_hide_a_relevant_job():
    posting = {'title': 'Data Engineer', 'location': 'Abu Dhabi, United Arab Emirates',
               'description': 'Build ETL pipelines in Python and SQL every day. 5 years preferred.'}
    _, placed = _placed(posting, _answer('DATA_ENGINEERING', 0.9, ['Build ETL pipelines in Python and SQL every day'],
                                         5, '5 years preferred'))
    assert placed['tier'] == ru.PROMINENT


def test_nationality_preference_note_makes_no_unsupported_claim():
    posting = {'title': 'Service Desk Analyst', 'location': 'Dubai, United Arab Emirates',
               'description': 'First line ICT service desk support for office users. '
                              'Preference will be given to UAE nationals.'}
    _, placed = _placed(posting, _answer('IT_SUPPORT', 0.9, ['First line ICT service desk support for office users'],
                                         wording=[{'kind': 'NATIONALS_PREFERENCE',
                                                   'text': 'Preference will be given to UAE nationals'}]))
    text = ' '.join(placed['notes'] + placed['warnings'] + placed['reasons']).lower()
    assert 'all applicants' not in text and 'considered' not in text
    assert 'employer’s wording' in text and not re.search(r'\byou (?:are|may be) (?:eligible|ineligible)\b', text)
    assert placed['tier'] == ru.PROMINENT


def test_owner_designated_role_stays_visible_lower_with_warning():
    posting = {'title': 'Associate Support Engineer ( UAE National )', 'location': 'Abu Dhabi, United Arab Emirates',
               'description': 'Provide L1 support for business applications and log incidents. 0-2 years (Fresh Graduate).'}
    answer = _answer('APPLICATION_SUPPORT', 0.9, ['Provide L1 support for business applications and log incidents'],
                     0, '0-2 years (Fresh Graduate)',
                     [{'kind': 'DESIGNATED_NATIONALS', 'text': 'Associate Support Engineer ( UAE National )'}])
    _, placed = _placed(posting, answer)
    assert placed['tier'] == ru.LOWER and placed['warnings']
    assert 'does not know or assume' in placed['warnings'][0]


def test_eligibility_wording_must_be_about_nationality():
    posting = {'title': 'Graduate Software Engineer', 'description': 'Develop and test backend services in Python daily.'}
    answer = _answer('SOFTWARE_ENGINEERING', 0.9, ['Develop and test backend services in Python daily'],
                     wording=[{'kind': 'DESIGNATED_NATIONALS', 'text': 'Graduate Software Engineer'}])
    assert ru.verify(answer, posting)['eligibility_wording'] == []


def test_evidence_is_checked_against_the_bounded_text_sent_to_the_assessor():
    filler = 'x ' * (ru.MAX_INPUT_CHARS // 2)
    posting = {'title': 'T' * 400 + ' Emirati', 'description': filler + 'Triage SIEM alerts and escalate incidents daily.'}
    request = ru.assessor_request(posting)
    assert 'Triage SIEM' not in request['job']['description'] and 'Emirati' not in request['job']['title']
    answer = _answer('SECURITY_OPERATIONS', 0.95, ['Triage SIEM alerts and escalate incidents daily'],
                     wording=[{'kind': 'DESIGNATED_NATIONALS', 'text': 'Emirati'}])
    out = ru.verify(answer, posting)
    assert out['primary_function'] == ru.UNKNOWN_FUNCTION and out['eligibility_wording'] == []


MALFORMED = [
    None, [], 'SECURITY_OPERATIONS', 7, {'primary_function': 'IT_SUPPORT'},
    {**_answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users']), 'extra': 1},
    _answer('IT_SUPPORT', float('nan'), ['Resolve desktop tickets for office users']),
    _answer('IT_SUPPORT', float('inf'), ['Resolve desktop tickets for office users']),
    _answer('IT_SUPPORT', True, ['Resolve desktop tickets for office users']),
    _answer('IT_SUPPORT', '0.9', ['Resolve desktop tickets for office users']),
    _answer('IT_SUPPORT', 1.5, ['Resolve desktop tickets for office users']),
    _answer('IT_SUPPORT', 0.9, 'Resolve desktop tickets for office users'),
    _answer('IT_SUPPORT', 0.9, [{'text': 'Resolve desktop tickets'}]),
    _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'] * 50),
    _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'], True, '1 year'),
    _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'], 2.0, '2 years'),
    _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'], 99, '99 years'),
    _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'], 1, ['1 year']),
    _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'], wording=['UAE National']),
    _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'],
            wording=[{'kind': 'DESIGNATED_NATIONALS', 'text': 'UAE National', 'eligible': True}]),
    _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'],
            wording=[{'kind': 'ELIGIBLE', 'text': 'UAE National'}]),
    {**_answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users']), 'assessor': {'x': 1}},
    {**_answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users']), 'candidate_is_eligible': True},
]


@pytest.mark.parametrize('raw', MALFORMED, ids=[f'malformed-{i}' for i in range(len(MALFORMED))])
def test_malformed_answers_are_rejected_whole_and_never_raise(raw):
    posting = {'title': 'IT Support (UAE National)', 'location': 'Dubai',
               'description': 'Resolve desktop tickets for office users. 1 year of experience.'}
    out = ru.verify(raw, posting)
    assert out['primary_function'] == ru.UNKNOWN_FUNCTION and out['required_years_min'] is None
    assert out['eligibility_wording'] == [] and out['discarded']
    placed = ru.place(out, {'bucket': 'LOW', 'score': 40}, CFG, OWNER_LIKE)
    assert placed['tier'] == ru.LOWER and not placed['understanding_used']


def test_eval_script_never_opens_or_accepts_holdout_items(tmp_path):
    import subprocess
    import sys
    snaps = tmp_path / 'snaps'
    snaps.mkdir()
    (snaps / 'X01.txt').write_text('Resolve desktop tickets for office users. 1 year of experience.', encoding='utf-8')
    items = {'items': [
        {'item_id': 'X01', 'split': 'development', 'title': 'IT Support', 'employer': 'Fictional Co',
         'official_url': 'https://example.invalid/x01', 'platform': 'fixture', 'location_stated': 'Dubai'},
        {'item_id': 'Y01', 'split': 'holdout', 'title': 'SECRET HOLDOUT TITLE', 'employer': 'Other Co',
         'official_url': 'https://example.invalid/y01', 'platform': 'fixture', 'location_stated': 'Dubai'}]}
    understandings = {'items': {'X01': _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'])}}
    labels = {'labels': {'X01': {'first_saved_choice': 'show_lower'}}}
    profile = {'source': 'fictional', 'career_config': {'career_tracks': TRACKS}, 'profile': {}}
    paths = {}
    for name, obj in (('items', items), ('understandings', understandings), ('labels', labels),
                      ('profile', profile), ('preferences', OWNER_LIKE)):
        paths[name] = tmp_path / f'{name}.json'
        paths[name].write_text(json.dumps(obj), encoding='utf-8')
    script = str(Path(__file__).resolve().parents[1] / 'scripts' / 'shadow_role_eval.py')

    def run(labels_path):
        args = [sys.executable, script, '--snapshots', str(snaps), '--out', str(tmp_path / 'out.json'),
                '--labels', str(labels_path)]
        for name in ('items', 'understandings', 'profile', 'preferences'):
            args += ['--' + name, str(paths[name])]
        return subprocess.run(args, capture_output=True, text=True, timeout=120)

    ok = run(paths['labels'])
    assert ok.returncode == 0, ok.stderr
    out = json.loads((tmp_path / 'out.json').read_text(encoding='utf-8'))
    assert out['holdout_boundary']['holdout_items_seen'] == 1
    assert out['holdout_boundary']['holdout_snapshots_opened'] == 0
    assert out['holdout_boundary']['snapshots_opened'] == ['X01']
    assert 'SECRET HOLDOUT TITLE' not in json.dumps(out) and 'Y01' not in json.dumps(out['rows'])

    bad = tmp_path / 'bad_labels.json'
    bad.write_text(json.dumps({'labels': {**labels['labels'], 'Y01': {'first_saved_choice': 'hide'}}}), encoding='utf-8')
    refused = run(bad)
    assert refused.returncode != 0 and 'holdout' in (refused.stderr + refused.stdout).lower()


UNHASHABLE_KINDS = [['DESIGNATED_NATIONALS'], {'k': 'DESIGNATED_NATIONALS'}, {'DESIGNATED_NATIONALS'}, None, 3]


@pytest.mark.parametrize('kind', UNHASHABLE_KINDS, ids=[type(k).__name__ for k in UNHASHABLE_KINDS])
def test_unhashable_or_wrong_type_wording_kind_is_rejected_not_raised(kind):
    posting = {'title': 'IT Support (UAE National)', 'description': 'Resolve desktop tickets for office users.'}
    answer = _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'],
                     wording=[{'kind': kind, 'text': 'UAE National'}])
    out = ru.verify(answer, posting)
    assert out['primary_function'] == ru.UNKNOWN_FUNCTION and out['eligibility_wording'] == []
    assert any('eligibility_wording' in d for d in out['discarded'])


def test_random_malformed_answers_never_raise():
    import random
    rng = random.Random(4620922)
    atoms = [None, True, 0, -1, 1.5, float('nan'), '', 'x', 'IT_SUPPORT', 'DESIGNATED_NATIONALS', [], {}]

    def value(depth=0):
        roll = rng.random()
        if depth > 2 or roll < 0.5:
            return rng.choice(atoms)
        if roll < 0.75:
            return [value(depth + 1) for _ in range(rng.randint(0, 3))]
        return {rng.choice(['kind', 'text', 'x', 'primary_function']): value(depth + 1) for _ in range(rng.randint(0, 3))}

    keys = sorted(ru.RESPONSE_KEYS) + ['assessor', 'extra']
    posting = {'title': 'IT Support', 'description': 'Resolve desktop tickets for office users. 1 year of experience.'}
    for _ in range(2000):
        raw = {k: value() for k in keys if rng.random() < 0.8}
        if rng.random() < 0.3:
            raw['eligibility_wording'] = [{'kind': value(), 'text': value()}]
        out = ru.verify(raw, posting)
        assert out['primary_function'] in ru.FUNCTIONS
        ru.place(out, {'bucket': 'LOW', 'score': 40}, CFG, OWNER_LIKE)

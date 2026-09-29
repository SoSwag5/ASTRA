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


X01_TEXT = ('Resolve desktop tickets for office users and keep the asset register current. Install and patch '
            'laptops, reset accounts, and escalate network faults to the infrastructure team. 1 year of '
            'experience in a service desk role is required.\nPreferred qualifications:\n 3 years preferred.')


def _dev_tree(tmp_path, items_extra=(), label_extra=None, understand_extra=None, x01_text=X01_TEXT, item_patch=None):
    """A fictional private tree: one development item X01, one holdout Y01."""
    import hashlib
    snaps = tmp_path / 'snaps'
    snaps.mkdir(exist_ok=True)
    (snaps / 'X01.txt').write_text(x01_text, encoding='utf-8')
    (snaps / 'Y01.txt').write_text('SECRET HOLDOUT BODY ' * 20, encoding='utf-8')
    x01 = {'item_id': 'X01', 'split': 'development', 'title': 'Service Desk Zetaworks', 'employer': 'Fictional Co',
           'official_url': 'https://example.invalid/x01', 'platform': 'fixture', 'location_stated': 'Dubai',
           'desc_sha256': hashlib.sha256(X01_TEXT.encode('utf-8')).hexdigest(), 'desc_chars': len(X01_TEXT)}
    x01.update(item_patch or {})
    items = {'items': [x01, {'item_id': 'Y01', 'split': 'holdout', 'title': 'SECRET HOLDOUT TITLE',
                             'employer': 'Other Co', 'official_url': 'https://example.invalid/y01',
                             'platform': 'fixture', 'location_stated': 'Dubai', 'desc_sha256': '0' * 64,
                             'desc_chars': 400}, *items_extra]}
    understandings = {'items': {'X01': _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users']),
                                **(understand_extra or {})}}
    labels = {'labels': {'X01': {'first_saved_choice': 'show_lower', 'current_choice': 'show_lower'},
                         **(label_extra or {})}}
    profile = {'source': 'fictional', 'career_config': {'career_tracks': TRACKS}, 'profile': {}}
    args = ['--snapshots', str(snaps), '--out', str(tmp_path / 'out.json')]
    for name, obj in (('items', items), ('understandings', understandings), ('labels', labels),
                      ('profile', profile), ('preferences', {'preferences': OWNER_LIKE})):
        path = tmp_path / f'{name}.json'
        path.write_text(json.dumps(obj), encoding='utf-8')
        args += ['--' + name, str(path)]
    return args


def _run_dev(args):
    import subprocess
    import sys
    script = str(Path(__file__).resolve().parents[1] / 'scripts' / 'shadow_role_eval.py')
    return subprocess.run([sys.executable, script, *args], capture_output=True, text=True, timeout=120)


def test_eval_script_never_opens_or_accepts_holdout_items(tmp_path):
    ok = _run_dev(_dev_tree(tmp_path))
    assert ok.returncode == 0, ok.stderr
    out = json.loads((tmp_path / 'out.json').read_text(encoding='utf-8'))
    boundary = out['boundary']
    assert boundary['other_split_rows_parsed'] == 1 and boundary['other_split_snapshots_opened_by_this_process'] == 0
    assert boundary['snapshots_opened_by_this_process'] == ['X01']
    assert 'cannot show what any person' in boundary['scope']
    text = json.dumps(out)
    assert 'SECRET HOLDOUT' not in text and 'Y01' not in json.dumps(out['rows'])
    assert out['network_attempts'] == [] and set(out['inputs_sha256']) == {'items', 'understandings', 'labels',
                                                                             'profile', 'preferences'}
    # the X01 years span sits under a preferred heading only for the 3 years; 1 year is required
    assert out['rows'][0]['candidate']['tier'] == ru.PROMINENT


@pytest.mark.parametrize('extra,needle', [
    ({'label_extra': {'Y01': {'first_saved_choice': 'hide'}}}, 'outside the selected split'),
    ({'understand_extra': {'Y01': _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'])}},
     'outside the selected split'),
    ({'items_extra': [{'item_id': 'X01', 'split': 'holdout', 'desc_sha256': '0' * 64, 'desc_chars': 1}]},
     'duplicate item id'),
    ({'items_extra': [{'item_id': 'Z01', 'split': 'holdot', 'desc_sha256': '0' * 64, 'desc_chars': 1}]},
     'unknown split'),
    ({'items_extra': [{'item_id': '../Y01', 'split': 'development', 'desc_sha256': '0' * 64, 'desc_chars': 1}]},
     'malformed'),
    ({'x01_text': X01_TEXT + ' tampered'}, 'does not match its frozen sha256'),
    ({'item_patch': {'desc_sha256': 'not-a-hash'}}, 'no frozen description sha256'),
])
def test_eval_script_fails_closed(tmp_path, extra, needle):
    refused = _run_dev(_dev_tree(tmp_path, **extra))
    assert refused.returncode != 0
    assert needle in refused.stderr and 'refusing to run' in refused.stderr
    assert 'SECRET HOLDOUT' not in refused.stderr + refused.stdout
    assert not (tmp_path / 'out.json').exists()


def test_eval_script_excludes_unsure_and_unreadable_without_crashing(tmp_path):
    import hashlib
    short = 'Too short.'
    extra = [{'item_id': 'X02', 'split': 'development', 'title': 'Short', 'employer': 'Fictional Co',
              'desc_sha256': hashlib.sha256(short.encode()).hexdigest(), 'desc_chars': len(short)},
             {'item_id': 'X03', 'split': 'development', 'title': 'Unsure', 'employer': 'Fictional Co',
              'desc_sha256': hashlib.sha256(X01_TEXT.encode()).hexdigest(), 'desc_chars': len(X01_TEXT)}]
    args = _dev_tree(tmp_path, items_extra=extra,
                     label_extra={'X02': {'first_saved_choice': 'show_lower'},
                                  'X03': {'first_saved_choice': 'unsure', 'current_choice': 'hide'}})
    (tmp_path / 'snaps' / 'X02.txt').write_text(short, encoding='utf-8')
    (tmp_path / 'snaps' / 'X03.txt').write_text(X01_TEXT, encoding='utf-8')
    done = _run_dev(args)
    assert done.returncode == 0, done.stderr
    out = json.loads((tmp_path / 'out.json').read_text(encoding='utf-8'))
    reasons = {e['item_id']: ' '.join(e['reasons']) for e in out['excluded']}
    assert 'SOURCE_UNREADABLE' in reasons['X02'] and 'unsure' in reasons['X03']
    assert out['later_label_changes'] == [{'item_id': 'X03', 'first_saved_choice': 'unsure', 'current_choice': 'hide'}]
    assert out['items_scored'] == 1 and 'X02' not in out['boundary']['snapshots_opened_by_this_process']


def test_network_guard_blocks_resolution_connect_send_and_bind():
    import subprocess
    import sys
    scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
    code = ('import sys, socket, _socket; sys.path.insert(0, %r); import c_eval_common as c; c.disable_network()\n'
            'calls = [lambda: socket.create_connection(("127.0.0.1", 9)), lambda: socket.getaddrinfo("example.invalid", 443),\n'
            '         lambda: socket.gethostbyname("localhost"), lambda: socket.socket().connect(("10.0.0.1", 80)),\n'
            '         lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("127.0.0.1", 9)),\n'
            '         lambda: _socket.socket().connect(("127.0.0.1", 9)), lambda: socket.socket().bind(("127.0.0.1", 0))]\n'
            'for call in calls:\n'
            '    try:\n        call(); print("ALLOWED")\n    except OSError as e:\n        print("blocked", e)\n') % scripts
    done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.count('network disabled') == 7 and 'ALLOWED' not in done.stdout


def test_dev_report_carries_no_titles_quotes_or_label_free_text(tmp_path):
    import hashlib
    text = X01_TEXT + '\nPreference will be given to UAE nationals.'
    args = _dev_tree(tmp_path, x01_text=text,
                     item_patch={'desc_sha256': hashlib.sha256(text.encode()).hexdigest(), 'desc_chars': len(text)},
                     understand_extra={'X01': _answer('IT_SUPPORT', 0.9, ['Resolve desktop tickets for office users'],
                                                      wording=[{'kind': 'NATIONALS_PREFERENCE',
                                                                'text': 'Preference will be given to UAE nationals'}])},
                     label_extra={'X01': {'first_saved_choice': 'show_lower', 'use_for_fit_scoring': True,
                                          'reason': 'PRIVATE OWNER REASON'}})
    done = _run_dev(args)
    assert done.returncode == 0, done.stderr
    report = (tmp_path / 'out.json').read_text(encoding='utf-8')
    assert 'Zetaworks' not in report and 'Preference will be given' not in report
    assert '[employer wording]' in report and 'PRIVATE OWNER REASON' not in report


# --- v3 candidate: preferred versus required, ranges, adjacent roles, band ---

OWNER_V3 = FIXTURE['owner_like_preferences']
SOC_DUTY = 'Triage SIEM alerts and escalate incidents to the IR team'


@pytest.mark.parametrize('tail,span,expected', [
    ('Requirements: degree in IT. Preferred qualifications: certifications that meet the requirements of the '
     'SOC. 5 years in a SOC.', '5 years in a SOC', None),                       # body word does not reset
    ('Good to have: 5 years in a SOC.', '5 years in a SOC', None),
    ('Preferred:\n 5 years in a SOC.', '5 years in a SOC', None),
    ('Preferred qualifications: ' + 'Familiarity with many security tools and frameworks. ' * 14
     + '5 years in a SOC.', '5 years in a SOC', None),                          # heading far above
    ('Preferred qualifications:\n You meet the following requirements: 5 years in a SOC.', '5 years in a SOC', None),
    ('Preferred qualifications: CISSP.\nRequirements:\n 5 years in a SOC.', '5 years in a SOC', 5),
    ('\n BASIC QUALIFICATIONS \n 2 years in a SOC.\n PREFERRED QUALIFICATIONS \n Internship', '2 years in a SOC', 2),
    ('Minimum Work Experience : - \n 5+ years in a SOC.', '5+ years in a SOC', 5),
    ('5 years in a SOC.', '5 years in a SOC', 5),
])
def test_preferred_headings_are_read_from_line_structure(tail, span, expected):
    posting = {'title': 'SOC Analyst', 'description': SOC_DUTY + '. ' + tail}
    years = int(re.search(r'\d+', span).group())
    assert ru.verify(_answer('SECURITY_OPERATIONS', 0.9, [SOC_DUTY], years, span), posting)['required_years_min'] == expected


@pytest.mark.parametrize('span,claimed,expected', [
    ('3-5 years in a SOC', 5, 3), ('2 to 4 years of SOC experience', 4, 2), ('3 – 6 years in a SOC', 6, 3),
    ('0 - 1 years in a SOC', 0, 0), ('3-5 years in a SOC', 3, 3),
    ('Minimum 2 years in a SOC (2019-2021 programme)', 2, 2), ('24-7 rota; 2 years in a SOC', 2, 2),
])
def test_a_range_upper_bound_is_never_the_required_minimum(span, claimed, expected):
    posting = {'title': 'SOC Analyst', 'description': f'{SOC_DUTY}. Requirements: {span}.'}
    out = ru.verify(_answer('SECURITY_OPERATIONS', 0.9, [SOC_DUTY], claimed, span), posting)
    assert out['required_years_min'] == expected
    assert any('upper part of a quoted range' in d for d in out['discarded']) is (claimed != expected)


ADJ_JOB = {'title': 'Junior Systems Coordinator', 'location': 'Abu Dhabi, United Arab Emirates',
           'description': 'Maintain release trackers for the enterprise resource planning system and prepare '
                          'status reports for the application team. Minimum 7 years of experience.'}
ADJ_SPAN = 'Maintain release trackers for the enterprise resource planning system'


@pytest.mark.parametrize('years,span,wording,expected', [
    (None, None, (), ru.LOWER),
    (None, None, [{'kind': 'DESIGNATED_NATIONALS', 'text': 'Junior Systems Coordinator'}], ru.LOWER),
    (7, 'Minimum 7 years of experience', (), ru.SUGGESTED_HIDDEN),
])
def test_adjacent_role_is_lower_never_prominent(years, span, wording, expected):
    fa, placed = _placed(ADJ_JOB, _answer('ICT_ADJACENT', 0.85, [ADJ_SPAN], years, span, wording), OWNER_V3)
    assert placed['tier'] == expected and placed['understanding_used']
    assert any('adjacent technical role' in r for r in placed['reasons'])
    assert ru.verify(_answer('ICT_ADJACENT', 0.85, [ADJ_SPAN]), ADJ_JOB)['primary_function'] == 'ICT_ADJACENT'


def test_adjacent_reading_supersedes_keyword_domain_rejection_but_only_to_lower():
    keyword_rejection = {'hard_reject': {'code': 'DOMAIN_INCOMPATIBLE'}, 'bucket': 'REJECTED', 'score': None}
    placed = ru.place(ru.verify(_answer('ICT_ADJACENT', 0.85, [ADJ_SPAN]), ADJ_JOB), keyword_rejection, CFG, OWNER_V3)
    assert placed['tier'] == ru.LOWER
    weak = ru.place(ru.verify(_answer('ICT_ADJACENT', 0.5, [ADJ_SPAN]), ADJ_JOB), keyword_rejection, CFG, OWNER_V3)
    assert weak['tier'] == ru.SUGGESTED_HIDDEN and not weak['understanding_used']


@pytest.mark.parametrize('years,expected,reason', [
    (2, ru.PROMINENT, 'enabled field'), (3, ru.LOWER, 'comfortable limit'), (5, ru.LOWER, 'comfortable limit'),
    (6, ru.SUGGESTED_HIDDEN, 'stretch limit'), (14, ru.SUGGESTED_HIDDEN, 'stretch limit'),
])
def test_owner_band_hides_only_at_six_or_more_required_years(years, expected, reason):
    posting = {'title': 'Security Engineer', 'location': 'Abu Dhabi, United Arab Emirates',
               'description': f'{SOC_DUTY}. Minimum {years} years in security operations.'}
    _, placed = _placed(posting, _answer('SECURITY_OPERATIONS', 0.9, [SOC_DUTY], years,
                                         f'Minimum {years} years in security operations'), OWNER_V3)
    assert placed['tier'] == expected and any(reason in r for r in placed['reasons'])
    assert OWNER_V3['stretch_max_years'] == 5


def test_preferred_years_never_move_a_relevant_role_under_the_owner_band():
    posting = {'title': 'Security Engineer', 'location': 'Abu Dhabi, United Arab Emirates',
               'description': f'{SOC_DUTY}.\nPreferred qualifications:\n 8 years in security operations.'}
    _, placed = _placed(posting, _answer('SECURITY_OPERATIONS', 0.9, [SOC_DUTY], 8,
                                         '8 years in security operations'), OWNER_V3)
    assert placed['tier'] == ru.PROMINENT and any('no seniority adjustment' in n for n in placed['notes'])


@pytest.mark.parametrize('kind,prefs,expected_tier,warned', [
    ('DESIGNATED_NATIONALS', 'owner', ru.LOWER, True),
    ('DESIGNATED_NATIONALS', 'default', ru.PROMINENT, True),
    ('NATIONALS_PREFERENCE', 'owner', ru.PROMINENT, False),
])
def test_eligibility_wording_is_a_warning_never_a_decision(kind, prefs, expected_tier, warned):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import c_eval_common
    text = 'Cyber Analyst (UAE National)' if kind == 'DESIGNATED_NATIONALS' else 'Preference will be given to UAE nationals'
    posting = {'title': 'Cyber Analyst (UAE National)', 'location': 'Abu Dhabi, United Arab Emirates',
               'description': f'{SOC_DUTY}. Preference will be given to UAE nationals.'}
    _, placed = _placed(posting, _answer('SECURITY_OPERATIONS', 0.9, [SOC_DUTY], wording=[{'kind': kind, 'text': text}]),
                        OWNER_V3 if prefs == 'owner' else {})
    assert placed['tier'] == expected_tier and bool(placed['warnings']) is warned
    assert not c_eval_common.asserts_eligibility(placed['reasons'] + placed['warnings'] + placed['notes'])
    assert c_eval_common.asserts_eligibility(['You are not eligible for this role'])


def test_assessor_request_explains_every_function_and_the_range_rule():
    request = ru.assessor_request({'title': 'x', 'description': 'y'})
    assert set(request['schema']['properties']['primary_function']['enum']) == ru.FUNCTIONS
    assert set(ru.FUNCTION_GUIDE) == ru.FUNCTIONS and 'ICT_ADJACENT' in ru.FUNCTIONS
    for name in ru.FUNCTIONS:
        assert f'{name} = ' in request['instructions']
    assert 'lower bound' in request['instructions'] and 'never infer nationality' in request['instructions']
    assert (ru.SCHEMA_VERSION, ru.POLICY_VERSION) == ('role-understanding-2', 'shadow-placement-2')


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


# --- independent review round 1 (2026-09-29): compound headings, clauses, ranges ---

@pytest.mark.parametrize('tail,span,expected', [
    ('Required Qualifications:\n- Degree in IT\nPreferred Qualifications and Experience:\n- 7 years in a SOC', '7 years in a SOC', None),
    ('Required Qualifications:\n- Degree\nPreferred Skills & Experience:\n- 7 years in a SOC', '7 years in a SOC', None),
    ('Required Qualifications:\n- Degree\nPreferred qualifications include:\n- 7 years in a SOC', '7 years in a SOC', None),
    ('Requirements:\n- Degree\nNice to have:\n- Key skills: Splunk\n- 7 years in a SOC', '7 years in a SOC', None),
    ('Requirements: Degree in IT Preferred Qualifications: 7 years in a SOC', '7 years in a SOC', None),
    ('Requirements:\n- Degree\nNice to haves:\n- 7 years in a SOC', '7 years in a SOC', None),
    ('Requirements:\n- Degree\nDesirable criteria:\n- 7 years in a SOC', '7 years in a SOC', None),
    ('Requirements:\n- Degree\nPreferred:\n- Qualifications: CISSP\n- 7 years in a SOC', '7 years in a SOC', None),
    ('Requirements:\n- Degree\nPreferred/Desired Qualifications:\n- 7 years in a SOC', '7 years in a SOC', None),
    ('Required/Preferred Qualifications:\n- 7 years in a SOC', '7 years in a SOC', None),
    ('Preferred Qualifications: CISSP Requirements: 7 years in a SOC', '7 years in a SOC', 7),
    ('Requirements:\n Arabic speakers preferred\n 7 years in a SOC', '7 years in a SOC', 7),
    ('Tools: Splunk and QRadar. 7 years in a SOC', '7 years in a SOC', 7),
])
def test_compound_and_flattened_headings(tail, span, expected):
    posting = {'title': 'SOC Analyst', 'description': SOC_DUTY + '.\n' + tail}
    assert ru.verify(_answer('SECURITY_OPERATIONS', 0.9, [SOC_DUTY], 7, span), posting)['required_years_min'] == expected


@pytest.mark.parametrize('tail,claimed,span,expected', [
    ('8+ years of experience in security operations, CISSP is an advantage.', 8,
     '8+ years of experience in security operations', 8),
    ('3+ years in a SOC, CCNA a plus.', 3, '3+ years in a SOC, CCNA a plus', 3),
    ('5 years of experience, preferably in banking.', 5, '5 years of experience', 5),
    ('5 years of experience, preferred.', 5, '5 years of experience', None),
    ('Minimum 3 years (5 years preferred).', 3, 'Minimum 3 years', 3),
    ('5+ years in data engineering (desirable).', 5, '5+ years in data engineering', None),
    ('Preferably 5 years in data roles.', 5, 'Preferably 5 years in data roles', None),
    ('Hybrid 2-3 days per week; 3 years in a SOC.', 3, 'Hybrid 2-3 days per week; 3 years in a SOC', 3),
    ('Grade 3-6; 6 years in a SOC.', 6, 'Grade 3-6; 6 years in a SOC', 6),
    ('Between 3 and 7 years in a SOC.', 7, 'Between 3 and 7 years in a SOC', 3),
    ('3-to-7 years in a SOC.', 7, '3-to-7 years in a SOC', 3),
    ('15 years in a SOC.', 5, '5 years in a SOC', None),               # a figure inside a larger number is not found
])
def test_preference_must_govern_the_years_clause_and_ranges_must_be_years(tail, claimed, span, expected):
    posting = {'title': 'SOC Analyst', 'description': SOC_DUTY + '.\n' + tail}
    assert ru.verify(_answer('SECURITY_OPERATIONS', 0.9, [SOC_DUTY], claimed, span), posting)['required_years_min'] == expected


@pytest.mark.parametrize('text,kept,uae', [
    ('Cyber Analyst (UAE National)', True, True), ('Emirati Talent programme', True, True),
    ('Saudi nationals only', True, False), ('Open to all nationals', False, None),
    ('Candidates of all nationalities are welcome', False, None),
])
def test_designated_wording_is_specific_and_its_warning_says_what_it_is(text, kept, uae):
    posting = {'title': 'Cyber Analyst (UAE National)', 'location': 'Abu Dhabi, United Arab Emirates',
               'description': f'{SOC_DUTY}. {text}.'}
    answer = _answer('SECURITY_OPERATIONS', 0.9, [SOC_DUTY], wording=[{'kind': 'DESIGNATED_NATIONALS', 'text': text}])
    _, placed = _placed(posting, answer, OWNER_V3)
    assert bool(placed['warnings']) is kept and placed['tier'] != ru.SUGGESTED_HIDDEN
    if kept:
        assert ('targets UAE nationals' in placed['warnings'][0]) is uae
        assert 'does not know or assume' in placed['warnings'][0]


def test_low_confidence_adjacent_reading_leaves_the_engine_placement():
    fa, placed = _placed(ADJ_JOB, _answer('ICT_ADJACENT', 0.65, [ADJ_SPAN]), OWNER_V3)
    assert not placed['understanding_used'] and 'below the 0.7 confidence' in placed['reasons'][0]

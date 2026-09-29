"""#46.2-C blind round (scripts/c_blind_round.py). Fictional, isolated, no network.

A whole round -- requests, readings, labeling page, seal, lock, compare -- on
fictional postings, plus the fail-closed checks around it. Git history is
replaced by an in-memory stand-in and the public records go to a temporary
folder, so nothing here writes to the repository. These tests pin custody
behaviour; they are not an accuracy claim.
"""
import argparse
import hashlib
import inspect
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import c_blind_round as cbr  # noqa: E402
import c_eval_common as common  # noqa: E402
from backend import role_understanding as ru  # noqa: E402

DUTY = {
    'Y01': ('SOC Analyst', 'Triage SIEM alerts and escalate confirmed incidents to the response team', 'SECURITY_OPERATIONS', 1),
    'Y02': ('Warehouse Supervisor', 'Supervise forklift crews and schedule inbound pallet deliveries each shift', 'SUPPLY_CHAIN_MATERIALS', 3),
    'Y03': ('Service Desk Analyst (UAE National)', 'Resolve desktop and account tickets for office users every day', 'IT_SUPPORT', 0),
    'Y04': ('Senior Network Architect', 'Design the enterprise network and lead the architecture review board', 'INFRASTRUCTURE_CLOUD_NETWORK', 10),
    'Y05': ('Junior Data Analyst', 'Build SQL dashboards and analyse service ticket volumes for managers', 'DATA_ANALYTICS', 0),
    'Y06': ('Patient Care Assistant', 'Assist nurses with patient hygiene and mobility on the medical ward', 'CLINICAL_OR_THERAPY', 1),
    'Y07': ('ERP Coordinator', 'Maintain change trackers for the enterprise resource planning rollout and take minutes', 'ICT_ADJACENT', 0),
    'Y08': ('Cloud Support Engineer', 'Administer cloud virtual machines and resolve platform incidents for customers', 'INFRASTRUCTURE_CLOUD_NETWORK', 2),
    'Y09': ('Security Guard', 'Patrol the premises and monitor CCTV at the main gate on rotating shifts', 'PHYSICAL_SECURITY', 1),
    'Y10': ('QA Tester', 'Write and execute manual test cases for the mobile banking application', 'QA_TESTING', 1),
}
OWNER = {  # fictional Owner labels: fit and nationality-wording answers
    'Y01': ('show_prominently', 'none'), 'Y02': ('hide', 'none'), 'Y03': ('show_lower', 'targets'),
    'Y04': ('hide', 'none'), 'Y05': ('show_lower', 'none'), 'Y06': ('hide', 'none'), 'Y07': ('show_lower', 'none'),
    'Y08': ('show_prominently', 'none'), 'Y09': ('hide', 'none'), 'Y10': ('show_lower', 'not_sure'),
}
SEAL_TIME = datetime.fromisoformat('2026-09-30T07:00:00+00:00').timestamp()
LABEL_TIME = '2026-09-30T08:00:00Z'


def _text(item_id):
    title, duty, _, years = DUTY[item_id]
    body = (f'About the role: {title} in a fictional company. Key duties:\n - {duty}.\n - Work with colleagues '
            f'across the team and keep records current.\nRequirements:\n - Minimum {years} years of relevant '
            f'experience.\n - Bachelor degree or equivalent.')
    if 'UAE National' in title:
        body += '\nThis role is open to UAE nationals only.'
    return body + '\n<script>alert("x")</script> & </script>'


class FakeGit:
    """In-memory commits of the record files, standing in for Git history."""

    def __init__(self):
        self.order, self.times, self.history, self.content = [], {}, {}, {}

    def commit(self, *paths, when=SEAL_TIME):
        sha = f'{len(self.order) + 1:040x}'
        self.order.append(sha)
        self.times[sha] = when
        for path in paths:
            self.history.setdefault(str(path), []).insert(0, sha)
            self.content[str(path)] = Path(path).read_bytes().replace(b'\r\n', b'\n')
        return sha

    def path_commits(self, path):
        return list(self.history.get(str(path), []))

    def committed(self, path):
        path = Path(path)
        return path.exists() and self.content.get(str(path)) == path.read_bytes().replace(b'\r\n', b'\n')

    def commit_time(self, sha):
        return self.times[sha]

    def is_ancestor(self, older, newer):
        return self.order.index(older) <= self.order.index(newer)

    def head(self):
        return self.order[-1]


class Tree(type(Path())):
    """tmp_path that also carries the fake Git."""


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Fictional private inputs, fictional records folder, fake Git, and a
    freeze manifest matching the current code."""
    snaps = tmp_path / 'snaps'
    snaps.mkdir()
    rows = [{'item_id': 'D01', 'split': 'development', 'title': 'DEV ONLY TITLE', 'employer': 'Dev Co',
             'desc_sha256': hashlib.sha256(b'dev text').hexdigest(), 'desc_chars': 8}]
    (snaps / 'D01.txt').write_text('dev text', encoding='utf-8')
    for item_id in DUTY:
        text = _text(item_id)
        (snaps / f'{item_id}.txt').write_text(text, encoding='utf-8')
        rows.append({'item_id': item_id, 'split': 'holdout', 'title': DUTY[item_id][0], 'employer': 'Fictional Employer',
                     'official_url': f'https://example.invalid/{item_id}', 'platform': 'fixture',
                     'location_stated': 'Abu Dhabi, United Arab Emirates',
                     'desc_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'desc_chars': len(text)})
    (snaps / 'Y11.txt').write_text('n/a', encoding='utf-8')
    rows.append({'item_id': 'Y11', 'split': 'holdout', 'title': 'Unreadable posting', 'employer': 'Other Employer',
                 'location_stated': 'Dubai', 'desc_sha256': hashlib.sha256(b'n/a').hexdigest(), 'desc_chars': 3})
    items = tmp_path / 'items.json'
    items.write_text(json.dumps({'items': rows}), encoding='utf-8')
    (tmp_path / 'records').mkdir()
    git = FakeGit()
    monkeypatch.setattr(cbr, 'RECORDS_DIR', tmp_path / 'records')
    monkeypatch.setattr(cbr, 'EXPECTED_ITEMS_SHA256', common.file_sha256(items))
    monkeypatch.setattr(cbr, 'HOLDOUT_IDS', tuple(sorted([*DUTY, 'Y11'])))
    for name in ('path_commits', 'committed', 'commit_time', 'is_ancestor', 'head'):
        monkeypatch.setattr(cbr, name, getattr(git, name))
    manifest = {'constants': cbr.constants(),
                'files': [{'path': p, 'sha256': common.text_sha256_lf(ROOT / p)} for p in cbr.frozen_paths()]}
    (tmp_path / 'freeze.json').write_text(json.dumps(manifest), encoding='utf-8')
    root = Tree(tmp_path)
    root.git = git
    return root


def ns(**kwargs):
    return argparse.Namespace(**kwargs)


def _readings(requests_path, override=None):
    requests = json.loads(Path(requests_path).read_text(encoding='utf-8'))['items']
    readings = {}
    for item_id in requests:
        title, duty, function, years = DUTY[item_id]
        wording = [{'kind': 'DESIGNATED_NATIONALS', 'text': title}] if 'UAE National' in title else []
        readings[item_id] = {'primary_function': function, 'function_confidence': 0.9, 'function_evidence': [duty],
                             'required_years_min': years, 'years_evidence': f'Minimum {years} years of relevant experience',
                             'eligibility_wording': wording}
    readings.update(override or {})
    return {'artifact': 'discovery_46_2c_blind_readings', 'version': 'v3', 'reader': 'fictional test reader',
            'items': readings}


def _labels_export(t, answers=OWNER, change=None, at=LABEL_TIME, name='labels.json'):
    rows, snapshots = cbr.holdout(t / 'items.json', t / 'snaps')
    labels = {}
    for item_id, (fit, nationality) in answers.items():
        first = {'fit': fit, 'nationality': nationality, 'text_problem': False, 'reason': 'private note', 'at': at}
        labels[item_id] = {'first_saved': first, 'final': first, 'changes': []}
    if change:
        item_id, fit = change
        later = {**labels[item_id]['first_saved'], 'fit': fit, 'at': '2026-09-30T09:00:00Z'}
        labels[item_id] = {**labels[item_id], 'final': later, 'changes': [later]}
    out = {'artifact': 'discovery_46_2c_blind_labels', 'version': 'v3',
           'items_digest': cbr.items_digest(cbr.page_postings(rows, snapshots)),
           'exported_at': '2026-09-30T10:00:00Z', 'labels': labels, 'unreadable_not_labelled': ['Y11']}
    path = t / name
    path.write_bytes((json.dumps(out, indent=1) + '\n').encode('utf-8'))
    return path


def _base(t):
    return dict(items=t / 'items.json', snapshots=t / 'snaps', freeze=t / 'freeze.json')


def _seal(t, readings_override=None, suffix=''):
    base = _base(t)
    if not (t / 'requests.json').exists():
        cbr.cmd_requests(ns(**base, out=t / 'requests.json'))
        cbr.cmd_labeling_page(ns(items=base['items'], snapshots=base['snapshots'], out=t / 'page.html'))
    (t / f'readings{suffix}.json').write_text(json.dumps(_readings(t / 'requests.json', readings_override)),
                                              encoding='utf-8')
    cbr.cmd_seal(ns(**base, requests=t / 'requests.json', readings=t / f'readings{suffix}.json', page=t / 'page.html',
                    reader='fictional test reader', out_private=t / f'predictions{suffix}.json'))
    return base


def _lock(t, labels_path, owner_hex=None):
    base = _base(t)
    cbr.cmd_lock(ns(items=base['items'], snapshots=base['snapshots'], labels=labels_path,
                    owner_sha256=owner_hex or common.file_sha256(labels_path)))


def _compare(t, suffix='', out='result_private.json'):
    base = _base(t)
    cbr.cmd_compare(ns(**base, labels=t / 'labels.json', requests=t / 'requests.json',
                       readings=t / f'readings{suffix}.json', predictions=t / f'predictions{suffix}.json',
                       page=t / 'page.html', out_private=t / out))
    return json.loads((t / 'records' / cbr.RESULT_NAME).read_text(encoding='utf-8'))


def _full_round(t, change=None):
    _seal(t)
    seal_commit = t.git.commit(t / 'records' / cbr.SEAL_NAME)
    labels = _labels_export(t, change=change)
    _lock(t, labels)
    lock_commit = t.git.commit(t / 'records' / cbr.LOCK_NAME, when=SEAL_TIME + 7200)
    return seal_commit, lock_commit


def test_full_fictional_round(tree):
    t = tree
    _seal(t)
    seal = json.loads((t / 'records' / cbr.SEAL_NAME).read_text(encoding='utf-8'))
    assert seal['counts'] == {'holdout_items': 11, 'snapshots_hash_verified': 11, 'readable': 10, 'unreadable': ['Y11'],
                              'readings_present': 10, 'readings_rejected_whole': 0}
    assert 'not provable by code' in seal['declaration']
    public_text = (t / 'records' / cbr.SEAL_NAME).read_text(encoding='utf-8')
    assert 'Triage SIEM' not in public_text and 'SOC Analyst' not in public_text   # hashes and counts only
    requests = json.loads((t / 'requests.json').read_text(encoding='utf-8'))
    assert set(requests['items']) == set(DUTY) and 'D01' not in json.dumps(requests)
    assert 'Fictional Employer' not in json.dumps(requests['items'])   # assessor sees title, location, description only

    seal_commit = t.git.commit(t / 'records' / cbr.SEAL_NAME)
    _lock(t, _labels_export(t, change=('Y10', 'hide')))
    lock = json.loads((t / 'records' / cbr.LOCK_NAME).read_text(encoding='utf-8'))
    assert lock['seal_commit'] == seal_commit and 'not provable by code' in lock['declaration']
    t.git.commit(t / 'records' / cbr.LOCK_NAME, when=SEAL_TIME + 7200)
    result = _compare(t)
    first = result['results']['first_saved']
    assert all(result['integrity'].values())
    assert first['N'] == 10 and (first['shown'], first['hidden']) == (6, 4)
    assert first['excluded'] == [{'item_id': 'Y11', 'reasons': ['E1 SOURCE_UNREADABLE']}]
    assert first['candidate']['M1_tier_agreement'] == {'agree': 8, 'of': 10}
    assert first['current']['M1_tier_agreement'] == {'agree': 5, 'of': 10}
    assert first['candidate']['M2_relevant_hidden'] == {'count': 0, 'of': 6}
    assert first['current']['M5_shown_above_hidden'] == {'correct': 19, 'ties': 2, 'pairs': 24}
    assert first['candidate']['M7_prominent_above_lower'] == {'correct': 6, 'ties': 0, 'pairs': 8}
    assert first['eligibility']['missed'] == 0 and first['eligibility']['answered_targets'] == 1
    assert result['verdict'] == 'PASS' and result['label_basis_of_record'] == 'first_saved'
    assert '10 readable' in result['limits'] and '2 employer(s)' in result['limits']
    by_id = {r['item_id']: r for r in result['rows']}
    assert by_id['Y07']['candidate_tier'] == ru.LOWER and by_id['Y03']['candidate_designated_warning'] is True
    assert by_id['Y10']['label_changed_after_first_save'] is True and by_id['Y10']['owner_first_saved_fit'] == 'show_lower'
    assert result['results']['final']['shown'] == 5   # the later change is reported separately, not scored of record
    assert 'private note' not in json.dumps(result)
    assert 'private note' in (t / 'result_private.json').read_text(encoding='utf-8')


def test_a_failed_round_cannot_be_resealed_relocked_or_rerun(tree):
    t = tree
    wrong = {'Y01': {'primary_function': 'PHYSICAL_SECURITY', 'function_confidence': 0.9,
                     'function_evidence': [DUTY['Y01'][1]], 'required_years_min': None, 'years_evidence': None,
                     'eligibility_wording': []}}
    _seal(t, readings_override=wrong)
    t.git.commit(t / 'records' / cbr.SEAL_NAME)
    _lock(t, _labels_export(t))
    t.git.commit(t / 'records' / cbr.LOCK_NAME, when=SEAL_TIME + 7200)
    assert _compare(t)['verdict'] == 'FAIL'
    t.git.commit(t / 'records' / cbr.RESULT_NAME, when=SEAL_TIME + 9000)
    # the labels are now known; every route back to a new blind run is refused
    with pytest.raises(SystemExit, match='written once'):
        _lock(t, _labels_export(t, name='labels2.json'))
    with pytest.raises(SystemExit, match='written once'):
        _seal(t, suffix='2')
    (t / 'records' / cbr.RESULT_NAME).unlink()
    with pytest.raises(SystemExit, match='written once'):
        _compare(t, out='result_private2.json')
    (t / 'records' / cbr.SEAL_NAME).unlink()
    (t / 'records' / cbr.LOCK_NAME).unlink()
    with pytest.raises(SystemExit, match='written once'):
        _seal(t, suffix='2')


def test_lock_refuses_a_seal_committed_more_than_once(tree):
    t = tree
    _seal(t)
    t.git.commit(t / 'records' / cbr.SEAL_NAME)
    t.git.commit(t / 'records' / cbr.SEAL_NAME, when=SEAL_TIME + 60)
    with pytest.raises(SystemExit, match='committed exactly once'):
        _lock(t, _labels_export(t))


def test_lock_refuses_labels_saved_before_the_seal_commit(tree):
    t = tree
    _seal(t)
    t.git.commit(t / 'records' / cbr.SEAL_NAME)
    with pytest.raises(SystemExit, match='saved before the seal was committed'):
        _lock(t, _labels_export(t, at='2026-09-30T06:59:00Z'))


def test_lock_refuses_an_uncommitted_seal_and_a_hash_the_owner_did_not_report(tree):
    t = tree
    _seal(t)
    with pytest.raises(SystemExit, match='committed exactly once'):
        _lock(t, _labels_export(t))
    t.git.commit(t / 'records' / cbr.SEAL_NAME)
    with pytest.raises(SystemExit, match='does not match the SHA-256 the Owner reported'):
        _lock(t, _labels_export(t), owner_hex='0' * 64)
    assert not (t / 'records' / cbr.LOCK_NAME).exists()


def test_compare_requires_seal_before_lock_in_history(tree, monkeypatch):
    t = tree
    _full_round(t)
    monkeypatch.setattr(cbr, 'is_ancestor', lambda older, newer: False)
    with pytest.raises(SystemExit, match='seal commit must precede the lock commit'):
        _compare(t)


def test_committed_records_are_hashed_independently_of_line_endings(tree):
    t = tree
    _full_round(t)
    for name in (cbr.SEAL_NAME, cbr.LOCK_NAME):
        path = t / 'records' / name
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))   # a CRLF checkout of the same blob
    assert _compare(t)['integrity']['lock_names_this_seal'] is True


@pytest.mark.parametrize('mutate,needle', [
    ('readings', 'hash mismatch: readings'),
    ('predictions', 'hash mismatch: predictions'),
    ('page', 'hash mismatch: labeling_page'),
    ('labels', 'hash mismatch: labels'),
])
def test_compare_refuses_anything_changed_after_seal_or_lock(tree, mutate, needle):
    t = tree
    _full_round(t)
    target = {'readings': t / 'readings.json', 'predictions': t / 'predictions.json', 'page': t / 'page.html',
              'labels': t / 'labels.json'}[mutate]
    target.write_bytes(target.read_bytes() + b' ')
    with pytest.raises(SystemExit, match=needle):
        _compare(t)
    assert not (t / 'records' / cbr.RESULT_NAME).exists()


def test_unreproducible_predictions_make_every_verdict_inconclusive(tree):
    t = tree
    _full_round(t)
    predictions = json.loads((t / 'predictions.json').read_text(encoding='utf-8'))
    sealed_hash = common.file_sha256(t / 'predictions.json')
    predictions['items']['Y01']['candidate']['tier'] = 'LOWER'
    (t / 'predictions.json').write_bytes(cbr.canonical_bytes(predictions))
    seal_path = t / 'records' / cbr.SEAL_NAME   # simulate a seal that recorded non-reproducible output
    seal = json.loads(seal_path.read_text(encoding='utf-8'))
    assert seal['predictions_sha256'] == sealed_hash
    seal['predictions_sha256'] = common.file_sha256(t / 'predictions.json')
    seal_path.write_bytes(cbr.canonical_bytes(seal))
    t.git.content[str(seal_path)] = seal_path.read_bytes()
    lock_path = t / 'records' / cbr.LOCK_NAME
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    lock['seal_record_sha256'] = common.text_sha256_lf(seal_path)
    lock_path.write_bytes(cbr.canonical_bytes(lock))
    t.git.content[str(lock_path)] = lock_path.read_bytes()
    result = _compare(t)
    assert result['integrity']['predictions_reproduce'] is False
    assert result['verdict'] == 'INCONCLUSIVE'
    assert {r['verdict'] for r in result['results'].values()} == {'INCONCLUSIVE'}


def test_labels_must_come_from_the_frozen_posting_set(tree):
    t = tree
    _seal(t)
    t.git.commit(t / 'records' / cbr.SEAL_NAME)
    path = _labels_export(t)
    data = json.loads(path.read_text(encoding='utf-8'))
    data['items_digest'] = '0' * 64
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(SystemExit, match='items digest differs'):
        _lock(t, path)


@pytest.mark.parametrize('mutate', [
    lambda labels: labels['Y01']['first_saved'].update(fit='maybe'),
    lambda labels: labels.update(D01=labels['Y01']),
    lambda labels: labels.update(Y11=labels['Y01']),
    lambda labels: labels['Y01']['first_saved'].update(fit=None),
    lambda labels: labels.pop('Y05'),                                    # a readable item without a label
    lambda labels: labels['Y02'].update(final={**labels['Y02']['first_saved'], 'fit': 'show_lower'}),
    lambda labels: labels['Y02']['first_saved'].update(at='yesterday'),
])
def test_malformed_incomplete_or_out_of_scope_labels_are_refused(tree, mutate):
    t = tree
    _seal(t)
    t.git.commit(t / 'records' / cbr.SEAL_NAME)
    path = _labels_export(t)
    data = json.loads(path.read_text(encoding='utf-8'))
    mutate(data['labels'])
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(SystemExit, match='refusing to run'):
        _lock(t, path)


def test_only_the_pre_registered_items_file_is_accepted(tree, monkeypatch):
    t = tree
    monkeypatch.setattr(cbr, 'EXPECTED_ITEMS_SHA256', '0' * 64)
    with pytest.raises(SystemExit, match='not the pre-registered frozen items file'):
        cbr.cmd_labeling_page(ns(items=t / 'items.json', snapshots=t / 'snaps', out=t / 'page.html'))


def test_readings_naming_a_development_item_are_refused(tree):
    t = tree
    base = _base(t)
    cbr.cmd_requests(ns(**base, out=t / 'requests.json'))
    cbr.cmd_labeling_page(ns(items=base['items'], snapshots=base['snapshots'], out=t / 'page.html'))
    readings = _readings(t / 'requests.json')
    readings['items']['D01'] = readings['items']['Y01']
    (t / 'readings.json').write_text(json.dumps(readings), encoding='utf-8')
    with pytest.raises(SystemExit, match='outside the selected split'):
        cbr.cmd_seal(ns(**base, requests=t / 'requests.json', readings=t / 'readings.json', page=t / 'page.html',
                        reader='x', out_private=t / 'predictions.json'))


def test_seal_refuses_requests_that_are_not_the_frozen_bounded_requests(tree):
    t = tree
    base = _base(t)
    cbr.cmd_requests(ns(**base, out=t / 'requests.json'))
    cbr.cmd_labeling_page(ns(items=base['items'], snapshots=base['snapshots'], out=t / 'page.html'))
    requests = json.loads((t / 'requests.json').read_text(encoding='utf-8'))
    requests['items']['Y01']['instructions'] += ' The Owner likes SOC roles.'
    (t / 'requests.json').write_text(json.dumps(requests), encoding='utf-8')
    (t / 'readings.json').write_text(json.dumps(_readings(t / 'requests.json')), encoding='utf-8')
    with pytest.raises(SystemExit, match='differ from the bounded requests'):
        cbr.cmd_seal(ns(**base, requests=t / 'requests.json', readings=t / 'readings.json', page=t / 'page.html',
                        reader='x', out_private=t / 'predictions.json'))


def test_freeze_verification_fails_closed(tree):
    t = tree
    assert re.fullmatch(r'[0-9a-f]{64}', cbr.verify_freeze(t / 'freeze.json'))
    manifest = json.loads((t / 'freeze.json').read_text(encoding='utf-8'))
    for mutate, needle in ((lambda m: m['files'][0].update(sha256='0' * 64), 'changed since the freeze'),
                           (lambda m: m['files'].pop(), 'set of frozen files differs'),
                           (lambda m: m['constants']['criteria'].update(C3_min_margin_over_current=0), 'constants'),
                           (lambda m: m['constants'].update(holdout_ids=['Y01']), 'constants')):
        broken = json.loads(json.dumps(manifest))
        mutate(broken)
        path = t / 'broken.json'
        path.write_text(json.dumps(broken), encoding='utf-8')
        with pytest.raises(SystemExit, match=needle):
            cbr.verify_freeze(path)
    crlf = t / 'crlf.json'
    crlf.write_bytes((t / 'freeze.json').read_bytes().replace(b'\n', b'\r\n'))
    assert cbr.verify_freeze(crlf) == cbr.verify_freeze(t / 'freeze.json')
    assert 'backend/role_understanding.py' in cbr.frozen_paths() and cbr.PREFERENCES in cbr.frozen_paths()


def test_freeze_refuses_when_git_cannot_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(common, 'git', lambda *args: None)
    with pytest.raises(SystemExit, match='Git could not confirm'):
        cbr.cmd_freeze(ns(out=tmp_path / 'freeze.json'))
    assert not (tmp_path / 'freeze.json').exists()


def test_labeling_page_carries_posting_text_only(tree):
    t = tree
    assert list(inspect.signature(cbr.build_labeling_page).parameters) == ['postings']
    cbr.cmd_labeling_page(ns(items=t / 'items.json', snapshots=t / 'snaps', out=t / 'page.html'))
    page = (t / 'page.html').read_text(encoding='utf-8')
    blob = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S).group(1)
    data = json.loads(blob)
    assert {tuple(sorted(p)) for p in data['items']} == {('chars', 'description', 'employer', 'id', 'location', 'title')}
    assert [p['id'] for p in data['items']] != sorted(p['id'] for p in data['items'])   # seeded display order
    assert 'D01' not in blob and 'DEV ONLY' not in blob
    for forbidden in ('PROMINENT', 'SUGGESTED_HIDDEN', 'score', 'primary_function', 'years_evidence', 'bucket'):
        assert forbidden not in blob
    assert '</script>' not in blob and '<script>alert' not in blob          # posting text cannot break out
    assert not re.search(r'(?:src|href)\s*=\s*["\']?(?:https?:)?//', page) and 'fetch(' not in page
    assert "connect-src 'none'" in page
    with pytest.raises(SystemExit, match='already exists'):
        cbr.cmd_labeling_page(ns(items=t / 'items.json', snapshots=t / 'snaps', out=t / 'page.html'))


@pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')
def test_page_sha256_matches_hashlib():
    page = (ROOT / cbr.PAGE_TEMPLATE).read_text(encoding='utf-8')
    code = page[page.index('// SHA-256 (FIPS 180-4)'):page.index('// END SHA-256')]
    samples = ['', 'abc', 'a' * 55, 'b' * 56, 'c' * 64, 'd' * 1000, '{"labels": "é — ✓ عربي"}\n']
    script = code + '\nconst out = [];\nfor (const s of %s) out.push(sha256Hex(new TextEncoder().encode(s)));\n' \
                    'console.log(JSON.stringify(out));\n' % json.dumps(samples)
    done = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=60, encoding='utf-8')
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == [hashlib.sha256(s.encode('utf-8')).hexdigest() for s in samples]


def test_owner_procedure_in_a_real_browser(tree):
    """The Owner's exact steps on fictional postings: answer, save (one item
    changed after its first save), export; the shown hash must lock."""
    from playwright.sync_api import sync_playwright
    t = tree
    _seal(t)
    t.git.commit(t / 'records' / cbr.SEAL_NAME, when=datetime.now().timestamp() - 60)
    requests_seen = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.on('request', lambda r: requests_seen.append(r.url))
        page.goto((t / 'page.html').as_uri())
        assert page.is_disabled('#export')
        assert 'No label is needed' in page.text_content('#card-Y11')
        for item_id, (fit, nationality) in OWNER.items():
            page.check(f'input[name="fit-{item_id}"][value="{fit}"]')
            page.check(f'input[name="nat-{item_id}"][value="{nationality}"]')
            page.click(f'#card-{item_id} button')
        page.check('input[name="fit-Y10"][value="hide"]')
        page.click('#card-Y10 button')
        assert 'changed 1 time' in page.text_content('#card-Y10 .status')
        with page.expect_download() as download:
            page.click('#export')
        exported = t / 'owner_export.json'
        download.value.save_as(str(exported))
        shown = page.text_content('#hash').strip()
        browser.close()
    assert [u for u in requests_seen if not u.startswith(('file:', 'blob:', 'data:'))] == []
    assert shown == common.file_sha256(exported)
    _lock(t, exported, owner_hex=shown)
    labels = json.loads(exported.read_text(encoding='utf-8'))['labels']
    assert labels['Y10']['first_saved']['fit'] == 'show_lower' and labels['Y10']['final']['fit'] == 'hide'
    assert set(labels) == set(OWNER)


def test_cli_refuses_existing_outputs():
    done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'c_blind_round.py'), 'freeze', '--out',
                           str(ROOT / cbr.PLAN)], capture_output=True, text=True, timeout=120)
    assert done.returncode != 0 and 'refusing to run' in done.stderr

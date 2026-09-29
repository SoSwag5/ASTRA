"""#46.2-C blind round (scripts/c_blind_round.py). Fictional, isolated, no network.

A whole round -- requests, readings, labeling page, seal, lock, compare -- on
fictional postings, plus the fail-closed checks around it. These tests pin
custody behaviour; they are not an accuracy claim.
"""
import argparse
import hashlib
import inspect
import json
import re
import shutil
import subprocess
import sys
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


def _text(item_id):
    title, duty, _, years = DUTY[item_id]
    body = (f'About the role: {title} in a fictional company. Key duties:\n - {duty}.\n - Work with colleagues '
            f'across the team and keep records current.\nRequirements:\n - Minimum {years} years of relevant '
            f'experience.\n - Bachelor degree or equivalent.')
    if 'UAE National' in title:
        body += '\nThis role is open to UAE nationals only.'
    return body + '\n<script>alert("x")</script> & </script>'


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Fictional private inputs, a freeze manifest matching the current code,
    and a stand-in for 'this record is committed'."""
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
    rows.append({'item_id': 'Y11', 'split': 'holdout', 'title': 'Unreadable posting', 'employer': 'Fictional Employer',
                 'location_stated': 'Dubai', 'desc_sha256': hashlib.sha256(b'n/a').hexdigest(), 'desc_chars': 3})
    items = tmp_path / 'items.json'
    items.write_text(json.dumps({'items': rows}), encoding='utf-8')
    manifest = {'constants': cbr.constants(),
                'files': [{'path': p, 'sha256': common.text_sha256_lf(ROOT / p)} for p in cbr.frozen_paths()]}
    freeze = tmp_path / 'freeze.json'
    freeze.write_text(json.dumps(manifest), encoding='utf-8')
    monkeypatch.setattr(cbr, 'committed', lambda path: True)
    return tmp_path


def ns(**kwargs):
    return argparse.Namespace(**kwargs)


def _readings(requests_path):
    requests = json.loads(Path(requests_path).read_text(encoding='utf-8'))['items']
    readings = {}
    for item_id in requests:
        title, duty, function, years = DUTY[item_id]
        wording = [{'kind': 'DESIGNATED_NATIONALS', 'text': title}] if 'UAE National' in title else []
        readings[item_id] = {'primary_function': function, 'function_confidence': 0.9, 'function_evidence': [duty],
                             'required_years_min': years, 'years_evidence': f'Minimum {years} years of relevant experience',
                             'eligibility_wording': wording}
    return {'artifact': 'discovery_46_2c_blind_readings', 'version': 'v3', 'reader': 'fictional test reader',
            'items': readings}


def _labels_export(t, answers=OWNER, change=None):
    rows, snapshots = cbr.holdout(t / 'items.json', t / 'snaps')
    postings = cbr.page_postings(rows, snapshots)
    labels = {}
    for item_id, (fit, nationality) in answers.items():
        first = {'fit': fit, 'nationality': nationality, 'text_problem': False, 'reason': 'private note', 'at': '2026-09-30T08:00:00Z'}
        labels[item_id] = {'first_saved': first, 'final': first, 'changes': []}
    if change:
        item_id, fit = change
        later = {**labels[item_id]['first_saved'], 'fit': fit, 'at': '2026-09-30T09:00:00Z'}
        labels[item_id] = {**labels[item_id], 'final': later, 'changes': [later]}
    out = {'artifact': 'discovery_46_2c_blind_labels', 'version': 'v3', 'items_digest': cbr.items_digest(postings),
           'exported_at': '2026-09-30T10:00:00Z', 'labels': labels, 'unreadable_not_labelled': ['Y11']}
    path = t / 'labels.json'
    path.write_bytes((json.dumps(out, indent=1) + '\n').encode('utf-8'))
    return path


def _through_seal(t):
    base = dict(items=t / 'items.json', snapshots=t / 'snaps', freeze=t / 'freeze.json')
    cbr.cmd_requests(ns(**base, out=t / 'requests.json'))
    (t / 'readings.json').write_text(json.dumps(_readings(t / 'requests.json')), encoding='utf-8')
    cbr.cmd_labeling_page(ns(items=base['items'], snapshots=base['snapshots'], out=t / 'page.html'))
    cbr.cmd_seal(ns(**base, requests=t / 'requests.json', readings=t / 'readings.json', page=t / 'page.html',
                    reader='fictional test reader', out_private=t / 'predictions.json', out_public=t / 'seal.json'))
    return base


def _compare(t, base, suffix=''):
    cbr.cmd_compare(ns(**base, seal=t / 'seal.json', lock=t / 'lock.json', labels=t / 'labels.json',
                       requests=t / 'requests.json', readings=t / 'readings.json', predictions=t / 'predictions.json',
                       page=t / 'page.html', out_private=t / f'result_private{suffix}.json',
                       out_public=t / f'result{suffix}.json'))
    return json.loads((t / f'result{suffix}.json').read_text(encoding='utf-8'))


def _lock(t, base, labels_path, owner_hex=None):
    cbr.cmd_lock(ns(items=base['items'], snapshots=base['snapshots'], labels=labels_path,
                    owner_sha256=owner_hex or common.file_sha256(labels_path), seal=t / 'seal.json', out=t / 'lock.json'))


def test_full_fictional_round_and_run_once(tree):
    t = tree
    base = _through_seal(t)
    seal = json.loads((t / 'seal.json').read_text(encoding='utf-8'))
    assert seal['counts'] == {'holdout_items': 11, 'snapshots_hash_verified': 11, 'readable': 10, 'unreadable': ['Y11'],
                              'readings_present': 10, 'readings_rejected_whole': 0}
    public_text = (t / 'seal.json').read_text(encoding='utf-8')
    assert 'Triage SIEM' not in public_text and 'SOC Analyst' not in public_text   # hashes and counts only
    requests = json.loads((t / 'requests.json').read_text(encoding='utf-8'))
    assert set(requests['items']) == set(DUTY) and 'D01' not in json.dumps(requests)
    assert 'Fictional Employer' not in json.dumps(requests['items'])   # assessor sees title, location, description only

    labels = _labels_export(t, change=('Y10', 'hide'))
    _lock(t, base, labels)
    result = _compare(t, base)
    first = result['results']['first_saved']
    assert result['integrity']['predictions_reproduce'] is True and all(result['integrity'].values())
    assert first['N'] == 10 and (first['shown'], first['hidden']) == (6, 4)
    assert first['excluded'] == [{'item_id': 'Y11', 'reasons': ['E1 SOURCE_UNREADABLE', 'no Owner label']}]
    assert first['candidate']['M2_relevant_hidden'] == {'count': 0, 'of': 6}
    assert first['eligibility']['missed'] == 0 and first['eligibility']['answered_targets'] == 1
    assert result['verdict'] in ('PASS', 'FAIL') and result['label_basis_of_record'] == 'first_saved'
    by_id = {r['item_id']: r for r in result['rows']}
    assert by_id['Y07']['candidate_tier'] == ru.LOWER and by_id['Y03']['candidate_designated_warning'] is True
    assert by_id['Y10']['label_changed_after_first_save'] is True and by_id['Y10']['owner_first_saved_fit'] == 'show_lower'
    assert result['results']['final']['shown'] == 5   # the later change is reported separately, not scored of record
    assert 'private note' not in json.dumps(result)
    assert 'private note' in (t / 'result_private.json').read_text(encoding='utf-8')

    with pytest.raises(SystemExit, match='runs once'):
        _compare(t, base)


def test_lock_refuses_a_hash_the_owner_did_not_report(tree):
    t = tree
    base = _through_seal(t)
    labels = _labels_export(t)
    with pytest.raises(SystemExit, match='does not match the SHA-256 the Owner reported'):
        _lock(t, base, labels, owner_hex='0' * 64)
    assert not (t / 'lock.json').exists()


def test_lock_requires_a_committed_seal(tree, monkeypatch):
    t = tree
    base = _through_seal(t)
    monkeypatch.setattr(cbr, 'committed', lambda path: False)
    with pytest.raises(SystemExit, match='must be committed'):
        _lock(t, base, _labels_export(t))


@pytest.mark.parametrize('mutate,needle', [
    ('readings', 'hash mismatch: readings'),
    ('predictions', 'hash mismatch: predictions'),
    ('page', 'hash mismatch: labeling_page'),
    ('labels', 'hash mismatch: labels'),
])
def test_compare_refuses_anything_changed_after_seal_or_lock(tree, mutate, needle):
    t = tree
    base = _through_seal(t)
    _lock(t, base, _labels_export(t))
    target = {'readings': t / 'readings.json', 'predictions': t / 'predictions.json', 'page': t / 'page.html',
              'labels': t / 'labels.json'}[mutate]
    target.write_bytes(target.read_bytes() + b' ')
    with pytest.raises(SystemExit, match=needle):
        _compare(t, base)
    assert not (t / 'result.json').exists()


def test_labels_must_come_from_the_frozen_page(tree):
    t = tree
    base = _through_seal(t)
    path = _labels_export(t)
    data = json.loads(path.read_text(encoding='utf-8'))
    data['items_digest'] = '0' * 64
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(SystemExit, match='not made on the page built from the frozen postings'):
        _lock(t, base, path)


@pytest.mark.parametrize('bad', [
    {'Y01': {'first_saved': {'fit': 'maybe', 'nationality': 'none', 'text_problem': False, 'reason': '', 'at': 'x'}}},
    {'D01': {'first_saved': {'fit': 'hide', 'nationality': 'none', 'text_problem': False, 'reason': '', 'at': 'x'}}},
    {'Y11': {'first_saved': {'fit': 'hide', 'nationality': 'none', 'text_problem': False, 'reason': '', 'at': 'x'}}},
    {'Y01': {'first_saved': {'fit': None, 'nationality': 'none', 'text_problem': False, 'reason': '', 'at': 'x'}}},
])
def test_malformed_or_out_of_scope_labels_are_refused(tree, bad):
    t = tree
    base = _through_seal(t)
    path = _labels_export(t)
    data = json.loads(path.read_text(encoding='utf-8'))
    for item_id, entry in bad.items():
        data['labels'][item_id] = {'first_saved': entry['first_saved'], 'final': entry['first_saved'], 'changes': []}
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(SystemExit, match='refusing to run'):
        _lock(t, base, path)


def test_readings_naming_a_development_item_are_refused(tree):
    t = tree
    base = dict(items=t / 'items.json', snapshots=t / 'snaps', freeze=t / 'freeze.json')
    cbr.cmd_requests(ns(**base, out=t / 'requests.json'))
    readings = _readings(t / 'requests.json')
    readings['items']['D01'] = readings['items']['Y01']
    (t / 'readings.json').write_text(json.dumps(readings), encoding='utf-8')
    cbr.cmd_labeling_page(ns(items=base['items'], snapshots=base['snapshots'], out=t / 'page.html'))
    with pytest.raises(SystemExit, match='outside the selected split'):
        cbr.cmd_seal(ns(**base, requests=t / 'requests.json', readings=t / 'readings.json', page=t / 'page.html',
                        reader='x', out_private=t / 'predictions.json', out_public=t / 'seal.json'))


def test_seal_refuses_requests_that_are_not_the_frozen_bounded_requests(tree):
    t = tree
    base = dict(items=t / 'items.json', snapshots=t / 'snaps', freeze=t / 'freeze.json')
    cbr.cmd_requests(ns(**base, out=t / 'requests.json'))
    requests = json.loads((t / 'requests.json').read_text(encoding='utf-8'))
    requests['items']['Y01']['instructions'] += ' The Owner likes SOC roles.'
    (t / 'requests.json').write_text(json.dumps(requests), encoding='utf-8')
    (t / 'readings.json').write_text(json.dumps(_readings(t / 'requests.json')), encoding='utf-8')
    cbr.cmd_labeling_page(ns(items=base['items'], snapshots=base['snapshots'], out=t / 'page.html'))
    with pytest.raises(SystemExit, match='differ from the bounded requests'):
        cbr.cmd_seal(ns(**base, requests=t / 'requests.json', readings=t / 'readings.json', page=t / 'page.html',
                        reader='x', out_private=t / 'predictions.json', out_public=t / 'seal.json'))


def test_freeze_verification_fails_closed(tree):
    t = tree
    assert re.fullmatch(r'[0-9a-f]{64}', cbr.verify_freeze(t / 'freeze.json'))
    manifest = json.loads((t / 'freeze.json').read_text(encoding='utf-8'))
    for mutate, needle in ((lambda m: m['files'][0].update(sha256='0' * 64), 'changed since the freeze'),
                           (lambda m: m['files'].pop(), 'set of frozen files differs'),
                           (lambda m: m['constants']['criteria'].update(C3_min_margin_over_current=0), 'constants')):
        broken = json.loads(json.dumps(manifest))
        mutate(broken)
        path = t / 'broken.json'
        path.write_text(json.dumps(broken), encoding='utf-8')
        with pytest.raises(SystemExit, match=needle):
            cbr.verify_freeze(path)
    assert 'backend/role_understanding.py' in cbr.frozen_paths() and cbr.PREFERENCES in cbr.frozen_paths()


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


def test_cli_blocks_network_and_refuses_existing_outputs(tree):
    t = tree
    (t / 'exists.json').write_text('{}', encoding='utf-8')
    done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'c_blind_round.py'), 'labeling-page', '--items',
                           str(t / 'items.json'), '--snapshots', str(t / 'snaps'), '--out', str(t / 'exists.json')],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode != 0 and 'already exists' in done.stderr

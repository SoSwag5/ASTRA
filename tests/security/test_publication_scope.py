"""Publication gate scope: synthetic PR merge refs are out of scope, nothing else is.

Builds throwaway git repositories; no live application storage or real address
is used. The fixture address below is invented for these assertions.
"""
import subprocess
from pathlib import Path

import pytest

from scripts.publication_gate import PATTERNS, audit, publishable_tips, scan

BACKSLASH = chr(92)
# Split so this file carries no literal the gate is required to flag; exempting
# the path instead would blind the gate to a real leak here.
DRIVE = 'C' + ':'

# Assembled at runtime so this file does not itself carry a literal address the
# gate must flag. Exempting the path instead would blind the gate to a real leak
# here, so the pattern is exercised in full without weakening any rule.
FIXTURE_EMAIL = 'fixture.person@' + 'gmail' + '.com'
SAFE_EMAIL = 'author@example.invalid'


def g(repo, *args):
    return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    g(repo, 'init', '-q', '-b', 'master')
    g(repo, 'config', 'user.name', 'Fixture')
    g(repo, 'config', 'user.email', SAFE_EMAIL)
    (repo / 'README.md').write_text('clean\n', encoding='utf-8')
    g(repo, 'add', '.')
    g(repo, 'commit', '-q', '-m', 'base')
    return repo


def synthetic_merge(repo, *, head_email=SAFE_EMAIL, head_body='clean\n', keep_branch=False):
    """Reproduce a pull_request checkout: detached HEAD at refs/pull/1/merge."""
    g(repo, 'checkout', '-q', '-b', 'feature')
    (repo / 'feature.txt').write_text(head_body, encoding='utf-8')
    g(repo, 'add', '.')
    g(repo, '-c', 'user.email=' + head_email, 'commit', '-q', '-m', 'proposed change')
    g(repo, 'checkout', '-q', 'master')
    # GitHub authors this merge itself, from the account's profile address.
    g(repo, '-c', 'user.email=' + FIXTURE_EMAIL, 'merge', '--no-ff', '-q', '-m', 'Merge feature', 'feature')
    merge = g(repo, 'rev-parse', 'HEAD')
    g(repo, 'update-ref', 'refs/pull/1/merge', merge)
    g(repo, 'reset', '-q', '--hard', 'HEAD~1')
    g(repo, 'checkout', '-q', '--detach', merge)
    if not keep_branch:
        # Leaves refs/pull/1/merge as the only route to the proposed commit.
        g(repo, 'branch', '-q', '-D', 'feature')
    return merge


def test_sanitized_repository_passes(repo):
    assert audit(repo)['status'] == 'PASS'


def test_real_repository_still_passes():
    assert audit()['status'] == 'PASS'


def test_address_in_reachable_branch_commit_metadata_fails(repo):
    g(repo, 'checkout', '-q', '-b', 'leak')
    (repo / 'note.txt').write_text('x\n', encoding='utf-8')
    g(repo, 'add', '.')
    g(repo, '-c', 'user.email=' + FIXTURE_EMAIL, 'commit', '-q', '-m', 'leak')
    result = audit(repo)
    assert result['status'] == 'BLOCKED'
    assert {'location': 'history:commit-metadata', 'category': 'personal_email'} in result['findings']


def test_address_in_reachable_tag_content_fails(repo):
    (repo / 'leak.txt').write_text(FIXTURE_EMAIL + '\n', encoding='utf-8')
    g(repo, 'add', '.')
    g(repo, 'commit', '-q', '-m', 'tagged leak')
    g(repo, 'tag', 'v0.0.1')
    g(repo, 'reset', '-q', '--hard', 'HEAD~1')
    result = audit(repo)
    assert result['status'] == 'BLOCKED'
    assert any(f['location'] == 'history:leak.txt' for f in result['findings'])


def test_address_in_worktree_fails(repo):
    (repo / 'draft.md').write_text('contact ' + FIXTURE_EMAIL + '\n', encoding='utf-8')
    result = audit(repo)
    assert result['status'] == 'BLOCKED'
    assert {'location': 'tree:draft.md', 'category': 'personal_email'} in result['findings']


def test_packaged_artifact_content_still_fails(repo):
    (repo / 'release-notes.txt').write_text('signed off by ' + FIXTURE_EMAIL, encoding='utf-8')
    g(repo, 'add', '.')
    g(repo, 'commit', '-q', '-m', 'notes')
    result = audit(repo)
    assert result['status'] == 'BLOCKED'
    assert any(f['category'] == 'personal_email' and 'release-notes.txt' in f['location'] for f in result['findings'])


def test_synthetic_pull_merge_metadata_is_ignored(repo):
    merge = synthetic_merge(repo)
    assert merge not in publishable_tips(repo)
    assert audit(repo)['status'] == 'PASS'


def test_synthetic_merge_does_not_hide_the_proposed_commit_metadata(repo):
    """The merge is skipped; the commit it proposes must still be scanned."""
    synthetic_merge(repo, head_email=FIXTURE_EMAIL)
    result = audit(repo)
    assert result['status'] == 'BLOCKED'
    assert {'location': 'history:commit-metadata', 'category': 'personal_email'} in result['findings']


def test_synthetic_merge_does_not_hide_the_proposed_commit_content(repo):
    synthetic_merge(repo, head_body='reach me at ' + FIXTURE_EMAIL + '\n')
    result = audit(repo)
    assert result['status'] == 'BLOCKED'
    assert any(f['location'] == 'history:feature.txt' for f in result['findings'])


# Payloads are synthetic. A scoping change once silently dropped an escape from
# private_machine_path so it matched forward slashes only; these pin every rule.
DETECTIONS = [
    ('private_machine_path', DRIVE + BACKSLASH + 'Users' + BACKSLASH + 'someone' + BACKSLASH + 'notes.txt'),
    ('private_machine_path', DRIVE + '/Users/someone/notes.txt'),
    ('personal_email', 'contact ' + FIXTURE_EMAIL),
    ('private_key', '-----BEGIN OPENSSH ' + 'PRIVATE KEY-----'),
    ('api_token', 'ghp_' + 'A' * 36),
    ('api_token', 'AKIA' + 'B' * 16),
    ('employment_record_table', '| ID | Company | Role | Status | Result |'),
]


@pytest.mark.parametrize('category,payload', DETECTIONS)
def test_each_detection_rule_still_fires(category, payload):
    findings = []
    scan(payload.encode(), 'tree:fixture.txt', findings)
    assert {'location': 'tree:fixture.txt', 'category': category} in findings


NOTICE_SOURCES = ('THIRD_PARTY_NOTICES.md', 'frontend/public/third-party-notices.txt')
NOTICE_PACKAGED = 'frontend/dist/third-party-notices.txt'


@pytest.mark.parametrize('path', NOTICE_SOURCES + (NOTICE_PACKAGED,))
def test_upstream_attribution_is_waived_in_notice_files(path):
    """Vite publishes public/ into dist/, so the artifact carries it twice."""
    findings = []
    scan(('maintainer ' + FIXTURE_EMAIL).encode(), 'artifact:' + path, findings)
    assert findings == []


@pytest.mark.parametrize('path', NOTICE_SOURCES + (NOTICE_PACKAGED,))
def test_notice_waiver_covers_only_attribution(path):
    """A key or token in a notice file is still a finding."""
    findings = []
    scan(('-----BEGIN OPENSSH ' + 'PRIVATE KEY-----').encode(), 'artifact:' + path, findings)
    assert [f['category'] for f in findings] == ['private_key']


def test_notice_waiver_does_not_leak_to_neighbouring_paths():
    for path in ('frontend/dist/notes.txt', 'docs/third-party-notices.txt',
                 'frontend/dist/third-party-notices.txt.bak'):
        findings = []
        scan(('maintainer ' + FIXTURE_EMAIL).encode(), 'artifact:' + path, findings)
        assert [f['category'] for f in findings] == ['personal_email'], path


def test_detection_rule_set_is_not_silently_reduced():
    assert set(PATTERNS) == {
        'employment_record_table', 'private_key', 'api_token',
        'private_machine_path', 'personal_email',
    }

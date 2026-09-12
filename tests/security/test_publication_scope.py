"""Publication gate scope: synthetic PR merge refs are out of scope, nothing else is.

Builds throwaway git repositories; no live application storage or real address
is used. The fixture address below is invented for these assertions.
"""
import subprocess
from pathlib import Path

import pytest

from scripts.publication_gate import audit, publishable_tips

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

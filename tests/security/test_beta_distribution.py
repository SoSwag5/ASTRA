"""Release identity and artifact-path regressions; no real user data."""
import json
from pathlib import Path

import pytest
from scripts.release_version import load_version


@pytest.mark.parametrize('value', [
    '../escape', '1.1.0/other', '1.1.0-beta.1\nother', '01.1.0',
    '1.1.0-beta.01', '', '1.1.0;cmd', '1.1.0-unknown.1',
])
def test_release_version_rejects_unsafe_or_unsupported_labels(tmp_path, value):
    path = tmp_path / 'VERSION'
    path.write_text(value, encoding='utf-8')
    with pytest.raises(ValueError):
        load_version(path)


@pytest.mark.parametrize('value', ['1.0.0', '1.1.0-beta.1', '1.1.0-rc.1', '2.0.0-alpha.0'])
def test_release_version_accepts_supported_semantic_versions(tmp_path, value):
    path = tmp_path / 'VERSION'
    path.write_text(value + '\n', encoding='utf-8')
    assert load_version(path) == value


def test_shipped_identity_matches_runtime_and_frontend():
    from backend.build_info import VERSION
    root = Path(__file__).resolve().parents[2]
    expected = load_version(root / 'VERSION')
    assert VERSION == expected
    assert json.loads((root / 'frontend/package.json').read_text())['version'] == expected
    lock = json.loads((root / 'frontend/package-lock.json').read_text())
    assert lock['version'] == lock['packages']['']['version'] == expected


def test_changing_version_makes_the_running_build_stale(tmp_path, monkeypatch):
    from backend import build_info
    (tmp_path / 'backend').mkdir()
    (tmp_path / 'backend/example.py').write_text('pass\n')
    path = tmp_path / 'VERSION'
    path.write_text('1.1.0-beta.1\n')
    monkeypatch.setattr(build_info, 'ROOT', tmp_path)
    original = build_info.source_id()
    monkeypatch.setattr(build_info, 'BUILD', original)
    assert not build_info.info()['stale']
    path.write_text('1.1.0-beta.2\n')
    assert build_info.info()['stale']

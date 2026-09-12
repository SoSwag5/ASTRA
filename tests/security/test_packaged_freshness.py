"""An unpacked release must not be reported stale by mtime comparison.

zipfile.extractall does not restore entry timestamps, so every extracted file
carries its extraction time. frontend/dist extracts before frontend/src, which
made source reliably appear newer than the build it came from and failed the
hosted clean-installation acceptance.
"""
import os
import zipfile

from backend.doctor import frontend_stale


def layout(root, *, manifest):
    (root/'frontend'/'dist').mkdir(parents=True)
    (root/'frontend'/'src').mkdir(parents=True)
    (root/'frontend'/'dist'/'index.html').write_text('built', encoding='utf-8')
    (root/'frontend'/'src'/'main.tsx').write_text('source', encoding='utf-8')
    if manifest:
        (root/'release-manifest.json').write_text('{}', encoding='utf-8')
    return root


def make_source_newer(root):
    built = (root/'frontend'/'dist'/'index.html').stat().st_mtime
    os.utime(root/'frontend'/'src'/'main.tsx', (built + 10, built + 10))


def test_packaged_release_is_never_stale(tmp_path):
    root = layout(tmp_path/'packaged', manifest=True)
    make_source_newer(root)
    assert frontend_stale(root) is False


def test_working_tree_still_reports_a_stale_build(tmp_path):
    """The developer signal must survive: this is why the check exists."""
    root = layout(tmp_path/'worktree', manifest=False)
    make_source_newer(root)
    assert frontend_stale(root) is True


def test_working_tree_with_fresh_build_is_not_stale(tmp_path):
    root = layout(tmp_path/'fresh', manifest=False)
    built = (root/'frontend'/'dist'/'index.html').stat().st_mtime
    os.utime(root/'frontend'/'src'/'main.tsx', (built - 10, built - 10))
    assert frontend_stale(root) is False


def test_missing_build_is_not_reported_as_stale(tmp_path):
    """Absence is reported by the caller as missing, not as staleness."""
    root = layout(tmp_path/'nobuild', manifest=False)
    (root/'frontend'/'dist'/'index.html').unlink()
    assert frontend_stale(root) is False


def test_extraction_order_alone_would_mark_a_release_stale(tmp_path):
    """Reproduces the hosted failure: extractall assigns extraction times."""
    archive = tmp_path/'release.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for name in ('release-manifest.json', 'frontend/dist/index.html'):
            z.writestr(zipfile.ZipInfo(name, date_time=(2026, 9, 12, 0, 0, 0)), 'x')
        for index in range(60):
            z.writestr(zipfile.ZipInfo('frontend/src/%02d.tsx' % index, date_time=(2026, 9, 12, 0, 0, 0)), 'y')

    target = tmp_path/'unpacked'
    with zipfile.ZipFile(archive) as z:
        z.extractall(target)

    built = (target/'frontend'/'dist'/'index.html').stat().st_mtime
    newer = [p for p in (target/'frontend'/'src').rglob('*') if p.is_file() and p.stat().st_mtime > built]
    assert newer, 'expected extraction order to make sources look newer'
    assert frontend_stale(target) is False

"""Characterization tests for backend.adapters.discover('lever'/'ashby', ...)
post-migration (issue #39), mirroring test_greenhouse_characterization.py's
role for issue #38: lock in the EXTERNAL dict shape callers (backend/main.py)
rely on, mocking the actual seam (transport.fetch_json via lever.py/ashby.py)
rather than the retired backend.adapters.fetch.

Fields that were already correct in the legacy adapters.py path (title,
location, hostedUrl/jobUrl, single-request Ashby retrieval) are asserted
unchanged here. Two fields are DELIBERATELY different from the legacy
output, both confirmed bugs from the #39 audit:
- Ashby's remote_status now distinguishes Hybrid from On-site instead of
  collapsing every non-remote job to 'On-site'.
- The dict now always carries 'remote_status' at all (previously silently
  dropped for every provider routed through backend.job_providers.compatibility,
  defaulting to the Job model's own 'UNKNOWN' column default).
"""
import pytest

from backend import adapters

pytestmark = pytest.mark.usefixtures('no_unexpected_network')


def _install_lever(monkeypatch, rows):
    monkeypatch.setattr('backend.job_providers.lever.fetch_json', lambda url, budget, **kw: rows)


def _install_ashby(monkeypatch, payload):
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: payload)


# ---- Lever ----

def test_lever_normal_board_returns_expected_dict_shape(monkeypatch):
    _install_lever(monkeypatch, [{
        'id': '501', 'text': 'SOC Analyst', 'hostedUrl': 'https://jobs.lever.co/acme/501',
        'categories': {'allLocations': ['Dubai, UAE']}, 'description': '<p>Monitor <b>SIEM</b> alerts.</p>',
        'workplaceType': 'remote', 'createdAt': 1700000000000,
    }])
    jobs = adapters.discover('lever', 'acme')
    assert len(jobs) == 1
    j = jobs[0]
    assert j['title'] == 'SOC Analyst'
    assert j['company'] == 'acme'
    assert j['location'] == 'Dubai, UAE'
    assert j['job_url'] == 'https://jobs.lever.co/acme/501'
    assert j['description'] == 'Monitor\nSIEM\nalerts.'
    assert j['source'] == 'Lever'
    assert j['source_job_id'] == '501'
    assert j['remote_status'] == 'remote'
    assert j['date_posted']


def test_lever_zero_jobs_is_an_empty_list(monkeypatch):
    _install_lever(monkeypatch, [])
    assert adapters.discover('lever', 'acme') == []


def test_lever_board_fetched_once_when_a_single_page(monkeypatch):
    calls = []

    def fake(url, budget, **kw):
        calls.append(url)
        return []

    monkeypatch.setattr('backend.job_providers.lever.fetch_json', fake)
    adapters.discover('lever', 'acme')
    assert len(calls) == 1


def test_lever_invalid_board_rejected_before_any_request(monkeypatch):
    calls = []
    monkeypatch.setattr('backend.job_providers.lever.fetch_json', lambda *a, **kw: calls.append(1))
    with pytest.raises(ValueError):
        adapters.discover('lever', '../etc/passwd')
    assert calls == []


def test_lever_transport_failure_raises_like_legacy_discover_contract(monkeypatch):
    from backend.job_providers import transport as t
    monkeypatch.setattr('backend.job_providers.lever.fetch_json',
                         lambda url, budget, **kw: (_ for _ in ()).throw(t.TransportError('READ_TIMEOUT', 'Read timed out')))
    with pytest.raises(ValueError):
        adapters.discover('lever', 'acme')


# ---- Ashby ----

def test_ashby_normal_board_returns_expected_dict_shape(monkeypatch):
    _install_ashby(monkeypatch, {'jobs': [{
        'id': 'b52d240f', 'title': 'Backend Engineer', 'location': 'Dubai',
        'isListed': True, 'workplaceType': 'OnSite',
        'jobUrl': 'https://jobs.ashbyhq.com/acme/b52d240f',
        'applyUrl': 'https://jobs.ashbyhq.com/acme/b52d240f/application',
        'descriptionPlain': 'Do the work', 'publishedAt': '2026-08-12T05:44:50.125+00:00',
    }]})
    jobs = adapters.discover('ashby', 'acme')
    assert len(jobs) == 1
    j = jobs[0]
    assert j['title'] == 'Backend Engineer'
    assert j['company'] == 'acme'
    assert j['location'] == 'Dubai'
    assert j['job_url'] == 'https://jobs.ashbyhq.com/acme/b52d240f/application'
    assert j['description'] == 'Do the work'
    assert j['source'] == 'Ashby'
    assert j['source_job_id'] == 'b52d240f'
    assert j['date_posted'] == '2026-08-12T05:44:50.125+00:00'
    # Deliberately different from legacy: correctly 'On-site' via the
    # documented workplaceType enum, not merely inferred from isRemote.
    assert j['remote_status'] == 'On-site'


def test_ashby_hybrid_is_no_longer_collapsed_to_on_site(monkeypatch):
    """The confirmed #39 audit bug: legacy code returned 'On-site' here."""
    _install_ashby(monkeypatch, {'jobs': [{
        'id': '1', 'title': 'Hybrid Role', 'workplaceType': 'Hybrid', 'isRemote': False,
        'jobUrl': 'https://jobs.ashbyhq.com/acme/1',
    }]})
    jobs = adapters.discover('ashby', 'acme')
    assert jobs[0]['remote_status'] == 'Hybrid'


def test_ashby_unlisted_jobs_are_excluded(monkeypatch):
    _install_ashby(monkeypatch, {'jobs': [
        {'id': '1', 'title': 'Visible', 'jobUrl': 'https://jobs.ashbyhq.com/acme/1', 'isListed': True},
        {'id': '2', 'title': 'Hidden', 'jobUrl': 'https://jobs.ashbyhq.com/acme/2', 'isListed': False},
    ]})
    jobs = adapters.discover('ashby', 'acme')
    assert [j['source_job_id'] for j in jobs] == ['1']


def test_ashby_zero_jobs_is_an_empty_list(monkeypatch):
    _install_ashby(monkeypatch, {'jobs': []})
    assert adapters.discover('ashby', 'acme') == []


def test_ashby_missing_id_still_produces_a_usable_job_via_url_fallback(monkeypatch):
    """Deliberately different from legacy (which raised a raw KeyError on
    x['id']): a documented, stable fallback identity keeps the job usable."""
    _install_ashby(monkeypatch, {'jobs': [{
        'title': 'No native id', 'jobUrl': 'https://jobs.ashbyhq.com/acme/no-id',
    }]})
    jobs = adapters.discover('ashby', 'acme')
    assert len(jobs) == 1
    assert jobs[0]['source_job_id'] == 'https://jobs.ashbyhq.com/acme/no-id'


def test_ashby_invalid_board_rejected_before_any_request(monkeypatch):
    calls = []
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda *a, **kw: calls.append(1))
    with pytest.raises(ValueError):
        adapters.discover('ashby', '../etc/passwd')
    assert calls == []


def test_ashby_transport_failure_raises_like_legacy_discover_contract(monkeypatch):
    from backend.job_providers import transport as t
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json',
                         lambda url, budget, **kw: (_ for _ in ()).throw(t.TransportError('UPSTREAM_ERROR', 'Upstream returned 404')))
    with pytest.raises(ValueError):
        adapters.discover('ashby', 'backpack')

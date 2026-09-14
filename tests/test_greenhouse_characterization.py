"""Characterization tests for backend.adapters.discover('greenhouse', ...).

These lock in the EXTERNAL behavior of the Greenhouse discovery path --
the dict shape callers (backend/main.py's discover task) rely on -- so the
issue #38 provider-framework migration can be verified not to have changed
it. They intentionally do not test internals (which module does the
fetching); they test what discover('greenhouse', board, url) returns for a
given fixture HTTP response, exactly as backend/main.py consumes it.

Codex round-2 finding F7: an earlier version of this file mocked
backend.adapters.validate_url, a seam production no longer uses once the
Greenhouse fetch moved into backend.job_providers -- the mock silently did
nothing and every test here made a real DNS/HTTPS call to Greenhouse.
These tests now mock backend.job_providers.greenhouse.fetch_json (the
actual seam) and enable no_unexpected_network to fail loudly, not
silently succeed over a real connection, if that ever regresses again.
"""
import pytest
from backend import adapters
import backend.job_providers.greenhouse as gh

pytestmark = pytest.mark.usefixtures('no_unexpected_network')


def _install(monkeypatch, payload):
    def fake_fetch_json(url, budget, **kw):
        return payload
    monkeypatch.setattr(gh, 'fetch_json', fake_fetch_json)


def test_normal_board_returns_expected_dict_shape(monkeypatch):
    payload = {'jobs': [{'id': 501, 'title': 'SOC Analyst', 'absolute_url': 'https://job-boards.greenhouse.io/acme/jobs/501', 'location': {'name': 'Dubai, UAE'}, 'content': '<p>Monitor <b>SIEM</b> alerts.</p>', 'first_published': '2026-01-05T00:00:00Z', 'application_deadline': '2026-03-01T00:00:00Z'}]}
    _install(monkeypatch, payload)
    jobs = adapters.discover('greenhouse', 'acme')
    assert len(jobs) == 1
    j = jobs[0]
    assert j['title'] == 'SOC Analyst'
    assert j['company'] == 'acme'
    assert j['location'] == 'Dubai, UAE'
    assert j['job_url'] == 'https://job-boards.greenhouse.io/acme/jobs/501'
    assert j['description'] == 'Monitor\nSIEM\nalerts.'
    assert j['source'] == 'Greenhouse'
    assert j['source_job_id'] == '501'
    assert j['date_posted'] == '2026-01-05T00:00:00Z'
    assert j['closing_date'] == '2026-03-01T00:00:00Z'


def test_zero_jobs_is_an_empty_list_not_an_error(monkeypatch):
    _install(monkeypatch, {'jobs': []})
    assert adapters.discover('greenhouse', 'acme') == []


def test_multiple_jobs_all_returned(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': ''}, {'id': 2, 'title': 'B', 'absolute_url': 'https://x/2', 'location': {'name': 'Sharjah'}, 'content': ''}]}
    _install(monkeypatch, payload)
    jobs = adapters.discover('greenhouse', 'acme')
    assert [j['source_job_id'] for j in jobs] == ['1', '2']


def test_escaped_html_content_is_cleaned_to_plain_text(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': '&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;\n<p>Real duty</p>'}]}
    _install(monkeypatch, payload)
    jobs = adapters.discover('greenhouse', 'acme')
    assert '<script>' not in jobs[0]['description']
    assert 'Real duty' in jobs[0]['description']


def test_missing_publication_date_stays_missing_not_invented(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': ''}]}
    _install(monkeypatch, payload)
    jobs = adapters.discover('greenhouse', 'acme')
    assert jobs[0]['date_posted'] == ''
    assert jobs[0]['closing_date'] == ''


def test_hybrid_location_pulls_embedded_location_from_description(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Hybrid'}, 'content': 'About us.\nLocation: Dubai, UAE\nMore text.'}]}
    _install(monkeypatch, payload)
    jobs = adapters.discover('greenhouse', 'acme')
    assert 'Dubai, UAE' in jobs[0]['location']
    assert 'Hybrid' in jobs[0]['location']


def test_board_is_fetched_exactly_once_per_discover_call(monkeypatch):
    calls = []
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': ''}]}

    def fake_fetch_json(url, budget, **kw):
        calls.append(url)
        return payload

    monkeypatch.setattr(gh, 'fetch_json', fake_fetch_json)
    adapters.discover('greenhouse', 'acme')
    assert len(calls) == 1


def test_invalid_board_identifier_rejected_before_any_request(monkeypatch):
    calls = []
    monkeypatch.setattr(gh, 'fetch_json', lambda *a, **kw: calls.append(1))
    with pytest.raises(ValueError):
        adapters.discover('greenhouse', '../etc/passwd')
    assert calls == []

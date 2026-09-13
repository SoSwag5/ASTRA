"""Contract, completeness, and compatibility tests for the new job-provider
framework (issue #38): backend.job_providers.greenhouse/registry/compatibility.
"""
import pytest

from backend.job_providers import registry
from backend.job_providers.compatibility import to_legacy_items
from backend.job_providers.contracts import FetchCompletion, FetchContext, SourceHealth
from backend.job_providers.greenhouse import GreenhouseProvider
from backend.job_providers import transport as t


def _fake_fetch_json(pages):
    """pages: list of (expected_url_substring, payload_or_exception) consumed in order."""
    calls = []

    def fake(url, budget, **kw):
        calls.append(url)
        _, result = pages.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    return fake, calls


def test_capabilities_declares_no_cursor_and_detail_support():
    caps = GreenhouseProvider().capabilities()
    assert caps.provider == 'greenhouse'
    assert caps.supports_cursor is False
    assert caps.supports_detail_fetch is True


def test_successful_fetch_is_complete_and_healthy(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'SOC Analyst', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': 'Duties', 'first_published': '2026-01-01T00:00:00Z'}]}
    fake, calls = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.HEALTHY
    assert len(batch.records) == 1
    assert batch.records[0].provider == 'greenhouse'
    assert batch.records[0].source_board == 'acme'
    assert batch.records[0].provider_job_id == '1'
    assert len(calls) == 1


def test_empty_board_is_complete_and_empty_not_failed(monkeypatch):
    fake, _ = _fake_fetch_json([('boards-api', {'jobs': []})])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.EMPTY
    assert batch.records == []
    assert batch.error is None


def test_missing_publication_date_is_left_missing_not_invented(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': ''}]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].posted_at == ''
    assert batch.records[0].closing_at == ''


def test_transport_failure_is_failed_with_sanitized_error(monkeypatch):
    fake, _ = _fake_fetch_json([('boards-api', t.TransportError('DESTINATION_BLOCKED', 'Private network addresses are blocked'))])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.health == SourceHealth.POLICY_BLOCKED
    assert batch.records == []
    assert batch.error.code == 'DESTINATION_BLOCKED'


def test_unexpected_top_level_shape_fails_closed(monkeypatch):
    fake, _ = _fake_fetch_json([('boards-api', {'not_jobs': []})])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.health == SourceHealth.MALFORMED


def test_jobs_not_a_list_fails_closed(monkeypatch):
    fake, _ = _fake_fetch_json([('boards-api', {'jobs': 'oops'})])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED


def test_row_missing_required_field_is_rejected_not_the_whole_board(monkeypatch):
    payload = {'jobs': [
        {'id': 1, 'title': 'Good', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}},
        {'id': 2, 'absolute_url': 'https://x/2', 'location': {'name': 'Dubai'}},  # missing title
    ]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.COMPLETE
    assert len(batch.records) == 1
    assert batch.metrics.records_rejected == 1


def test_wrong_field_type_is_rejected_per_row(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 123, 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}}]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []
    assert batch.metrics.records_rejected == 1


def test_invalid_board_rejected_before_any_network_call(monkeypatch):
    calls = []
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', lambda *a, **kw: calls.append(1))
    batch = GreenhouseProvider().fetch(FetchContext(), '../etc/passwd')
    assert batch.completion == FetchCompletion.FAILED
    assert calls == []


# ---- detail-fallback / budget / coverage-cap semantics ----

def test_oversized_list_falls_back_and_all_summary_rows_still_returned(monkeypatch):
    summary = {'jobs': [{'id': i, 'title': f'Role {i}', 'absolute_url': f'https://x/{i}', 'location': {'name': 'Dubai'}} for i in range(3)]}
    detail_calls = []

    def fake(url, budget, **kw):
        if url.endswith('?content=true'):
            raise t.TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
        if url == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs':
            return summary
        detail_calls.append(url)
        job_id = url.rsplit('/', 1)[-1]
        return {'content': f'Detail for {job_id}'}

    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(detail_budget=100), 'acme')
    assert len(batch.records) == 3
    assert batch.completion == FetchCompletion.COMPLETE
    assert len(detail_calls) == 3


def test_detail_budget_exceeded_is_partial_never_empty_never_silently_complete(monkeypatch):
    summary = {'jobs': [{'id': i, 'title': f'Role {i}', 'absolute_url': f'https://x/{i}', 'location': {'name': 'Dubai'}} for i in range(5)]}

    def fake(url, budget, **kw):
        if url.endswith('?content=true'):
            raise t.TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
        if url == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs':
            return summary
        return {'content': 'Detail'}

    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(detail_budget=2), 'acme')
    assert len(batch.records) == 5  # every summary row is still returned
    assert batch.completion == FetchCompletion.PARTIAL
    assert batch.health == SourceHealth.PARTIAL
    assert batch.metrics.coverage_cap_reached is True


def test_title_hints_prioritize_detail_budget_without_ranking_them(monkeypatch):
    summary = {'jobs': [
        {'id': 1, 'title': 'Barista', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}},
        {'id': 2, 'title': 'SOC Analyst', 'absolute_url': 'https://x/2', 'location': {'name': 'Dubai'}},
    ]}
    detailed_ids = []

    def fake(url, budget, **kw):
        if url.endswith('?content=true'):
            raise t.TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
        if url == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs':
            return summary
        detailed_ids.append(url.rsplit('/', 1)[-1])
        return {'content': 'Detail'}

    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(title_hints=('soc analyst',), detail_budget=1), 'acme')
    assert detailed_ids == ['2']
    assert len(batch.records) == 2  # the non-hinted row is still present, just without detail content


def test_one_items_detail_failure_does_not_void_the_rest(monkeypatch):
    summary = {'jobs': [
        {'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}},
        {'id': 2, 'title': 'B', 'absolute_url': 'https://x/2', 'location': {'name': 'Dubai'}},
    ]}

    def fake(url, budget, **kw):
        if url.endswith('?content=true'):
            raise t.TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
        if url == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs':
            return summary
        if url.endswith('/1'):
            raise t.TransportError('TIMEOUT', 'Request timed out')
        return {'content': 'Detail for 2'}

    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 2
    assert batch.completion == FetchCompletion.PARTIAL


# ---- registry ----

def test_registry_resolves_greenhouse_and_unknown_provider_is_none():
    assert registry.get_provider('greenhouse') is not None
    assert registry.get_provider('nonexistent') is None


# ---- compatibility seam ----

def test_compatibility_preserves_legacy_dict_shape_and_carries_health(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'SOC Analyst', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': 'Duties'}]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    items = to_legacy_items(batch)
    assert isinstance(items, list)
    assert items[0] == {
        'company': 'acme', 'title': 'SOC Analyst', 'location': 'Dubai', 'job_url': 'https://x/1',
        'description': 'Duties', 'source': 'Greenhouse', 'source_job_id': '1', 'date_posted': '', 'closing_date': '',
    }
    assert items.health['completion'] == 'COMPLETE'
    assert items.health['health'] == 'HEALTHY'


def test_compatibility_raises_on_failed_batch_matching_legacy_discover_contract(monkeypatch):
    fake, _ = _fake_fetch_json([('boards-api', t.TransportError('DESTINATION_BLOCKED', 'Private network addresses are blocked'))])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    with pytest.raises(ValueError):
        to_legacy_items(batch)

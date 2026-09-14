"""Contract, completeness, and compatibility tests for the new job-provider
framework (issue #38): backend.job_providers.greenhouse/registry/compatibility.
"""
import pytest

from backend.job_providers import registry
from backend.job_providers.compatibility import to_legacy_items
from backend.job_providers.contracts import CompletionReason, FetchCompletion, FetchContext, SourceHealth
from backend.job_providers.greenhouse import GreenhouseProvider, ProviderFetchFailed
from backend.job_providers import transport as t

pytestmark = pytest.mark.usefixtures('no_unexpected_network')


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
    # Codex B4 point 1: a mix of valid+invalid rows is COMPLETE
    # (enumeration finished normally) but must not silently claim fully
    # HEALTHY -- SourceHealth.PARTIAL + SOME_RECORDS_REJECTED says a
    # source record was actually malformed and dropped.
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.PARTIAL
    assert batch.completion_reason == CompletionReason.SOME_RECORDS_REJECTED.value
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
    assert batch.metrics.content_cap_reached is True
    assert batch.completion_reason == CompletionReason.DETAIL_BUDGET_EXHAUSTED.value


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
            raise t.TransportError('READ_TIMEOUT', 'Read timed out')
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
        'remote_status': 'UNKNOWN',
    }
    assert items.health['completion'] == 'COMPLETE'
    assert items.health['health'] == 'HEALTHY'


def test_compatibility_raises_on_failed_batch_matching_legacy_discover_contract(monkeypatch):
    fake, _ = _fake_fetch_json([('boards-api', t.TransportError('DESTINATION_BLOCKED', 'Private network addresses are blocked'))])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    with pytest.raises(ValueError):
        to_legacy_items(batch)


def test_compatibility_failure_exception_carries_true_completion_not_stale_complete(monkeypatch):
    """Codex F5/B6.4: a failing source must not be reported as COMPLETE,
    and the exception must carry bounded completion/health/reason/metrics
    (not just completion/health) so main.py can persist fresh telemetry."""
    fake, _ = _fake_fetch_json([('boards-api', t.TransportError('READ_TIMEOUT', 'Read timed out'))])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    with pytest.raises(ProviderFetchFailed) as exc:
        to_legacy_items(batch)
    assert exc.value.completion == 'FAILED'
    assert exc.value.health == 'UNAVAILABLE'
    assert exc.value.completion_reason == CompletionReason.TRANSPORT_ERROR.value
    assert exc.value.error_code == 'READ_TIMEOUT'
    assert isinstance(exc.value.metrics, dict)
    assert exc.value.metrics['requests_attempted'] >= 0


# ---- F3: malformed records/details must not look successful ----

def test_dict_job_id_is_rejected_not_stringified(monkeypatch):
    payload = {'jobs': [{'id': {'bad': 1}, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}}]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []
    assert batch.completion == FetchCompletion.FAILED  # the only row was rejected -> not a genuine empty board


def test_dict_content_is_rejected_not_silently_emptied(monkeypatch):
    payload = {'jobs': [
        {'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': {'nested': True}},
        {'id': 2, 'title': 'B', 'absolute_url': 'https://x/2', 'location': {'name': 'Dubai'}, 'content': 'fine'},
    ]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.records[0].provider_job_id == '2'
    assert batch.metrics.records_rejected == 1


def test_board_with_only_unusable_rows_is_failed_not_empty(monkeypatch):
    payload = {'jobs': [{'id': 1}]}  # missing title/url/location entirely
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.health == SourceHealth.MALFORMED
    assert batch.error.code == 'ALL_RECORDS_REJECTED'
    assert batch.completion_reason == CompletionReason.ALL_RECORDS_REJECTED.value


def test_malformed_location_shape_rejects_the_row(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': 'Dubai'}]}  # location must be a dict
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_non_http_url_is_rejected(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'javascript:alert(1)', 'location': {'name': 'Dubai'}}]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_empty_detail_dict_is_a_failed_detail_attempt_not_a_success(monkeypatch):
    summary = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}}]}

    def fake(url, budget, **kw):
        if url.endswith('?content=true'):
            raise t.TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
        if url == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs':
            return summary
        return {}  # empty dict: not a usable detail payload

    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1  # summary row still usable
    assert batch.completion == FetchCompletion.PARTIAL
    assert batch.metrics.detail_requests_attempted == 1
    assert batch.metrics.detail_requests_succeeded == 0


# ---- F1: source deadline is a real upper bound, not a between-calls check ----

def test_deadline_expiring_mid_detail_loop_stops_further_detail_attempts(monkeypatch):
    summary = {'jobs': [
        {'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}},
        {'id': 2, 'title': 'B', 'absolute_url': 'https://x/2', 'location': {'name': 'Dubai'}},
        {'id': 3, 'title': 'C', 'absolute_url': 'https://x/3', 'location': {'name': 'Dubai'}},
    ]}
    calls = []

    def fake(url, budget, **kw):
        if url.endswith('?content=true'):
            raise t.TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
        if url == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs':
            return summary
        calls.append(url)
        if url.endswith('/1'):
            return {'content': 'Detail 1'}
        budget.deadline = 0
        budget.check()

    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 2  # stopped after the deadline hit on item 2 -- never attempted item 3
    assert batch.completion == FetchCompletion.FAILED
    assert batch.error.code == 'DEADLINE_EXCEEDED'
    assert batch.metrics.errors_count == 2  # content cap and one source deadline


def test_result_arriving_after_deadline_expired_is_not_reported_as_complete(monkeypatch):
    """The transport itself is responsible for not returning a parsed
    result once the deadline has passed; the provider must not
    second-guess a raised DEADLINE_EXCEEDED as anything but a failure to
    fully complete that particular call.
    """
    fake, _ = _fake_fetch_json([('boards-api', t.TransportError('DEADLINE_EXCEEDED', 'Source deadline exceeded'))])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.completion != FetchCompletion.COMPLETE


# ---- F6: telemetry precision ----

def test_metrics_track_attempted_vs_succeeded_and_encoded_vs_decoded(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': 'x'}]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.metrics.records_received == 1
    assert batch.metrics.records_accepted == 1
    assert batch.metrics.records_rejected == 0
    assert batch.metrics.errors_count == 0


# ---- B4: Greenhouse validation / detail-merge hardening ----

def test_empty_string_id_is_rejected(monkeypatch):
    payload = {'jobs': [{'id': '', 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}}]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_whitespace_only_id_is_rejected(monkeypatch):
    payload = {'jobs': [{'id': '   ', 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}}]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_malformed_url_does_not_raise_a_raw_valueerror(monkeypatch):
    """urlsplit('https://[') raises ValueError; the provider must reject
    the row, not let that exception escape out of fetch()."""
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://[', 'location': {'name': 'Dubai'}}]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')  # must not raise
    assert batch.records == []


def test_absent_timestamp_and_malformed_timestamp_are_distinguished(monkeypatch):
    payload = {'jobs': [
        {'id': 1, 'title': 'Absent', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}},
        {'id': 2, 'title': 'Malformed', 'absolute_url': 'https://x/2', 'location': {'name': 'Dubai'}, 'first_published': {'weird': True}},
    ]}
    fake, _ = _fake_fetch_json([('boards-api', payload)])
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 2  # a malformed OPTIONAL field never rejects the whole record
    absent, malformed = batch.records
    assert absent.posted_at == '' and 'first_published_malformed' not in absent.raw_fields
    assert malformed.posted_at == '' and malformed.raw_fields.get('first_published_malformed') is True


def test_detail_with_unrelated_keys_is_rejected_not_counted_as_success(monkeypatch):
    """{'foo': 'bar'} is a non-empty dict but not a genuine Greenhouse
    detail payload (no 'content' key) -- must not count as a successful
    detail fetch."""
    summary = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}}]}

    def fake(url, budget, **kw):
        if url.endswith('?content=true'):
            raise t.TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
        if url == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs':
            return summary
        return {'foo': 'bar'}

    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.metrics.detail_requests_succeeded == 0


def test_malformed_detail_merge_never_destroys_a_valid_summary(monkeypatch):
    """Codex B4 point 6: a detail response with a corrupt title must not
    be allowed to silently overwrite and destroy an already-usable
    summary row -- the candidate merge is validated before being
    committed; on failure the original summary is kept.
    """
    summary = {'jobs': [{'id': 1, 'title': 'Good Title', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}}]}

    def fake(url, budget, **kw):
        if url.endswith('?content=true'):
            raise t.TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
        if url == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs':
            return summary
        return {'content': 'ok', 'title': {}}  # malformed title would corrupt the merge

    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.records[0].title == 'Good Title'  # original summary preserved, not destroyed
    assert batch.records[0].description == ''  # the bad detail was not merged in either
    assert batch.metrics.detail_requests_attempted == 1
    assert batch.metrics.detail_requests_succeeded == 0


def test_valid_detail_merge_is_committed_and_counted(monkeypatch):
    summary = {'jobs': [{'id': 1, 'title': 'Good Title', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}}]}

    def fake(url, budget, **kw):
        if url.endswith('?content=true'):
            raise t.TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
        if url == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs':
            return summary
        return {'content': 'Real duties here'}

    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', fake)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].description == 'Real duties here'
    assert batch.metrics.detail_requests_succeeded == 1
    assert batch.completion == FetchCompletion.COMPLETE

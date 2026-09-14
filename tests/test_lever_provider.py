"""Contract, pagination, and createdAt-provenance tests for
backend.job_providers.lever (issue #39).

Lever's own postings-api documentation confirms skip/limit pagination is
supported (the legacy adapters.py path made exactly one request and
silently truncated any board with more postings than that single page),
and confirms `createdAt` is NOT part of the documented schema despite
being present on real responses. These tests focus on the bounded
pagination this migration adds and the best-effort, clearly-provenanced
handling of createdAt.
"""
import pytest

from backend.job_providers.lever import LeverProvider, LEVER_PAGE_SIZE, LEVER_MAX_PAGES, LEVER_MAX_RECORDS
from backend.job_providers.contracts import CompletionReason, FetchCompletion, FetchContext, ProviderFetchFailed, SourceHealth
from backend.job_providers import registry
from backend.job_providers.compatibility import to_legacy_items
from backend.job_providers import transport as t

pytestmark = pytest.mark.usefixtures('no_unexpected_network')


def _posting(i, **overrides):
    base = {
        'id': str(i), 'text': f'Role {i}', 'hostedUrl': f'https://jobs.lever.co/acme/{i}',
        'applyUrl': f'https://jobs.lever.co/acme/{i}/apply',
        'categories': {'location': 'Dubai', 'allLocations': ['Dubai']},
        'workplaceType': 'remote', 'createdAt': 1700000000000 + i,
        'description': '<p>Do the work</p>', 'lists': [],
    }
    base.update(overrides)
    return base


def _paged(monkeypatch, pages):
    """pages: dict of skip -> list-of-rows (or an Exception to raise)."""
    calls = []

    def fake(url, budget, **kw):
        calls.append(url)
        skip = int(url.split('skip=')[1].split('&')[0])
        result = pages[skip]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr('backend.job_providers.lever.fetch_json', fake)
    return calls


def test_capabilities_declares_cursor_support_no_detail_fetch():
    caps = LeverProvider().capabilities()
    assert caps.provider == 'lever'
    assert caps.supports_cursor is True
    assert caps.supports_detail_fetch is False


def test_single_short_page_is_complete_and_healthy(monkeypatch):
    calls = _paged(monkeypatch, {0: [_posting(1)]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 1
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.HEALTHY
    assert len(batch.records) == 1


def test_zero_jobs_is_complete_and_empty(monkeypatch):
    _paged(monkeypatch, {0: []})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.EMPTY


# ---- pagination ----

def test_multi_page_pagination_collects_all_pages(monkeypatch):
    page0 = [_posting(i) for i in range(LEVER_PAGE_SIZE)]
    page1 = [_posting(i) for i in range(LEVER_PAGE_SIZE, LEVER_PAGE_SIZE + 30)]
    calls = _paged(monkeypatch, {0: page0, LEVER_PAGE_SIZE: page1})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 2
    assert len(batch.records) == LEVER_PAGE_SIZE + 30
    assert batch.completion == FetchCompletion.COMPLETE


def test_page_termination_on_short_final_page(monkeypatch):
    page0 = [_posting(i) for i in range(LEVER_PAGE_SIZE)]
    page1 = [_posting(i) for i in range(LEVER_PAGE_SIZE, LEVER_PAGE_SIZE + 1)]
    calls = _paged(monkeypatch, {0: page0, LEVER_PAGE_SIZE: page1})
    LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 2  # stops after the short page, never requests a third


def test_pagination_bound_caps_pages_and_records(monkeypatch):
    full_page = lambda seed: [_posting(seed * 1000 + i) for i in range(LEVER_PAGE_SIZE)]
    pages = {skip: full_page(skip) for skip in range(0, LEVER_PAGE_SIZE * (LEVER_MAX_PAGES + 5), LEVER_PAGE_SIZE)}
    calls = _paged(monkeypatch, pages)
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == LEVER_MAX_PAGES
    assert len(batch.records) == LEVER_MAX_RECORDS
    assert batch.completion == FetchCompletion.PARTIAL
    assert batch.completion_reason == CompletionReason.PAGINATION_LIMIT_REACHED.value
    assert batch.metrics.content_cap_reached is True


def test_repeated_cyclic_page_stops_early_without_duplicating_records(monkeypatch):
    """A board that ignores `skip` and keeps returning the same page must
    not be looped on up to the full page cap, and must not produce
    duplicate records for the same postings."""
    same_page = [_posting(i) for i in range(LEVER_PAGE_SIZE)]
    pages = {skip: same_page for skip in range(0, LEVER_PAGE_SIZE * LEVER_MAX_PAGES, LEVER_PAGE_SIZE)}
    calls = _paged(monkeypatch, pages)
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 2  # detected after the second identical page, not all LEVER_MAX_PAGES
    assert len(batch.records) == LEVER_PAGE_SIZE  # not duplicated
    assert batch.completion == FetchCompletion.PARTIAL
    assert batch.completion_reason == CompletionReason.PAGINATION_LIMIT_REACHED.value


def test_transport_failure_after_earlier_pages_preserves_them_as_partial(monkeypatch):
    """Owner instruction: page 1..N succeed, page N+1 fails -> PARTIAL
    preserving the valid earlier records, not a full failure."""
    page0 = [_posting(i) for i in range(LEVER_PAGE_SIZE)]
    calls = _paged(monkeypatch, {0: page0, LEVER_PAGE_SIZE: t.TransportError('READ_TIMEOUT', 'Read timed out')})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 2
    assert len(batch.records) == LEVER_PAGE_SIZE
    assert batch.completion == FetchCompletion.PARTIAL
    assert batch.completion_reason == CompletionReason.TRANSPORT_ERROR.value
    assert batch.error.code == 'READ_TIMEOUT'


def test_transport_failure_on_first_page_is_a_full_failure(monkeypatch):
    _paged(monkeypatch, {0: t.TransportError('READ_TIMEOUT', 'Read timed out')})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.records == []


def test_malformed_pagination_response_after_first_page_is_partial(monkeypatch):
    page0 = [_posting(i) for i in range(LEVER_PAGE_SIZE)]
    _paged(monkeypatch, {0: page0, LEVER_PAGE_SIZE: {'not': 'a list'}})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == LEVER_PAGE_SIZE
    assert batch.completion == FetchCompletion.PARTIAL


def test_malformed_first_page_response_is_a_full_failure(monkeypatch):
    _paged(monkeypatch, {0: {'not': 'a list'}})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.health == SourceHealth.MALFORMED


# ---- record validation ----

def test_missing_id_is_rejected(monkeypatch):
    job = _posting(1)
    del job['id']
    _paged(monkeypatch, {0: [job]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_missing_title_is_rejected(monkeypatch):
    job = _posting(1)
    del job['text']
    _paged(monkeypatch, {0: [job]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_invalid_hosted_url_is_rejected(monkeypatch):
    _paged(monkeypatch, {0: [_posting(1, hostedUrl='not-a-url')]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_invalid_apply_url_falls_back_to_hosted_url(monkeypatch):
    job = _posting(1, applyUrl='not-a-url')
    _paged(monkeypatch, {0: [job]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].apply_url == job['hostedUrl']


def test_missing_optional_fields_degrade_gracefully(monkeypatch):
    job = {'id': '1', 'text': 'Role', 'hostedUrl': 'https://jobs.lever.co/acme/1'}
    _paged(monkeypatch, {0: [job]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    r = batch.records[0]
    assert r.location == 'UNKNOWN' and r.remote_status == 'UNKNOWN' and r.posted_at == ''


def test_multiple_locations_are_joined(monkeypatch):
    job = _posting(1, categories={'allLocations': ['Dubai', 'Singapore']})
    _paged(monkeypatch, {0: [job]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert 'Dubai' in batch.records[0].location and 'Singapore' in batch.records[0].location


def test_workplace_type_is_passed_through_raw(monkeypatch):
    _paged(monkeypatch, {0: [_posting(1, workplaceType='hybrid')]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].remote_status == 'hybrid'


def test_all_malformed_is_failed_not_empty(monkeypatch):
    job = _posting(1)
    del job['text']
    _paged(monkeypatch, {0: [job]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.error.code == 'ALL_RECORDS_REJECTED'


def test_mixed_valid_and_malformed_rows(monkeypatch):
    bad = _posting(2)
    del bad['text']
    _paged(monkeypatch, {0: [_posting(1), bad]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.metrics.records_rejected == 1
    assert batch.completion_reason == CompletionReason.SOME_RECORDS_REJECTED.value


# ---- createdAt provenance (the confirmed undocumented-field finding) ----

def test_valid_created_at_is_preserved_with_provenance_flag(monkeypatch):
    _paged(monkeypatch, {0: [_posting(1, createdAt=1700000000000)]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    r = batch.records[0]
    assert r.posted_at != ''
    assert r.raw_fields.get('posted_at_provenance') == 'undocumented_createdAt_field'


def test_absent_created_at_is_neutral_empty_string(monkeypatch):
    job = _posting(1)
    del job['createdAt']
    _paged(monkeypatch, {0: [job]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    r = batch.records[0]
    assert r.posted_at == ''
    assert 'posted_at_provenance' not in r.raw_fields
    assert 'createdAt_malformed' not in r.raw_fields


def test_malformed_created_at_does_not_crash_and_is_flagged(monkeypatch):
    _paged(monkeypatch, {0: [_posting(1, createdAt='not-a-number')]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')  # must not raise
    r = batch.records[0]
    assert r.posted_at == ''
    assert r.raw_fields.get('createdAt_malformed') is True


def test_negative_created_at_is_treated_as_malformed(monkeypatch):
    _paged(monkeypatch, {0: [_posting(1, createdAt=-5)]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].posted_at == ''


def test_created_at_never_fabricated_from_fetch_time(monkeypatch):
    """Regression: absence must stay '' -- never silently filled with the
    current fetch timestamp, which would misrepresent when the posting
    was actually created."""
    job = _posting(1)
    del job['createdAt']
    _paged(monkeypatch, {0: [job]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].posted_at == ''


# ---- board validation / registry / compatibility ----

def test_invalid_board_rejected_before_any_network_call(monkeypatch):
    calls = []
    monkeypatch.setattr('backend.job_providers.lever.fetch_json', lambda *a, **kw: calls.append(1))
    batch = LeverProvider().fetch(FetchContext(), '../etc/passwd')
    assert batch.completion == FetchCompletion.FAILED
    assert calls == []


def test_registry_resolves_lever():
    assert registry.get_provider('lever') is not None


def test_board_fetched_with_bounded_pages_no_extra_requests_when_single_page(monkeypatch):
    calls = _paged(monkeypatch, {0: [_posting(1)]})
    LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 1


def test_compatibility_preserves_workplace_type_and_source_label(monkeypatch):
    _paged(monkeypatch, {0: [_posting(1, workplaceType='remote')]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    items = to_legacy_items(batch)
    assert items[0]['source'] == 'Lever'
    assert items[0]['remote_status'] == 'remote'


def test_compatibility_raises_on_failed_batch(monkeypatch):
    _paged(monkeypatch, {0: t.TransportError('READ_TIMEOUT', 'Read timed out')})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    with pytest.raises(ProviderFetchFailed):
        to_legacy_items(batch)

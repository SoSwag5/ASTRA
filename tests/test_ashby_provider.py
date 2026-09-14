"""Contract, completeness, and identity/workplace-semantics tests for
backend.job_providers.ashby (issue #39).

Ashby's public job-board API has no pagination (verified against Ashby's
own documentation) -- these tests focus on the two audit-confirmed
legacy bugs this migration fixes: an assumed-present `id` field the
public schema never actually documents, and workplace-type collapsing
(every non-remote job silently mapped to On-site, destroying Hybrid).
"""
import pytest

from backend.job_providers.ashby import AshbyProvider
from backend.job_providers.contracts import CompletionReason, FetchCompletion, FetchContext, SourceHealth
from backend.job_providers import registry
from backend.job_providers.compatibility import to_legacy_items
from backend.job_providers.contracts import ProviderFetchFailed
from backend.job_providers import transport as t

pytestmark = pytest.mark.usefixtures('no_unexpected_network')


def _job(**overrides):
    base = {
        'id': 'b52d240f-2ccb-4aea-800b-623e9ca8ae09', 'title': 'Backend Engineer',
        'location': 'Dubai', 'isListed': True, 'isRemote': False, 'workplaceType': 'OnSite',
        'jobUrl': 'https://jobs.ashbyhq.com/acme/b52d240f', 'applyUrl': 'https://jobs.ashbyhq.com/acme/b52d240f/application',
        'descriptionPlain': 'Do the work', 'publishedAt': '2026-08-12T05:44:50.125+00:00',
    }
    base.update(overrides)
    return base


def _install(monkeypatch, payload):
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: payload)


def test_capabilities_declares_no_cursor_no_detail_fetch():
    caps = AshbyProvider().capabilities()
    assert caps.provider == 'ashby'
    assert caps.supports_cursor is False
    assert caps.supports_detail_fetch is False


def test_successful_fetch_is_complete_and_healthy(monkeypatch):
    _install(monkeypatch, {'jobs': [_job()]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.HEALTHY
    assert len(batch.records) == 1
    r = batch.records[0]
    assert r.provider == 'ashby' and r.source_board == 'acme'
    assert r.provider_job_id == 'b52d240f-2ccb-4aea-800b-623e9ca8ae09'
    assert r.title == 'Backend Engineer'
    assert r.apply_url == 'https://jobs.ashbyhq.com/acme/b52d240f/application'


def test_empty_board_is_complete_and_empty_not_failed(monkeypatch):
    _install(monkeypatch, {'jobs': []})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.EMPTY
    assert batch.records == []


def test_unlisted_job_is_excluded_not_counted_as_rejected(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(isListed=False)]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.EMPTY
    assert batch.metrics.records_received == 0
    assert batch.metrics.records_rejected == 0


# ---- identity: the confirmed 'id not guaranteed' finding ----

def test_missing_id_falls_back_to_documented_job_url(monkeypatch):
    job = _job()
    del job['id']
    _install(monkeypatch, {'jobs': [job]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.records[0].provider_job_id == job['jobUrl']
    assert batch.records[0].raw_fields.get('identity_fallback') == 'jobUrl'


def test_empty_string_id_falls_back_to_job_url(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(id='')]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].raw_fields.get('identity_fallback') == 'jobUrl'


def test_no_id_and_no_valid_job_url_is_rejected(monkeypatch):
    job = _job()
    del job['id']
    job['jobUrl'] = 'not-a-url'
    job['applyUrl'] = 'not-a-url'
    _install(monkeypatch, {'jobs': [job]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []
    assert batch.completion == FetchCompletion.FAILED  # the only row was rejected, not a genuine empty board


def test_id_present_is_preferred_over_job_url(monkeypatch):
    _install(monkeypatch, {'jobs': [_job()]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].provider_job_id == 'b52d240f-2ccb-4aea-800b-623e9ca8ae09'
    assert 'identity_fallback' not in batch.records[0].raw_fields


# ---- workplace semantics: the confirmed Hybrid-collapsing bug ----

def test_workplace_type_onsite_is_on_site_not_inferred(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(workplaceType='OnSite', isRemote=False)]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].remote_status == 'On-site'


def test_workplace_type_remote(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(workplaceType='Remote', isRemote=True)]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].remote_status == 'Remote'


def test_workplace_type_hybrid_is_preserved_not_collapsed_to_on_site(monkeypatch):
    """The confirmed legacy bug: isRemote=False used to force 'On-site'
    even when Ashby's own documented workplaceType said Hybrid."""
    _install(monkeypatch, {'jobs': [_job(workplaceType='Hybrid', isRemote=False)]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].remote_status == 'Hybrid'


def test_absent_workplace_type_with_remote_true_is_remote(monkeypatch):
    job = _job(isRemote=True)
    del job['workplaceType']
    _install(monkeypatch, {'jobs': [job]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].remote_status == 'Remote'


def test_absent_workplace_type_and_false_isremote_is_unknown_not_on_site(monkeypatch):
    """isRemote=False alone must never be read as 'On-site' -- that is
    exactly the confirmed bug this migration fixes."""
    job = _job(isRemote=False)
    del job['workplaceType']
    _install(monkeypatch, {'jobs': [job]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].remote_status == 'UNKNOWN'


def test_unrecognized_workplace_type_value_is_unknown(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(workplaceType='SomeNewEnumValue', isRemote=False)]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].remote_status == 'UNKNOWN'


def test_conflicting_isremote_and_workplace_type_prefers_documented_enum(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(workplaceType='Hybrid', isRemote=True)]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].remote_status == 'Hybrid'


# ---- validation ----

def test_malformed_row_missing_title_is_rejected_not_the_whole_board(monkeypatch):
    good = _job()
    bad = _job(id='other-id')
    del bad['title']
    _install(monkeypatch, {'jobs': [good, bad]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.PARTIAL
    assert batch.completion_reason == CompletionReason.SOME_RECORDS_REJECTED.value


def test_all_malformed_is_failed_not_empty(monkeypatch):
    bad = _job()
    del bad['title']
    _install(monkeypatch, {'jobs': [bad]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.health == SourceHealth.MALFORMED
    assert batch.error.code == 'ALL_RECORDS_REJECTED'


def test_malformed_url_does_not_raise(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(jobUrl='https://[', applyUrl='https://[')]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')  # must not raise
    assert batch.records == []


def test_malformed_description_type_is_flagged_not_crashed(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(descriptionPlain={'nested': True})]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.records[0].description == ''
    assert batch.records[0].raw_fields.get('descriptionPlain_malformed') is True


def test_malformed_published_at_degrades_gracefully(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(publishedAt={'weird': True})]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].posted_at == ''


def test_absent_published_at_stays_missing_not_invented(monkeypatch):
    job = _job()
    del job['publishedAt']
    _install(monkeypatch, {'jobs': [job]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].posted_at == ''


def test_missing_location_is_unknown(monkeypatch):
    job = _job()
    del job['location']
    _install(monkeypatch, {'jobs': [job]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].location == 'UNKNOWN'


def test_mixed_valid_and_malformed_true_empty_and_all_malformed(monkeypatch):
    # mixed
    _install(monkeypatch, {'jobs': [_job(id='a'), {'title': 'ok but no id or url'}]})
    mixed = AshbyProvider().fetch(FetchContext(), 'acme')
    assert len(mixed.records) == 1 and mixed.metrics.records_rejected == 1
    # true empty
    _install(monkeypatch, {'jobs': []})
    empty = AshbyProvider().fetch(FetchContext(), 'acme')
    assert empty.health == SourceHealth.EMPTY


def test_transport_failure_is_failed_and_isolated(monkeypatch):
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json',
                         lambda url, budget, **kw: (_ for _ in ()).throw(t.TransportError('UPSTREAM_ERROR', 'Upstream returned 404')))
    batch = AshbyProvider().fetch(FetchContext(), 'backpack')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.health == SourceHealth.UNAVAILABLE
    assert batch.error.code == 'UPSTREAM_ERROR'


def test_unexpected_top_level_shape_fails_closed(monkeypatch):
    _install(monkeypatch, {'not_jobs': []})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.health == SourceHealth.MALFORMED


def test_invalid_board_rejected_before_any_network_call(monkeypatch):
    calls = []
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda *a, **kw: calls.append(1))
    batch = AshbyProvider().fetch(FetchContext(), '../etc/passwd')
    assert batch.completion == FetchCompletion.FAILED
    assert calls == []


# ---- registry / compatibility ----

def test_registry_resolves_ashby():
    assert registry.get_provider('ashby') is not None


def test_compatibility_carries_real_remote_status_and_source_label(monkeypatch):
    _install(monkeypatch, {'jobs': [_job(workplaceType='Hybrid')]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    items = to_legacy_items(batch)
    assert items[0]['source'] == 'Ashby'
    assert items[0]['remote_status'] == 'Hybrid'


def test_compatibility_raises_on_failed_batch(monkeypatch):
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json',
                         lambda url, budget, **kw: (_ for _ in ()).throw(t.TransportError('UPSTREAM_ERROR', 'Upstream returned 404')))
    batch = AshbyProvider().fetch(FetchContext(), 'backpack')
    with pytest.raises(ProviderFetchFailed) as exc:
        to_legacy_items(batch)
    assert exc.value.error_code == 'UPSTREAM_ERROR'


# ---- Backpack investigation regression (issue #39 audit finding) ----

def test_board_returning_404_is_isolated_typed_failure_not_a_crash(monkeypatch):
    """Regression for the live Backpack/Ashby investigation performed
    during the #39 audit: the board slug returns a genuine upstream 404
    (verified live against the real Ashby API), which is a stale source
    configuration, not an ASTRA bug. This proves the migrated provider
    turns that into a clean, typed, isolated failure -- FAILED/UNAVAILABLE
    with error code UPSTREAM_ERROR -- instead of the generic uncaught
    httpx.HTTPStatusError the legacy adapters.py path raised (visible in
    the live UI as 'Source request failed (HTTPStatusError)').
    """
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json',
                         lambda url, budget, **kw: (_ for _ in ()).throw(t.TransportError('UPSTREAM_ERROR', 'Upstream returned 404')))
    batch = AshbyProvider().fetch(FetchContext(), 'backpack')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.health == SourceHealth.UNAVAILABLE
    assert batch.error.code == 'UPSTREAM_ERROR'
    assert batch.records == []

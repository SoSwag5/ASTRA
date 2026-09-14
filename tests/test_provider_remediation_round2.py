"""Regression coverage for the PR #55 independent (Codex) review round on
issue #39: six findings against the Lever/Ashby provider migration.

Finding 1 (HIGH): a malformed provider URL (credentials embedded) used to
pass provider-native validation, then blow up inside
backend.services.add_job() and roll back every other valid job in that
same source's run.

Finding 2 (HIGH): Lever pagination bounds/cycle protection -- a record
cap enforced too late, and cycle detection that only compared the
immediately previous page.

Finding 3 (HIGH): the source Budget/deadline did not cover per-record
transformation (only transport requests), so a fetch could return
COMPLETE/HEALTHY after its own deadline had already passed.

Finding 4 (MEDIUM): the compatibility seam mapped legacy job_url from
apply_url instead of source_url, changing "open original posting"
behavior for Lever/Ashby.

Finding 6 (MEDIUM): Ashby's URL-based fallback identity was not
canonicalized, so the same posting reached via different tracking query
parameters or a fragment produced different identities.

(Finding 5 -- Lever createdAt must never populate date_posted -- has its
dedicated regression coverage in tests/test_lever_provider.py, next to
the rest of Lever's createdAt-provenance tests.)
"""
import os
import subprocess
import sys

import pytest

from backend.job_providers.ashby import AshbyProvider
from backend.job_providers.compatibility import to_legacy_items
from backend.job_providers.contracts import CompletionReason, FetchCompletion, FetchContext, SourceHealth
from backend.job_providers.greenhouse import GreenhouseProvider
from backend.job_providers.lever import LeverProvider, LEVER_MAX_PAGES, LEVER_MAX_RECORDS, LEVER_PAGE_SIZE
from backend.job_providers import transport as t

pytestmark = pytest.mark.usefixtures('no_unexpected_network')


# =====================================================================
# Finding 1: malformed URL must never roll back a valid sibling record
# =====================================================================

def _lever_posting(id_, **overrides):
    base = {'id': id_, 'text': f'Role {id_}', 'hostedUrl': f'https://jobs.lever.co/acme/{id_}',
            'categories': {'location': 'Dubai'}, 'description': 'SIEM'}
    base.update(overrides)
    return base


def _ashby_job(id_, **overrides):
    base = {'id': id_, 'title': f'Role {id_}', 'jobUrl': f'https://jobs.ashbyhq.com/acme/{id_}',
            'location': 'Dubai'}
    base.update(overrides)
    return base


def test_lever_credentialed_url_rejected_not_accepted(monkeypatch):
    good = _lever_posting('1')
    bad = _lever_posting('2', hostedUrl='https://user:pass@jobs.lever.co/acme/2')
    monkeypatch.setattr('backend.job_providers.lever.fetch_json', lambda url, budget, **kw: [good, bad])
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.records[0].provider_job_id == '1'
    assert batch.metrics.records_rejected == 1
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.PARTIAL


def test_ashby_credentialed_url_rejected_not_accepted(monkeypatch):
    good = _ashby_job('1')
    bad = _ashby_job('2', jobUrl='https://user:pass@jobs.ashbyhq.com/acme/2', applyUrl='https://user:pass@jobs.ashbyhq.com/acme/2')
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [good, bad]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.records[0].provider_job_id == '1'
    assert batch.metrics.records_rejected == 1


def test_lever_all_credentialed_is_failed_not_empty(monkeypatch):
    bad = _lever_posting('1', hostedUrl='https://user:pass@jobs.lever.co/acme/1')
    monkeypatch.setattr('backend.job_providers.lever.fetch_json', lambda url, budget, **kw: [bad])
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.error.code == 'ALL_RECORDS_REJECTED'


def _isolated(tmp_path, script):
    data = tmp_path / 'data'
    env = {**os.environ, 'HUNTER_DATA_DIR': str(data), 'DATABASE_URL': f'sqlite:///{data / "isolated.db"}', 'APP_TOKEN': ''}
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=env, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_lever_orchestration_mixed_record_commits_valid_job(tmp_path):
    """Real end-to-end reproduction of finding 1 through
    main.task('discover') -> provider -> compatibility -> ingestion: a
    credential-bearing sibling row must never roll back the valid job in
    the same source's run."""
    _isolated(tmp_path, r'''
from backend.models import *
import backend.main as m
import backend.job_providers.lever as lever_mod
initialize()
with Session.begin() as db:
    db.add(JobSource(name='LV', adapter='lever', board='lv-co', enabled=True))
good = {'id':'1','text':'SOC Analyst','hostedUrl':'https://jobs.lever.co/lv-co/1','categories':{'location':'Dubai'},'description':'SIEM'}
bad = {'id':'2','text':'SOC Analyst 2','hostedUrl':'https://user:pass@jobs.lever.co/lv-co/2','categories':{'location':'Dubai'},'description':'SIEM'}
lever_mod.fetch_json = lambda url, budget, **kw: [good, bad]
r = m.task('discover')
assert r['status'] == 'COMPLETED', r
source_report = r['report']['sources'][0]
assert source_report['error'] == '', source_report
assert source_report['imported'] == 1, source_report
assert source_report['metrics']['records_accepted'] == 1
assert source_report['metrics']['records_rejected'] == 1
with Session() as db:
    assert db.query(Job).count() == 1
print('OK')
''')


def test_ashby_orchestration_mixed_record_commits_valid_job(tmp_path):
    _isolated(tmp_path, r'''
from backend.models import *
import backend.main as m
import backend.job_providers.ashby as ashby_mod
initialize()
with Session.begin() as db:
    db.add(JobSource(name='AS', adapter='ashby', board='as-co', enabled=True))
good = {'id':'1','title':'SOC Analyst','jobUrl':'https://jobs.ashbyhq.com/as-co/1','location':'Dubai'}
bad = {'id':'2','title':'SOC Analyst 2','jobUrl':'https://user:pass@jobs.ashbyhq.com/as-co/2','location':'Dubai'}
ashby_mod.fetch_json = lambda url, budget, **kw: {'jobs': [good, bad]}
r = m.task('discover')
assert r['status'] == 'COMPLETED', r
source_report = r['report']['sources'][0]
assert source_report['error'] == '', source_report
assert source_report['imported'] == 1, source_report
with Session() as db:
    assert db.query(Job).count() == 1
print('OK')
''')


# =====================================================================
# Finding 2: Lever pagination bounds / cycle protection
# =====================================================================

def _full_page(seed, n=LEVER_PAGE_SIZE):
    return [_lever_posting(f'{seed}-{i}') for i in range(n)]


def _paged(monkeypatch, pages):
    calls = []

    def fake(url, budget, **kw):
        calls.append(url)
        skip = int(url.split('skip=')[1].split('&')[0])
        result = pages.get(skip, [])
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr('backend.job_providers.lever.fetch_json', fake)
    return calls


def _ids(batch):
    return [r.provider_job_id for r in batch.records]


def test_1_server_ignores_limit_and_returns_over_cap_in_one_response(monkeypatch):
    over_cap = [_lever_posting(str(i)) for i in range(LEVER_MAX_RECORDS + 200)]
    _paged(monkeypatch, {0: over_cap})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == LEVER_MAX_RECORDS
    assert len(set(_ids(batch))) == LEVER_MAX_RECORDS
    assert batch.completion == FetchCompletion.PARTIAL
    assert batch.completion_reason == CompletionReason.PAGINATION_LIMIT_REACHED.value


def test_2_exactly_max_records_in_one_response(monkeypatch):
    exact = [_lever_posting(str(i)) for i in range(LEVER_MAX_RECORDS)]
    _paged(monkeypatch, {0: exact})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == LEVER_MAX_RECORDS
    assert len(set(_ids(batch))) == LEVER_MAX_RECORDS


def test_3_max_plus_one_in_one_response(monkeypatch):
    over = [_lever_posting(str(i)) for i in range(LEVER_MAX_RECORDS + 1)]
    _paged(monkeypatch, {0: over})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == LEVER_MAX_RECORDS
    assert batch.completion == FetchCompletion.PARTIAL


def test_4_a_b_a_non_consecutive_cycle_stops_and_deduplicates(monkeypatch):
    page_a = _full_page('a')
    page_b = _full_page('b')
    calls = _paged(monkeypatch, {0: page_a, LEVER_PAGE_SIZE: page_b, LEVER_PAGE_SIZE * 2: page_a, LEVER_PAGE_SIZE * 3: []})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 3  # never reaches the trailing empty page
    assert len(batch.records) == LEVER_PAGE_SIZE * 2
    assert len(set(_ids(batch))) == LEVER_PAGE_SIZE * 2
    assert batch.completion == FetchCompletion.PARTIAL
    assert batch.completion_reason == CompletionReason.PAGINATION_LIMIT_REACHED.value


def test_5_immediate_repeat_a_a(monkeypatch):
    page_a = _full_page('a')
    calls = _paged(monkeypatch, {0: page_a, LEVER_PAGE_SIZE: page_a})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 2
    assert len(batch.records) == LEVER_PAGE_SIZE
    assert len(set(_ids(batch))) == LEVER_PAGE_SIZE


def test_6_pages_with_partial_overlap_deduplicate_correctly(monkeypatch):
    page1 = [_lever_posting(str(i)) for i in range(100)]
    page2 = [_lever_posting(str(i)) for i in range(50, 150)]  # 50 overlap + 50 new
    _paged(monkeypatch, {0: page1, LEVER_PAGE_SIZE: page2})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 150
    assert len(set(_ids(batch))) == 150


def test_7_page_containing_only_already_seen_records_stops(monkeypatch):
    page1 = [_lever_posting(str(i)) for i in range(100)]
    subset_repeat = [_lever_posting(str(i)) for i in range(0, 30)]  # pure subset of page1
    calls = _paged(monkeypatch, {0: page1, LEVER_PAGE_SIZE: subset_repeat})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 2
    assert len(batch.records) == 100
    assert batch.completion == FetchCompletion.PARTIAL


def test_8_final_short_page_terminates_normally(monkeypatch):
    page1 = _full_page('a')
    page2 = [_lever_posting(f'b-{i}') for i in range(10)]
    calls = _paged(monkeypatch, {0: page1, LEVER_PAGE_SIZE: page2})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 2
    assert len(batch.records) == LEVER_PAGE_SIZE + 10
    assert batch.completion == FetchCompletion.COMPLETE
    assert batch.health == SourceHealth.HEALTHY


def test_9_legitimate_multi_page_board(monkeypatch):
    pages = {LEVER_PAGE_SIZE * i: [_lever_posting(f'{i}-{j}') for j in range(LEVER_PAGE_SIZE)] for i in range(3)}
    pages[LEVER_PAGE_SIZE * 3] = [_lever_posting('final-1')]
    calls = _paged(monkeypatch, pages)
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 4
    assert len(batch.records) == LEVER_PAGE_SIZE * 3 + 1
    assert batch.completion == FetchCompletion.COMPLETE


def test_10_later_page_transport_failure_preserves_earlier_pages(monkeypatch):
    page1 = _full_page('a')
    _paged(monkeypatch, {0: page1, LEVER_PAGE_SIZE: t.TransportError('READ_TIMEOUT', 'Read timed out')})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == LEVER_PAGE_SIZE
    assert batch.completion == FetchCompletion.PARTIAL
    assert batch.error.code == 'READ_TIMEOUT'


def test_records_never_exceed_cap_and_ids_always_unique_property(monkeypatch):
    """General property check across several shapes."""
    for pages in (
        {0: [_lever_posting(str(i)) for i in range(LEVER_MAX_RECORDS + 500)]},
        {0: _full_page('a'), LEVER_PAGE_SIZE: _full_page('a'), LEVER_PAGE_SIZE * 2: _full_page('b')},
    ):
        _paged(monkeypatch, pages)
        batch = LeverProvider().fetch(FetchContext(), 'acme')
        assert len(batch.records) <= LEVER_MAX_RECORDS
        ids = _ids(batch)
        assert len(ids) == len(set(ids))


# =====================================================================
# Finding 3: source deadline must cover per-record transformation
# =====================================================================

def _slow_clean(monkeypatch, delay, after=0):
    import backend.adapters as adapters_mod
    real_clean = adapters_mod.clean
    count = {'n': 0}

    def fake(s):
        count['n'] += 1
        if count['n'] > after:
            import time
            time.sleep(delay)
        return real_clean(s)

    monkeypatch.setattr(adapters_mod, 'clean', fake)


def test_lever_deadline_expiry_during_first_record_transformation_is_failed(monkeypatch):
    _slow_clean(monkeypatch, 0.03)
    monkeypatch.setattr('backend.job_providers.lever.fetch_json', lambda url, budget, **kw: [_lever_posting('1')])
    batch = LeverProvider().fetch(FetchContext(deadline_seconds=0.005), 'acme')
    assert batch.completion != FetchCompletion.COMPLETE
    assert batch.records == []


def test_lever_deadline_expiry_after_several_records_is_partial(monkeypatch):
    _slow_clean(monkeypatch, 0.05, after=3)
    rows = [_lever_posting(str(i)) for i in range(10)]
    monkeypatch.setattr('backend.job_providers.lever.fetch_json', lambda url, budget, **kw: rows)
    batch = LeverProvider().fetch(FetchContext(deadline_seconds=0.04), 'acme')
    assert batch.completion == FetchCompletion.PARTIAL
    assert 0 < len(batch.records) < 10
    assert batch.error.code == 'DEADLINE_EXCEEDED'


def test_lever_deadline_already_expired_before_first_record_is_failed(monkeypatch):
    monkeypatch.setattr('backend.job_providers.lever.fetch_json', lambda url, budget, **kw: [_lever_posting('1')])
    batch = LeverProvider().fetch(FetchContext(deadline_seconds=0.0), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.records == []


def _slow_string_field(monkeypatch, delay, after=0):
    """Ashby has no HTML-cleaning step; simulate expensive per-record
    transformation the same way finding 3 was reported -- a slow step
    inside per-record processing."""
    import backend.job_providers.ashby as ashby_mod
    real = ashby_mod._to_record
    count = {'n': 0}

    def fake(row, source_board, retrieved_at):
        count['n'] += 1
        if count['n'] > after:
            import time
            time.sleep(delay)
        return real(row, source_board, retrieved_at)

    monkeypatch.setattr(ashby_mod, '_to_record', fake)


def test_ashby_deadline_expiry_during_first_record_transformation_is_failed(monkeypatch):
    _slow_string_field(monkeypatch, 0.03)
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [_ashby_job('1')]})
    batch = AshbyProvider().fetch(FetchContext(deadline_seconds=0.005), 'acme')
    assert batch.completion != FetchCompletion.COMPLETE
    assert batch.records == []


def test_ashby_deadline_expiry_after_several_records_is_partial(monkeypatch):
    _slow_string_field(monkeypatch, 0.05, after=3)
    rows = {'jobs': [_ashby_job(str(i)) for i in range(10)]}
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: rows)
    batch = AshbyProvider().fetch(FetchContext(deadline_seconds=0.04), 'acme')
    assert batch.completion == FetchCompletion.PARTIAL
    assert 0 < len(batch.records) < 10
    assert batch.error.code == 'DEADLINE_EXCEEDED'


def test_ashby_deadline_already_expired_before_first_record_is_failed(monkeypatch):
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [_ashby_job('1')]})
    batch = AshbyProvider().fetch(FetchContext(deadline_seconds=0.0), 'acme')
    assert batch.completion == FetchCompletion.FAILED
    assert batch.records == []


# =====================================================================
# Finding 4: legacy job_url must be source_url, not apply_url
# =====================================================================

def test_greenhouse_job_url_is_source_url(monkeypatch):
    payload = {'jobs': [{'id': 1, 'title': 'A', 'absolute_url': 'https://x/1', 'location': {'name': 'Dubai'}, 'content': ''}]}
    monkeypatch.setattr('backend.job_providers.greenhouse.fetch_json', lambda url, budget, **kw: payload)
    batch = GreenhouseProvider().fetch(FetchContext(), 'acme')
    items = to_legacy_items(batch)
    assert items[0]['job_url'] == batch.records[0].source_url == batch.records[0].apply_url  # Greenhouse: same value either way


def test_lever_job_url_is_hosted_url_not_apply_url(monkeypatch):
    posting = _lever_posting('1', applyUrl='https://jobs.lever.co/acme/1/apply')
    monkeypatch.setattr('backend.job_providers.lever.fetch_json', lambda url, budget, **kw: [posting])
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    items = to_legacy_items(batch)
    assert items[0]['job_url'] == posting['hostedUrl']
    assert items[0]['job_url'] != posting['applyUrl']
    assert batch.records[0].apply_url == posting['applyUrl']


def test_ashby_job_url_is_job_url_not_apply_url(monkeypatch):
    job = _ashby_job('1', applyUrl='https://jobs.ashbyhq.com/acme/1/application')
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [job]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    items = to_legacy_items(batch)
    assert items[0]['job_url'] == job['jobUrl']
    assert items[0]['job_url'] != job['applyUrl']
    assert batch.records[0].apply_url == job['applyUrl']


# =====================================================================
# Finding 6: Ashby fallback identity must be canonicalized
# =====================================================================

def test_same_url_differing_only_query_yields_same_identity(monkeypatch):
    j1 = _ashby_job('x', jobUrl='https://jobs.ashbyhq.com/acme/abc?utm_source=a')
    del j1['id']
    j2 = _ashby_job('x', jobUrl='https://jobs.ashbyhq.com/acme/abc?utm_source=b&ref=c')
    del j2['id']
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j1]})
    b1 = AshbyProvider().fetch(FetchContext(), 'acme')
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j2]})
    b2 = AshbyProvider().fetch(FetchContext(), 'acme')
    assert b1.records[0].provider_job_id == b2.records[0].provider_job_id


def test_same_url_differing_only_fragment_yields_same_identity(monkeypatch):
    j1 = _ashby_job('x', jobUrl='https://jobs.ashbyhq.com/acme/abc#section1')
    del j1['id']
    j2 = _ashby_job('x', jobUrl='https://jobs.ashbyhq.com/acme/abc#section2')
    del j2['id']
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j1]})
    b1 = AshbyProvider().fetch(FetchContext(), 'acme')
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j2]})
    b2 = AshbyProvider().fetch(FetchContext(), 'acme')
    assert b1.records[0].provider_job_id == b2.records[0].provider_job_id


def test_scheme_and_host_case_normalized(monkeypatch):
    j1 = _ashby_job('x', jobUrl='HTTPS://Jobs.AshbyHQ.com/acme/abc')
    del j1['id']
    j2 = _ashby_job('x', jobUrl='https://jobs.ashbyhq.com/acme/abc')
    del j2['id']
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j1]})
    b1 = AshbyProvider().fetch(FetchContext(), 'acme')
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j2]})
    b2 = AshbyProvider().fetch(FetchContext(), 'acme')
    assert b1.records[0].provider_job_id == b2.records[0].provider_job_id


def test_different_path_yields_different_identity(monkeypatch):
    j1 = _ashby_job('x', jobUrl='https://jobs.ashbyhq.com/acme/abc')
    del j1['id']
    j2 = _ashby_job('x', jobUrl='https://jobs.ashbyhq.com/acme/xyz')
    del j2['id']
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j1]})
    b1 = AshbyProvider().fetch(FetchContext(), 'acme')
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j2]})
    b2 = AshbyProvider().fetch(FetchContext(), 'acme')
    assert b1.records[0].provider_job_id != b2.records[0].provider_job_id


def test_malformed_fallback_url_is_rejected(monkeypatch):
    j = _ashby_job('x', jobUrl='not-a-url')
    del j['id']
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_original_source_url_preserved_exactly_for_navigation(monkeypatch):
    original = 'https://jobs.ashbyhq.com/acme/abc?utm_source=x#foo'
    j = _ashby_job('x', jobUrl=original)
    del j['id']
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].source_url == original  # untouched -- canonicalization only affects the derived identity
    assert batch.records[0].provider_job_id != original  # the identity IS canonicalized


def test_native_id_takes_precedence_over_url_fallback(monkeypatch):
    j = _ashby_job('native-id-123', jobUrl='https://jobs.ashbyhq.com/acme/abc?utm_source=x')
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': [j]})
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records[0].provider_job_id == 'native-id-123'
    assert 'identity_fallback' not in batch.records[0].raw_fields

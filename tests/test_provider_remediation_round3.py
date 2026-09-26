"""Regression coverage for the second independent (Codex) retest round on
PR #55 / issue #39: two remaining HIGH blockers.

Blocker A: an Ashby row with a valid native id and a credential-bearing
(or otherwise downstream-invalid) jobUrl was still accepted, with
applyUrl silently substituted as source_url -- the row must instead be
rejected outright; a native id or a valid applyUrl never excuses an
invalid jobUrl.

Blocker B: Lever pagination deduplicated on the RAW native id (e.g.
integer 1 and string '1' are distinct as raw values/set members), while
the final ProviderRecord.provider_job_id stringified both to '1' --
producing two accepted records that collide on identity, violating
provider-local uniqueness.
"""
import os
import subprocess
import sys

import pytest

from backend.job_providers.ashby import AshbyProvider
from backend.job_providers.compatibility import to_legacy_items
from backend.job_providers.contracts import FetchCompletion, FetchContext, SourceHealth
from backend.job_providers.lever import LeverProvider, LEVER_MAX_PAGES, LEVER_MAX_RECORDS, LEVER_PAGE_SIZE

pytestmark = pytest.mark.usefixtures('no_unexpected_network')


def _isolated(tmp_path, script):
    data = tmp_path / 'data'
    env = {**os.environ, 'HUNTER_DATA_DIR': str(data), 'DATABASE_URL': f'sqlite:///{data / "isolated.db"}', 'APP_TOKEN': ''}
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=env, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


# =====================================================================
# BLOCKER A -- Ashby: invalid jobUrl must never be replaced by applyUrl
# =====================================================================

def _job(**overrides):
    base = {'id': 'native-1', 'title': 'Role', 'jobUrl': 'https://jobs.ashbyhq.com/acme/1',
            'applyUrl': 'https://jobs.ashbyhq.com/acme/1/apply'}
    base.update(overrides)
    return base


def _install(monkeypatch, jobs):
    monkeypatch.setattr('backend.job_providers.ashby.fetch_json', lambda url, budget, **kw: {'jobs': jobs})


def test_ashby_1_credentialed_joburl_with_valid_apply_url_is_rejected(monkeypatch):
    """THE REVIEWER'S EXACT REPRO."""
    job = _job(jobUrl='https://user:pass@jobs.ashbyhq.com/acme/1')
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []
    assert batch.completion == FetchCompletion.FAILED
    assert batch.error.code == 'ALL_RECORDS_REJECTED'


def test_ashby_2_joburl_unsupported_scheme_with_valid_apply_url_is_rejected(monkeypatch):
    job = _job(jobUrl='ftp://jobs.ashbyhq.com/acme/1')
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_ashby_3_joburl_missing_hostname_with_valid_apply_url_is_rejected(monkeypatch):
    job = _job(jobUrl='https:///acme/1')
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_ashby_4_valid_joburl_and_valid_applyurl_is_accepted(monkeypatch):
    job = _job()
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.records[0].source_url == job['jobUrl']
    assert batch.records[0].apply_url == job['applyUrl']


def test_ashby_5_valid_joburl_absent_applyurl_falls_back_to_source_url(monkeypatch):
    job = _job()
    del job['applyUrl']
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.records[0].apply_url == batch.records[0].source_url == job['jobUrl']


def test_ashby_6_native_id_absent_tracking_query_and_fragment_stable_identity(monkeypatch):
    job = _job(jobUrl='https://jobs.ashbyhq.com/acme/1?utm_source=x#foo')
    del job['id']
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    r = batch.records[0]
    assert r.provider_job_id == 'https://jobs.ashbyhq.com/acme/1'  # canonicalized
    assert r.source_url == job['jobUrl']  # ORIGINAL, uncanonicalized, unchanged
    assert r.raw_fields.get('identity_fallback') == 'jobUrl'


def test_ashby_7_orchestration_mixed_valid_and_invalid_joburl_commits_valid(tmp_path):
    _isolated(tmp_path, r'''
from backend.models import *
import backend.main as m
from tests.scan_harness import confirmed_discover
import backend.job_providers.ashby as ashby_mod
initialize()
with Session.begin() as db:
    db.add(JobSource(name='AS', adapter='ashby', board='as-co', enabled=True))
good = {'id':'1','title':'SOC Analyst','jobUrl':'https://jobs.ashbyhq.com/as-co/1','location':'Dubai'}
bad = {'id':'2','title':'SOC Analyst 2','jobUrl':'https://user:pass@jobs.ashbyhq.com/as-co/2','applyUrl':'https://jobs.ashbyhq.com/as-co/2/apply','location':'Dubai'}
ashby_mod.fetch_json = lambda url, budget, **kw: {'jobs': [good, bad]}
r = confirmed_discover()
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


def test_ashby_8_legacy_job_url_is_original_joburl_not_applyurl(monkeypatch):
    job = _job()
    assert job['jobUrl'] != job['applyUrl']
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    items = to_legacy_items(batch)
    assert items[0]['job_url'] == job['jobUrl']
    assert items[0]['job_url'] != job['applyUrl']


def test_ashby_invalid_joburl_missing_native_id_is_rejected(monkeypatch):
    job = _job(jobUrl='https://user:pass@jobs.ashbyhq.com/acme/1')
    del job['id']
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_ashby_over_length_joburl_is_rejected(monkeypatch):
    job = _job(jobUrl='https://jobs.ashbyhq.com/acme/' + 'a' * 2000)
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')
    assert batch.records == []


def test_ashby_malformed_row_does_not_crash_source(monkeypatch):
    job = _job(jobUrl='https://user:pass@jobs.ashbyhq.com/acme/1')
    _install(monkeypatch, [job])
    batch = AshbyProvider().fetch(FetchContext(), 'acme')  # must not raise
    assert batch.completion == FetchCompletion.FAILED
    assert batch.health == SourceHealth.MALFORMED


# =====================================================================
# BLOCKER B -- Lever: id normalization must be consistent everywhere
# =====================================================================

def _posting(id_, **overrides):
    base = {'id': id_, 'text': f'Role {id_}', 'hostedUrl': f'https://jobs.lever.co/acme/{id_}',
            'categories': {'location': 'Dubai'}}
    base.update(overrides)
    return base


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


def _assert_unique(batch):
    ids = [r.provider_job_id for r in batch.records]
    assert len(set(ids)) == len(ids), f'duplicate provider_job_id values: {ids}'


def test_lever_1_int_and_string_same_page_dedupe_to_one_record(monkeypatch):
    """THE REVIEWER'S EXACT REPRO."""
    row_int = _posting(1)
    row_str = _posting('1', hostedUrl='https://jobs.lever.co/acme/str1')
    _paged(monkeypatch, {0: [row_int, row_str]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    _assert_unique(batch)


def test_lever_2_int_page1_string_page2_dedupe_to_one_identity(monkeypatch):
    fillers = [_posting(f'filler-{i}') for i in range(LEVER_PAGE_SIZE - 1)]
    page1 = [_posting(1)] + fillers
    page2 = [_posting('1', hostedUrl='https://jobs.lever.co/acme/dup')]  # duplicate of page1's int id
    _paged(monkeypatch, {0: page1, LEVER_PAGE_SIZE: page2})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == LEVER_PAGE_SIZE  # the cross-page duplicate contributes nothing new
    _assert_unique(batch)


def test_lever_3_duplicate_normalized_id_plus_unique_record_retained(monkeypatch):
    row_int = _posting(1)
    row_str_dup = _posting('1', hostedUrl='https://jobs.lever.co/acme/dup')
    row_unique = _posting('2')
    _paged(monkeypatch, {0: [row_int, row_str_dup, row_unique]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 2
    _assert_unique(batch)
    assert {r.provider_job_id for r in batch.records} == {'1', '2'}


def test_lever_4_malformed_composite_id_is_rejected_not_crashed(monkeypatch):
    for bad_id in ({'nested': 1}, [1, 2], None, 1.5, True):
        row = _posting(1)
        row['id'] = bad_id
        _paged(monkeypatch, {0: [row]})
        batch = LeverProvider().fetch(FetchContext(), 'acme')  # must not raise
        assert batch.records == [], f'bad_id={bad_id!r} was incorrectly accepted'


def test_lever_5_normal_documented_string_ids_unchanged(monkeypatch):
    row = _posting('abc-123-def')
    _paged(monkeypatch, {0: [row]})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == 1
    assert batch.records[0].provider_job_id == 'abc-123-def'


def test_lever_6_a_b_a_cycle_still_bounded_and_unique_with_normalization(monkeypatch):
    page_a = [_posting(f'a-{i}') for i in range(LEVER_PAGE_SIZE)]
    page_b = [_posting(f'b-{i}') for i in range(LEVER_PAGE_SIZE)]
    calls = _paged(monkeypatch, {0: page_a, LEVER_PAGE_SIZE: page_b, LEVER_PAGE_SIZE * 2: page_a})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(calls) == 3
    assert len(batch.records) == LEVER_PAGE_SIZE * 2
    _assert_unique(batch)
    assert batch.completion == FetchCompletion.PARTIAL


def test_lever_7_over_cap_response_stays_within_cap_and_unique(monkeypatch):
    over_cap = [_posting(i) for i in range(LEVER_MAX_RECORDS + 200)]
    _paged(monkeypatch, {0: over_cap})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == LEVER_MAX_RECORDS
    _assert_unique(batch)
    assert batch.completion == FetchCompletion.PARTIAL


def test_lever_int_and_string_mixed_with_pagination_cap_stays_unique(monkeypatch):
    """Combines Blocker B's id-type mixing with Blocker/Finding 2's cap
    enforcement, to make sure the two fixes compose correctly."""
    page1 = [_posting(i) for i in range(LEVER_PAGE_SIZE)]  # ints 0..99
    page2 = [_posting(str(i)) for i in range(50, LEVER_PAGE_SIZE + 50)]  # strings '50'..'149' -- 50 overlap with page1
    _paged(monkeypatch, {0: page1, LEVER_PAGE_SIZE: page2})
    batch = LeverProvider().fetch(FetchContext(), 'acme')
    assert len(batch.records) == LEVER_PAGE_SIZE + 50  # 100 + (150-100) new
    _assert_unique(batch)

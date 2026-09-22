"""Cross-provider contract and failure-isolation tests (issue #39).

Proves Greenhouse, Lever and Ashby all sit behind the same Provider
contract and shared transport (no provider does its own direct HTTP,
none imports ranking/recall/eligibility logic), and -- through the real
backend.main discover orchestration, not a reimplementation of it -- that
one provider's failure never rolls back, hides, or corrupts another's
results or telemetry, in either permutation order.
"""
import inspect
import os
import subprocess
import sys

import pytest

from backend.job_providers.ashby import AshbyProvider
from backend.job_providers.greenhouse import GreenhouseProvider
from backend.job_providers.lever import LeverProvider
from backend.job_providers.contracts import Provider

pytestmark = pytest.mark.usefixtures('no_unexpected_network')

PROVIDERS = {'greenhouse': GreenhouseProvider, 'lever': LeverProvider, 'ashby': AshbyProvider}


def test_all_three_providers_implement_the_same_base_contract():
    for provider_cls in PROVIDERS.values():
        assert issubclass(provider_cls, Provider)


def test_no_provider_module_imports_ranking_or_recall_logic():
    import backend.job_providers.ashby as ashby_mod
    import backend.job_providers.greenhouse as gh_mod
    import backend.job_providers.lever as lever_mod
    for mod in (gh_mod, lever_mod, ashby_mod):
        source = inspect.getsource(mod)
        assert 'recall' not in source
        assert 'import evaluate' not in source and 'from ..services' not in source


def test_no_provider_module_uses_httpx_directly():
    """Every provider must go through backend.job_providers.transport's
    fetch_json rather than inventing its own httpx.Client call."""
    import backend.job_providers.ashby as ashby_mod
    import backend.job_providers.greenhouse as gh_mod
    import backend.job_providers.lever as lever_mod
    for mod in (gh_mod, lever_mod, ashby_mod):
        source = inspect.getsource(mod)
        assert 'httpx' not in source
        assert 'fetch_json' in source


def _isolated(tmp_path, script):
    data = tmp_path / 'data'
    env = {**os.environ, 'HUNTER_DATA_DIR': str(data), 'DATABASE_URL': f'sqlite:///{data / "isolated.db"}', 'APP_TOKEN': ''}
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=env, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_one_provider_failure_does_not_affect_others_first_permutation(tmp_path):
    _isolated(tmp_path, r'''
from backend.models import *
import backend.main as m
from tests.scan_harness import confirmed_discover
initialize()
with Session.begin() as db:
    db.add(JobSource(name='GH', adapter='greenhouse', board='gh-co', enabled=True))
    db.add(JobSource(name='LV', adapter='lever', board='lv-co', enabled=True))
    db.add(JobSource(name='AS', adapter='ashby', board='as-co', enabled=True))

def fake_discover(adapter, board, url='', cfg=None):
    # Title must be an eligible target role (matches DEFAULTS.target_roles)
    # so the job survives recall/eligibility filtering and this test is
    # actually checking failure isolation, not incidentally re-testing
    # role-relevance filtering.
    if adapter == 'greenhouse':
        return [{'title': 'SOC Analyst', 'company': board, 'location': 'Dubai', 'description': 'SIEM', 'job_url': 'https://x/gh1', 'source': 'Greenhouse'}]
    if adapter == 'lever':
        raise ValueError('Source unavailable')
    if adapter == 'ashby':
        return [{'title': 'SOC Analyst', 'company': board, 'location': 'Dubai', 'description': 'SIEM', 'job_url': 'https://x/as1', 'source': 'Ashby'}]
    raise AssertionError('unexpected adapter')

m.discover = fake_discover
r = confirmed_discover()
assert r['status'] == 'PARTIAL', r
by_name = {s['name']: s for s in r['report']['sources']}
assert by_name['GH']['error'] == '' and by_name['GH']['imported'] == 1, by_name['GH']
assert by_name['AS']['error'] == '' and by_name['AS']['imported'] == 1, by_name['AS']
assert by_name['LV']['error'] != '' and by_name['LV']['imported'] == 0, by_name['LV']
with Session() as db:
    names = {j.company for j in db.query(Job).all()}
    assert names == {'GH', 'AS'}, names
''')


def test_one_provider_failure_does_not_affect_others_second_permutation(tmp_path):
    """Same as above with a different failing provider, to rule out an
    ordering-dependent isolation bug."""
    _isolated(tmp_path, r'''
from backend.models import *
import backend.main as m
from tests.scan_harness import confirmed_discover
initialize()
with Session.begin() as db:
    db.add(JobSource(name='GH', adapter='greenhouse', board='gh-co', enabled=True))
    db.add(JobSource(name='LV', adapter='lever', board='lv-co', enabled=True))
    db.add(JobSource(name='AS', adapter='ashby', board='as-co', enabled=True))

def fake_discover(adapter, board, url='', cfg=None):
    if adapter == 'greenhouse':
        raise ValueError('Source unavailable')
    if adapter == 'lever':
        return [{'title': 'SOC Analyst', 'company': board, 'location': 'Dubai', 'description': 'SIEM', 'job_url': 'https://x/lv1', 'source': 'Lever'}]
    if adapter == 'ashby':
        return [{'title': 'SOC Analyst', 'company': board, 'location': 'Dubai', 'description': 'SIEM', 'job_url': 'https://x/as1', 'source': 'Ashby'}]
    raise AssertionError('unexpected adapter')

m.discover = fake_discover
r = confirmed_discover()
assert r['status'] == 'PARTIAL', r
by_name = {s['name']: s for s in r['report']['sources']}
assert by_name['GH']['error'] != '' and by_name['GH']['imported'] == 0, by_name['GH']
assert by_name['LV']['error'] == '' and by_name['LV']['imported'] == 1, by_name['LV']
assert by_name['AS']['error'] == '' and by_name['AS']['imported'] == 1, by_name['AS']
with Session() as db:
    names = {j.company for j in db.query(Job).all()}
    assert names == {'LV', 'AS'}, names
''')

"""The fictional page replay must actually exercise its selected polling mode."""

import os
import socket
import subprocess
import sys

from scripts import perf_discovery_poll as perf


def test_old_and_new_page_replays_request_different_work(tmp_path, monkeypatch):
    fixture = tmp_path / 'fictional-load'
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    subprocess.run(
        [sys.executable, '-c',
         'from scripts.perf_discovery_poll import build; import sys; '
         'build(sys.argv[1], jobs=12, runs=3, heavy_runs=1, heavy_decisions=3, light_decisions=1)',
         str(fixture)],
        cwd=perf.ROOT, env=env, check=True, timeout=90,
    )
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        monkeypatch.setattr(perf, 'PORT', sock.getsockname()[1])

    options = {'seconds': 0.7, 'act_at': 999, 'sequential_reps': 1, 'poll_interval': 0.3}
    old = perf.measure(fixture / 'data', perf.ROOT, client='old', **options)['page']
    new = perf.measure(fixture / 'data', perf.ROOT, client='new', **options)['page']

    assert old['rounds_started'] >= 2
    assert old['rounds_skipped'] == 0
    assert old['request_counts']['/api/jobs'] == old['rounds_completed']
    assert new['rounds_started'] >= 2
    assert new['request_counts']['/api/jobs'] == 1
    assert new['peak_rounds_in_flight'] == 1

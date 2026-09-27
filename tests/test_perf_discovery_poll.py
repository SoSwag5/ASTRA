"""The fictional page replay must actually exercise its selected polling mode."""

import os
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from scripts import perf_discovery_poll as perf


def test_old_and_new_page_replays_request_different_work(tmp_path):
    fixture = tmp_path / 'fictional-load'
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    subprocess.run(
        [sys.executable, '-c',
         'from scripts.perf_discovery_poll import build; import sys; '
         'build(sys.argv[1], jobs=12, runs=3, heavy_runs=1, heavy_decisions=3, light_decisions=1)',
         str(fixture)],
        cwd=perf.ROOT, env=env, check=True, timeout=90,
    )
    options = {'seconds': 0.7, 'act_at': 999, 'sequential_reps': 1, 'poll_interval': 0.3}
    old = perf.measure(fixture / 'data', perf.ROOT, client='old', **options)['page']
    new = perf.measure(fixture / 'data', perf.ROOT, client='new', **options)['page']

    assert old['rounds_started'] >= 2
    assert old['rounds_skipped'] == 0
    assert old['request_counts']['/api/jobs'] == old['rounds_completed']
    assert new['rounds_started'] >= 2
    assert new['request_counts']['/api/jobs'] == 1
    assert new['peak_rounds_in_flight'] == 1


def test_replay_refuses_an_unrelated_service_on_its_selected_port(tmp_path, monkeypatch):
    """A port collision must never make the harness use or stop another process."""
    class UnrelatedService(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({'ok': True, 'pid': os.getpid(), 'build': 'unrelated'}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    class LaunchedProcess:
        pid = os.getpid() + 12345
        terminated = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert self.terminated
            return 0

    unrelated = HTTPServer(('127.0.0.1', 0), UnrelatedService)
    thread = threading.Thread(target=unrelated.serve_forever, daemon=True)
    thread.start()
    launched = LaunchedProcess()
    monkeypatch.setattr(perf, '_free_loopback_port', lambda: unrelated.server_port)
    monkeypatch.setattr(perf.subprocess, 'Popen', lambda *_args, **_kwargs: launched)
    try:
        with pytest.raises(RuntimeError, match='different process'):
            perf.start_server(perf.ROOT, tmp_path / 'data')
        assert launched.terminated
        assert httpx.get(f'http://127.0.0.1:{unrelated.server_port}/api/health').json()['build'] == 'unrelated'
    finally:
        unrelated.shutdown()
        unrelated.server_close()
        thread.join(timeout=5)


def test_replay_refuses_a_failed_pause_action(tmp_path, monkeypatch):
    fixture = tmp_path / 'fictional-load'
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    subprocess.run(
        [sys.executable, '-c',
         'from scripts.perf_discovery_poll import build; import sys; '
         'build(sys.argv[1], jobs=12, runs=3, heavy_runs=1, heavy_decisions=3, light_decisions=1)',
         str(fixture)],
        cwd=perf.ROOT, env=env, check=True, timeout=90,
    )
    real_post = httpx.Client.post

    def failed_post(client, url, *args, **kwargs):
        if url == '/api/records/sources':
            raise RuntimeError('fictional Pause write failure')
        return real_post(client, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, 'post', failed_post)
    with pytest.raises(RuntimeError, match='Pause action failed'):
        perf.measure(fixture / 'data', perf.ROOT, client='new', seconds=0.7,
                     act_at=0, sequential_reps=1, poll_interval=0.3)


def test_replay_shutdown_closes_its_authenticated_server(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    proc, health, port, nonce = perf.start_server(perf.ROOT, data)
    try:
        assert health['ok'] is True
        assert httpx.get(f'http://127.0.0.1:{port}/__astra_perf_identity').json()['nonce'] == nonce
    finally:
        perf.stop_server(proc, port, nonce)
    with pytest.raises(httpx.RequestError):
        httpx.get(f'http://127.0.0.1:{port}/api/health', timeout=1)

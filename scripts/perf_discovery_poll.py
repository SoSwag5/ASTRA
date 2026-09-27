"""Reproduce and measure Discovery page load on a fictional, isolated database.

Builds a fictional database shaped like a single-user installation after weeks
of scanning (about 1,200 jobs; about 80 discovery runs whose stored per-posting
decision audits total about 180 MB), starts a real local ASTRA server from a
chosen source tree on a spare loopback port, and replays what the Discovery
page does: every 5 seconds it requests /search/overview, /jobs, /settings and
/scan/status together, without waiting for the previous round (setInterval).
Part-way through, it presses Pause on one source the way the page does
(POST /records/sources, then the page reload and the app-wide reload).

Everything is fictional and stays in a temporary directory. No job source,
scan endpoint or Owner data is touched.

  python scripts/perf_discovery_poll.py build --out <dir>
  python scripts/perf_discovery_poll.py measure --data <dir> --tree <repo root> [--seconds 45] [--client new]
  python scripts/perf_discovery_poll.py worker --data <dir> [--polling] [--client new]

--client old replays the page before the responsiveness fix (every round asks for
all four responses and does not wait for the previous round); --client new
replays the fixed page (one round at a time; the job list only on the first
round and once a minute, since this replay changes no run).
"""
import argparse
import copy
import ctypes
import json
import os
import random
import secrets
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLL = ('/api/search/overview', '/api/jobs', '/api/settings', '/api/scan/status')
POLL_LIGHT = ('/api/search/overview', '/api/settings', '/api/scan/status')
JOBS_EVERY = 60.0
RELOAD = ('/api/jobs', '/api/dashboard', '/api/settings', '/api/profile')
WORDS = ('monitor alerts triage incidents escalate network endpoint cloud identity access review '
         'controls policy risk logs detection response analyst platform tooling customer service team '
         'report quarterly systems patch vulnerability scan evidence audit training support security').split()


def fictional_text(rng, size):
    out, n = [], 0
    while n < size:
        word = rng.choice(WORDS)
        out.append(word)
        n += len(word) + 1
    return ' '.join(out)


# --- Build -----------------------------------------------------------------------------
def build(out, jobs=1200, runs=80, heavy_runs=24, heavy_decisions=900, light_decisions=60, seed=4602):
    """Create a fictional database under `out`/data. Returns summary sizes."""
    out = Path(out)
    data = out / 'data'
    data.mkdir(parents=True, exist_ok=True)
    os.environ['HUNTER_DATA_DIR'] = str(data)
    os.environ['DATABASE_URL'] = 'sqlite:///' + (data / 'hunter.db').as_posix()
    sys.path.insert(0, str(ROOT))
    from backend import recall
    from backend.models import AutomationRun, DEFAULTS, Job, JobSource, Session, Settings, initialize
    from datetime import datetime, timedelta, timezone

    initialize()
    rng = random.Random(seed)
    cfg = dict(DEFAULTS)
    profile = {'skills': [{'text': s} for s in ('SIEM', 'Splunk', 'Linux', 'Python', 'incident response')],
               'declarations': {'verified_relevant_experience_years': 1,
                                'verified_relevant_experience_years_confirmed': True}}
    titles = ('SOC Analyst', 'Security Engineer', 'Senior Platform Engineer', 'Customer Support Specialist',
              'Data Analyst', 'Identity Operations Associate', 'Sales Executive', 'Network Engineer')
    templates = []
    for i in range(48):
        item = {'title': titles[i % len(titles)] + f' {i}', 'company': f'Fictional Co {i % 17}',
                'location': rng.choice(('Dubai, United Arab Emirates', 'Remote', 'London, United Kingdom',
                                        'Abu Dhabi, United Arab Emirates', 'Singapore')),
                'description': fictional_text(rng, rng.choice((1500, 3000, 6000))), 'remote_status': '',
                'job_url': f'https://jobs.example.invalid/{i}', 'experience_requirement': '', 'date_posted': '',
                'closing_date': ''}
        templates.append((item, recall.evaluate(item, cfg, profile)))
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    with Session.begin() as db:
        row = db.get(Settings, 1)
        if row is None:
            db.add(Settings(id=1, value=cfg))
        sources = []
        for i in range(13):
            adapter = ('lever', 'greenhouse', 'ashby', 'smartrecruiters')[i % 4]
            sources.append(JobSource(name=f'Fictional Board {i:02d}', adapter=adapter, board=f'fictional{i}',
                                     url=f'https://boards.example.invalid/{i}', enabled=True,
                                     details={'jobs_fetched': rng.randint(5, 400)}))
        for i in range(52):
            sources.append(JobSource(name=f'Fictional Manual {i:02d}', adapter='manual', enabled=False,
                                     url=f'https://careers.example.invalid/{i}', details={}))
        db.add_all(sources)
        db.flush()
        auto = [s for s in sources if s.adapter != 'manual']
        for n in range(jobs):
            item, decision = templates[n % len(templates)]
            analysis = {'recall': {k: v for k, v in decision.items() if k != 'fit_assessment'},
                        'fit_assessment': decision['fit_assessment'], 'why': [fictional_text(rng, 60)] * 4,
                        'discovery': {'source_id': auto[n % len(auto)].id}, 'first_seen': now.isoformat(),
                        'last_seen': now.isoformat()}
            db.add(Job(company=item['company'], title=item['title'], location=item['location'],
                       job_url=item['job_url'] + f'-{n}', description=fictional_text(rng, rng.choice((1500, 3500, 9000))),
                       source='Fictional', match_score=int(decision['priority']), status='NEW',
                       recommendation='REVIEW', analysis=analysis,
                       date_found=(now - timedelta(hours=n)).isoformat()))
        for r in range(runs):
            count = heavy_decisions if r >= runs - heavy_runs else (light_decisions if r >= runs - 70 else 0)
            decisions = []
            for d in range(count):
                item, decision = templates[(r + d) % len(templates)]
                decisions.append({'source_id': auto[d % len(auto)].id,
                                  'item': {**item, 'description': item['description'][:2200]},
                                  'disposition': 'DUPLICATE', 'job_id': d + 1, 'decision': copy.deepcopy(decision),
                                  'already_seen': True, 'bucket': decision['fit_assessment']['bucket']})
            report = {'trigger': 'MANUAL_START', 'discovered': 3, 'duplicates': count, 'failures': 0,
                      'duration_seconds': 30.0 + r, 'sources_attempted': len(auto), 'sources_successful': len(auto),
                      'sources': [{'id': s.id, 'name': s.name, 'scanned': 40, 'imported': 1, 'duplicates': 39,
                                   'filtered': {}, 'error': ''} for s in auto],
                      'funnel': {'fetched': count}, 'decisions': decisions}
            db.add(AutomationRun(task='discover', status='COMPLETED', report=report,
                                 created_at=(now + timedelta(hours=r)).isoformat(),
                                 updated_at=(now + timedelta(hours=r, minutes=5)).isoformat()))
    import sqlite3
    with sqlite3.connect(data / 'hunter.db') as c:
        c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        sizes = {'jobs': c.execute('select count(*) from jobs').fetchone()[0],
                 'runs': c.execute("select count(*) from automation_runs where task='discover'").fetchone()[0],
                 'reports_mb': round(c.execute('select sum(length(report)) from automation_runs').fetchone()[0] / 1e6, 1),
                 'jobs_mb': round(c.execute('select sum(length(analysis)+length(description)) from jobs').fetchone()[0] / 1e6, 1)}
    return sizes


# --- Measure ---------------------------------------------------------------------------
def _process_stats(pid):
    """(peak working set bytes, CPU seconds) for a process, Windows only; (None, None) elsewhere."""
    if os.name != 'nt':
        return None, None

    class Counters(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong)] + [
            (n, ctypes.c_size_t) for n in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                                           'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                                           'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    kernel32 = ctypes.WinDLL('kernel32')
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None, None
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        peak = counters.PeakWorkingSetSize if kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters),
                                                                               counters.cb) else None
        created, exited, kernel, user = (ctypes.c_ulonglong() for _ in range(4))
        cpu = ((kernel.value + user.value) / 1e7 if kernel32.GetProcessTimes(
            handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)) else None)
        return peak, cpu
    finally:
        kernel32.CloseHandle(handle)


def _free_loopback_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


_REPLAY_WRAPPER = '''import json
import os
import threading
from backend.main import app as inner

async def app(scope, receive, send):
    if scope['type'] == 'http' and scope['path'] == '/__astra_perf_identity':
        body = json.dumps({'nonce': os.environ['ASTRA_PERF_NONCE'], 'pid': os.getpid()}).encode()
        await send({'type': 'http.response.start', 'status': 200,
                    'headers': [(b'content-type', b'application/json')]})
        await send({'type': 'http.response.body', 'body': body})
        return
    if scope['type'] == 'http' and scope['path'] == '/__astra_perf_stop':
        headers = dict(scope['headers'])
        authorized = headers.get(b'x-astra-perf-nonce') == os.environ['ASTRA_PERF_NONCE'].encode()
        await send({'type': 'http.response.start', 'status': 200 if authorized else 403,
                    'headers': []})
        await send({'type': 'http.response.body', 'body': b''})
        if authorized:
            threading.Timer(0.1, os._exit, args=(0,)).start()
        return
    await inner(scope, receive, send)
'''


def stop_server(proc, port=None, nonce=None):
    """Stop the identity-matched replay or its own process handle; never trust a reported PID."""
    if port is not None and nonce is not None:
        import httpx
        try:
            httpx.post(f'http://127.0.0.1:{port}/__astra_perf_stop',
                       headers={'x-astra-perf-nonce': nonce}, timeout=3)
            proc.wait(timeout=5)
            return
        except (httpx.RequestError, subprocess.TimeoutExpired):
            pass
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=30)


def start_server(tree, data):
    port = _free_loopback_port()
    nonce = secrets.token_urlsafe(32)
    (Path(data).parent / 'astra_perf_wrapper.py').write_text(_REPLAY_WRAPPER, encoding='utf-8')
    env = dict(os.environ, HUNTER_DATA_DIR=str(data), HUNTER_PORT=str(port), ASTRA_PERF_NONCE=nonce)
    env.pop('DATABASE_URL', None)
    env.pop('APP_TOKEN', None)
    python = Path(tree) / '.venv' / 'Scripts' / 'python.exe'
    python = python if python.exists() else Path(sys.executable)
    proc = subprocess.Popen([str(python), '-m', 'uvicorn', 'astra_perf_wrapper:app', '--app-dir',
                             str(Path(data).parent), '--host', '127.0.0.1', '--port', str(port),
                             '--no-access-log'], cwd=str(tree), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import httpx
    try:
        for _ in range(120):
            if proc.poll() is not None:
                raise RuntimeError('server exited during startup')
            time.sleep(0.5)
            try:
                response = httpx.get(f'http://127.0.0.1:{port}/__astra_perf_identity', timeout=5)
            except httpx.RequestError:
                continue
            if proc.poll() is not None:
                raise RuntimeError('server exited during startup')
            if response.status_code != 200:
                raise RuntimeError('replay port is served by a different process')
            try:
                identity = response.json()
            except ValueError as exc:
                raise RuntimeError('unexpected health response on replay port') from exc
            if not isinstance(identity, dict) or identity.get('nonce') != nonce:
                raise RuntimeError('replay port is served by a different process')
            health_response = httpx.get(f'http://127.0.0.1:{port}/api/health', timeout=5)
            health_response.raise_for_status()
            health = health_response.json()
            if not isinstance(health, dict) or health.get('ok') is not True or health.get('pid') != identity.get('pid'):
                raise RuntimeError('health response does not match the identity-matched replay process')
            return proc, health, port, nonce
        raise RuntimeError('server did not start')
    except BaseException:
        stop_server(proc)
        raise


def measure(data, tree, seconds=45, act_at=12.0, sequential_reps=3, client='old', poll_interval=5.0):
    """Start a server on a copy of `data`, replay the Discovery page, return the measurements."""
    import httpx
    if client not in ('old', 'new') or poll_interval <= 0:
        raise ValueError('Choose an old/new client and a positive polling interval')
    work = Path(tempfile.mkdtemp(prefix='astra-perf-'))
    copy_data = work / 'data'
    try:
        shutil.copytree(data, copy_data)
        proc, health, port, nonce = start_server(tree, copy_data)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    pid = health['pid']
    base = f'http://127.0.0.1:{port}'
    out = {'build': health.get('build'), 'client': client, 'endpoints': {}, 'page': {}}
    try:
        with httpx.Client(base_url=base, timeout=300) as probe_client:
            for path in POLL + ('/api/dashboard',):
                walls, sizes = [], []
                for _ in range(sequential_reps):
                    t = time.perf_counter()
                    reply = probe_client.get(path)
                    walls.append(time.perf_counter() - t)
                    sizes.append(len(reply.content))
                    reply.raise_for_status()
                out['endpoints'][path] = {'median_s': round(statistics.median(walls), 3), 'bytes': sizes[-1]}
            source = next(s for s in probe_client.get('/api/search/overview').json()['sources'] if s['enabled'])
        _, cpu_before = _process_stats(pid)
        lock = threading.Lock()
        rounds, in_flight, peak_in_flight, act, jobs_at = [], [0], [0], {}, [None]
        request_counts, skipped_rounds, request_errors, action_errors = Counter(), [0], [], []

        def checked_get(http_client, path):
            try:
                http_client.get(path).raise_for_status()
            except Exception as exc:
                with lock:
                    request_errors.append(f'{path}: {type(exc).__name__}: {exc}')

        def paths():
            if client == 'old':
                return POLL
            if jobs_at[0] is None or time.perf_counter() - jobs_at[0] >= JOBS_EVERY:
                jobs_at[0] = time.perf_counter()
                return POLL
            return POLL_LIGHT

        def one_round():
            with lock:
                if client == 'new' and in_flight[0]:
                    skipped_rounds[0] += 1        # single-flight: skip while a round is pending
                    return
                in_flight[0] += 1
                peak_in_flight[0] = max(peak_in_flight[0], in_flight[0])
            t = time.perf_counter()
            try:
                requested = paths()
                with lock:
                    request_counts.update(requested)
                with httpx.Client(base_url=base, timeout=600) as c:
                    threads = [threading.Thread(target=checked_get, args=(c, p)) for p in requested]
                    for th in threads:
                        th.start()
                    for th in threads:
                        th.join()
            except Exception as exc:
                with lock:
                    request_errors.append(f'round: {type(exc).__name__}: {exc}')
            finally:
                with lock:
                    rounds.append(time.perf_counter() - t)
                    in_flight[0] -= 1

        def pause_source():
            t = time.perf_counter()
            try:
                with httpx.Client(base_url=base, timeout=600) as c:
                    c.post('/api/records/sources', json={'id': source['id'], 'enabled': False}).raise_for_status()
                    act['saved_s'] = round(time.perf_counter() - t, 3)
                    for group in (POLL, RELOAD):      # the page's load(), then the app's reload()
                        threads = [threading.Thread(target=checked_get, args=(c, p)) for p in group]
                        for th in threads:
                            th.start()
                        for th in threads:
                            th.join()
                act['refreshed_s'] = round(time.perf_counter() - t, 3)
            except Exception as exc:
                with lock:
                    action_errors.append(f'{type(exc).__name__}: {exc}')

        started, workers, acted = time.perf_counter(), [], None
        while time.perf_counter() - started < seconds:
            worker = threading.Thread(target=one_round)
            worker.start()
            workers.append(worker)
            if acted is None and time.perf_counter() - started >= act_at:
                acted = threading.Thread(target=pause_source)
                acted.start()
            time.sleep(poll_interval)
            if acted is None and time.perf_counter() - started >= act_at:
                acted = threading.Thread(target=pause_source)
                acted.start()
        for worker in workers + ([acted] if acted else []):
            worker.join()
        if action_errors or (acted is not None and not {'saved_s', 'refreshed_s'} <= act.keys()):
            raise RuntimeError(f'Pause action failed or incomplete: {action_errors[:5]}')
        if request_errors:
            raise RuntimeError(f'Polling replay failed: {request_errors[:5]}')
        peak, cpu_after = _process_stats(pid)
        out['page'] = {'seconds': seconds, 'rounds_started': len(workers),
                       'rounds_completed': len(rounds), 'rounds_skipped': skipped_rounds[0],
                       'request_counts': dict(request_counts),
                       'round_median_s': round(statistics.median(rounds), 2), 'round_max_s': round(max(rounds), 2),
                       'peak_rounds_in_flight': peak_in_flight[0], 'pause_action': act,
                       'server_cpu_s': round(cpu_after - cpu_before, 1) if cpu_before is not None else None,
                       'server_peak_working_set_mib': round(peak / 2**20) if peak else None,
                       'total_s': round(time.perf_counter() - started, 1)}
    finally:
        stop_server(proc, port, nonce)
        shutil.rmtree(work, ignore_errors=True)
    return out


def worker_throughput(data, polling=False, seed_jobs=300, repeat=150, new=20, seed=4602, client='old'):
    """Time discovery's per-posting path (add_job, analyze, discovery stamp) in-process.

    A fictional employer first gets `seed_jobs` stored postings through the same
    path. Then `repeat` of them are seen again (duplicates) and `new` unseen ones
    arrive, as in a rescan of a large board. With `polling`, threads replay the
    Discovery page's unguarded 5-second request rounds against the same process
    through the ASGI app, as the server does while a scan runs.
    """
    work = Path(tempfile.mkdtemp(prefix='astra-worker-'))
    shutil.copytree(data, work / 'data')
    os.environ['HUNTER_DATA_DIR'] = str(work / 'data')
    os.environ['DATABASE_URL'] = 'sqlite:///' + (work / 'data' / 'hunter.db').as_posix()
    os.environ.pop('APP_TOKEN', None)
    sys.path.insert(0, str(ROOT))
    from sqlalchemy import select
    from backend.models import JobSource, Session, now, settings
    from backend.services import add_job, analyze
    rng = random.Random(seed)

    def posting(n):
        return {'title': f'Fictional Engineer {n % 40} Level {n % 3}', 'company': 'Big Fictional Employer',
                'location': rng.choice(('Dubai, United Arab Emirates', 'Remote', 'London, United Kingdom')),
                'job_url': f'https://jobs.example.invalid/big/{n}', 'source_job_id': f'big-{n}',
                'source': 'Lever', 'description': fictional_text(rng, 3000), 'date_posted': '', 'closing_date': ''}

    def process(db, source, cfg, item):
        j, d = add_job(db, dict(item), job_source=source)
        analyze(db, j, profile={}, cfg=cfg)
        j.analysis = {**j.analysis, 'last_seen': now(), 'discovery': {'source_id': source.id, 'last_seen': now()}}
        return bool(d)
    with Session() as db:
        source = db.scalar(select(JobSource).where(JobSource.adapter == 'lever').limit(1))
        cfg = settings(db)
        for n in range(seed_jobs):
            process(db, source, cfg, posting(n))
        db.commit()
    stop, rounds = threading.Event(), []
    if polling:
        from fastapi.testclient import TestClient
        from backend.main import app

        busy, jobs_at = [False], [None]

        def one_round():
            if client == 'new':
                if busy[0]:
                    return
                busy[0] = True
            t = time.perf_counter()
            fresh = jobs_at[0] is None or time.perf_counter() - jobs_at[0] >= JOBS_EVERY
            if fresh:
                jobs_at[0] = time.perf_counter()
            session = TestClient(app)
            threads = [threading.Thread(target=session.get, args=(p,)) for p in (POLL if client == 'old' or fresh else POLL_LIGHT)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
            rounds.append(time.perf_counter() - t)
            busy[0] = False

        def poller():
            while not stop.is_set():
                threading.Thread(target=one_round, daemon=True).start()
                stop.wait(5)
        threading.Thread(target=poller, daemon=True).start()
    items = [posting(n) for n in range(repeat)] + [posting(seed_jobs + n) for n in range(new)]
    started, cpu = time.perf_counter(), time.process_time()
    with Session() as db:
        source = db.get(JobSource, source.id)
        duplicates = sum(process(db, source, cfg, item) for item in items)
        db.commit()
    elapsed = time.perf_counter() - started
    stop.set()
    out = {'polling': polling, 'client': client if polling else None, 'postings': len(items), 'duplicates': duplicates,
           'seconds': round(elapsed, 2), 'seconds_per_posting': round(elapsed / len(items), 4),
           'process_cpu_s': round(time.process_time() - cpu, 1), 'poll_rounds_finished': len(rounds)}
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--out', required=True)
    m = sub.add_parser('measure')
    m.add_argument('--data', required=True)
    m.add_argument('--tree', required=True)
    m.add_argument('--seconds', type=float, default=45)
    m.add_argument('--client', choices=('old', 'new'), default='old')
    w = sub.add_parser('worker')
    w.add_argument('--data', required=True)
    w.add_argument('--polling', action='store_true')
    w.add_argument('--client', choices=('old', 'new'), default='old')
    args = parser.parse_args(argv)
    if args.command == 'build':
        print(json.dumps(build(args.out)))
    elif args.command == 'worker':
        print(json.dumps(worker_throughput(Path(args.data), polling=args.polling, client=args.client)), flush=True)
        os._exit(0)   # daemon polling threads may still hold the ASGI portal
    else:
        print(json.dumps(measure(Path(args.data), Path(args.tree), args.seconds, client=args.client), indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Windows disposable ZIP installation acceptance. Never uses the live data/task."""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from publication_gate import PRIVATE, scan

def request(port, path, data=None):
    req = urllib.request.Request('http://127.0.0.1:'+str(port)+path,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()

def run(archive):
    if os.name != 'nt':
        raise RuntimeError('Windows required')
    with tempfile.TemporaryDirectory(prefix='astra-clean-install-') as temp:
        target = Path(temp)
        with zipfile.ZipFile(archive) as z:
            findings = []
            names = z.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Duplicate ZIP entries')
            for item in z.infolist():
                name = item.filename
                p = PurePosixPath(name)
                if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or not name.startswith('astra/'):
                    raise ValueError('Unsafe release path')
                if item.file_size > 30_000_000 or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Unsafe release member')
                scan(z.read(item), 'artifact:'+name.removeprefix('astra/'), findings)
            if findings:
                raise ValueError('Private/sensitive release content')
            manifest = json.loads(z.read('astra/release-manifest.json'))
            expected = {'astra/'+n for n in manifest['sha256']} | {'astra/release-manifest.json'}
            if set(names) != expected:
                raise ValueError('Manifest member set mismatch')
            for name, digest in manifest['sha256'].items():
                if hashlib.sha256(z.read('astra/'+name)).hexdigest() != digest:
                    raise ValueError('Manifest digest mismatch')
            z.extractall(target)
        project = target/'astra'
        if (project/'data').exists() or (project/'.venv').exists() or (project/'.env').exists():
            raise ValueError('Installation is not empty')
        env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'HUNTER_DATA_DIR', 'APP_TOKEN', 'ASTRA_DEMO_ONLY', 'BIND_HOST', 'PYTHONPATH')}
        env.update(PYTHONUTF8='1', PYTHON_KEYRING_BACKEND='keyring.backends.fail.Keyring')
        setup = subprocess.run(['cmd.exe', '/d', '/c', 'setup.bat'], cwd=project, env=env,
                               capture_output=True, text=True, timeout=900)
        if setup.returncode:
            # Synthetic environment, but do not leak local paths in public evidence.
            raise RuntimeError('setup.bat failed with exit '+str(setup.returncode))
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
        env.update(HUNTER_PORT=str(port), HUNTER_DATA_DIR=str(project/'data'), DATABASE_URL='sqlite:///'+str(project/'data/hunter.db'))
        process = None
        def start(demo=False):
            nonlocal process
            childenv = dict(env)
            if demo:
                childenv['ASTRA_DEMO_ONLY'] = '1'
            process = subprocess.Popen([str(project/'.venv/Scripts/python.exe'), '-m', 'uvicorn', 'backend.main:app',
                                        '--host', '127.0.0.1', '--port', str(port), '--no-access-log', '--no-proxy-headers'],
                                       cwd=project, env=childenv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(90):
                if process.poll() is not None:
                    raise RuntimeError('Disposable server exited')
                try:
                    if request(port, '/demo' if demo else '/api/health')[0] == 200:
                        return
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.25)
            raise RuntimeError('Disposable startup timeout')
        def stop():
            nonlocal process
            if process is not None:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)
                process = None
        try:
            start()
            assert request(port, '/demo')[0] == 200
            assert json.loads(request(port, '/api/jobs')[1]) == []
            assert request(port, '/api/jobs', {'company':'Example Acceptance Company','title':'Synthetic Role','description':'Fictional installation test'})[0] == 200
            stop(); start()
            jobs = json.loads(request(port, '/api/jobs')[1])
            assert len(jobs) == 1 and jobs[0]['company'] == 'Example Acceptance Company'
            stop(); start(demo=True)
            for path in ('/api/health','/api/profile','/api/jobs','/api/settings','/api/privacy/export','/api/files/tracker.xlsx'):
                assert request(port, path)[0] == 404
            assert request(port, '/api/jobs', {})[0] == 404
        finally:
            stop()
    return {'status':'PASS','artifact_sha256':hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
            'checks':['manifest','setup.bat','empty database','demo','synthetic mutation','restart persistence','demo API denial','shutdown','temporary cleanup'],
            'environment':'GitHub-hosted Windows' if os.getenv('GITHUB_ACTIONS')=='true' and os.getenv('RUNNER_ENVIRONMENT')=='github-hosted' else 'same-host disposable rehearsal; not a clean VM'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.archive.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))

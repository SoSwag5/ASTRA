"""Refresh hashes for existing exact pins from PyPI. Review diff before install."""
import concurrent.futures
import json
import re
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def entry(pin):
    name,version=pin.split('==')
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:
        data=json.load(response)
    hashes=sorted({f['digests']['sha256'] for f in data['urls'] if f['packagetype']=='bdist_wheel'})
    if not hashes:raise RuntimeError('No wheels for '+name)
    marker='; sys_platform == "win32"' if name.lower()=='pywin32-ctypes' else ''
    return pin+marker+' \\\n'+' \\\n'.join('    --hash=sha256:'+h for h in hashes)+'\n'

def main():
    path=ROOT/'requirements.lock.txt'
    pins=re.findall(r'^([\w.-]+==[\w.+-]+)',path.read_text(),re.M)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(entry,pins))
    path.write_text('# Exact Windows runtime and test dependencies.\n--require-hashes\n--only-binary=:all:\n'+''.join(rows))
    print('Locked',len(rows),'packages; verify with a fresh installation')

if __name__=='__main__':main()

"""Build an unpublished deterministic source + prebuilt-frontend release ZIP."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.publication_gate import git, PRIVATE

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-build',action='store_true',help='CI: frontend and tests already passed')
    args=parser.parse_args()
    if git('status','--porcelain').strip():raise RuntimeError('Commit reviewed source changes before packaging')
    subprocess.run([sys.executable,str(ROOT/'scripts/publication_gate.py')],cwd=ROOT,check=True)
    if not args.skip_build:
        npm='npm.cmd' if os.name=='nt' else 'npm'
        for command in ([npm,'ci'],[npm,'test'],[npm,'run','build']):subprocess.run(command,cwd=ROOT/'frontend',check=True)
        subprocess.run([sys.executable,'-m','pytest','-q'],cwd=ROOT,check=True)
    files={}
    for raw in git('ls-files','-z').split(b'\0'):
        if not raw:continue
        name=raw.decode()
        if PRIVATE.search(name):raise RuntimeError('Private artifact in tracked source')
        files[name]=(ROOT/name).read_bytes()
    for path in sorted((ROOT/'frontend/dist').rglob('*')):
        if path.is_file():files[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    if 'frontend/dist/index.html' not in files:raise RuntimeError('Frontend missing')
    manifest={'version':'1.0.0-rc.1','source_commit':git('rev-parse','HEAD').decode().strip(),
              'python':'3.14 (3.13 compatible)','node_build':'24 LTS','node_runtime_required':False,
              'sha256':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}}
    files['release-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    out=ROOT/'release';out.mkdir(exist_ok=True)
    target=out/'astra-1.0.0-rc.1.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(files.items()):
            item=zipfile.ZipInfo('astra/'+name,date_time=(2026,9,12,0,0,0))
            item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16
            archive.writestr(item,data)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n')
    with zipfile.ZipFile(target) as archive:
        assert not any(PRIVATE.search(n.removeprefix('astra/')) for n in archive.namelist())
        assert archive.testzip() is None
    print(json.dumps({'archive':str(target.relative_to(ROOT)),'sha256':digest,'files':len(files)}))

if __name__=='__main__':main()

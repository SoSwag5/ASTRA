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
from scripts.publication_gate import git, PRIVATE, scan

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-build',action='store_true',help='CI: frontend and tests already passed')
    parser.add_argument('--sbom',type=Path,required=True,help='Validated CycloneDX 1.7 BOM from assurance environment')
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
    bom=json.loads(args.sbom.read_text(encoding='utf-8'))
    if bom.get('specVersion')!='1.7':raise RuntimeError('CycloneDX 1.7 required')
    # Full schema validation executes in the separate assurance environment.
    validation=json.loads(args.sbom.with_suffix('.validation.json').read_text())
    if validation.get('status')!='PASS' or validation.get('sha256')!=hashlib.sha256(args.sbom.read_bytes()).hexdigest():
        raise RuntimeError('Missing or stale SBOM validation')
    files['security/sbom.cdx.json']=args.sbom.read_bytes()
    findings=[]
    for name,data in files.items():scan(data,'artifact:'+name,findings)
    if findings:
        # Locations and categories only; payloads are never printed.
        print(json.dumps({'status':'BLOCKED','findings':findings},indent=2),file=sys.stderr)
        raise RuntimeError('Artifact content failed publication gate: '+', '.join(sorted({f['location']+' ('+f['category']+')' for f in findings})))
    manifest={'version':'1.0.0-rc.1','source_commit':git('rev-parse','HEAD').decode().strip(),
              'python_reference':'3.13.2','python_verification_target':['3.13','3.14'],'node_build':'24 LTS','node_runtime_required':False,
              'sbom_sha256':validation['sha256'],'sbom_specification':'1.7',
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

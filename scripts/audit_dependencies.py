"""Read installed metadata and public vulnerability records; never send project files."""
import importlib.metadata as metadata
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import httpx

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--offline',action='store_true',help='Regenerate inventory and notices from installed files only; leave the vulnerability report unchanged.')
args=parser.parse_args()
OUT=ROOT/'audit'; OUT.mkdir(exist_ok=True)
generated=datetime.now(timezone.utc).date().isoformat()
packages=[]; notices=[f'# Third-party notices\n\nGenerated from installed package metadata on {generated}.\nThese notices are not a legal clearance. Unknown metadata and missing licence files must be resolved before redistribution. Optional platform packages absent from this installation need review on the target platform. Browser downloads and operating-system packages need their own inventory.\n']

def is_notice(file):
    """Include nested bundled notices, font licences and *.js.LICENSE sidecars."""
    name=file.name.lower()
    return any(word in name for word in ('license','licence','copying','notice')) and file.suffix.lower() in ('','.txt','.md','.rst','.license','.licence')

def append_notices(row,files):
    row['license_files']=[]
    row['license_read_errors']=[]
    for label,file in files:
        try:
            body=file.read_text(encoding='utf-8',errors='replace')
        except OSError as error:
            row['license_read_errors'].append({'path':label,'error_type':type(error).__name__})
            continue
        # Licence texts can exceed 100KB (Vite and Playwright's bundled Node do).
        # Preserve the complete text instead of silently dropping long notices.
        row['license_files'].append(label)
        fence='`' * max(3,1+max((len(match.group()) for match in re.finditer(r'`+',body)),default=0))
        notices.append(f'\n### {label}\n\n{fence}text\n{body}\n{fence}\n')
    if not row['license_files']:
        notices.append('\nNo licence file was found in this installed package. Review the upstream package before redistribution.\n')

for distribution in sorted(metadata.distributions(),key=lambda d:d.metadata['Name'].lower()):
    m=distribution.metadata; name=m['Name']; version=distribution.version
    license=m.get('License-Expression') or m.get('License') or '; '.join(x for x in m.get_all('Classifier',[]) if x.startswith('License ::')) or 'UNKNOWN'
    row={'ecosystem':'PyPI','name':name,'version':version,'license':license,'source':f'https://pypi.org/project/{name}/{version}/','attribution':'Retain bundled copyright/license notices','redistribution':'See installed licence text; review any UNKNOWN entry','modification':'See licence; do not remove notices'}
    packages.append(row); notices.append(f'\n## {name} {version}\n\nSource: {row["source"]}\n\nLicence metadata: {license}\n')
    append_notices(row,[(str(file),Path(distribution.locate_file(file))) for file in distribution.files or [] if is_notice(file)])

lock=json.loads((ROOT/'frontend/package-lock.json').read_text())
for path,entry in lock['packages'].items():
    if not path: continue
    name=path.split('node_modules/')[-1]; installed=ROOT/'frontend'/path
    source=entry.get('resolved','UNKNOWN'); license=entry.get('license','UNKNOWN')
    row={'ecosystem':'npm','name':name,'version':entry['version'],'license':license,'source':source,'development':entry.get('dev',False),'install_script':entry.get('hasInstallScript',False),'attribution':'Retain copyright and licence text','redistribution':'See licence text; optional platform binaries may be present in lock only','modification':'See licence'}
    packages.append(row); notices.append(f'\n## {name} {entry["version"]}\n\nSource: {source}\n\nLicence: {license}\n')
    if installed.exists():
        files=[file for file in installed.rglob('*') if file.is_file() and is_notice(file) and 'node_modules' not in file.relative_to(installed).parts]
        append_notices(row,[(str(file.relative_to(ROOT/'frontend')),file) for file in sorted(files)])
    else:
        row['license_files']=[]
        row['license_read_errors']=[]
        row['installed']=False
        notices.append('\nPackage is present in the lockfile but not installed on this platform; its licence text is not included here.\n')

(OUT/'dependency-inventory.json').write_text(json.dumps(packages,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'THIRD_PARTY_NOTICES.md').write_text('\n'.join(notices),encoding='utf-8')

if args.offline:
    print(json.dumps({'inventoried':len(packages),'unknown_licenses':sum(p['license']=='UNKNOWN' for p in packages),'license_read_errors':sum(len(p['license_read_errors']) for p in packages),'python_audit_skipped':True,'vulnerability_report':'unchanged'}))
    raise SystemExit(0)

def audit(row):
    try:
        response=httpx.get(f'https://pypi.org/pypi/{row["name"]}/{row["version"]}/json',timeout=20)
        response.raise_for_status()
        return {'name':row['name'],'version':row['version'],'status':'checked','vulnerabilities':response.json().get('vulnerabilities',[])}
    except Exception as error: return {'name':row['name'],'version':row['version'],'status':'UNVERIFIED','error_type':type(error).__name__}

with ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(audit,[p for p in packages if p['ecosystem']=='PyPI']))
(OUT/'python-vulnerabilities.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps({'inventoried':len(packages),'unknown_licenses':sum(p['license']=='UNKNOWN' for p in packages),'python_checked':sum(r['status']=='checked' for r in results),'python_unverified':sum(r['status']!='checked' for r in results),'python_vulnerability_records':sum(len(r.get('vulnerabilities',[])) for r in results)}))

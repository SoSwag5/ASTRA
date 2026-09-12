"""Scan tracked worktree and reachable history; print locations, never payloads.

Heuristics supplement manual PII review. Third-party attribution and fictional
example addresses are permitted. Errors are CHECK_COULD_NOT_RUN (exit 2).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATTERNS={
    'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'api_token':rb'(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})',
    'private_machine_path':rb'[A-Za-z]:[\\/]Users[\\/][^\s\x22\x27]+',
    'personal_email':rb'[\w.+-]+@(?:gmail|outlook|hotmail|yahoo)\.com',
}
PRIVATE=re.compile(r'(^|/)(data|backups|\.local|private|node_modules|\.venv)/|\.(db|sqlite|xlsx|docx|pdf|bundle)$|(^|/)(UAE_.*|CAMPAIGN_GAP_MAP|SEARCH_QUALITY_AUDIT|AUDIT_SECOND_PASS)\.md$|(^|/)\.env$',re.I)

def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),*args],cwd=ROOT)

def scan(data,location,findings):
    path=location.split(':',1)[-1]
    if PRIVATE.search(path):findings.append({'location':location,'category':'private_artifact'})
    for name,pattern in PATTERNS.items():
        # Preserve upstream license authors' chosen public contact attribution.
        if name=='personal_email' and path in ('THIRD_PARTY_NOTICES.md','frontend/public/third-party-notices.txt'):continue
        if re.search(pattern,data):findings.append({'location':location,'category':name})

def main():
    findings=[];count=0
    try:
        for raw in git('ls-files','-z').split(b'\0'):
            if not raw:continue
            path=raw.decode();file=ROOT/path
            if file.is_file():scan(file.read_bytes(),'tree:'+path,findings);count+=1
        objects=git('rev-list','--objects','--all').decode().splitlines()
        for entry in objects:
            oid,_,path=entry.partition(' ')
            if git('cat-file','-t',oid).strip()!=b'blob':continue
            scan(git('cat-file','blob',oid),'history:'+path,findings);count+=1
        metadata=git('log','--all','--format=%B%n%ae%n%ce')
        scan(metadata,'history:commit-metadata',findings)
        result={'status':'BLOCKED' if findings else 'PASS','objects_checked':count,'findings':findings,'scope':'tracked worktree + all reachable refs + commit messages/author emails','limitation':'Pattern scan is not proof of absence of all PII; review fictional fixtures and assets manually.'}
        print(json.dumps(result,indent=2));return 1 if findings else 0
    except Exception as error:
        print(json.dumps({'status':'CHECK_COULD_NOT_RUN','error':type(error).__name__}));return 2

if __name__=='__main__':sys.exit(main())

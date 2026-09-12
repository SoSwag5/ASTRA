"""Scan tracked worktree and publishable history; print locations, never payloads.

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
    'employment_record_table':rb'(?im)^\|\s*ID\s*\|\s*Company\s*\|\s*Role\s*\|\s*Status\s*\|\s*Result\s*\|',
    'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'api_token':rb'(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})',
    'private_machine_path':rb'[A-Za-z]:[\\/]Users[\\/][^\s\x22\x27]+',
    'personal_email':rb'[\w.+-]+@(?:gmail|outlook|hotmail|yahoo)\.com',
}
PRIVATE=re.compile(r'(^|/)(data|backups|\.local|private|node_modules|\.venv)/|\.(db|sqlite|xlsx|docx|pdf|bundle)$|(^|/)(UAE_.*|CAMPAIGN_GAP_MAP|SEARCH_QUALITY_AUDIT|AUDIT_SECOND_PASS)\.md$|(^|/)\.env$',re.I)
# GitHub synthesises refs/pull/N/merge for pull_request checkouts. That commit is
# created by GitHub, is never part of the published repository, and carries
# GitHub-supplied authorship, so policing its own metadata blocks every pull
# request while protecting nothing. Its parents - the real base and the proposed
# head - are publishable and are scanned in its place, so no authored commit is
# ever skipped.
SYNTHETIC_REF=re.compile(r'^refs/(?:remotes/)?pull/')

def git(*args,root=ROOT):
    root=Path(root)
    return subprocess.check_output(['git','-c','safe.directory='+root.as_posix(),*args],cwd=root)

def publishable_tips(root=ROOT):
    """Return commits that can actually enter the published repository/release."""
    refs={}
    for line in git('for-each-ref','--format=%(objectname) %(refname)',root=root).decode().splitlines():
        oid,_,name=line.partition(' ')
        if oid and name:refs[name]=oid
    tips={oid for name,oid in refs.items() if not SYNTHETIC_REF.match(name)}
    head=git('rev-parse','HEAD',root=root).decode().strip()
    synthetic={oid for name,oid in refs.items() if SYNTHETIC_REF.match(name)}
    if head in synthetic and head not in tips:
        # Scan what the synthetic merge proposes, not GitHub's generated commit.
        tips.update(git('rev-list','--parents','-n','1',head,root=root).decode().split()[1:])
    else:
        tips.add(head)
    return sorted(tips)

def scan(data,location,findings):
    path=location.split(':',1)[-1]
    if PRIVATE.search(path):findings.append({'location':location,'category':'private_artifact'})
    for name,pattern in PATTERNS.items():
        # Preserve upstream license authors' chosen public contact attribution.
        if name=='personal_email' and path in ('THIRD_PARTY_NOTICES.md','frontend/public/third-party-notices.txt'):continue
        if re.search(pattern,data):findings.append({'location':location,'category':name})

def audit(root=ROOT):
    root=Path(root)
    findings=[];count=0
    tips=publishable_tips(root)
    for raw in git('ls-files','--cached','--others','--exclude-standard','-z',root=root).split(b'\0'):
        if not raw:continue
        path=raw.decode();file=root/path
        if file.is_file():scan(file.read_bytes(),'tree:'+path,findings);count+=1
    for entry in git('rev-list','--objects',*tips,root=root).decode().splitlines():
        oid,_,path=entry.partition(' ')
        if git('cat-file','-t',oid,root=root).strip()!=b'blob':continue
        scan(git('cat-file','blob',oid,root=root),'history:'+path,findings);count+=1
    metadata=git('log','--format=%B%n%ae%n%ce',*tips,root=root)
    scan(metadata,'history:commit-metadata',findings)
    return {'status':'BLOCKED' if findings else 'PASS','objects_checked':count,'findings':findings,'scope':'tracked and non-ignored untracked worktree + all publishable refs (GitHub-generated refs/pull/*/merge replaced by their real parents) + commit messages/author emails','limitation':'Pattern scan is not proof of absence of all PII; human review of packaged documents and images is mandatory.'}

def main():
    try:
        result=audit()
        print(json.dumps(result,indent=2));return 1 if result['findings'] else 0
    except Exception as error:
        print(json.dumps({'status':'CHECK_COULD_NOT_RUN','error':type(error).__name__}));return 2

if __name__=='__main__':sys.exit(main())

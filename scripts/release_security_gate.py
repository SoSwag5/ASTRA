"""Fail-closed release decision. Job outcomes come from GitHub needs context.

Local use produces BLOCKED without all remote evidence. This never publishes.
Repository protections/maintainer evidence review remain separate release inputs.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('verification', 'build', 'clean-install', 'provenance', 'verify-attestation')

def assess_asvs(asvs):
    canonical = json.loads((ROOT/'docs/security/asvs-5.0.0-requirements.json').read_text(encoding='utf-8'))
    expected = {r['id']: r for r in canonical}
    if not isinstance(asvs,list) or any(not isinstance(r,dict) for r in asvs):
        return ['Invalid ASVS assessment format']
    ids = [r.get('id') for r in asvs]
    if any(not isinstance(i,str) for i in ids) or len(ids)!=len(expected) or set(ids)!=set(expected):
        return ['Incomplete or substituted ASVS 5.0.0 assessment']
    blockers=[]
    for row in asvs:
        ident=row['id']; official=expected[ident]
        if row.get('level')!=official['level'] or row.get('requirement')!=official['requirement']:
            blockers.append('Altered ASVS requirement or level: '+ident)
        if official['level'] != 1: continue
        result=row.get('result')
        if result not in ('PASS','N/A'):
            blockers.append('Applicable L1 control unresolved: '+ident)
        required_fields=('rationale','evidence','verification_method')
        if any(not isinstance(row.get(f),str) or not row[f].strip() for f in required_fields):
            blockers.append('Missing L1 justification or evidence: '+ident)
        if result=='N/A' and row.get('applicability')!='NOT APPLICABLE':
            blockers.append('Unjustified L1 applicability: '+ident)
        if result=='PASS' and row.get('applicability')!='APPLICABLE':
            blockers.append('Inconsistent L1 applicability: '+ident)
    return blockers

def assess(needs, source, manifest, asvs, review):
    blockers = []
    if not re.fullmatch(r'[a-f0-9]{40}', source or ''):
        blockers.append('Invalid source commit')
    for name in REQUIRED:
        if needs.get(name, {}).get('result') != 'success':
            blockers.append('Mandatory job not successful: '+name)
    if manifest.get('source_commit') != source:
        blockers.append('Artifact/source identity mismatch or missing manifest')
    blockers.extend(assess_asvs(asvs))
    # Human review is explicit, source-bound evidence; not inferred from scans.
    if review.get('source_commit') != source or not review.get('reviewer'):
        blockers.append('Missing source-bound maintainer review')
    for name in ('publication_content', 'codeql_findings_triaged', 'dependency_review', 'repository_controls', 'scorecard_reviewed', 'residual_risks'):
        entry = review.get(name, {})
        if entry.get('status') != 'PASS' or not entry.get('evidence'):
            blockers.append('Missing reviewed evidence: '+name)
    return blockers

def artifact_checks(artifact, manifest, sbom):
    blockers=[]
    try:
        bom_bytes=sbom.read_bytes()
        bom=json.loads(bom_bytes)
        digest=hashlib.sha256(bom_bytes).hexdigest()
        validation=json.loads(sbom.with_suffix('.validation.json').read_text(encoding='utf-8'))
        if bom.get('bomFormat')!='CycloneDX' or bom.get('specVersion')!='1.7' or validation.get('status')!='PASS' or validation.get('sha256')!=digest or manifest.get('sbom_sha256')!=digest:
            blockers.append('Missing, failed or stale SBOM validation')
        with zipfile.ZipFile(artifact) as archive:
            if archive.read('astra/security/sbom.cdx.json')!=bom_bytes:
                blockers.append('Packaged SBOM differs from validated SBOM')
            packaged=json.loads(archive.read('astra/release-manifest.json'))
            if packaged!=manifest:blockers.append('Packaged manifest mismatch')
            names=archive.namelist()
            expected={'astra/'+n for n in manifest['sha256']}|{'astra/release-manifest.json'}
            if len(names)!=len(set(names)) or set(names)!=expected:
                blockers.append('Artifact member set mismatch')
            for name,file_digest in manifest['sha256'].items():
                if hashlib.sha256(archive.read('astra/'+name)).hexdigest()!=file_digest:
                    blockers.append('Artifact file digest mismatch: '+name)
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile):
        blockers.append('Artifact/SBOM verification evidence unavailable or malformed')
    return blockers

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, default=ROOT/'release/astra-1.0.0-rc.1.zip')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--sbom', type=Path, default=ROOT/'release/astra-1.0.0-rc.1.cdx.json')
    parser.add_argument('--output', type=Path, default=ROOT/'release/release-security-gate.json')
    args = parser.parse_args()
    source = os.getenv('GITHUB_SHA', '')
    if not source:
        try:source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        except (OSError,subprocess.CalledProcessError):pass
    input_blockers=[]
    def read_object(value,label):
        try:
            obj=json.loads(value)
            if not isinstance(obj,dict):raise ValueError(label)
            return obj
        except (ValueError,TypeError):
            input_blockers.append('Malformed '+label);return {}
    needs = read_object(os.getenv('ASTRA_JOB_RESULTS', '{}'),'job results')
    for name,entry in list(needs.items()):
        if not isinstance(entry,dict):input_blockers.append('Malformed job result');needs[name]={}
    manifest = read_object(args.manifest.read_text(encoding='utf-8'),'manifest') if args.manifest and args.manifest.exists() else {}
    review = read_object(args.review.read_text(encoding='utf-8'),'review') if args.review and args.review.exists() else {}
    for name,entry in list(review.items()):
        if name not in ('source_commit','artifact_sha256','reviewer') and not isinstance(entry,dict):
            input_blockers.append('Malformed review entry');review[name]={}
    asvs = json.loads((ROOT/'docs/security/OWASP_ASVS_5.0.0_MAPPING.json').read_text(encoding='utf-8'))
    blockers = input_blockers+assess(needs, source, manifest, asvs, review)
    blockers.extend(artifact_checks(args.artifact,manifest,args.sbom))
    digest = hashlib.sha256(args.artifact.read_bytes()).hexdigest() if args.artifact.exists() else None
    if not digest or review.get('artifact_sha256') != digest:
        blockers.append('Missing artifact or artifact-bound maintainer review')
    if os.getenv('GITHUB_ACTIONS') != 'true':
        blockers.append('Hosted release execution not established')
    # Local technical/data blockers are those resolvable without hosted execution
    # or human review evidence (ASVS mapping integrity + malformed gate inputs).
    LOCAL_MARKERS = ('ASVS', 'L1', 'Malformed', 'job result', 'job results')
    local_blockers = [b for b in blockers if any(m in b for m in LOCAL_MARKERS)]
    local_assurance = 'BLOCKED LOCALLY' if local_blockers else 'PASS FOR REMOTE ASSURANCE'
    result = {'decision': 'BLOCKED' if blockers else 'APPROVED WITH DOCUMENTED RESIDUAL RISK',
              'local_assurance': local_assurance, 'local_blockers': local_blockers,
              'source_commit': source or None, 'artifact_sha256': digest, 'jobs': needs,
              'generated_at': datetime.now(timezone.utc).isoformat(), 'blockers': blockers,
              'run': os.getenv('GITHUB_RUN_ID'), 'repository': os.getenv('GITHUB_REPOSITORY'),
              'publication_authorized': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    args.output.with_suffix('.md').write_text('# Release Security Assurance Report\n\nDecision: **'+result['decision']+'**\n\n```json\n'+json.dumps(result, indent=2)+'\n```\n\nTechnical approval does not authorize publication. See the accompanying SBOM, test, SCA, CodeQL, installation and attestation evidence.\n')
    print(json.dumps(result))
    return 1 if blockers else 0

if __name__ == '__main__':
    sys.exit(main())

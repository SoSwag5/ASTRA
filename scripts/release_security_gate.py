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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('verification', 'build', 'clean-install', 'provenance', 'verify-attestation')

def assess(needs, source, manifest, asvs, review):
    blockers = []
    if not re.fullmatch(r'[a-f0-9]{40}', source or ''):
        blockers.append('Invalid source commit')
    for name in REQUIRED:
        if needs.get(name, {}).get('result') != 'success':
            blockers.append('Mandatory job not successful: '+name)
    if manifest.get('source_commit') != source:
        blockers.append('Artifact/source identity mismatch or missing manifest')
    ids = [r.get('id') for r in asvs]
    if len(ids) != 345 or len(set(ids)) != 345:
        blockers.append('Incomplete ASVS 5.0.0 assessment')
    l1 = [r['id'] for r in asvs if r.get('level') == 1 and r.get('result') not in ('PASS', 'N/A')]
    if l1:
        blockers.append('Applicable L1 controls unresolved: '+str(len(l1)))
    # Human review is explicit, source-bound evidence; not inferred from scans.
    if review.get('source_commit') != source or not review.get('reviewer'):
        blockers.append('Missing source-bound maintainer review')
    for name in ('publication_content', 'codeql_findings_triaged', 'repository_controls', 'scorecard_reviewed', 'residual_risks'):
        entry = review.get(name, {})
        if entry.get('status') != 'PASS' or not entry.get('evidence'):
            blockers.append('Missing reviewed evidence: '+name)
    return blockers

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, default=ROOT/'release/astra-1.0.0-rc.1.zip')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'release/release-security-gate.json')
    args = parser.parse_args()
    source = os.getenv('GITHUB_SHA', '')
    needs = json.loads(os.getenv('ASTRA_JOB_RESULTS', '{}'))
    manifest = json.loads(args.manifest.read_text()) if args.manifest and args.manifest.exists() else {}
    review = json.loads(args.review.read_text()) if args.review and args.review.exists() else {}
    asvs = json.loads((ROOT/'docs/security/OWASP_ASVS_5.0.0_MAPPING.json').read_text())
    blockers = assess(needs, source, manifest, asvs, review)
    digest = hashlib.sha256(args.artifact.read_bytes()).hexdigest() if args.artifact.exists() else None
    if not digest or review.get('artifact_sha256') != digest:
        blockers.append('Missing artifact or artifact-bound maintainer review')
    if os.getenv('GITHUB_ACTIONS') != 'true':
        blockers.append('Hosted release execution not established')
    result = {'decision': 'BLOCKED' if blockers else 'APPROVED WITH DOCUMENTED RESIDUAL RISK',
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

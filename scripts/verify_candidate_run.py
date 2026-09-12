"""Bind a previously built candidate to this source without rebuilding it."""
import hashlib
import json
import os
from pathlib import Path


def job_results(run,jobs,source,repository):
    if run.get('head_sha')!=source or run.get('repository',{}).get('full_name')!=repository:
        raise ValueError('Candidate source or repository mismatch')
    if run.get('path')!='.github/workflows/release.yml' or run.get('event')!='workflow_dispatch' or run.get('status')!='completed':
        raise ValueError('Not a completed release-candidate workflow')
    names={'verification':'Security Verification','build':'build','clean-install':'clean-install',
           'provenance':'provenance','verify-attestation':'verify-attestation'}
    results={}
    for control,name in names.items():
        matches=[job for job in jobs if job.get('name')==name or job.get('name','').endswith(' / '+name)]
        if len(matches)!=1 or matches[0].get('conclusion')!='success':
            raise ValueError('Candidate control did not succeed: '+control)
        results[control]={'result':'success'}
    return results


def main():
    root=Path('release')
    run=json.loads((root/'candidate-run.json').read_text())
    pages=json.loads((root/'candidate-jobs.json').read_text())
    jobs=[job for page in pages for job in page['jobs']]
    results=job_results(run,jobs,os.environ['GITHUB_SHA'],os.environ['GITHUB_REPOSITORY'])
    install=json.loads((root/'clean-install.json').read_text())
    digest=hashlib.sha256((root/'astra-1.0.0-rc.1.zip').read_bytes()).hexdigest()
    if install.get('status')!='PASS' or install.get('artifact_sha256')!=digest:
        raise ValueError('Clean-install evidence is not bound to this candidate')
    with open(os.environ['GITHUB_ENV'],'a') as output:
        output.write('ASTRA_JOB_RESULTS='+json.dumps(results)+'\n')
    print('Candidate jobs, source and clean-install digest verified')


if __name__=='__main__':main()

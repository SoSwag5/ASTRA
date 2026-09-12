"""Release assurance failure cases; no live application storage is used."""
import json
from pathlib import Path
import pytest
from scripts.publication_gate import scan
from scripts.release_security_gate import assess, assess_asvs, REQUIRED
from scripts.verify_sbom_attestation import matches
from scripts.verify_candidate_run import job_results

ROOT = Path(__file__).resolve().parents[2]

def valid_inputs():
    source = 'a'*40
    asvs = json.loads((ROOT/'docs/security/OWASP_ASVS_5.0.0_MAPPING.json').read_text(encoding='utf-8'))
    for row in asvs:
        row['result'] = 'PASS'
        row['applicability'] = 'APPLICABLE'
    review = {'source_commit':source, 'reviewer':'Synthetic Test Reviewer'}
    for name in ('publication_content','codeql_findings_triaged','dependency_review','repository_controls','scorecard_reviewed','residual_risks'):
        review[name] = {'status':'PASS','evidence':'synthetic unit-test evidence'}
    return ({name:{'result':'success'} for name in REQUIRED},source,{'source_commit':source},asvs,review)

@pytest.mark.parametrize('status', ['failure','cancelled','skipped','timed_out',None])
def test_release_gate_rejects_unsuccessful_jobs(status):
    inputs = valid_inputs()
    inputs[0]['provenance'] = {'result':status}
    assert any('provenance' in b for b in assess(*inputs))

def test_release_gate_rejects_missing_job_and_wrong_source():
    inputs = valid_inputs()
    del inputs[0]['build']
    inputs[2]['source_commit'] = 'b'*40
    assert len(assess(*inputs)) >= 2

def test_release_gate_rejects_partial_l1_and_missing_review():
    inputs = valid_inputs()
    next(r for r in inputs[3] if r['level']==1)['result'] = 'PARTIAL'
    inputs[4].clear()
    assert any('L1' in b for b in assess(*inputs))
    assert any('review' in b for b in assess(*inputs))

def test_release_gate_accepts_only_complete_synthetic_prerequisites():
    assert assess(*valid_inputs()) == []

@pytest.mark.parametrize('change', ['blank_reason','blank_evidence','level','substitute','duplicate','applicability'])
def test_asvs_gate_rejects_unjustified_na_and_requirement_tampering(change):
    rows=valid_inputs()[3]
    row=next(r for r in rows if r['level']==1)
    row.update(result='N/A',applicability='NOT APPLICABLE')
    if change=='blank_reason':row['rationale']=' '
    if change=='blank_evidence':row['evidence']=''
    if change=='level':row['level']=3
    if change=='substitute':row['id']='v5.0.0-999.1.1'
    if change=='duplicate':rows[-1]=dict(rows[0])
    if change=='applicability':row['applicability']='APPLICABLE'
    assert assess_asvs(rows)

@pytest.mark.parametrize('value', [None, {}, [None], [{'id':[]}], []])
def test_asvs_gate_rejects_malformed_assessments(value):
    assert assess_asvs(value)

@pytest.mark.parametrize('change',['source','repository','workflow','unfinished','missing','failed','duplicate'])
def test_candidate_review_rejects_unbound_or_unsuccessful_runs(change):
    run={'head_sha':'a'*40,'repository':{'full_name':'fixture/astra'},'path':'.github/workflows/release.yml','event':'workflow_dispatch','status':'completed'}
    jobs=[{'name':name,'conclusion':'success'} for name in ('verification / Security Verification','build','clean-install','provenance','verify-attestation')]
    assert job_results(run,jobs,'a'*40,'fixture/astra')
    if change=='source':run['head_sha']='b'*40
    if change=='repository':run['repository']['full_name']='other/astra'
    if change=='workflow':run['path']='untrusted.yml'
    if change=='unfinished':run['status']='in_progress'
    if change=='missing':jobs.pop()
    if change=='failed':jobs[0]['conclusion']='failure'
    if change=='duplicate':jobs.append(dict(jobs[0]))
    with pytest.raises(ValueError):job_results(run,jobs,'a'*40,'fixture/astra')

@pytest.mark.parametrize('change',['validation','bom','file','manifest'])
def test_release_gate_rejects_artifact_or_sbom_tampering(tmp_path,change):
    import hashlib,zipfile
    from scripts.release_security_gate import artifact_checks
    bom=tmp_path/'bom.json';body=b'{"bomFormat":"CycloneDX","specVersion":"1.7"}'
    bom.write_bytes(body);digest=hashlib.sha256(body).hexdigest()
    validation={'status':'PASS','sha256':digest}
    manifest={'sbom_sha256':digest,'sha256':{'security/sbom.cdx.json':digest,'fixture.txt':hashlib.sha256(b'fixture').hexdigest()}}
    if change=='validation':validation['status']='FAIL'
    bom.with_suffix('.validation.json').write_text(json.dumps(validation))
    artifact=tmp_path/'candidate.zip'
    with zipfile.ZipFile(artifact,'w') as z:
        z.writestr('astra/security/sbom.cdx.json',body if change!='bom' else b'changed')
        z.writestr('astra/fixture.txt',b'fixture' if change!='file' else b'changed')
        z.writestr('astra/release-manifest.json',json.dumps(manifest if change!='manifest' else {}))
    assert artifact_checks(artifact,manifest,bom)

def test_publication_gate_detects_record_table_without_private_fixture():
    headings = ('ID','Company','Role','Status','Result')
    payload = ('| '+' | '.join(headings)+' |\n').encode()
    findings = []
    scan(payload,'tree:docs/fictional-report.md',findings)
    assert findings == [{'location':'tree:docs/fictional-report.md','category':'employment_record_table'}]

def test_sbom_attestation_rejects_wrong_predicate_and_bom():
    bom = {'bomFormat':'CycloneDX','specVersion':'1.7'}
    assert matches(bom,[{'verificationResult':{'statement':{'predicateType':'https://cyclonedx.org/bom','predicate':bom}}}])
    assert not matches(bom,{'predicateType':'https://cyclonedx.org/bom','predicate':{'specVersion':'1.5'}})
    assert not matches(bom,{'predicateType':'untrusted','predicate':bom})

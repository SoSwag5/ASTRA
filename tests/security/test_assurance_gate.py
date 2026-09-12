"""Release assurance failure cases; no live application storage is used."""
import json
from pathlib import Path
import pytest
from scripts.publication_gate import scan
from scripts.release_security_gate import assess, REQUIRED
from scripts.verify_sbom_attestation import matches

ROOT = Path(__file__).resolve().parents[2]

def valid_inputs():
    source = 'a'*40
    asvs = json.loads((ROOT/'docs/security/OWASP_ASVS_5.0.0_MAPPING.json').read_text())
    for row in asvs:
        row['result'] = 'PASS'
    review = {'source_commit':source, 'reviewer':'Synthetic Test Reviewer'}
    for name in ('publication_content','codeql_findings_triaged','repository_controls','scorecard_reviewed','residual_risks'):
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

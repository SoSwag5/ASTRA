from types import SimpleNamespace
from backend.services import experience_years,score
from backend.models import DEFAULTS

def test_experience_bounds():
    assert experience_years('Minimum 1-3 years of experience.')==1
    assert experience_years('5 years of experience preferred. Minimum 1 year of experience.')==1
    assert experience_years('Our company has 20 years of experience. Candidates need 2+ years of experience.')==2
    assert experience_years('3+ years required')==3

def test_unrelated_and_stretch():
    p={'raw_text':'Computer Science SOC SIEM Python Linux'}
    # Issue #41: an out-of-track role with no strong unrelated-profession
    # evidence (AML Analyst is not a configured "unrelated profession") is
    # ranked LOW/stretch rather than hard-excluded -- maximize discovery,
    # rank imperfect fits lower instead of silently discarding them.
    j=SimpleNamespace(title='AML Analyst',description='Risk analysis',location='Dubai',remote_status='',company='Fixture',job_url='')
    r=score(j,p,DEFAULTS);assert r['fit'] in ('Stretch role','Low priority — review');assert not r['hard_blockers']
    # A relevant 0-3 year requirement is normal early-career territory, not
    # a stretch role (non-negotiable outcome #1).
    j.title='SOC Analyst';j.description='3+ years of experience required. SIEM SOC'
    assert score(j,p,DEFAULTS)['fit'] in ('Strong fit','Good fit')
    # Unconfirmed UAE-national wording needs human review even when the
    # underlying match/score is strong -- eligibility uncertainty is
    # surfaced through the recommendation gate, not through score suppression.
    j.title='SOC Analyst (UAE National)';j.description='SOC SIEM'
    assert score(j,p,DEFAULTS)['recommendation']=='NEEDS_REVIEW'

def test_low_bucket_never_maps_to_skip():
    # Phase 13 non-negotiable outcome: LOW is a normal rankable/visible
    # bucket, never the hidden/SKIP disposition reserved for an actual hard
    # rejection. Regression test for a bug found during self-review: the
    # legacy minimum_score/maybe_score thresholds don't align with the new
    # bucket boundaries and could otherwise fall a merely-LOW (not
    # hard-rejected) job all the way through to 'SKIP'.
    p={'raw_text':''}
    j=SimpleNamespace(title='Software Engineer',description='10+ years of React and Node.js required',location='',remote_status='',company='Fixture',job_url='')
    r=score(j,p,{**DEFAULTS,'career_tracks':['CYBERSECURITY']})
    assert r['recall']['fit_assessment']['bucket']=='LOW'
    assert not r['hard_blockers']
    assert r['recommendation']=='NEEDS_REVIEW'

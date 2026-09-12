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
    j=SimpleNamespace(title='AML Analyst',description='Risk analysis',location='Dubai',remote_status='',company='Fixture',job_url='')
    assert score(j,p,DEFAULTS)['fit']=='Outside focus'
    j.title='SOC Analyst';j.description='3+ years of experience required. SIEM SOC'
    assert score(j,p,DEFAULTS)['fit']=='Stretch role'
    j.title='SOC Analyst (UAE National)';j.description='SOC SIEM'
    assert score(j,p,DEFAULTS)['fit']=='Eligibility review'

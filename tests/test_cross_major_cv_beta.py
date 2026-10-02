"""Fictional cross-major PDF uploads; import safety is not ranking-quality evidence."""
import json
import os
import subprocess
import sys

import pytest


CASES = [
    ('Business Administration', 'Market research, Excel, stakeholder analysis', 'Business Analyst'),
    ('Computer Science and Artificial Intelligence', 'Python, machine learning, data analysis', 'Machine Learning Engineer'),
    ('International Relations', 'Policy research, diplomacy, report writing', 'Policy Research Assistant'),
    ('Finance', 'Financial analysis, Excel, accounting', 'Financial Analyst'),
    ('Cybersecurity', 'SIEM, incident response, network security', 'SOC Analyst'),
]


@pytest.mark.parametrize('major,skills,role', CASES, ids=['business','ai','international-relations','finance','cybersecurity'])
@pytest.mark.parametrize('heading', ['TECHNICAL SKILLS', 'SKILLS'], ids=['supported-heading','generic-heading'])
def test_fictional_cv_upload_preserves_major_and_requires_review(tmp_path, major, skills, role, heading):
    script = r'''
import io,json,socket
from reportlab.pdfgen import canvas
from fastapi.testclient import TestClient

case = json.loads(CASE)
buffer = io.BytesIO()
pdf = canvas.Canvas(buffer)
text = pdf.beginText(40,800)
lines = ['Fictional Graduate', 'Fictional City | fictional.example', 'PROFILE',
         'Recent graduate in '+case['major']+'. Interested in '+case['role']+'.',
         case['heading'], 'Core: '+case['skills'], 'EDUCATION',
         'Bachelor degree in '+case['major']+' at Fictional University', 'PROJECTS',
         'A fictional academic project; all examples are synthetic.']
for line in lines: text.textLine(line)
pdf.drawText(text);pdf.showPage();pdf.save()

def blocked(*args, **kwargs): raise AssertionError('CV import attempted network access')
socket.getaddrinfo = blocked
socket.create_connection = blocked
from backend.main import app
from backend.models import Session,Job,Application
from backend.query_planner import plan
with TestClient(app) as client:
    response = client.post('/api/import/cv',files={'file':('fictional-cv.pdf',buffer.getvalue(),'application/pdf')})
    assert response.status_code == 200, response.text
    profile = client.get('/api/profile').json()
    assert case['major'] in profile['raw_text']
    assert profile['name'] == 'Fictional Graduate' and profile['confirmed'] is False
    assert profile['declarations']['extraction_state'] == 'EXTRACTED — NEEDS CONFIRMATION'
    assert profile['email'] == 'UNKNOWN' and profile['phone'] == 'UNKNOWN'
    if case['heading'] == 'TECHNICAL SKILLS':
        assert {s['text'] for s in profile['skills']} == set(case['skills'].split(', '))
    else:
        # The current parser does not infer facts from arbitrary headings.
        # Preserve original text and require corrections; never invent skills.
        assert profile['skills'] == []
    bad = client.post('/api/import/cv',files={'file':('fictional-bad.pdf',b'%PDF-1.4\n/JavaScript (x)\n%%EOF','application/pdf')})
    assert bad.status_code in (400,422), bad.status_code
    after = client.get('/api/profile').json()
    assert after['raw_text'] == profile['raw_text'] and after['confirmed'] is False
with Session() as db:
    assert db.query(Job).count() == db.query(Application).count() == 0
assert plan(case['role'])[0]['query'] == case['role']
print('fictional upload/review/no-action checks passed')
'''.replace('CASE', repr(json.dumps(dict(major=major, skills=skills, role=role, heading=heading))))
    data = tmp_path / 'data'
    env = {**os.environ, 'HUNTER_DATA_DIR':str(data),
           'DATABASE_URL':'sqlite:///'+str(tmp_path/'fictional.db'),
           'APP_TOKEN':'', 'PYTHON_KEYRING_BACKEND':'keyring.backends.fail.Keyring',
           'ASTRA_DEMO_ONLY':'0'}
    result = subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr

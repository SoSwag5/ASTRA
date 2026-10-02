"""Beta review regressions: fictional inputs, disposable storage, no live scan."""
import io
import os
import subprocess
import sys

import pytest
from reportlab.pdfgen import canvas


def text_cv(lines, delayed_summary=False):
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    y = 800
    delayed = []
    for line in lines:
        if delayed_summary and line.startswith('Recent graduate'):
            delayed.append((y, line))
        else:
            pdf.drawString(40, y, line)
        y -= 18
    # Real PDFs can paint a top-of-page paragraph after lower sections.
    for at, line in delayed:
        pdf.drawString(40, at, line)
    pdf.save()
    return output.getvalue()


def escaped_action_pdf():
    content = b'BT /F1 10 Tf 40 700 Td (Fictional graduate CV with enough readable text to reproduce the active content import boundary safely and without real information.) Tj ET'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R /O#70enAction 5 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 6 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        br'<< /S /J#61vaScript /J#53 (app.alert\(fictional\)) >>',
        b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream',
    ]
    data = bytearray(b'%PDF-1.4\n')
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(str(number).encode()+b' 0 obj\n'+obj+b'\nendobj\n')
    xref = len(data)
    data.extend(b'xref\n0 7\n0000000000 65535 f \n')
    for offset in offsets:
        data.extend(f'{offset:010} 00000 n \n'.encode())
    data.extend(b'trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n')
    return bytes(data)


def test_escaped_pdf_action_is_rejected_by_bounded_parser(tmp_path):
    from backend.document_security import extract_pdf, validate_document
    payload = escaped_action_pdf()
    # The raw heuristic is deliberately bypassed; decoded inspection must stop it.
    assert validate_document(payload, 'fictional.pdf', 'pdf') == payload
    path = tmp_path / 'fictional.pdf'
    path.write_bytes(payload)
    with pytest.raises(ValueError, match='safely parsed'):
        extract_pdf(path)


def test_layout_reading_order_keeps_summary_before_skills(tmp_path):
    from backend.document_security import extract_pdf
    path = tmp_path / 'fictional-layout.pdf'
    path.write_bytes(text_cv([
        'Fictional Graduate', 'Fictional City | fictional.example', 'PROFILE',
        'Recent graduate in Finance seeking entry-level financial analysis.',
        'TECHNICAL SKILLS', 'Core: Excel, financial analysis', 'EDUCATION',
        'Bachelor degree in Finance from Fictional University', 'CERTIFICATIONS AND COURSES',
        'Fictional spreadsheet course',
    ], delayed_summary=True))
    extracted = extract_pdf(path)
    assert extracted.index('Recent graduate') < extracted.index('TECHNICAL SKILLS')


@pytest.mark.parametrize('heading', ['SKILLS', 'Skills:', 'technical skills', '  Key   Skills  '])
def test_explicit_skill_aliases_accept_plain_lists_without_category(heading):
    from backend.cv_sections import parse_sections, skill_facts
    sections = parse_sections([heading, 'Excel, financial analysis; Python', '- Stakeholder analysis',
                               'Skills', 'excel', 'Languages', 'English', 'Education', 'Fictional degree'])
    assert [text for text, context in skill_facts(sections['TECHNICAL SKILLS'])] == [
        'Excel', 'financial analysis', 'Python', 'Stakeholder analysis']
    assert sections['EDUCATION'] == ['Fictional degree']


def test_section_aliases_preserve_repeated_sections_and_body_text():
    from backend.cv_sections import parse_sections
    sections = parse_sections(['Professional Summary:', 'Recent graduate in Finance.',
                               'Work Experience', 'Fictional internship', 'Projects',
                               'Skills are important in this project.', 'Academic Projects',
                               'Second fictional project', 'Courses', 'Fictional course'])
    assert sections['PROFILE'] == ['Recent graduate in Finance.']
    assert sections['EXPERIENCE'] == ['Fictional internship']
    assert sections['PERSONAL PROJECTS'] == ['Skills are important in this project.', 'Second fictional project']
    assert sections['CERTIFICATIONS AND COURSES'] == ['Fictional course']


@pytest.mark.parametrize('key', ['/OpenAction', '/AA', '/JavaScript', '/JS', '/EmbeddedFiles', '/EF', '/XFA'])
def test_decoded_pdf_policy_rejects_unsupported_keys(key):
    from pypdf.generic import DictionaryObject, NameObject, NullObject
    from backend.pdf_policy import require_inert_pdf
    class Reader:
        trailer = DictionaryObject({NameObject(key): NullObject()})
    with pytest.raises(ValueError, match='unsupported'):
        require_inert_pdf(Reader())


def test_pdf_object_traversal_terminates_cycles_and_limits_depth():
    from pypdf.generic import DictionaryObject, NameObject, ArrayObject
    from backend.pdf_policy import require_inert_pdf
    class Reader: pass
    reader = Reader()
    root = DictionaryObject(); root[NameObject('/Parent')] = root
    reader.trailer = root
    require_inert_pdf(reader)
    value = ArrayObject()
    for _ in range(105): value = ArrayObject([value])
    reader.trailer = DictionaryObject({NameObject('/Nested'): value})
    with pytest.raises(ValueError, match='complexity'): require_inert_pdf(reader)


def test_rejected_import_and_legacy_original_download_preserve_data(tmp_path):
    good = text_cv(['Fictional Graduate', 'Fictional City | fictional.example', 'Summary',
                    'Recent graduate in Finance with a fictional spreadsheet project.',
                    'Skills', 'Excel, financial analysis', 'Education', 'Fictional finance degree'])
    (tmp_path / 'good.pdf').write_bytes(good)
    (tmp_path / 'active.pdf').write_bytes(escaped_action_pdf())
    script = '''
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.models import DATA
with TestClient(app) as client:
    good = Path(GOOD).read_bytes(); active = Path(ACTIVE).read_bytes()
    assert client.post('/api/import/cv',files={'file':('fictional.pdf',good,'application/pdf')}).status_code == 200
    before = client.get('/api/profile').json()
    assert client.post('/api/import/cv',files={'file':('active.pdf',active,'application/pdf')}).status_code == 400
    assert client.get('/api/profile').json() == before
    assert (DATA/'master.pdf').read_bytes() == good
    assert client.get('/api/files/master.pdf').status_code == 200
    (DATA/'master.pdf').write_bytes(active)  # fictional original stored by an older beta
    assert client.get('/api/files/master.pdf').status_code == 400
    assert (DATA/'master.pdf').read_bytes() == active  # never silently delete an original
    assert client.get('/api/profile').json() == before
'''.replace('GOOD', repr(str(tmp_path/'good.pdf'))).replace('ACTIVE', repr(str(tmp_path/'active.pdf')))
    env = {**os.environ,'DATABASE_URL':'sqlite:///'+str(tmp_path/'fictional.db'),
           'HUNTER_DATA_DIR':str(tmp_path/'data'),'APP_TOKEN':'','ASTRA_DEMO_ONLY':'0'}
    result = subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('origin', [
    'http://localhost:5173', 'http://localhost:5174',
    'http://localhost:8787.attacker.example', 'null',
])
def test_foreign_origin_cannot_mutate_jobs(tmp_path, origin):
    script = '''
from fastapi.testclient import TestClient
from backend.main import app
with TestClient(app) as client:
    before = client.get('/api/jobs').json()
    response = client.post('/api/jobs', json={'company':'Fictional Company','title':'Fictional Analyst','location':'Dubai','description':'Fictional'}, headers={'Origin':ORIGIN})
    assert response.status_code == 403, response.status_code
    assert client.get('/api/jobs').json() == before
'''.replace('ORIGIN', repr(origin))
    env = {**os.environ, 'DATABASE_URL':'sqlite:///'+str(tmp_path/'fictional.db'),
           'HUNTER_DATA_DIR':str(tmp_path/'data'), 'HUNTER_PORT':'8787',
           'APP_TOKEN':'', 'ASTRA_DEV_ORIGIN':'', 'ASTRA_DEMO_ONLY':'0'}
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr

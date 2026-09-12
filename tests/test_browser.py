import pytest
from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from types import SimpleNamespace
from backend.models import Base,ApprovedAnswer,Application,Job
from backend.browser import fill_form
from backend.policy import norm
from backend.adapters import ADAPTERS

@pytest.mark.parametrize('kind',['greenhouse','lever','ashby'])
def test_ats_dry_run(kind,tmp_path,monkeypatch):
    import backend.browser as browser
    monkeypatch.setattr(browser,'DATA',tmp_path);(tmp_path/'cv.pdf').write_bytes(b'%PDF-1.4 test fixture')
    e=create_engine('sqlite://');Base.metadata.create_all(e)
    with Session(e) as db, sync_playwright() as pw:
        j=Job(company='Fixture',title='SOC');db.add(j);db.flush();a=Application(job_id=j.id);db.add(a);db.flush()
        b=pw.chromium.launch(headless=True);page=b.new_page()
        page.set_content(f'<h1>{kind} fixture</h1><form onsubmit="document.body.dataset.submitted=1;return false"><label for="name">Full name</label><input id="name" required><label for="email">Email</label><input id="email" type="email" required><label for="resume">Resume</label><input id="resume" type="file" required><button type="submit">Submit application</button></form>')
        unknown=fill_form(page,{'name':'Alex Example','email':'test@example.com'},db,a,SimpleNamespace(pdf_path='cv.pdf'))
        assert not unknown;assert page.locator('#name').input_value()=='Alex Example';assert page.locator('#resume').evaluate('(x)=>x.files.length')==1
        assert page.locator(ADAPTERS[kind]().submit_selector()).count()==1
        assert page.locator('body').get_attribute('data-submitted') is None
        page.screenshot(path=str(tmp_path/f'{kind}.png'));assert (tmp_path/f'{kind}.png').exists();b.close()
def test_sensitive_browser_block(tmp_path):
    e=create_engine('sqlite://');Base.metadata.create_all(e)
    with Session(e) as db,sync_playwright() as pw:
        j=Job(company='Fixture',title='SOC');db.add(j);db.flush();a=Application(job_id=j.id);db.add(a);db.flush()
        b=pw.chromium.launch();page=b.new_page();page.set_content('<label for="q">Are you authorized to work?</label><input id="q" required>')
        assert fill_form(page,{'name':'Candidate Example'},db,a,None)==['Are you authorized to work?'];assert page.locator('#q').input_value()==''
        page.set_content('<h1>Verify you are human</h1>')
        with pytest.raises(ValueError):fill_form(page,{},db,a,None)
        b.close()

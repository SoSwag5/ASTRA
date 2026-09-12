"""Offline form rehearsal with isolated temporary data and synthetic identity."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from playwright.sync_api import sync_playwright
from .models import Base,Job,Application
from .browser import fill_form

def rehearse():
    with tempfile.TemporaryDirectory() as folder:
        pdf=Path(folder)/'synthetic.pdf'
        from reportlab.pdfgen.canvas import Canvas
        c=Canvas(str(pdf)); c.drawString(72,720,'Synthetic rehearsal CV'); c.save()
        engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
        with Session(engine) as db,sync_playwright() as pw:
            j=Job(company='Offline rehearsal',title='Synthetic vacancy');db.add(j);db.flush()
            a=Application(job_id=j.id);db.add(a);db.flush()
            browser=pw.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                page.route('**/*',lambda route:route.abort())
                page.set_content('<form onsubmit="document.body.dataset.submitted=1;return false"><label for="n">Full name</label><input id="n" required><label for="e">Email</label><input id="e" required><label for="r">Resume</label><input id="r" type="file" required><button type="submit">Submit</button></form>')
                unknown=fill_form(page,{'name':'Synthetic Candidate','email':'rehearsal@example.invalid'},db,a,SimpleNamespace(pdf_path=str(pdf)))
                ok=not unknown and page.locator('#r').evaluate('(e)=>e.files.length')==1 and page.locator('body').get_attribute('data-submitted') is None
                return {'ok':ok,'submitted':False,'external_requests':0,'message':'Synthetic name, email, and CV filled locally. Submit was never clicked.'}
            finally: browser.close()

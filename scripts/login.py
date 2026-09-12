"""User-operated first login for a permitted career site; never submits forms."""
import sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from playwright.sync_api import sync_playwright
from backend.models import Session,SiteAdapter,DATA,initialize
from backend.policy import validate_url,host,linkedin

raise SystemExit('App-managed employer login is disabled. Open the employer site in your own browser. The app does not store new employer sessions.')
initialize()
url=input('Permitted career-site URL (LinkedIn is not supported): ').strip()
validate_url(url)
with Session() as db:
    site=db.scalar(select(SiteAdapter).where(SiteAdapter.domain==host(url)))
    if not site or not site.enabled or not site.permitted:
        raise SystemExit('Enable and permit this exact domain in Settings first.')
profile=DATA/'browser_profiles'/hashlib.sha256(host(url).encode()).hexdigest()[:16]
with sync_playwright() as pw:
    context=pw.chromium.launch_persistent_context(str(profile),headless=False)
    def route(r):
        if linkedin(r.request.url): r.abort()
        else: r.continue_()
    context.route('**/*',route)
    page=context.pages[0] if context.pages else context.new_page()
    page.goto(url,wait_until='domcontentloaded')
    input('Complete login yourself. Do not run another browser task. Press Enter here when finished: ')
    context.close()

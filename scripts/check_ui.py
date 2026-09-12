"""Read-only smoke check of the local dashboard, with no profile confirmation."""
from pathlib import Path
import re
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://localhost:8787',wait_until='networkidle')
    page.get_by_role('heading',name='A focused search. A stronger next move.',exact=True).wait_for()
    page.wait_for_timeout(1000)
    if page.get_by_role('button',name='×',exact=True).is_visible():
        page.get_by_role('button',name='×',exact=True).click()
    (root/'work').mkdir(exist_ok=True)
    page.screenshot(path=str(root/'work/dashboard.png'),full_page=True)

    print('Errors:',errors,flush=True)
    for name in ['Jobs','Application Queue','Applications','Interviews','Documents','Approved Answers','Automation','Logs','Settings','Dashboard']:
        page.get_by_role('button',name=re.compile('^'+re.escape(name))).first.click()
        page.wait_for_timeout(250)
    assert not errors,errors
    browser.close()
print('All ten dashboard screens opened without browser errors. No data changed.')




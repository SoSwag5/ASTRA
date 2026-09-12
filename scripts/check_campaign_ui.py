"""Read-only live UI checks: no synthetic data or application changes."""
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://localhost:8787',wait_until='networkidle');page.keyboard.press('Escape')
    page.get_by_role('heading',name='Your next moves',exact=True).wait_for()
    page.screenshot(path=str(Path('work/campaign-today.png')),full_page=True)
    page.get_by_role('tab',name='Search elsewhere',exact=True).click()
    page.get_by_role('link',name='Open',exact=False).first.wait_for()
    assert page.get_by_text('LinkedIn',exact=True).is_visible()
    page.get_by_role('button',name='Progress',exact=True).click()
    page.get_by_role('heading',name='Outcomes, with the right context').wait_for()
    page.screenshot(path='work/campaign-progress.png',full_page=True)
    page.get_by_role('button',name='Applications',exact=True).click()
    page.get_by_text('5 tracked · 5 submitted',exact=True).wait_for()
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_role('button',name='Today',exact=True).click()
    page.get_by_role('heading',name='Your next moves',exact=True).wait_for()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path='work/campaign-mobile.png',full_page=True)
    assert not errors,errors
    browser.close();print('Today, portals, progress, five applications and mobile width passed.')

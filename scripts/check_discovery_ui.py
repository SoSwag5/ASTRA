"""Read-only local interface check. Does not scan, apply, or edit records."""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    try:
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://localhost:8787',wait_until='networkidle')
        page.keyboard.press('Escape')
        page.get_by_role('button',name='Discovery',exact=True).click()
        control=page.get_by_role('combobox',name='Discovery sort order')
        control.wait_for();assert control.input_value()=='uae_first'
        control.select_option('date_found');control.select_option('match_score');control.select_option('uae_first')
        page.get_by_role('button',name=re.compile('^Jobs')).first.click()
        control=page.get_by_role('combobox',name='Job sort order')
        assert control.input_value()=='uae_first'
        control.select_option('date_found');control.select_option('uae_first')
        assert not errors,errors
        target=Path(__file__).resolve().parents[1]/'work'/'uae-sorting.png';target.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(target),full_page=True)
        print('Discovery and Jobs sorting controls passed; no browser errors or application mutations.')
    finally: browser.close()

from pathlib import Path
from playwright.sync_api import sync_playwright
import json
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://localhost:8787',wait_until='networkidle');page.keyboard.press('Escape')
 page.get_by_role('heading',name='Your next moves',exact=True).wait_for()
 assert page.get_by_text('Last discovery:',exact=False).is_visible()
 page.get_by_role('button',name='Discovery',exact=True).click()
 page.get_by_role('heading',name='Opportunities to review',exact=True).wait_for()
 assert page.get_by_role('combobox',name='Search policy',exact=True).input_value()=='BALANCED'
 page.get_by_role('button',name='Near misses (0)',exact=True).click()
 page.get_by_text('Latest scan evidence',exact=False).click()
 page.get_by_role('heading',name='Successive filtering steps').wait_for()
 page.screenshot(path='work/recall-discovery-desktop.png',full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 page.screenshot(path='work/recall-discovery-mobile.png',full_page=True)
 page.get_by_role('button',name='Today',exact=True).click()
 page.get_by_role('tab',name='Search elsewhere',exact=True).click()
 page.get_by_text('Recruitment agencies',exact=False).first.wait_for()
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 page.screenshot(path='work/recall-portals-mobile.png',full_page=True)
 page.set_viewport_size({'width':1440,'height':1000})
 page.get_by_role('button',name='Settings',exact=True).click()
 page.get_by_role('heading',name='Keep your search running',exact=True).wait_for()
 assert page.get_by_text('Windows task: Not installed',exact=False).is_visible()
 page.get_by_role('button',name='Applications',exact=True).click()
 page.get_by_text('5 tracked · 5 submitted',exact=True).wait_for()
 assert not errors,errors
 browser.close()
 Path('work/recall-ui-check.json').write_text(json.dumps({'desktop':True,'mobile_width_390':True,'search_policy_default':'BALANCED','near_miss_empty_state':True,'funnel':True,'agencies':True,'windows_task_installed':False,'existing_applications':5,'browser_errors':errors},indent=2),encoding='utf-8')
 print('Desktop, mobile, funnel, agencies, scheduler state and five applications verified; no submissions or saved test jobs.')

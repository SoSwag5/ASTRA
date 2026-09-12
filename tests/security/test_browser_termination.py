"""Real Chromium on a disposable server; exercise built product state cleanup."""
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import pytest
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[2]
KEY='synthetic-fixture-access-key-not-a-real-secret'


@pytest.mark.parametrize('protected',[False,True])
def test_private_browser_state_clears_on_close_and_offline(tmp_path,protected):
    assert (ROOT/'frontend/dist/index.html').is_file(), 'Build frontend before browser acceptance'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env={**os.environ,'APP_TOKEN':KEY if protected else '',
         'HUNTER_PORT':str(port),'HUNTER_DATA_DIR':str(tmp_path/'data'),
         'DATABASE_URL':'sqlite:///'+str(tmp_path/'browser.db')}
    process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(port),'--no-access-log','--no-proxy-headers'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def request(path,data=None,token='',method=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        with urllib.request.urlopen(req,timeout=3) as r:return json.load(r)
    try:
        for _ in range(100):
            try:request('/api/access');break
            except OSError:time.sleep(.1)
        else:raise AssertionError('Disposable server did not start')
        token=request('/api/access',{'key':KEY})['token'] if protected else ''
        request('/api/jobs',{'company':'Fictional Closure Company','title':'PRIVATE_BROWSER_MARKER','description':'Synthetic fixture'},token)
        request('/api/settings',{'wizard_step':10},token,method='PUT')
        with sync_playwright() as p:
            browser=p.chromium.launch()
            context=browser.new_context()
            page=context.new_page()
            page.goto(base)
            def open_workspace():
                if protected:page.get_by_label('Access key',exact=True).fill(KEY)
                page.get_by_role('button',name='Open workspace',exact=True).click()
            if protected:open_workspace()
            expect(page.get_by_role('button',name='Close workspace',exact=True)).to_be_visible()
            page.get_by_role('button',name=re.compile(r'^Jobs\b')).click()
            expect(page.get_by_role('button',name='PRIVATE_BROWSER_MARKER',exact=True)).to_be_visible()
            storage=page.evaluate('JSON.stringify({local:{...localStorage},session:{...sessionStorage}})')
            assert KEY not in storage and 'PRIVATE_BROWSER_MARKER' not in storage
            page.get_by_role('button',name='Close workspace',exact=True).click()
            expect(page.get_by_role('heading',name='Open ASTRA')).to_be_visible()
            assert 'PRIVATE_BROWSER_MARKER' not in page.locator('body').inner_text()
            open_workspace()
            expect(page.get_by_role('button',name='Close workspace',exact=True)).to_be_visible()
            page.get_by_role('button',name=re.compile(r'^Jobs\b')).click()
            expect(page.get_by_role('button',name='PRIVATE_BROWSER_MARKER',exact=True)).to_be_visible()
            context.set_offline(True)
            expect(page.get_by_role('heading',name='Open ASTRA')).to_be_visible()
            assert 'PRIVATE_BROWSER_MARKER' not in page.locator('body').inner_text()
            assert page.evaluate('sessionStorage.getItem("token")') is None
            context.set_offline(False)
            browser.close()
    finally:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)

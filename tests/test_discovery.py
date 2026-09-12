import pytest,httpx
from backend.discovery import discovery_reason
from backend.models import DEFAULTS
from backend import adapters

@pytest.mark.parametrize('title,location,keep',[
    ('SOC Analyst L1','Dubai',True),('GRC Analyst','Abu Dhabi, UAE',True),
    ('Cybersecurity Graduate','United Arab Emirates',True),
    ('Security Analyst','Remote',True),('Security Analyst','United States - Remote',False),
    ('Security Analyst','Remote - EMEA',True),('Security Analyst','Singapore',False),
    ('AML Analyst','Dubai',False),('Backend Engineer','Dubai',False),
    ('Senior SOC Analyst','Dubai',False),('Security Guard','Dubai',False),
])
def test_screen(title,location,keep):
    assert (discovery_reason({'title':title,'location':location},DEFAULTS) is None)==keep

@pytest.mark.parametrize('body,content_type,blocked',[
    ('{"jobs":[{"id":"1","title":"Security Analyst","description":"Cloudflare and MFA"}]}','application/json',False),
    ('<h1>Verify you are human</h1>','text/html',True),
    ('{"message":"Verify you are human"}','application/json',True),
])
def test_posting_payload_vs_challenge(monkeypatch,body,content_type,blocked):
    monkeypatch.setattr(adapters,'validate_url',lambda url: url)
    class Client:
        def __init__(self,**kw): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def stream(self,method,url):
            from contextlib import nullcontext
            return nullcontext(httpx.Response(200,text=body,headers={'content-type':content_type},request=httpx.Request(method,url)))
    monkeypatch.setattr(adapters.httpx,'Client',Client)
    if blocked:
        with pytest.raises(ValueError): adapters.fetch('https://example.com')
    else: assert adapters.fetch('https://example.com').status_code==200

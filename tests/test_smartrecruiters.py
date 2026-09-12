import gzip,httpx
from contextlib import nullcontext
from backend import adapters

def test_compressed_feed(monkeypatch):
    body=b'{"jobs":[{"id":"1","title":"Cloudflare Engineer"}]}'
    class Client:
        def __init__(self,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def stream(self,method,url):
            return nullcontext(httpx.Response(200,content=gzip.compress(body),headers={'content-type':'application/json','content-encoding':'gzip'},request=httpx.Request(method,url)))
    monkeypatch.setattr(adapters,'validate_url',lambda url: url)
    monkeypatch.setattr(adapters.httpx,'Client',Client)
    assert adapters.fetch('https://example.com').json()['jobs'][0]['id']=='1'

def test_public_uae_pagination(monkeypatch):
    calls=[]
    class Response:
        def __init__(self,data): self.data=data
        def json(self): return self.data
    def fetch(url):
        calls.append(url)
        if '?' in url:
            assert 'destination=PUBLIC' in url and 'country=ae' in url
            indexes=range(100) if 'offset=0' in url else [100]
            return Response({'totalFound':101,'content':[{'id':str(i),'name':'SOC Analyst'} for i in indexes]})
        ident=url.rsplit('/',1)[-1]
        return Response({'id':ident,'name':'SOC Analyst','location':{'country':'ae','city':'Dubai'},'jobAd':{'sections':{'qualifications':{'text':'<p>SIEM required</p>'}}}})
    monkeypatch.setattr(adapters,'fetch',fetch)
    jobs=adapters.discover('smartrecruiters','Fixture')
    assert len(jobs)==101 and jobs[-1]['source_job_id']=='100'
    assert jobs[0]['description']=='SIEM required'
    assert all('api.smartrecruiters.com/v1/companies/Fixture/postings' in u for u in calls)

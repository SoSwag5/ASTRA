import re,json
from datetime import datetime,timezone
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from .policy import validate_url, host, linkedin, challenge

def fetch(url):
    validate_url(url)
    with httpx.Client(timeout=25,trust_env=False,follow_redirects=False,headers={'User-Agent':'ASTRA/1.0 personal-career-assistant'}) as c:
        for _ in range(5):
            with c.stream('GET',url) as stream:
                chunks=[]; size=0
                for chunk in stream.iter_bytes():
                    size+=len(chunk)
                    if size>5_000_000: raise ValueError('Response too large')
                    chunks.append(chunk)
                # iter_bytes already decompresses the body. Do not decode it twice.
                headers={k:v for k,v in stream.headers.items() if k.lower() not in ('content-encoding','content-length')}
                r=httpx.Response(stream.status_code,headers=headers,content=b''.join(chunks),request=stream.request)
            if r.is_redirect: url=urljoin(url,r.headers['location']); validate_url(url); continue
            r.raise_for_status()
            if len(r.content)>5_000_000: raise ValueError('Response too large')
            # Job descriptions can mention Cloudflare or MFA as skills. Only a
            # validated public posting payload is exempt from HTML challenge checks.
            posting_payload=False
            if 'application/json' in r.headers.get('content-type',''):
                try:
                    payload=r.json()
                    rows=payload.get('jobs',payload.get('content')) if isinstance(payload,dict) else payload
                    posting_payload=isinstance(rows,list) and all(isinstance(x,dict) and ('title' in x or 'text' in x or 'name' in x) and 'id' in x for x in rows)
                    if isinstance(payload,dict) and payload.get('id') and (isinstance(payload.get('jobAd',{}).get('sections'),dict) or ('title' in payload and 'content' in payload)): posting_payload=True
                except ValueError: pass
            if not posting_payload and challenge(r.text): raise ValueError('NEEDS HUMAN ACTION: site protection detected')
            return r
    raise ValueError('Too many redirects')
def clean(s):
    import html
    return BeautifulSoup(html.unescape(html.unescape(s or '')),'html.parser').get_text('\n',strip=True)
def discover(kind,board,url='',cfg=None):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',board) and kind!='generic': raise ValueError('Invalid board name')
    if kind=='smartrecruiters':
        # Public UAE listings only. No credentials, candidate data or application APIs.
        base=f'https://api.smartrecruiters.com/v1/companies/{board}/postings'
        summaries=[]
        for offset in range(0,500,100):
            payload=fetch(f'{base}?country=ae&destination=PUBLIC&limit=100&offset={offset}').json()
            rows=payload['content']; summaries.extend(rows)
            if offset+len(rows)>=payload['totalFound'] or not rows: break
        else: raise ValueError('UAE posting limit reached; narrow this company source before scanning')
        output=[]
        for item in summaries:
            ident=str(item['id'])
            if not re.fullmatch(r'[a-zA-Z0-9-]+',ident): raise ValueError('Invalid posting identifier')
            detail=fetch(f'{base}/{ident}').json()
            loc=detail.get('location',item.get('location',{}))
            if str(loc.get('country','')).lower() not in ('ae','uae','united arab emirates'): continue
            sections=detail.get('jobAd',{}).get('sections',{})
            description='\n'.join(clean(v.get('text','')) for v in sections.values() if isinstance(v,dict))
            output.append(dict(company=board,title=detail.get('name',item['name']),location=', '.join(filter(None,[loc.get('city'),loc.get('region'),'United Arab Emirates'])),job_url=detail.get('postingUrl') or f'https://jobs.smartrecruiters.com/{board}/{ident}',description=description,source='SmartRecruiters',source_job_id=ident,date_posted=detail.get('releasedDate',item.get('releasedDate','')),remote_status='Remote' if loc.get('remote') else 'UNKNOWN'))
        return output
    if kind=='greenhouse':
        # Delegates to the common job-provider framework (issue #38);
        # backend/job_providers/greenhouse.py owns Greenhouse's own
        # endpoint/schema/budget rules. title_hints is a plain configured
        # keyword list (never recall.py's role classifier) used only to
        # prioritize a bounded detail-fetch budget when the full board is
        # too large to fetch with content inline.
        from .job_providers.compatibility import to_legacy_items
        from .job_providers.contracts import FetchContext
        from .job_providers.registry import get_provider
        cfg=cfg or {}
        hints=tuple(cfg.get('target_roles',[]))+tuple(cfg.get('campaign',{}).get('adjacent_roles',[]))
        batch=get_provider('greenhouse').fetch(FetchContext(title_hints=hints),board)
        return to_legacy_items(batch)
    if kind=='lever':
        rows=fetch(f'https://api.lever.co/v0/postings/{board}?mode=json').json()
        return [dict(company=board,title=x['text'],location=' / '.join(x.get('categories',{}).get('allLocations') or [x.get('categories',{}).get('location','UNKNOWN')]),job_url=x['hostedUrl'],description=clean(x.get('description','')+' '.join(y.get('content','') for y in x.get('lists',[]))),source='Lever',source_job_id=x['id'],remote_status=x.get('workplaceType','UNKNOWN'),date_posted=datetime.fromtimestamp(x['createdAt']/1000,timezone.utc).isoformat() if x.get('createdAt') else '') for x in rows]
    if kind=='ashby':
        rows=fetch(f'https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true').json()['jobs']
        return [dict(company=board,title=x['title'],location=x.get('location','UNKNOWN'),job_url=x['jobUrl'],description=x.get('descriptionPlain',''),source='Ashby',source_job_id=x['id'],date_posted=x.get('publishedAt',''),remote_status='Remote' if x.get('isRemote') else 'On-site') for x in rows if x.get('isListed',True)]
    return [parse_url(url)]
def parse_url(url):
    soup=BeautifulSoup(fetch(url).text,'html.parser')
    for script in soup.select('script[type="application/ld+json"]'):
        try: data=json.loads(script.string or '')
        except (ValueError,TypeError): continue
        rows=data if isinstance(data,list) else data.get('@graph',[data])
        for x in rows:
            if x.get('@type')=='JobPosting':
                loc=x.get('jobLocation',{}); loc=loc[0] if isinstance(loc,list) and loc else loc
                addr=loc.get('address',{}) if isinstance(loc,dict) else {}
                return dict(company=x.get('hiringOrganization',{}).get('name',host(url)),title=x.get('title','Untitled'),description=clean(x.get('description','')),location=', '.join(str(v) for v in addr.values()) or 'UNKNOWN',job_url=url,source='Company',date_posted=x.get('datePosted',''),closing_date=x.get('validThrough',''))
    raise ValueError('No structured job found. Paste the description to import this job.')

class FormAdapter:
    """Deterministic configured selectors, never model-generated browser actions."""
    def __init__(self,config=None): self.config=config or {}
    def submit_selector(self): return self.config.get('submit_selector','button[type="submit"]')
    def success_selector(self): return self.config.get('success_selector','')
class GreenhouseAdapter(FormAdapter): pass
class LeverAdapter(FormAdapter): pass
class AshbyAdapter(FormAdapter): pass
ADAPTERS={'greenhouse':GreenhouseAdapter,'lever':LeverAdapter,'ashby':AshbyAdapter,'generic':FormAdapter}

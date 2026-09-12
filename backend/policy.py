import re, socket, ipaddress
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from difflib import SequenceMatcher

STATUSES={'FOUND','ANALYZED','HIGH_PRIORITY','MAYBE','SKIP','READY_TO_APPLY','NEEDS_REVIEW','NEEDS_HUMAN_ACTION','APPLYING','APPLIED','FAILED','INTERVIEW','REJECTED','WITHDRAWN','OFFER'}
TERMINAL={'APPLIED','INTERVIEW','REJECTED','WITHDRAWN','OFFER'}
def norm(s):
    import unicodedata
    return re.sub(r'[^\w]+',' ',unicodedata.normalize('NFKC',s).casefold(),flags=re.UNICODE).strip()
def host(url): return (urlsplit(url).hostname or '').lower().rstrip('.')
def linkedin(url): return host(url)=='linkedin.com' or host(url).endswith('.linkedin.com') or host(url)=='lnkd.in'
def canonical(url):
    if not url: return ''
    p=urlsplit(url)
    query=urlencode(sorted((k,v) for k,v in parse_qsl(p.query) if not k.startswith(('utm_','trk')) and k not in ('ref','source')))
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),query,''))
def validate_url(url,resolve=True):
    p=urlsplit(url)
    if p.scheme not in ('https','http') or not p.hostname or p.username or p.password: raise ValueError('Use a public HTTP(S) URL without credentials')
    if linkedin(url): raise ValueError('LinkedIn is manual-only. Paste the job description instead.')
    if p.port not in (None,80,443): raise ValueError('Only public web ports are permitted')
    if resolve:
        for item in socket.getaddrinfo(p.hostname,p.port or 443):
            if not ipaddress.ip_address(item[4][0]).is_global: raise ValueError('Private network addresses are blocked')
    return url
def duplicate(a,b):
    if a.get('job_url') and canonical(a['job_url'])==canonical(b.get('job_url','')): return True
    if a.get('source_job_id') and a.get('source')==b.get('source') and a['source_job_id']==b.get('source_job_id'): return True
    if a.get('source_job_id') and b.get('source_job_id') and a.get('source')==b.get('source') and a['source_job_id']!=b['source_job_id']: return False
    same=norm(a.get('company',''))==norm(b.get('company','')) and bool(norm(a.get('company','')))
    title=SequenceMatcher(None,norm(a.get('title','')),norm(b.get('title',''))).ratio()
    loc=norm(a.get('location',''))==norm(b.get('location',''))
    desc=SequenceMatcher(None,a.get('description','')[:12000],b.get('description','')[:12000]).ratio() if len(a.get('description',''))>100 else 0
    return same and ((title>.92 and loc) or (title>.75 and desc>.92))
SENSITIVE=re.compile(r'citizen|nationality|visa|sponsor|authoriz|criminal|disabil|ethnic|gender|veteran|clearance|legal|attest|consent|salary|compensation|conflict|race\b|background|agree|certify|acknowledge',re.I)
def sensitive(q): return bool(SENSITIVE.search(q))

DEMOGRAPHIC=re.compile(r'disabil|health|ethnic|race\b|religio|sexual|gender|veteran|criminal|marital|family status|birth|national ident|passport|social security|personality|psychometric',re.I)
def demographic(q): return bool(DEMOGRAPHIC.search(q))

def live_assessment(text):
    return bool(re.search(r'psychometric|personality (?:test|assessment)|coding (?:test|assessment)|technical (?:test|assessment)|screening quiz|timed assessment|employer assessment',text,re.I))
def challenge(text):
    return bool(re.search(r'captcha|verify you are human|checking your browser|cloudflare|two.factor|multi.factor|verification code|one.time (?:password|code)|authenticator|sign in to continue|log in to continue',text,re.I))
def transition(old,new):
    if new not in STATUSES: raise ValueError('Invalid status')
    allowed={'APPLIED':{'INTERVIEW','REJECTED','WITHDRAWN','OFFER'},'INTERVIEW':{'INTERVIEW','REJECTED','WITHDRAWN','OFFER'},'OFFER':{'WITHDRAWN'},'REJECTED':set(),'WITHDRAWN':set()}
    if old in allowed and new!=old and new not in allowed[old]: raise ValueError('Cannot move a completed application back into submission queue')
def submission_gate(job,app,cfg,site,count,resume,unknown=False):
    blockers=['External browser submission is disabled in this release; review and submit in your own browser']
    if linkedin(job.job_url) or job.source.lower()=='linkedin': blockers.append('LinkedIn manual-submit only')
    if cfg['autopilot']!='AUTO_ALLOWED': blockers.append('Autopilot does not allow submission')
    if not site or not site.enabled or not site.auto_submit or not site.permitted or site.domain!=host(job.job_url): blockers.append('Domain not explicitly permitted for auto submission')
    if job.match_score<cfg['minimum_score'] or job.recommendation not in ('APPLY','HIGH_PRIORITY'): blockers.append('Match or requirements need review')
    if job.duplicate_of: blockers.append('Duplicate job')
    if app.submission_attempted or app.status in TERMINAL: blockers.append('Submission already attempted; human reconciliation required')
    if count>=cfg['daily_limit']: blockers.append('Daily application limit reached')
    if not resume: blockers.append('Generate CV first')
    if unknown: blockers.append('Unanswered required or sensitive question')
    if app.attempts>cfg['max_retries']: blockers.append('Retry limit reached')
    if host(job.job_url) in cfg['blocked_domains'] or job.company.lower() in [x.lower() for x in cfg['blocked_companies']]: blockers.append('Blocked company or domain')
    return blockers

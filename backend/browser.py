import threading,re,hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from playwright.sync_api import sync_playwright
from .models import *
from .policy import *
from .services import answer_for,candidate,set_status
from .adapters import ADAPTERS

LOCK=threading.Lock()
def screenshot(page,path):
    page.screenshot(path=str(path),full_page=True,mask=page.locator('input[type=password],input[autocomplete=one-time-code]').all())
def fill_form(page,p,db,application,cv):
    text=page.locator('body').inner_text()
    if live_assessment(text): raise ValueError('Live assessment: answer directly under the employer rules; automation is disabled')
    if challenge(text) or page.locator('iframe[src*="captcha"],input[autocomplete="one-time-code"],input[type="password"]').count(): raise ValueError('NEEDS HUMAN ACTION: authentication or challenge')
    unknown=[]
    for field in page.locator('input,textarea,select').all():
        if not field.is_visible() or not field.is_enabled(): continue
        typ=field.get_attribute('type') or 'text'
        if typ in ('hidden','submit','button','reset'): continue
        fid=field.get_attribute('id'); name=field.get_attribute('name') or ''
        label=field.get_attribute('aria-label') or field.get_attribute('placeholder') or ''
        if fid:
            labels=page.locator('label').all()
            for l in labels:
                if l.get_attribute('for')==fid: label=l.inner_text(); break
        label=(label or name).strip().rstrip('*').strip(); required=field.get_attribute('required') is not None or field.get_attribute('aria-required')=='true'
        if typ=='file':
            if re.search(r'resume|cv',label+' '+name,re.I): field.set_input_files(str(DATA/cv.pdf_path))
            elif required: unknown.append(label or 'Unknown upload')
            continue
        answer=answer_for(db,label,p)
        if answer is None:
            if required or sensitive(label): unknown.append(label or 'Unlabelled question')
        else:
            try:
                tag=field.evaluate('(e)=>e.tagName.toLowerCase()')
                if tag=='select': field.select_option(label=answer)
                elif typ in ('checkbox','radio'):
                    if answer.lower() in ('yes','true','agree'): field.check()
                    elif answer.lower() in ('no','false'): field.uncheck()
                    else: unknown.append(label)
                else: field.fill(answer)
            except Exception: unknown.append(label)
        db.add(ApplicationQuestion(application_id=application.id,question=label or name or 'Unlabelled',answer=answer or 'UNKNOWN',required=required))
    return unknown
def run_browser(db,j,mode='ASSISTED',dry_run=True,fixture=None):
    if fixture is None:
        raise ValueError('External form filling and submission are disabled. Review your documents, then open the job page and submit yourself. Dry-run uploads can also send private data.')
    if not LOCK.acquire(blocking=False): raise ValueError('Another browser run is active')
    try: return _run(db,j,mode,dry_run,fixture)
    finally: LOCK.release()
def _run(db,j,mode,dry_run,fixture):
    if not fixture: raise ValueError('External browser automation is disabled')
    dry_run=True
    if linkedin(j.job_url) or j.source.lower()=='linkedin': raise ValueError('LinkedIn is PREPARE_ONLY; no browser interaction permitted')
    if mode not in ('ASSISTED','AUTO_ALLOWED'): raise ValueError('Use assisted or auto-allowed mode')
    a=db.scalar(select(Application).where(Application.job_id==j.id))
    if not a: raise ValueError('Prepare application first')
    if a.status in TERMINAL or a.submission_attempted: raise ValueError('Already submitted or uncertain previous submission; reconcile manually')
    cfg=settings(db); dry_run=dry_run or cfg['dry_run']; site=db.scalar(select(SiteAdapter).where(SiteAdapter.domain==host(j.job_url)))
    if not fixture:
        validate_url(j.job_url)
        if not site or not site.enabled or not site.permitted: raise ValueError('Enable this exact domain and confirm site permission first')
    if a.attempts>cfg['max_retries']: raise ValueError('Retry limit reached')
    p=candidate(db)
    if not p['confirmed']: raise ValueError('Confirm candidate profile first')
    cv=db.scalar(select(ResumeVersion).where(ResumeVersion.job_id==j.id).order_by(ResumeVersion.id.desc()))
    if not cv or not (DATA/cv.pdf_path).exists(): raise ValueError('Generate CV first')
    run=BrowserRun(application_id=a.id,site=host(j.job_url),dry_run=dry_run); db.add(run); a.attempts+=1; a.mode=mode; db.flush(); db.commit()
    shots=DATA/'screenshots'; shots.mkdir(exist_ok=True)
    profile=DATA/'browser_profiles'/hashlib.sha256(host(j.job_url).encode()).hexdigest()[:16]
    page=None
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            context=browser.new_context(accept_downloads=False)
            page=context.pages[0] if context.pages else context.new_page()
            def route(r):
                if fixture: r.abort(); return
                url=r.request.url
                try:
                    if url.startswith(('data:','about:')): r.continue_(); return
                    validate_url(url)
                    # Cross-domain resources are blocked until explicitly allowed in adapter configuration.
                    permitted=[host(j.job_url)]+(site.config.get('resource_domains',[]) if site else [])
                    if host(url) not in permitted: r.abort(); return
                    r.continue_()
                except Exception: r.abort()
            context.route('**/*',route)
            if fixture: page.set_content(fixture)
            else: page.goto(j.job_url,wait_until='domcontentloaded',timeout=30000)
            run.step='fill'; unknown=fill_form(page,p,db,a,cv)
            before=shots/f'{run.id}_before.png'; screenshot(page,before); run.screenshot_before=str(before.relative_to(DATA))
            if unknown:
                a.status=j.status='NEEDS_REVIEW'; run.error='Human answers required: '+', '.join(unknown); run.step='questions'; log(db,run.error,j.id)
            elif dry_run or mode=='ASSISTED':
                a.status=j.status='NEEDS_HUMAN_ACTION'; run.step='review'; log(db,'Dry run completed; no final submission. Review screenshot and submit manually in your browser.',j.id)
            else:
                today=datetime.now(ZoneInfo('Asia/Dubai')).date()
                count=sum(1 for x in db.scalars(select(Application).where(Application.submission_attempted==True)) if not x.submission_started_at or datetime.fromisoformat(x.submission_started_at).astimezone(ZoneInfo('Asia/Dubai')).date()==today)
                reasons=submission_gate(j,a,cfg,site,count,cv,False)
                adapter=ADAPTERS.get(site.kind,ADAPTERS['generic'])(site.config)
                if not adapter.success_selector(): reasons.append('Configure an explicit success selector before auto submission')
                if challenge(page.locator('body').inner_text()): reasons.append('Challenge detected')
                valid=page.locator('form').evaluate_all('(forms)=>forms.length > 0 && forms.every(f=>f.checkValidity())')
                if not valid: reasons.append('Form validation incomplete')
                if reasons: raise ValueError('; '.join(reasons))
                if page.locator(adapter.submit_selector()).count()!=1: raise ValueError('Final submit control is ambiguous')
                if page.locator(adapter.success_selector()).is_visible(): raise ValueError('Success indicator was already present before submission')
                a.submission_attempted=True; a.submission_started_at=datetime.now(ZoneInfo('Asia/Dubai')).isoformat(); a.status=j.status='APPLYING'; run.step='submit'; db.commit()
                page.locator(adapter.submit_selector()).click(timeout=10000)
                page.locator(adapter.success_selector()).wait_for(state='visible',timeout=15000)
                after=shots/f'{run.id}_after.png'; screenshot(page,after); run.screenshot_after=str(after.relative_to(DATA)); a.confirmation=page.locator(adapter.success_selector()).inner_text()[:500]
                from .application_state import prime_state
                prime_state(db,a)
                application=set_status(db,j,'APPLIED'); run.step='confirmed'
                # Issue #46: a browser-confirmed submission is the user's own
                # action (they drove the browser), so it carries manual
                # authority in the canonical model. External browser submission
                # is disabled in this release, but the path is routed through
                # the state service rather than left as a future bypass.
                from .application_state import record_legacy_assertion,SOURCE_BROWSER_CONFIRMATION,REASON_BROWSER_CONFIRMED
                record_legacy_assertion(db,application,'APPLIED',source_category=SOURCE_BROWSER_CONFIRMATION,asserted_by='BROWSER',reason_code=REASON_BROWSER_CONFIRMED)
            db.commit(); context.close()
    except Exception as exc:
        run.error=('Browser operation failed: '+str(exc).split('\n')[0])[:500]; run.retryable=not a.submission_attempted and not isinstance(exc,ValueError)
        a.status=j.status='NEEDS_HUMAN_ACTION' if a.submission_attempted or isinstance(exc,ValueError) else 'FAILED'; log(db,run.error,j.id,'ERROR'); db.commit()
    return serialize(run)
def browser_test():
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True); page=b.new_page(); page.set_content('<h1>Browser ready</h1>'); ok=page.locator('h1').inner_text()=='Browser ready'; b.close(); return {'ok':ok}

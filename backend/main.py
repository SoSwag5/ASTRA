import os,json,shutil,csv,io,threading,tempfile,asyncio,secrets,logging
from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from collections import Counter
from urllib.parse import urlsplit
from fastapi import FastAPI,HTTPException,UploadFile,File,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select
from apscheduler.schedulers.background import BackgroundScheduler
from .models import *
from .services import *
from .adapters import discover,parse_url
from .providers import provider
from .browser import run_browser,browser_test
from .discovery import discovery_reason
from . import career_tracks
from .build_info import info as build_info
from .access import sessions

from .reliability import ProcessLock
scheduler=BackgroundScheduler(timezone='Asia/Dubai'); task_lock=ProcessLock()
def _source_outcome(source, report, outcome):
    """Replace current telemetry; preserve the legacy human-readable error."""
    error = outcome.get('error')
    report.update(completion=outcome['completion'],
                  completion_reason=outcome.get('completion_reason'),
                  health=outcome['health'], metrics=outcome.get('metrics'),
                  structured_error=error, error_code=error['code'] if error else None)
    source.details = {**source.details,
                      'last_completion':report['completion'],
                      'last_completion_reason':report['completion_reason'],
                      'last_health':report['health'],
                      'last_metrics':report['metrics'],
                      'last_structured_error':error,
                      'last_error_code':report['error_code']}


def _compat_funnel(rows):
    """Issue #43: the pre-#43 recall funnel is retained ONLY as derived
    compatibility output for the existing recall audit view and workspace UI.
    Its attribute counts overlap by design and it is NOT a second
    authoritative funnel -- backend.discovery_telemetry
    (discovery-telemetry-v1) is the single source of truth. The marker below
    says so inside the persisted report itself, so no consumer has to guess
    which of the two shapes is authoritative. backend/recall.py is a
    provenance-pinned #42 evaluation input and is deliberately not edited to
    carry this note.
    """
    from .recall import funnel
    from .discovery_telemetry import REPORT_KEY, TELEMETRY_SCHEMA_VERSION
    return {**funnel(rows), 'schema': 'legacy-discovery-funnel-compat-1',
            'authoritative_funnel': f'{REPORT_KEY} ({TELEMETRY_SCHEMA_VERSION})',
            'compatibility_note': 'Derived compatibility output retained for pre-issue-#43 '
                                  'consumers. Attribute counts overlap and this is not the '
                                  'authoritative monotonic discovery funnel.'}


def _record_progress(db, run_id, report, total, done, current):
    """Persist scan progress so the workspace can show it while the run is
    still going. Merges into the stored report, so a concurrent cancel request
    recorded there is never overwritten."""
    not_fetched=[e for e in report.get('scope_accounting',[]) if e['outcome'].startswith('NOT_FETCHED')]
    report['progress']={'sources_total':total,'sources_done':done,'current_source':current,
                        'postings_seen':report.get('scanned',0),'sources_not_fetched':len(not_fetched),
                        'scope_changed_sources':list(report.get('scope_changed_sources',[]))}
    # Session is expire_on_commit=False, so re-read the row: a cancel request
    # committed by another request must be merged, never overwritten.
    from .scan_control import _report_guard
    with _report_guard:
        row=db.get(AutomationRun,run_id); db.refresh(row)
        row.report={**(row.report or {}),'progress':report['progress'],'trigger':report['trigger'],
                    'started_at':report['started_at'],**({'scope':report['scope']} if 'scope' in report else {})}
        db.commit()


DISCOVERY_REFUSED={'refused':True,'detail':'Discovery runs only from a confirmed Start Scan: review the scope, then confirm.'}


def task(name, scheduled_run=False, trigger=None, confirmation=None):
    """Run one task.

    Discovery is manual-only and this boundary enforces it: name='discover'
    runs only with a ScanConfirmation from backend/scan_control.confirm(),
    which is issued for one previewed, Owner-confirmed scope and can be
    claimed once. Anything else -- a scheduler, a script, a direct call, a
    reused confirmation -- is refused without fetching anything. The
    confirmation carries the task_lock (already held), the RUNNING
    AutomationRun, the ScanStop that admits every provider call in order with
    Stop, the confirmed settings and each confirmed source's definition. Every
    confirmed source is accounted for in the report: fetched, failed, not
    fetched because the Owner cancelled, or not fetched because it was
    disabled, edited or deleted after confirmation. An accepted Stop always
    ends the run CANCELLED and the report names any source it let finish."""
    run_id=cancel=source_ids=source_defs=None
    if name=='discover':
        from .scan_control import ScanConfirmation
        if not isinstance(confirmation,ScanConfirmation) or not confirmation.claim():
            return dict(DISCOVERY_REFUSED)
        # confirm() acquired task_lock for this confirmation; this task owns it now.
        run_id,cancel=confirmation.run_id,confirmation.cancel
        source_ids,source_defs=list(confirmation.source_ids),confirmation.source_defs
        trigger=confirmation.trigger
    elif confirmation is not None:
        raise ValueError('A scan confirmation applies only to discovery')
    elif not task_lock.acquire(blocking=False): return {'busy':True}
    try:
        with Session() as db:
            cfg=confirmation.cfg if name=='discover' else settings(db)
            if run_id is None:
                run=AutomationRun(task=name); db.add(run); db.commit(); prior={}
            else:
                run=db.get(AutomationRun,run_id); db.refresh(run); prior=dict(run.report or {})
            report={'discovered':0,'duplicates':0,'prepared':0,'submitted':0,'failures':0,'trigger':trigger or prior.get('trigger') or ('APP' if scheduled_run else 'MANUAL'),'started_at':prior.get('started_at') or now(),'checked':0,'buckets':{k:0 for k in ('STRONG','GOOD','STRETCH','LOW','REJECTED')},'assessment_comparisons':{}}
            if prior.get('scope'): report['scope']=prior['scope']
            cancelled_sources=0
            try:
                if name=='discover':
                    from .recall import evaluate
                    from . import discovery_telemetry as telemetry
                    from .scan_control import source_definition, missing_source
                    single=source_ids[0] if confirmation.single_source else None
                    report.update(scanned=0,filtered=0,sources=[],source_id=single,decisions=[],
                                  scope_changed_sources=[],scope_accounting=[])
                    profile=candidate(db) if db.scalar(select(CandidateProfile)) else {}
                    # Issue #43: one authoritative funnel accumulator for this run. It only
                    # ever OBSERVES the pipeline below -- it never changes ranking,
                    # eligibility, deduplication, provider transport or persistence, and a
                    # telemetry failure can never roll back a valid source's ingestion.
                    run_telemetry=telemetry.RunTelemetry(run_id=run.id,trigger=report['trigger'],
                                                         started_at=report['started_at'],
                                                         source_filter=single,cfg=cfg)
                    confirmed=set(source_ids)
                    # Sources outside the confirmed scope are reported as skipped, never as
                    # zeroes: disabled ones as disabled, enabled ones as not targeted.
                    for other in db.scalars(select(JobSource).where(JobSource.adapter!='manual')):
                        if other.id not in confirmed:
                            run_telemetry.skip(other,telemetry.SKIPPED_NOT_TARGETED if other.enabled else telemetry.SKIPPED_DISABLED)
                    # Every confirmed source is walked in confirmed order and accounted for,
                    # including one disabled or deleted after confirmation: the scope the
                    # Owner confirmed never silently shrinks.
                    planned=len(source_ids)
                    done=0
                    _record_progress(db,run.id,report,planned,done,None)
                    for position,sid in enumerate(source_ids):
                        final_source=position==planned-1
                        source=db.get(JobSource,sid)
                        if source is not None:
                            db.refresh(source)  # expire_on_commit=False: compare the stored row, not a cached copy
                        confirmed_def=source_defs.get(sid) or {}
                        change=('DELETED' if source is None else
                                'DISABLED' if not source.enabled else
                                'EDITED' if source_definition(source)!=confirmed_def else None)
                        if change:
                            # Changed after the Owner confirmed this scope: not fetched, and named.
                            run_telemetry.skip(source or missing_source(sid,confirmed_def),telemetry.SKIPPED_SCOPE_CHANGED)
                            entry={'id':sid,'name':confirmed_def.get('name') or (source.name if source else None),'change':change}
                            report['scope_changed_sources'].append(entry)
                            report['scope_accounting'].append({**entry,'outcome':'NOT_FETCHED_SCOPE_CHANGED'})
                            cancel.accounted(final=final_source)
                            _record_progress(db,run.id,report,planned,done,None); continue
                        # Persisting progress can wait on SQLite. Check cancellation
                        # after that wait, immediately before starting this source, so
                        # a Stop received during the progress update is honoured.
                        _record_progress(db,run.id,report,planned,done,source.name)
                        if cancel.is_set():
                            run_telemetry.skip(source,telemetry.SKIPPED_CANCELLED); cancelled_sources+=1
                            report['scope_accounting'].append({'id':sid,'name':source.name,'outcome':'NOT_FETCHED_CANCELLED'})
                            cancel.accounted(final=final_source)
                            _record_progress(db,run.id,report,planned,done,None); continue
                        source_report={'id':source.id,'name':source.name,'scanned':0,'checked':0,'imported':0,'duplicates':0,'filtered':{},'error':'','completion':'COMPLETE','buckets':{k:0 for k in ('STRONG','GOOD','STRETCH','LOW','REJECTED')},'assessment_comparisons':{}}
                        source_decisions=[]
                        attempt=run_telemetry.attempt(source)
                        try:
                            source.details={**source.details,'last_attempted':now(),'mode':'MANUAL','market':'UAE campaign','interval_hours':source.details.get('interval_hours',cfg['discovery_interval_hours'])}
                            if source.adapter=='generic':
                                raise ValueError('Generic page scanning is disabled pending destination and platform review; use a public board API or paste the description')
                            # The provider-entry checkpoint. admit() checks Stop and
                            # admits this source as one step ordered against Stop
                            # acceptance, and the provider call follows it directly: a
                            # Stop accepted before admission means this source is never
                            # fetched, and one accepted after it names this source as in
                            # flight. When refused, undo the tentative bookkeeping (no
                            # write is flushed yet) and mark telemetry as skipped.
                            if not cancel.admit(sid,source.name):
                                attempt.skipped(telemetry.SKIPPED_CANCELLED)
                                cancelled_sources+=1
                                report['scope_accounting'].append({'id':sid,'name':source.name,'outcome':'NOT_FETCHED_CANCELLED'})
                                db.rollback()
                                cancel.accounted(final=final_source)
                                _record_progress(db,run.id,report,planned,done,None)
                                continue
                            items=discover(source.adapter,source.board,source.url,cfg)
                            health=getattr(items,'health',None)
                            outcome=health or {
                                'completion':'COMPLETE', 'health':'HEALTHY' if items else 'EMPTY',
                                'completion_reason':None, 'metrics':None, 'error':None}
                            _source_outcome(source, source_report, outcome)
                            # #43 FETCHED is exactly what the provider/compatibility boundary
                            # delivered to this orchestration loop -- never HTTP requests, raw
                            # JSON elements, or the provider's own pre-validation row count
                            # (those stay in provider_metrics as separate diagnostics).
                            attempt.record_fetch(outcome)
                            # Issue #41 Owner Decision 1: a structurally valid posting is always
                            # persisted through #40's normalize/dedupe seam, even when hard-rejected
                            # -- rejection is expressed later as a hidden SKIP status, never as
                            # skipped persistence. Only a record that cannot safely satisfy #40's
                            # persistence contract (e.g. an unusable job_url) becomes a bounded
                            # INVALID_JOB result instead of crashing the whole source.
                            for item in items:
                                report['scanned']+=1; source_report['scanned']+=1
                                attempt.observed()
                                item['company']=source.name
                                audit={'source_id':source.id,'item':{k:str(item.get(k,''))[:(2200 if k=='description' else 2000)] for k in ('title','company','location','job_url','source_job_id','source','date_posted','closing_date','description')},'disposition':'PENDING'}
                                source_decisions.append(audit);report['decisions'].append(audit)
                                try:
                                    j,d=add_job(db,item,job_source=source)
                                except ValueError as invalid:
                                    audit.update(disposition='INVALID_JOB',invalid_reason=str(invalid))
                                    source_report['invalid']=source_report.get('invalid',0)+1
                                    # Rejected by #40's own ingestion contract, so it never
                                    # enters STRUCTURALLY_VALID. No second structural
                                    # validator exists: add_job() is the only authority.
                                    attempt.invalid_observation()
                                    continue
                                attempt.persisted(j.id,created=not d)
                                # #40 persistence/identity is resolved first. The canonical
                                # persisted Job is then assessed once, for new and reused rows
                                # alike, with an empty profile representing UNKNOWN evidence.
                                result=analyze(db,j,profile=profile,cfg=cfg)
                                decision=result['recall'];bucket=decision['fit_assessment']['bucket'] if decision.get('fit_assessment') else ('REJECTED' if decision['excluded'] else 'LOW')
                                # #43 reads this one authoritative #41 decision; it never
                                # reimplements geography, eligibility or relevance rules.
                                attempt.assessed(j.id,decision)
                                # Rescoring a discovery never changes historical application fields or stages.
                                j.analysis={**j.analysis,'first_seen':j.analysis.get('first_seen',j.date_found),'last_seen':now(),'discovery':{**j.analysis.get('discovery',{}),'source_id':source.id,'last_seen':now()}}
                                audit.update(job_id=j.id,decision=decision,disposition='DUPLICATE' if d else 'NEW',already_seen=bool(j.analysis.get('seen_at')),bucket=bucket)
                                report['checked']+=1;source_report['checked']+=1
                                report['duplicates' if d else 'discovered']+=1
                                source_report['duplicates' if d else 'imported']+=1
                                report['buckets'][bucket]+=1;source_report['buckets'][bucket]+=1
                                comparison=decision.get('assessment_shadow',{}).get('comparison_category')
                                if comparison:
                                    report['assessment_comparisons'][comparison]=report['assessment_comparisons'].get(comparison,0)+1
                                    source_report['assessment_comparisons'][comparison]=source_report['assessment_comparisons'].get(comparison,0)+1
                            source_report['filtered']=dict(Counter('INVALID_JOB' for a in source_decisions if a['disposition']=='INVALID_JOB'))
                            report['filtered']+=sum(source_report['filtered'].values())
                            source_report['rejected']=dict(Counter(a['decision']['hard'][0]['code'] for a in source_decisions if a.get('decision') and a['decision']['excluded']))
                            source_report['funnel']=_compat_funnel(source_decisions)
                            source.details={**source.details,'last_success':now(),'last_verified':now()[:10],'jobs_fetched':source_report['scanned'],'new_jobs':source_report['imported'],'updated_jobs':source_report['duplicates'],'last_error':''}
                            db.commit()
                        except Exception as e:
                            db.rollback(); report['discovered']-=source_report['imported']; report['duplicates']-=source_report['duplicates'];report['checked']-=source_report['checked']
                            for bucket,count in source_report.get('buckets',{}).items(): report['buckets'][bucket]-=count
                            for category,count in source_report.get('assessment_comparisons',{}).items(): report['assessment_comparisons'][category]-=count
                            source_report['imported']=source_report['duplicates']=source_report['checked']=0; source_report['buckets']={k:0 for k in ('STRONG','GOOD','STRETCH','LOW','REJECTED')};source_report['assessment_comparisons']={}
                            for audit in report.get('decisions',[]):
                                if audit['source_id']==source.id and audit['disposition'] in ('NEW','DUPLICATE','PENDING'):audit['disposition']='SOURCE_ERROR';audit.pop('job_id',None)
                            source_report['funnel']=_compat_funnel(source_decisions)
                            # A provider-framework exception (issue #38) carries the batch's own
                            # truthful completion/health/metrics; a legacy adapter's plain
                            # exception has none, so it is truthfully FAILED here regardless of
                            # the default set at the top of this loop. Either way, this attempt's
                            # telemetry always REPLACES whatever a prior successful run recorded
                            # -- a fresh failure must never leave stale success metrics in place.
                            code=getattr(e,'error_code',None)
                            failure={'completion':getattr(e,'completion','FAILED'),
                                     'completion_reason':getattr(e,'completion_reason',None),
                                     'health':getattr(e,'health','UNAVAILABLE'),
                                     'metrics':getattr(e,'metrics',None),
                                     'error':{'code':code or 'SOURCE_REQUEST_FAILED',
                                              'message':str(e) if code else 'Source request failed'}}
                            _source_outcome(source, source_report, failure)
                            # A provider failure is reported as a failure, never as
                            # "zero relevant jobs": the rolled-back canonical stages
                            # are cleared and the attempt is marked incomplete.
                            attempt.failed(failure)
                            source.details={**source.details,'last_attempted':now(),'last_error':'Request failed; retry or review source configuration'}
                            report['failures']+=1; source_report['error']='Source request failed ('+type(e).__name__+'). Check the source URL or retry later.'; log(db,source_report['error'],level='ERROR'); db.commit()
                        report['sources'].append(source_report)
                        report['scope_accounting'].append({'id':source.id,'name':source.name,
                                                           'outcome':'FAILED' if source_report['error'] else 'FETCHED'})
                        cancel.accounted(final=final_source)
                        done+=1
                        _record_progress(db,run.id,report,planned,done,None)
                elif name in ('analyze','prepare','process'):
                    for j in list(db.scalars(select(Job).where(Job.status.not_in(TERMINAL|{'SKIP'})))):
                        try:
                            if name=='analyze': analyze(db,j)
                            elif name=='prepare' and j.recommendation in ('APPLY','HIGH_PRIORITY'):
                                if not db.scalar(select(Application).where(Application.job_id==j.id)): prepare(db,j); report['prepared']+=1
                            elif False:  # External submission is disabled; legacy settings cannot re-enable it.
                                site=db.scalar(select(SiteAdapter).where(SiteAdapter.domain==host(j.job_url)))
                                if site and site.enabled and site.auto_submit and site.permitted and not linkedin(j.job_url) and j.status=='READY_TO_APPLY':
                                    run_browser(db,j,'AUTO_ALLOWED',False); report['submitted']+=int(j.status=='APPLIED')
                            db.commit()
                        except Exception as e: db.rollback(); report['failures']+=1; log(db,'Task could not finish ('+type(e).__name__+')',j.id,'ERROR'); db.commit()
                elif name=='sync': report.update(sync_tracker(db))
                elif name=='report': report.update(metrics(db))
                else: raise ValueError('Unknown task')
                report['finished_at']=now();report['duration_seconds']=round((datetime.fromisoformat(report['finished_at'])-datetime.fromisoformat(report['started_at'])).total_seconds(),3)
                if name=='discover':
                    report.update({bucket.lower():count for bucket,count in report['buckets'].items()})
                    report['hard_reasons']=dict(Counter(
                        audit['decision']['hard'][0]['code'] for audit in report['decisions']
                        if audit.get('decision') and audit['decision']['excluded'] and audit.get('disposition')!='SOURCE_ERROR'))
                    report['funnel']=_compat_funnel(report['decisions']);report['sources_attempted']=len(report['sources']);report['sources_successful']=sum(not s['error'] for s in report['sources'])
                    # Every source is done: admit nothing more and refuse any later Stop,
                    # so this status and an accepted Stop can never disagree. An accepted
                    # Stop ends the run CANCELLED even when it arrived during the last
                    # source, and the report names the source it let finish. Otherwise a
                    # confirmed source left unfetched because it changed after
                    # confirmation makes the run PARTIAL: the confirmed scope was not
                    # completed.
                    stopped=cancel.close()
                    run_status='CANCELLED' if stopped else ('PARTIAL' if report['failures'] or report['scope_changed_sources'] else 'COMPLETED')
                    if stopped: report['cancelled']={'sources_not_fetched':cancelled_sources,
                                                     'source_in_flight_at_stop':cancel.in_flight_at_stop}
                    report['confirmed_scope']={'sources_confirmed':planned,
                                               'sources_fetched':sum(e['outcome']=='FETCHED' for e in report['scope_accounting']),
                                               'sources_failed':sum(e['outcome']=='FAILED' for e in report['scope_accounting']),
                                               'sources_not_fetched':sum(e['outcome'].startswith('NOT_FETCHED') for e in report['scope_accounting'])}
                    if len(report['scope_accounting'])!=planned: raise RuntimeError('A confirmed source was not accounted for')
                    # Issue #43: the authoritative, versioned discovery funnel. Building it
                    # cannot fail the run -- RunTelemetry.finalize() returns a bounded
                    # telemetry-error payload rather than raising or publishing fabricated
                    # counts, and every source's ingestion is already committed by now.
                    report[telemetry.REPORT_KEY]=run_telemetry.finalize(
                        db,run_status,finished_at=report['finished_at'],
                        duration_seconds=report['duration_seconds'])
                    # Bound discovery telemetry and verbose decisions to 90 days. Idempotent
                    # and limited to discovery reporting: no Job, JobObservation,
                    # Application, user decision or application history is ever touched.
                    telemetry.prune_expired(db)
                if name=='discover':
                    from .scan_control import _report_guard
                    with _report_guard:
                        run=db.get(AutomationRun,run.id); db.refresh(run)
                        if (run.report or {}).get('cancel_requested_at'): report['cancel_requested_at']=run.report['cancel_requested_at']
                        run.status=run_status; run.report=report; db.commit()
                else:
                    run=db.get(AutomationRun,run.id); db.refresh(run)
                    run.status='PARTIAL' if report['failures'] else 'COMPLETED'; run.report=report; db.commit()
            except Exception as e:
                db.rollback()
                report['finished_at']=now();report['duration_seconds']=round((datetime.fromisoformat(report['finished_at'])-datetime.fromisoformat(report['started_at'])).total_seconds(),3)
                if name=='discover':
                    cancel.close()   # nothing more is fetched; a Stop after this is refused
                    from .scan_control import _report_guard
                    with _report_guard:
                        run=db.get(AutomationRun,run.id); db.refresh(run)
                        if (run.report or {}).get('cancel_requested_at'): report['cancel_requested_at']=run.report['cancel_requested_at']
                        run.status='FAILED'
                        run.report={**report,'error':'Task failed ('+type(e).__name__+'); no success is recorded.'}; db.commit()
                else:
                    run=db.get(AutomationRun,run.id); run.status='FAILED'
                    run.report={**report,'error':'Task failed ('+type(e).__name__+'); no success is recorded.'}; db.commit()
            return serialize(run)
    finally: task_lock.release()
# Discovery is manual-only. It is never registered with the scheduler, never
# caught up after a gap and never resumed after a restart; the only way to
# start it is the workspace's Start Scan confirmation (backend/scan_control.py).
# Stored legacy settings (discovery_enabled, discovery_interval_hours, a
# 'discover' entry in schedule) are preserved untouched and simply have no
# scheduling effect.
def scheduled(name):
    if name=='discover': return
    with Session() as db:
        cfg=settings(db)
        if cfg['autopilot']=='OFF' or (name=='sync' and not cfg['auto_sync']): return
    task(name,scheduled_run=True,trigger='APP')
def configure_schedule():
    with Session() as db:
        cfg=settings(db)
    scheduler.remove_all_jobs()
    for name,time in cfg['schedule'].items():
        if name=='discover': continue
        hour,minute=map(int,time.split(':')); scheduler.add_job(scheduled,'cron',args=[name],id=name,hour=hour,minute=minute,timezone=cfg.get('application_profile',{}).get('timezone','Asia/Dubai'),misfire_grace_time=1800,coalesce=True,max_instances=1)
    from .workbook import retry_sync
    scheduler.add_job(retry_sync,'interval',seconds=30,id='workbook_retry',coalesce=True,max_instances=1)
    from .reliability import backup_database
    scheduler.add_job(backup_database,'interval',hours=24,id='daily_backup',coalesce=True,max_instances=1)
@asynccontextmanager
async def lifespan(app):
    if os.getenv('ASTRA_DEMO_ONLY')=='1':
        yield
        return
    initialize()
    # Issue #44: additive Gmail account table. Owned by backend/gmail_accounts.py
    # rather than models.initialize(), because backend/models.py is a
    # SHA-256-pinned #42 evaluation-provenance input; see that module's
    # docstring. Idempotent and safe on an existing database.
    from .gmail_accounts import initialize_gmail_schema
    initialize_gmail_schema()
    from .gmail_sync import initialize_sync_schema
    initialize_sync_schema()
    # Issue #46: additive canonical application-state, transition-history and
    # Gmail reconciliation tables. Owned here for the same reason as #44/#45 --
    # backend/models.py is a SHA-256-pinned #42 evaluation-provenance input.
    # Idempotent; existing applications are bootstrapped lazily on first
    # contact, never by a bulk rewrite at startup.
    from .application_reconciliation import initialize_reconciliation_schema
    initialize_reconciliation_schema()
    if os.getenv('BIND_HOST','127.0.0.1') not in ('127.0.0.1','localhost') and not os.getenv('APP_TOKEN'): raise RuntimeError('APP_TOKEN required for public binding')
    # A process restart cannot finish an earlier in-memory scan.
    if task_lock.acquire(False):
        try:
            with Session.begin() as db:
                for run in db.scalars(select(AutomationRun).where(AutomationRun.status=='RUNNING')):
                    stopping=bool((run.report or {}).get('cancel_requested_at'))
                    run.status='CANCELLED' if stopping else 'INTERRUPTED'
                    run.report={**run.report,'restart':'NOT_RESTARTED',
                                'error':('App stopped while this scan was being cancelled. It was not restarted.' if stopping else
                                         'App stopped before this run finished. It was not restarted automatically; press Start Scan when you want a new scan.')}
        finally:task_lock.release()
    configure_schedule(); scheduler.start()
    yield
    scheduler.shutdown(wait=False)
app=FastAPI(title='ASTRA',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])
mutation_lock=asyncio.Lock()
@app.middleware('http')
async def guard(req:Request,call_next):
    import ipaddress
    from .security_events import record as security_event
    if os.getenv('ASTRA_DEMO_ONLY')=='1' and req.url.path.startswith('/api'):
        return JSONResponse({'detail':'Private API disabled in demo-only mode'},404)
    peer=req.client.host if req.client else ''
    if peer!='testclient':
        try: local=ipaddress.ip_address(peer).is_loopback
        except ValueError: local=False
        if not local:
            security_event('PEER_BLOCKED','Non-loopback network peer rejected',peer=peer,path=req.url.path)
            return JSONResponse({'detail':'This workspace accepts connections only from this device'},403)
    origin=req.headers.get('origin')
    port=os.getenv('HUNTER_PORT','8787')
    if origin and origin not in (f'http://localhost:{port}',f'http://127.0.0.1:{port}','http://localhost:5173'):
        security_event('INVALID_ORIGIN_BLOCKED','Cross-origin request rejected',origin=origin,path=req.url.path)
        return JSONResponse({'detail':'Origin blocked'},403)
    if req.headers.get('sec-fetch-site')=='cross-site':
        security_event('CSRF_REJECTED','Sec-Fetch-Site cross-site rejected',path=req.url.path,method=req.method)
        return JSONResponse({'detail':'Cross-site access blocked'},403)
    token=os.getenv('APP_TOKEN','')
    if not token: sessions.verify('','')
    if req.url.path.startswith('/api') and req.headers.get('sec-fetch-dest','empty')!='empty':
        return JSONResponse({'detail':'Use the workspace to access private data'},403)
    if token and req.url.path.startswith('/api') and req.url.path != '/api/access':
        bearer=req.headers.get('authorization','').removeprefix('Bearer ')
        if not sessions.verify(token,bearer): return JSONResponse({'detail':'Unlock your workspace to continue'},401)
    try: length=int(req.headers.get('content-length','0'))
    except ValueError: return JSONResponse({'detail':'Invalid content length'},400)
    if length<0 or length>11_000_000: return JSONResponse({'detail':'Upload limit is 10 MB'},413)
    if req.method not in ('GET','HEAD','OPTIONS') and (req.headers.get('transfer-encoding') or 'content-length' not in req.headers):
        return JSONResponse({'detail':'Send a bounded request with Content-Length; streaming uploads are unsupported'},411)
    try:
        if req.method not in ('GET','HEAD','OPTIONS'):
            if not req.headers.get('content-type','').startswith(('application/json','multipart/form-data')) and length:
                return JSONResponse({'detail':'Use JSON or a supported file upload'},415)
            async with mutation_lock: response=await call_next(req)
        else: response=await call_next(req)
    except Exception:
        # Catch before ServerErrorMiddleware re-raises to Uvicorn: database
        # exception parameter dumps can contain private profile/answer values.
        response=JSONResponse({'detail':'The operation could not finish. No success is recorded. Check the input or local storage, then retry.'},500)
    response.headers['X-Content-Type-Options']='nosniff'; response.headers['Referrer-Policy']='no-referrer'; response.headers['X-Frame-Options']='DENY'
    response.headers['Cache-Control']='no-store'
    response.headers['Permissions-Policy']='geolocation=(), camera=(), microphone=(), payment=(), usb=(), interest-cohort=()'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'"
    return response

# Outermost response policy includes guard rejections and TrustedHost failures.
@app.middleware('http')
async def response_policy(req:Request,call_next):
    response=await call_next(req)
    response.headers.update({
        'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'no-referrer',
        'X-Frame-Options':'DENY', 'Cache-Control':'no-store',
        'Permissions-Policy':'geolocation=(), camera=(), microphone=(), payment=(), usb=(), interest-cohort=()',
        'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'",
    })
    return response

class AccessRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    key: str=Field(min_length=1,max_length=1000)

@app.get('/api/access')
def access_status():
    return {'required':bool(os.getenv('APP_TOKEN',''))}

@app.post('/api/access')
def unlock_access(data:AccessRequest,req:Request):
    key=os.getenv('APP_TOKEN','')
    if not key: raise HTTPException(400,'Access-key protection is not configured')
    token,retry=sessions.issue(key,data.key,req.headers.get('authorization','').removeprefix('Bearer '))
    if not token:
        from .security_events import record
        record('ACCESS_REJECTED')
        if retry: return JSONResponse({'detail':'Too many attempts. Wait one minute before trying again.'},429,headers={'Retry-After':str(retry)})
        raise HTTPException(401,'Access key was not accepted')
    return {'token':token,'idle_seconds':sessions.IDLE_SECONDS,'maximum_seconds':sessions.MAX_SECONDS}

@app.post('/api/access/lock')
def lock_access(req:Request):
    sessions.revoke(req.headers.get('authorization','').removeprefix('Bearer '))
    return JSONResponse({'locked':True},headers={'Clear-Site-Data':'"cache", "storage"'})
logger=logging.getLogger('astra')
def log_safe(value):
    """Keep request data from forging extra log records or hiding in control bytes."""
    return re.sub(r'[^\w./:-]','_',str(value))[:200]
# Unexpected internals can name local paths, SQL or credentials. Only messages
# this application authors itself reach a client; the detail stays in the local
# log, which is why failures are reported through this single constant.
UNEXPECTED_FAILURE='The operation could not finish. No success is recorded. Retry or check local storage availability.'
@app.exception_handler(ValueError)
async def value_error(req,exc): return JSONResponse({'detail':str(exc)},400)
@app.exception_handler(Exception)
async def unexpected_error(req,exc):
    logger.exception('Unhandled error serving %s',log_safe(req.url.path))
    return JSONResponse({'detail':UNEXPECTED_FAILURE},500)
def get_job(db,id):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'Job not found')
    return j
@app.get('/api/health')
def health(): return {'ok':True,'scheduler':scheduler.running,'pid':os.getpid(),**build_info()}
def metrics(db):
    jobs=list(db.scalars(select(Job))); apps=list(db.scalars(select(Application))); counts=Counter(a.status for a in apps); applied=[a for a in apps if a.applied_date]; today=datetime.now(ZoneInfo('Asia/Dubai')).date(); dates=[]
    for a in applied:
        try: dates.append(datetime.fromisoformat(a.applied_date).astimezone(ZoneInfo('Asia/Dubai')).date())
        except ValueError: pass
    interviews=counts['INTERVIEW']+counts['OFFER']; responses=interviews+counts['REJECTED']
    return {'jobs':len(jobs),'high_priority':sum(j.priority=='HIGH' for j in jobs),'ready':sum(a.status=='READY_TO_APPLY' for a in apps),'applied':len(applied),'today':sum(d==today for d in dates),'week':sum(d>=today-timedelta(days=today.weekday()) for d in dates),'interviews':interviews,'offers':counts['OFFER'],'rejections':counts['REJECTED'],'response_rate':round(responses/max(len(applied),1)*100),'interview_rate':round(interviews/max(len(applied),1)*100),'average_score':round(sum(j.match_score for j in jobs)/max(len(jobs),1)),'overdue_followups':sum(not f.done and f.due_date<now() for f in db.scalars(select(FollowUp))),'by_status':dict(counts),'by_source':dict(Counter(j.source for j in jobs)),'by_location':dict(Counter(j.location for j in jobs)),'by_week':dict(Counter(d.strftime('%Y-W%W') for d in dates)),'scores':dict(Counter(str(j.match_score//10*10) for j in jobs)),'missing':dict(Counter(s for j in jobs for s in j.missing_skills).most_common(10)),'best':[serialize(j) for j in sorted(jobs,key=lambda j:j.match_score,reverse=True) if j.status not in TERMINAL|{'SKIP'}][:5]}
@app.get('/api/dashboard')
def dashboard():
    with Session() as db: return metrics(db)
@app.get('/api/profile')
def profile():
    with Session() as db: return candidate(db) if db.scalar(select(CandidateProfile)) else None
@app.put('/api/profile')
def update_profile(data:dict):
    with Session.begin() as db:
        p=db.scalar(select(CandidateProfile))
        if not p: raise ValueError('Import CV first')
        for k in ('name','email','phone','location','summary'):
            if k in data and (not isinstance(data[k],str) or len(data[k])>20000): raise ValueError('Profile text must be under 20,000 characters')
        if 'confirmed' in data and type(data['confirmed']) is not bool: raise ValueError('Confirmation must be true or false')
        if 'declarations' in data and (not isinstance(data['declarations'],dict) or len(json.dumps(data['declarations']))>30000): raise ValueError('Invalid profile declarations')
        changed=[k for k in ('name','email','phone','location','summary') if k in data and data[k]!=getattr(p,k)]
        for k in ('name','email','phone','location','summary','declarations','confirmed'):
            if k in data: setattr(p,k,data[k])
        if changed and data.get('confirmed') is not True: p.confirmed=False
        p.declarations={**p.declarations,'field_sources':{**p.declarations.get('field_sources',{}),**{k:{'state':'USER PROVIDED','updated_at':now()} for k in changed}},'extraction_state':'VERIFIED' if p.confirmed else 'EXTRACTED — NEEDS CONFIRMATION'}
        log(db,'Candidate profile updated by user'); return serialize(p)
@app.post('/api/import/cv')
def cv_upload(file:UploadFile=File(...)):
    from .document_security import validate_document,MAX_FILE
    content=validate_document(file.file.read(MAX_FILE+1),file.filename,'pdf',file.content_type)
    with tempfile.TemporaryDirectory(prefix='.import-',dir=DATA) as folder:
        path=Path(folder)/'cv.pdf'; path.write_bytes(content)
        master=DATA/'master.pdf'; backup=Path(folder)/'previous.pdf'
        if master.exists(): shutil.copy2(master,backup)
        try:
            with Session.begin() as db: result=serialize(import_cv(db,path))
            return result
        except Exception:
            if backup.exists(): os.replace(backup,master)
            elif master.exists(): master.unlink()
            raise

@app.put('/api/profile/facts/{kind}/{fact_id}')
def correct_fact(kind:str,fact_id:int,data:dict):
    types={'skills':Skill,'employments':Employment,'education':Education,'certifications':Certification,'projects':Project}
    if kind not in types: raise HTTPException(404)
    value=data.get('text')
    if not isinstance(value,str) or not value.strip() or len(value)>20000: raise ValueError('Enter a fact under 20,000 characters')
    with Session.begin() as db:
        fact=db.get(types[kind],fact_id)
        if not fact: raise HTTPException(404)
        fact.text=value; fact.provenance='USER PROVIDED '+now()
        profile=db.get(CandidateProfile,fact.candidate_id); profile.confirmed=False
        log(db,'Candidate corrected a source fact; confirmation required')
        return serialize(fact)
@app.post('/api/import/tracker')
def tracker_upload(file:UploadFile=File(...)):
    from .document_security import validate_document,MAX_FILE
    content=validate_document(file.file.read(MAX_FILE+1),file.filename,'xlsx',file.content_type)
    with tempfile.TemporaryDirectory(prefix='.import-',dir=DATA) as folder:
        path=Path(folder)/'tracker.xlsx'; path.write_bytes(content)
        target=DATA/'tracker.xlsx'; backup=Path(folder)/'previous.xlsx'
        if target.exists(): shutil.copy2(target,backup)
        try:
            with Session.begin() as db:
                result=import_tracker(db,path)
                if backup.exists(): shutil.copy2(backup,DATA/'tracker_previous.xlsx')
                os.replace(path,target)
            return result
        except Exception:
            if backup.exists(): os.replace(backup,target)
            elif target.exists(): target.unlink()
            raise
@app.post('/api/import/csv')
def csv_upload(file:UploadFile=File(...)):
    from .document_security import validate_document,MAX_FILE
    from itertools import islice
    content=validate_document(file.file.read(MAX_FILE+1),file.filename,'csv',file.content_type)
    rows=list(islice(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))),10001)); imported=0; duplicates=0
    if len(rows)>10000: raise ValueError('CSV supports up to 10,000 rows')
    with Session.begin() as db:
        for row in rows:
            data={HEADERS.get(k,k):v for k,v in row.items() if v and HEADERS.get(k,k) in ('company','title','location','job_url','description','source','salary','remote_status')}
            job,dupe=add_job(db,data)
            job.analysis={**(job.analysis or {}),'source_type':'CSV','workflow_status_preserved':True}
            analyze(db,job); imported+=not bool(dupe); duplicates+=bool(dupe)
    return {'imported':imported,'duplicates':duplicates}
@app.get('/api/jobs')
def jobs():
    with Session() as db: return [serialize(j) for j in db.scalars(select(Job).order_by(Job.id.desc()))]
class JobInput(BaseModel):
    company:str=Field(min_length=1,max_length=200)
    title:str=Field(min_length=1,max_length=300)
    location:str='UNKNOWN'
    job_url:str=''
    description:str=Field(default='',max_length=100000)
    source:str='Manual'
    salary:str='UNKNOWN'
    remote_status:str='UNKNOWN'
    employment_type:str='UNKNOWN'
    experience_requirement:str=Field(default='UNKNOWN',max_length=1000)
    notes:str=Field(default='',max_length=20000)
    date_found:str=''
@app.post('/api/jobs')
def create_job(data:JobInput):
    with Session.begin() as db:
        values=data.model_dump()
        if not values.get('date_found'):values.pop('date_found',None)
        elif not __import__('backend.search_workspace',fromlist=['parse_date']).parse_date(values['date_found']):raise ValueError('Choose a valid discovery date')
        j,d=add_job(db,values)
        if not d:
            agency=any(token in (data.source+' '+data.job_url).lower() for token in ['michaelpage','michael page','hays','charterhouse','roberthalf','robert half','cooperfitch','cooper fitch','guildhall','mackenzie'])
            j.analysis={**j.analysis,'source_type':'RECRUITMENT_AGENCY' if agency else 'MANUAL','discovered_via':data.source,'first_seen':j.date_found}
        j.analysis={**(j.analysis or {}),'workflow_status_preserved':True}
        analyze(db,j)
        return {**serialize(j),'duplicate':d}
@app.post('/api/import/url')
def import_url(data:dict):
    url=data.get('url','')
    if linkedin(url): raise ValueError('LinkedIn: use Add job and paste the description; this URL will not be fetched')
    raise ValueError('Arbitrary webpage imports are disabled pending platform and destination review. Add a public company board in Discovery, or paste the job description using Add job.')
@app.get('/api/jobs/{id}')
def job_detail(id:int):
    with Session() as db:
        j=get_job(db,id); a=db.scalar(select(Application).where(Application.job_id==id))
        from .campaign import fit,review_signals,remote_scope
        history=[{'id':x.id,'title':other.title,'status':x.tracking.get('stage',x.status),'date':x.applied_date} for x,other in db.execute(select(Application,Job).join(Job,Application.job_id==Job.id)) if norm(other.company)==norm(j.company) and x.job_id!=j.id]
        return {**serialize(j),'fit_band':fit(j),'review_signals':review_signals(j),'remote_scope':remote_scope(j),'company_history':history,'application':serialize(a) if a else None,'resumes':[serialize(x) for x in db.scalars(select(ResumeVersion).where(ResumeVersion.job_id==id))],'letters':[serialize(x) for x in db.scalars(select(CoverLetter).where(CoverLetter.job_id==id))],'events':[serialize(x) for x in db.scalars(select(ApplicationEvent).where(ApplicationEvent.job_id==id))],'questions':[serialize(x) for x in db.scalars(select(ApplicationQuestion).where(ApplicationQuestion.application_id==a.id))] if a else [],'browser_runs':[serialize(x) for x in db.scalars(select(BrowserRun).where(BrowserRun.application_id==a.id))] if a else []}
@app.post('/api/jobs/{id}/{action}')
def job_action(id:int,action:str,data:dict={}):
    with Session() as db:
        j=get_job(db,id)
        if action=='analyze': result=analyze(db,j)
        elif action=='cv': result=serialize(generate_cv(db,j))
        elif action=='cover': result=serialize(cover(db,j))
        elif action=='prepare': result=serialize(prepare(db,j))
        elif action=='status':
            # Issue #46: the legacy workflow status still moves exactly as
            # before (compatibility projection), and the same user assertion
            # is then offered to the authoritative state service, which either
            # records the canonical transition with its provenance or records
            # a bounded reason why it is not permitted. The handler invents no
            # transition rule of its own.
            from .application_state import prime_state,pre_action_state,record_legacy_assertion,SOURCE_USER_ACTION
            existing=db.scalar(select(Application).where(Application.job_id==j.id))
            # Capture where this application was BEFORE set_status() rewrites
            # Application.status/Job.status. When no Application exists yet,
            # set_status() creates one already in the requested state, so a
            # first-ever bootstrap taken afterwards would read the user's own
            # edit back and record a brand-new user action as LEGACY_MIGRATION
            # with no manual authority. The captured state is handed to the
            # state service as the bootstrap baseline instead.
            before=pre_action_state(db,j,existing)
            prime_state(db,existing)
            application=set_status(db,j,data.get('status',''))
            record_legacy_assertion(db,application,data.get('status',''),source_category=SOURCE_USER_ACTION,asserted_by='USER',bootstrap_from=before)
            result=serialize(application)
        elif action=='browser': result=run_browser(db,j,data.get('mode','ASSISTED'),data.get('dry_run',True))
        elif action=='ai':
            p=candidate(db)
            if not p['confirmed']: raise ValueError('Confirm profile facts before requesting model advice')
            facts={str(s['id']):s['text'] for s in p['skills']}; result=provider(settings(db)['provider'],consent=data.get('allow_cloud') is True).advise(j.description,facts).model_dump(); j.analysis={**j.analysis,'ai_advice':result}
        else: raise HTTPException(404)
        db.commit(); return result
@app.post('/api/bulk/prepare')
def bulk(data:dict):
    ids=data.get('ids',[])
    if not isinstance(ids,list) or len(ids)>100 or any(type(i) is not int or i<=0 for i in ids):raise ValueError('Select at most 100 valid jobs')
    result=[]
    for id in ids[:100]:
        try: result.append({'id':id,'result':job_action(id,'prepare')})
        # Fixed strings only: no exception text reaches a client from here. The
        # per-job route reports the specific reason when it is opened, and the
        # cause of an unexpected failure is written to the local log. Every id
        # is a positive int by the check above, so int() cannot carry a newline
        # into a log record; log_safe covers the free-text values elsewhere.
        except HTTPException:
            logger.exception('Bulk preparation rejected job %d',int(id))
            result.append({'id':id,'error':'This job is no longer available. Reload the list.'})
        except ValueError:
            logger.exception('Bulk preparation validation failed for job %d',int(id))
            result.append({'id':id,'error':'This job needs attention before it can be prepared. Open it to see what is required.'})
        except Exception:
            logger.exception('Bulk preparation failed for job %d',int(id))
            result.append({'id':id,'error':UNEXPECTED_FAILURE})
    return result
COLLECTIONS={'applications':Application,'answers':ApprovedAnswer,'interviews':Interview,'followups':FollowUp,'sources':JobSource,'sites':SiteAdapter,'logs':ApplicationEvent,'runs':AutomationRun,'documents':ResumeVersion,'recruiters':Recruiter}
@app.get('/api/records/{kind}')
def records(kind:str):
    if kind not in COLLECTIONS: raise HTTPException(404)
    with Session() as db: return [serialize(x) for x in db.scalars(select(COLLECTIONS[kind]).order_by(COLLECTIONS[kind].id.desc()))]
@app.post('/api/records/{kind}')
def save_record(kind:str,data:dict):
    if kind not in ('answers','interviews','followups','sources','sites','recruiters'): raise ValueError('Read-only collection')
    model=COLLECTIONS[kind]
    from .input_rules import record_input
    data=record_input(kind,data,model)
    if kind=='answers': data['normalized_question']=norm(data.get('question',''))
    if kind=='sites':
        domain=data.get('domain','').lower().strip().rstrip('.')
        if not re.fullmatch(r'[a-z0-9.-]+',domain) or linkedin('https://'+domain): raise ValueError('Invalid domain or LinkedIn is blocked')
        data['domain']=domain
    if kind=='sources' and (data.get('adapter')=='linkedin' or linkedin(data.get('url',''))): raise ValueError('LinkedIn cannot be monitored')
    with Session.begin() as db:
        row=db.get(model,data['id']) if data.get('id') else model()
        if row is None: raise ValueError('Record not found')
        for k,v in data.items():
            if k in model.__table__.columns.keys() and k not in ('id','created_at','updated_at'): setattr(row,k,v)
        db.add(row); db.flush(); return serialize(row)
@app.get('/api/career-tracks')
def career_tracks_list():
    return career_tracks.public_tracks()
@app.get('/api/profile/career-suggestions')
def career_suggestions():
    with Session() as db:
        p=candidate(db) if db.scalar(select(CandidateProfile)) else None
        if not p: return []
        text=' '.join([p.get('raw_text',''),p.get('summary','')]+[s['text'] for s in p.get('skills',[])])
        return career_tracks.suggest(text)
@app.post('/api/settings/career-focus')
def set_career_focus(data:dict):
    ids=[x for x in data.get('career_tracks',[]) if isinstance(x,str)]
    if any(x not in career_tracks.TRACKS for x in ids): raise ValueError('Unknown career track')
    custom=[x.strip() for x in data.get('custom_target_roles',[]) if isinstance(x,str) and x.strip()][:20]
    if any(len(x)>200 for x in custom): raise ValueError('Target role titles must be under 200 characters')
    if not ids and not custom: raise ValueError('Choose at least one career track or add a custom target role')
    with Session.begin() as db:
        cfg={**settings(db),'career_tracks':ids,'custom_target_roles':custom}
        cfg['target_roles']=career_tracks.target_role_titles(cfg)
        cfg['search_focus_confirmed']=True
        cfg['career_profile_version']=career_tracks.VERSION
        db.get(Settings,1).value=cfg
        return cfg
@app.get('/api/settings')
def get_settings():
    with Session() as db: return settings(db)
@app.put('/api/settings')
def put_settings(data:dict):
    with Session.begin() as db:
        cfg={**settings(db),**{k:v for k,v in data.items() if k in DEFAULTS}}
        from .input_rules import settings_input
        settings_input(cfg,DEFAULTS)
        if cfg['autopilot'] not in ('OFF','PREPARE_ONLY'): raise ValueError('Automatic submission is disabled. Choose OFF or PREPARE_ONLY.')
        cfg['dry_run']=True
        if cfg['provider'] not in ('rules','ollama','openai'): raise ValueError('Unknown model provider')
        if type(cfg['ai_daily_limit']) is not int or not 0<=cfg['ai_daily_limit']<=100:
            raise ValueError('Daily AI limit must be a whole number from 0 to 100')
        if type(cfg['discovery_enabled']) is not bool or type(cfg['discovery_interval_hours']) is not int or cfg['discovery_interval_hours'] not in (3,6,12,24): raise ValueError('Choose scans every 3, 6, 12 or 24 hours')
        if not 0<=int(cfg['daily_limit'])<=100 or not 0<=int(cfg['max_retries'])<=5: raise ValueError('Invalid limits')
        if set(cfg['weights'])!=set(DEFAULTS['weights']) or any(not isinstance(v,(int,float)) or v<0 for v in cfg['weights'].values()) or sum(cfg['weights'].values())<=0: raise ValueError('Invalid scoring weights')
        for name,t in cfg['schedule'].items():
            if name not in DEFAULTS['schedule'] or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',t): raise ValueError('Schedules must use HH:MM')
        db.get(Settings,1).value=cfg
    configure_schedule(); return cfg
@app.post('/api/sync')
def sync():
    with Session() as db:campaign_enabled=settings(db).get('campaign_workbook')
    if campaign_enabled:
        from .campaign import pending
        from .workbook import retry_sync
        with Session.begin() as db:pending(db)
        retry_sync()
        with Session() as db:
            state=db.get(WorkbookSync,1)
            return {'path':'tracker.xlsx','pending':state.revision>state.exported_revision,'message':state.error or ('Excel update pending' if state.revision>state.exported_revision else 'Excel tracker synchronized')}
    with Session.begin() as db: return sync_tracker(db)
@app.post('/api/tasks/{name}')
def run_task(name:str):
    if name=='discover': raise ValueError('Scans start only from Start Scan in Discovery: review the scope, then confirm.')
    return task(name)
@app.post('/api/browser/test')
def test_browser(): return browser_test()
@app.post('/api/browser/rehearsal')
def test_rehearsal():
    from .rehearsal import rehearse
    return rehearse()
DOWNLOAD_NAME=re.compile(r'[A-Za-z0-9._-]+')
DOWNLOAD_SUFFIXES=('.pdf','.docx','.xlsx','.png')
@app.get('/api/files/{path:path}')
def file_download(path:str):
    # Each component is allowlisted before the join, so no traversal, absolute,
    # UNC or drive-qualified path is ever built. Containment is then re-checked
    # after resolution, which also stops a symlink inside the data directory
    # from pointing outside it.
    parts=[p for p in path.replace('\\','/').split('/') if p]
    if not parts or any(p in ('.','..') or not DOWNLOAD_NAME.fullmatch(p) for p in parts): raise HTTPException(404)
    root=DATA.resolve()
    target=root.joinpath(*parts).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.suffix not in DOWNLOAD_SUFFIXES: raise HTTPException(404)
    return FileResponse(target,filename=target.name)
from .search_workspace import router as search_router
app.include_router(search_router)
from .scan_control import router as scan_router
app.include_router(scan_router)
from .campaign import router as campaign_router
from . import source_catalog
app.include_router(campaign_router)
from .privacy import router as privacy_router
app.include_router(privacy_router)
from .recall_api import router as recall_router
app.include_router(recall_router)
from .gmail_api import router as gmail_router
app.include_router(gmail_router)
from .application_state_api import router as application_state_router
app.include_router(application_state_router)
dist=Path(__file__).resolve().parents[1]/'frontend'/'dist'
@app.get('/demo',include_in_schema=False)
def demo_page():
    if not dist.exists(): raise HTTPException(404)
    return FileResponse(dist/'index.html')
if dist.exists(): app.mount('/',StaticFiles(directory=dist,html=True),name='ui')

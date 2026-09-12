"""Local data controls. Destructive actions require an exact scope confirmation."""
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, text
from .models import *

router=APIRouter(prefix='/api/privacy')
POLICY_VERSION='2026-09-11'
PRIVACY_COPY={
    'local':'Your CV, extracted profile, answers, preferences, saved jobs, application history and generated documents are stored on this computer. They are not uploaded by discovery or document preparation.',
    'network':'Enabled public-board scans send your IP address and requested board URL to the source. Opening a job link uses your browser and the destination’s privacy rules.',
    'models':'Rules mode makes no model request. Ollama is restricted to this device. Each OpenAI advice request requires your approval and sends the current job description and your listed skills to api.openai.com. Model advice is unverified commentary, never an approved career fact.',
    'submission':'The app does not fill external forms, upload CVs to employers or submit applications. Review your documents and answers, then submit in your own browser. Assessments and optional demographic answers stay under your direct control.',
    'storage':'Local files and SQLite are not encrypted by this app. Protect your OS account and use disk encryption. API credentials saved here use the operating system credential store. No analytics or remote error-reporting service is configured.',
    'deletion':'Deletion removes app-managed records, derived documents, tracker copies, backups and browser-session files for the selected scope. Downloaded/exported copies, original uploads outside the app, cloud-provider retention and employer records cannot be erased here. SSD recovery, OS backups and synced folders may retain copies.',
    'export':'Exports contain private information and are unencrypted. Browser sessions and API credentials are excluded. Keep exports somewhere you control.'
}

def managed_files():
    root=DATA.resolve()
    project=Path(__file__).resolve().parents[1]
    if root==Path(root.anchor) or root==Path.home().resolve() or root==project or root in project.parents:
        raise ValueError('Use a dedicated application data folder before export or deletion')
    db_path=Path(engine.url.database).resolve() if engine.url.database else None
    active_db={str(db_path)+suffix for suffix in ('','-wal','-shm','-journal')} if db_path else set()
    known_files={'master.pdf','incoming.pdf','incoming.xlsx','tracker.xlsx','tracker_previous.xlsx','tracker.tmp.xlsx',
                 'hunter.db','hunter.db-wal','hunter.db-shm','hunter.db-journal',
                 'security-events.log','security-events.log.1','ai-usage.db','ai-usage.db-journal','ai-usage.db-wal','ai-usage.db-shm'}
    known_directories={'documents','backups','screenshots','browser_profiles'}
    # A wrongly configured data root must never turn these controls into a general
    # filesystem exporter or recursive eraser. Inspect before touching any files.
    for entry in root.iterdir():
        if entry.is_symlink() or (hasattr(entry,'is_junction') and entry.is_junction()):
            raise ValueError('Data directory contains a link; review it before export or deletion')
        name=entry.name.lower()
        if str(entry.resolve()) in active_db: continue
        if (entry.is_dir() and (name in known_directories or name.startswith('.import-'))) or (entry.is_file() and (name in known_files or (name.startswith('.master-') and name.endswith('.pdf')))): continue
        raise ValueError('The data folder contains unrecognized files or folders. Move unrelated items outside it before export or deletion; no files were removed.')
    files=[]
    for path in DATA.rglob('*'):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('Data directory contains a link; review it before export or deletion')
        if not path.resolve().is_relative_to(root): raise ValueError('Unsafe data path')
        if path.is_file():
            # Only the active database is excluded: an old hunter.db from a prior
            # database location also contains private data and must be removed.
            if str(path.resolve()) in active_db: continue
            files.append(path)
    return files

@router.get('')
def privacy_info():
    with Session() as db:
        return {'policy_version':POLICY_VERSION,'storage_path':str(DATA),'copy':PRIVACY_COPY,
                'counts':{table.name:db.scalar(select(__import__('sqlalchemy').func.count()).select_from(table)) for table in Base.metadata.sorted_tables},
                'external_form_automation':False,'encrypted_by_app':False,
                'platforms':platforms(),'application_profile':application_profile(db)}

def platforms():
    refs={'greenhouse':'https://docs.greenhouse.io/job-board.html','lever':'https://github.com/lever/postings-api','ashby':'https://developers.ashbyhq.com/docs/public-job-posting-api'}
    return [{'platform':name,'discovery':'PUBLIC READ API','submission':'MANUAL ONLY','source':url,'reviewed':POLICY_VERSION} for name,url in refs.items()]+[
        {'platform':'LinkedIn','discovery':'DISABLED','submission':'MANUAL ONLY','source':'No integration enabled','reviewed':POLICY_VERSION},
        {'platform':'Other websites','discovery':'DISABLED — PASTE DESCRIPTION','submission':'MANUAL ONLY','source':'Site-specific terms not verified','reviewed':POLICY_VERSION}]

@router.get('/export')
async def export_data():
    from .main import mutation_lock
    # Mutating API requests use this same lock. Build the complete archive before
    # releasing it so records and their documents describe one coherent state.
    async with mutation_lock:
        return await run_in_threadpool(_export_data)

def _export_data():
    from .main import task_lock
    if not task_lock.acquire(False): raise HTTPException(409,'Wait for the current scan or task to finish')
    try:
        # Browser cookies and sessions are intentionally never exported.
        files=[p for p in managed_files() if not p.name.startswith(('security-events.log','ai-usage.db')) and not any(part.lower()=='browser_profiles' or part.lower().startswith('.import-') for part in p.relative_to(DATA).parts)]
        if sum(p.stat().st_size for p in files)>100_000_000: raise ValueError('Export exceeds 100 MB; use a protected local backup while the app is stopped')
        with Session() as db:
            records={table.name:[dict(row) for row in db.execute(select(table)).mappings()] for table in Base.metadata.sorted_tables}
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('records.json',json.dumps(records,ensure_ascii=False,indent=2))
            archive.writestr('README.txt',PRIVACY_COPY['export']+'\nSchema version: '+POLICY_VERSION)
            for path in files: archive.write(path,'files/'+path.relative_to(DATA).as_posix())
        return Response(buffer.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="job-search-private-export.zip"','Cache-Control':'no-store'})
    finally: task_lock.release()

class DeleteRequest(BaseModel):
    scope:Literal['cv','history','all']
    confirmation:str

@router.post('/delete')
def delete_data(request:DeleteRequest):
    expected={'cv':'DELETE CV','history':'DELETE APPLICATION HISTORY','all':'DELETE ALL LOCAL DATA'}[request.scope]
    if request.confirmation!=expected: raise ValueError('Type '+expected+' to confirm this deletion')
    from .main import task_lock
    if not task_lock.acquire(False): raise HTTPException(409,'Wait for the current scan or task to finish')
    try:
        files=managed_files()
        if request.scope!='all': files=[p for p in files if not p.name.startswith('ai-usage.db')]
        if request.scope=='history': files=[p for p in files if p.name not in ('master.pdf','incoming.pdf')]
        if request.scope=='all': delete_credential('openai')
        # Preflight all paths before removing anything. A filesystem failure is surfaced,
        # never reported as success; retry can finish the idempotent deletion.
        for path in files: path.unlink()
        removed_models={ResumeVersion,CoverLetter,ApplicationQuestion,BrowserRun,ApplicationEvent,AutomationRun,WorkbookSync}
        if request.scope in ('cv','all'): removed_models|={Skill,Employment,Education,Certification,Project,ApprovedAnswer,CandidateProfile}
        if request.scope in ('history','all'): removed_models|={Recruiter,FollowUp,Interview,Application}
        if request.scope=='all': removed_models|={Job,JobSource,SiteAdapter,AutomationRun}
        with Session.begin() as db:
            tables={model.__table__ for model in removed_models}
            for table in reversed(Base.metadata.sorted_tables):
                if table in tables: db.execute(delete(table))
            if request.scope!='all':
                for job in db.scalars(select(Job)):
                    job.notes=''; job.analysis={}; job.matching_skills=[]; job.missing_skills=[]; job.red_flags=[]
                    if request.scope=='history': job.status='FOUND'
                for app in db.scalars(select(Application)):
                    app.recruiter_message={}; app.confirmation=''
                for interview in db.scalars(select(Interview)): interview.notes=''
                for follow in db.scalars(select(FollowUp)): follow.message=''
            cfg=db.get(Settings,1)
            if cfg:
                cfg.value={**DEFAULTS,'autopilot':'OFF','discovery_enabled':False,'wizard_step':1} if request.scope=='all' else {**cfg.value,'profile_confirmed':False}
                if request.scope=='cv': cfg.value={k:v for k,v in cfg.value.items() if k not in ('application_profile','application_profile_provenance')}
        # SQLite secure_delete clears removed cells; reclaim WAL/free pages after commit.
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
            connection.exec_driver_sql('VACUUM')
        return {'deleted':request.scope,'files_removed':len(files),'limitations':PRIVACY_COPY['deletion']}
    finally: task_lock.release()

def credential_backend():
    import keyring
    backend=keyring.get_keyring()
    module=type(backend).__module__
    if module not in ('keyring.backends.Windows','keyring.backends.macOS','keyring.backends.SecretService'):
        try:
            from .security_events import record
            record('SECRET_STORAGE_UNAVAILABLE','Native credential store unavailable; failing closed',backend=module)
        except Exception: pass
        raise ValueError('A supported native secure credential store is unavailable; no plaintext fallback is used')
    return backend

def read_credential(name):
    value=credential_backend().get_password('LocalJobHunter',name)
    if not value: raise ValueError('Save the API key in Privacy & Local Data before using cloud advice')
    return value

def delete_credential(name):
    import keyring.errors
    try: credential_backend().delete_password('LocalJobHunter',name)
    except keyring.errors.PasswordDeleteError: pass

class CredentialInput(BaseModel):
    key:str=Field(min_length=10,max_length=1000)

@router.put('/credentials/openai')
def save_credential(value:CredentialInput):
    credential_backend().set_password('LocalJobHunter','openai',value.key)
    return {'saved':True,'location':'OS secure credential store','cloud_consent_granted':False}

class ApplicationProfile(BaseModel):
    preferred_name:str=Field(default='',max_length=200)
    legal_name:str=Field(default='',max_length=200)
    residence_country:str=Field(default='',max_length=2)
    target_countries:list[str]=Field(default_factory=list,max_length=20)
    ui_locale:str=Field(default='en-GB',max_length=35)
    cv_language:str=Field(default='',max_length=35)
    timezone:str=Field(default='Asia/Dubai',max_length=100)
    relocation:Literal['UNKNOWN','YES','NO']='UNKNOWN'
    work_modes:list[Literal['remote','hybrid','on-site']]=Field(default_factory=list)
    languages:list[str]=Field(default_factory=list,max_length=30)
    work_authorisation:dict[str,Literal['UNKNOWN','YES','NO']]=Field(default_factory=dict)
    sponsorship:dict[str,Literal['UNKNOWN','YES','NO']]=Field(default_factory=dict)
    notice_period:str=Field(default='',max_length=200)
    salary_amount:str=Field(default='',max_length=30)
    salary_currency:str=Field(default='',max_length=3)
    salary_period:Literal['UNKNOWN','hour','day','week','month','year']='UNKNOWN'
    portfolio:str=Field(default='',max_length=1000)
    github:str=Field(default='',max_length=1000)
    linkedin:str=Field(default='',max_length=1000)
    travel:Literal['UNKNOWN','YES','NO']='UNKNOWN'
    role_preferences:list[str]=Field(default_factory=list,max_length=100)

def application_profile(db):
    cfg=db.get(Settings,1)
    return ApplicationProfile(**((cfg.value if cfg else {}).get('application_profile',{}))).model_dump()

@router.put('/application-profile')
def save_application_profile(value:ApplicationProfile):
    from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
    import re
    try: ZoneInfo(value.timezone)
    except (ZoneInfoNotFoundError,ValueError): raise ValueError('Choose an IANA timezone') from None
    codes=[value.residence_country,*value.target_countries,*value.work_authorisation,*value.sponsorship]
    if any(c and not re.fullmatch('[A-Z]{2}',c) for c in codes): raise ValueError('Use two-letter country codes, for example AE or DE')
    if value.salary_currency and not re.fullmatch('[A-Z]{3}',value.salary_currency): raise ValueError('Use a three-letter currency code')
    if not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*',value.ui_locale): raise ValueError('Use a locale such as ar-AE, en-GB or de-DE')
    for url in (value.portfolio,value.github,value.linkedin):
        if url:
            from urllib.parse import urlsplit
            p=urlsplit(url)
            if p.scheme!='https' or not p.hostname or p.username or p.password: raise ValueError('Profile links must be HTTPS without credentials')
    if any(len(s)>300 for s in value.languages+value.role_preferences): raise ValueError('Profile field is too long')
    with Session.begin() as db:
        cfg=db.get(Settings,1)
        cfg.value={**cfg.value,'application_profile':value.model_dump(),'application_profile_provenance':{'state':'USER PROVIDED','updated_at':now()}}
    from .main import configure_schedule
    configure_schedule()
    return value.model_dump()

@router.get('/self-check')
def self_check():
    from .doctor import run_checks
    checks=run_checks()
    order={'PASS':0,'WARNING':1,'FAIL':2}
    overall=max((c['status'] for c in checks),key=lambda s:order[s],default='PASS')
    return {'overall':overall,'checks':checks}

@router.get('/security-events')
def security_events(limit:int=100):
    from .security_events import tail
    return {'events':tail(min(max(limit,1),500))}

@router.get('/ai-usage')
def ai_usage():
    from .ai_usage import snapshot
    return snapshot()

@router.get('/market/{country}')
def market_policy(country:str):
    return {'market':country.upper()[:2],'version':POLICY_VERSION,'source':None,'last_reviewed':None,'state':'LOCAL GUIDANCE NOT VERIFIED',
            'guidance':'Use a generic skills, experience, education and contact template. Review the employer instructions. No photo, birth date, nationality or sensitive details are added automatically. This is not legal advice or a claim of local compliance.'}

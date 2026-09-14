import os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, String, Text, JSON, ForeignKey, UniqueConstraint, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from dotenv import load_dotenv

load_dotenv()
def require_local_path(path):
    path=Path(path).resolve()
    if str(path).startswith(('\\\\','//')): raise RuntimeError('Network storage is disabled; choose a local data directory')
    if os.name=='nt':
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor))==4: raise RuntimeError('Mapped network storage is disabled')
    return path
DATA = require_local_path(os.getenv('HUNTER_DATA_DIR', Path(__file__).resolve().parents[1] / 'data'))
DATA.mkdir(parents=True, exist_ok=True,mode=0o700)
def now(): return datetime.now(timezone.utc).isoformat()
class Base(DeclarativeBase): pass
class Record:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now, onupdate=now)
class CandidateProfile(Record, Base):
    __tablename__='candidate_profiles'
    name: Mapped[str] = mapped_column(default='UNKNOWN')
    email: Mapped[str] = mapped_column(default='UNKNOWN')
    phone: Mapped[str] = mapped_column(default='UNKNOWN')
    location: Mapped[str] = mapped_column(default='UNKNOWN')
    summary: Mapped[str] = mapped_column(Text, default='')
    raw_text: Mapped[str] = mapped_column(Text, default='')
    confirmed: Mapped[bool] = mapped_column(default=False)
    declarations: Mapped[dict] = mapped_column(JSON, default=dict)
class Fact(Record):
    candidate_id: Mapped[int] = mapped_column(ForeignKey('candidate_profiles.id'))
    text: Mapped[str] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(default='MASTER CV')
class Skill(Fact, Base):
    __tablename__='skills'
    context: Mapped[str] = mapped_column(default='listed in master CV')
class Employment(Fact, Base): __tablename__='employments'
class Education(Fact, Base): __tablename__='education'
class Certification(Fact, Base): __tablename__='certifications'
class Project(Fact, Base): __tablename__='projects'
class JobSource(Record, Base):
    __tablename__='job_sources'
    name: Mapped[str]
    adapter: Mapped[str] = mapped_column(default='generic')
    board: Mapped[str] = mapped_column(default='')
    url: Mapped[str] = mapped_column(default='')
    enabled: Mapped[bool] = mapped_column(default=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
class Job(Record, Base):
    __tablename__='jobs'
    company: Mapped[str]
    title: Mapped[str]
    location: Mapped[str] = mapped_column(default='UNKNOWN')
    remote_status: Mapped[str] = mapped_column(default='UNKNOWN')
    job_url: Mapped[str] = mapped_column(default='')
    canonical_url: Mapped[str] = mapped_column(default='', index=True)
    source: Mapped[str] = mapped_column(default='Manual')
    source_job_id: Mapped[str] = mapped_column(default='')
    description: Mapped[str] = mapped_column(Text, default='')
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    preferred_requirements: Mapped[list] = mapped_column(JSON, default=list)
    salary: Mapped[str] = mapped_column(default='UNKNOWN')
    employment_type: Mapped[str] = mapped_column(default='UNKNOWN')
    experience_requirement: Mapped[str] = mapped_column(default='UNKNOWN')
    date_found: Mapped[str] = mapped_column(default=now)
    date_posted: Mapped[str] = mapped_column(default='')
    closing_date: Mapped[str] = mapped_column(default='')
    match_score: Mapped[int] = mapped_column(default=0)
    hard_requirement_score: Mapped[int] = mapped_column(default=0)
    skill_score: Mapped[int] = mapped_column(default=0)
    experience_score: Mapped[int] = mapped_column(default=0)
    education_score: Mapped[int] = mapped_column(default=0)
    location_score: Mapped[int] = mapped_column(default=0)
    priority: Mapped[str] = mapped_column(default='UNSCORED')
    missing_skills: Mapped[list] = mapped_column(JSON, default=list)
    matching_skills: Mapped[list] = mapped_column(JSON, default=list)
    red_flags: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(default='NEEDS_REVIEW')
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default='FOUND')
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey('jobs.id'), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default='')
    # Issue #40: additive-only. apply_url is the application URL kept
    # separate from job_url/canonical_url (the original posting URL);
    # normalization_version/dedupe_fingerprint support the conservative
    # cross-provider match rule (backend/deduplication.py Rule 4) without a
    # quadratic all-Job scan. A pre-#40 Job keeps these at their defaults
    # until a new observation resolves onto it.
    apply_url: Mapped[str] = mapped_column(default='')
    normalization_version: Mapped[str] = mapped_column(default='')
    dedupe_fingerprint: Mapped[str] = mapped_column(default='', index=True)
class JobObservation(Record, Base):
    """One provider/manual OBSERVATION of a posting (issue #40). Job stays
    the stable, compatibility-facing canonical row (Owner Decision 1) --
    this table is purely additive provenance/evidence, never a second
    canonical job model. See docs/architecture/adr/0010-job-observation-
    and-conservative-deduplication.md.
    """
    __tablename__='job_observations'
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    job_source_id: Mapped[int | None] = mapped_column(ForeignKey('job_sources.id'), nullable=True)
    provider_family: Mapped[str] = mapped_column(default='manual')
    provider_version: Mapped[str] = mapped_column(default='')
    board_key: Mapped[str] = mapped_column(default='')
    # 'native' | 'url_fallback' | 'manual' | 'legacy_incomplete' -- see
    # backend/normalization.py IDENTITY_KINDS.
    identity_kind: Mapped[str] = mapped_column(default='manual')
    provider_job_id: Mapped[str] = mapped_column(default='')
    requisition_id: Mapped[str] = mapped_column(default='', index=True)
    requisition_id_authority: Mapped[str] = mapped_column(default='')
    employer_name_observed: Mapped[str] = mapped_column(default='UNKNOWN')
    title_observed: Mapped[str] = mapped_column(default='')
    location_observed: Mapped[str] = mapped_column(default='UNKNOWN')
    workplace_observed: Mapped[str] = mapped_column(default='UNKNOWN')
    description_observed: Mapped[str] = mapped_column(Text, default='')
    source_url: Mapped[str] = mapped_column(default='')
    apply_url: Mapped[str] = mapped_column(default='')
    posted_at: Mapped[str] = mapped_column(default='')
    # 'documented_provider_field' | 'legacy_carried_forward' | 'none' -- only
    # 'documented_provider_field' may ever populate authoritative Job.date_posted.
    posted_at_authority: Mapped[str] = mapped_column(default='none')
    closing_at: Mapped[str] = mapped_column(default='')
    retrieved_at: Mapped[str] = mapped_column(default='')
    provider_facts: Mapped[dict] = mapped_column(JSON, default=dict)
    anomaly_flags: Mapped[list] = mapped_column(JSON, default=list)
    first_seen_at: Mapped[str] = mapped_column(default=now)
    last_seen_at: Mapped[str] = mapped_column(default=now)
    normalization_version: Mapped[str] = mapped_column(default='')
    fingerprint: Mapped[str] = mapped_column(default='', index=True)
    match_method: Mapped[str] = mapped_column(default='')
    match_version: Mapped[str] = mapped_column(default='')
    match_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__=(
        # SQLite/standard SQL treat NULL as distinct from any other NULL for
        # a UNIQUE constraint, so multiple 'manual'/'legacy_incomplete' rows
        # (job_source_id always NULL for those) never collide here -- this
        # only actually constrains real provider identity, which always
        # carries a concrete job_source_id (Phase 6: never scope uniqueness
        # by provider_family + provider_job_id alone).
        UniqueConstraint('provider_family','job_source_id','identity_kind','provider_job_id',name='uq_job_observation_identity'),
    )
class Application(Record, Base):
    __tablename__='applications'
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'), unique=True)
    status: Mapped[str] = mapped_column(default='NEEDS_REVIEW')
    mode: Mapped[str] = mapped_column(default='PREPARE_ONLY')
    applied_date: Mapped[str] = mapped_column(default='')
    confirmation: Mapped[str] = mapped_column(default='')
    recruiter_message: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(default=0)
    submission_attempted: Mapped[bool] = mapped_column(default=False)
    submission_started_at: Mapped[str] = mapped_column(default='')
    tracking: Mapped[dict] = mapped_column(JSON, default=dict)
class ApplicationQuestion(Record, Base):
    __tablename__='application_questions'
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id'))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default='UNKNOWN')
    required: Mapped[bool] = mapped_column(default=True)
class ApprovedAnswer(Record, Base):
    __tablename__='approved_answers'
    question: Mapped[str]
    normalized_question: Mapped[str] = mapped_column(unique=True)
    answer: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(default='general')
    approved: Mapped[bool] = mapped_column(default=False)
    last_used: Mapped[str] = mapped_column(default='')
    notes: Mapped[str] = mapped_column(default='')
class ResumeVersion(Record, Base):
    __tablename__='resume_versions'
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    pdf_path: Mapped[str]
    docx_path: Mapped[str]
    master: Mapped[str] = mapped_column(Text)
    tailored: Mapped[str] = mapped_column(Text)
    diff: Mapped[str] = mapped_column(Text)
    fact_ids: Mapped[list] = mapped_column(JSON)
class CoverLetter(Record, Base):
    __tablename__='cover_letters'
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    text: Mapped[str] = mapped_column(Text)
class Recruiter(Record, Base):
    __tablename__='recruiters'
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id'))
    name: Mapped[str]
    contact: Mapped[str] = mapped_column(default='')
    contacted: Mapped[bool] = mapped_column(default=False)
class FollowUp(Record, Base):
    __tablename__='followups'
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id'), unique=True)
    due_date: Mapped[str]
    done: Mapped[bool] = mapped_column(default=False)
    message: Mapped[str] = mapped_column(Text, default='')
class Interview(Record, Base):
    __tablename__='interviews'
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id'))
    stage: Mapped[str] = mapped_column(default='Recruiter Screen')
    date: Mapped[str]
    timezone: Mapped[str] = mapped_column(default='Asia/Dubai')
    interviewer: Mapped[str] = mapped_column(default='')
    meeting_url: Mapped[str] = mapped_column(default='')
    notes: Mapped[str] = mapped_column(Text, default='')
class AutomationRun(Record, Base):
    __tablename__='automation_runs'
    task: Mapped[str]
    status: Mapped[str] = mapped_column(default='RUNNING')
    report: Mapped[dict] = mapped_column(JSON, default=dict)
class BrowserRun(Record, Base):
    __tablename__='browser_runs'
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id'))
    site: Mapped[str]
    step: Mapped[str] = mapped_column(default='start')
    error: Mapped[str] = mapped_column(default='')
    retryable: Mapped[bool] = mapped_column(default=False)
    screenshot_before: Mapped[str] = mapped_column(default='')
    screenshot_after: Mapped[str] = mapped_column(default='')
    dry_run: Mapped[bool] = mapped_column(default=True)
class ApplicationEvent(Record, Base):
    __tablename__='application_events'
    job_id: Mapped[int | None] = mapped_column(ForeignKey('jobs.id'), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(default='INFO')
    application_id: Mapped[int | None] = mapped_column(ForeignKey('applications.id'), nullable=True)
    event_type: Mapped[str] = mapped_column(default='LOG')
    occurred_at: Mapped[str] = mapped_column(default=now)
    source: Mapped[str] = mapped_column(default='SYSTEM')
    stage: Mapped[str] = mapped_column(default='')
class WorkbookSync(Base):
    __tablename__='workbook_sync'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    revision: Mapped[int] = mapped_column(default=0)
    exported_revision: Mapped[int] = mapped_column(default=0)
    last_success: Mapped[str] = mapped_column(default='')
    error: Mapped[str] = mapped_column(default='')
class SiteAdapter(Record, Base):
    __tablename__='site_adapters'
    domain: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str] = mapped_column(default='generic')
    enabled: Mapped[bool] = mapped_column(default=False)
    auto_submit: Mapped[bool] = mapped_column(default=False)
    permitted: Mapped[bool] = mapped_column(default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
class Settings(Base):
    __tablename__='settings'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    value: Mapped[dict] = mapped_column(JSON, default=dict)

database_url=os.getenv('DATABASE_URL',f'sqlite:///{DATA / "hunter.db"}')
from sqlalchemy.engine import make_url
parsed_database=make_url(database_url)
if parsed_database.drivername != 'sqlite' or parsed_database.host or (parsed_database.database or '').startswith(('//','\\\\')) or parsed_database.query:
    raise RuntimeError('Only a local SQLite database is supported. Network database URLs are disabled.')
if parsed_database.database and parsed_database.database!=':memory:': require_local_path(parsed_database.database)
engine=create_engine(database_url,connect_args={'check_same_thread':False,'timeout':30})
if engine.dialect.name=='sqlite':
    @event.listens_for(engine,'connect')
    def sqlite_settings(conn, _):
        conn.execute('PRAGMA foreign_keys=ON'); conn.execute('PRAGMA journal_mode=WAL'); conn.execute('PRAGMA secure_delete=ON')
Session=sessionmaker(engine,expire_on_commit=False)

@event.listens_for(Session.class_,'before_flush')
def queue_workbook(session,flush_context,instances):
    watched=(Application,FollowUp,Interview,Recruiter,ApplicationEvent)
    if not any(isinstance(x,watched) for x in list(session.new)+list(session.dirty)+list(session.deleted)):return
    row=next((x for x in session.new if isinstance(x,WorkbookSync)),None) or session.get(WorkbookSync,1)
    if row is None:row=WorkbookSync(id=1,revision=0,exported_revision=0);session.add(row)
    row.revision=(row.revision or 0)+1
def serialize(obj): return {c.name:getattr(obj,c.name) for c in obj.__table__.columns}
DEFAULTS=dict(autopilot='PREPARE_ONLY',dry_run=True,daily_limit=10,max_retries=2,followup_days=7,minimum_score=70,high_priority=80,maybe_score=60,provider='rules',cover_letter='required',auto_sync=False,profile_confirmed=False,wizard_step=1,blocked_companies=[],blocked_domains=[],career_tracks=['CYBERSECURITY'],custom_target_roles=[],search_focus_confirmed=True,career_profile_version='career-tracks-1',target_roles=['SOC Analyst','Cybersecurity Analyst','Security Analyst','Security Operations Analyst','Information Security Analyst','Information Security Associate','Cybersecurity Associate','SOC Associate','Graduate Cybersecurity Analyst','Graduate Security Analyst','IT Security Analyst','Cyber Defense Analyst','Junior Blue Team Analyst','Security Monitoring Analyst','Vulnerability Management Analyst','Junior Vulnerability Analyst','GRC Analyst','Information Security GRC Associate','Network Security Analyst','Junior Incident Response Analyst'],excluded_roles=['senior','lead','principal','manager','director','head','architect','sales'],locations=['Abu Dhabi','Dubai','UAE','United Arab Emirates'],remote_uae=True,salary_minimum=0,cv_template='ATS',ats_preferences=['greenhouse','lever','ashby'],weights={'skills':30,'experience':25,'role':15,'education':10,'location':10,'seniority':5,'other':5},schedule={'discover':'01:00','analyze':'01:15','prepare':'01:30','process':'02:00','sync':'03:00','report':'07:30'})
DEFAULTS.update(discovery_enabled=True, discovery_interval_hours=3)
DEFAULTS.update(ai_daily_limit=20)
FRESH_DEFAULTS={**DEFAULTS,'career_tracks':[],'custom_target_roles':[],'target_roles':[],'search_focus_confirmed':False}
def settings(db):
    row=db.get(Settings,1)
    return {**DEFAULTS,**(row.value if row else {})}
def log(db,message,job_id=None,level='INFO'):
    db.add(ApplicationEvent(job_id=job_id,message=message,level=level))
def initialize():
    Base.metadata.create_all(engine)
    from sqlalchemy import inspect, text
    if 'submission_started_at' not in {c['name'] for c in inspect(engine).get_columns('applications')}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE applications ADD COLUMN submission_started_at VARCHAR NOT NULL DEFAULT ''"))
    with Session.begin() as db:
        if not db.get(Settings,1): db.add(Settings(id=1,value=FRESH_DEFAULTS))
    additions={'applications':{'tracking':"JSON NOT NULL DEFAULT '{}'"},'job_sources':{'details':"JSON NOT NULL DEFAULT '{}'"},'application_events':{'application_id':'INTEGER REFERENCES applications(id)','event_type':"VARCHAR NOT NULL DEFAULT 'LOG'",'occurred_at':"VARCHAR NOT NULL DEFAULT ''",'source':"VARCHAR NOT NULL DEFAULT 'SYSTEM'",'stage':"VARCHAR NOT NULL DEFAULT ''"},
        # Issue #40: additive Job fields. A pre-#40 database gets these at
        # their neutral defaults; nothing existing is renamed or removed.
        'jobs':{'apply_url':"VARCHAR NOT NULL DEFAULT ''",'normalization_version':"VARCHAR NOT NULL DEFAULT ''",'dedupe_fingerprint':"VARCHAR NOT NULL DEFAULT ''"}}
    with engine.begin() as connection:
        for table,fields in additions.items():
            existing={c['name'] for c in inspect(connection).get_columns(table)}
            for field,definition in fields.items():
                if field not in existing: connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {field} {definition}'))
        # create_all() only creates an index when it creates the column's
        # table for the first time; jobs.dedupe_fingerprint may have just
        # been added by ALTER TABLE above to a table that already existed.
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_jobs_dedupe_fingerprint ON jobs (dedupe_fingerprint)'))
    with Session.begin() as db:
        if not db.get(WorkbookSync,1): db.add(WorkbookSync(id=1))
    _backfill_legacy_observations()

def _backfill_legacy_observations():
    """Issue #40, forward-safe migration only (Owner Decision 2): every
    pre-#40 Job gets EXACTLY ONE JobObservation explicitly marked
    identity_kind='legacy_incomplete', populated only from facts the old
    Job row already had -- never inferring a board/source instance,
    provider identity, or a posted timestamp that was not already trusted.
    Idempotent: a Job that already has at least one observation (this
    backfill having already run, or a real post-#40 discovery having
    already produced one) is never touched again, so repeated startups
    never create duplicate backfill rows. Never consolidates, deletes, or
    reparents anything -- see docs/architecture/adr/0010-job-observation-
    and-conservative-deduplication.md.
    """
    from sqlalchemy import select
    from .normalization import NORMALIZATION_VERSION
    provider_family_for_source={'Greenhouse':'greenhouse','Lever':'lever','Ashby':'ashby','SmartRecruiters':'smartrecruiters'}
    with Session.begin() as db:
        observed_job_ids={row[0] for row in db.execute(select(JobObservation.job_id).distinct())}
        for job in db.scalars(select(Job)):
            if job.id in observed_job_ids: continue
            db.add(JobObservation(
                job_id=job.id, job_source_id=None,
                provider_family=provider_family_for_source.get(job.source,'legacy'),
                provider_version='', board_key='', identity_kind='legacy_incomplete',
                provider_job_id=job.source_job_id or '',
                employer_name_observed=job.company, title_observed=job.title,
                location_observed=job.location, workplace_observed=job.remote_status,
                description_observed=job.description, source_url=job.job_url, apply_url='',
                posted_at=job.date_posted, posted_at_authority='legacy_carried_forward' if job.date_posted else 'none',
                closing_at=job.closing_date, retrieved_at=job.date_found,
                provider_facts={}, anomaly_flags=['legacy_incomplete_backfill'],
                first_seen_at=job.date_found, last_seen_at=job.date_found,
                normalization_version=NORMALIZATION_VERSION, fingerprint='',
                match_method='legacy_backfill', match_version=NORMALIZATION_VERSION, match_evidence={},
            ))

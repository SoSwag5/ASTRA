"""Apply the discovery upgrade without changing any tracked application."""
import sys,sqlite3
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from backend.models import *
from backend.discovery import discovery_reason

backup=DATA/'backups'/('before_discovery_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
backup.parent.mkdir(exist_ok=True)
with sqlite3.connect(DATA/'hunter.db') as src,sqlite3.connect(backup) as dst: src.backup(dst)
initialize()
with Session.begin() as db:
    cfg=settings(db); cfg.update(autopilot='PREPARE_ONLY',dry_run=True,auto_sync=True)
    db.get(Settings,1).value=cfg
    for name,adapter,board,url in [
        ('Lean Technologies','ashby','LeanTech','https://jobs.ashbyhq.com/LeanTech'),
        ('Netcracker','greenhouse','netcracker','https://www.netcracker.com/careers/open-positions'),
    ]:
        source=db.scalar(select(JobSource).where(JobSource.adapter==adapter,JobSource.board==board))
        if not source: source=JobSource(name=name,adapter=adapter,board=board,url=url);db.add(source)
        source.enabled=True
    changed=0;preserved=0
    for job in db.scalars(select(Job)):
        if db.scalar(select(Application).where(Application.job_id==job.id)) or job.status in {'APPLIED','INTERVIEW','OFFER','REJECTED','WITHDRAWN','APPLYING'}:
            preserved+=1;continue
        if job.source not in ('Greenhouse','Ashby','Lever'): continue
        reason=discovery_reason(serialize(job),cfg)
        if reason and job.status!='SKIP':
            job.status=job.recommendation='SKIP';job.red_flags=list(dict.fromkeys([*job.red_flags,reason])); changed+=1
            job.analysis={**job.analysis,'discovery_filter':reason}
            log(db,'Discovery screening: '+reason,job.id)
    log(db,f'Discovery upgraded. {changed} untracked irrelevant jobs skipped; {preserved} tracked applications preserved. Manual submission mode retained.')
    print({'skipped':changed,'tracked_applications_preserved':preserved,'backup':backup.name})

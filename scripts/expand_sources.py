"""Enable verified public feeds, refresh untracked scores, preserve user tracking."""
import sys,sqlite3
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from backend.models import *
from backend.services import analyze

backup=DATA/'backups'/('before_source_expansion_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
backup.parent.mkdir(exist_ok=True)
with sqlite3.connect(engine.url.database) as src,sqlite3.connect(backup) as dst: src.backup(dst)
with Session.begin() as db:
    for name,board in [('Check Point Software Technologies','CheckPointSoftwareTechnologies2'),('VAM Systems','VAMSystems')]:
        row=db.scalar(select(JobSource).where(JobSource.adapter=='smartrecruiters',JobSource.board==board))
        if not row:
            db.add(JobSource(name=name,adapter='smartrecruiters',board=board,url=f'https://jobs.smartrecruiters.com/{board}',enabled=True))
    preserved=0;rescored=0
    profile=db.scalar(select(CandidateProfile))
    for job in db.scalars(select(Job)):
        if db.scalar(select(Application).where(Application.job_id==job.id)) or job.status in {'APPLIED','INTERVIEW','OFFER','REJECTED','WITHDRAWN','APPLYING'}:
            preserved+=1;continue
        if profile: analyze(db,job);rescored+=1
    log(db,f'Public source expansion: SmartRecruiters UAE added. {rescored} untracked jobs rescored, {preserved} application records preserved.')
    print({'rescored':rescored,'applications_preserved':preserved,'backup':backup.name})

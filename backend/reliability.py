"""Local snapshots and an OS-released cross-process discovery lock."""
import hashlib,os,sqlite3,shutil,threading
from datetime import datetime
from pathlib import Path
from .models import engine,DATA

class ProcessLock:
    def __init__(self):self.guard=threading.Lock();self.handle=None
    def acquire(self,blocking=True):
        if not self.guard.acquire(blocking):return False
        directory=Path(__file__).resolve().parents[1]/'.runtime';directory.mkdir(exist_ok=True)
        name=hashlib.sha256(str(engine.url.database).encode()).hexdigest()[:16]
        handle=open(directory/('discovery-'+name+'.lock'),'a+b')
        try:
            handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.handle=handle;return True
        except OSError:handle.close();self.guard.release();return False
    def release(self):
        if self.handle:self.handle.close();self.handle=None
        self.guard.release()
    def locked(self):
        if not self.acquire(False):return True
        self.release();return False

def backup_database(force=False):
    source=Path(engine.url.database)
    if not source.is_file():return None
    folder=DATA/'backups';folder.mkdir(exist_ok=True)
    day=datetime.now().strftime('%Y%m%d')
    if not force and list(folder.glob('daily_'+day+'*.db')):return None
    target=folder/('daily_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
    with sqlite3.connect(source) as src,sqlite3.connect(target) as dest:
        src.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup validation failed')
    if (DATA/'tracker.xlsx').exists():shutil.copy2(DATA/'tracker.xlsx',target.with_suffix('.xlsx'))
    # Only this module's generated daily snapshots rotate; migration backups remain.
    for old in sorted(folder.glob('daily_*.db'),reverse=True)[30:]:
        old.unlink()
        companion=old.with_suffix('.xlsx')
        if companion.exists():companion.unlink()
    return target.name

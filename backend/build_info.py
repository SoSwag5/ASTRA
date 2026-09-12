"""Local source identity, captured once at import to detect stale servers."""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.0-rc.1'

def source_id():
    digest=hashlib.sha256()
    for path in sorted((ROOT/'backend').glob('*.py')):
        digest.update(path.name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()[:16]

STARTED = datetime.now(timezone.utc).isoformat()
BUILD = source_id()

def info():
    return dict(version=VERSION,build=BUILD,started_at=STARTED,stale=BUILD!=source_id())

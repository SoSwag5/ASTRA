"""Local UTC-day request budget. Reservations survive failures and restarts.

SQLite BEGIN IMMEDIATE serializes reservations across processes. No prompt text,
credential, or model response is stored. Same-user file tampering is out of scope.
"""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from .models import DATA, Session, settings

MAX_INPUT = 40_000
MAX_OUTPUT = 1_000
TIMEOUT = 45

def day():
    return datetime.now(timezone.utc).date().isoformat()

def connect():
    conn = sqlite3.connect(DATA / 'ai-usage.db', timeout=10)
    conn.execute('CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, requests INTEGER NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0)')
    conn.execute('CREATE TABLE IF NOT EXISTS lease (id INTEGER PRIMARY KEY, expires REAL NOT NULL, fingerprint TEXT NOT NULL)')
    conn.commit()
    return conn

def snapshot():
    with connect() as conn:
        row = conn.execute('SELECT requests,input_tokens,output_tokens FROM usage WHERE day=?', (day(),)).fetchone() or (0,0,0)
    with Session() as db:
        limit = settings(db).get('ai_daily_limit', 20)
    return dict(day=day(), requests=row[0], input_tokens=row[1], output_tokens=row[2], daily_limit=limit, max_input_characters=MAX_INPUT, max_output_tokens=MAX_OUTPUT)

@contextmanager
def reserve(job, facts):
    payload = json.dumps({'job':job,'facts':facts}, ensure_ascii=False)
    if len(payload) > MAX_INPUT:
        raise ValueError('AI input exceeds 40,000 characters; shorten the job or skills')
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    with Session() as db:
        limit = settings(db).get('ai_daily_limit',20)
    reserved_day = day()
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        active = conn.execute('SELECT expires,fingerprint FROM lease WHERE id=1').fetchone()
        if active and active[0] > time.time():
            raise ValueError('An AI request is active or was just sent; wait before retrying')
        conn.execute('INSERT OR IGNORE INTO usage(day,requests) VALUES (?,0)',(reserved_day,))
        if conn.execute('SELECT requests FROM usage WHERE day=?',(reserved_day,)).fetchone()[0] >= limit:
            from .security_events import record; record('AI_QUOTA_EXCEEDED')
            raise ValueError('Daily AI request limit reached; rules mode remains available')
        conn.execute('UPDATE usage SET requests=requests+1 WHERE day=?',(reserved_day,))
        conn.execute('INSERT OR REPLACE INTO lease VALUES (1,?,?)',(time.time()+300,fingerprint))
    try:
        yield reserved_day
    finally:
        # Brief cooldown suppresses duplicate clicks. Failures still consume a slot:
        # the provider may have processed a request even when its response was lost.
        with connect() as conn:
            conn.execute('UPDATE lease SET expires=? WHERE id=1',(time.time()+2,))

def record_tokens(reserved_day, usage):
    values = [usage.get(k,0) for k in ('prompt_tokens','completion_tokens')]
    if any(type(v) is not int or v < 0 for v in values):
        return
    with connect() as conn:
        conn.execute('UPDATE usage SET input_tokens=input_tokens+?,output_tokens=output_tokens+? WHERE day=?',(*values,reserved_day))

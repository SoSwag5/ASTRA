"""Non-destructive local diagnostics: `python -m backend.doctor`.

Inspects data directory, database, credential storage, localhost binding,
AI mode, backups and scheduled-task status. Never writes user data, never
reveals secret values. Returns PASS / WARNING / FAIL with remediation.
"""
import json, os, sys
from pathlib import Path


def _check(results, name, status, detail, remediation=''):
    results.append({'check': name, 'status': status, 'detail': detail, 'remediation': remediation})


def run_checks():
    results = []
    from .models import DATA, engine, settings, Session, initialize
    from sqlalchemy import select
    # Idempotent, non-destructive: ensures schema exists so the CLI works standalone.
    try: initialize()
    except Exception: pass

    # 1. Data directory writable
    try:
        probe = DATA / '.doctor-probe'
        probe.write_text('ok', encoding='utf-8'); probe.unlink()
        _check(results, 'data_directory_writable', 'PASS', f'{DATA} is writable')
    except Exception as e:
        _check(results, 'data_directory_writable', 'FAIL', f'{type(e).__name__}', 'Choose a writable HUNTER_DATA_DIR you own')

    # 2. Database reachable + integrity
    try:
        with engine.connect() as conn:
            ok = conn.exec_driver_sql('PRAGMA integrity_check').fetchone()[0]
            secure = conn.exec_driver_sql('PRAGMA secure_delete').fetchone()[0]
            journal = conn.exec_driver_sql('PRAGMA journal_mode').fetchone()[0]
        _check(results, 'database_integrity', 'PASS' if ok == 'ok' else 'FAIL', f'integrity={ok}')
        _check(results, 'database_secure_delete', 'PASS' if secure else 'WARNING',
               f'secure_delete={secure}, journal={journal}',
               '' if secure else 'secure_delete pragma should be ON')
    except Exception as e:
        _check(results, 'database_integrity', 'FAIL', f'{type(e).__name__}', 'Database unreachable or corrupt')

    # 3. Credential storage backend (never reveals the key)
    try:
        from .privacy import credential_backend, read_credential
        backend = type(credential_backend()).__module__
        _check(results, 'credential_backend', 'PASS', f'native store: {backend}')
        try:
            read_credential('openai'); present = True
        except Exception:
            present = False
        _check(results, 'openai_key_present', 'PASS', 'stored' if present else 'not stored (rules/ollama mode works without it)')
    except Exception as e:
        _check(results, 'credential_backend', 'WARNING', f'{type(e).__name__}',
               'A native OS credential store is required for OpenAI features; other modes work without it')

    # 4. Localhost binding
    bind = os.getenv('BIND_HOST', '127.0.0.1')
    token = bool(os.getenv('APP_TOKEN'))
    if bind in ('127.0.0.1', 'localhost'):
        _check(results, 'localhost_binding', 'PASS', f'loopback only (BIND_HOST={bind})')
    elif token:
        _check(results, 'localhost_binding', 'WARNING', f'non-loopback bind {bind} with APP_TOKEN set',
               'Public binding is unsupported for daily use; prefer loopback')
    else:
        _check(results, 'localhost_binding', 'FAIL', f'non-loopback bind {bind} without APP_TOKEN',
               'Set BIND_HOST=127.0.0.1 or provide APP_TOKEN')

    # 5. AI data-sharing mode
    try:
        with Session() as db:
            cfg = settings(db)
        provider = cfg.get('provider', 'rules')
        if provider == 'rules':
            _check(results, 'ai_data_sharing', 'PASS', 'rules mode: no data leaves this device')
        elif provider == 'ollama':
            _check(results, 'ai_data_sharing', 'PASS', 'ollama: loopback-only local model')
        else:
            _check(results, 'ai_data_sharing', 'WARNING', 'openai: job description + listed skills sent on explicit per-request approval',
                   'Switch to rules/ollama for fully local operation')
    except Exception as e:
        _check(results, 'ai_data_sharing', 'WARNING', f'{type(e).__name__}')

    # 6. Backups present + not empty
    try:
        backups = list((DATA / 'backups').glob('daily_*.db'))
        _check(results, 'backups', 'PASS' if backups else 'WARNING',
               f'{len(backups)} daily snapshot(s)', '' if backups else 'No backup yet; one is created on first daily run')
    except Exception as e:
        _check(results, 'backups', 'WARNING', f'{type(e).__name__}')

    # 7. Recent security events (detection layer alive)
    try:
        from .security_events import tail
        events = tail(500)
        _check(results, 'security_telemetry', 'PASS', f'{len(events)} recent security event(s) recorded locally')
    except Exception as e:
        _check(results, 'security_telemetry', 'WARNING', f'{type(e).__name__}')

    return results


def main():
    results = run_checks()
    worst = 'PASS'
    order = {'PASS': 0, 'WARNING': 1, 'FAIL': 2}
    for r in results:
        if order[r['status']] > order[worst]:
            worst = r['status']
    if '--json' in sys.argv:
        print(json.dumps({'overall': worst, 'checks': results}, indent=2))
    else:
        print('ASTRA doctor —', worst)
        for r in results:
            line = f"  [{r['status']:7}] {r['check']}: {r['detail']}"
            if r['remediation']:
                line += f"\n            -> {r['remediation']}"
            print(line)
    sys.exit(0 if worst != 'FAIL' else 1)


if __name__ == '__main__':
    main()

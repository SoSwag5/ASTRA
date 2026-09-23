"""#46.2-D offline harness: fictional postings through the local Ollama connector.

Separate from `scripts/shadow_role_eval.py` on purpose. That script needs the
#46.2-C private inputs -- posting evidence, development labels and the
employer-separated holdout. This one reads only the committed fictional fixture
`tests/fixtures/ollama_offline_cases_v1.json` and never opens any of those.

  --mode mocked  (default)  Every case goes through `ollama_connector.understand`
                            against an in-process fake Ollama (httpx
                            MockTransport) that replays the case's canned answer
                            or simulated fault. No model, no socket, and a fixed
                            memory reading, so it reproduces from the repository.
                            It tests ASTRA's code, never a model.

  --mode live               Each fictional posting once through an already-running
                            local Ollama, after a preflight that must pass in
                            full: numeric-loopback endpoint, every listener on
                            the port bound to loopback, cloud disabled in
                            server.json, the named tag installed with the
                            expected digest, and free memory above the local
                            floor. Never installs, pulls, updates, configures,
                            starts or stops anything.

A run cannot select or promote a model, claim a quality improvement, or compare
against the baseline engine: the postings are invented and #46.2 approved no
gate. The report states outcomes and counts only, and includes no posting or
answer text.

When run as a script it points HUNTER_DATA_DIR and DATABASE_URL at a fresh
scratch directory before importing anything from `backend`, and it asserts at
the end that `backend.models` was never imported.
"""
import argparse
import copy
import hashlib
import ipaddress
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if __name__ == '__main__':
    _SCRATCH = Path(tempfile.mkdtemp(prefix='astra-46-2-d-harness-'))
    os.environ['HUNTER_DATA_DIR'] = str(_SCRATCH / 'data')
    os.environ['DATABASE_URL'] = 'sqlite:///' + (_SCRATCH / 'harness.db').as_posix()
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from backend import ollama_connector as oc  # noqa: E402
from backend import role_understanding as ru  # noqa: E402

FIXTURE_PATH = ROOT / 'tests' / 'fixtures' / 'ollama_offline_cases_v1.json'
DEFAULT_ENDPOINT = 'http://127.0.0.1:11434'

# The in-process fake Ollama's single model. Fictional by construction.
MOCK_TAG = 'astra-fixture-assessor:mocked'
MOCK_DIGEST = '0' * 64
# Mocked runs use this reading instead of the machine's, so a result never
# depends on how busy the laptop is. Only the resource-refusal case lowers it.
MOCK_MEMORY = {'total_bytes': 16 * 2**30, 'available_bytes': 8 * 2**30, 'source': 'fixture'}
HANG_RELEASE_SECONDS = 5.0


def load_fixture(path=FIXTURE_PATH):
    # LF-normalised before hashing, so a Windows CRLF checkout and a Linux
    # checkout of the same commit report the same digest.
    raw = path.read_bytes().replace(b'\r\n', b'\n')
    fixture = json.loads(raw.decode('utf-8'))
    fixture['_sha256'] = hashlib.sha256(raw).hexdigest()
    return fixture


def posting_of(case, fixture):
    return fixture['postings'][case['posting']]


def cfg_of(fixture):
    return {'career_tracks': fixture['career_tracks']}


# --- The in-process fake Ollama ---------------------------------------------
def _streamed(body, status=200):
    """A streamed response, the shape a real server produces. The connector
    reads bodies with `iter_raw`, which refuses preloaded content."""
    payload = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
    return httpx.Response(status, content=iter([payload]), headers={'content-type': 'application/json'})


def envelope(content):
    """An Ollama `/api/chat` nonstreaming response carrying `content`."""
    return {'model': MOCK_TAG, 'message': {'role': 'assistant', 'content': content}, 'done': True,
            'total_duration': 0, 'eval_count': 0}


def mock_transport(case, cancel, release):
    """A MockTransport that plays one case: its canned answer or its fault."""
    scenario = case.get('scenario') or {}
    kind = scenario.get('kind')

    def handle(request):
        if kind == 'connect_refused':
            raise httpx.ConnectError('connection refused', request=request)
        path = request.url.path
        if path == '/api/tags':
            digest = 'e' * 64 if kind == 'digest_mismatch' else MOCK_DIGEST
            return _streamed({'models': [{'name': MOCK_TAG, 'digest': digest}]})
        if path != '/api/chat':
            return httpx.Response(404)
        if kind in ('hang', 'cancel_in_flight'):
            if kind == 'cancel_in_flight':
                # The Owner cancels while this request is in flight.
                threading.Timer(scenario['cancel_after_seconds'], cancel.set).start()
            release.wait(HANG_RELEASE_SECONDS)
            raise httpx.ReadTimeout('released by the harness', request=request)
        if kind == 'redirect':
            return httpx.Response(302, headers={'location': scenario['location']})
        if kind == 'status':
            return httpx.Response(scenario['status'], json={'error': 'fixture status'})
        if kind == 'raw_body':
            return _streamed(scenario['body'])
        if kind == 'raw_content':
            return _streamed(envelope(scenario['content']))
        return _streamed(envelope(json.dumps(case['answer'], ensure_ascii=False)))

    return httpx.MockTransport(handle)


def run_mocked(case, fixture):
    """One case through `understand` against the fake Ollama. Returns the Outcome."""
    scenario = case.get('scenario') or {}
    cancel, release = threading.Event(), threading.Event()
    snapshot = dict(MOCK_MEMORY)
    if scenario.get('kind') == 'low_memory':
        snapshot['available_bytes'] = scenario['available_bytes']
    kwargs = {}
    if 'budget_seconds' in scenario:
        kwargs['budget'] = scenario['budget_seconds']
    try:
        return oc.understand(posting_of(case, fixture), oc.resolve_endpoint(DEFAULT_ENDPOINT), MOCK_TAG,
                             MOCK_DIGEST, transport=mock_transport(case, cancel, release), cancel=cancel,
                             snapshot=snapshot, **kwargs)
    finally:
        release.set()


# --- Placement and expectations ---------------------------------------------
def placements(outcome, fixture):
    """(baseline, shadow) placements. Baseline is the unchanged #41 stub with no
    understanding; shadow uses the understanding only when it was accepted."""
    stub = fixture['fit_assessment_stub']
    before = copy.deepcopy(stub)
    baseline = ru.place(None, stub, cfg_of(fixture), fixture['owner_like_preferences'])
    shadow = ru.place(outcome.understanding if outcome.accepted else None, stub, cfg_of(fixture),
                      fixture['owner_like_preferences'])
    if stub != before:
        raise AssertionError('placement mutated the baseline assessment')
    return baseline, shadow


def expectation_mismatches(case, outcome, shadow):
    """What differs from the fixture's expectation for ASTRA's code. Empty when it matches."""
    expect, problems = case['expect'], []
    if outcome.reason != expect['reason']:
        problems.append(f"reason {outcome.reason} != {expect['reason']}")
    for key in ('attempts', 'model_calls'):
        if key in expect and getattr(outcome, key) != expect[key]:
            problems.append(f'{key} {getattr(outcome, key)} != {expect[key]}')
    if expect['reason'] != oc.ACCEPTED:
        if outcome.understanding is not None:
            problems.append('a failed outcome carried an understanding')
        return problems
    if outcome.understanding is None:
        return problems + ['accepted outcome has no understanding']
    u = outcome.understanding
    if u['primary_function'] != expect['primary_function']:
        problems.append(f"function {u['primary_function']} != {expect['primary_function']}")
    if u['required_years_min'] != expect['required_years_min']:
        problems.append(f"years {u['required_years_min']} != {expect['required_years_min']}")
    kinds = [w['kind'] for w in u['eligibility_wording']]
    if kinds != expect['eligibility_kinds']:
        problems.append(f"eligibility kinds {kinds} != {expect['eligibility_kinds']}")
    if shadow['tier'] != expect['tier']:
        problems.append(f"tier {shadow['tier']} != {expect['tier']}")
    if 'warnings' in expect and len(shadow['warnings']) != expect['warnings']:
        problems.append(f"warnings {len(shadow['warnings'])} != {expect['warnings']}")
    if 'notes_min' in expect and len(shadow['notes']) < expect['notes_min']:
        problems.append(f"notes {len(shadow['notes'])} < {expect['notes_min']}")
    return problems


def record(case_id, covers, outcome, baseline, shadow, limitation=False):
    """A text-free per-case record."""
    entry = {'id': case_id, 'covers': covers, **outcome.report(),
             'baseline_tier': baseline['tier'], 'shadow_tier': shadow['tier'],
             'shadow_warnings': len(shadow['warnings']), 'shadow_notes': len(shadow['notes'])}
    if limitation:
        entry['known_limitation'] = True
    if outcome.accepted:
        u = outcome.understanding
        entry['understanding'] = {'primary_function': u['primary_function'],
                                  'function_confidence': u['function_confidence'],
                                  'evidence_spans_kept': len(u['function_evidence']),
                                  'required_years_min': u['required_years_min'],
                                  'eligibility_kinds': [w['kind'] for w in u['eligibility_wording']]}
    else:
        # The property #46.2 requires of every failure: the baseline stands.
        entry['baseline_unchanged'] = shadow['tier'] == baseline['tier'] and not shadow['understanding_used']
    return entry


def summarize(records):
    """Counts only. Mocked records carry `dispatched_to_fake_ollama` instead of
    `model_calls`, because nothing they sent reached a model."""
    by_reason = {}
    for r in records:
        by_reason[r['reason']] = by_reason.get(r['reason'], 0) + 1
    failures = [r for r in records if not r['accepted']]
    elapsed = [r['elapsed_seconds'] for r in records]
    return {
        'cases': len(records),
        'accepted': len(records) - len(failures),
        'rejected_or_failed': len(failures),
        'by_reason': dict(sorted(by_reason.items())),
        'evidence_grounding_failures': by_reason.get(oc.EVIDENCE_REJECTED, 0),
        'grounding_discards_total': sum(r['grounding_discards'] for r in records),
        'accepted_known_limitations': sum(1 for r in records if r['accepted'] and r.get('known_limitation')),
        'baseline_unchanged_on_every_failure': all(r['baseline_unchanged'] for r in failures),
        'model_calls': sum(r.get('model_calls', 0) for r in records),
        'requests_dispatched_to_fake_ollama': sum(r.get('dispatched_to_fake_ollama', 0) for r in records),
        'latency_seconds': {'total': round(sum(elapsed), 3), 'max': round(max(elapsed, default=0.0), 3),
                            'mean': round(sum(elapsed) / max(len(elapsed), 1), 3)},
    }


# --- Provenance and preflight -----------------------------------------------
def git(*args):
    try:
        return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, timeout=30,
                              check=True).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return 'UNKNOWN'


def code_provenance():
    status = git('status', '--porcelain')
    return {'commit_sha': git('rev-parse', 'HEAD'), 'branch': git('rev-parse', '--abbrev-ref', 'HEAD'),
            'working_tree': 'clean' if status == '' else 'DIRTY: this report does not describe a committed tree',
            'uncommitted_paths': [line[3:] for line in status.splitlines()] if status else []}


def versions(fixture):
    system_prompt = oc.build_messages({'title': '', 'location': '', 'description': ''})[0][0]['content']
    return {'connector': oc.CONNECTOR_VERSION, 'prompt': oc.PROMPT_VERSION,
            'system_prompt_sha256': hashlib.sha256(system_prompt.encode('utf-8')).hexdigest(),
            'schema': oc.SCHEMA_VERSION,
            'response_schema_sha256': hashlib.sha256(
                json.dumps(ru.response_schema(), sort_keys=True).encode('utf-8')).hexdigest(),
            'placement_policy': ru.POLICY_VERSION,
            'fixture': FIXTURE_PATH.relative_to(ROOT).as_posix(), 'fixture_sha256': fixture['_sha256']}


def cloud_flag():
    """Ollama's documented cloud kill switch in ~/.ollama/server.json. Read-only."""
    path = Path.home() / '.ollama' / 'server.json'
    shown = '~/.ollama/server.json'
    if not path.exists():
        return {'file': shown, 'present': False, 'disable_ollama_cloud': None}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))   # tolerate a BOM written by PowerShell
    except (OSError, ValueError) as error:
        return {'file': shown, 'present': True, 'unreadable': type(error).__name__, 'disable_ollama_cloud': None}
    value = data.get('disable_ollama_cloud') if isinstance(data, dict) else None
    return {'file': shown, 'present': True, 'disable_ollama_cloud': value}


def _address_of(local):
    host = local.rsplit(':', 1)[0].strip('[]').split('%', 1)[0]
    return ipaddress.ip_address(host)


def parse_listeners(netstat_output, port):
    """Local addresses in LISTENING state on `port`, from Windows `netstat -ano` text."""
    found = []
    for line in netstat_output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].upper().startswith('TCP') and parts[3].upper() == 'LISTENING' \
                and parts[1].rsplit(':', 1)[-1] == str(port):
            found.append(parts[1])
    return found


def listeners(port):
    """Local addresses listening on `port`, from `netstat` (read-only), or None
    when they cannot be enumerated here. Fail-closed: None blocks a live run."""
    if platform.system() != 'Windows':
        return None
    found = []
    for family in ('TCP', 'TCPv6'):
        try:
            out = subprocess.run(['netstat', '-ano', '-p', family], capture_output=True, text=True,
                                 timeout=30, check=True).stdout
        except (subprocess.SubprocessError, OSError):
            return None
        found += parse_listeners(out, port)
    return found


def vram_observation():
    """GPU memory from nvidia-smi if present. An observation, not a gate."""
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=memory.total,memory.used,memory.free',
                              '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=30,
                             check=True).stdout.strip().splitlines()
        total, used, free = (int(v.strip()) for v in out[0].split(','))
        return {'total_mib': total, 'used_mib': used, 'free_mib': free}
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return {'unavailable': True}


def preflight(endpoint_url, tag, digest, embed_tag=None, embed_digest=None):
    """Every condition that must hold before one fictional token is sent."""
    checks, blockers = {}, []
    try:
        endpoint = oc.resolve_endpoint(endpoint_url)
        checks['endpoint'] = {'accepted': endpoint.base, 'rule': 'numeric loopback literal only'}
    except oc.EndpointRejected as error:
        return None, {'endpoint': {'rejected': str(error)}}, [f'endpoint rejected: {error}']
    if not digest or (embed_tag and not embed_digest):
        blockers.append('every model tag needs its expected digest; #46.2 selected no model')

    flag = cloud_flag()
    checks['cloud'] = flag
    if flag['disable_ollama_cloud'] is not True:
        blockers.append('Ollama cloud is not provably disabled in ~/.ollama/server.json; not changing it')

    bound = listeners(endpoint.port)
    if bound is None:
        checks['listeners'] = 'could not be enumerated'
        blockers.append('cannot prove the service listens only on loopback')
    else:
        remote = [a for a in bound if not _address_of(a).is_loopback]
        checks['listeners'] = {'port': endpoint.port, 'addresses': bound, 'non_loopback': remote}
        if not bound:
            blockers.append(f'nothing is listening on port {endpoint.port}: Ollama is not running, '
                            'and this harness does not start it')
        elif remote:
            blockers.append(f'Ollama also listens on non-loopback {remote}; not calling it')

    if bound:
        version = oc._request('GET', endpoint, '/api/version', None, time.monotonic() + oc.TAGS_BUDGET)
        checks['version'] = {'failed': version.reason} if isinstance(version, oc.Outcome) else version
        if isinstance(version, oc.Outcome):
            blockers.append(f'/api/version failed: {version.reason}')
        outcome, store = oc.installed_models(endpoint)
        if not outcome.accepted:
            checks['installed_models'] = {'failed': outcome.reason}
            blockers.append(f'could not list installed models: {outcome.reason}')
        else:
            checks['installed_models'] = store
            for name, expected in ((tag, digest), (embed_tag, embed_digest)):
                if name and name not in store:
                    blockers.append(f'model {name} is not installed; this harness never pulls one')
                elif name and expected and store[name] != expected:
                    blockers.append(f'model {name} digest {store[name]} != expected {expected}')

    reading = oc.memory_snapshot()
    checks['memory'] = reading or {'unavailable': True}
    checks['memory_floor_bytes'] = oc.MIN_FREE_RAM_BYTES
    refusal = oc.check_resources(snapshot=reading or {})
    if refusal is not None:
        blockers.append(f'resource refusal: {refusal.detail}')
    checks['vram'] = vram_observation()
    return endpoint, checks, blockers


# --- Runs -------------------------------------------------------------------
def mocked_run(fixture):
    records, mismatches = [], {}
    for case in fixture['cases']:
        outcome = run_mocked(case, fixture)
        baseline, shadow = placements(outcome, fixture)
        entry = record(case['id'], case['covers'], outcome, baseline, shadow, case.get('limitation', False))
        entry['dispatched_to_fake_ollama'] = entry.pop('model_calls')
        problems = expectation_mismatches(case, outcome, shadow)
        entry['matches_fixture_expectation'] = not problems
        if problems:
            mismatches[case['id']] = problems
        records.append(entry)
    return records, mismatches


def mocked_embedding(fixture):
    """One embedding call against the fake Ollama, to exercise that path."""
    texts = [p['description'] for p in list(fixture['postings'].values())[:4]]

    def handle(request):
        if request.url.path == '/api/tags':
            return _streamed({'models': [{'name': MOCK_TAG, 'digest': MOCK_DIGEST}]})
        sent = json.loads(request.content)
        if sent.get('truncate') is not False:
            return httpx.Response(400, json={'error': 'truncate must be false'})
        return _streamed({'model': MOCK_TAG,
                          'embeddings': [[0.1 * (i + 1), 0.2, 0.3] for i in range(len(sent['input']))]})

    outcome = oc.embed(oc.resolve_endpoint(DEFAULT_ENDPOINT), MOCK_TAG, texts, MOCK_DIGEST,
                       transport=httpx.MockTransport(handle), snapshot=MOCK_MEMORY)
    report = {**outcome.report(), 'texts': len(texts)}
    report['dispatched_to_fake_ollama'] = report.pop('model_calls')
    return report


def live_run(fixture, endpoint, tag, digest):
    """Each posting that has a canned-answer case, once, through the real model.
    Scenario cases simulate faults and are not sent. Nothing is scored against
    the fixture's expectations: those describe canned answers, not labels."""
    used = []
    for case in fixture['cases']:
        if 'answer' in case and case['posting'] not in used:
            used.append(case['posting'])
    records = []
    for name in used:
        posting = fixture['postings'][name]
        outcome = oc.understand(posting, endpoint, tag, digest)
        baseline, shadow = placements(outcome, fixture)
        records.append(record(f'posting:{name}', 'live reading of a fictional posting', outcome, baseline, shadow))
    return records


def live_embedding(fixture, endpoint, tag, digest):
    texts = [p['description'] for p in list(fixture['postings'].values())[:4]]
    outcome = oc.embed(endpoint, tag, texts, digest)
    return {**outcome.report(), 'texts': len(texts)}


CLAIMS_NOT_MADE = [
    'No model is selected, promoted or recommended by this run.',
    'No quality improvement is claimed: the postings are invented, and mocked answers are canned.',
    'No baseline comparison exists; the deterministic engine was not run on real postings here.',
    'No #46.2 gate passed. Both benchmark evaluator variants failed the proposed quality gates, '
    'and those gates remain unapproved.',
    'Nothing here is evidence about real postings, real employers or the #46.2-C holdout, which was not opened.',
]


def finalize_live_report(report):
    """Classify a live run from dispatched requests and accepted results."""
    calls = report['summary']['model_calls']
    report['model']['request_dispatched'] = calls > 0
    if calls == 0:
        report['real_model_smoke_test'] = 'COULD NOT RUN: no model call was dispatched'
        report['outcome'] = 'BLOCKED: no model call was attempted'
        return 2
    report['real_model_smoke_test'] = f'DISPATCHED: {calls} request(s) to local model endpoints'
    rejected = report['summary']['rejected_or_failed']
    if report.get('embedding') and not report['embedding']['accepted']:
        rejected += 1
    report['outcome'] = 'COMPLETED' if rejected == 0 else 'COMPLETED WITH REJECTIONS OR FAILURES'
    return 0 if rejected == 0 else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mode', choices=('mocked', 'live'), default='mocked')
    parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT, help='a numeric loopback origin; names are refused')
    parser.add_argument('--tag', help='installed evaluator tag (live). #46.2 selected no model, so name one')
    parser.add_argument('--digest', help='expected manifest digest of --tag (live, required)')
    parser.add_argument('--embed-tag')
    parser.add_argument('--embed-digest')
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--out', help='where to write the JSON report')
    args = parser.parse_args(argv)

    fixture = load_fixture()
    report = {
        'harness': 'offline_ollama_harness', 'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'mode': args.mode, 'code': code_provenance(), 'versions': versions(fixture),
        'request_bounds': {'num_ctx': oc.NUM_CTX, 'temperature': 0, 'stream': False,
                           'num_predict': oc.MAX_OUTPUT_TOKENS, 'keep_alive': oc.KEEP_ALIVE,
                           'embed_truncate': False, 'max_embed_batch': oc.MAX_EMBED_BATCH,
                           'max_embed_chars': oc.MAX_EMBED_CHARS, 'chat_budget_seconds': oc.CHAT_BUDGET,
                           'read_timeout_seconds': oc.READ_TIMEOUT, 'max_attempts': oc.MAX_ATTEMPTS,
                           'max_response_bytes': oc.MAX_RESPONSE_BYTES,
                           'free_ram_floor_bytes': oc.MIN_FREE_RAM_BYTES},
        'platform': {'python': platform.python_version(), 'httpx': httpx.__version__, 'system': platform.system(),
                     'release': platform.release()},
        'data_statement': fixture['note'],
        'model': {'request_dispatched': False, 'tag': None, 'digest': None},
    }
    status = 0
    if args.mode == 'mocked':
        report['preflight'] = 'skipped: mocked mode dials no socket'
        report['real_model_smoke_test'] = 'NOT RUN in this report: mocked mode'
        records, mismatches = mocked_run(fixture)
        report['cases'], report['summary'] = records, summarize(records)
        report['embedding'] = mocked_embedding(fixture)
        report['fixture_expectation_mismatches'] = mismatches
        report['outcome'] = 'COMPLETED' if not mismatches else 'COMPLETED WITH MISMATCHES'
        status = 0 if not mismatches else 1
    else:
        if not args.tag:
            parser.error('--mode live requires --tag and --digest: #46.2 selected no model')
        endpoint, checks, blockers = preflight(args.endpoint, args.tag, args.digest, args.embed_tag, args.embed_digest)
        report['preflight'], report['preflight_blockers'] = checks, blockers
        if blockers:
            report['outcome'] = 'BLOCKED: no model call was attempted'
            report['real_model_smoke_test'] = 'COULD NOT RUN: ' + '; '.join(blockers)
            report['summary'] = {'model_calls': 0}
            status = 2
        elif args.preflight_only:
            report['outcome'] = 'PREFLIGHT PASSED: no model call attempted (--preflight-only)'
            report['summary'] = {'model_calls': 0}
        else:
            report['model'] = {'request_dispatched': False, 'tag': args.tag, 'digest': args.digest,
                               'embed_tag': args.embed_tag, 'embed_digest': args.embed_digest}
            records = live_run(fixture, endpoint, args.tag, args.digest)
            report['cases'], report['summary'] = records, summarize(records)
            if args.embed_tag:
                report['embedding'] = live_embedding(fixture, endpoint, args.embed_tag, args.embed_digest)
                report['summary']['model_calls'] += report['embedding']['model_calls']
            report['memory_after'] = oc.memory_snapshot() or {'unavailable': True}
            report['vram_after'] = vram_observation()
            status = finalize_live_report(report)
    report['claims_not_made'] = CLAIMS_NOT_MADE
    if 'backend.models' in sys.modules:
        raise AssertionError('the harness must not import storage')
    write(report, args.out)
    return status


def write(report, out):
    body = json.dumps(report, indent=2, ensure_ascii=False)
    if out:
        Path(out).write_text(body + '\n', encoding='utf-8')
        print(f'report written to {out}')
    print(f"mode={report['mode']} outcome={report['outcome']}")
    if report.get('summary'):
        print(json.dumps(report['summary'], indent=2))
    for blocker in report.get('preflight_blockers') or ():
        print(f'BLOCKER: {blocker}')


if __name__ == '__main__':
    raise SystemExit(main())

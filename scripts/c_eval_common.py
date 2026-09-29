"""Shared offline helpers for the #46.2-C evaluations (development and blind).

Nothing in ``backend`` imports this module. It reads private inputs (frozen
items, posting snapshots, role readings, labels) from paths given on the
command line; none of them is in the repository.

Fail-closed rules:
- The items file is parsed whole, because it holds every split. Each row is
  checked for a well-formed unique id and a known split. Rows of the other
  split keep only their id once ``load_items`` returns; the parsed file is
  dropped. The process has still loaded their other fields, so nothing here
  can show that no person has read them.
- A snapshot is read only for a row of the selected split, from a file named
  by its validated id, and must match the frozen SHA-256 and character count.
- Readings and labels may name only ids of the selected split.

Importing this module changes nothing global. Scripts call
``disable_network()`` first.
"""
import hashlib
import json
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import recall, role_understanding as ru  # noqa: E402

ITEM_ID = re.compile(r'[A-Z][0-9]{2,3}')
SPLITS = ('development', 'holdout')
SHA256_HEX = re.compile(r'[0-9a-f]{64}')
MIN_READABLE_CHARS = 200
LABEL_TIER = {'show_prominently': ru.PROMINENT, 'show_lower': ru.LOWER, 'hide': ru.SUGGESTED_HIDDEN}
LABEL_CHOICES = set(LABEL_TIER) | {'unsure'}
ROW_FIELDS = ('item_id', 'split', 'title', 'employer', 'official_url', 'platform', 'reference', 'posted',
              'location_stated', 'engine_input_location', 'desc_sha256', 'desc_chars')
ASSERTS_ELIGIBILITY = re.compile(
    r"\byou (?:are|may be|might be|would be|seem to be|appear to be)\s+(?:not\s+)?(?:eligible|ineligible)\b"
    r"|\byou (?:do not |don't |)qualify\b|\b(?:eligible|ineligible) to apply\b", re.I)

NETWORK_ATTEMPTS = []


def refuse(message):
    raise SystemExit('refusing to run: ' + message)


def disable_network():
    """Block DNS and outbound connections for this process (IP literals too)."""
    def blocked(*args, **kwargs):
        NETWORK_ATTEMPTS.append(repr(args[-1] if args else None)[:120])
        raise OSError('offline evaluation: network disabled')
    socket.getaddrinfo = blocked
    socket.create_connection = blocked
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_sha256_lf(path):
    """SHA-256 of a text file with CRLF canonicalised to LF (as the #42 manifest)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def read_json(path, name):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        refuse(f'{name} file unreadable ({type(error).__name__})')


def _check_row(row):
    item_id = row['item_id']
    if not isinstance(row.get('desc_sha256'), str) or not SHA256_HEX.fullmatch(row['desc_sha256']):
        refuse(f'{item_id} has no frozen description sha256')
    if not isinstance(row.get('desc_chars'), int) or isinstance(row['desc_chars'], bool) or row['desc_chars'] < 0:
        refuse(f'{item_id} has no frozen description length')
    for field in ('title', 'employer', 'official_url', 'platform', 'reference', 'posted', 'location_stated',
                  'engine_input_location'):
        if row.get(field) is not None and not isinstance(row[field], str):
            refuse(f'{item_id} field {field} is not text')
    return {field: row[field] for field in ROW_FIELDS if field in row}


def load_items(path, split):
    """(rows of `split`, ids of every other row). Refuses on any malformed row,
    unknown split or duplicate id. A refusal names at most an id, never a
    field value."""
    if split not in SPLITS:
        refuse(f'unknown split {split!r}')
    data = read_json(path, 'items')
    rows = data.get('items') if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        refuse('items file has no item list')
    selected, others, seen = [], set(), set()
    for row in rows:
        if not isinstance(row, dict):
            refuse('an item row is not an object')
        item_id, row_split = row.get('item_id'), row.get('split')
        if not isinstance(item_id, str) or not ITEM_ID.fullmatch(item_id):
            refuse('an item id is malformed')
        if item_id in seen:
            refuse(f'duplicate item id {item_id}')
        seen.add(item_id)
        if row_split not in SPLITS:
            refuse(f'{item_id} has an unknown split')
        if row_split == split:
            selected.append(_check_row(row))
        else:
            others.add(item_id)
    del rows, data
    if not selected:
        refuse(f'no {split} items')
    return selected, others


def readable(row):
    return row['desc_chars'] >= MIN_READABLE_CHARS


class Snapshots:
    """Reads posting snapshots of the selected rows only, verifying each."""

    def __init__(self, directory, rows):
        self.directory, self.rows, self.opened = Path(directory), {r['item_id']: r for r in rows}, []

    def read(self, item_id):
        row = self.rows.get(item_id)
        if row is None:
            raise PermissionError('snapshot outside the selected split')
        path = self.directory / f'{item_id}.txt'
        try:
            text = path.read_text(encoding='utf-8')   # universal newlines: frozen hashes are over LF text
        except (OSError, UnicodeDecodeError) as error:
            refuse(f'{item_id} snapshot unreadable ({type(error).__name__})')
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != row['desc_sha256'] or len(text) != row['desc_chars']:
            refuse(f'{item_id} snapshot does not match its frozen sha256 and length')
        self.opened.append(item_id)
        return text


def load_keyed(path, key, allowed_ids, name):
    """A {item_id: object} mapping that may name only `allowed_ids`."""
    data = read_json(path, name)
    mapping = data.get(key) if isinstance(data, dict) else None
    if not isinstance(mapping, dict):
        refuse(f'{name} file has no {key!r} mapping')
    outside = [k for k in mapping if k not in allowed_ids]
    if outside:
        refuse(f'{name} name {len(outside)} item(s) outside the selected split (holdout or unknown); '
               f'the other split must stay untouched')
    return data, mapping


def build_job(row, text):
    """The engine input, built exactly as in the development evaluation."""
    location = row['engine_input_location'] if 'engine_input_location' in row else (row.get('location_stated') or '')
    return {'title': row.get('title') or '', 'company': row.get('employer') or '', 'location': location,
            'description': text, 'job_url': row.get('official_url') or '', 'source': row.get('platform') or '',
            'source_job_id': str(row.get('reference') or row['item_id']), 'date_posted': (row.get('posted') or '')[:10],
            'closing_date': '', 'remote_status': ''}


def current_tier(fa):
    if fa['hard_reject']:
        return ru.SUGGESTED_HIDDEN
    return ru.PROMINENT if fa['bucket'] in ('STRONG', 'GOOD') else ru.LOWER


def assess(row, text, reading, cfg, profile, preferences, clock):
    """Current path, legacy shadow and candidate for one posting."""
    job = build_job(row, text)
    decision = recall.evaluate(job, cfg, profile, clock)
    fa, legacy = decision['fit_assessment'], decision['legacy_shadow']
    understanding = ru.verify(reading, job)
    placed = ru.place(understanding, fa, cfg, preferences)
    return {
        'current': {'bucket': fa['bucket'], 'score': fa['score'], 'tier': current_tier(fa),
                    'hard_reject': (fa['hard_reject'] or {}).get('code'), 'match_type': fa['match_type'],
                    'role_family': fa['role_family'],
                    'required_years_parsed': fa['experience'].get('effective_required_minimum'),
                    'geography': fa['geography']['compatibility'], 'eligibility_state': fa['eligibility']['state']},
        'legacy': {'excluded': legacy['excluded'], 'priority': legacy['priority']},
        'understanding': {k: understanding[k] for k in ('primary_function', 'function_confidence',
                                                        'required_years_min', 'discarded')}
                         | {'eligibility_kinds': [w['kind'] for w in understanding['eligibility_wording']]},
        'candidate': {'tier': placed['tier'], 'reasons': placed['reasons'], 'warnings': placed['warnings'],
                      'notes': placed['notes'], 'understanding_used': placed['understanding_used']},
    }


def candidate_key(row):
    return ru.TIER_RANK[row['candidate']['tier']], -(row['current']['score'] or 0)


def current_key(row):
    return (1, 0) if row['current']['score'] is None else (0, -row['current']['score'])


def pairwise(first, second, key):
    """(a, b) pairs, a from `first` and b from `second`, ordered a above b."""
    pairs = [(a, b) for a in first for b in second]
    return {'correct': sum(key(a) < key(b) for a, b in pairs), 'ties': sum(key(a) == key(b) for a, b in pairs),
            'pairs': len(pairs)}


def fit_metrics(rows, system):
    """M1-M5 and M7 (plan v3 section 7) for 'candidate' or 'current'."""
    key = candidate_key if system == 'candidate' else current_key
    tier = lambda r: r[system]['tier']  # noqa: E731
    shown = [r for r in rows if r['owner_tier'] != ru.SUGGESTED_HIDDEN]
    hidden = [r for r in rows if r['owner_tier'] == ru.SUGGESTED_HIDDEN]
    return {
        'M1_tier_agreement': {'agree': sum(tier(r) == r['owner_tier'] for r in rows), 'of': len(rows)},
        'M2_relevant_hidden': {'count': sum(tier(r) == ru.SUGGESTED_HIDDEN for r in shown), 'of': len(shown)},
        'M3_irrelevant_promoted': {'count': sum(tier(r) == ru.PROMINENT for r in hidden), 'of': len(hidden)},
        'M4_irrelevant_visible': {'count': sum(tier(r) != ru.SUGGESTED_HIDDEN for r in hidden), 'of': len(hidden)},
        'M5_shown_above_hidden': pairwise(shown, hidden, key),
        'M7_prominent_above_lower': pairwise([r for r in rows if r['owner_tier'] == ru.PROMINENT],
                                             [r for r in rows if r['owner_tier'] == ru.LOWER], key),
    }


def asserts_eligibility(texts):
    return any(ASSERTS_ELIGIBILITY.search(t or '') for t in texts)


def code_identity(paths):
    """Git HEAD, whether any listed path differs from it, and LF hashes."""
    def git(*args):
        try:
            done = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, timeout=30)
            return done.stdout.strip() if done.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    return {'git_head': git('rev-parse', 'HEAD'),
            'paths_differing_from_head': (git('status', '--porcelain', '--', *paths) or '').splitlines(),
            'sha256_lf': {p: text_sha256_lf(ROOT / p) for p in paths}}


def write_new(path, obj):
    """Write JSON to a path that must not exist yet."""
    path = Path(path)
    if path.exists():
        refuse(f'{path.name} already exists; this step writes a new file only')
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    return file_sha256(path)

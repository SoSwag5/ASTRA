"""Offline before/after evaluation of the #46.2 shadow placement (development split only).

No network, no database writes that matter (set HUNTER_DATA_DIR to a scratch
directory), no live scan. Reads local posting snapshots that are NOT in the
repository, recorded role understandings, and imported Owner labels. Holdout
items are skipped before any file of theirs is opened.

Usage:
  python scripts/shadow_role_eval.py --items FROZEN.json --snapshots DIR \
      --understandings UNDERSTANDINGS.json --labels LABELS.json \
      --profile PROFILE_FIXTURE.json --preferences PREFS.json --out OUT.json
"""
import argparse
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_lookups = []


def _no_network(*args, **kwargs):
    _lookups.append(args[0] if args else None)
    raise OSError('offline evaluation: network disabled')


socket.getaddrinfo = _no_network

from backend import recall, role_understanding as ru  # noqa: E402
from backend.models import DEFAULTS  # noqa: E402

CLOCK = datetime(2026, 9, 22, tzinfo=timezone.utc)
LABEL_TIER = {'show_prominently': ru.PROMINENT, 'show_lower': ru.LOWER, 'hide': ru.SUGGESTED_HIDDEN}


def current_tier(fa):
    if fa['hard_reject']:
        return ru.SUGGESTED_HIDDEN
    return ru.PROMINENT if fa['bucket'] in ('STRONG', 'GOOD') else ru.LOWER


def pairwise(rows, key):
    """Share of (Owner-shown, Owner-hidden) pairs the system orders correctly."""
    shown = [r for r in rows if r['owner_tier'] != ru.SUGGESTED_HIDDEN]
    hidden = [r for r in rows if r['owner_tier'] == ru.SUGGESTED_HIDDEN]
    pairs = [(a, b) for a in shown for b in hidden]
    right = sum(1 for a, b in pairs if key(a) < key(b))
    ties = sum(1 for a, b in pairs if key(a) == key(b))
    return {'correct': right, 'ties': ties, 'pairs': len(pairs)}


def main():
    ap = argparse.ArgumentParser()
    for name in ('items', 'snapshots', 'understandings', 'labels', 'profile', 'preferences', 'out'):
        ap.add_argument('--' + name, required=True)
    a = ap.parse_args()
    items = json.loads(Path(a.items).read_text(encoding='utf-8'))['items']
    understandings = json.loads(Path(a.understandings).read_text(encoding='utf-8'))['items']
    labels = json.loads(Path(a.labels).read_text(encoding='utf-8'))['labels']
    fixture = json.loads(Path(a.profile).read_text(encoding='utf-8'))
    prefs = json.loads(Path(a.preferences).read_text(encoding='utf-8'))
    cfg = {**DEFAULTS, **fixture['career_config']}

    rows, excluded = [], []
    for it in items:
        if it['split'] != 'development':
            continue  # holdout: never opened
        k = it['item_id']
        label = labels.get(k)
        if label is None or not label.get('use_for_fit_scoring', True):
            excluded.append({'item_id': k, 'reason': (label or {}).get('exclusion_reason', 'no Owner label')})
            continue
        text = (Path(a.snapshots) / f'{k}.txt').read_text(encoding='utf-8')
        location = it['engine_input_location'] if 'engine_input_location' in it else (it.get('location_stated') or '')
        job = {'title': it['title'] or '', 'company': it['employer'], 'location': location, 'description': text,
               'job_url': it['official_url'], 'source': it['platform'],
               'source_job_id': str(it.get('reference') or k), 'date_posted': (it.get('posted') or '')[:10],
               'closing_date': '', 'remote_status': ''}
        decision = recall.evaluate(job, cfg, fixture['profile'], CLOCK)
        fa, legacy = decision['fit_assessment'], decision['legacy_shadow']
        understanding = ru.verify(understandings.get(k), job)
        placed = ru.place(understanding, fa, cfg, prefs)
        rows.append({
            'item_id': k, 'title': it['title'], 'owner_choice': label['first_saved_choice'],
            'owner_tier': LABEL_TIER[label['first_saved_choice']],
            'current': {'bucket': fa['bucket'], 'score': fa['score'], 'tier': current_tier(fa),
                        'match_type': fa['match_type'], 'role_family': fa['role_family'],
                        'required_years_parsed': fa['experience'].get('effective_required_minimum'),
                        'experience_points': fa['components']['experience'],
                        'geography': fa['geography']['compatibility'], 'eligibility_state': fa['eligibility']['state']},
            'legacy': {'excluded': legacy['excluded'], 'priority': legacy['priority']},
            'understanding': {k2: understanding[k2] for k2 in ('primary_function', 'function_confidence',
                                                               'required_years_min', 'discarded')}
                             | {'eligibility_kinds': [w['kind'] for w in understanding['eligibility_wording']]},
            'candidate': {'tier': placed['tier'], 'reasons': placed['reasons'], 'warnings': bool(placed['warnings']),
                          'notes': placed['notes']},
        })

    n = len(rows)
    owner_hidden = [r for r in rows if r['owner_tier'] == ru.SUGGESTED_HIDDEN]
    owner_shown = [r for r in rows if r['owner_tier'] != ru.SUGGESTED_HIDDEN]
    top = {ru.PROMINENT}

    def summary(tier_of):
        return {
            'exact_tier_agreement': {'agree': sum(tier_of(r) == r['owner_tier'] for r in rows), 'of': n},
            'owner_hidden_placed_hidden': {'count': sum(tier_of(r) == ru.SUGGESTED_HIDDEN for r in owner_hidden), 'of': len(owner_hidden)},
            'owner_hidden_placed_top': {'count': sum(tier_of(r) in top for r in owner_hidden), 'of': len(owner_hidden)},
            'owner_shown_placed_hidden': {'count': sum(tier_of(r) == ru.SUGGESTED_HIDDEN for r in owner_shown), 'of': len(owner_shown)},
        }

    metrics = {
        'current_engine': summary(lambda r: r['current']['tier']),
        'candidate': summary(lambda r: r['candidate']['tier']),
        'legacy_engine_shown_vs_hidden': {
            'owner_hidden_excluded': {'count': sum(r['legacy']['excluded'] for r in owner_hidden), 'of': len(owner_hidden)},
            'owner_shown_excluded': {'count': sum(r['legacy']['excluded'] for r in owner_shown), 'of': len(owner_shown)},
        },
        'pairwise_shown_above_hidden': {
            'current_engine_score': pairwise(rows, lambda r: (1, 0) if r['current']['score'] is None else (0, -r['current']['score'])),
            'legacy_engine': pairwise(rows, lambda r: (int(r['legacy']['excluded']), -(r['legacy']['priority'] or 0))),
            'candidate': pairwise(rows, lambda r: (ru.TIER_RANK[r['candidate']['tier']], -(r['current']['score'] or 0))),
        },
    }
    out = {'artifact': 'discovery_46_2c_shadow_eval', 'policy_version': ru.POLICY_VERSION,
           'schema_version': ru.SCHEMA_VERSION, 'clock': CLOCK.isoformat(), 'preferences': prefs,
           'profile_fixture': fixture.get('source'), 'items_scored': n, 'excluded': excluded,
           'network_lookups_attempted': _lookups, 'metrics': metrics, 'rows': rows}
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(metrics, indent=1))


if __name__ == '__main__':
    main()

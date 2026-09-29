"""Offline before/after evaluation of the #46.2 shadow placement (development split only).

No network (DNS and outbound connections are blocked for the process), no live
scan, no database of record (set HUNTER_DATA_DIR to a scratch directory). Reads
local posting snapshots that are NOT in the repository, recorded role readings
and imported Owner labels. Development results are in-sample diagnostics, not
blind accuracy.

Holdout boundary, precisely (see scripts/c_eval_common.py):
- The items file is parsed whole because it holds every split. Every row must
  have a well-formed unique id and a known split, or the run refuses. Holdout
  rows keep only their id after parsing; no other holdout field is used,
  printed or written. The process has nevertheless loaded them.
- The run refuses if the labels or the readings name any non-development item.
- Snapshots are opened only for development rows, from files named by
  validated ids, and must match the frozen SHA-256 and length.
- The output lists the snapshots THIS process opened. It cannot show what any
  person or other process read.

Exclusions: a description under 200 characters (SOURCE_UNREADABLE), a label
marked not for fit scoring, an 'unsure' label, or no label. First-saved labels
are scored; later label changes are listed separately. The report carries item
ids, tiers and reasons -- no posting titles, quoted employer wording or label
free text. Input hashes are LF-canonical for repository files and exact bytes
for private files.

Usage:
  python scripts/shadow_role_eval.py --items FROZEN.json --snapshots DIR \
      --understandings UNDERSTANDINGS.json --labels LABELS.json \
      --profile PROFILE_FIXTURE.json --preferences PREFS.json --out OUT.json
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import c_eval_common as common  # noqa: E402
from backend import role_understanding as ru  # noqa: E402
from backend.models import DEFAULTS  # noqa: E402

CLOCK = datetime(2026, 9, 22, tzinfo=timezone.utc)
CODE_PATHS = ['backend/role_understanding.py', 'scripts/c_eval_common.py', 'scripts/shadow_role_eval.py']
QUOTE = re.compile(r'“[^”]*”')   # employer wording quoted from a posting stays out of the report
STATUS = ('IN-SAMPLE DIAGNOSTIC on development labels the Owner saved after seeing Codex suggestions; the role '
          'readings were written after those labels were read. Not blind accuracy and not proof of improvement.')


def main(argv=None):
    common.disable_network()
    ap = argparse.ArgumentParser()
    for name in ('items', 'snapshots', 'understandings', 'labels', 'profile', 'preferences', 'out'):
        ap.add_argument('--' + name, required=True)
    a = ap.parse_args(argv)
    rows, other_ids = common.load_items(a.items, 'development')
    dev_ids = {r['item_id'] for r in rows}
    _, understandings = common.load_keyed(a.understandings, 'items', dev_ids, 'understandings')
    _, labels = common.load_keyed(a.labels, 'labels', dev_ids, 'labels')
    for k, label in labels.items():
        if not isinstance(label, dict) or label.get('first_saved_choice') not in common.LABEL_CHOICES:
            common.refuse(f'label {k} has no valid first_saved_choice')
    snapshots = common.Snapshots(a.snapshots, rows)
    fixture = common.read_json(a.profile, 'profile')
    prefs = common.read_json(a.preferences, 'preferences')
    if isinstance(prefs, dict) and isinstance(prefs.get('preferences'), dict):
        prefs = prefs['preferences']   # a versioned preferences file
    cfg = {**DEFAULTS, **fixture['career_config']}

    scored, excluded = [], []
    for row in rows:
        k = row['item_id']
        label = labels.get(k)
        reasons = []
        if not common.readable(row):
            reasons.append(f'SOURCE_UNREADABLE: description has {row["desc_chars"]} characters '
                           f'(< {common.MIN_READABLE_CHARS})')
        if label is None:
            reasons.append('no Owner label')
        else:
            if label.get('use_for_fit_scoring', True) is False:
                reasons.append('Owner label marked not for fit scoring')   # its private free text is not copied
            if label['first_saved_choice'] == 'unsure':
                reasons.append('Owner chose unsure')
        if reasons:
            excluded.append({'item_id': k, 'reasons': reasons})
            continue
        result = common.assess(row, snapshots.read(k), understandings.get(k), cfg, fixture['profile'], prefs, CLOCK)
        result['candidate']['warnings'] = bool(result['candidate']['warnings'])
        result['candidate']['notes'] = [QUOTE.sub('“[employer wording]”', n) for n in result['candidate']['notes']]
        scored.append({'item_id': k, 'owner_choice': label['first_saved_choice'],
                       'owner_tier': common.LABEL_TIER[label['first_saved_choice']], **result})

    later_changes = [{'item_id': k, 'first_saved_choice': v['first_saved_choice'], 'current_choice': v.get('current_choice')}
                     for k, v in sorted(labels.items())
                     if v.get('current_choice') not in (None, v['first_saved_choice'])]
    metrics = {'current_engine': common.fit_metrics(scored, 'current'),
               'candidate': common.fit_metrics(scored, 'candidate'),
               'legacy_engine_shown_vs_hidden': {
                   'owner_hidden_excluded': {'count': sum(r['legacy']['excluded'] for r in scored
                                                          if r['owner_tier'] == ru.SUGGESTED_HIDDEN),
                                             'of': sum(r['owner_tier'] == ru.SUGGESTED_HIDDEN for r in scored)},
                   'owner_shown_excluded': {'count': sum(r['legacy']['excluded'] for r in scored
                                                         if r['owner_tier'] != ru.SUGGESTED_HIDDEN),
                                            'of': sum(r['owner_tier'] != ru.SUGGESTED_HIDDEN for r in scored)}}}
    out = {'artifact': 'discovery_46_2c_shadow_eval', 'split': 'development', 'status': STATUS,
           'policy_version': ru.POLICY_VERSION,
           'schema_version': ru.SCHEMA_VERSION, 'clock': CLOCK.isoformat(), 'preferences': prefs,
           'profile_fixture': fixture.get('source'), 'items_scored': len(scored), 'excluded': excluded,
           'label_basis': 'first_saved_choice', 'later_label_changes': later_changes,
           'network_attempts': list(common.NETWORK_ATTEMPTS),
           'boundary': {'other_split_rows_parsed': len(other_ids),
                        'other_split_fields_retained': 'item_id only, after validation',
                        'snapshots_opened_by_this_process': sorted(snapshots.opened),
                        'other_split_snapshots_opened_by_this_process': len(set(snapshots.opened) & other_ids),
                        'scope': 'what this process did; it cannot show what any person or other process read'},
           'inputs_sha256': {name: common.record_sha256(getattr(a, name))
                             for name in ('items', 'understandings', 'labels', 'profile', 'preferences')},
           'code': common.code_identity(CODE_PATHS),
           'metrics': metrics, 'rows': scored}
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(metrics, indent=1))


if __name__ == '__main__':
    main()

"""Discovery v2 query planner (issue #37): user intent -> bounded search plan.

Deterministic and rule-based only. Does not rank, filter eligibility, or
retrieve postings -- those are later Discovery v2 stages. Expansion is
limited to an explicit, curated role-relation table; an unmatched title
returns only its normalized form, never a fuzzy or invented relation.
"""
import re

VERSION = 'query-planner-1'
MAX_EXPANSIONS = 10

_JUNIOR_WORDS = sorted(['entry level', 'entry-level', 'junior', 'graduate'], key=len, reverse=True)
_SENIOR_WORDS = sorted(['senior', 'principal', 'director', 'architect', 'manager', 'lead', 'head'], key=len, reverse=True)
_TIER_RE = re.compile(r'(?<!\w)(?:level|tier)\s*-?\s*(1|2|3|i{1,3})(?!\w)', re.I)
_ROMAN = {'i': 1, 'ii': 2, 'iii': 3}

_LOCATIONS = sorted(['United Arab Emirates', 'Abu Dhabi', 'Ras Al Khaimah', 'Umm Al Quwain',
                     'Dubai', 'Sharjah', 'Ajman', 'Fujairah', 'Al Ain', 'UAE'], key=len, reverse=True)

_ROLE_RELATIONS = [
    {'id': 'soc_analyst', 'aliases': ['soc analyst'], 'canonical': 'SOC Analyst',
     'synonyms': ['Security Operations Analyst'], 'broader': ['Cybersecurity Analyst']},
    {'id': 'cybersecurity_analyst',
     'aliases': ['cybersecurity analyst', 'cyber security analyst', 'cybersecurity', 'cyber security'],
     'canonical': 'Cybersecurity Analyst', 'synonyms': [], 'broader': []},
    {'id': 'security_analyst', 'aliases': ['security analyst'], 'canonical': 'Security Analyst',
     'synonyms': [], 'broader': ['Information Security Analyst']},
]
_ROLE_INDEX = {alias: entry for entry in _ROLE_RELATIONS for alias in entry['aliases']}

def _collapse(text):
    return ' '.join(text.split())

def _title_case(text):
    return ' '.join(word.capitalize() for word in text.split())

def _strip_match(text, match):
    return text[:match.start()] + ' ' + text[match.end():]

def _extract_locations(text):
    found = []
    for loc in _LOCATIONS:
        m = re.search(r'(?<!\w)' + re.escape(loc) + r'(?!\w)', text, re.I)
        if m:
            found.append(loc)
            text = _strip_match(text, m)
    return found, text

def _extract_seniority(text):
    m = _TIER_RE.search(text)
    if m:
        raw = m.group(1).lower()
        tier = int(raw) if raw.isdigit() else _ROMAN[raw]
        return 'junior', tier, _strip_match(text, m)
    for word in _JUNIOR_WORDS:
        m = re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text, re.I)
        if m:
            return 'junior', None, _strip_match(text, m)
    for word in _SENIOR_WORDS:
        m = re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text, re.I)
        if m:
            return 'senior', None, _strip_match(text, m)
    return None, None, text

def _row(query, priority, reason, source_rule, constraints):
    return {'query': query, 'priority': priority, 'reason': reason, 'source_rule': source_rule, 'constraints': constraints}

def _dedupe_and_cap(rows, max_expansions):
    seen = set()
    result = []
    for row in sorted(rows, key=lambda r: r['priority']):
        key = _collapse(row['query']).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= max_expansions:
            break
    return result

def plan(raw_query, max_expansions=MAX_EXPANSIONS):
    """Expand raw_query into a bounded, deduplicated, explainable search plan."""
    if not isinstance(raw_query, str):
        return []
    original = raw_query.strip()
    if not original:
        return []

    working = original
    locations, working = _extract_locations(working)
    seniority, tier, working = _extract_seniority(working)
    core_title = _collapse(working)
    constraints = {'locations': locations, 'seniority': seniority}

    rows = [_row(original, 0, "User's original query, always preserved and ranked highest.", 'exact_query', constraints)]
    entry = _ROLE_INDEX.get(core_title.casefold())
    rank = 1

    if entry is None:
        if core_title:
            normalized = _title_case(core_title)
            rows.append(_row(normalized, rank,
                              f"Normalized title form of '{original}'.", 'title_normalization', constraints))
        return _dedupe_and_cap(rows, max_expansions)

    primary = entry['canonical']
    if seniority == 'junior' and tier:
        rows.append(_row(f'{primary} Tier {tier}', rank,
                          f"Numbered seniority in '{original}' normalized to the canonical Tier {tier} form of '{primary}'.",
                          f"seniority_normalization:{entry['id']}", constraints))
        rank += 1
    if seniority == 'junior':
        rows.append(_row(f'Junior {primary}', rank,
                          f"Junior-level phrasing of '{primary}'.", f"seniority_normalization:{entry['id']}", constraints))
        rank += 1
    elif seniority == 'senior':
        rows.append(_row(f'Senior {primary}', rank,
                          f"Senior-level phrasing of '{primary}'.", f"seniority_normalization:{entry['id']}", constraints))
        rank += 1

    rows.append(_row(primary, rank,
                      f"Base title for '{primary}' without a seniority qualifier.", f"title_normalization:{entry['id']}", constraints))
    rank += 1

    for synonym in entry['synonyms']:
        rows.append(_row(synonym, rank,
                          f"'{synonym}' is an established synonym for '{primary}'.", f"role_synonym:{entry['id']}", constraints))
        rank += 1

    for broader in entry['broader']:
        if seniority == 'junior':
            rows.append(_row(f'Junior {broader}', rank,
                              f"'{broader}' is an approved broader/adjacent title for '{primary}'; junior-level phrasing preserved.",
                              f"approved_broader_relation:{entry['id']}", constraints))
            rank += 1
        elif seniority == 'senior':
            rows.append(_row(f'Senior {broader}', rank,
                              f"'{broader}' is an approved broader/adjacent title for '{primary}'; senior-level phrasing preserved.",
                              f"approved_broader_relation:{entry['id']}", constraints))
            rank += 1
        rows.append(_row(broader, rank,
                          f"'{broader}' is an approved broader/adjacent title for '{primary}'.",
                          f"approved_broader_relation:{entry['id']}", constraints))
        rank += 1

    return _dedupe_and_cap(rows, max_expansions)

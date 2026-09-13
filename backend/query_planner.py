"""Discovery v2 query planner (issue #37): user intent -> bounded search plan.

Deterministic and rule-based only. Does not rank, filter eligibility, or
retrieve postings -- those are later Discovery v2 stages.

Governing principle: when confidence is high, expand; when parsing is
ambiguous, preserve the exact query and avoid expansion. Concretely:

- Expansion is limited to an explicit, curated role-relation table
  (exact alias lookup, never fuzzy/substring matching). An unrecognized
  title returns only itself -- a seniority-looking word is never stripped
  unless the stripped result is a known role, so words that are actually
  part of a role's identity (Architect, Lead, Manager, ...) are never
  destructively removed from an unrecognized title.
- Numeric level/tier and categorical seniority (junior/senior words) are
  tracked as separate constraints. A numbered level only implies a
  categorical seniority where a specific role rule documents that
  (tier_one_implies_junior); level 2+ never implies junior. When an
  explicit categorical word and a numeric level are both present, that is
  treated as a conflict: both signals are preserved in constraints, but no
  seniority/level-derived expansion row is generated for that plan.
- A location wrapped in common delimiters (parentheses, commas, hyphens,
  irregular whitespace) is recognized and cleanly removed from the parsing
  representation without leaving punctuation debris; the raw exact query
  is never altered beyond outer whitespace trimming. A location preceded
  by an explicit negation word is never turned into an affirmative
  constraint -- the whole query is treated as ambiguous and returned
  exact-only instead.
"""
import re

VERSION = 'query-planner-2'
MAX_EXPANSIONS = 10

_JUNIOR_WORDS = sorted(['entry level', 'entry-level', 'junior', 'graduate'], key=len, reverse=True)
_SENIOR_WORDS = sorted(['senior', 'principal', 'director', 'architect', 'manager', 'lead', 'head'], key=len, reverse=True)
_LEVEL_RE = re.compile(r'\b(?:level|tier)\s*-?\s*(1|2|3|i{1,3})\b', re.I)
_ROMAN = {'i': 1, 'ii': 2, 'iii': 3}
_NEGATION_WORDS = ['not', 'no', 'excluding', 'except']

_LOCATIONS = sorted(['United Arab Emirates', 'Abu Dhabi', 'Ras Al Khaimah', 'Umm Al Quwain',
                     'Dubai', 'Sharjah', 'Ajman', 'Fujairah', 'Al Ain', 'UAE'], key=len, reverse=True)
_LOC_DELIM = r'[\s,;/\-()\[\]]*'

_ROLE_RELATIONS = [
    {'id': 'soc_analyst', 'aliases': ['soc analyst'], 'canonical': 'SOC Analyst',
     'synonyms': ['Security Operations Analyst'], 'broader': ['Cybersecurity Analyst'],
     'tier_one_implies_junior': True},
    {'id': 'cybersecurity_analyst',
     'aliases': ['cybersecurity analyst', 'cyber security analyst', 'cybersecurity', 'cyber security'],
     'canonical': 'Cybersecurity Analyst', 'synonyms': [], 'broader': [], 'tier_one_implies_junior': False},
    {'id': 'security_analyst', 'aliases': ['security analyst'], 'canonical': 'Security Analyst',
     'synonyms': [], 'broader': ['Information Security Analyst'], 'tier_one_implies_junior': False},
]
_ROLE_INDEX = {alias: entry for entry in _ROLE_RELATIONS for alias in entry['aliases']}

def _collapse(text):
    return ' '.join(text.split())

def _normalize_whitespace(text):
    return re.sub(r'\s+', ' ', text)

def _validate_max_expansions(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError('max_expansions must be an int, not a bool or other type')
    if value < 1:
        raise ValueError('max_expansions must be >= 1')

def _negated_location_present(text):
    for word in _NEGATION_WORDS:
        for loc in _LOCATIONS:
            if re.search(r'\b' + word + r'\s+' + re.escape(loc) + r'\b', text, re.I):
                return True
    return False

def _extract_locations(text):
    found = []
    for loc in _LOCATIONS:
        pattern = re.compile(_LOC_DELIM + r'\b' + re.escape(loc) + r'\b' + _LOC_DELIM, re.I)
        m = pattern.search(text)
        if m:
            found.append(loc)
            text = text[:m.start()] + ' ' + text[m.end():]
    return found, _collapse(text)

def _extract_level(text):
    m = _LEVEL_RE.search(text)
    if not m:
        return None, text
    raw = m.group(1).lower()
    level = int(raw) if raw.isdigit() else _ROMAN[raw]
    return level, _collapse(text[:m.start()] + ' ' + text[m.end():])

def _extract_category(text):
    for word in _JUNIOR_WORDS:
        m = re.search(r'\b' + re.escape(word) + r'\b', text, re.I)
        if m:
            return 'junior', _collapse(text[:m.start()] + ' ' + text[m.end():])
    for word in _SENIOR_WORDS:
        m = re.search(r'\b' + re.escape(word) + r'\b', text, re.I)
        if m:
            return 'senior', _collapse(text[:m.start()] + ' ' + text[m.end():])
    return None, text

def _resolve_role(text):
    """Look up a matched role only when confident; never commit a destructive strip that misses."""
    plain_key = text.casefold()
    entry = _ROLE_INDEX.get(plain_key)
    if entry is not None:
        return entry, None
    category, stripped = _extract_category(text)
    if category is not None:
        entry = _ROLE_INDEX.get(stripped.casefold())
        if entry is not None:
            return entry, category
    return None, None

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
    _validate_max_expansions(max_expansions)
    if not isinstance(raw_query, str):
        return []
    original = raw_query.strip()
    if not original:
        return []

    parsing_text = _normalize_whitespace(original)

    if _negated_location_present(parsing_text):
        constraints = {'locations': [], 'seniority': None, 'level': None, 'role': None}
        return [_row(original, 0,
                     'Query contains a negated location; parsing is ambiguous, so only the exact query is used.',
                     'ambiguous_negation_exact_only', constraints)]

    locations, working = _extract_locations(parsing_text)
    level, working = _extract_level(working)
    entry, category = _resolve_role(working)

    if entry is None:
        constraints = {'locations': locations, 'seniority': None, 'level': None, 'role': None}
        return [_row(original, 0,
                     'No curated role rule recognized this title; only the exact query is used to avoid '
                     'destructively altering unrecognized role-identity words.',
                     'exact_only_unrecognized', constraints)]

    conflict = category is not None and level is not None
    if conflict:
        seniority = category
    elif category is not None:
        seniority = category
    elif level == 1 and entry['tier_one_implies_junior']:
        seniority = 'junior'
    else:
        seniority = None

    constraints = {'locations': locations, 'seniority': seniority, 'level': level, 'role': entry['canonical']}
    primary = entry['canonical']
    rows = [_row(original, 0, "User's original query, always preserved and ranked highest.", 'exact_query', constraints)]
    rank = 1

    if not conflict:
        if level is not None:
            rows.append(_row(f'{primary} Tier {level}', rank,
                              f"Numbered seniority in '{original}' normalized to the canonical Tier {level} form of '{primary}'.",
                              f"level_normalization:{entry['id']}", constraints))
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
        if not conflict and seniority == 'junior':
            rows.append(_row(f'Junior {broader}', rank,
                              f"'{broader}' is an approved broader/adjacent title for '{primary}'; junior-level phrasing preserved.",
                              f"approved_broader_relation:{entry['id']}", constraints))
            rank += 1
        elif not conflict and seniority == 'senior':
            rows.append(_row(f'Senior {broader}', rank,
                              f"'{broader}' is an approved broader/adjacent title for '{primary}'; senior-level phrasing preserved.",
                              f"approved_broader_relation:{entry['id']}", constraints))
            rank += 1
        rows.append(_row(broader, rank,
                          f"'{broader}' is an approved broader/adjacent title for '{primary}'.",
                          f"approved_broader_relation:{entry['id']}", constraints))
        rank += 1

    return _dedupe_and_cap(rows, max_expansions)

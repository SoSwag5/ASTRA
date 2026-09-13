import pytest
from backend.query_planner import plan, _dedupe_and_cap, _row

def _texts(rows):
    return [r['query'] for r in rows]

def _casefold_texts(rows):
    return [r['query'].casefold() for r in rows]


# ---- Numeric/seniority (Codex finding 1) ----

def test_soc_analyst_level_1_infers_junior_via_documented_role_rule():
    rows = plan('SOC Analyst Level 1')
    assert _casefold_texts(rows) == [
        'soc analyst level 1', 'soc analyst tier 1', 'junior soc analyst', 'soc analyst',
        'security operations analyst', 'junior cybersecurity analyst', 'cybersecurity analyst',
    ]
    assert rows[0]['constraints']['seniority'] == 'junior'
    assert rows[0]['constraints']['level'] == 1

def test_soc_analyst_level_2_does_not_become_junior():
    rows = plan('SOC Analyst Level 2')
    texts = _casefold_texts(rows)
    assert 'junior soc analyst' not in texts
    assert 'junior cybersecurity analyst' not in texts
    assert texts == ['soc analyst level 2', 'soc analyst tier 2', 'soc analyst',
                      'security operations analyst', 'cybersecurity analyst']
    assert rows[0]['constraints']['seniority'] is None
    assert rows[0]['constraints']['level'] == 2

def test_soc_analyst_tier_ii_roman_numeral_normalizes_without_junior():
    rows = plan('SOC Analyst Tier II')
    texts = _casefold_texts(rows)
    assert 'soc analyst tier 2' in texts
    assert 'junior soc analyst' not in texts
    assert all(r['constraints']['level'] == 2 for r in rows)
    assert all(r['constraints']['seniority'] is None for r in rows)

def test_soc_analyst_level_iii_roman_numeral():
    rows = plan('SOC Analyst Level III')
    texts = _casefold_texts(rows)
    assert 'soc analyst tier 3' in texts
    assert 'junior soc analyst' not in texts
    assert all(r['constraints']['level'] == 3 for r in rows)

def test_senior_soc_analyst_level_1_does_not_acquire_junior():
    rows = plan('Senior SOC Analyst Level 1')
    for r in rows:
        assert r['constraints']['seniority'] != 'junior'
        assert r['constraints']['seniority'] == 'senior'
        assert r['constraints']['level'] == 1
        assert r['constraints']['seniority_conflict'] is True
    texts = _casefold_texts(rows)
    assert texts == ['senior soc analyst level 1', 'soc analyst', 'security operations analyst', 'cybersecurity analyst']

def test_principal_soc_analyst_tier_2_conflict_suppresses_seniority_expansion():
    rows = plan('Principal SOC Analyst Tier 2')
    for r in rows:
        assert r['constraints']['seniority'] == 'senior'
        assert r['constraints']['level'] == 2
        assert r['constraints']['seniority_conflict'] is True
    texts = _casefold_texts(rows)
    assert texts == ['principal soc analyst tier 2', 'soc analyst', 'security operations analyst', 'cybersecurity analyst']

def test_no_conflict_flag_when_only_one_signal_present():
    for query in ['SOC Analyst Level 1', 'SOC Analyst Level 2', 'Junior SOC Analyst']:
        rows = plan(query)
        assert all(r['constraints']['seniority_conflict'] is False for r in rows)

def test_junior_soc_analyst():
    rows = plan('Junior SOC Analyst')
    texts = set(_casefold_texts(rows))
    assert texts == {'junior soc analyst', 'soc analyst', 'security operations analyst',
                      'junior cybersecurity analyst', 'cybersecurity analyst'}
    assert all(r['constraints']['level'] is None for r in rows)

def test_cybersecurity_graduate():
    rows = plan('Cybersecurity Graduate')
    texts = set(_casefold_texts(rows))
    assert texts == {'cybersecurity graduate', 'junior cybersecurity analyst', 'cybersecurity analyst'}

def test_junior_cybersecurity_analyst():
    rows = plan('Junior Cybersecurity Analyst')
    assert set(_casefold_texts(rows)) == {'junior cybersecurity analyst', 'cybersecurity analyst'}


# ---- Role integrity: unknown roles must not be destructively rewritten (Codex finding 2) ----

def test_security_architect_is_not_stripped_to_security():
    rows = plan('Security Architect')
    assert _texts(rows) == ['Security Architect']
    assert rows[0]['constraints'] == {'locations': [], 'seniority': None, 'level': None,
                                       'role': None, 'seniority_conflict': False}
    assert rows[0]['source_rule'] == 'exact_only_unrecognized'

def test_lead_generation_specialist_is_not_stripped_to_generation_specialist():
    rows = plan('Lead Generation Specialist')
    assert _texts(rows) == ['Lead Generation Specialist']

def test_graduate_program_manager_is_not_stripped():
    rows = plan('Graduate Program Manager')
    assert _texts(rows) == ['Graduate Program Manager']

def test_senior_network_security_engineer_is_not_stripped():
    rows = plan('Senior Network Security Engineer')
    assert _texts(rows) == ['Senior Network Security Engineer']

def test_network_security_engineer_never_becomes_soc_analyst():
    rows = plan('Network Security Engineer')
    assert _texts(rows) == ['Network Security Engineer']
    texts = _casefold_texts(rows)
    assert not any('soc' in t or 'cybersecurity' in t for t in texts)

def test_security_analyst_bounded_expansion():
    rows = plan('Security Analyst')
    assert set(_casefold_texts(rows)) == {'security analyst', 'information security analyst'}


# ---- Location parsing without mutating the raw query (Codex finding 3) ----

@pytest.mark.parametrize('query,expected_location', [
    ('SOC Analyst Abu Dhabi', 'Abu Dhabi'),
    ('SOC Analyst Abu\tDhabi', 'Abu Dhabi'),
    ('SOC Analyst Abu\nDhabi', 'Abu Dhabi'),
    ('SOC Analyst (Abu Dhabi)', 'Abu Dhabi'),
    ('SOC Analyst, Dubai', 'Dubai'),
    ('SOC Analyst - Sharjah', 'Sharjah'),
])
def test_location_delimiter_variants_are_recognized_and_role_still_resolves(query, expected_location):
    rows = plan(query)
    assert rows[0]['query'] == query.strip()
    assert all(r['constraints']['locations'] == [expected_location] for r in rows)
    assert rows[0]['constraints']['role'] == 'SOC Analyst'
    texts = _casefold_texts(rows)
    assert 'soc analyst' in texts
    assert not any('(' in t or ')' in t or ',' in t for t in texts if t != query.strip().casefold())

@pytest.mark.parametrize('query,expected_location', [
    ('Ras  Al Khaimah', 'Ras Al Khaimah'),
    ('Umm Al\tQuwain', 'Umm Al Quwain'),
])
def test_irregular_whitespace_location_only_input(query, expected_location):
    rows = plan(query)
    assert rows[0]['query'] == query
    assert rows[0]['constraints']['locations'] == [expected_location]

@pytest.mark.parametrize('query', [
    'UAE', 'United Arab Emirates', 'Abu Dhabi', 'Dubai', 'Sharjah', 'Ajman', 'Fujairah',
])
def test_every_supported_uae_location_recognized_standalone(query):
    rows = plan('SOC Analyst ' + query)
    assert rows[0]['constraints']['locations'] == [query]

def test_multiple_locations_are_all_captured():
    rows = plan('SOC Analyst Dubai, Sharjah')
    assert set(rows[0]['constraints']['locations']) == {'Dubai', 'Sharjah'}

def test_location_word_boundary_negative_no_false_positive():
    rows = plan('Dubaian Consulting Group')
    assert rows[0]['constraints']['locations'] == []

def test_raw_exact_query_is_never_mutated_beyond_outer_trim():
    raw = '  SOC Analyst   (Abu   Dhabi)  \n'
    rows = plan(raw)
    assert rows[0]['query'] == raw.strip()


# ---- Negation, including wrapped forms (Codex finding 4, round 2) ----

def test_negated_location_is_not_an_affirmative_constraint():
    rows = plan('SOC Analyst not Dubai')
    assert len(rows) == 1
    assert rows[0]['query'] == 'SOC Analyst not Dubai'
    assert rows[0]['constraints']['locations'] == []
    assert rows[0]['source_rule'] == 'ambiguous_negation_exact_only'

@pytest.mark.parametrize('query', [
    'SOC Analyst no Dubai', 'SOC Analyst excluding Dubai', 'SOC Analyst except Dubai',
])
def test_other_negation_words_also_fall_back_to_exact_only(query):
    rows = plan(query)
    assert len(rows) == 1
    assert rows[0]['constraints']['locations'] == []

@pytest.mark.parametrize('query', [
    'SOC Analyst not (Dubai)',
    'SOC Analyst no (Abu Dhabi)',
    'SOC Analyst excluding [Sharjah]',
    'SOC Analyst except (UAE)',
])
def test_wrapped_negated_location_still_falls_back_to_exact_only(query):
    rows = plan(query)
    assert len(rows) == 1
    assert rows[0]['query'] == query
    assert rows[0]['constraints']['locations'] == []
    assert rows[0]['source_rule'] == 'ambiguous_negation_exact_only'

@pytest.mark.parametrize('query,expected_location', [
    ('SOC Analyst (Dubai)', 'Dubai'),
    ('SOC Analyst [Abu Dhabi]', 'Abu Dhabi'),
])
def test_nearby_non_negated_wrapped_location_still_affirms(query, expected_location):
    rows = plan(query)
    assert rows[0]['constraints']['locations'] == [expected_location]
    assert rows[0]['constraints']['role'] == 'SOC Analyst'
    assert len(rows) > 1


# ---- Every occurrence of a repeated location must be inspected for negation
#      (Codex final narrow review) ----

@pytest.mark.parametrize('query', [
    'SOC Analyst Dubai not Dubai',
    'SOC Analyst Dubai not (Dubai)',
    'SOC Analyst not Dubai Dubai',
    'SOC Analyst not (Dubai) Dubai',
    'SOC Analyst Abu Dhabi except Abu Dhabi',
    'SOC Analyst Abu Dhabi, except (Abu Dhabi)',
    'SOC Analyst except Abu Dhabi Abu Dhabi',
])
def test_any_negated_occurrence_of_a_repeated_location_forces_exact_only(query):
    rows = plan(query)
    assert len(rows) == 1
    assert rows[0]['query'] == query
    assert rows[0]['constraints']['locations'] == []
    assert rows[0]['constraints']['role'] is None
    assert rows[0]['source_rule'] == 'ambiguous_negation_exact_only'

@pytest.mark.parametrize('query,expected_location', [
    ('SOC Analyst Dubai Dubai', 'Dubai'),
    ('SOC Analyst Dubai, Dubai', 'Dubai'),
    ('SOC Analyst (Dubai) Dubai', 'Dubai'),
    ('SOC Analyst Abu Dhabi Abu Dhabi', 'Abu Dhabi'),
])
def test_repeated_non_negated_location_is_affirmed_once_and_deduplicated(query, expected_location):
    rows = plan(query)
    assert rows[0]['constraints']['locations'] == [expected_location]
    assert rows[0]['constraints']['role'] == 'SOC Analyst'
    assert len(rows) > 1
    texts = _casefold_texts(rows)
    assert len(texts) == len(set(texts))

def test_two_distinct_adjacent_locations_sharing_one_delimiter_run_are_both_captured():
    # Regression for an overlap bug: widening a match's boundary over shared
    # punctuation from both sides at once (Dubai's forward-widen and
    # Sharjah's backward-widen both claiming the same ", ") incorrectly
    # dropped the second location entirely.
    rows = plan('SOC Analyst Dubai, Sharjah')
    assert set(rows[0]['constraints']['locations']) == {'Dubai', 'Sharjah'}
    assert rows[0]['constraints']['role'] == 'SOC Analyst'

def test_negation_of_one_location_still_forces_the_whole_query_to_exact_only():
    # "not" negates Dubai specifically (Sharjah has no negation word before
    # it). Per the conservative rule, any negated location anywhere makes
    # the whole query ambiguous -> exact-only, not just a partial exclusion
    # of Dubai while affirming Sharjah alone.
    rows = plan('SOC Analyst not Dubai Sharjah')
    assert len(rows) == 1
    assert rows[0]['constraints']['locations'] == []
    assert rows[0]['source_rule'] == 'ambiguous_negation_exact_only'


# ---- max_expansions contract (Codex finding 5) ----

def test_max_expansions_one_returns_exact_only():
    rows = plan('SOC Analyst Level 1', max_expansions=1)
    assert len(rows) == 1
    assert rows[0]['query'] == 'SOC Analyst Level 1'

@pytest.mark.parametrize('value', [0, -1, -100])
def test_max_expansions_below_one_raises_value_error(value):
    with pytest.raises(ValueError):
        plan('SOC Analyst', max_expansions=value)

@pytest.mark.parametrize('value', [1.0, 3.5, True, False, None, '5', [], {}])
def test_max_expansions_wrong_type_raises_type_error(value):
    with pytest.raises(TypeError):
        plan('SOC Analyst', max_expansions=value)

def test_max_expansions_validated_even_for_empty_query():
    with pytest.raises(ValueError):
        plan('', max_expansions=0)
    with pytest.raises(TypeError):
        plan('', max_expansions=None)


# ---- Structured output / provenance (Codex finding 6) ----

def test_soc_analyst_level_1_exact_row_provenance():
    rows = plan('SOC Analyst Level 1')
    assert rows[0] == {
        'query': 'SOC Analyst Level 1', 'priority': 0,
        'reason': "User's original query, always preserved and ranked highest.",
        'source_rule': 'exact_query',
        'constraints': {'locations': [], 'seniority': 'junior', 'level': 1,
                         'role': 'SOC Analyst', 'seniority_conflict': False},
    }

def test_soc_analyst_level_1_tier_row_provenance():
    rows = plan('SOC Analyst Level 1')
    tier_row = next(r for r in rows if r['query'] == 'SOC Analyst Tier 1')
    assert tier_row['source_rule'] == 'level_normalization:soc_analyst'
    assert tier_row['reason'] == ("Numbered seniority in 'SOC Analyst Level 1' normalized to the canonical "
                                   "Tier 1 form of 'SOC Analyst'.")

def test_broader_relation_row_provenance():
    rows = plan('SOC Analyst Level 1')
    row = next(r for r in rows if r['query'] == 'Cybersecurity Analyst')
    assert row['source_rule'] == 'approved_broader_relation:soc_analyst'
    assert "approved broader/adjacent title for 'SOC Analyst'" in row['reason']

def test_security_architect_constraints_report_no_confident_role_or_seniority():
    rows = plan('Security Architect')
    assert rows[0]['constraints']['role'] is None
    assert rows[0]['constraints']['seniority'] is None

def test_every_row_has_full_provenance_fields():
    for row in plan('SOC Analyst Level 1'):
        assert row['query'] and row['reason'] and row['source_rule']
        assert isinstance(row['priority'], int)
        assert set(row['constraints']) == {'locations', 'seniority', 'level', 'role', 'seniority_conflict'}

def test_priority_may_have_gaps_after_dedup_and_is_not_a_contiguous_index():
    rows = plan('SOC Analyst Tier 1')
    priorities = [r['priority'] for r in rows]
    assert priorities == sorted(priorities)
    assert len(set(priorities)) == len(priorities)


# ---- Role table stays small (Codex finding 7) ----

def test_role_table_has_exactly_three_curated_entries():
    from backend.query_planner import _ROLE_RELATIONS
    assert {e['id'] for e in _ROLE_RELATIONS} == {'soc_analyst', 'cybersecurity_analyst', 'security_analyst'}


# ---- Determinism, dedup, and cap ----

@pytest.mark.parametrize('query', [
    'SOC Analyst Level 1', 'SOC Analyst Level 2', 'SOC Analyst Tier II', 'Senior SOC Analyst Level 1',
    'Principal SOC Analyst Tier 2', 'Junior SOC Analyst', 'Security Analyst', 'Network Security Engineer',
    'Security Architect', 'Lead Generation Specialist', 'SOC Analyst Abu Dhabi', 'SOC Analyst not Dubai',
])
def test_deterministic_across_repeated_calls(query):
    assert plan(query) == plan(query)

@pytest.mark.parametrize('query', [
    'SOC Analyst Level 1', 'SOC Analyst Tier 1', 'Junior SOC Analyst', 'Security Analyst',
    'SOC Analyst Abu Dhabi', 'Network Security Engineer',
])
def test_duplicate_expansions_are_eliminated(query):
    texts = _casefold_texts(plan(query))
    assert len(texts) == len(set(texts))

def test_dedupe_and_cap_enforces_limit_directly():
    constraints = {'locations': [], 'seniority': None, 'level': None, 'role': None}
    synthetic = [_row(f'Role {i}', i, 'synthetic', 'synthetic', constraints) for i in range(25)]
    capped = _dedupe_and_cap(synthetic, 10)
    assert len(capped) == 10
    assert [r['priority'] for r in capped] == list(range(10))

def test_dedupe_and_cap_removes_case_and_whitespace_duplicates():
    constraints = {'locations': [], 'seniority': None, 'level': None, 'role': None}
    rows = [
        _row('SOC Analyst', 0, 'a', 'a', constraints),
        _row('soc   analyst', 1, 'b', 'b', constraints),
        _row('Cybersecurity Analyst', 2, 'c', 'c', constraints),
    ]
    capped = _dedupe_and_cap(rows, 10)
    assert len(capped) == 2
    assert capped[0]['query'] == 'SOC Analyst'


# ---- Malformed/empty input ----

@pytest.mark.parametrize('bad_input', [None, '', '   ', 123, [], {}])
def test_malformed_or_empty_input_is_handled_safely(bad_input):
    assert plan(bad_input) == []

def test_exact_query_always_present_and_highest_priority():
    for query in ['SOC Analyst Level 1', 'Network Security Engineer', 'Security Analyst']:
        rows = plan(query)
        assert rows[0]['query'] == query
        assert rows[0]['priority'] == min(r['priority'] for r in rows)


# ---- Input length ceiling (Codex finding 1, round 2 defense-in-depth) ----

def test_query_at_max_length_is_processed():
    query = 'SOC Analyst ' + ('x' * (1024 - len('SOC Analyst ')))
    assert len(query) == 1024
    rows = plan(query)
    assert rows[0]['query'] == query

def test_query_over_max_length_raises_value_error():
    with pytest.raises(ValueError):
        plan('x' * 1025)

def test_query_length_checked_before_stripping():
    with pytest.raises(ValueError):
        plan(' ' * 1025)


# ---- Adversarial/resource performance (Codex finding 1, round 2) ----
#
# plan() itself now rejects anything over MAX_QUERY_LENGTH (1024 chars) as a
# defense-in-depth ceiling, so 2k/4k/8k-scale adversarial input can no longer
# reach the scanning code through the public plan() entry point -- that
# ceiling check is a cheap len() comparison performed before any scanning.
# The actual algorithmic fix (bounded, linear location/negation scanning,
# never an unbounded delimiter regex around the location literal) is what
# must scale, so it is exercised directly here via _scan_locations,
# independent of the public-API length ceiling, at sizes well beyond 1024.

from backend.query_planner import _scan_locations, MAX_QUERY_LENGTH

def _elapsed(fn):
    import time
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start

@pytest.mark.parametrize('n', [1000, 2000, 4000])
def test_scan_locations_punctuation_only_is_fast_and_bounded(n):
    assert _elapsed(lambda: _scan_locations('-' * n)) < 1.0

def test_scan_locations_scaling_is_not_quadratic():
    # A quadratic implementation shows a much-worse-than-linear time increase
    # per doubling; a linear one should not. Sizes are far beyond anything
    # plan() will accept, specifically to prove the algorithm itself (not
    # just the length ceiling) is no longer pathological. Generous margin so
    # this is not a flaky microbenchmark.
    small = _elapsed(lambda: _scan_locations('(' * 4000))
    large = _elapsed(lambda: _scan_locations('(' * 32000))
    assert large < max(small * 16, 0.5)

@pytest.mark.parametrize('filler', ['-', '(', ')', ',', '[', ']', '- , ( ) [ ] '])
def test_scan_locations_mixed_punctuation_fillers_stay_fast(filler):
    assert _elapsed(lambda: _scan_locations(filler * 4000)) < 1.0

def test_scan_locations_real_location_after_long_punctuation_prefix():
    prefix = '-(),[] ' * 2000
    text = 'SOC Analyst ' + prefix + 'Dubai'
    found, cleaned, negated = _scan_locations(text)
    assert _elapsed(lambda: _scan_locations(text)) < 1.0
    assert found == ['Dubai']
    assert negated is False

def test_query_within_length_limit_containing_punctuation_is_fast_through_plan():
    query = ('SOC Analyst ' + '-(),[] ' * 100 + 'Dubai')[:MAX_QUERY_LENGTH]
    result = plan(query)
    assert _elapsed(lambda: plan(query)) < 1.0
    assert 'Dubai' in result[0]['constraints']['locations']

def test_scan_locations_many_repeated_non_negated_occurrences_stay_linear():
    # Regression for a second O(n) issue found alongside the repeated-
    # location correctness bug: _negated_before used to slice the entire
    # prefix (up to O(n) long) per match, making a query with many
    # occurrences of the same location O(n^2) overall even though the
    # widening/reconstruction logic itself was already linear.
    small = _elapsed(lambda: _scan_locations('Dubai ' * 500))
    large = _elapsed(lambda: _scan_locations('Dubai ' * 8000))
    assert large < max(small * 32, 0.5)

def test_negation_word_as_suffix_of_a_longer_word_is_not_a_false_positive():
    # "cannot" ends in "not" but is not the word "not"; must not be
    # treated as negating the following location.
    rows = plan('SOC Analyst cannot Dubai')
    assert rows[0]['constraints']['locations'] == ['Dubai']

def test_over_length_query_is_rejected_immediately_regardless_of_size():
    huge = '-' * 50000
    def attempt():
        with pytest.raises(ValueError):
            plan(huge)
    assert _elapsed(attempt) < 1.0

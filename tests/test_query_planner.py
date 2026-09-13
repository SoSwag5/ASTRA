import re
import pytest
from backend.query_planner import plan, _dedupe_and_cap, _row, _SENIOR_WORDS

def _texts(rows):
    return [r['query'] for r in rows]

def test_soc_analyst_level_1_matches_owner_example():
    rows = plan('SOC Analyst Level 1')
    texts = {r.casefold() for r in _texts(rows)}
    assert texts == {
        'soc analyst level 1', 'soc analyst tier 1', 'soc analyst', 'junior soc analyst',
        'security operations analyst', 'junior cybersecurity analyst', 'cybersecurity analyst',
    }
    assert rows[0]['query'] == 'SOC Analyst Level 1'
    assert rows[0]['priority'] == 0
    assert rows[0]['source_rule'] == 'exact_query'

def test_soc_analyst_tier_1_dedupes_exact_against_normalized_tier_form():
    rows = plan('SOC Analyst Tier 1')
    texts = [r['query'].casefold() for r in rows]
    assert texts.count('soc analyst tier 1') == 1
    assert 'junior soc analyst' in texts
    assert 'cybersecurity analyst' in texts

def test_junior_soc_analyst():
    rows = plan('Junior SOC Analyst')
    texts = {r['query'].casefold() for r in rows}
    assert 'junior soc analyst' in texts
    assert 'soc analyst' in texts
    assert 'security operations analyst' in texts
    assert 'junior cybersecurity analyst' in texts
    assert 'cybersecurity analyst' in texts
    assert 'soc analyst tier 1' not in texts

def test_junior_cybersecurity_analyst():
    rows = plan('Junior Cybersecurity Analyst')
    texts = {r['query'].casefold() for r in rows}
    assert texts == {'junior cybersecurity analyst', 'cybersecurity analyst'}

def test_security_analyst_bounded_expansion():
    rows = plan('Security Analyst')
    texts = {r['query'].casefold() for r in rows}
    assert texts == {'security analyst', 'information security analyst'}

def test_network_security_engineer_does_not_become_soc_analyst():
    rows = plan('Network Security Engineer')
    texts = [r['query'].casefold() for r in rows]
    assert texts == ['network security engineer']
    assert not any('soc' in t or 'cybersecurity' in t for t in texts)

def test_cybersecurity_graduate():
    rows = plan('Cybersecurity Graduate')
    texts = {r['query'].casefold() for r in rows}
    assert texts == {'cybersecurity graduate', 'junior cybersecurity analyst', 'cybersecurity analyst'}

def test_soc_analyst_abu_dhabi_preserves_location_on_every_row():
    rows = plan('SOC Analyst Abu Dhabi')
    assert rows[0]['query'] == 'SOC Analyst Abu Dhabi'
    assert all(r['constraints']['locations'] == ['Abu Dhabi'] for r in rows)
    texts = {r['query'].casefold() for r in rows}
    assert 'soc analyst' in texts
    assert 'cybersecurity analyst' in texts
    assert not any(t != 'soc analyst abu dhabi' and 'abu dhabi' in t for t in texts)

def test_junior_soc_analyst_uae_preserves_location_and_seniority():
    rows = plan('Junior SOC Analyst UAE')
    assert all(r['constraints']['locations'] == ['UAE'] for r in rows)
    assert all(r['constraints']['seniority'] == 'junior' for r in rows)
    texts = {r['query'].casefold() for r in rows}
    assert 'junior soc analyst' in texts
    assert 'soc analyst tier 1' not in texts

@pytest.mark.parametrize('query', [
    'SOC Analyst Level 1', 'Junior SOC Analyst', 'Cybersecurity Graduate', 'Junior SOC Analyst UAE',
])
def test_no_senior_variants_for_junior_queries(query):
    rows = plan(query)
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(w) for w in _SENIOR_WORDS) + r')(?!\w)', re.I)
    assert not any(pattern.search(r['query']) for r in rows)

@pytest.mark.parametrize('query', [
    'SOC Analyst Level 1', 'SOC Analyst Tier 1', 'Junior SOC Analyst', 'Junior Cybersecurity Analyst',
    'Security Analyst', 'Network Security Engineer', 'Cybersecurity Graduate',
    'SOC Analyst Abu Dhabi', 'Junior SOC Analyst UAE',
])
def test_duplicate_expansions_are_eliminated(query):
    rows = plan(query)
    texts = [r['query'].casefold() for r in rows]
    assert len(texts) == len(set(texts))

@pytest.mark.parametrize('query', [
    'SOC Analyst Level 1', 'SOC Analyst Tier 1', 'Junior SOC Analyst', 'Junior Cybersecurity Analyst',
    'Security Analyst', 'Network Security Engineer', 'Cybersecurity Graduate',
    'SOC Analyst Abu Dhabi', 'Junior SOC Analyst UAE',
])
def test_deterministic_across_repeated_calls(query):
    assert plan(query) == plan(query)

def test_exact_query_always_present_and_highest_priority():
    for query in ['SOC Analyst Level 1', 'Network Security Engineer', 'Security Analyst']:
        rows = plan(query)
        assert rows[0]['query'] == query
        assert rows[0]['priority'] == min(r['priority'] for r in rows)

def test_planner_respects_maximum_expansion_limit_via_public_api():
    rows = plan('SOC Analyst Level 1', max_expansions=3)
    assert len(rows) == 3
    assert rows[0]['query'] == 'SOC Analyst Level 1'

def test_dedupe_and_cap_enforces_limit_directly():
    constraints = {'locations': [], 'seniority': None}
    synthetic = [_row(f'Role {i}', i, 'synthetic', 'synthetic', constraints) for i in range(25)]
    capped = _dedupe_and_cap(synthetic, 10)
    assert len(capped) == 10
    assert [r['priority'] for r in capped] == list(range(10))

def test_dedupe_and_cap_removes_case_and_whitespace_duplicates():
    constraints = {'locations': [], 'seniority': None}
    rows = [
        _row('SOC Analyst', 0, 'a', 'a', constraints),
        _row('soc   analyst', 1, 'b', 'b', constraints),
        _row('Cybersecurity Analyst', 2, 'c', 'c', constraints),
    ]
    capped = _dedupe_and_cap(rows, 10)
    assert len(capped) == 2
    assert capped[0]['query'] == 'SOC Analyst'

@pytest.mark.parametrize('bad_input', [None, '', '   ', 123, [], {}])
def test_malformed_or_empty_input_is_handled_safely(bad_input):
    assert plan(bad_input) == []

def test_seniority_only_input_does_not_crash():
    rows = plan('Junior')
    assert rows == [{'query': 'Junior', 'priority': 0,
                      'reason': "User's original query, always preserved and ranked highest.",
                      'source_rule': 'exact_query', 'constraints': {'locations': [], 'seniority': 'junior'}}]

def test_every_row_has_explainable_provenance_fields():
    for row in plan('SOC Analyst Level 1'):
        assert row['query'] and row['reason'] and row['source_rule']
        assert isinstance(row['priority'], int)
        assert 'locations' in row['constraints'] and 'seniority' in row['constraints']

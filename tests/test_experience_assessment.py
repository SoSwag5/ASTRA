"""Issue #41: backend.experience parser unit tests (scoped clauses, not the
legacy flattened shape -- see tests/test_recall.py for the compatibility
adapter's own tests)."""
import pytest
from backend import experience as exp


@pytest.mark.parametrize('text,minimum,necessity', [
    ('0 years required', 0, exp.REQUIRED),
    ('1-3 years of experience', 1, exp.REQUIRED),
    ('1–3 years of experience', 1, exp.REQUIRED),
    ('1—3 years of experience', 1, exp.REQUIRED),
    ('1 to 3 years of experience', 1, exp.REQUIRED),
    ('3+ years required', 3, exp.REQUIRED),
    ('minimum 5 years required', 5, exp.REQUIRED),
    ('at least five years required', 5, exp.REQUIRED),
    ('5 years preferred', 5, exp.PREFERRED),
    ('5 years is a plus', 5, exp.PREFERRED),
])
def test_parser_syntax_variants(text, minimum, necessity):
    req = exp.parse(text)
    assert req.clauses, text
    assert req.clauses[0].minimum_years == minimum
    assert req.clauses[0].necessity == necessity


def test_no_experience_required_is_not_a_numeric_zero_requirement():
    req = exp.parse('No experience required. Graduate role.')
    assert req.no_experience_required
    assert req.effective_required_minimum is None


def test_scoped_clauses_are_never_summed():
    req = exp.parse('7+ years overall, 2+ years in cloud infrastructure')
    minimums = sorted(c.minimum_years for c in req.clauses)
    assert minimums == [2, 7]
    assert req.effective_required_minimum == 7


def test_or_equivalent_is_recorded():
    req = exp.parse('Bachelor degree or 4 years of experience or equivalent required')
    assert any(c.or_equivalent for c in req.clauses)


def test_company_history_years_are_not_candidate_experience():
    req = exp.parse('Our company was founded 25 years ago. Candidates need 2 years of experience.')
    assert req.effective_required_minimum == 2


def test_training_duration_is_not_candidate_experience():
    req = exp.parse('Complete a 3-year training program before certification.')
    assert req.effective_required_minimum is None


def test_candidate_years_unknown_by_default():
    assert exp.candidate_years({}) is None
    assert exp.candidate_years({'declarations': {'verified_relevant_experience_years': 5}}) is None
    assert exp.candidate_years({'declarations': {'verified_relevant_experience_years': 5, 'verified_relevant_experience_years_confirmed': True}}) == 5.0

"""Issue #40 normalization unit tests: determinism, idempotence, Unicode
safety, URL identity rules, and unknown-value handling. See
backend/normalization.py.
"""
from backend import normalization as n


def test_normalization_is_deterministic_and_idempotent():
    title = ' Senior  SOC   Analyst '
    once = n.title_key(title)
    twice = n.title_key(n.title_key(title) or '')
    assert once == n.title_key(title)  # deterministic
    assert once == twice  # idempotent


def test_title_key_preserves_seniority_words():
    assert n.title_key('SOC Analyst') != n.title_key('Senior SOC Analyst')
    assert n.title_key('SOC Analyst') != n.title_key('Lead SOC Analyst')
    assert n.title_key('SOC Analyst') != n.title_key('Principal SOC Analyst')
    assert n.title_key('SOC Analyst') != n.title_key('SOC Manager')


def test_unicode_normalization_collapses_equivalent_forms():
    # 'é' as a single codepoint vs 'e' + combining acute accent.
    composed = 'Cliffé Analyst'
    decomposed = 'Cliffé Analyst'
    assert n.title_key(composed) == n.title_key(decomposed)


def test_employer_key_unknown_and_empty_are_none():
    assert n.employer_key('') is None
    assert n.employer_key('UNKNOWN') is None
    assert n.employer_key('Acme') is not None


def test_location_key_unknown_is_none_never_a_wildcard():
    assert n.location_key('UNKNOWN') is None
    assert n.location_key('') is None
    a = n.location_key('Dubai')
    b = n.location_key('Dubai')
    assert a is not None and a == b


def test_workplace_key_canonicalizes_known_values_and_rejects_unknown():
    assert n.workplace_key('Remote') == 'REMOTE'
    assert n.workplace_key('On-site') == 'ONSITE'
    assert n.workplace_key('on site') == 'ONSITE'
    assert n.workplace_key('Hybrid') == 'HYBRID'
    assert n.workplace_key('UNKNOWN') is None
    assert n.workplace_key('') is None
    assert n.workplace_key('Somewhere else') is None


def test_url_identity_strips_tracking_params_and_fragment():
    a = n.normalize_url_for_identity('https://boards.greenhouse.io/acme/jobs/123?utm_source=li&utm_campaign=x')
    b = n.normalize_url_for_identity('https://boards.greenhouse.io/acme/jobs/123#apply')
    c = n.normalize_url_for_identity('https://BOARDS.greenhouse.io/acme/jobs/123')
    assert a == b == c


def test_generic_careers_root_is_not_job_specific():
    assert n.is_job_specific_url('https://acme.example.com/careers') is False
    assert n.is_job_specific_url('https://acme.example.com/jobs') is False
    assert n.is_job_specific_url('https://acme.example.com/') is False
    assert n.is_job_specific_url('https://acme.example.com') is False


def test_login_and_portal_pages_are_not_job_specific():
    assert n.is_job_specific_url('https://portal.example.com/login') is False
    assert n.is_job_specific_url('https://portal.example.com/search') is False


def test_url_with_identifying_segment_is_job_specific():
    assert n.is_job_specific_url('https://boards.greenhouse.io/acme/jobs/123') is True
    assert n.is_job_specific_url('https://jobs.lever.co/acme/some-uuid-here') is True


def test_non_specific_url_never_becomes_identity():
    assert n.normalize_url_for_identity('https://acme.example.com/careers') is None
    assert n.normalize_url_for_identity('') is None
    assert n.normalize_url_for_identity(None) is None


def test_content_fingerprint_ignores_harmless_whitespace_and_case():
    a = n.content_fingerprint('Monitor SIEM alerts,   triage incidents,\nand escalate confirmed threats during business hours.')
    b = n.content_fingerprint('monitor siem alerts, triage incidents, and escalate confirmed threats during business hours.')
    assert a == b and a is not None


def test_content_fingerprint_none_for_short_or_empty_text():
    assert n.content_fingerprint('') is None
    assert n.content_fingerprint('Short.') is None


def test_content_fingerprint_differs_for_different_content():
    a = n.content_fingerprint('Monitor SIEM alerts, triage incidents, and escalate confirmed threats during business hours today.')
    b = n.content_fingerprint('Prepare payroll runs, reconcile timesheets, and file statutory reports every month end cycle.')
    assert a != b


def test_normalize_bundles_every_key():
    observation = n.JobObservationInput(
        employer_name='Acme Corp', title='Senior SOC Analyst', location='Dubai', workplace='Remote',
        description='Monitor SIEM alerts, triage incidents, and escalate confirmed threats during business hours.',
        source_url='https://boards.greenhouse.io/acme/jobs/123?utm_source=li',
    )
    result = n.normalize(observation)
    assert result.employer_key is not None
    assert result.title_key is not None
    assert result.location_key is not None
    assert result.workplace_key == 'REMOTE'
    assert result.url_identity is not None
    assert result.content_fingerprint is not None


def test_normalize_unknown_observation_yields_all_none_matching_keys():
    observation = n.JobObservationInput()  # every field at its UNKNOWN/empty default
    result = n.normalize(observation)
    assert result.employer_key is None
    assert result.title_key is None
    assert result.location_key is None
    assert result.workplace_key is None
    assert result.url_identity is None
    assert result.content_fingerprint is None


def test_canonical_view_only_promotes_documented_provider_posted_at():
    documented = n.JobObservationInput(posted_at='2026-01-01T00:00:00Z', posted_at_authority='documented_provider_field')
    undocumented = n.JobObservationInput(posted_at='2026-01-01T00:00:00Z', posted_at_authority='none')
    assert n.canonical_view(documented).date_posted == '2026-01-01T00:00:00Z'
    assert n.canonical_view(undocumented).date_posted == ''

"""Fixture-driven regressions for the #46 application-state model.

Every record here is fictional. No live mailbox, no real employer and no real
application is involved; the Gmail evidence rows are constructed directly in
the isolated test database from the same minimized shape #45 produces.
"""
import itertools
import threading

import pytest
from sqlalchemy import delete, select

from backend import application_reconciliation as reconciliation
from backend import application_state as states
from backend import gmail_confirmations as parsers
from backend import gmail_sync as sync
from backend.models import (Application, ApplicationEvent, FollowUp, Job,
                            JobObservation, Session, now)

FICTIONAL_COMPANY = 'Northwind Analytics'
FICTIONAL_ROLE = 'SOC Analyst'
FICTIONAL_URL = 'https://boards.greenhouse.io/northwind/jobs/4821'
APPLIED_AT = '2026-08-01T09:00:00+00:00'
RECEIVED_AT = '2026-08-01T09:04:00+00:00'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_state():
    """Isolated, empty canonical/evidence tables for every test."""
    from backend.models import initialize
    initialize()
    reconciliation.initialize_reconciliation_schema()
    with Session.begin() as db:
        db.execute(delete(reconciliation.GmailApplicationLink))
        db.execute(delete(states.ApplicationStateTransition))
        db.execute(delete(states.ApplicationStateRecord))
        db.execute(delete(sync.GmailConfirmation))
        db.execute(delete(ApplicationEvent))
        db.execute(delete(FollowUp))
        db.execute(delete(Application))
        db.execute(delete(JobObservation))
        db.execute(delete(Job))
    yield


def make_application(*, company=FICTIONAL_COMPANY, title=FICTIONAL_ROLE,
                     source='Greenhouse', apply_url=FICTIONAL_URL,
                     applied_date=APPLIED_AT, status='FOUND',
                     stage=None, date_found=APPLIED_AT):
    """One fictional job plus its application, as the existing code stores them."""
    from backend.normalization import employer_key
    with Session.begin() as db:
        job = Job(company=company, title=title, source=source,
                  apply_url=apply_url, job_url=apply_url,
                  normalized_employer_key=employer_key(company) or '',
                  date_found=date_found, status='FOUND')
        db.add(job)
        db.flush()
        application = Application(job_id=job.id, status=status,
                                  applied_date=applied_date,
                                  tracking={'stage': stage} if stage else {})
        db.add(application)
        db.flush()
        return application.id, job.id


def make_evidence(*, confidence='HIGH', company=FICTIONAL_COMPANY,
                  role=FICTIONAL_ROLE, url=FICTIONAL_URL,
                  received_at=RECEIVED_AT, message_id='fictional-message-1',
                  detected_state=parsers.APPLICATION_CONFIRMED,
                  parser_id='greenhouse-confirmation-v1',
                  signals=('SENDER_DOMAIN', 'SUBJECT_STRUCTURE', 'BODY_TEMPLATE',
                           'FIELD_CONSISTENCY', 'AUTHENTICATION')):
    """One minimized evidence row in exactly #45's stored shape."""
    with Session.begin() as db:
        row = sync.GmailConfirmation(
            account_slot='PRIMARY', gmail_account_id='fictional-account-id',
            gmail_message_id=message_id,
            sender='noreply@greenhouse.io',
            subject='Thank you for applying to ' + company,
            received_at=received_at, detected_company=company,
            detected_role=role, detected_state=detected_state,
            confidence=confidence, parser_id=parser_id,
            evidence_signals=list(signals), application_url=url)
        db.add(row)
        db.flush()
        return row.id


def current_state(application_id):
    with Session() as db:
        record = db.scalar(select(states.ApplicationStateRecord).where(
            states.ApplicationStateRecord.application_id == application_id))
        return record.current_state if record else None


def history_rows(application_id):
    with Session() as db:
        return db.scalars(
            select(states.ApplicationStateTransition)
            .where(states.ApplicationStateTransition.application_id == application_id)
            .order_by(states.ApplicationStateTransition.sequence)).all()


def force_state(application_id, state, *, source=states.SOURCE_USER_ACTION):
    """Walk an application to `state` through permitted transitions only."""
    path = {states.DISCOVERED: [], states.SAVED: [states.SAVED],
            states.APPLIED: [states.APPLIED],
            states.VIEWED: [states.APPLIED, states.VIEWED],
            states.ASSESSMENT: [states.APPLIED, states.ASSESSMENT],
            states.INTERVIEW: [states.APPLIED, states.INTERVIEW],
            states.OFFER: [states.APPLIED, states.OFFER],
            states.REJECTED: [states.APPLIED, states.REJECTED],
            states.CLOSED: [states.CLOSED]}[state]
    with Session.begin() as db:
        application = db.get(Application, application_id)
        states.ensure_state(db, application)
        for step in path:
            decision = states.assert_state(db, application, step,
                                           source_category=source)
            assert decision.applied or decision.reason_code == states.REFUSED_NO_CHANGE, (
                step, decision.reason_code)
    return current_state(application_id)


def reconcile(evidence_id):
    with Session.begin() as db:
        row = db.get(sync.GmailConfirmation, evidence_id)
        return reconciliation.reconcile_confirmation(db, row)


# ---------------------------------------------------------------------------
# The transition table
# ---------------------------------------------------------------------------
def test_transition_table_is_complete_and_forward_only():
    assert set(states.PERMITTED) == set(states.STATES)
    for previous, targets in states.PERMITTED.items():
        assert targets <= set(states.STATES)
        assert previous not in targets, 'a self-transition is not a transition'
        for target in targets:
            assert states.ORDINAL[target] > states.ORDINAL[previous], (
                f'{previous} -> {target} regresses')


@pytest.mark.parametrize('previous,new', list(itertools.product(states.STATES,
                                                                states.STATES)))
def test_every_state_pair_matches_the_declared_table(previous, new):
    """Fixture-driven coverage of all 81 ordered pairs, permitted and forbidden."""
    expected = new in states.PERMITTED[previous]
    assert states.is_permitted(previous, new) is expected

    application_id, _ = make_application()
    reached = force_state(application_id, previous)
    assert reached == previous
    with Session.begin() as db:
        application = db.get(Application, application_id)
        decision = states.assert_state(db, application, new,
                                       source_category=states.SOURCE_USER_ACTION)
    assert decision.applied is expected, (previous, new, decision.reason_code)
    assert current_state(application_id) == (new if expected else previous)
    if not expected:
        assert decision.reason_code in (states.REFUSED_NOT_PERMITTED,
                                        states.REFUSED_NO_CHANGE,
                                        states.REFUSED_TERMINAL)


@pytest.mark.parametrize('skip', [(states.DISCOVERED, states.APPLIED),
                                  (states.APPLIED, states.INTERVIEW),
                                  (states.APPLIED, states.OFFER),
                                  (states.VIEWED, states.INTERVIEW),
                                  (states.SAVED, states.APPLIED)])
def test_legitimate_forward_skips_are_permitted(skip):
    assert states.is_permitted(*skip)


@pytest.mark.parametrize('terminal', [states.OFFER, states.REJECTED])
def test_offer_and_rejected_may_only_close(terminal):
    assert states.PERMITTED[terminal] == frozenset({states.CLOSED})


def test_closed_has_no_outgoing_transition():
    assert states.PERMITTED[states.CLOSED] == frozenset()
    application_id, _ = make_application()
    force_state(application_id, states.CLOSED)
    for target in states.STATES:
        with Session.begin() as db:
            application = db.get(Application, application_id)
            decision = states.assert_state(db, application, target,
                                           source_category=states.SOURCE_USER_ACTION)
        assert not decision.applied
    assert current_state(application_id) == states.CLOSED


def test_unknown_state_and_unknown_source_are_refused():
    application_id, _ = make_application()
    with Session.begin() as db:
        application = db.get(Application, application_id)
        assert states.assert_state(db, application, 'PROMOTED',
                                   source_category=states.SOURCE_USER_ACTION
                                   ).reason_code == states.REFUSED_UNKNOWN_STATE
        assert states.assert_state(db, application, states.APPLIED,
                                   source_category='SOMEONE_ELSE'
                                   ).reason_code == states.REFUSED_UNKNOWN_SOURCE


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def test_history_is_append_only_and_carries_full_provenance():
    application_id, _ = make_application()
    force_state(application_id, states.APPLIED)
    rows = history_rows(application_id)
    assert [row.sequence for row in rows] == list(range(1, len(rows) + 1))
    bootstrap = rows[0]
    assert bootstrap.previous_state == ''
    assert bootstrap.source_category == states.SOURCE_LEGACY_MIGRATION
    assert bootstrap.reason_code == states.REASON_LEGACY_BOOTSTRAP
    final = rows[-1]
    assert final.new_state == states.APPLIED
    assert final.source_category == states.SOURCE_USER_ACTION
    assert final.occurred_at and final.recorded_at
    assert final.reason_code in states.ACCEPTED_REASONS

    before = len(rows)
    force_state(application_id, states.APPLIED)  # no-op
    assert len(history_rows(application_id)) == before
    # A later transition appends; it never rewrites an earlier row.
    identifiers = [row.id for row in rows]
    with Session.begin() as db:
        states.assert_state(db, db.get(Application, application_id), states.INTERVIEW,
                            source_category=states.SOURCE_USER_ACTION)
    after = history_rows(application_id)
    assert [row.id for row in after[:before]] == identifiers
    assert len(after) == before + 1


def test_refused_transitions_append_nothing():
    application_id, _ = make_application()
    force_state(application_id, states.APPLIED)
    before = len(history_rows(application_id))
    with Session.begin() as db:
        decision = states.assert_state(db, db.get(Application, application_id),
                                       states.SAVED,
                                       source_category=states.SOURCE_USER_ACTION)
    assert decision.reason_code == states.REFUSED_NOT_PERMITTED
    assert len(history_rows(application_id)) == before


def test_history_columns_reject_unbounded_external_content():
    application_id, _ = make_application()
    hostile = 'Northwind Analytics <script>alert(1)</script> ' * 20
    with Session.begin() as db:
        states.assert_state(
            db, db.get(Application, application_id), states.APPLIED,
            source_category=states.SOURCE_GMAIL_PARSER, confidence=states.HIGH,
            asserted_by=hostile, parser_id=hostile,
            gmail_message_id='bad\nvalue\r\n', gmail_account_id=hostile,
            evidence_tokens=[hostile, 'BODY_TRUNCATED', 'SENDER_DOMAIN'],
            field_agreement=['COMPANY', hostile], occurred_at='not-a-timestamp')
    row = history_rows(application_id)[-1]
    assert hostile not in row.asserted_by
    assert len(row.asserted_by) <= 64
    assert len(row.parser_id) <= states.MAX_PARSER_ID_CHARS
    assert row.gmail_message_id == '', 'control characters are not an identifier'
    assert row.evidence_tokens == ['BODY_TRUNCATED', 'OCCURRED_AT_INVALID',
                                   'SENDER_DOMAIN']
    assert row.field_agreement == ['COMPANY']
    assert states.parse_timestamp(row.occurred_at) is not None


@pytest.mark.parametrize('value', ['', 'not-a-timestamp', '2026-13-45T99:00:00Z',
                                   None, 12345, '2999-01-01T00:00:00+00:00'])
def test_invalid_or_future_timestamps_never_reach_history(value):
    application_id, _ = make_application()
    with Session.begin() as db:
        states.assert_state(db, db.get(Application, application_id), states.APPLIED,
                            source_category=states.SOURCE_USER_ACTION,
                            occurred_at=value)
    row = history_rows(application_id)[-1]
    parsed = states.parse_timestamp(row.occurred_at)
    assert parsed is not None
    from datetime import datetime, timezone
    assert parsed <= datetime.now(timezone.utc) + states.MAX_FUTURE_SKEW


# ---------------------------------------------------------------------------
# Manual authority and confidence gating
# ---------------------------------------------------------------------------
def test_manual_state_is_never_superseded_by_automated_evidence():
    application_id, _ = make_application()
    force_state(application_id, states.INTERVIEW)
    with Session.begin() as db:
        decision = states.assert_state(
            db, db.get(Application, application_id), states.APPLIED,
            source_category=states.SOURCE_GMAIL_PARSER, confidence=states.HIGH)
    assert not decision.applied
    assert current_state(application_id) == states.INTERVIEW


def test_medium_evidence_cannot_downgrade_a_manually_confirmed_state():
    application_id, _ = make_application()
    force_state(application_id, states.INTERVIEW)
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    assert result.decision != reconciliation.DECISION_LINKED
    assert current_state(application_id) == states.INTERVIEW
    assert not any(row.source_category == states.SOURCE_GMAIL_PARSER
                   for row in history_rows(application_id))


@pytest.mark.parametrize('confidence', ['MEDIUM', 'LOW'])
@pytest.mark.parametrize('target', [states.VIEWED, states.ASSESSMENT,
                                    states.INTERVIEW, states.OFFER,
                                    states.REJECTED])
def test_weak_evidence_cannot_set_a_later_state(confidence, target):
    application_id, _ = make_application()
    force_state(application_id, states.APPLIED)
    with Session.begin() as db:
        decision = states.assert_state(
            db, db.get(Application, application_id), target,
            source_category=states.SOURCE_GMAIL_PARSER, confidence=confidence)
    assert decision.reason_code == states.REFUSED_STATE_NOT_AUTOMATABLE
    assert current_state(application_id) == states.APPLIED


@pytest.mark.parametrize('target', [states.VIEWED, states.ASSESSMENT,
                                    states.INTERVIEW, states.OFFER,
                                    states.REJECTED, states.CLOSED])
def test_even_high_confidence_cannot_set_a_later_state(target):
    """#45 parses no later-stage message, so no confidence authorizes one."""
    application_id, _ = make_application()
    force_state(application_id, states.APPLIED)
    with Session.begin() as db:
        decision = states.assert_state(
            db, db.get(Application, application_id), target,
            source_category=states.SOURCE_GMAIL_PARSER, confidence=states.HIGH)
    assert decision.reason_code == states.REFUSED_STATE_NOT_AUTOMATABLE
    assert states.AUTOMATED_TARGET_STATES == frozenset({states.APPLIED})


def test_deferred_parser_states_have_no_canonical_mapping():
    for deferred in parsers.DEFERRED_STATES:
        assert deferred not in reconciliation.DETECTED_STATE_TO_CANONICAL


@pytest.mark.parametrize('confidence', ['MEDIUM', 'LOW', '', 'VERY_HIGH'])
def test_only_high_confidence_may_apply_a_transition(confidence):
    application_id, _ = make_application()
    with Session.begin() as db:
        decision = states.assert_state(
            db, db.get(Application, application_id), states.APPLIED,
            source_category=states.SOURCE_GMAIL_PARSER, confidence=confidence)
    assert decision.reason_code == states.REFUSED_CONFIDENCE_TOO_LOW
    assert current_state(application_id) != states.APPLIED


# ---------------------------------------------------------------------------
# Reconciliation matching
# ---------------------------------------------------------------------------
def test_high_confidence_unique_strong_match_applies_applied():
    application_id, _ = make_application()
    evidence_id = make_evidence()
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_LINKED
    assert result.reason_code == reconciliation.REASON_HIGH_UNIQUE_MATCH
    assert result.application_id == application_id
    assert len(result.matched_fields) >= 3
    assert current_state(application_id) == states.APPLIED
    row = history_rows(application_id)[-1]
    assert row.source_category == states.SOURCE_GMAIL_PARSER
    assert row.confidence == states.HIGH
    assert row.gmail_confirmation_id == evidence_id
    assert row.gmail_message_id == 'fictional-message-1'
    assert row.parser_id == 'greenhouse-confirmation-v1'
    assert states.FIELD_COMPANY in row.field_agreement


def test_a_single_matching_field_never_merges_records():
    """Company alone agrees; role, date, URL and platform all disagree."""
    application_id, _ = make_application(title='Payroll Administrator',
                                         source='Manual', apply_url='',
                                         applied_date='2026-01-05T09:00:00+00:00',
                                         date_found='2026-01-05T09:00:00+00:00')
    evidence_id = make_evidence()
    result = reconcile(evidence_id)
    # Never merged and never mutated. It stays reviewable rather than being
    # consumed, but it is not linked to anything.
    assert result.application_id is None
    assert result.decision != reconciliation.DECISION_LINKED
    assert result.reason_code == reconciliation.REASON_SINGLE_FIELD_ONLY
    assert result.matched_fields == [states.FIELD_COMPANY]
    assert result.strong_candidate_count == 0
    assert current_state(application_id) != states.APPLIED


def test_two_agreeing_fields_are_still_not_a_strong_match():
    """Company and role agree; nothing else does. Two fields is not enough."""
    application_id, _ = make_application(source='Manual', apply_url='',
                                         applied_date='2026-01-05T09:00:00+00:00',
                                         date_found='2026-01-05T09:00:00+00:00')
    evidence_id = make_evidence()
    result = reconcile(evidence_id)
    assert result.application_id is None
    assert result.decision != reconciliation.DECISION_LINKED
    assert result.reason_code == reconciliation.REASON_NO_STRONG_MATCH
    assert sorted(result.matched_fields) == [states.FIELD_COMPANY, states.FIELD_ROLE]
    assert result.strong_candidate_count == 0
    assert current_state(application_id) != states.APPLIED


def test_different_employer_produces_no_candidate_at_all():
    make_application(company='Contoso Robotics')
    evidence_id = make_evidence()
    result = reconcile(evidence_id)
    assert result.reason_code == reconciliation.REASON_NO_CANDIDATES
    assert result.candidate_count == 0
    assert result.application_id is None


def test_ambiguous_matches_never_mutate_or_create_an_application():
    first, _ = make_application()
    second, _ = make_application()
    with Session() as db:
        before = db.scalar(select(Application.id).order_by(Application.id.desc()))
    evidence_id = make_evidence()
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_NEEDS_REVIEW
    assert result.reason_code == reconciliation.REASON_AMBIGUOUS
    assert result.strong_candidate_count == 2
    assert current_state(first) != states.APPLIED
    assert current_state(second) != states.APPLIED
    with Session() as db:
        assert db.scalar(select(Application.id).order_by(Application.id.desc())) == before


def test_unmatched_evidence_never_fabricates_a_job_or_application():
    with Session() as db:
        jobs = len(db.scalars(select(Job)).all())
        applications = len(db.scalars(select(Application)).all())
    evidence_id = make_evidence(company='Unknown Holdings')
    result = reconcile(evidence_id)
    assert result.decision != reconciliation.DECISION_LINKED
    assert result.application_id is None
    with Session() as db:
        assert len(db.scalars(select(Job)).all()) == jobs
        assert len(db.scalars(select(Application)).all()) == applications
    assert reconciliation.reconciliation_status()['creates_applications'] is False


def test_existing_manual_application_is_never_duplicated():
    application_id, job_id = make_application()
    force_state(application_id, states.APPLIED)
    evidence_id = make_evidence()
    reconcile(evidence_id)
    with Session() as db:
        assert len(db.scalars(select(Application).where(
            Application.job_id == job_id)).all()) == 1
        assert len(db.scalars(select(Job)).all()) == 1
    # The application was already APPLIED, so nothing changed and the refusal
    # is explainable rather than silent.
    link = reconciliation.link_for(evidence_id)
    assert link['reason_code'] == reconciliation.REASON_TRANSITION_REFUSED
    assert current_state(application_id) == states.APPLIED


def test_medium_evidence_enters_needs_review_without_mutation():
    application_id, _ = make_application()
    force_state(application_id, states.SAVED)
    before = current_state(application_id)
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_NEEDS_REVIEW
    assert result.reason_code == reconciliation.REASON_MEDIUM_NEEDS_REVIEW
    assert result.application_id == application_id
    assert current_state(application_id) == before
    queue = reconciliation.needs_review()
    assert [item['gmail_confirmation_id'] for item in queue['items']] == [evidence_id]


def test_low_evidence_never_transitions_and_never_queues():
    application_id, _ = make_application()
    force_state(application_id, states.SAVED)
    before = current_state(application_id)
    evidence_id = make_evidence(confidence='LOW')
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_NO_ACTION
    assert result.reason_code == reconciliation.REASON_LOW_CONFIDENCE
    assert current_state(application_id) == before
    assert reconciliation.needs_review()['count'] == 0


def test_unsupported_detected_state_is_refused_before_matching():
    make_application()
    evidence_id = make_evidence(detected_state='INTERVIEW_INVITED')
    result = reconcile(evidence_id)
    assert result.reason_code == reconciliation.REASON_STATE_UNSUPPORTED
    assert result.application_id is None


def test_unusable_confidence_value_is_refused():
    make_application()
    evidence_id = make_evidence(confidence='CERTAIN')
    result = reconcile(evidence_id)
    assert result.reason_code == reconciliation.REASON_EVIDENCE_INVALID


@pytest.mark.parametrize('url', ['', 'not a url', 'javascript:alert(1)',
                                 'http://127.0.0.1/jobs/1',
                                 'https://boards.greenhouse.io/'])
def test_malformed_or_unsafe_urls_never_become_identity_evidence(url):
    make_application()
    evidence_id = make_evidence(url=url, role='Payroll Administrator',
                                received_at='2026-01-05T09:00:00+00:00')
    result = reconcile(evidence_id)
    # An unusable URL establishes no identity, so it neither agrees nor
    # contradicts -- and it certainly never links anything by itself.
    assert states.FIELD_URL not in result.matched_fields
    assert result.decision != reconciliation.DECISION_LINKED
    assert result.reason_code != reconciliation.REASON_URL_CONFLICT


def test_date_proximity_is_bounded():
    """A far-apart date withholds its corroboration, which is the difference
    between a two-field weak match and a three-field strong one."""
    application_id, _ = make_application(source='Manual', apply_url='')
    force_state(application_id, states.DISCOVERED)
    far = make_evidence(received_at='2026-11-20T09:00:00+00:00',
                        message_id='fictional-message-far', url='')
    far_result = reconcile(far)
    assert states.FIELD_DATE not in far_result.matched_fields
    assert far_result.decision != reconciliation.DECISION_LINKED
    assert current_state(application_id) != states.APPLIED

    near = make_evidence(received_at='2026-08-03T09:00:00+00:00',
                         message_id='fictional-message-near', url='')
    near_result = reconcile(near)
    assert states.FIELD_DATE in near_result.matched_fields
    assert near_result.decision == reconciliation.DECISION_LINKED
    assert current_state(application_id) == states.APPLIED


def test_source_platform_corroborates_only_a_known_family():
    application_id, job_id = make_application(source='Lever', apply_url='',
                                              title='Payroll Administrator')
    evidence_id = make_evidence()
    assert states.FIELD_PLATFORM not in reconcile(evidence_id).matched_fields
    assert current_state(application_id) != states.APPLIED


# ---------------------------------------------------------------------------
# Idempotency and concurrency
# ---------------------------------------------------------------------------
def test_replaying_the_same_evidence_creates_no_second_transition():
    application_id, _ = make_application()
    evidence_id = make_evidence()
    first = reconcile(evidence_id)
    depth = len(history_rows(application_id))
    for _ in range(3):
        again = reconcile(evidence_id)
        assert again.link_id == first.link_id
        assert again.transition_id == first.transition_id
    assert len(history_rows(application_id)) == depth
    with Session() as db:
        assert len(db.scalars(select(reconciliation.GmailApplicationLink)).all()) == 1


def test_reconcile_pending_is_idempotent_across_runs():
    make_application()
    make_evidence()
    first = reconciliation.reconcile_pending()
    assert first['considered'] == 1 and first['linked'] == 1
    second = reconciliation.reconcile_pending()
    assert second['considered'] == 0
    with Session() as db:
        assert len(db.scalars(select(reconciliation.GmailApplicationLink)).all()) == 1


def test_concurrent_reconciliation_produces_one_link_and_one_transition():
    application_id, _ = make_application()
    evidence_id = make_evidence()
    barrier = threading.Barrier(4)
    errors = []

    def worker():
        try:
            barrier.wait(timeout=20)
            reconcile(evidence_id)
        except Exception as error:  # surfaced below, never swallowed
            errors.append(repr(error))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors, errors
    with Session() as db:
        links = db.scalars(select(reconciliation.GmailApplicationLink)).all()
        assert len(links) == 1
        applications = db.scalars(select(Application)).all()
        assert len(applications) == 1
    applied = [row for row in history_rows(application_id)
               if row.source_category == states.SOURCE_GMAIL_PARSER]
    assert len(applied) == 1
    assert current_state(application_id) == states.APPLIED


def test_a_lost_history_append_race_is_a_bounded_refusal():
    """The unique (application_id, sequence) index is the real guarantee. A
    writer that loses the race is told so and leaves the transaction usable;
    it never produces a gap, a duplicate or an overwrite."""
    application_id, _ = make_application()
    force_state(application_id, states.SAVED)
    with Session.begin() as db:
        application = db.get(Application, application_id)
        record = states.ensure_state(db, application)
        # Simulate a competing writer having already taken the next sequence.
        db.add(states.ApplicationStateTransition(
            application_id=application_id, sequence=record.sequence + 1,
            previous_state=states.SAVED, new_state=states.APPLIED,
            source_category=states.SOURCE_USER_ACTION, asserted_by='OTHER'))
        db.flush()
        record.sequence -= 1  # our view of the sequence is now stale
        decision = states.assert_state(db, application, states.APPLIED,
                                       source_category=states.SOURCE_USER_ACTION)
        assert decision.reason_code == states.REFUSED_CONCURRENT_UPDATE
        assert not decision.applied
        # The transaction is still usable after the refusal.
        assert db.get(Application, application_id) is not None


def test_concurrent_bootstrap_produces_one_projection():
    application_id, _ = make_application()
    barrier = threading.Barrier(4)
    errors = []

    def worker():
        try:
            barrier.wait(timeout=20)
            with Session.begin() as db:
                states.ensure_state(db, db.get(Application, application_id))
        except Exception as error:
            errors.append(repr(error))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors, errors
    with Session() as db:
        assert len(db.scalars(select(states.ApplicationStateRecord).where(
            states.ApplicationStateRecord.application_id == application_id)).all()) == 1
        assert len(db.scalars(select(states.ApplicationStateTransition).where(
            states.ApplicationStateTransition.application_id == application_id)).all()) == 1


# ---------------------------------------------------------------------------
# User review operations
# ---------------------------------------------------------------------------
def test_user_confirmation_is_a_manual_transition_that_keeps_gmail_provenance():
    application_id, _ = make_application()
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    outcome = reconciliation.confirm_review(result.link_id)
    assert outcome['ok'] and outcome['applied']
    assert current_state(application_id) == states.APPLIED
    row = history_rows(application_id)[-1]
    assert row.source_category == states.SOURCE_USER_CONFIRMED_GMAIL
    assert row.reason_code == states.REASON_GMAIL_USER_CONFIRMED
    assert row.gmail_confirmation_id == evidence_id
    assert row.gmail_message_id == 'fictional-message-1'
    assert row.parser_id == 'greenhouse-confirmation-v1'
    # It carries the user's authority, so no later automated signal can
    # re-assert or supersede it.
    with Session() as db:
        record = db.scalar(select(states.ApplicationStateRecord).where(
            states.ApplicationStateRecord.application_id == application_id))
        assert record.manual_ordinal == states.ORDINAL[states.APPLIED]


def test_user_rejection_never_changes_state():
    application_id, _ = make_application()
    force_state(application_id, states.SAVED)
    before = current_state(application_id)
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    outcome = reconciliation.reject_review(result.link_id)
    assert outcome['ok'] and outcome['applied'] is False
    assert current_state(application_id) == before
    assert reconciliation.needs_review()['count'] == 0
    # Rejection is terminal for that item; it cannot then be confirmed.
    assert reconciliation.confirm_review(result.link_id)['ok'] is False


def test_confirming_an_ambiguous_item_requires_a_strong_candidate():
    first, _ = make_application()
    make_application()
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    assert result.reason_code == reconciliation.REASON_AMBIGUOUS
    assert reconciliation.confirm_review(result.link_id,
                                         application_id=9999)['ok'] is False
    outcome = reconciliation.confirm_review(result.link_id, application_id=first)
    assert outcome['ok'] and current_state(first) == states.APPLIED


# ---------------------------------------------------------------------------
# Legacy bootstrap and upgrade
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('stage,status,expected', [
    ('APPLIED', 'NEEDS_REVIEW', states.APPLIED),
    ('SHORTLISTED', 'NEEDS_REVIEW', states.SAVED),
    ('FINAL_INTERVIEW', 'NEEDS_REVIEW', states.INTERVIEW),
    ('HIRED', 'NEEDS_REVIEW', states.CLOSED),
    ('WITHDRAWN', 'NEEDS_REVIEW', states.CLOSED),
    ('NO_RESPONSE', 'APPLIED', states.APPLIED),
    (None, 'READY_TO_APPLY', states.SAVED),
    (None, 'REJECTED', states.REJECTED),
    (None, 'SKIP', states.DISCOVERED),
])
def test_legacy_bootstrap_derives_only_what_the_data_supports(stage, status, expected):
    application_id, _ = make_application(stage=stage, status=status)
    with Session.begin() as db:
        states.ensure_state(db, db.get(Application, application_id))
    assert current_state(application_id) == expected
    row = history_rows(application_id)[0]
    assert row.source_category == states.SOURCE_LEGACY_MIGRATION
    assert row.previous_state == ''
    assert row.confidence == '' and row.gmail_message_id == ''
    assert row.gmail_confirmation_id == 0 and row.parser_id == ''


def test_bootstrap_invents_no_date_when_the_record_has_none():
    application_id, _ = make_application(stage='APPLIED', applied_date='')
    with Session.begin() as db:
        states.ensure_state(db, db.get(Application, application_id))
    row = history_rows(application_id)[0]
    assert states.TOKEN_APPLIED_DATE_PRESENT not in row.evidence_tokens
    assert states.TOKEN_LEGACY_STAGE_DERIVED in row.evidence_tokens


def test_bootstrap_preserves_every_existing_record():
    application_id, job_id = make_application(stage='APPLIED')
    with Session.begin() as db:
        db.add(FollowUp(application_id=application_id, due_date=APPLIED_AT))
        db.add(ApplicationEvent(job_id=job_id, application_id=application_id,
                                message='Synthetic note'))
    with Session.begin() as db:
        states.ensure_state(db, db.get(Application, application_id))
    with Session() as db:
        assert db.get(Job, job_id) is not None
        assert db.get(Application, application_id).applied_date == APPLIED_AT
        assert len(db.scalars(select(FollowUp)).all()) == 1
        assert len(db.scalars(select(ApplicationEvent)).all()) == 1


def test_bootstrap_is_idempotent():
    application_id, _ = make_application(stage='APPLIED')
    for _ in range(3):
        with Session.begin() as db:
            states.ensure_state(db, db.get(Application, application_id))
    assert len(history_rows(application_id)) == 1


def test_upgrade_from_a_pre_46_schema_creates_the_tables_and_bootstraps():
    """A database that predates #46 has neither table; both are added additively."""
    from sqlalchemy import inspect, text
    application_id, _ = make_application(stage='APPLIED')
    from backend.models import engine
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE IF EXISTS gmail_application_links'))
        connection.execute(text('DROP TABLE IF EXISTS application_state_transitions'))
        connection.execute(text('DROP TABLE IF EXISTS application_states'))
    assert not states.schema_ready()
    assert not reconciliation.schema_ready()

    states.ensure_schema()
    reconciliation.initialize_reconciliation_schema()
    assert states.schema_ready() and reconciliation.schema_ready()
    # Rolling the schema forward twice is safe.
    reconciliation.initialize_reconciliation_schema()

    result = states.state_of(application_id)
    assert result['state']['current_state'] == states.APPLIED
    assert result['history'][0]['source_category'] == states.SOURCE_LEGACY_MIGRATION
    inspector = inspect(engine)
    assert {'applications', 'jobs'} <= set(inspector.get_table_names())


def test_rollback_to_a_pre_46_schema_leaves_existing_records_intact():
    """Dropping #46's additive tables is a supported rollback: the older code
    paths never referenced them, and no pre-#46 row depends on them."""
    from sqlalchemy import text
    application_id, job_id = make_application(stage='APPLIED')
    force_state(application_id, states.APPLIED)
    from backend.models import engine
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE IF EXISTS gmail_application_links'))
        connection.execute(text('DROP TABLE IF EXISTS application_state_transitions'))
        connection.execute(text('DROP TABLE IF EXISTS application_states'))
    with Session() as db:
        application = db.get(Application, application_id)
        assert application is not None
        assert application.tracking.get('stage') == 'APPLIED'
        assert db.get(Job, job_id) is not None


# ---------------------------------------------------------------------------
# Compatibility with the legacy vocabularies
# ---------------------------------------------------------------------------
def test_every_campaign_stage_and_workflow_status_has_a_declared_mapping():
    from backend.campaign import STAGES
    from backend.policy import STATUSES
    for stage in STAGES:
        assert stage in states.STAGE_TO_STATE, stage
        assert states.STAGE_TO_STATE[stage] in states.STATES or states.STAGE_TO_STATE[stage] is None
    for status in STATUSES:
        assert status in states.STATUS_TO_STATE, status
        assert states.STATUS_TO_STATE[status] in states.STATES or states.STATUS_TO_STATE[status] is None


def test_legacy_values_without_canonical_meaning_assert_nothing():
    application_id, _ = make_application()
    for value in ('NO_RESPONSE', 'SKIP', 'FAILED', '', None, 'NOT_A_STAGE'):
        with Session.begin() as db:
            assert states.record_legacy_assertion(
                db, db.get(Application, application_id), value,
                source_category=states.SOURCE_USER_ACTION) is None


def test_campaign_tracking_records_the_canonical_transition():
    from backend.campaign import TrackInput, track
    _, job_id = make_application(applied_date='', status='NEEDS_REVIEW')
    track(job_id, TrackInput(stage='APPLIED', cv_version='SOC v3',
                             date='2026-08-01T09:00:00+00:00'))
    with Session() as db:
        application = db.scalar(select(Application).where(Application.job_id == job_id))
    assert application.tracking['stage'] == 'APPLIED'
    assert current_state(application.id) == states.APPLIED
    row = history_rows(application.id)[-1]
    assert row.source_category == states.SOURCE_USER_ACTION
    assert row.new_state == states.APPLIED


def test_campaign_tracking_never_regresses_the_canonical_state():
    from backend.campaign import TrackInput, track
    _, job_id = make_application(applied_date='', status='NEEDS_REVIEW')
    track(job_id, TrackInput(stage='APPLIED', cv_version='SOC v3',
                             date='2026-08-01T09:00:00+00:00'))
    with Session() as db:
        application = db.scalar(select(Application).where(Application.job_id == job_id))
    depth = len(history_rows(application.id))
    track(job_id, TrackInput(stage='SHORTLISTED'))
    with Session() as db:
        refreshed = db.scalar(select(Application).where(Application.job_id == job_id))
    # The legacy compatibility field follows the user's edit exactly as before.
    assert refreshed.tracking['stage'] == 'SHORTLISTED'
    # The canonical state does not regress, and nothing was appended.
    assert current_state(application.id) == states.APPLIED
    assert len(history_rows(application.id)) == depth


def test_job_status_action_records_the_canonical_transition():
    from backend.services import set_status
    application_id, job_id = make_application(applied_date='', status='READY_TO_APPLY')
    with Session.begin() as db:
        job = db.get(Job, job_id)
        job.status = 'READY_TO_APPLY'
        application = set_status(db, job, 'APPLIED')
        states.record_legacy_assertion(db, application, 'APPLIED',
                                       source_category=states.SOURCE_USER_ACTION)
    assert current_state(application_id) == states.APPLIED


def test_summary_and_history_reads_are_bounded_and_explain_authority():
    application_id, _ = make_application()
    force_state(application_id, states.APPLIED)
    summary = states.state_summary()
    assert summary['states'][states.APPLIED] == 1
    assert summary['authoritative_field'] == 'application_states.current_state'
    assert set(summary['transition_table']) == set(states.STATES)
    history = states.transition_history(application_id, limit=1000)
    assert len(history) <= states.MAX_LISTED_TRANSITIONS
    result = states.state_of(application_id)
    assert result['legacy']['authoritative_field'] == 'application_states.current_state'


# ---------------------------------------------------------------------------
# Remediation: contradictory requisition URLs block automatic linking
# ---------------------------------------------------------------------------
def test_conflicting_requisition_urls_never_auto_link():
    """Employer, title, date and platform all agree -- which is exactly what
    two separate applications to the same employer share -- but the two
    records name different postings. That contradiction is decisive."""
    application_id, _ = make_application(
        apply_url='https://boards.greenhouse.io/northwind/jobs/111')
    evidence_id = make_evidence(
        url='https://boards.greenhouse.io/northwind/jobs/999')
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_NEEDS_REVIEW
    assert result.reason_code == reconciliation.REASON_URL_CONFLICT
    assert result.strong_candidate_count == 0
    assert current_state(application_id) != states.APPLIED
    assert not any(row.source_category == states.SOURCE_GMAIL_PARSER
                   for row in history_rows(application_id))
    # The other four fields did agree; they simply cannot outweigh it.
    assert {states.FIELD_COMPANY, states.FIELD_ROLE, states.FIELD_DATE,
            states.FIELD_PLATFORM} <= set(result.matched_fields)
    assert states.FIELD_URL not in result.matched_fields


def test_conflicting_urls_are_a_contradiction_not_a_missing_field():
    """A contradicted candidate corroborates but is never strong."""
    application_id, job_id = make_application(
        apply_url='https://boards.greenhouse.io/northwind/jobs/111')
    evidence_id = make_evidence(
        url='https://boards.greenhouse.io/northwind/jobs/999')
    with Session.begin() as db:
        row = db.get(sync.GmailConfirmation, evidence_id)
        candidates = reconciliation.find_candidates(db, row)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.conflicts == {states.FIELD_URL}
    assert candidate.corroborated is True
    assert candidate.strong is False
    # The user may still resolve it; only ASTRA is barred from deciding.
    assert candidate.confirmable is True


def test_a_url_conflict_review_item_is_resolvable_by_the_user():
    application_id, _ = make_application(
        apply_url='https://boards.greenhouse.io/northwind/jobs/111')
    evidence_id = make_evidence(
        url='https://boards.greenhouse.io/northwind/jobs/999')
    result = reconcile(evidence_id)
    assert result.application_id == application_id, 'the target is proposed'
    outcome = reconciliation.confirm_review(result.link_id)
    assert outcome['ok'] and outcome['applied']
    assert current_state(application_id) == states.APPLIED
    row = history_rows(application_id)[-1]
    assert row.source_category == states.SOURCE_USER_CONFIRMED_GMAIL


@pytest.mark.parametrize('spelling', [
    'https://boards.greenhouse.io/northwind/jobs/4821',
    'HTTPS://Boards.Greenhouse.IO/northwind/jobs/4821',
    'https://boards.greenhouse.io/northwind/jobs/4821/',
    'https://boards.greenhouse.io/northwind/jobs/4821?utm_source=newsletter',
    'https://boards.greenhouse.io/northwind/jobs/4821/?trk=alert&ref=mail',
])
def test_superficially_different_spellings_of_one_posting_still_link(spelling):
    """Normalization decides identity, so formatting differences agree
    rather than contradicting."""
    application_id, _ = make_application(apply_url=FICTIONAL_URL)
    evidence_id = make_evidence(url=spelling)
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_LINKED
    assert states.FIELD_URL in result.matched_fields
    assert result.reason_code == reconciliation.REASON_HIGH_UNIQUE_MATCH
    assert current_state(application_id) == states.APPLIED


@pytest.mark.parametrize('generic', [
    'https://boards.greenhouse.io/',
    'https://boards.greenhouse.io/northwind',
    'https://careers.example.com/login',
    'https://careers.example.com/search',
])
def test_generic_roots_establish_no_identity_and_contradict_nothing(generic):
    """A careers root, tenant root, login or search page is not a
    requisition, so it must neither agree nor contradict."""
    application_id, _ = make_application(apply_url=generic)
    evidence_id = make_evidence(url=FICTIONAL_URL)
    result = reconcile(evidence_id)
    assert result.reason_code != reconciliation.REASON_URL_CONFLICT
    with Session.begin() as db:
        row = db.get(sync.GmailConfirmation, evidence_id)
        candidate = reconciliation.find_candidates(db, row)[0]
    assert candidate.conflicts == set()
    # Conservative either way: the remaining fields still decide.
    assert states.FIELD_URL not in candidate.fields


def test_evidence_without_a_url_never_conflicts():
    application_id, _ = make_application(
        apply_url='https://boards.greenhouse.io/northwind/jobs/111')
    evidence_id = make_evidence(url='')
    result = reconcile(evidence_id)
    assert result.reason_code != reconciliation.REASON_URL_CONFLICT
    # Company, role, date and platform still agree, so this links normally.
    assert result.decision == reconciliation.DECISION_LINKED
    assert current_state(application_id) == states.APPLIED


def test_url_conflict_does_not_block_a_different_uncontradicted_application():
    """Two applications to one employer: the contradicted one is excluded,
    the matching one links. A conflict narrows, it does not paralyse."""
    conflicting, _ = make_application(
        apply_url='https://boards.greenhouse.io/northwind/jobs/111')
    matching, _ = make_application(apply_url=FICTIONAL_URL)
    evidence_id = make_evidence(url=FICTIONAL_URL)
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_LINKED
    assert result.application_id == matching
    assert current_state(matching) == states.APPLIED
    assert current_state(conflicting) != states.APPLIED


# ---------------------------------------------------------------------------
# Remediation: the first manual status change is a user action, not migration
# ---------------------------------------------------------------------------
def make_untracked_job(*, company='Fabrikam Systems', title='SOC Analyst',
                       status='FOUND'):
    """A Job with no Application at all -- the pre-#46 starting point."""
    from backend.normalization import employer_key
    with Session.begin() as db:
        job = Job(company=company, title=title, source='Manual', status=status,
                  normalized_employer_key=employer_key(company) or '',
                  date_found=APPLIED_AT)
        db.add(job)
        db.flush()
        return job.id


def status_action(job_id, status):
    """Drive the real job status route, guards and all."""
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as client:
        response = client.post(f'/api/jobs/{job_id}/status', json={'status': status})
        assert response.status_code == 200, response.text
        return response.json()


@pytest.mark.parametrize('legacy_status,expected', [
    ('APPLIED', states.APPLIED),
    ('READY_TO_APPLY', states.SAVED),
    ('INTERVIEW', states.INTERVIEW),
    ('REJECTED', states.REJECTED),
    ('OFFER', states.OFFER),
])
def test_first_manual_status_change_is_recorded_as_a_user_action(legacy_status,
                                                                 expected):
    job_id = make_untracked_job()
    with Session() as db:
        assert db.scalar(select(Application).where(
            Application.job_id == job_id)) is None, 'no application yet'

    status_action(job_id, legacy_status)

    with Session() as db:
        application = db.scalar(select(Application).where(
            Application.job_id == job_id))
    assert application is not None
    rows = history_rows(application.id)

    # The bootstrap records where the job actually was, from the job's own
    # workflow status, which the action had not yet touched.
    assert rows[0].source_category == states.SOURCE_LEGACY_MIGRATION
    assert rows[0].new_state == states.DISCOVERED
    assert states.TOKEN_PRE_ACTION_STATE in rows[0].evidence_tokens

    # The user's change is the user's change.
    assert rows[-1].source_category == states.SOURCE_USER_ACTION
    assert rows[-1].asserted_by == 'USER'
    assert rows[-1].previous_state == states.DISCOVERED
    assert rows[-1].new_state == expected
    assert rows[-1].reason_code == states.REASON_USER_ACTION
    assert any(row.source_category == states.SOURCE_USER_ACTION for row in rows)
    assert not any(row.source_category == states.SOURCE_LEGACY_MIGRATION
                   and row.new_state == expected for row in rows)

    # It carries manual authority, and legacy and canonical agree.
    with Session() as db:
        record = db.scalar(select(states.ApplicationStateRecord).where(
            states.ApplicationStateRecord.application_id == application.id))
    assert record.current_state == expected
    assert record.source_category == states.SOURCE_USER_ACTION
    assert record.manual_ordinal == states.ORDINAL[expected]
    assert states.canonical_for_legacy(application.status) == record.current_state


@pytest.mark.parametrize('legacy_status,expected', [
    ('INTERVIEW', states.INTERVIEW), ('OFFER', states.OFFER),
    ('REJECTED', states.REJECTED),
])
def test_a_post_submission_first_action_records_that_submission_was_implied(
        legacy_status, expected):
    """ASTRA never saw a submission, so the history says the user's
    assertion implies one rather than pretending ASTRA observed it."""
    job_id = make_untracked_job()
    status_action(job_id, legacy_status)
    with Session() as db:
        application = db.scalar(select(Application).where(
            Application.job_id == job_id))
    row = history_rows(application.id)[-1]
    assert row.new_state == expected
    assert states.TOKEN_SUBMISSION_IMPLIED in row.evidence_tokens


def test_a_manually_created_state_cannot_be_reasserted_by_gmail_evidence():
    """The regression this defect actually mattered for: manual_ordinal was
    left unset, so automated evidence could re-assert the user's own state."""
    job_id = make_untracked_job(company=FICTIONAL_COMPANY, title=FICTIONAL_ROLE)
    status_action(job_id, 'APPLIED')
    with Session() as db:
        application = db.scalar(select(Application).where(
            Application.job_id == job_id))
        application.applied_date = APPLIED_AT
        job = db.get(Job, job_id)
        job.apply_url = FICTIONAL_URL
        job.job_url = FICTIONAL_URL
        job.source = 'Greenhouse'
        db.commit()
    depth = len(history_rows(application.id))
    evidence_id = make_evidence()
    reconcile(evidence_id)
    assert len(history_rows(application.id)) == depth, 'no automated re-assertion'
    link = reconciliation.link_for(evidence_id)
    assert link['reason_code'] == reconciliation.REASON_TRANSITION_REFUSED


def test_second_manual_status_change_appends_a_second_user_action():
    job_id = make_untracked_job()
    status_action(job_id, 'APPLIED')
    status_action(job_id, 'INTERVIEW')
    with Session() as db:
        application = db.scalar(select(Application).where(
            Application.job_id == job_id))
    rows = history_rows(application.id)
    user_rows = [row for row in rows if row.source_category == states.SOURCE_USER_ACTION]
    assert [row.new_state for row in user_rows] == [states.APPLIED, states.INTERVIEW]
    assert current_state(application.id) == states.INTERVIEW


def test_campaign_tracking_on_an_untracked_job_is_also_a_user_action():
    """The same defect class on the other legacy write path."""
    from backend.campaign import TrackInput, track
    job_id = make_untracked_job()
    track(job_id, TrackInput(stage='APPLIED', cv_version='SOC v3',
                             date=APPLIED_AT))
    with Session() as db:
        application = db.scalar(select(Application).where(
            Application.job_id == job_id))
    rows = history_rows(application.id)
    assert rows[0].new_state == states.DISCOVERED
    assert rows[0].source_category == states.SOURCE_LEGACY_MIGRATION
    assert rows[-1].source_category == states.SOURCE_USER_ACTION
    assert rows[-1].new_state == states.APPLIED
    assert current_state(application.id) == states.APPLIED


# ---------------------------------------------------------------------------
# Remediation: unlinkable MEDIUM evidence stays reviewable and resolvable
# ---------------------------------------------------------------------------
def test_medium_evidence_with_no_candidate_stays_in_needs_review():
    evidence_id = make_evidence(confidence='MEDIUM', company='Unaffiliated Holdings')
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_NEEDS_REVIEW
    assert result.reason_code == reconciliation.REASON_NO_CANDIDATES
    assert result.application_id is None
    queue = reconciliation.needs_review()
    assert [item['gmail_confirmation_id'] for item in queue['items']] == [evidence_id]
    assert queue['items'][0]['application_id'] is None


def test_medium_evidence_with_no_candidate_never_creates_anything():
    with Session() as db:
        jobs = len(db.scalars(select(Job)).all())
        applications = len(db.scalars(select(Application)).all())
    reconcile(make_evidence(confidence='MEDIUM', company='Unaffiliated Holdings'))
    with Session() as db:
        assert len(db.scalars(select(Job)).all()) == jobs
        assert len(db.scalars(select(Application)).all()) == applications


def test_a_matching_application_created_later_is_picked_up_deterministically():
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    assert result.reason_code == reconciliation.REASON_NO_CANDIDATES
    assert result.application_id is None

    # The user saves the application afterwards.
    application_id, _ = make_application()

    summary = reconciliation.reconcile_pending()
    assert summary['revisited'] == 1
    assert summary['considered'] == 0
    link = reconciliation.link_for(evidence_id)
    assert link['decision'] == reconciliation.DECISION_NEEDS_REVIEW
    assert link['reason_code'] == reconciliation.REASON_MEDIUM_NEEDS_REVIEW
    assert link['application_id'] == application_id
    # Still no mutation: MEDIUM waits for the user.
    assert current_state(application_id) != states.APPLIED

    outcome = reconciliation.confirm_review(link['id'])
    assert outcome['ok'] and outcome['applied']
    assert current_state(application_id) == states.APPLIED
    row = history_rows(application_id)[-1]
    assert row.source_category == states.SOURCE_USER_CONFIRMED_GMAIL
    assert row.gmail_confirmation_id == evidence_id


def test_high_evidence_unmatched_then_matched_links_on_the_next_run():
    evidence_id = make_evidence(confidence='HIGH')
    assert reconcile(evidence_id).reason_code == reconciliation.REASON_NO_CANDIDATES
    application_id, _ = make_application()
    summary = reconciliation.reconcile_pending()
    assert summary['revisited'] == 1 and summary['linked'] == 1
    assert current_state(application_id) == states.APPLIED
    link = reconciliation.link_for(evidence_id)
    assert link['decision'] == reconciliation.DECISION_LINKED


def test_a_user_may_confirm_unmatched_medium_evidence_directly():
    """No `reconcile_pending` in between: confirmation re-evaluates
    candidates itself, so the queue item is actionable as soon as a target
    exists."""
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    application_id, _ = make_application()
    outcome = reconciliation.confirm_review(result.link_id)
    assert outcome['ok'] and outcome['applied']
    assert current_state(application_id) == states.APPLIED


def test_confirming_unmatched_evidence_rejects_an_invalid_target():
    unrelated, _ = make_application(company='Contoso Robotics',
                                    title='Payroll Administrator')
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    outcome = reconciliation.confirm_review(result.link_id,
                                            application_id=unrelated)
    assert outcome['ok'] is False
    assert outcome['reason_code'] == reconciliation.REASON_NO_STRONG_MATCH
    assert current_state(unrelated) != states.APPLIED
    # Rejected targets leave the item reviewable rather than consuming it.
    assert reconciliation.needs_review()['count'] == 1


def test_revisiting_is_idempotent_and_never_duplicates():
    evidence_id = make_evidence(confidence='MEDIUM')
    reconcile(evidence_id)
    application_id, _ = make_application()
    for _ in range(3):
        reconciliation.reconcile_pending()
    with Session() as db:
        assert len(db.scalars(select(reconciliation.GmailApplicationLink)).all()) == 1
        assert len(db.scalars(select(Application)).all()) == 1
    assert reconciliation.needs_review()['count'] == 1
    # Three revisits changed nothing, so the application is still untouched.
    assert history_rows(application_id) == []
    outcome = reconciliation.confirm_review(reconciliation.link_for(evidence_id)['id'])
    assert outcome['applied']
    settled = [(row.source_category, row.new_state)
               for row in history_rows(application_id)]
    assert settled == [(states.SOURCE_LEGACY_MIGRATION, states.DISCOVERED),
                       (states.SOURCE_USER_CONFIRMED_GMAIL, states.APPLIED)]
    # Once resolved it is no longer revisited.
    summary = reconciliation.reconcile_pending()
    assert summary['revisited'] == 0 and summary['considered'] == 0
    assert [(row.source_category, row.new_state)
            for row in history_rows(application_id)] == settled


def test_an_attached_review_item_is_not_revisited_underneath_the_user():
    """A MEDIUM item already proposing a target must not have that target
    swapped by a later run."""
    application_id, _ = make_application()
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    assert result.application_id == application_id
    summary = reconciliation.reconcile_pending()
    assert summary['revisited'] == 0
    assert reconciliation.link_for(evidence_id)['application_id'] == application_id


def test_low_evidence_is_still_never_queued_after_the_change():
    application_id, _ = make_application()
    force_state(application_id, states.SAVED)
    evidence_id = make_evidence(confidence='LOW')
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_NO_ACTION
    assert result.reason_code == reconciliation.REASON_LOW_CONFIDENCE
    assert reconciliation.needs_review()['count'] == 0
    assert current_state(application_id) == states.SAVED
    # And it is not revisited either, however the records change.
    make_application(company='Northwind Analytics')
    summary = reconciliation.reconcile_pending()
    assert summary['revisited'] == 0
    assert reconciliation.needs_review()['count'] == 0


def test_rejected_review_items_are_not_revisited():
    evidence_id = make_evidence(confidence='MEDIUM')
    result = reconcile(evidence_id)
    assert reconciliation.reject_review(result.link_id)['ok']
    make_application()
    summary = reconciliation.reconcile_pending()
    assert summary['revisited'] == 0
    assert reconciliation.link_for(evidence_id)['decision'] == (
        reconciliation.DECISION_USER_REJECTED)


# ---------------------------------------------------------------------------
# Remediation: summaries and histories are complete and order-independent
# ---------------------------------------------------------------------------
def make_legacy_application(*, company='Contoso Robotics', stage='APPLIED',
                            status='APPLIED'):
    """A pre-#46 application: legacy columns only, no canonical state row."""
    application_id, _ = make_application(company=company, status=status,
                                         stage=stage)
    with Session.begin() as db:
        db.execute(delete(states.ApplicationStateTransition).where(
            states.ApplicationStateTransition.application_id == application_id))
        db.execute(delete(states.ApplicationStateRecord).where(
            states.ApplicationStateRecord.application_id == application_id))
    assert current_state(application_id) is None, 'starts uninitialized'
    return application_id


def test_summary_counts_legacy_applications_before_any_detail_read():
    first = make_legacy_application(company='Contoso Robotics')
    second = make_legacy_application(company='Fabrikam Systems', stage='SHORTLISTED',
                                     status='READY_TO_APPLY')
    summary = states.state_summary()
    assert summary['applications_total'] == 2
    assert summary['total'] == 2
    assert summary['pending_initialization'] == 0
    assert summary['complete'] is True
    assert summary['states'][states.APPLIED] == 1
    assert summary['states'][states.SAVED] == 1
    # And it did not depend on reading either detail view first.
    assert current_state(first) == states.APPLIED
    assert current_state(second) == states.SAVED


def test_summary_is_stable_across_repeated_reads():
    make_legacy_application()
    make_legacy_application(company='Fabrikam Systems')
    first = states.state_summary()
    for _ in range(3):
        assert states.state_summary()['states'] == first['states']
        assert states.state_summary()['total'] == first['total']
    with Session() as db:
        assert len(db.scalars(select(states.ApplicationStateRecord)).all()) == 2
        assert len(db.scalars(select(states.ApplicationStateTransition)).all()) == 2


def test_history_of_a_legacy_application_needs_no_prior_detail_read():
    application_id = make_legacy_application()
    history = states.transition_history(application_id)
    assert len(history) == 1
    assert history[0]['source_category'] == states.SOURCE_LEGACY_MIGRATION
    assert history[0]['new_state'] == states.APPLIED
    # Repeated reads are idempotent, not cumulative.
    for _ in range(3):
        assert len(states.transition_history(application_id)) == 1


def test_detail_read_after_summary_reports_the_same_state():
    application_id = make_legacy_application()
    summary = states.state_summary()
    detail = states.state_of(application_id)
    assert detail['state']['current_state'] == states.APPLIED
    assert states.state_summary()['states'] == summary['states']
    assert len(detail['history']) == 1


def test_a_nonexistent_application_stays_distinguishable():
    existing = make_legacy_application()
    assert states.transition_history(existing) is not None
    assert states.transition_history(999_999) is None
    assert states.state_of(999_999) is None
    # An existing-but-uninitialized application is NOT treated as missing.
    other = make_legacy_application(company='Fabrikam Systems')
    assert states.transition_history(other) == states.transition_history(other)
    assert len(states.transition_history(other)) == 1


def test_backfill_is_idempotent_and_reports_what_it_did():
    make_legacy_application()
    make_legacy_application(company='Fabrikam Systems')
    assert states.uninitialized_count() == 2
    assert states.ensure_all_states() == 2
    assert states.uninitialized_count() == 0
    assert states.ensure_all_states() == 0
    with Session() as db:
        assert len(db.scalars(select(states.ApplicationStateTransition)).all()) == 2


def test_backfill_never_attributes_a_user_action_to_migration():
    """It only ever runs for applications no user action has touched."""
    job_id = make_untracked_job()
    status_action(job_id, 'APPLIED')
    with Session() as db:
        application = db.scalar(select(Application).where(
            Application.job_id == job_id))
    before = [(row.sequence, row.source_category) for row in history_rows(application.id)]
    assert states.ensure_all_states() == 0
    assert [(row.sequence, row.source_category)
            for row in history_rows(application.id)] == before
    assert any(source == states.SOURCE_USER_ACTION for _, source in before)


def test_summary_reports_incompleteness_rather_than_a_short_total(monkeypatch):
    """If more applications exist than one call initializes, the reader is
    told the breakdown is partial instead of being given a wrong total."""
    make_legacy_application()
    make_legacy_application(company='Fabrikam Systems')
    monkeypatch.setattr(states, 'MAX_BACKFILL', 1)
    summary = states.state_summary()
    assert summary['applications_total'] == 2
    assert summary['pending_initialization'] == 1
    assert summary['complete'] is False
    assert summary['total'] == 1


def test_history_api_distinguishes_missing_from_uninitialized():
    from fastapi.testclient import TestClient
    from backend.main import app
    application_id = make_legacy_application()
    with TestClient(app) as client:
        found = client.get(f'/api/applications/{application_id}/state/history')
        assert found.status_code == 200
        assert len(found.json()['history']) == 1
        assert client.get('/api/applications/999999/state/history').status_code == 404
        assert client.get('/api/applications/999999/state').status_code == 404


def test_summary_api_is_complete_without_any_prior_detail_read():
    from fastapi.testclient import TestClient
    from backend.main import app
    make_legacy_application()
    make_legacy_application(company='Fabrikam Systems')
    with TestClient(app) as client:
        summary = client.get('/api/applications/state/summary').json()
    assert summary['total'] == 2
    assert summary['applications_total'] == 2
    assert summary['complete'] is True


# ---------------------------------------------------------------------------
# Remediation: `limit` bounds the whole reconciliation run
# ---------------------------------------------------------------------------
def make_unresolved_evidence(index, *, confidence='MEDIUM'):
    """Evidence reconciled once with no candidate: an unresolved, unattached
    NEEDS_REVIEW item."""
    evidence_id = make_evidence(confidence=confidence,
                                company=f'Unaffiliated Holdings {index}',
                                message_id=f'fictional-unresolved-{index}',
                                url='')
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_NEEDS_REVIEW
    assert result.application_id is None
    return evidence_id


def make_pending_evidence(index, *, confidence='MEDIUM'):
    """Evidence that has never been reconciled at all."""
    return make_evidence(confidence=confidence,
                         company=f'Untouched Holdings {index}',
                         message_id=f'fictional-pending-{index}', url='')


def queue_sizes():
    with Session() as db:
        pending = db.scalars(
            select(sync.GmailConfirmation.id)
            .outerjoin(reconciliation.GmailApplicationLink,
                       reconciliation.GmailApplicationLink.gmail_confirmation_id
                       == sync.GmailConfirmation.id)
            .where(reconciliation.GmailApplicationLink.id.is_(None))).all()
        unresolved = db.scalars(
            select(reconciliation.GmailApplicationLink.gmail_confirmation_id)
            .where(reconciliation.GmailApplicationLink.decision
                   == reconciliation.DECISION_NEEDS_REVIEW,
                   reconciliation.GmailApplicationLink.application_id.is_(None))).all()
    return list(pending), list(unresolved)


def test_two_pending_plus_two_unresolved_with_limit_two_process_two_total():
    """The reviewed defect: each queue applied the limit independently, so a
    run could do twice the requested work."""
    make_unresolved_evidence(1)
    make_unresolved_evidence(2)
    make_pending_evidence(3)
    make_pending_evidence(4)
    assert [len(part) for part in queue_sizes()] == [2, 2]

    summary = reconciliation.reconcile_pending(limit=2)
    total = summary['considered'] + summary['revisited']
    assert total <= 2, f'requested 2, processed {total}'
    assert total == 2
    assert summary['processed'] == total
    assert summary['limit'] == 2
    # Round-robin: both queues advanced, neither monopolized the budget.
    assert summary['considered'] == 1
    assert summary['revisited'] == 1


@pytest.mark.parametrize('requested', [1, 2, 3, 4, 5, 8])
def test_the_total_processed_never_exceeds_the_requested_limit(requested):
    for index in range(1, 5):
        make_unresolved_evidence(index)
    for index in range(5, 9):
        make_pending_evidence(index)
    summary = reconciliation.reconcile_pending(limit=requested)
    total = summary['considered'] + summary['revisited']
    assert total <= requested, f'requested {requested}, processed {total}'
    assert summary['processed'] == total
    assert summary['limit'] == requested


def test_limit_of_one_processes_exactly_one_eligible_item():
    make_unresolved_evidence(1)
    make_pending_evidence(2)
    summary = reconciliation.reconcile_pending(limit=1)
    assert summary['considered'] + summary['revisited'] == 1
    assert summary['processed'] == 1


def test_limit_of_one_still_processes_when_only_one_queue_has_work():
    """Spare capacity is not wasted on an empty queue."""
    make_unresolved_evidence(1)
    assert queue_sizes()[0] == []
    summary = reconciliation.reconcile_pending(limit=1)
    assert summary['revisited'] == 1 and summary['considered'] == 0
    assert summary['processed'] == 1


def test_an_empty_queue_yields_its_whole_share_to_the_other():
    for index in range(1, 5):
        make_pending_evidence(index)
    summary = reconciliation.reconcile_pending(limit=4)
    assert summary['considered'] == 4 and summary['revisited'] == 0
    assert summary['processed'] == 4


def test_the_default_limit_never_processes_more_than_max_run_evidence(monkeypatch):
    monkeypatch.setattr(reconciliation, 'MAX_RUN_EVIDENCE', 3)
    for index in range(1, 6):
        make_unresolved_evidence(index)
    for index in range(6, 11):
        make_pending_evidence(index)
    # Default argument, and an explicit request far above the ceiling.
    for summary in (reconciliation.reconcile_pending(),
                    reconciliation.reconcile_pending(limit=10_000)):
        total = summary['considered'] + summary['revisited']
        assert total <= reconciliation.MAX_RUN_EVIDENCE, total
        assert summary['limit'] == reconciliation.MAX_RUN_EVIDENCE


def test_both_queues_make_progress_across_repeated_runs():
    """Neither queue starves the other: a backlog on one side still leaves
    room for the other in every run."""
    for index in range(1, 4):
        make_unresolved_evidence(index)
    for index in range(4, 7):
        make_pending_evidence(index)
    seen_considered = seen_revisited = 0
    for _ in range(3):
        summary = reconciliation.reconcile_pending(limit=2)
        assert summary['considered'] + summary['revisited'] <= 2
        seen_considered += summary['considered']
        seen_revisited += summary['revisited']
    assert seen_considered > 0, 'new confirmations never progressed'
    assert seen_revisited > 0, 'unresolved items never progressed'
    # The pending queue drains; nothing is left permanently unreconciled.
    assert queue_sizes()[0] == []


def test_a_sustained_stream_of_new_confirmations_does_not_starve_revisits():
    make_unresolved_evidence(1)
    make_unresolved_evidence(2)
    revisited = 0
    for round_number in range(3):
        # New evidence keeps arriving between runs.
        make_pending_evidence(10 + round_number * 2)
        make_pending_evidence(11 + round_number * 2)
        summary = reconciliation.reconcile_pending(limit=2)
        assert summary['considered'] + summary['revisited'] <= 2
        revisited += summary['revisited']
    assert revisited > 0, 'unresolved items were starved by new confirmations'


def test_a_large_unresolved_backlog_does_not_block_new_confirmations():
    for index in range(1, 9):
        make_unresolved_evidence(index)
    make_pending_evidence(20)
    summary = reconciliation.reconcile_pending(limit=2)
    assert summary['considered'] + summary['revisited'] <= 2
    assert summary['considered'] == 1, 'new confirmation was blocked'


def test_no_confirmation_is_processed_through_both_paths_in_one_run():
    """A review item this run creates must not also be revisited by it."""
    make_pending_evidence(1)
    make_pending_evidence(2)
    summary = reconciliation.reconcile_pending(limit=10)
    assert summary['considered'] == 2
    assert summary['revisited'] == 0
    assert summary['processed'] == 2


def test_bounded_runs_never_duplicate_links_transitions_or_applications():
    for index in range(1, 4):
        make_unresolved_evidence(index)
    for index in range(4, 7):
        make_pending_evidence(index)
    application_id, _ = make_application()
    with Session() as db:
        confirmations_before = len(db.scalars(select(sync.GmailConfirmation)).all())
    for _ in range(6):
        reconciliation.reconcile_pending(limit=2)
    with Session() as db:
        links = db.scalars(select(reconciliation.GmailApplicationLink)).all()
        assert len(links) == confirmations_before
        assert len({link.gmail_confirmation_id for link in links}) == len(links)
        assert len(db.scalars(select(sync.GmailConfirmation)).all()) == confirmations_before
        assert len(db.scalars(select(Application)).all()) == 1
        transitions = db.scalars(select(states.ApplicationStateTransition).where(
            states.ApplicationStateTransition.application_id == application_id)).all()
    assert len({row.sequence for row in transitions}) == len(transitions)
    assert reconciliation.needs_review()['count'] == len(
        [link for link in links
         if link.decision == reconciliation.DECISION_NEEDS_REVIEW])


def test_low_evidence_is_unaffected_by_the_shared_budget():
    application_id, _ = make_application()
    force_state(application_id, states.SAVED)
    low = make_evidence(confidence='LOW', message_id='fictional-low-1')
    make_unresolved_evidence(2)
    summary = reconciliation.reconcile_pending(limit=4)
    assert summary['considered'] + summary['revisited'] <= 4
    assert reconciliation.link_for(low)['decision'] == reconciliation.DECISION_NO_ACTION
    assert reconciliation.link_for(low)['reason_code'] == (
        reconciliation.REASON_LOW_CONFIDENCE)
    assert current_state(application_id) == states.SAVED
    assert low not in [item['gmail_confirmation_id']
                       for item in reconciliation.needs_review()['items']]
    # LOW is never revisited either, whatever the budget.
    for _ in range(3):
        assert all(item['gmail_confirmation_id'] != low
                   for item in reconciliation.needs_review()['items'])
        reconciliation.reconcile_pending(limit=4)


def test_resolved_rejected_and_attached_items_are_not_revisited():
    attached_target, _ = make_application()
    attached = make_evidence(confidence='MEDIUM', message_id='fictional-attached')
    assert reconcile(attached).application_id == attached_target

    confirmed_target, _ = make_application(company='Contoso Robotics')
    confirmed = make_evidence(confidence='MEDIUM', company='Contoso Robotics',
                              message_id='fictional-confirmed', url='')
    confirmed_result = reconcile(confirmed)
    assert reconciliation.confirm_review(confirmed_result.link_id)['ok']

    rejected = make_unresolved_evidence(9)
    rejected_link = reconciliation.link_for(rejected)['id']
    assert reconciliation.reject_review(rejected_link)['ok']

    summary = reconciliation.reconcile_pending(limit=reconciliation.MAX_RUN_EVIDENCE)
    assert summary['revisited'] == 0, 'a settled item was revisited'
    assert summary['considered'] == 0
    assert reconciliation.link_for(attached)['application_id'] == attached_target
    assert reconciliation.link_for(confirmed)['decision'] == (
        reconciliation.DECISION_USER_CONFIRMED)
    assert reconciliation.link_for(rejected)['decision'] == (
        reconciliation.DECISION_USER_REJECTED)


def test_the_four_earlier_defects_remain_fixed_under_a_bounded_run():
    """One consolidated guard so the bound fix cannot silently regress them."""
    # 1. Contradictory requisition URLs still never auto-link.
    conflicted, _ = make_application(
        apply_url='https://boards.greenhouse.io/northwind/jobs/111')
    conflict_evidence = make_evidence(
        url='https://boards.greenhouse.io/northwind/jobs/999',
        message_id='fictional-bound-conflict')
    # 3. Unmatched MEDIUM evidence is still queued, not consumed.
    unmatched = make_evidence(confidence='MEDIUM', company='Unaffiliated Holdings 1',
                              message_id='fictional-bound-unmatched', url='')
    summary = reconciliation.reconcile_pending(limit=reconciliation.MAX_RUN_EVIDENCE)
    assert summary['considered'] + summary['revisited'] == summary['processed']
    assert reconciliation.link_for(conflict_evidence)['reason_code'] == (
        reconciliation.REASON_URL_CONFLICT)
    assert current_state(conflicted) != states.APPLIED
    unmatched_link = reconciliation.link_for(unmatched)
    assert unmatched_link['decision'] == reconciliation.DECISION_NEEDS_REVIEW
    assert unmatched_link['application_id'] is None

    # 2. A first manual status change is still a USER_ACTION.
    job_id = make_untracked_job(company='Fabrikam Systems')
    status_action(job_id, 'APPLIED')
    with Session() as db:
        application = db.scalar(select(Application).where(
            Application.job_id == job_id))
    rows = history_rows(application.id)
    assert rows[0].source_category == states.SOURCE_LEGACY_MIGRATION
    assert rows[-1].source_category == states.SOURCE_USER_ACTION

    # 4. Summaries still account for every application without a detail read.
    legacy = make_legacy_application(company='Tailspin Toys')
    overview = states.state_summary()
    assert overview['complete'] is True
    assert overview['total'] == overview['applications_total']
    assert states.transition_history(legacy) is not None
    assert states.transition_history(999_999) is None


def test_reconcile_api_honours_the_requested_batch_size():
    """The caller-visible batch-size contract, through the real route."""
    from fastapi.testclient import TestClient
    from backend.main import app
    make_unresolved_evidence(1)
    make_unresolved_evidence(2)
    make_pending_evidence(3)
    make_pending_evidence(4)
    with TestClient(app) as client:
        response = client.post('/api/applications/state/reconcile',
                               json={'limit': 2})
        assert response.status_code == 200
        body = response.json()
    total = body['considered'] + body['revisited']
    assert total <= 2, f'API requested 2, processed {total}'
    assert body['processed'] == total
    assert body['limit'] == 2


def test_reconcile_api_still_rejects_out_of_range_batch_sizes():
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as client:
        assert client.post('/api/applications/state/reconcile',
                           json={'limit': 0}).status_code == 400
        assert client.post('/api/applications/state/reconcile',
                           json={'limit': reconciliation.MAX_RUN_EVIDENCE + 1}
                           ).status_code == 400
        default = client.post('/api/applications/state/reconcile', json={})
        assert default.status_code == 200
        assert default.json()['limit'] == reconciliation.MAX_RUN_EVIDENCE

"""#47 Progress projection: every displayed figure against fictional records.

Each test builds a small fictional workspace directly in the isolated test
database, computes the expected figure independently from those records,
and compares it with what `backend.progress` reports. No live mailbox, no
real employer and no real application is involved.

Dates are anchored to a Wednesday two weeks before the real current date,
in Asia/Dubai, so every fixture lies in the past (#46 clamps future
occurrences) and inside the 90-day telemetry retention window whenever the
suite runs.
"""
import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, func, select

from backend import application_reconciliation as reconciliation
from backend import application_state as states
from backend import discovery_telemetry as telemetry
from backend import gmail_accounts as accounts
from backend import gmail_confirmations as parsers
from backend import gmail_sync as sync
from backend import progress
from backend.models import (Application, ApplicationEvent, AutomationRun, FollowUp,
                            Job, JobObservation, Session)
from backend.normalization import employer_key

DUBAI = ZoneInfo('Asia/Dubai')
UTC = timezone.utc
_today = datetime.now(UTC).astimezone(DUBAI).date()
#: A Monday two weeks ago (Dubai calendar).
MONDAY = _today - timedelta(days=_today.weekday()) - timedelta(days=14)
#: Wednesday 14:00 Dubai of that week: the reporting clock.
CLOCK = datetime.combine(MONDAY + timedelta(days=2), time(14, 0), tzinfo=DUBAI).astimezone(UTC)
WEEK_START = datetime.combine(MONDAY, time(0), tzinfo=DUBAI).astimezone(UTC)


def dubai(day_offset, hour=10, minute=0, second=0):
    """A UTC ISO timestamp `day_offset` Dubai days after MONDAY at hour:minute."""
    moment = datetime.combine(MONDAY + timedelta(days=day_offset),
                              time(hour, minute, second), tzinfo=DUBAI)
    return moment.astimezone(UTC).isoformat()


COMPANY = 'Northwind Analytics'
ROLE = 'SOC Analyst'
URL = 'https://boards.greenhouse.io/northwind/jobs/4821'


# ---------------------------------------------------------------------------
# Fixtures and fictional records
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_state():
    from backend.models import initialize
    initialize()
    accounts.initialize_gmail_schema()
    sync.initialize_sync_schema()
    reconciliation.initialize_reconciliation_schema()
    with Session.begin() as db:
        db.execute(delete(reconciliation.GmailApplicationLink))
        scheduler = db.get(reconciliation.ReconciliationScheduler, 1)
        if scheduler is not None:
            scheduler.attempt_sequence = 0
            scheduler.next_queue = reconciliation.QUEUE_PENDING
        db.execute(delete(states.ApplicationStateTransition))
        db.execute(delete(states.ApplicationStateRecord))
        db.execute(delete(sync.GmailConfirmation))
        db.execute(delete(accounts.GmailAccount))
        db.execute(delete(ApplicationEvent))
        db.execute(delete(FollowUp))
        db.execute(delete(Application))
        db.execute(delete(JobObservation))
        db.execute(delete(Job))
        db.execute(delete(AutomationRun))
    yield


def make_job(*, company=COMPANY, title=ROLE, source='Greenhouse', url=URL, status='FOUND'):
    with Session.begin() as db:
        job = Job(company=company, title=title, source=source, apply_url=url,
                  job_url=url, normalized_employer_key=employer_key(company) or '',
                  date_found=dubai(-20), status=status)
        db.add(job)
        db.flush()
        return job.id


def make_application(*, company=COMPANY, title=ROLE, source='Greenhouse', url=URL,
                     applied_date='', status='FOUND', stage=None, tracking=None):
    job_id = make_job(company=company, title=title, source=source, url=url)
    with Session.begin() as db:
        details = dict(tracking or {})
        if stage:
            details['stage'] = stage
        application = Application(job_id=job_id, status=status,
                                  applied_date=applied_date, tracking=details)
        db.add(application)
        db.flush()
        return application.id


def assert_user(application_id, state, occurred_at='', source=states.SOURCE_USER_ACTION):
    """One user assertion through the state service, exactly as the UI paths do."""
    with Session.begin() as db:
        application = db.get(Application, application_id)
        states.ensure_state(db, application)
        decision = states.assert_state(db, application, state, source_category=source,
                                       asserted_by='USER', occurred_at=occurred_at)
    return decision


def make_evidence(*, confidence='MEDIUM', company=COMPANY, role=ROLE, url=URL,
                  received_at=None, message_id='fictional-message-1',
                  account_id='fictional-account-id'):
    with Session.begin() as db:
        row = sync.GmailConfirmation(
            account_slot='PRIMARY', gmail_account_id=account_id,
            gmail_message_id=message_id, sender='noreply@greenhouse.io',
            subject='FICTIONAL-SUBJECT-SENTINEL Thank you for applying to ' + company,
            received_at=received_at or dubai(1, 9, 4), detected_company=company,
            detected_role=role, detected_state=parsers.APPLICATION_CONFIRMED,
            confidence=confidence, parser_id='greenhouse-confirmation-v1',
            evidence_signals=['SENDER_DOMAIN', 'SUBJECT_STRUCTURE'],
            application_url=url)
        db.add(row)
        db.flush()
        return row.id


def reconcile(evidence_id):
    with Session.begin() as db:
        row = db.get(sync.GmailConfirmation, evidence_id)
        return reconciliation.reconcile_confirmation(db, row)


def report(period=progress.THIS_WEEK):
    return progress.progress_report(period, clock=CLOCK)


def current(application_id):
    with Session() as db:
        record = db.scalar(select(states.ApplicationStateRecord).where(
            states.ApplicationStateRecord.application_id == application_id))
        return record.current_state if record else None


def run_payload(run_id, started_at, sources):
    """A real `discovery-telemetry-v1` payload built by the production class."""
    run = telemetry.RunTelemetry(run_id=run_id, trigger='MANUAL', started_at=started_at)
    for source in sources:
        run.sources.append(source)

    class NoEngagement:
        def execute(self, *args, **kwargs):
            return []
    return run.finalize(NoEngagement(), 'COMPLETED', finished_at=started_at,
                        duration_seconds=1.0)


COMPLETE = {'completion': 'COMPLETE', 'health': 'HEALTHY', 'completion_reason': None,
            'metrics': None, 'error': None}
PARTIAL = {'completion': 'PARTIAL', 'health': 'PARTIAL',
           'completion_reason': 'DETAIL_BUDGET_EXHAUSTED', 'metrics': None, 'error': None}
FAILED = {'completion': 'FAILED', 'health': 'UNAVAILABLE', 'completion_reason': 'TRANSPORT_ERROR',
          'metrics': None, 'error': {'code': 'READ_TIMEOUT', 'message': 'private diagnostic'}}


def source_attempt(source_id, new_job_ids=(), seen_job_ids=(), fetch=COMPLETE):
    attempt = telemetry.SourceAttempt(source_id, f'Fictional board {source_id}', 'greenhouse')
    attempt.record_fetch(fetch)
    if fetch is FAILED:
        attempt.failed(fetch)
        return attempt
    decision = {'hard': [], 'soft': [], 'excluded': False, 'location_compatible': True,
                'eligibility': {'state': 'ELIGIBLE', 'scope': 'synthetic', 'evidence': []}}
    for job_id, created in [(j, True) for j in new_job_ids] + [(j, False) for j in seen_job_ids]:
        attempt.observed()
        attempt.persisted(job_id, created=created)
        attempt.assessed(job_id, decision)
    return attempt


def add_run(created_at, sources=None, *, status='COMPLETED', report=None):
    with Session.begin() as db:
        run = AutomationRun(task='discover', status=status, report={})
        db.add(run)
        db.flush()
        run.created_at = created_at
        if report is not None:
            run.report = report
        elif sources is not None:
            run.report = {telemetry.REPORT_KEY: run_payload(run.id, created_at, sources)}
        return run.id


def snapshot():
    """Row counts and the latest write time of every table #47 reads."""
    tables = (Application, Job, FollowUp, ApplicationEvent, AutomationRun,
              states.ApplicationStateRecord, states.ApplicationStateTransition,
              sync.GmailConfirmation, reconciliation.GmailApplicationLink,
              reconciliation.ReconciliationScheduler)
    with Session() as db:
        return {table.__tablename__: (db.scalar(select(func.count()).select_from(table)),
                                      db.scalar(select(func.max(table.updated_at))))
                for table in tables}


# ---------------------------------------------------------------------------
# Period windows
# ---------------------------------------------------------------------------
def test_periods_are_half_open_asia_dubai_calendar_windows():
    week = progress.period_window(progress.THIS_WEEK, CLOCK)
    assert week['start'] == datetime.combine(MONDAY, time(0), tzinfo=DUBAI).isoformat()
    assert week['end'] == datetime.combine(MONDAY + timedelta(days=7), time(0),
                                           tzinfo=DUBAI).isoformat()
    assert week['first_day'] == MONDAY.isoformat()
    assert week['last_day'] == (MONDAY + timedelta(days=6)).isoformat()
    assert week['includes_today'] is True

    last = progress.period_window(progress.LAST_WEEK, CLOCK)
    assert last['end'] == week['start'] and last['includes_today'] is False

    today = CLOCK.astimezone(DUBAI).date()
    thirty = progress.period_window(progress.LAST_30_DAYS, CLOCK)
    assert thirty['first_day'] == (today - timedelta(days=29)).isoformat()
    assert thirty['last_day'] == today.isoformat()

    ninety = progress.period_window(progress.LAST_90_DAYS, CLOCK)
    assert ninety['_start'] > telemetry.retention_cutoff(CLOCK)

    with pytest.raises(ValueError):
        progress.period_window('forever', CLOCK)


# ---------------------------------------------------------------------------
# Absent data is reported as absent, never as zero
# ---------------------------------------------------------------------------
def test_empty_workspace_reports_absence_rather_than_zero():
    result = report()
    assert result['discovery']['status'] == progress.STATUS_NO_SCANS
    assert result['discovery']['new_relevant'] is None
    assert result['gmail']['status'] == progress.STATUS_NOT_CONNECTED
    assert result['gmail']['messages'] is None
    assert result['gmail']['applications'] is None
    # Application history is complete and simply empty: zero is the truth.
    assert result['applications']['submitted']['count'] == 0
    assert result['applications']['current']['complete'] is True
    # An empty review queue is an exact count over the whole table.
    assert result['review'] == {'status': 'OK', 'total': 0, 'excluded_other_confidence': 0}
    for key in ('interview', 'offer', 'rejected', 'replies'):
        assert result['outcomes'][key] == {'count': 0, 'of': 0, 'rate': None,
                                           'enough_data': False}


# ---------------------------------------------------------------------------
# Applications: event history versus current state
# ---------------------------------------------------------------------------
def test_dubai_week_boundary_places_events_in_the_right_week():
    sunday_night = make_application(company='Contoso Security', url='')
    monday_morning = make_application(company='Fabrikam Cyber', url='')
    # 23:59:59 on the Sunday before MONDAY, Dubai time -- which is still the
    # same *UTC* date as the next event. A UTC-date window would get this wrong.
    assert_user(sunday_night, states.APPLIED, dubai(-1, 23, 59, 59))
    assert_user(monday_morning, states.APPLIED, dubai(0, 0, 0, 0))
    assert dubai(-1, 23, 59, 59)[:10] == dubai(0, 0, 0, 0)[:10]

    this_week = report()['applications']['submitted']
    last_week = report(progress.LAST_WEEK)['applications']['submitted']
    assert [item['application_id'] for item in this_week['items']] == [monday_morning]
    assert [item['application_id'] for item in last_week['items']] == [sunday_night]


def test_submission_is_counted_once_across_user_and_gmail_sources():
    manual = make_application()
    assert_user(manual, states.APPLIED, dubai(1, 9, 0))
    # The same application's HIGH confirmation arrives afterwards. #46 refuses
    # the automated transition, so it must not become a second submission.
    manual_evidence = make_evidence(confidence='HIGH', received_at=dubai(1, 9, 4),
                                    message_id='fictional-manual')
    assert reconcile(manual_evidence).decision == reconciliation.DECISION_NO_ACTION

    automatic = make_application(company='Contoso Security', title='Detection Engineer',
                                 url='https://boards.greenhouse.io/contoso/jobs/77',
                                 applied_date=dubai(2, 8, 0))
    auto_evidence = make_evidence(confidence='HIGH', company='Contoso Security',
                                  role='Detection Engineer',
                                  url='https://boards.greenhouse.io/contoso/jobs/77',
                                  received_at=dubai(2, 8, 5), message_id='fictional-auto')
    assert reconcile(auto_evidence).decision == reconciliation.DECISION_LINKED

    result = report()
    submitted = result['applications']['submitted']
    assert submitted['count'] == 2
    assert submitted['by_source'] == {states.SOURCE_USER_ACTION: 1,
                                      states.SOURCE_GMAIL_PARSER: 1}
    assert {item['application_id'] for item in submitted['items']} == {manual, automatic}

    gmail = result['gmail']
    assert gmail['messages'] == 2
    assert gmail['applications'] == 1  # only the evidence that was linked
    assert gmail['by_outcome'][reconciliation.DECISION_LINKED] == 1
    assert gmail['by_outcome'][reconciliation.DECISION_NO_ACTION] == 1
    assert [item['application_id'] for item in gmail['items']] == [automatic]
    assert gmail['items'][0]['advanced_state'] is True


def test_reached_applied_in_period_differs_from_currently_applied():
    moved_on = make_application(company='Contoso Security', url='')
    assert_user(moved_on, states.APPLIED, dubai(0, 11))
    assert_user(moved_on, states.INTERVIEW, dubai(1, 15))
    still_applied = make_application(company='Fabrikam Cyber', url='')
    assert_user(still_applied, states.APPLIED, dubai(-3, 11))  # last week

    result = report()
    apps = result['applications']
    assert apps['submitted']['count'] == 1  # reached APPLIED this week
    assert apps['current']['states'][states.APPLIED] == 1  # is at APPLIED now
    assert apps['current']['states'][states.INTERVIEW] == 1
    assert apps['stage_changes']['by_state'][states.INTERVIEW] == 1
    assert apps['stage_changes']['items'][0]['previous_state'] == states.APPLIED


def test_bootstrap_rows_are_dated_only_by_a_recorded_applied_date():
    dated = make_application(company='Contoso Security', url='', status='APPLIED',
                             applied_date=dubai(1, 12))
    undated = make_application(company='Fabrikam Cyber', url='', status='APPLIED')
    interview = make_application(company='Litware Defence', url='', stage='INTERVIEW')

    result = report()
    submitted = result['applications']['submitted']
    assert [item['application_id'] for item in submitted['items']] == [dated]
    assert submitted['by_source'] == {states.SOURCE_LEGACY_MIGRATION: 1}
    assert submitted['submission_date_not_recorded'] == 2  # undated + interview
    # A bootstrap is not a stage event: its time is when ASTRA first knew.
    assert result['applications']['stage_changes']['count'] == 0
    assert current(undated) == states.APPLIED and current(interview) == states.INTERVIEW


def test_a_later_stage_without_a_submission_date_is_not_a_dated_submission():
    application = make_application(url='')
    decision = assert_user(application, states.INTERVIEW, dubai(1, 10))
    assert decision.applied

    apps = report()['applications']
    assert apps['submitted']['count'] == 0
    assert apps['submitted']['submission_date_not_recorded'] == 1
    assert apps['stage_changes']['by_state'][states.INTERVIEW] == 1
    assert report()['outcomes']['submitted_total'] == 1


# ---------------------------------------------------------------------------
# Discovery telemetry
# ---------------------------------------------------------------------------
def test_new_relevant_jobs_use_run_level_cross_source_deduplication():
    # Two sources observed the same brand-new canonical job 501. Summing
    # per-source NEW would report 2; the run-level union is 1.
    first = add_run(dubai(0, 9), [source_attempt(1, new_job_ids=[501]),
                                  source_attempt(2, new_job_ids=[501])])
    second = add_run(dubai(2, 9), [source_attempt(1, new_job_ids=[601, 602],
                                                  seen_job_ids=[501])])
    add_run(dubai(-2, 9), [source_attempt(1, new_job_ids=[401])])  # last week

    with Session() as db:
        payload = db.get(AutomationRun, first).report[telemetry.REPORT_KEY]
    assert payload['funnel'][telemetry.NEW] == 1
    assert sum(s['funnel'][telemetry.NEW] for s in payload['sources']) == 2

    discovery = report()['discovery']
    assert discovery['status'] == progress.STATUS_OK
    assert discovery['new_relevant'] == 1 + 2
    assert discovery['lower_bound'] is False
    assert [run['run_id'] for run in discovery['runs']] == [second, first]
    assert report(progress.LAST_WEEK)['discovery']['new_relevant'] == 1


def test_partial_failed_unavailable_and_running_scans_are_never_zero():
    add_run(dubai(0, 9), [source_attempt(1, new_job_ids=[701]),
                          source_attempt(2, fetch=FAILED)])
    add_run(dubai(1, 9), [source_attempt(1, new_job_ids=[702, 703], fetch=PARTIAL)])
    add_run(dubai(1, 12), report={'discovered': 4, 'sources': []})  # pre-#43 run
    add_run(dubai(2, 9), status='RUNNING')

    discovery = report()['discovery']
    assert discovery['runs_in_period'] == 4
    assert discovery['runs_counted'] == 2
    assert discovery['new_relevant'] == 3
    assert discovery['status'] == progress.STATUS_INCOMPLETE
    assert discovery['lower_bound'] is True
    assert discovery['runs_incomplete'] == 2  # failed source and partial fetch
    assert discovery['runs_unavailable'] == 1
    assert discovery['runs_in_progress'] == 1
    failed_run = [run for run in discovery['runs'] if run['sources_failed']][0]
    assert failed_run['counts_complete'] is False


def test_scans_without_telemetry_are_not_recorded_rather_than_zero():
    add_run(dubai(1, 9), report={'discovered': 4, 'sources': []})
    error = {telemetry.REPORT_KEY: {'schema_version': telemetry.TELEMETRY_SCHEMA_VERSION,
                                    'status': 'TELEMETRY_ERROR', 'funnel': None,
                                    'sources': []}}
    add_run(dubai(1, 10), report=error)
    discovery = report()['discovery']
    assert discovery['status'] == progress.STATUS_NOT_RECORDED
    assert discovery['new_relevant'] is None
    assert discovery['runs_telemetry_error'] == 1
    assert discovery['runs_unavailable'] == 1


def test_scans_outside_retention_are_not_read():
    add_run((datetime.now(UTC) - timedelta(days=91)).isoformat(),
            [source_attempt(1, new_job_ids=[801])])
    assert report(progress.LAST_90_DAYS)['discovery']['status'] == progress.STATUS_NO_SCANS


# ---------------------------------------------------------------------------
# Gmail evidence
# ---------------------------------------------------------------------------
def test_gmail_messages_deduplicate_by_message_and_keep_low_confidence_apart():
    make_application()
    # The same mailbox message stored twice after a reconnect (new evidence
    # namespace), a LOW fallback, an unreconciled MEDIUM, and one from last week.
    make_evidence(message_id='fictional-dup', account_id='fictional-grant-1')
    make_evidence(message_id='fictional-dup', account_id='fictional-grant-2')
    make_evidence(confidence='LOW', message_id='fictional-low')
    make_evidence(message_id='fictional-waiting', company='Contoso Security')
    make_evidence(message_id='fictional-old', received_at=dubai(-1, 23, 59, 59))
    with Session() as db:
        for row in db.scalars(select(sync.GmailConfirmation).where(
                sync.GmailConfirmation.gmail_message_id == 'fictional-dup')):
            reconcile(row.id)

    gmail = report()['gmail']
    assert gmail['status'] == 'OK'
    assert gmail['messages'] == 2  # fictional-dup once, fictional-waiting
    assert gmail['low_confidence_not_used'] == 1
    assert gmail['by_outcome']['NOT_RECONCILED'] == 1
    assert gmail['by_outcome'][reconciliation.DECISION_NEEDS_REVIEW] == 1
    # All-time unmatched HIGH/MEDIUM evidence, whatever the period.
    assert gmail['not_reconciled_total'] == 2  # fictional-waiting and fictional-old
    assert report(progress.LAST_WEEK)['gmail']['messages'] == 1


def test_gmail_coverage_reports_only_what_a_completed_sync_covered():
    assert progress.gmail_coverage()['status'] == progress.STATUS_NOT_CONNECTED
    completed = int((CLOCK - timedelta(days=1)).timestamp())
    with Session.begin() as db:
        db.add(accounts.GmailAccount(slot='PRIMARY', status=accounts.CONNECTED,
                                     sync_state={'version': sync.SYNC_STATE_VERSION,
                                                 'completed_through': completed}))
    coverage = progress.gmail_coverage()
    assert coverage == {'status': 'CONNECTED', 'connected': True, 'sync_state': 'COMPLETE',
                        'checked_through': datetime.fromtimestamp(completed, UTC).isoformat()}
    with Session.begin() as db:
        row = db.scalar(select(accounts.GmailAccount))
        row.sync_state = {'version': sync.SYNC_STATE_VERSION, 'after': completed - 60,
                          'before': completed, 'page_token': None}
    coverage = progress.gmail_coverage()
    assert coverage['sync_state'] == 'INCOMPLETE' and coverage['checked_through'] is None
    # Connected but nothing received yet: a true zero, not "not connected".
    gmail = report()['gmail']
    assert gmail['status'] == 'OK' and gmail['messages'] == 0


# ---------------------------------------------------------------------------
# Needs Review queue and candidates
# ---------------------------------------------------------------------------
def queue_json(**params):
    return progress.review_page(**params)


def test_review_queue_offers_exactly_the_candidates_confirm_would_accept():
    proposed = make_application()
    medium = make_evidence(message_id='fictional-medium')
    assert reconcile(medium).reason_code == reconciliation.REASON_MEDIUM_NEEDS_REVIEW

    page = queue_json()
    [item] = page['items']
    assert item['confidence'] == 'MEDIUM'
    assert item['proposed_application_id'] == proposed
    assert item['default_application_id'] == proposed
    assert [c['application_id'] for c in item['candidates']] == [proposed]
    candidate = item['candidates'][0]
    assert candidate['proposed'] is True and candidate['company'] == COMPANY
    # Strictly read-only: an application nothing has initialized yet has no
    # canonical row, and the projection says so rather than bootstrapping it.
    assert candidate['current_state'] is None
    states.state_summary()  # the existing #46 read-repair
    assert queue_json()['items'][0]['candidates'][0]['current_state'] == states.DISCOVERED
    assert set(candidate['matched_fields']) >= {states.FIELD_COMPANY, states.FIELD_ROLE}
    assert item['platform'] == 'GREENHOUSE'


def test_ambiguous_item_lists_every_confirmable_candidate_without_choosing():
    first = make_application()
    second = make_application()
    unrelated = make_application(company='Contoso Security', url='')
    evidence = make_evidence(message_id='fictional-ambiguous')
    assert reconcile(evidence).reason_code == reconciliation.REASON_AMBIGUOUS

    [item] = queue_json()['items']
    assert item['proposed_application_id'] is None
    assert item['default_application_id'] is None  # the user must choose
    assert sorted(c['application_id'] for c in item['candidates']) == [first, second]

    link_id = item['link_id']
    states.state_summary()
    refused = reconciliation.confirm_review(link_id, application_id=unrelated)
    assert refused == {'ok': False, 'reason_code': reconciliation.REASON_NO_STRONG_MATCH,
                       'link': refused['link']}
    assert reconciliation.confirm_review(link_id)['ok'] is False  # no silent pick
    accepted = reconciliation.confirm_review(link_id, application_id=second)
    assert accepted['ok'] is True and accepted['applied'] is True
    assert current(second) == states.APPLIED and current(first) == states.DISCOVERED


def test_unmatched_high_evidence_stays_visible_and_low_never_enters():
    high = make_evidence(confidence='HIGH', company='Tailspin Security',
                         message_id='fictional-high-unmatched')
    low = make_evidence(confidence='LOW', company='Tailspin Security',
                        message_id='fictional-low')
    assert reconcile(high).reason_code == reconciliation.REASON_NO_CANDIDATES
    assert reconcile(low).decision == reconciliation.DECISION_NO_ACTION

    page = queue_json()
    assert page['total'] == 1 and page['excluded_other_confidence'] == 0
    [item] = page['items']
    assert item['confidence'] == 'HIGH'
    assert item['candidates'] == [] and item['default_application_id'] is None


def test_review_total_is_the_whole_queue_not_the_page():
    make_application()
    make_application()
    for index in range(3):
        reconcile(make_evidence(message_id=f'fictional-{index}'))
    first = queue_json(limit=2)
    assert first['total'] == 3 and len(first['items']) == 2
    rest = queue_json(limit=2, offset=2)
    assert rest['total'] == 3 and len(rest['items']) == 1
    ids = [item['link_id'] for item in first['items'] + rest['items']]
    assert ids == sorted(ids, reverse=True) and len(set(ids)) == 3
    assert report()['review']['total'] == 3


def test_review_projection_is_read_only_and_minimized():
    make_application()
    reconcile(make_evidence(message_id='fictional-private-id', account_id='fictional-acct'))
    states.state_summary()
    before = snapshot()
    page = queue_json()
    whole = report()
    assert snapshot() == before

    body = json.dumps(page) + json.dumps(whole)
    for forbidden in ('FICTIONAL-SUBJECT-SENTINEL', 'noreply@greenhouse.io',
                      'fictional-private-id', 'fictional-acct', URL, '"subject"',
                      '"sender"', '"gmail_message_id"', '"application_url"'):
        assert forbidden not in body, forbidden


# ---------------------------------------------------------------------------
# Confirm and reject through the existing #46 endpoints
# ---------------------------------------------------------------------------
def test_confirm_and_reject_drive_the_existing_rules_and_the_figures():
    from fastapi.testclient import TestClient
    from backend.main import app

    confirmable = make_application()
    rejectable = make_application(company='Contoso Security', title='Detection Engineer',
                                  url='https://boards.greenhouse.io/contoso/jobs/77')
    later = make_application(company='Litware Defence', title='Threat Analyst',
                             url='https://boards.greenhouse.io/litware/jobs/12')
    assert_user(later, states.INTERVIEW, dubai(0, 16))
    reconcile(make_evidence(message_id='fictional-confirm'))
    reconcile(make_evidence(company='Contoso Security', role='Detection Engineer',
                            url='https://boards.greenhouse.io/contoso/jobs/77',
                            message_id='fictional-reject'))
    reconcile(make_evidence(company='Litware Defence', role='Threat Analyst',
                            url='https://boards.greenhouse.io/litware/jobs/12',
                            message_id='fictional-later'))

    with TestClient(app) as client:
        assert client.get('/api/applications/state/summary').json()['complete'] is True
        page = client.get('/api/progress/needs-review').json()
        assert page['total'] == 3
        by_app = {item['default_application_id']: item for item in page['items']}

        confirm_link = by_app[confirmable]['link_id']
        confirmed = client.post(
            f'/api/applications/state/needs-review/{confirm_link}/confirm',
            json={'application_id': confirmable}).json()
        assert confirmed['ok'] is True and confirmed['applied'] is True
        assert confirmed['state']['previous_state'] == states.DISCOVERED
        assert confirmed['state']['current_state'] == states.APPLIED

        # Repeating a resolution is refused and changes nothing.
        again = client.post(f'/api/applications/state/needs-review/{confirm_link}/confirm',
                            json={'application_id': confirmable}).json()
        assert again['ok'] is False
        assert again['reason_code'] == reconciliation.REASON_LINK_NOT_REVIEWABLE
        assert client.post(f'/api/applications/state/needs-review/{confirm_link}/reject',
                           json={}).json()['ok'] is False

        reject_link = by_app[rejectable]['link_id']
        rejected = client.post(f'/api/applications/state/needs-review/{reject_link}/reject',
                               json={}).json()
        assert rejected == {'ok': True, 'applied': False, 'link': rejected['link']}
        assert current(rejectable) == states.DISCOVERED

        # Confirming evidence for an application already past APPLIED resolves
        # the item without moving the application.
        later_link = by_app[later]['link_id']
        resolved = client.post(f'/api/applications/state/needs-review/{later_link}/confirm',
                               json={'application_id': later}).json()
        assert resolved['ok'] is True and resolved['applied'] is False
        assert resolved['state']['reason_code'] == states.REFUSED_NOT_PERMITTED
        assert resolved['state']['current_state'] == states.INTERVIEW
        assert current(later) == states.INTERVIEW

        after = client.get('/api/progress?period=last_30_days').json()  # real clock
        assert after['review']['total'] == 0
        submitted = after['applications']['submitted']
        assert submitted['by_source'] == {states.SOURCE_USER_CONFIRMED_GMAIL: 1}
        assert [item['application_id'] for item in submitted['items']] == [confirmable]
        outcomes = after['gmail']['by_outcome']
        assert outcomes[reconciliation.DECISION_USER_CONFIRMED] == 2
        assert outcomes[reconciliation.DECISION_USER_REJECTED] == 1
        items = {item['application_id']: item for item in after['gmail']['items']}
        assert items[confirmable]['advanced_state'] is True
        assert items[later]['advanced_state'] is False


# ---------------------------------------------------------------------------
# Follow-ups, outcomes, trend and the canonical pipeline
# ---------------------------------------------------------------------------
def test_followups_use_canonical_state_and_dubai_calendar_dates():
    today = CLOCK.astimezone(DUBAI).date()

    def with_followup(company, due, done=False, closed=False):
        application = make_application(company=company, url='')
        if closed:
            assert_user(application, states.CLOSED, dubai(0, 9))
        with Session.begin() as db:
            db.add(FollowUp(application_id=application, due_date=due, done=done))
        return application

    overdue = with_followup('Contoso Security', dubai(1, 9))
    # 21:30 UTC is already the next Dubai day: due tomorrow, not today.
    tomorrow = with_followup('Fabrikam Cyber',
                             datetime.combine(today, time(21, 30), tzinfo=UTC).isoformat())
    due_today = with_followup('Litware Defence',
                              datetime.combine(today, time(19, 30), tzinfo=UTC).isoformat())
    with_followup('Tailspin Security', dubai(12))  # beyond seven days
    with_followup('Adatum Labs', dubai(2), done=True)
    with_followup('Wingtip Systems', dubai(2), closed=True)
    with_followup('Proseware Defence', 'not a date')

    followups = report()['actions']['followups']
    assert [item['application_id'] for item in followups['items']] == [overdue, due_today,
                                                                      tomorrow]
    assert followups['due_now'] == 2 and followups['overdue'] == 1
    assert followups['next_7_days'] == 3
    assert followups['date_not_recorded'] == 1


def test_outcome_rates_withhold_percentages_below_the_minimum():
    ids = [make_application(company=f'Fictional Employer {n}', url='') for n in range(3)]
    for index, application in enumerate(ids):
        assert_user(application, states.APPLIED, dubai(-7 * index, 10))
    assert_user(ids[0], states.INTERVIEW, dubai(1, 10))
    with Session.begin() as db:
        db.add(ApplicationEvent(application_id=ids[1], event_type='MEANINGFUL_RESPONSE',
                                message='Fictional reply'))
        db.add(ApplicationEvent(application_id=ids[2], event_type='AUTOMATED_CONFIRMATION',
                                message='Fictional receipt'))
    outcomes = report()['outcomes']
    assert outcomes['submitted_total'] == 3
    assert outcomes['interview'] == {'count': 1, 'of': 3, 'rate': None, 'enough_data': False}
    assert outcomes['replies']['count'] == 1  # automated receipts do not count
    weekly = {week['week_start']: week['submitted'] for week in outcomes['weekly']}
    assert len(outcomes['weekly']) == progress.TREND_WEEKS
    assert weekly[MONDAY.isoformat()] == 1
    assert weekly[(MONDAY - timedelta(days=7)).isoformat()] == 1
    assert weekly[(MONDAY - timedelta(days=14)).isoformat()] == 1

    more = [make_application(company=f'Fictional Firm {n}', url='') for n in range(7)]
    for application in more:
        assert_user(application, states.APPLIED, dubai(1, 11))
    outcomes = report()['outcomes']
    assert outcomes['interview'] == {'count': 1, 'of': 10, 'rate': 0.1, 'enough_data': True}
    sources = {row['name']: row for row in outcomes['by_source']}
    assert sources['Greenhouse']['submitted'] == 10
    assert outcomes['by_cv_version'][0]['name'] == 'Not recorded'


def test_pipeline_uses_canonical_state_and_flags_legacy_divergence():
    application = make_application(tracking={'cv_version': 'Fictional CV v2'}, url='')
    assert_user(application, states.APPLIED, dubai(0, 10))
    assert_user(application, states.INTERVIEW, dubai(1, 10))
    # A legacy edit moved the compatibility stage backwards; the canonical
    # state does not regress, and the page must say which is authoritative.
    with Session.begin() as db:
        row = db.get(Application, application)
        row.tracking = {**row.tracking, 'stage': 'APPLIED'}
    quiet = make_application(company='Contoso Security', url='', stage='SHORTLISTED')

    result = progress.pipeline()
    rows = {item['application_id']: item for item in result['items']}
    assert rows[application]['current_state'] == states.INTERVIEW
    assert rows[application]['legacy_stage'] == 'APPLIED'
    assert rows[application]['submitted_at'] == dubai(0, 10)
    assert rows[application]['cv_version'] == 'Fictional CV v2'
    assert rows[quiet]['current_state'] == states.SAVED
    assert rows[quiet]['legacy_stage'] is None and rows[quiet]['submitted'] is False
    assert result['total'] == 2 and result['truncated'] is False


# ---------------------------------------------------------------------------
# API boundary
# ---------------------------------------------------------------------------
def test_routes_validate_input_and_inherit_the_private_api_guard():
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as client:
        assert client.get('/api/progress').status_code == 200
        for period in progress.PERIODS:
            assert client.get(f'/api/progress?period={period}').json()['period']['key'] == period
        assert client.get('/api/progress?period=forever').status_code == 400
        assert client.get('/api/progress/needs-review?limit=0').status_code == 422
        assert client.get('/api/progress/needs-review?limit=21').status_code == 422
        assert client.get('/api/progress/needs-review?offset=-1').status_code == 422
        assert client.get('/api/progress/applications').status_code == 200
        blocked = client.get('/api/progress', headers={'Sec-Fetch-Site': 'cross-site'})
        assert blocked.status_code == 403
        navigation = client.get('/api/progress', headers={'Sec-Fetch-Dest': 'document'})
        assert navigation.status_code == 403
        assert client.get('/api/progress').headers['cache-control'] == 'no-store'


# ---------------------------------------------------------------------------
# The frontend's words for bounded codes must name codes that really exist
# ---------------------------------------------------------------------------
def _ts_keys(source, constant):
    """Top-level keys of one `export const NAME: Record<...> = {...}` map."""
    import re
    block = re.search(r'export const ' + constant + r'\b[^=]*=\s*\{(.*?)\n\};', source, re.S)
    assert block, constant
    return set(re.findall(r'^\s*([A-Z_]+):', block.group(1), re.M)) | set(
        re.findall(r'[{,]\s*([A-Z_]+):', block.group(1)))


def test_frontend_vocabulary_matches_backend_codes():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'progressModel.ts'
              ).read_text(encoding='utf-8')
    assert _ts_keys(source, 'REVIEW_REASONS') <= set(reconciliation.REASON_CODES)
    assert _ts_keys(source, 'STATE_LABELS') == set(states.STATES)
    assert _ts_keys(source, 'SOURCE_LABELS') == set(states.SOURCE_CATEGORIES)
    assert _ts_keys(source, 'FIELD_LABELS') == set(states.AGREEMENT_FIELDS)
    assert _ts_keys(source, 'PLATFORM_LABELS') == set(reconciliation.PLATFORM_FAMILIES)
    assert _ts_keys(source, 'STAGE_LABELS') == set(telemetry.FUNNEL_STAGES)
    # Refusal codes the review outcome text switches on.
    for code in (reconciliation.REASON_LINK_NOT_REVIEWABLE, reconciliation.REASON_NO_STRONG_MATCH):
        assert f"case '{code}':" in source, code
    # Every queue reason #46 can leave on a NEEDS_REVIEW item has words.
    queued = {reconciliation.REASON_MEDIUM_NEEDS_REVIEW, reconciliation.REASON_AMBIGUOUS,
              reconciliation.REASON_URL_CONFLICT, reconciliation.REASON_SINGLE_FIELD_ONLY,
              reconciliation.REASON_NO_STRONG_MATCH, reconciliation.REASON_NO_CANDIDATES}
    assert queued <= _ts_keys(source, 'REVIEW_REASONS')

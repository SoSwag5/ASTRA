"""Read-only Progress reporting projection (#47).

Answers four questions for the Progress, Today and Applications pages:

1. What discovery, application and Gmail events happened in a period?
2. What needs the user's decision now?
3. What recorded source supports each figure?
4. What is incomplete, unavailable or too sparse to interpret?

Everything here is a *reading* of records other modules own. The contract
for every figure -- source, event versus current state, time field, window,
deduplication key and missing/partial/failed treatment -- is
`docs/architecture/PROGRESS_DASHBOARD.md`.

Rules, each of which is a test:

* **No new state logic.** Canonical state and history come from
  `application_state`; the only write reachable from here is that module's
  existing read-repair (`state_summary()` -> `ensure_all_states()`), which
  records truthful `LEGACY_MIGRATION` bootstrap rows exactly as every other
  #46 read already does. No transition is proposed, applied or refused here.
* **No new matching logic.** Review candidates are
  `application_reconciliation.find_candidates()` filtered by
  `Candidate.confirmable` -- the same call and the same filter
  `confirm_review()` applies -- so the user can only be offered a target the
  confirm endpoint would accept.
* **Discovery through its own read model.** Runs are read with
  `search_workspace._telemetry_runs()` (the bounded retention query behind
  `/api/search/telemetry/runs`) and projected with
  `discovery_telemetry.public_view()` (its whitelist). Run-level canonical
  stages are already deduplicated across sources; per-source values are never
  summed.
* **Unknown is never zero.** Missing, partial, failed, in-progress and
  unavailable inputs are reported as such, with counts, instead of being
  folded into a number.
* **Minimized Gmail fields only.** The review projection returns detected
  company, detected role, received time, platform, confidence, reason and
  matched field names. It never returns a subject, sender, message or
  account identifier, evidence URL or snippet.
* **Bounded.** Every list and every scan has an explicit cap and reports
  when it was reached.
"""
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from . import application_reconciliation as reconciliation
from . import application_state as states
from . import discovery_telemetry as telemetry
from . import gmail_accounts as accounts
from . import gmail_sync
from .models import Application, ApplicationEvent, FollowUp, Job, Session

router = APIRouter(prefix='/api/progress')

SCHEMA_VERSION = 'progress-v1'
TIMEZONE_NAME = 'Asia/Dubai'
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

THIS_WEEK = 'this_week'
LAST_WEEK = 'last_week'
LAST_30_DAYS = 'last_30_days'
LAST_90_DAYS = 'last_90_days'
PERIODS = (THIS_WEEK, LAST_WEEK, LAST_30_DAYS, LAST_90_DAYS)
PERIOD_LABELS = {THIS_WEEK: 'This week', LAST_WEEK: 'Last week',
                 LAST_30_DAYS: 'Last 30 days', LAST_90_DAYS: 'Last 90 days'}

#: Items returned in any one list. Counts are always exact; lists are samples
#: of the counted records, with `truncated` saying when more exist.
MAX_LISTED = 50
#: History rows read per request. A local single-user database is far below
#: this; it exists so a pathological database cannot make a request unbounded.
MAX_TRANSITIONS = 20_000
MAX_EVIDENCE_ROWS = 20_000
MAX_PIPELINE_ROWS = 500
MAX_REVIEW_PAGE = 20
MAX_REVIEW_OFFSET = 100_000
#: Discovery history is read in the same page size the telemetry endpoint
#: allows, for at most this many pages.
TELEMETRY_PAGE = 20
MAX_TELEMETRY_PAGES = 10
#: Below this denominator a rate is reported as "not enough data".
RATE_MINIMUM = 10
TREND_WEEKS = 12
FOLLOWUP_HORIZON_DAYS = 7

#: Confidence levels the Needs Review queue may contain. #46 never queues LOW;
#: anything else found in the queue is excluded and counted, not shown.
REVIEWABLE_CONFIDENCE = (states.HIGH, states.MEDIUM)
#: Canonical states after which a follow-up is no longer an action.
FOLLOWUP_CLOSED_STATES = frozenset({states.REJECTED, states.CLOSED})
#: States recorded as "other stage changes". APPLIED is reported separately
#: as a submission, and DISCOVERED is never a transition target.
STAGE_EVENT_STATES = (states.SAVED, states.VIEWED, states.ASSESSMENT,
                      states.INTERVIEW, states.OFFER, states.REJECTED,
                      states.CLOSED)

SUBMISSION_DATED = 'DATED'
SUBMISSION_UNDATED = 'UNDATED'

STATUS_OK = 'OK'
STATUS_INCOMPLETE = 'INCOMPLETE'
STATUS_NO_SCANS = 'NO_SCANS'
STATUS_NOT_RECORDED = 'NOT_RECORDED'
STATUS_UNAVAILABLE = 'UNAVAILABLE'
STATUS_NOT_CONNECTED = 'NOT_CONNECTED'


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------
def _now(clock=None):
    return (clock or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _parse(value):
    """A timezone-aware UTC datetime, or `None`. Uses #46's strict parser."""
    parsed = states.parse_timestamp(value)
    return parsed.astimezone(timezone.utc) if parsed is not None else None


def _local_midnight(day):
    return datetime.combine(day, time(0), tzinfo=TIMEZONE)


def period_window(period, clock=None):
    """The half-open `[start, end)` window for a period, in Asia/Dubai.

    Weeks start on Monday (ISO). Rolling windows are whole Dubai calendar
    days including today, so `last_90_days` always starts after the 90-day
    telemetry retention cutoff.
    """
    if period not in PERIODS:
        raise ValueError('Choose a supported period')
    local = _now(clock).astimezone(TIMEZONE)
    today = local.date()
    monday = today - timedelta(days=today.weekday())
    if period == THIS_WEEK:
        start, end = monday, monday + timedelta(days=7)
    elif period == LAST_WEEK:
        start, end = monday - timedelta(days=7), monday
    else:
        days = 30 if period == LAST_30_DAYS else 90
        start, end = today - timedelta(days=days - 1), today + timedelta(days=1)
    start_at, end_at = _local_midnight(start), _local_midnight(end)
    return {'key': period, 'label': PERIOD_LABELS[period],
            'timezone': TIMEZONE_NAME,
            'start': start_at.isoformat(), 'end': end_at.isoformat(),
            'first_day': start.isoformat(),
            'last_day': (end - timedelta(days=1)).isoformat(),
            'includes_today': start <= today < end,
            '_start': start_at.astimezone(timezone.utc),
            '_end': end_at.astimezone(timezone.utc)}


def _public_window(window):
    return {key: value for key, value in window.items() if not key.startswith('_')}


def _within(moment, window):
    return moment is not None and window['_start'] <= moment < window['_end']


def _local_day(moment):
    return moment.astimezone(TIMEZONE).date() if moment is not None else None


# ---------------------------------------------------------------------------
# Application history
# ---------------------------------------------------------------------------
def _histories(db):
    """`({application_id: [transition, ...]}, truncated)` in sequence order."""
    rows = db.scalars(
        select(states.ApplicationStateTransition)
        .order_by(states.ApplicationStateTransition.application_id,
                  states.ApplicationStateTransition.sequence)
        .limit(MAX_TRANSITIONS + 1)).all()
    truncated = len(rows) > MAX_TRANSITIONS
    grouped = defaultdict(list)
    for row in rows[:MAX_TRANSITIONS]:
        grouped[row.application_id].append(row)
    return grouped, truncated


def _tokens(row):
    return set(row.evidence_tokens or [])


def submission_of(history):
    """When, and on whose assertion, one application was submitted.

    Returns `None` when the history records no submission, otherwise
    `{'kind', 'occurred_at', 'source_category', 'transition_id'}` where
    `kind` is `DATED` (the occurrence is a recorded event time) or `UNDATED`
    (a submission is established, its date is not).

    * An accepted transition into APPLIED is dated by its `occurred_at`,
      unless #46 had to replace an unparseable time (`OCCURRED_AT_INVALID`).
    * A bootstrap row is dated only when it carries
      `LEGACY_APPLIED_DATE_PRESENT`; its time is then the recorded applied
      date. Any other bootstrap time is when ASTRA first knew, not when the
      application happened.
    * A later stage recorded without APPLIED ever being recorded carries
      `SUBMISSION_IMPLIED_BY_LATER_STATE`: submitted, date not recorded.

    APPLIED can be entered at most once (the transition table has no
    regression), so the first submission found is the only one.
    """
    for row in history:
        tokens = _tokens(row)
        ordinal = states.ORDINAL.get(row.new_state, -1)
        if row.source_category == states.SOURCE_LEGACY_MIGRATION:
            if states.TOKEN_APPLIED_DATE_PRESENT in tokens:
                return _submission(SUBMISSION_DATED, row)
            if (ordinal >= states.ORDINAL[states.APPLIED]
                    and row.new_state != states.CLOSED):
                return _submission(SUBMISSION_UNDATED, row)
            continue
        if row.new_state == states.APPLIED:
            kind = (SUBMISSION_UNDATED if states.TOKEN_OCCURRED_AT_INVALID in tokens
                    else SUBMISSION_DATED)
            return _submission(kind, row)
        if states.TOKEN_SUBMISSION_IMPLIED in tokens:
            return _submission(SUBMISSION_UNDATED, row)
    return None


def _submission(kind, row):
    return {'kind': kind,
            'occurred_at': _parse(row.occurred_at) if kind == SUBMISSION_DATED else None,
            'source_category': row.source_category,
            'transition_id': row.id}


def _reached(history):
    """Every canonical state this history records, bootstrap included."""
    return {row.new_state for row in history}


def _stage_events(history):
    """`(dated_events, undated_count)` of non-submission stage changes.

    Bootstrap rows are excluded: a bootstrap's time is when ASTRA first knew
    about the application, not when it reached that stage.
    """
    events, undated = [], 0
    for row in history:
        if row.source_category == states.SOURCE_LEGACY_MIGRATION:
            continue
        if row.new_state not in STAGE_EVENT_STATES:
            continue
        if states.TOKEN_OCCURRED_AT_INVALID in _tokens(row):
            undated += 1
            continue
        events.append(row)
    return events, undated


# ---------------------------------------------------------------------------
# Shared lookups
# ---------------------------------------------------------------------------
def _applications(db, ids=None):
    """`{application_id: (Application, Job)}` for the given ids, or the most
    recent `MAX_TRANSITIONS` applications when no ids are given."""
    query = select(Application, Job).join(Job, Application.job_id == Job.id)
    if ids is not None:
        if not ids:
            return {}
        query = query.where(Application.id.in_(list(ids)))
    else:
        query = query.order_by(Application.id.desc()).limit(MAX_TRANSITIONS)
    return {application.id: (application, job)
            for application, job in db.execute(query).all()}


def _current_states(db, ids=None):
    query = select(states.ApplicationStateRecord)
    if ids is not None:
        if not ids:
            return {}
        query = query.where(states.ApplicationStateRecord.application_id.in_(list(ids)))
    return {record.application_id: record for record in db.scalars(query)}


def _job_label(pair):
    if pair is None:
        return {'job_id': None, 'company': None, 'title': None}
    _, job = pair
    return {'job_id': job.id, 'company': job.company, 'title': job.title}


def _iso(moment):
    return moment.isoformat() if moment is not None else None


# ---------------------------------------------------------------------------
# Period figures: applications
# ---------------------------------------------------------------------------
def _application_figures(db, histories, window):
    submitted, undated = [], []
    by_source = Counter()
    for application_id, history in histories.items():
        submission = submission_of(history)
        if submission is None:
            continue
        if submission['kind'] == SUBMISSION_UNDATED:
            undated.append(application_id)
        elif _within(submission['occurred_at'], window):
            submitted.append((submission['occurred_at'], application_id,
                              submission['source_category']))
            by_source[submission['source_category']] += 1
    submitted.sort(reverse=True)

    stage_rows, stage_undated = [], 0
    for history in histories.values():
        events, missing = _stage_events(history)
        stage_undated += missing
        stage_rows.extend(row for row in events if _within(_parse(row.occurred_at), window))
    stage_rows.sort(key=lambda row: (_parse(row.occurred_at), row.id), reverse=True)

    listed_ids = {application_id for _, application_id, _ in submitted[:MAX_LISTED]}
    listed_ids |= {row.application_id for row in stage_rows[:MAX_LISTED]}
    pairs = _applications(db, listed_ids)
    stage_counts = Counter(row.new_state for row in stage_rows)
    return {
        'submitted': {
            'count': len(submitted),
            'by_source': {source: by_source.get(source, 0)
                          for source in states.SOURCE_CATEGORIES if by_source.get(source)},
            'submission_date_not_recorded': len(undated),
            'items': [{'application_id': application_id,
                       **_job_label(pairs.get(application_id)),
                       'occurred_at': _iso(moment), 'source_category': source}
                      for moment, application_id, source in submitted[:MAX_LISTED]],
            'truncated': len(submitted) > MAX_LISTED,
        },
        'stage_changes': {
            'count': len(stage_rows),
            'by_state': {state: stage_counts.get(state, 0) for state in STAGE_EVENT_STATES},
            'date_not_recorded': stage_undated,
            'items': [{'application_id': row.application_id,
                       **_job_label(pairs.get(row.application_id)),
                       'state': row.new_state, 'previous_state': row.previous_state,
                       'occurred_at': _iso(_parse(row.occurred_at)),
                       'source_category': row.source_category}
                      for row in stage_rows[:MAX_LISTED]],
            'truncated': len(stage_rows) > MAX_LISTED,
        },
    }


# ---------------------------------------------------------------------------
# Period figures: Gmail
# ---------------------------------------------------------------------------
def _gmail_ready():
    return gmail_sync.schema_ready() and reconciliation.schema_ready()


def gmail_coverage():
    """Connection and sync coverage for the primary slot. No identity data."""
    if not accounts.schema_ready():
        return {'status': STATUS_UNAVAILABLE, 'connected': False,
                'sync_state': 'NONE', 'checked_through': None}
    with Session() as db:
        row = db.scalar(select(accounts.GmailAccount).where(
            accounts.GmailAccount.slot == 'PRIMARY'))
    connected = row is not None and row.status == accounts.CONNECTED
    state = row.sync_state if row is not None and isinstance(row.sync_state, dict) else {}
    sync_state, checked_through = 'NONE', None
    if state.get('version') == gmail_sync.SYNC_STATE_VERSION:
        if any(key in state for key in ('after', 'before', 'page_token')):
            # An interval is part-way through. Nothing before it is claimed,
            # because an interrupted first sync has completed nothing at all.
            sync_state = 'INCOMPLETE'
        elif type(state.get('completed_through')) is int:
            sync_state = 'COMPLETE'
            checked_through = datetime.fromtimestamp(
                state['completed_through'], tz=timezone.utc).isoformat()
    return {'status': 'CONNECTED' if connected else STATUS_NOT_CONNECTED,
            'connected': connected, 'sync_state': sync_state,
            'checked_through': checked_through}


def _evidence_rows(db):
    rows = db.execute(
        select(gmail_sync.GmailConfirmation, reconciliation.GmailApplicationLink)
        .outerjoin(reconciliation.GmailApplicationLink,
                   reconciliation.GmailApplicationLink.gmail_confirmation_id
                   == gmail_sync.GmailConfirmation.id)
        .order_by(gmail_sync.GmailConfirmation.id.desc())
        .limit(MAX_EVIDENCE_ROWS + 1)).all()
    return rows[:MAX_EVIDENCE_ROWS], len(rows) > MAX_EVIDENCE_ROWS


def _gmail_figures(db, window):
    coverage = gmail_coverage()
    if not _gmail_ready():
        return {'status': STATUS_UNAVAILABLE, 'coverage': coverage, 'messages': None,
                'applications': None, 'by_outcome': {}, 'low_confidence_not_used': None,
                'not_reconciled_total': None, 'items': [], 'truncated': False,
                'scan_truncated': False}
    rows, scan_truncated = _evidence_rows(db)
    messages, applications = set(), set()
    outcomes = defaultdict(set)
    low, not_reconciled_total = set(), set()
    detected = []
    for evidence, link in rows:
        reviewable = evidence.confidence in REVIEWABLE_CONFIDENCE
        if reviewable and link is None:
            not_reconciled_total.add(evidence.gmail_message_id or evidence.id)
        received = _parse(evidence.received_at)
        if not _within(received, window):
            continue
        key = evidence.gmail_message_id or f'row-{evidence.id}'
        if not reviewable:
            low.add(key)
            continue
        messages.add(key)
        outcome = link.decision if link is not None else 'NOT_RECONCILED'
        outcomes[outcome].add(key)
        if link is not None and link.decision in (reconciliation.DECISION_LINKED,
                                                  reconciliation.DECISION_USER_CONFIRMED):
            if link.application_id:
                applications.add(link.application_id)
            detected.append((received, evidence, link))
    detected.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    pairs = _applications(db, {link.application_id for _, _, link in detected[:MAX_LISTED]
                               if link.application_id})
    items = []
    for received, evidence, link in detected[:MAX_LISTED]:
        label = _job_label(pairs.get(link.application_id))
        items.append({'link_id': link.id, 'application_id': link.application_id,
                      'job_id': label['job_id'],
                      'company': label['company'] or evidence.detected_company,
                      'title': label['title'] or evidence.detected_role,
                      'received_at': _iso(received), 'decision': link.decision,
                      'advanced_state': bool(link.transition_id)})
    if not coverage['connected'] and not rows:
        # Gmail has never supplied anything: how many confirmations arrived
        # is unknown, not zero.
        return {'status': STATUS_NOT_CONNECTED, 'coverage': coverage, 'messages': None,
                'applications': None, 'by_outcome': {}, 'low_confidence_not_used': None,
                'not_reconciled_total': None, 'items': [], 'truncated': False,
                'scan_truncated': False}
    return {'status': STATUS_OK, 'coverage': coverage,
            'messages': len(messages), 'applications': len(applications),
            'by_outcome': {decision: len(outcomes.get(decision, ()))
                           for decision in (*reconciliation.DECISIONS, 'NOT_RECONCILED')},
            'low_confidence_not_used': len(low),
            'not_reconciled_total': len(not_reconciled_total),
            'items': items, 'truncated': len(detected) > MAX_LISTED,
            'scan_truncated': scan_truncated}


def review_counts(db=None):
    """Exact Needs Review totals over the whole queue, never a page size."""
    if not _gmail_ready():
        return {'status': STATUS_UNAVAILABLE, 'total': None,
                'excluded_other_confidence': None}

    def _count(session, reviewable):
        condition = gmail_sync.GmailConfirmation.confidence.in_(REVIEWABLE_CONFIDENCE)
        return session.scalar(
            select(func.count()).select_from(reconciliation.GmailApplicationLink)
            .join(gmail_sync.GmailConfirmation,
                  gmail_sync.GmailConfirmation.id
                  == reconciliation.GmailApplicationLink.gmail_confirmation_id)
            .where(reconciliation.GmailApplicationLink.decision
                   == reconciliation.DECISION_NEEDS_REVIEW,
                   condition if reviewable else ~condition)) or 0

    if db is None:
        with Session() as session:
            return review_counts(session)
    return {'status': STATUS_OK, 'total': _count(db, True),
            'excluded_other_confidence': _count(db, False)}


# ---------------------------------------------------------------------------
# Period figures: discovery
# ---------------------------------------------------------------------------
RUN_SOURCE_FIELDS = ('sources_attempted', 'sources_succeeded', 'sources_partial',
                     'sources_failed', 'sources_skipped', 'sources_incomplete')


def _run_summary(view):
    """One run in the period, from `public_view()`. Unknown stays `None`."""
    payload = view.get('telemetry') or {}
    funnel = payload.get('funnel') if isinstance(payload.get('funnel'), dict) else None
    usable = view['telemetry_status'] == telemetry.TELEMETRY_OK and funnel is not None
    summary = {'run_id': view['run_id'], 'run_created_at': view['run_created_at'],
               'run_status': view['run_status'],
               'telemetry_status': view['telemetry_status'],
               # An OK telemetry status with a null funnel is a finalization
               # error: #43 reports no counts rather than wrong ones.
               'telemetry_error': view['telemetry_status'] == telemetry.TELEMETRY_OK
               and funnel is None,
               'counts_complete': (payload.get('counts_complete') is True) if usable else None,
               'new': funnel.get(telemetry.NEW) if usable else None,
               'relevant': funnel.get(telemetry.RELEVANT) if usable else None}
    for field in RUN_SOURCE_FIELDS:
        summary[field] = payload.get(field) if usable else None
    return summary


def _discovery_figures(db, window):
    from .search_workspace import _telemetry_runs
    summaries, reached_start, truncated = [], False, False
    for page in range(MAX_TELEMETRY_PAGES):
        runs = _telemetry_runs(db, TELEMETRY_PAGE, page * TELEMETRY_PAGE)
        for run in runs:
            created = _parse(run.created_at)
            if created is not None and created < window['_start']:
                reached_start = True
                continue
            if not _within(created, window):
                continue
            summaries.append(_run_summary(telemetry.public_view(run)))
        if reached_start or len(runs) < TELEMETRY_PAGE:
            break
    else:
        truncated = True

    counted = [run for run in summaries if run['new'] is not None]
    in_progress = sum(run['telemetry_status'] == telemetry.RUN_IN_PROGRESS for run in summaries)
    errors = sum(run['telemetry_error'] for run in summaries)
    unavailable = sum(run['telemetry_status'] == telemetry.TELEMETRY_UNAVAILABLE
                      for run in summaries)
    incomplete = sum(run['counts_complete'] is False for run in counted)
    if not summaries:
        status, value = STATUS_NO_SCANS, None
    elif not counted:
        status, value = STATUS_NOT_RECORDED, None
    else:
        value = sum(run['new'] for run in counted)
        status = (STATUS_INCOMPLETE
                  if incomplete or unavailable or errors or in_progress or truncated
                  else STATUS_OK)
    return {'status': status,
            'new_relevant': value,
            'lower_bound': status == STATUS_INCOMPLETE,
            'runs_in_period': len(summaries), 'runs_counted': len(counted),
            'runs_incomplete': incomplete, 'runs_unavailable': unavailable,
            'runs_in_progress': in_progress, 'runs_telemetry_error': errors,
            'history_truncated': truncated,
            'retention_days': telemetry.RETENTION_DAYS,
            'runs': summaries[:MAX_LISTED], 'truncated': len(summaries) > MAX_LISTED}


# ---------------------------------------------------------------------------
# Current state: follow-ups and next actions
# ---------------------------------------------------------------------------
def _action_figures(db, clock=None):
    today = _now(clock).astimezone(TIMEZONE).date()
    horizon = today + timedelta(days=FOLLOWUP_HORIZON_DAYS)
    records = _current_states(db)
    followups, undated = [], 0
    pairs = _applications(db)
    for follow in db.scalars(select(FollowUp).where(FollowUp.done.is_(False))):
        pair = pairs.get(follow.application_id)
        record = records.get(follow.application_id)
        if pair is None or (record is not None
                            and record.current_state in FOLLOWUP_CLOSED_STATES):
            continue
        due = _local_day(_parse(follow.due_date))
        if due is None:
            undated += 1
            continue
        if due > horizon:
            continue
        followups.append((due, follow.application_id))
    followups.sort()
    actions = []
    for application_id, (application, job) in pairs.items():
        tracking = application.tracking if isinstance(application.tracking, dict) else {}
        label = tracking.get('next_action')
        record = records.get(application_id)
        if not label or (record is not None and record.current_state in FOLLOWUP_CLOSED_STATES):
            continue
        due = _local_day(_parse(tracking.get('next_action_date')))
        if due is None or due > horizon:
            continue
        actions.append((due, application_id, str(label)[:500]))
    actions.sort()

    def _item(due, application_id):
        return {'application_id': application_id, **_job_label(pairs.get(application_id)),
                'due_on': due.isoformat(), 'overdue': due < today, 'due_now': due <= today,
                'current_state': records[application_id].current_state
                if application_id in records else None}

    return {'today': today.isoformat(),
            'applications_truncated': len(pairs) >= MAX_TRANSITIONS,
            'followups': {'due_now': sum(due <= today for due, _ in followups),
                          'overdue': sum(due < today for due, _ in followups),
                          'next_7_days': len(followups),
                          'date_not_recorded': undated,
                          'items': [_item(due, application_id)
                                    for due, application_id in followups[:MAX_LISTED]],
                          'truncated': len(followups) > MAX_LISTED},
            'next_actions': {'next_7_days': len(actions),
                             'items': [{**_item(due, application_id), 'action': label}
                                       for due, application_id, label in actions[:MAX_LISTED]],
                             'truncated': len(actions) > MAX_LISTED}}


# ---------------------------------------------------------------------------
# All-time outcomes, trend and breakdowns
# ---------------------------------------------------------------------------
def _rate(numerator, denominator):
    return {'count': numerator, 'of': denominator,
            'rate': round(numerator / denominator, 4)
            if denominator >= RATE_MINIMUM else None,
            'enough_data': denominator >= RATE_MINIMUM}


def _outcome_figures(db, histories, clock=None):
    submitted = {}
    for application_id, history in histories.items():
        submission = submission_of(history)
        if submission is not None:
            submitted[application_id] = submission
    reached = {application_id: _reached(histories[application_id])
               for application_id in submitted}
    interviewed = {a for a, seen in reached.items() if states.INTERVIEW in seen}
    offered = {a for a, seen in reached.items() if states.OFFER in seen}
    rejected = {a for a, seen in reached.items() if states.REJECTED in seen}
    replied = set()
    if submitted:
        replied = set(db.scalars(
            select(ApplicationEvent.application_id)
            .where(ApplicationEvent.event_type == 'MEANINGFUL_RESPONSE',
                   ApplicationEvent.application_id.in_(list(submitted)))
            .distinct()))
    total = len(submitted)

    today = _now(clock).astimezone(TIMEZONE).date()
    monday = today - timedelta(days=today.weekday())
    weeks = [monday - timedelta(days=7 * offset) for offset in range(TREND_WEEKS - 1, -1, -1)]
    per_week = Counter()
    for submission in submitted.values():
        day = _local_day(submission['occurred_at'])
        if day is None:
            continue
        per_week[day - timedelta(days=day.weekday())] += 1

    pairs = _applications(db, set(submitted))
    groups = {'source': defaultdict(set), 'cv_version': defaultdict(set)}
    for application_id in submitted:
        pair = pairs.get(application_id)
        if pair is None:
            continue
        application, job = pair
        tracking = application.tracking if isinstance(application.tracking, dict) else {}
        groups['source'][(job.source or '').strip() or 'Not recorded'].add(application_id)
        groups['cv_version'][str(tracking.get('cv_version') or '').strip()[:300]
                             or 'Not recorded'].add(application_id)

    def _breakdown(group):
        rows = [{'name': name, 'submitted': len(ids),
                 'interview': len(ids & interviewed), 'offer': len(ids & offered)}
                for name, ids in group.items()]
        return sorted(rows, key=lambda row: (-row['submitted'], row['name']))[:MAX_LISTED]

    return {'submitted_total': total,
            'submission_date_not_recorded': sum(
                s['kind'] == SUBMISSION_UNDATED for s in submitted.values()),
            'interview': _rate(len(interviewed), total),
            'offer': _rate(len(offered), total),
            'rejected': _rate(len(rejected), total),
            'replies': _rate(len(replied), total),
            'rate_minimum': RATE_MINIMUM,
            'weekly': [{'week_start': week.isoformat(), 'submitted': per_week.get(week, 0)}
                       for week in weeks],
            'by_source': _breakdown(groups['source']),
            'by_cv_version': _breakdown(groups['cv_version'])}


# ---------------------------------------------------------------------------
# Public read models
# ---------------------------------------------------------------------------
def progress_report(period=THIS_WEEK, *, clock=None):
    """Everything the Progress page shows for one period."""
    window = period_window(period, clock)
    # The existing #46 read-repair, so every application has its truthful
    # canonical row before anything is counted. No other write happens here.
    summary = states.state_summary()
    with Session() as db:
        histories, history_truncated = _histories(db)
        report = {
            'schema': SCHEMA_VERSION,
            'generated_at': _now(clock).isoformat(),
            'period': _public_window(window),
            'applications': {
                **_application_figures(db, histories, window),
                'history_truncated': history_truncated,
                'current': {'states': summary['states'], 'total': summary['total'],
                            'applications_total': summary['applications_total'],
                            'pending_initialization': summary['pending_initialization'],
                            'complete': summary['complete']},
            },
            'gmail': _gmail_figures(db, window),
            'review': review_counts(db),
            'actions': _action_figures(db, clock),
            'discovery': _discovery_figures(db, window),
            'outcomes': _outcome_figures(db, histories, clock),
        }
    return report


def _candidate_rows(db, candidates, proposed):
    pairs = _applications(db, {candidate.application_id for candidate in candidates})
    records = _current_states(db, {candidate.application_id for candidate in candidates})
    rows = []
    for candidate in candidates:
        label = _job_label(pairs.get(candidate.application_id))
        record = records.get(candidate.application_id)
        rows.append({'application_id': candidate.application_id, **label,
                     'current_state': record.current_state if record else None,
                     'matched_fields': sorted(candidate.fields),
                     'conflicting_fields': sorted(candidate.conflicts),
                     'proposed': candidate.application_id == proposed})
    rows.sort(key=lambda row: (not row['proposed'], row['application_id']))
    return rows


def review_page(*, limit=10, offset=0):
    """One page of the Needs Review queue with its confirmable candidates.

    Read-only: nothing here flushes, commits or calls the state service.
    """
    limit = max(1, min(int(limit), MAX_REVIEW_PAGE))
    offset = max(0, min(int(offset), MAX_REVIEW_OFFSET))
    if not _gmail_ready():
        return {'schema': SCHEMA_VERSION, 'status': STATUS_UNAVAILABLE, 'total': None,
                'excluded_other_confidence': None, 'limit': limit, 'offset': offset,
                'items': []}
    with Session() as db:
        counts = review_counts(db)
        pairs = db.execute(
            select(reconciliation.GmailApplicationLink, gmail_sync.GmailConfirmation)
            .join(gmail_sync.GmailConfirmation,
                  gmail_sync.GmailConfirmation.id
                  == reconciliation.GmailApplicationLink.gmail_confirmation_id)
            .where(reconciliation.GmailApplicationLink.decision
                   == reconciliation.DECISION_NEEDS_REVIEW,
                   gmail_sync.GmailConfirmation.confidence.in_(REVIEWABLE_CONFIDENCE))
            .order_by(reconciliation.GmailApplicationLink.id.desc())
            .offset(offset).limit(limit)).all()
        items = []
        for link, evidence in pairs:
            found = reconciliation.find_candidates(db, evidence)
            confirmable = [candidate for candidate in found if candidate.confirmable]
            ids = {candidate.application_id for candidate in confirmable}
            proposed = link.application_id
            # Exactly what confirm_review() would choose with no explicit
            # target: the proposal, else the only corroborating candidate.
            default = (proposed if proposed in ids
                       else next(iter(ids)) if proposed is None and len(ids) == 1
                       else None)
            items.append({
                'link_id': link.id,
                'confidence': evidence.confidence,
                'reason_code': link.reason_code,
                'received_at': _iso(_parse(evidence.received_at)),
                'platform': reconciliation.PARSER_PLATFORMS.get(evidence.parser_id, ''),
                'detected_company': evidence.detected_company,
                'detected_role': evidence.detected_role,
                'detected_state': evidence.detected_state,
                'matched_fields': list(link.matched_fields or []),
                'proposed_application_id': proposed,
                'proposed_confirmable': proposed in ids if proposed else None,
                'default_application_id': default,
                'candidates': _candidate_rows(db, confirmable, proposed),
                'candidates_truncated': len(found) >= reconciliation.MAX_CANDIDATES,
            })
        # Never let this read leave anything pending in the session.
        db.rollback()
    return {'schema': SCHEMA_VERSION, 'status': STATUS_OK,
            'total': counts['total'],
            'excluded_other_confidence': counts['excluded_other_confidence'],
            'limit': limit, 'offset': offset, 'items': items}


def pipeline(*, clock=None):
    """Canonical current state for every application, bounded."""
    states.state_summary()
    with Session() as db:
        histories, history_truncated = _histories(db)
        total = db.scalar(select(func.count()).select_from(Application)) or 0
        rows = db.execute(
            select(states.ApplicationStateRecord, Application, Job)
            .join(Application, Application.id == states.ApplicationStateRecord.application_id)
            .join(Job, Job.id == Application.job_id)
            .order_by(states.ApplicationStateRecord.entered_at.desc(),
                      Application.id.desc())
            .limit(MAX_PIPELINE_ROWS)).all()
        listed = [application.id for _, application, _ in rows]
        follow = {row.application_id: row for row in db.scalars(
            select(FollowUp).where(FollowUp.application_id.in_(listed)))} if listed else {}
        items = []
        for record, application, job in rows:
            tracking = application.tracking if isinstance(application.tracking, dict) else {}
            legacy = tracking.get('stage') or application.status
            mapped = states.canonical_for_legacy(legacy)
            submission = submission_of(histories.get(application.id, []))
            follow_up = follow.get(application.id)
            items.append({
                'application_id': application.id, 'job_id': job.id,
                'company': job.company, 'title': job.title,
                'current_state': record.current_state,
                'entered_at': _iso(_parse(record.entered_at)),
                'source_category': record.source_category,
                'submitted': submission is not None,
                'submitted_at': _iso(submission['occurred_at']) if submission else None,
                'legacy_stage': legacy if mapped is not None and mapped != record.current_state
                else None,
                'cv_version': str(tracking.get('cv_version') or '')[:300] or None,
                'followup_due_on': _iso_day(follow_up) if follow_up and not follow_up.done
                else None,
            })
    return {'schema': SCHEMA_VERSION, 'total': total, 'listed': len(items),
            'truncated': total > len(items), 'history_truncated': history_truncated,
            'states': list(states.STATES), 'items': items}


def _iso_day(follow_up):
    day = _local_day(_parse(follow_up.due_date))
    return day.isoformat() if day else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get('')
def progress(period: str = Query(default=THIS_WEEK, max_length=20)):
    """Verified figures for one period. Read-only apart from #46 read-repair."""
    return progress_report(period)


@router.get('/needs-review')
def needs_review(limit: int = Query(default=10, ge=1, le=MAX_REVIEW_PAGE),
                 offset: int = Query(default=0, ge=0, le=MAX_REVIEW_OFFSET)):
    """The Needs Review queue with confirmable candidates, one page at a time."""
    return review_page(limit=limit, offset=offset)


@router.get('/applications')
def applications():
    """Canonical current state per application, bounded."""
    return pipeline()

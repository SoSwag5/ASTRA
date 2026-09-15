"""Issue #42: offline evaluation + bounded calibration harness for issue #41's
FitAssessment engine.

Pure, deterministic, network-free. Consumes the REAL production engine
(`backend.assessment.assess`, `backend.recall.evaluate_legacy`,
`backend.recall.evaluate`) -- this module never recomputes a score or
reimplements domain/seniority/geography classification.

Reference labels (MUST_SHOW / REASONABLE_STRETCH / LOW_BUT_USEFUL /
GENUINE_REJECTION / UNCLEAR) use an evaluation-only vocabulary distinct from
system buckets (STRONG/GOOD/STRETCH/LOW/REJECTED) -- see
docs/evaluation/FIT_EVALUATION.md. A case's `reference_status` is either
`PROPOSED` (a Claude-authored seed label, not yet reviewed) or
`OWNER_ADJUDICATED` (the repository Owner has personally reviewed the case
and recorded a final label plus decision method/rationale under
`owner_adjudication` -- see docs/evaluation/FIT_LABEL_REVIEW.md); strict
corpus validation rejects any other status.
"""
import hashlib
import json
import math
import re
import subprocess
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from . import assessment
from . import career_tracks
from . import experience as experience_module
from . import recall
from .models import DEFAULTS

REPORT_SCHEMA_VERSION = 'fit-eval-report-2'
METRIC_DEFINITION_VERSION = 'metrics-v2'
CORPUS_SCHEMA_VERSION = 'fit-eval-corpus-1'
HUMAN_LABEL_VERSION = 'labels-v2'
CANDIDATE_POLICY_SCHEMA_VERSION = 'fit-candidate-policy-1'
QUALITY_GATE_SCHEMA_VERSION = 'fit-quality-gate-1'

BASELINE_VIEW = 'BASELINE'
CANDIDATE_VIEW = 'CANDIDATE'
LEGACY_VIEW = 'LEGACY'

LABELS = ('MUST_SHOW', 'REASONABLE_STRETCH', 'LOW_BUT_USEFUL', 'GENUINE_REJECTION', 'UNCLEAR')
USEFUL_LABELS = ('MUST_SHOW', 'REASONABLE_STRETCH', 'LOW_BUT_USEFUL')
DEFAULT_GAINS = {'MUST_SHOW': 3, 'REASONABLE_STRETCH': 2, 'LOW_BUT_USEFUL': 1, 'GENUINE_REJECTION': 0}
HARD_REASONS_EVALUATED = ('DOMAIN_INCOMPATIBLE', 'GEO_INCOMPATIBLE', 'EXTREME_LEADERSHIP_MISMATCH',
                          'CONFIRMED_ELIGIBILITY_CONFLICT')
BUCKET_ORDER = {'STRONG': 4, 'GOOD': 3, 'STRETCH': 2, 'LOW': 1, 'REJECTED': 0}
INSUFFICIENT_DATA = 'INSUFFICIENT_DATA'
UNAVAILABLE = 'UNAVAILABLE'
OK = 'OK'

REFERENCE_STATUSES = ('PROPOSED', 'OWNER_ADJUDICATED')
OWNER_DECISION_METHODS = ('OWNER_BULK_APPROVAL', 'OWNER_INDIVIDUAL')
OWNER_ADJUDICATION_FIELDS = frozenset({
    'original_reference_label', 'decision_method', 'group_id', 'changed', 'owner_rationale',
})
SPLITS = ('development', 'holdout')
STABLE_ID = re.compile(r'[a-z0-9][a-z0-9_-]{1,80}')
ALLOWED_HARD_REASONS = frozenset(HARD_REASONS_EVALUATED + ('USER_BLOCKED',))
ALLOWED_BUCKETS = frozenset(BUCKET_ORDER)


class CorpusError(ValueError):
    """A structural problem with an evaluation corpus file."""


def _read_json_object(path, kind):
    try:
        raw = Path(path).read_text(encoding='utf-8')
    except OSError as e:
        raise CorpusError(f'{kind} could not be read: {e}') from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise CorpusError(f'{kind} is not valid JSON: {e}') from e
    if not isinstance(data, dict):
        raise CorpusError(f'{kind} root must be a JSON object')
    return data


def _stable_id(value):
    return isinstance(value, str) and STABLE_ID.fullmatch(value) is not None


# ---------------------------------------------------------------------------
# Corpus loading and validation
# ---------------------------------------------------------------------------

def load_corpus(path):
    """Load and validate a versioned evaluation corpus. Raises CorpusError
    with a specific, actionable message on any structural problem -- this
    harness never silently tolerates a malformed corpus.
    """
    data = _read_json_object(path, 'Corpus')

    for key in ('corpus_schema_version', 'corpus_content_version', 'human_label_version',
                'metric_definition_version', 'fixed_assessment_clock', 'cases'):
        if key not in data:
            raise CorpusError(f'Corpus is missing required top-level key: {key}')
    if data['corpus_schema_version'] != CORPUS_SCHEMA_VERSION:
        raise CorpusError(f"Unsupported corpus_schema_version {data['corpus_schema_version']!r}; "
                           f"this harness only understands {CORPUS_SCHEMA_VERSION!r}. Refusing to guess.")
    if data['metric_definition_version'] != METRIC_DEFINITION_VERSION:
        raise CorpusError(f"Unsupported metric_definition_version {data['metric_definition_version']!r}; "
                           f"expected {METRIC_DEFINITION_VERSION!r}. Refusing to reinterpret the corpus.")
    if data['human_label_version'] != HUMAN_LABEL_VERSION:
        raise CorpusError(f"Unsupported human_label_version {data['human_label_version']!r}; "
                           f"expected {HUMAN_LABEL_VERSION!r}. Refusing to guess label semantics.")
    if not isinstance(data['corpus_content_version'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}\.\d+', data['corpus_content_version']):
        raise CorpusError('corpus_content_version must use YYYY-MM-DD.N format')
    try:
        fixed_clock = datetime.fromisoformat(data['fixed_assessment_clock'].replace('Z', '+00:00'))
    except (ValueError, AttributeError) as e:
        raise CorpusError(f'fixed_assessment_clock is not a valid ISO-8601 timestamp: {e}') from e
    if fixed_clock.utcoffset() is None:
        raise CorpusError('fixed_assessment_clock must include a timezone offset')

    cases = data['cases']
    if not isinstance(cases, list) or not cases:
        raise CorpusError('Corpus cases must be a non-empty list')

    seen_ids = set()
    seen_opportunity_ids = {}
    query_ids = {}
    bulk_groups = {}
    for i, case in enumerate(cases):
        where = f'case[{i}]'
        for key in ('id', 'query_id', 'source_kind', 'reference_opportunity_id', 'split', 'job',
                    'reference_label', 'reference_status',
                    'human_reason', 'allowed_hard_reasons', 'reference_link_state'):
            if key not in case:
                raise CorpusError(f'{where}: missing required field {key!r}')
        cid = case['id']
        if not _stable_id(cid):
            raise CorpusError(f'{where}: id {cid!r} is not a stable lowercase-kebab identifier')
        if cid in seen_ids:
            raise CorpusError(f'Duplicate case id: {cid!r}')
        seen_ids.add(cid)
        query_id = case['query_id']
        if not _stable_id(query_id):
            raise CorpusError(f'{where} ({cid}): query_id {query_id!r} is not a stable lowercase identifier')
        opportunity_id = case['reference_opportunity_id']
        if not _stable_id(opportunity_id):
            raise CorpusError(f'{where} ({cid}): reference_opportunity_id {opportunity_id!r} is invalid')
        if opportunity_id in seen_opportunity_ids:
            other = seen_opportunity_ids[opportunity_id]
            raise CorpusError(f'Duplicate reference_opportunity_id {opportunity_id!r}: {other!r} and {cid!r}; '
                              'an opportunity may not cross development/holdout under another case id')
        seen_opportunity_ids[opportunity_id] = cid
        if case['split'] not in SPLITS:
            raise CorpusError(f'{where} ({cid}): invalid split {case["split"]!r}; must be one of {SPLITS}')
        if case['reference_label'] not in LABELS:
            raise CorpusError(f'{where} ({cid}): invalid reference_label {case["reference_label"]!r}; '
                               f'must be one of {LABELS}')
        if case['reference_status'] not in REFERENCE_STATUSES:
            raise CorpusError(f'{where} ({cid}): invalid reference_status {case["reference_status"]!r}; '
                              f'this foundation accepts only {REFERENCE_STATUSES}')
        owner = case.get('owner_adjudication')
        if case['reference_status'] == 'PROPOSED':
            if 'owner_adjudication' in case:
                raise CorpusError(f'{where} ({cid}): PROPOSED cases must not carry owner_adjudication')
        else:
            if not isinstance(owner, dict):
                raise CorpusError(f'{where} ({cid}): OWNER_ADJUDICATED requires an owner_adjudication object')
            if set(owner) != OWNER_ADJUDICATION_FIELDS:
                missing = sorted(OWNER_ADJUDICATION_FIELDS - set(owner))
                extra = sorted(set(owner) - OWNER_ADJUDICATION_FIELDS)
                raise CorpusError(f'{where} ({cid}): owner_adjudication fields must be exactly '
                                  f'{sorted(OWNER_ADJUDICATION_FIELDS)}; missing={missing}, extra={extra}')
            original = owner['original_reference_label']
            if original not in LABELS:
                raise CorpusError(f'{where} ({cid}): invalid original_reference_label {original!r}')
            method = owner['decision_method']
            if method not in OWNER_DECISION_METHODS:
                raise CorpusError(f'{where} ({cid}): invalid owner decision_method {method!r}; '
                                  f'must be one of {OWNER_DECISION_METHODS}')
            changed = owner['changed']
            if not isinstance(changed, bool):
                raise CorpusError(f'{where} ({cid}): owner_adjudication.changed must be boolean')
            expected_changed = original != case['reference_label']
            if changed != expected_changed:
                raise CorpusError(f'{where} ({cid}): owner_adjudication.changed must equal whether the '
                                  'final reference_label differs from original_reference_label')
            rationale = owner['owner_rationale']
            if rationale is not None and (not isinstance(rationale, str) or not rationale.strip()):
                raise CorpusError(f'{where} ({cid}): owner_rationale must be null or non-empty text')
            if changed and rationale is None:
                raise CorpusError(f'{where} ({cid}): changed Owner decisions require owner_rationale')
            group_id = owner['group_id']
            if method == 'OWNER_INDIVIDUAL':
                if group_id is not None:
                    raise CorpusError(f'{where} ({cid}): OWNER_INDIVIDUAL requires group_id null')
            else:
                if not isinstance(group_id, str) or not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,39}', group_id):
                    raise CorpusError(f'{where} ({cid}): OWNER_BULK_APPROVAL requires a stable group_id')
                if changed:
                    raise CorpusError(f'{where} ({cid}): OWNER_BULK_APPROVAL cannot silently change a proposal')
                bulk_groups.setdefault(group_id, []).append((cid, original, case['reference_label']))
        if not isinstance(case['allowed_hard_reasons'], list):
            raise CorpusError(f'{where} ({cid}): allowed_hard_reasons must be a list')
        if len(case['allowed_hard_reasons']) != len(set(case['allowed_hard_reasons'])):
            raise CorpusError(f'{where} ({cid}): allowed_hard_reasons contains duplicates')
        unknown_reasons = set(case['allowed_hard_reasons']) - ALLOWED_HARD_REASONS
        if unknown_reasons:
            raise CorpusError(f'{where} ({cid}): invalid allowed_hard_reasons {sorted(unknown_reasons)}')
        if case['reference_label'] != 'GENUINE_REJECTION' and case['allowed_hard_reasons']:
            raise CorpusError(f'{where} ({cid}): allowed_hard_reasons is only meaningful for '
                               'GENUINE_REJECTION cases')
        if case['reference_link_state'] not in ('LIKELY_LIVE', 'LIKELY_STALE', 'UNKNOWN'):
            raise CorpusError(f'{where} ({cid}): invalid reference_link_state {case["reference_link_state"]!r}')
        if not isinstance(case['human_reason'], str) or not case['human_reason'].strip():
            raise CorpusError(f'{where} ({cid}): human_reason must be non-empty text')
        if not isinstance(case['source_kind'], str) or not case['source_kind'].strip():
            raise CorpusError(f'{where} ({cid}): source_kind must be non-empty text')
        if not isinstance(case.get('tags', {}), dict):
            raise CorpusError(f'{where} ({cid}): tags must be an object')
        if not isinstance(case.get('career_config', {}), dict):
            raise CorpusError(f'{where} ({cid}): career_config must be an object')
        if not isinstance(case.get('candidate_profile_fixture', {}), dict):
            raise CorpusError(f'{where} ({cid}): candidate_profile_fixture must be an object')
        job = case['job']
        if not isinstance(job, dict) or not job.get('title'):
            raise CorpusError(f'{where} ({cid}): job.title is required')
        query_ids.setdefault(query_id, []).append(cid)

    if len(query_ids) < 1:
        raise CorpusError('Corpus has no query sets')
    for group_id, members in bulk_groups.items():
        if len(members) < 2:
            raise CorpusError(f'Owner bulk-approval group {group_id!r} must contain at least two cases')
        label_pairs = {(original, final) for _, original, final in members}
        if len(label_pairs) != 1:
            raise CorpusError(f'Owner bulk-approval group {group_id!r} mixes label decisions')
    if 'query_sets' in data:
        if not isinstance(data['query_sets'], list) or len(data['query_sets']) != len(set(data['query_sets'])):
            raise CorpusError('query_sets must be a unique list')
        if set(data['query_sets']) != set(query_ids):
            raise CorpusError('query_sets must exactly match case query_id values')
    split_by_query = {}
    for case in cases:
        split_by_query.setdefault(case['query_id'], set()).add(case['split'])
    mixed = sorted(qid for qid, splits in split_by_query.items() if len(splits) != 1)
    if mixed:
        raise CorpusError(f'Whole query sets must stay in one split; mixed query sets: {mixed}')
    expected_holdout = {qid for qid, splits in split_by_query.items() if splits == {'holdout'}}
    if 'holdout_query_sets' in data:
        if not isinstance(data['holdout_query_sets'], list) or len(data['holdout_query_sets']) != len(set(data['holdout_query_sets'])):
            raise CorpusError('holdout_query_sets must be a unique list')
        if set(data['holdout_query_sets']) != expected_holdout:
            raise CorpusError('holdout_query_sets must exactly match query sets whose cases use split=holdout')
    if 'label_gains' in data and data['label_gains'] != DEFAULT_GAINS:
        raise CorpusError(f'label_gains must exactly match metric definition {METRIC_DEFINITION_VERSION}')
    data['_query_index'] = query_ids
    return data


# ---------------------------------------------------------------------------
# Running the real engine
# ---------------------------------------------------------------------------

def _clock(corpus):
    return datetime.fromisoformat(corpus['fixed_assessment_clock'].replace('Z', '+00:00'))


def _case_cfg(case):
    cfg = dict(DEFAULTS)
    cfg.update(case.get('career_config', {}))
    return cfg


@dataclass
class CaseResult:
    id: str
    query_id: str
    split: str
    source_kind: str
    reference_label: str
    reference_status: str
    allowed_hard_reasons: list
    reference_link_state: str
    tags: dict
    new_bucket: str
    new_score: object
    new_hard_reason: object
    legacy_excluded: object = None
    legacy_priority: object = None
    comparison_category: object = None
    candidate_bucket: object = None
    candidate_score: object = None

    def to_public_dict(self):
        """Bounded, privacy-safe: no job description/profile text."""
        return {'id': self.id, 'query_id': self.query_id, 'split': self.split,
                'source_kind': self.source_kind, 'reference_label': self.reference_label,
                'reference_status': self.reference_status, 'reference_link_state': self.reference_link_state,
                'tags': self.tags, 'new_bucket': self.new_bucket, 'new_score': self.new_score,
                'new_hard_reason': self.new_hard_reason, 'legacy_excluded': self.legacy_excluded,
                'legacy_priority': self.legacy_priority, 'comparison_category': self.comparison_category,
                'candidate_bucket': self.candidate_bucket, 'candidate_score': self.candidate_score}


def run_case(case, corpus, engine='compare', candidate_policy=None):
    """Assess one corpus case with the real engine. `engine`: 'new' (assess()
    only), 'legacy' (evaluate_legacy() only), or 'compare' (both, plus the
    real legacy/new shadow comparison from backend.recall).
    """
    item = dict(case['job'])
    profile = case.get('candidate_profile_fixture') or {}
    cfg = _case_cfg(case)
    clock = _clock(corpus)

    new_bucket = new_score = new_hard_reason = None
    legacy_excluded = legacy_priority = comparison_category = None

    if engine in ('new', 'compare'):
        if engine == 'compare':
            decision = recall.evaluate(item, cfg, profile, clock)
            new_fa = decision['fit_assessment']
            legacy = decision['legacy_shadow']
            comparison_category = decision['assessment_shadow']['comparison_category']
            legacy_excluded = legacy['excluded']
            legacy_priority = legacy['priority']
        else:
            new_fa = assessment.assess(item, cfg, profile, clock)
        new_bucket = new_fa['bucket']
        new_score = new_fa['score']
        new_hard_reason = new_fa['hard_reject']['code'] if new_fa['hard_reject'] else None
    else:
        legacy = recall.evaluate_legacy(item, cfg, profile, clock)
        legacy_excluded = legacy['excluded']
        legacy_priority = legacy['priority']

    candidate_bucket = candidate_score = None
    if candidate_policy is not None:
        new_fa_for_candidate = new_fa if engine in ('new', 'compare') else assessment.assess(item, cfg, profile, clock)
        candidate_score, candidate_bucket = apply_candidate_policy(new_fa_for_candidate, candidate_policy)

    return CaseResult(
        id=case['id'], query_id=case['query_id'], split=case.get('split', 'development'),
        source_kind=case['source_kind'], reference_label=case['reference_label'],
        reference_status=case['reference_status'], allowed_hard_reasons=list(case['allowed_hard_reasons']),
        reference_link_state=case['reference_link_state'], tags=case.get('tags', {}),
        new_bucket=new_bucket, new_score=new_score, new_hard_reason=new_hard_reason,
        legacy_excluded=legacy_excluded, legacy_priority=legacy_priority,
        comparison_category=comparison_category, candidate_bucket=candidate_bucket, candidate_score=candidate_score)


def run_corpus(corpus, engine='compare', case_filter=None, candidate_policy=None):
    """Run every (filtered) case through the real engine. Deterministic:
    results are returned in stable corpus order; callers sort per query set.
    """
    results = []
    for case in corpus['cases']:
        if case_filter is not None and not case_filter(case):
            continue
        results.append(run_case(case, corpus, engine=engine, candidate_policy=candidate_policy))
    return results


# ---------------------------------------------------------------------------
# Bounded candidate calibration (Phase 14/15): external, transparent
# recomposition of already-computed, already-normalized component points.
# Never touches hard-reject logic or semantic classification.
# ---------------------------------------------------------------------------

@dataclass
class CandidatePolicy:
    schema_version: str
    id: str
    description: str
    weights: dict  # component -> weight (must sum to 100)
    bucket_floors: list = field(default_factory=lambda: list(assessment.BUCKET_FLOORS))

    def content_hash(self):
        payload = json.dumps({'schema_version': self.schema_version, 'weights': self.weights,
                              'bucket_floors': self.bucket_floors}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_candidate_policy(path):
    data = _read_json_object(path, 'Candidate policy')
    for key in ('policy_schema_version', 'id', 'description', 'weights'):
        if key not in data:
            raise CorpusError(f'Candidate policy missing required field: {key}')
    if data['policy_schema_version'] != CANDIDATE_POLICY_SCHEMA_VERSION:
        raise CorpusError(f"Unsupported policy_schema_version {data['policy_schema_version']!r}; "
                          f"expected {CANDIDATE_POLICY_SCHEMA_VERSION!r}")
    if not _stable_id(data['id']):
        raise CorpusError(f'Candidate policy id {data["id"]!r} is invalid')
    if not isinstance(data['description'], str) or not data['description'].strip():
        raise CorpusError('Candidate policy description must be non-empty text')
    if not isinstance(data['weights'], dict) or set(data['weights']) != set(assessment.WEIGHTS):
        raise CorpusError(f'Candidate policy weights must cover exactly {sorted(assessment.WEIGHTS)}')
    for component, value in data['weights'].items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise CorpusError(f'Candidate policy weight {component!r} must be a finite number')
        if value < 0:
            raise CorpusError(f'Candidate policy weight {component!r} must be nonnegative')
    if abs(sum(data['weights'].values()) - 100) > 1e-9:
        raise CorpusError('Candidate policy weights must sum to 100')
    floors = data.get('bucket_floors')
    if floors is not None:
        if not isinstance(floors, list) or not floors:
            raise CorpusError('Candidate policy bucket_floors must be a non-empty list')
        normalized = []
        for i, entry in enumerate(floors):
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise CorpusError(f'Candidate policy bucket_floors[{i}] must be [numeric_floor, bucket_name]')
            floor, name = entry
            if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not math.isfinite(floor):
                raise CorpusError(f'Candidate policy bucket_floors[{i}] floor must be a finite number')
            if floor < 0 or floor > 100:
                raise CorpusError(f'Candidate policy bucket_floors[{i}] floor must be between 0 and 100')
            if name not in ALLOWED_BUCKETS - {'REJECTED'}:
                raise CorpusError(f'Candidate policy bucket_floors[{i}] has unknown bucket {name!r}')
            normalized.append((floor, name))
        names = [name for _, name in normalized]
        if set(names) != {'STRONG', 'GOOD', 'STRETCH', 'LOW'} or len(names) != 4:
            raise CorpusError('Candidate policy bucket_floors must define STRONG, GOOD, STRETCH, and LOW once each')
        values = [floor for floor, _ in normalized]
        if values != sorted(values, reverse=True) or len(values) != len(set(values)):
            raise CorpusError('Candidate policy bucket_floors must be strictly descending')
        if normalized[-1] != (0, 'LOW'):
            raise CorpusError('Candidate policy bucket_floors must end with [0, "LOW"]')
        floors = normalized
    return CandidatePolicy(schema_version=data['policy_schema_version'], id=data['id'],
                            description=data['description'], weights=dict(data['weights']),
                            bucket_floors=floors or list(assessment.BUCKET_FLOORS))


def apply_candidate_policy(fit_assessment, policy):
    """Recompose the SAME per-component contributions the production engine
    already computed under a candidate weight policy. A hard reject is never
    recomposed -- it stays authoritative from the real engine regardless of
    candidate weights (Phase 15: no candidate may alter a hard rule).
    """
    if fit_assessment['hard_reject']:
        return None, 'REJECTED'
    ratios = {k: (v / assessment.WEIGHTS[k]) if assessment.WEIGHTS[k] else 0.0
              for k, v in fit_assessment['components'].items()}
    total = sum(ratios[k] * policy.weights[k] for k in ratios)
    score = max(0, min(100, round(total)))
    for floor, name in sorted(policy.bucket_floors, key=lambda x: -x[0]):
        if score >= floor:
            return score, name
    return score, 'LOW'


# ---------------------------------------------------------------------------
# Metric primitives
# ---------------------------------------------------------------------------

def _rate(numerator, denominator, failing_ids=None):
    if denominator == 0:
        return {'numerator': 0, 'denominator': 0, 'value': None, 'status': INSUFFICIENT_DATA,
                'failing_case_ids': []}
    return {'numerator': numerator, 'denominator': denominator, 'value': round(numerator / denominator, 4),
            'status': OK, 'failing_case_ids': sorted(failing_ids or [])}


def _unavailable_rate(reason='UNAVAILABLE_FOR_LEGACY_ENGINE'):
    return {'numerator': None, 'denominator': None, 'value': None, 'status': UNAVAILABLE,
            'failing_case_ids': [], 'reason': reason}


def _unavailable_ranking(reason='UNAVAILABLE_FOR_LEGACY_ENGINE'):
    metric = {'value': None, 'status': UNAVAILABLE, 'query_sets_scored': 0, 'reason': reason}
    return {'per_query_set': {}, 'precision_at_k': dict(metric), 'recall_at_k': dict(metric),
            'ndcg_at_k': dict(metric)}


def scored(results):
    """Results whose reference label is not UNCLEAR -- UNCLEAR is counted for
    coverage but excluded from every scored metric denominator by default.
    """
    return [r for r in results if r.reference_label != 'UNCLEAR']


def must_show_false_rejection(results):
    pool = [r for r in scored(results) if r.reference_label == 'MUST_SHOW']
    failing = [r.id for r in pool if r.new_bucket == 'REJECTED']
    return _rate(len(failing), len(pool), failing)


def useful_false_rejection(results):
    pool = [r for r in scored(results) if r.reference_label in USEFUL_LABELS]
    failing = [r.id for r in pool if r.new_bucket == 'REJECTED']
    return _rate(len(failing), len(pool), failing)


def new_useful_regression(results):
    """Reference-useful cases where the legacy evaluator accepted the
    posting and the new engine hard-rejects it. Highest-priority review set.
    """
    pool = [r for r in scored(results) if r.reference_label in USEFUL_LABELS and r.legacy_excluded is False]
    failing = [r.id for r in pool if r.new_bucket == 'REJECTED']
    return _rate(len(failing), len(pool), failing)


def high_priority_leakage(results):
    pool = [r for r in scored(results) if r.reference_label == 'GENUINE_REJECTION']
    leaking = [r.id for r in pool if r.new_bucket in ('STRONG', 'GOOD')]
    return _rate(len(leaking), len(pool), leaking)


def broad_leakage(results):
    pool = [r for r in scored(results) if r.reference_label == 'GENUINE_REJECTION']
    leaking = [r.id for r in pool if r.new_bucket in ('STRONG', 'GOOD', 'STRETCH', 'LOW')]
    low_only = [r.id for r in pool if r.new_bucket == 'LOW']
    result = _rate(len(leaking), len(pool), leaking)
    result['low_only'] = _rate(len(low_only), len(pool), low_only)
    return result


def hard_reason_precision(results):
    """Excludes UNCLEAR cases: precision compares a predicted hard reason
    against a declared human judgment (allowed_hard_reasons), which by
    construction only GENUINE_REJECTION cases carry -- an UNCLEAR case can
    never be "correct" here, so including it would only make precision look
    worse without adding real information.
    """
    out = {}
    for code in HARD_REASONS_EVALUATED:
        predicted = [r for r in scored(results) if r.new_hard_reason == code]
        correct = [r for r in predicted if code in r.allowed_hard_reasons]
        incorrect = [r.id for r in predicted if code not in r.allowed_hard_reasons]
        rate = _rate(len(correct), len(predicted), incorrect)
        rate['predicted_count'] = len(predicted)
        rate['human_allowed_count'] = len(correct)
        out[code] = rate
    return out


def user_blocked_check(results):
    """USER_BLOCKED is deterministic user-configured exclusion, not a
    semantic judgment -- reported separately per Phase 6, same shape as the
    other hard-reason metrics for consistency.
    """
    predicted = [r for r in scored(results) if r.new_hard_reason == 'USER_BLOCKED']
    correct = [r for r in predicted if 'USER_BLOCKED' in r.allowed_hard_reasons]
    incorrect = [r.id for r in predicted if 'USER_BLOCKED' not in r.allowed_hard_reasons]
    rate = _rate(len(correct), len(predicted), incorrect)
    rate['predicted_count'] = len(predicted)
    rate['human_allowed_count'] = len(correct)
    return rate


def legacy_new_transitions(results):
    from collections import Counter
    counts = Counter(r.comparison_category for r in results if r.comparison_category)
    recoveries = {k: v for k, v in counts.items() if k.startswith('LEGACY_REJECTED_NEW_')}
    recovered_useful = [r.id for r in results if r.comparison_category and
                        r.comparison_category.startswith('LEGACY_REJECTED_NEW_') and
                        r.reference_label in USEFUL_LABELS]
    new_regressions = [r.id for r in results if r.comparison_category == 'NEW_REJECTED']
    new_regressions_useful = [r.id for r in results if r.comparison_category == 'NEW_REJECTED' and
                              r.reference_label in USEFUL_LABELS]
    return {'category_counts': dict(counts), 'recoveries_by_bucket': recoveries,
            'recovered_case_ids_reference_useful': sorted(recovered_useful),
            'new_regression_case_ids': sorted(new_regressions),
            'new_regression_case_ids_reference_useful': sorted(new_regressions_useful)}


# ---------------------------------------------------------------------------
# Ranking / ordinal quality
# ---------------------------------------------------------------------------

def _rank_value(r):
    """Higher is better: bucket order first, then score within the bucket."""
    return BUCKET_ORDER.get(r.new_bucket, -1) * 1000 + (r.new_score if r.new_score is not None else -1)


def rank_query_set(results):
    """Deterministic descending rank: bucket order, then score, then case id
    as a fully stable tie-break.
    """
    return sorted(results, key=lambda r: (-_rank_value(r), r.id))


def _gain(label, gains):
    return gains.get(label, 0)


def precision_recall_ndcg_at_k(results_by_query, k=10, gains=None):
    gains = gains or DEFAULT_GAINS
    per_query = {}
    p_values, r_values, ndcg_values = [], [], []
    for qid, results in results_by_query.items():
        pool = scored(results)
        if not pool:
            continue
        ranked = rank_query_set(pool)
        effective_k = min(k, len(ranked))
        top = ranked[:effective_k]
        relevant_total = sum(1 for r in pool if _gain(r.reference_label, gains) > 0)
        relevant_in_top = sum(1 for r in top if _gain(r.reference_label, gains) > 0)
        precision = relevant_in_top / effective_k if effective_k else None
        recall = relevant_in_top / relevant_total if relevant_total else None
        dcg = sum(_gain(r.reference_label, gains) / (__import__('math').log2(i + 2)) for i, r in enumerate(top))
        ideal = sorted(pool, key=lambda r: -_gain(r.reference_label, gains))[:effective_k]
        idcg = sum(_gain(r.reference_label, gains) / (__import__('math').log2(i + 2)) for i, r in enumerate(ideal))
        ndcg = (dcg / idcg) if idcg > 0 else None
        per_query[qid] = {'k': effective_k, 'precision': precision, 'recall': recall, 'ndcg': ndcg,
                          'relevant_total': relevant_total, 'pool_size': len(pool)}
        if precision is not None:
            p_values.append(precision)
        if recall is not None:
            r_values.append(recall)
        if ndcg is not None:
            ndcg_values.append(ndcg)
    macro = lambda values: (round(sum(values) / len(values), 4) if values else None)
    return {'per_query_set': per_query,
            'precision_at_k': {'value': macro(p_values), 'status': OK if p_values else INSUFFICIENT_DATA,
                               'query_sets_scored': len(p_values)},
            'recall_at_k': {'value': macro(r_values), 'status': OK if r_values else INSUFFICIENT_DATA,
                            'query_sets_scored': len(r_values)},
            'ndcg_at_k': {'value': macro(ndcg_values), 'status': OK if ndcg_values else INSUFFICIENT_DATA,
                         'query_sets_scored': len(ndcg_values)}}


def pairwise_ordering_agreement(results_by_query, gains=None):
    gains = gains or DEFAULT_GAINS
    concordant = comparable = 0
    for results in results_by_query.values():
        pool = scored(results)
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                a, b = pool[i], pool[j]
                ga, gb = _gain(a.reference_label, gains), _gain(b.reference_label, gains)
                if ga == gb:
                    continue
                comparable += 1
                higher_label, lower_label = (a, b) if ga > gb else (b, a)
                concordant += int(_rank_value(higher_label) > _rank_value(lower_label))
    return _rate(concordant, comparable)


def bucket_distribution_by_label(results):
    from collections import Counter
    out = {}
    for label in LABELS:
        pool = [r for r in results if r.reference_label == label]
        out[label] = dict(Counter(r.new_bucket for r in pool))
    return out


# ---------------------------------------------------------------------------
# Duplicate rate (#40 corpus, isolated in-memory DB) and stale-link rate
# ---------------------------------------------------------------------------

def duplicate_rate(dedupe_corpus_path='tests/fixtures/job_dedupe_corpus.json'):
    """`duplicate_rate` here means #40's dedupe RECALL: the fraction of the
    #40 corpus's MUST_COLLAPSE groups where every observation correctly
    resolves onto a single Job, measured against an isolated in-memory
    SQLite database (never the live/production database). The complementary
    `false_merge_rate` over MUST_NOT_COLLAPSE pairs is reported alongside
    for transparency. This does not replace #40's own certification test
    suite (tests/test_job_deduplication.py, tests/test_issue40_remediation.py)
    -- it is a bounded summary metric for the evaluation report.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as OrmSession
    from .models import Base, JobSource
    from .services import add_job

    corpus = json.loads(Path(dedupe_corpus_path).read_text(encoding='utf-8'))
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    sources = {}

    def source_for(db, obs):
        """Each observation's OWN job_source_id, never borrowed from a
        sibling observation -- several must_not_collapse pairs are
        deliberately built from two DIFFERENT source instances (the same
        native id under two different boards must stay distinct), so
        reusing one observation's source for the other would silently
        defeat exactly the case being tested.
        """
        source_id = obs.get('job_source_id')
        if source_id is None:
            return None
        if source_id not in sources:
            src = JobSource(id=source_id, name=f'source-{source_id}', adapter='lever', board='fixture', enabled=True)
            db.add(src)
            db.flush()
            sources[source_id] = src
        return sources[source_id]

    collapsed_groups = failing_groups = 0
    with OrmSession(engine, expire_on_commit=False) as db:
        for group in corpus['must_collapse']:
            job_ids = set()
            for obs in group['observations']:
                j, _ = add_job(db, _observation_to_add_job_data(obs), job_source=source_for(db, obs))
                job_ids.add(j.id)
            if len(job_ids) == 1:
                collapsed_groups += 1
            else:
                failing_groups += 1
        collapse_rate = _rate(collapsed_groups, collapsed_groups + failing_groups)

        false_merges = correctly_distinct = 0
        for pair in corpus['must_not_collapse']:
            obs_a, obs_b = pair['observations']
            j1, _ = add_job(db, _observation_to_add_job_data(obs_a), job_source=source_for(db, obs_a))
            j2, d = add_job(db, _observation_to_add_job_data(obs_b), job_source=source_for(db, obs_b))
            if j1.id == j2.id:
                false_merges += 1
            else:
                correctly_distinct += 1
        false_merge_rate = _rate(false_merges, false_merges + correctly_distinct)
    engine.dispose()
    return {'dedupe_recall_rate': collapse_rate, 'false_merge_rate': false_merge_rate}


# backend.services._PROVIDER_FAMILY_FOR_SOURCE maps a capitalized display
# label (the ingestion dict's 'source' field) to a lowercase provider family
# -- the inverse of that map, needed because this corpus's observations
# already carry the lowercase family (JobObservationInput's own convention).
# Passing the lowercase string straight through as 'source' would silently
# resolve to provider_family='manual' for every real provider (a bug found
# while wiring this up: it forced identity_kind='manual' regardless of a
# present native id, which collapsed distinct native ids onto one unique-
# constraint tuple and raised a spurious IntegrityError).
_SOURCE_LABEL_FOR_PROVIDER_FAMILY = {'greenhouse': 'Greenhouse', 'lever': 'Lever', 'ashby': 'Ashby',
                                     'smartrecruiters': 'SmartRecruiters', 'linkedin': 'LinkedIn'}


def _observation_to_add_job_data(obs):
    provider_family = obs.get('provider_family', 'manual')
    return {'company': obs.get('employer_name', 'UNKNOWN'), 'title': obs.get('title', ''),
            'location': obs.get('location', 'UNKNOWN'), 'remote_status': obs.get('workplace', 'UNKNOWN'),
            'description': obs.get('description', ''), 'job_url': obs.get('source_url', ''),
            'source': _SOURCE_LABEL_FOR_PROVIDER_FAMILY.get(provider_family, 'Manual'),
            'source_job_id': obs.get('provider_job_id', ''),
            'date_posted': obs.get('posted_at', ''), 'closing_date': obs.get('closing_at', '')}


def stale_link_rate(results):
    """Offline proxy only: the fraction of corpus cases whose
    reference_link_state (a labelled snapshot judgment, not a live check) is
    LIKELY_STALE. This harness performs NO network link validation -- see
    docs/evaluation/FIT_EVALUATION.md.
    """
    pool = list(results)
    stale = [r.id for r in pool if r.reference_link_state == 'LIKELY_STALE']
    rate = _rate(len(stale), len(pool), stale)
    rate['unknown_count'] = sum(1 for r in pool if r.reference_link_state == 'UNKNOWN')
    return rate


# ---------------------------------------------------------------------------
# Canonical report
# ---------------------------------------------------------------------------

def _git_commit():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[1],
                              capture_output=True, text=True, timeout=5,
                              check=True).stdout.strip()
    except Exception:
        return 'UNKNOWN'


def _git_tree_hash():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], cwd=Path(__file__).resolve().parents[1],
                              capture_output=True, text=True, timeout=5,
                              check=True).stdout.strip()
    except Exception:
        return 'UNKNOWN'


def build_report(corpus, corpus_path, results, *, split_filter=None, slice_filters=None,
                  candidate_policy=None, engine='compare', evaluation_view=None):
    """Assemble the single canonical machine-readable report. Deterministic:
    same commit + corpus + ruleset + candidate policy + fixed clock always
    produces the same report (modulo the informational git_commit/corpus_sha
    fields, which are themselves deterministic functions of repository state).
    """
    if evaluation_view is None:
        evaluation_view = LEGACY_VIEW if engine == 'legacy' else (CANDIDATE_VIEW if candidate_policy else BASELINE_VIEW)
    if evaluation_view not in (BASELINE_VIEW, CANDIDATE_VIEW, LEGACY_VIEW):
        raise CorpusError(f'Unsupported evaluation_view {evaluation_view!r}')
    if engine == 'legacy' and evaluation_view != LEGACY_VIEW:
        raise CorpusError('legacy engine requires LEGACY evaluation view')
    if evaluation_view == CANDIDATE_VIEW and candidate_policy is None:
        raise CorpusError('CANDIDATE evaluation view requires a candidate policy')

    filtered = results
    if split_filter:
        filtered = [r for r in filtered if r.split == split_filter]

    metric_results = filtered
    if evaluation_view == CANDIDATE_VIEW:
        metric_results = _as_candidate_view(filtered)

    by_query = {}
    for r in metric_results:
        by_query.setdefault(r.query_id, []).append(r)

    versions = {'assessment_schema': assessment.SCHEMA_VERSION, 'assessment_ruleset': assessment.RULESET_VERSION,
                'taxonomy': career_tracks.VERSION, 'experience_parser': experience_module.VERSION,
                'metric_definition_version': METRIC_DEFINITION_VERSION}

    coverage_total = len(filtered)
    unclear_count = sum(1 for r in filtered if r.reference_label == 'UNCLEAR')
    from collections import Counter
    label_distribution = dict(Counter(r.reference_label for r in filtered))

    if evaluation_view == LEGACY_VIEW:
        primary_metrics = {
            'must_show_false_rejection_rate': _unavailable_rate(),
            'useful_false_rejection_rate': _unavailable_rate(),
            'new_useful_regression_rate': _unavailable_rate(),
            'high_priority_irrelevant_leakage': _unavailable_rate(),
            'broad_irrelevant_leakage': {**_unavailable_rate(), 'low_only': _unavailable_rate()},
        }
        hard_metrics = {code: {**_unavailable_rate(), 'predicted_count': None,
                               'human_allowed_count': None} for code in HARD_REASONS_EVALUATED}
        blocked_metric = {**_unavailable_rate(), 'predicted_count': None, 'human_allowed_count': None}
        ranking_metrics = _unavailable_ranking()
        pairwise_metric = _unavailable_rate()
        bucket_distribution = {label: {} for label in LABELS}
    else:
        primary_metrics = {
            'must_show_false_rejection_rate': must_show_false_rejection(metric_results),
            'useful_false_rejection_rate': useful_false_rejection(metric_results),
            'new_useful_regression_rate': new_useful_regression(metric_results),
            'high_priority_irrelevant_leakage': high_priority_leakage(metric_results),
            'broad_irrelevant_leakage': broad_leakage(metric_results),
        }
        hard_metrics = hard_reason_precision(metric_results)
        blocked_metric = user_blocked_check(metric_results)
        ranking_metrics = precision_recall_ndcg_at_k(by_query, k=10)
        pairwise_metric = pairwise_ordering_agreement(by_query)
        bucket_distribution = bucket_distribution_by_label(metric_results)

    owner_count = sum(1 for r in filtered if r.reference_status == 'OWNER_ADJUDICATED')
    proposed_count = sum(1 for r in filtered if r.reference_status == 'PROPOSED')
    if filtered and owner_count == len(filtered):
        label_caveat = ('Reference labels are Owner-adjudicated (reference_status '
                        'OWNER_ADJUDICATED); this is the repository Owner\'s individual review and '
                        'rationale recorded per case (see docs/evaluation/FIT_LABEL_REVIEW.md), not a '
                        'multi-human consensus or independently human-labelled benchmark.')
    elif filtered and proposed_count == len(filtered):
        label_caveat = ('Reference labels are Claude-authored proposals, carry reference_status PROPOSED, '
                        'and are not independent human or Owner-approved ground truth.')
    elif filtered:
        label_caveat = (f'Reference-label provenance is mixed: {owner_count} OWNER_ADJUDICATED and '
                        f'{proposed_count} PROPOSED. Metrics are not a fully Owner-adjudicated benchmark; '
                        'inspect each per-case reference_status before interpreting results.')
    else:
        label_caveat = 'No reference-labelled cases are included in this report.'

    evaluated_commit = _git_commit()
    evaluated_tree_hash = _git_tree_hash()
    report = {
        'report_schema_version': REPORT_SCHEMA_VERSION,
        'corpus_schema_version': corpus['corpus_schema_version'],
        'corpus_content_version': corpus['corpus_content_version'],
        'human_label_version': corpus['human_label_version'],
        'metric_definition_version': corpus['metric_definition_version'],
        'corpus_sha256': hashlib.sha256(Path(corpus_path).read_bytes()).hexdigest(),
        'git_commit': evaluated_commit,
        'provenance': {
            'evaluated_commit': evaluated_commit,
            'evaluated_tree_hash': evaluated_tree_hash,
            'report_snapshot_note': 'Committed reports are generated from this clean evaluated commit and may be stored in a later report-only commit.',
        },
        'versions': versions,
        'engine': engine,
        'evaluation_view': evaluation_view,
        'split_filter': split_filter,
        'slice_filters': slice_filters or {},
        'candidate_policy': {'schema_version': candidate_policy.schema_version, 'id': candidate_policy.id,
                             'hash': candidate_policy.content_hash()} if candidate_policy else None,
        'coverage': {'total_cases': coverage_total, 'query_sets': len(by_query),
                    'unclear_count': unclear_count, 'reference_label_distribution': label_distribution},
        'primary_metrics': primary_metrics,
        'hard_reason_precision': hard_metrics,
        'user_blocked_check': blocked_metric,
        'legacy_new_transitions': legacy_new_transitions(filtered),
        'ranking_metrics': ranking_metrics,
        'pairwise_ordering_agreement': pairwise_metric,
        'bucket_distribution_by_reference_label': bucket_distribution,
        'per_case': [r.to_public_dict() for r in sorted(filtered, key=lambda r: r.id)],
        'determinism': {'wall_clock_excluded': True, 'assessment_clock': corpus['fixed_assessment_clock']},
        'caveats': [
            label_caveat,
            'Score means ranking priority, never a probability. score_kind is always RANKING_PRIORITY.',
            'Results measure this corpus only, not global web recall; provider coverage in the corpus is '
            'metadata, never a quality signal.',
            'Thresholds/bucket boundaries and component weights remain provisional (issue #41); no '
            'production default is changed by running this harness.',
        ],
    }
    return report


def _as_candidate_view(results):
    """Reuse every existing metric function unchanged for a candidate policy
    by substituting candidate_bucket/candidate_score in place of
    new_bucket/new_score. hard_reason/legacy fields are untouched (a
    candidate weight policy never changes hard-reject outcomes).
    """
    missing = [r.id for r in results if r.candidate_bucket is None]
    if missing:
        raise CorpusError(f'Candidate evaluation view is missing candidate outcomes for: {missing[:5]}')
    return [replace(r, new_bucket=r.candidate_bucket, new_score=r.candidate_score) for r in results]


def summarize_candidate(results, split=None, evaluation_view=CANDIDATE_VIEW):
    """Bounded summary for one candidate policy over one split: exactly the
    lexicographic criteria Phase 15 asks for, nothing else.
    """
    pool = [r for r in results if split is None or r.split == split]
    if evaluation_view == BASELINE_VIEW:
        view = pool
    elif evaluation_view == CANDIDATE_VIEW:
        view = _as_candidate_view(pool)
    else:
        raise CorpusError(f'Unsupported candidate-summary view {evaluation_view!r}')
    return {
        'split': split or 'all', 'case_count': len(pool),
        'must_show_false_rejection_rate': must_show_false_rejection(view),
        'useful_false_rejection_rate': useful_false_rejection(view),
        'new_useful_regression_rate': new_useful_regression(view),
        'high_priority_irrelevant_leakage': high_priority_leakage(view),
        'ndcg_at_k': precision_recall_ndcg_at_k(_group_by_query(view))['ndcg_at_k'],
    }


def _group_by_query(results):
    by_query = {}
    for r in results:
        by_query.setdefault(r.query_id, []).append(r)
    return by_query


def _lexicographic_key(summary):
    """Lower is better on every criterion, in the Phase 15 priority order:
    (1) eliminate MUST_SHOW rejection, (2) minimize useful false rejection,
    (3) avoid useful legacy-accepted -> new-rejected regressions, (4) control
    STRONG/GOOD irrelevant leakage, (5) improve ordinal quality (1 - nDCG,
    so smaller is better), (6) [deviation from current ruleset is compared
    by the caller, not encoded here, since it depends on which policy is
    "current"].
    """
    def val(m, default=1.0):
        return m['value'] if m['status'] == OK and m['value'] is not None else default
    ndcg = summary['ndcg_at_k']
    return (val(summary['must_show_false_rejection_rate']), val(summary['useful_false_rejection_rate']),
            val(summary['new_useful_regression_rate']), val(summary['high_priority_irrelevant_leakage']),
            1 - (ndcg['value'] if ndcg['status'] == OK and ndcg['value'] is not None else 0.0))


def _policy_deviation(weights):
    return sum(abs(weights[name] - assessment.WEIGHTS[name]) for name in assessment.WEIGHTS)


def evaluate_candidate_policies(corpus, policies, engine='compare'):
    """Run each predeclared candidate policy on development and holdout
    splits. Never picks a "winner" automatically for production -- returns
    the full comparison for the Owner to review (Phase 15: no automatic
    'best candidate' adoption).
    """
    baseline_results = run_corpus(corpus, engine=engine)
    entries = [{
        'id': 'current-ruleset', 'description': f'Unmodified {assessment.RULESET_VERSION} (baseline)',
        'weights': dict(assessment.WEIGHTS), 'hash': 'baseline',
        'development': summarize_candidate(baseline_results, 'development', BASELINE_VIEW),
        'holdout': summarize_candidate(baseline_results, 'holdout', BASELINE_VIEW),
    }]
    for policy in policies:
        results = run_corpus(corpus, engine=engine, candidate_policy=policy)
        entries.append({
            'id': policy.id, 'description': policy.description, 'weights': policy.weights,
            'hash': policy.content_hash(),
            'development': summarize_candidate(results, 'development'),
            'holdout': summarize_candidate(results, 'holdout'),
        })
    baseline_key = _lexicographic_key(entries[0]['development'])
    improving = [entry for entry in entries[1:] if _lexicographic_key(entry['development']) < baseline_key]
    ranked = sorted(improving, key=lambda e: (_lexicographic_key(e['development']),
                                               _policy_deviation(e['weights']), e['id']))
    return {'entries': entries, 'smallest_improvement_candidate_id': ranked[0]['id'] if ranked else None,
            'note': 'PROPOSED comparison only. No candidate is adopted into production defaults by this report; '
                    'Owner review and a code change to backend/assessment.py plus a new ruleset version are '
                    'required before any candidate can become authoritative.'}


# ---------------------------------------------------------------------------
# PROPOSED quality-gate evaluation (Phase 17) -- never an approved gate.
# ---------------------------------------------------------------------------

_GATE_OPERATORS = {
    '<=': lambda observed, threshold: observed <= threshold,
    '>=': lambda observed, threshold: observed >= threshold,
    '==': lambda observed, threshold: observed == threshold,
}


def _supported_gate_metrics():
    primary = {
        'primary_metrics.must_show_false_rejection_rate',
        'primary_metrics.useful_false_rejection_rate',
        'primary_metrics.new_useful_regression_rate',
        'primary_metrics.high_priority_irrelevant_leakage',
        'primary_metrics.broad_irrelevant_leakage',
    }
    hard = {f'hard_reason_precision.{code}' for code in HARD_REASONS_EVALUATED}
    return primary | hard | {'user_blocked_check'}


def validate_quality_gate(gate):
    if not isinstance(gate, dict):
        raise CorpusError('Quality gate root must be a JSON object')
    for key in ('gate_schema_version', 'id', 'approval_state', 'target_engine', 'target_view',
                'description', 'required_checks'):
        if key not in gate:
            raise CorpusError(f'Quality gate missing required field: {key}')
    if gate['gate_schema_version'] != QUALITY_GATE_SCHEMA_VERSION:
        raise CorpusError(f"Unsupported gate_schema_version {gate['gate_schema_version']!r}; "
                          f"expected {QUALITY_GATE_SCHEMA_VERSION!r}")
    if not _stable_id(gate['id']):
        raise CorpusError(f'Quality gate id {gate["id"]!r} is invalid')
    if gate['approval_state'] != 'PROPOSED / NOT OWNER-APPROVED':
        raise CorpusError('Quality gate approval_state must remain PROPOSED / NOT OWNER-APPROVED')
    if gate['target_engine'] not in ('new', 'compare'):
        raise CorpusError('Quality gate target_engine must be new or compare')
    if gate['target_view'] not in (BASELINE_VIEW, CANDIDATE_VIEW):
        raise CorpusError('Quality gate target_view must be BASELINE or CANDIDATE')
    if not isinstance(gate['description'], str) or not gate['description'].strip():
        raise CorpusError('Quality gate description must be non-empty text')
    required = gate['required_checks']
    optional = gate.get('optional_checks', [])
    if not isinstance(required, list) or not required:
        raise CorpusError('Quality gate must define at least one required check')
    if not isinstance(optional, list):
        raise CorpusError('Quality gate optional_checks must be a list')
    supported = _supported_gate_metrics()
    seen_names = set()
    for required_flag, checks in ((True, required), (False, optional)):
        for i, check in enumerate(checks):
            where = f'{"required" if required_flag else "optional"}_checks[{i}]'
            if not isinstance(check, dict):
                raise CorpusError(f'Quality gate {where} must be an object')
            for key in ('name', 'metric', 'operator', 'threshold', 'min_denominator'):
                if key not in check:
                    raise CorpusError(f'Quality gate {where} missing required field: {key}')
            if not _stable_id(check['name']):
                raise CorpusError(f'Quality gate {where} name {check["name"]!r} is invalid')
            if check['name'] in seen_names:
                raise CorpusError(f'Quality gate duplicate check name: {check["name"]!r}')
            seen_names.add(check['name'])
            if check['metric'] not in supported:
                raise CorpusError(f'Quality gate {where} has unsupported metric {check["metric"]!r}')
            if check['operator'] not in _GATE_OPERATORS:
                raise CorpusError(f'Quality gate {where} has unsupported operator {check["operator"]!r}')
            threshold = check['threshold']
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold):
                raise CorpusError(f'Quality gate {where} threshold must be a finite number')
            minimum = check['min_denominator']
            if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
                raise CorpusError(f'Quality gate {where} min_denominator must be a nonnegative integer')
    return gate


def load_quality_gate(path):
    return validate_quality_gate(_read_json_object(path, 'Quality gate'))


def _gate_metric(report, path):
    if path.startswith('primary_metrics.'):
        return report['primary_metrics'][path.split('.', 1)[1]]
    if path.startswith('hard_reason_precision.'):
        return report['hard_reason_precision'][path.split('.', 1)[1]]
    if path == 'user_blocked_check':
        return report['user_blocked_check']
    raise CorpusError(f'Unsupported quality-gate metric {path!r}')


def evaluate_quality_gate(report, gate):
    """Evaluate a validated PROPOSED gate against one explicit report view.

    Every required check must be evaluable and pass before the overall gate
    can PASS. Optional checks may be skipped when data is insufficient.
    """
    validate_quality_gate(gate)
    if report['engine'] != gate['target_engine']:
        raise CorpusError(f'Quality gate targets engine {gate["target_engine"]!r}, '
                          f'but report engine is {report["engine"]!r}')
    if report['evaluation_view'] != gate['target_view']:
        raise CorpusError(f'Quality gate targets view {gate["target_view"]!r}, '
                          f'but report view is {report["evaluation_view"]!r}')
    checks = []
    for required, definitions in ((True, gate['required_checks']), (False, gate.get('optional_checks', []))):
        for definition in definitions:
            metric = _gate_metric(report, definition['metric'])
            denominator = metric.get('denominator')
            insufficient = (metric['status'] in (INSUFFICIENT_DATA, UNAVAILABLE) or
                            denominator is None or denominator < definition['min_denominator'])
            result = {
                'name': definition['name'], 'metric': definition['metric'], 'required': required,
                'operator': definition['operator'], 'threshold': definition['threshold'],
                'min_denominator': definition['min_denominator'], 'denominator': denominator,
            }
            if insufficient:
                result['status'] = INSUFFICIENT_DATA if required else 'SKIPPED_INSUFFICIENT_DATA'
                result['observed'] = metric.get('value')
                result['reason'] = ('METRIC_UNAVAILABLE' if metric['status'] == UNAVAILABLE else
                                    'DENOMINATOR_BELOW_MINIMUM')
            else:
                result['observed'] = metric['value']
                passed = _GATE_OPERATORS[definition['operator']](metric['value'], definition['threshold'])
                result['status'] = 'PASS' if passed else 'FAIL'
            checks.append(result)

    required_results = [check for check in checks if check['required']]
    if any(check['status'] == 'FAIL' for check in required_results):
        overall = 'FAIL'
    elif any(check['status'] == INSUFFICIENT_DATA for check in required_results):
        overall = INSUFFICIENT_DATA
    else:
        overall = 'PASS'
    return {'gate_schema_version': gate['gate_schema_version'], 'gate_id': gate['id'],
            'gate_status': overall, 'target_engine': gate['target_engine'],
            'target_view': gate['target_view'], 'checks': checks,
            'approval_state': gate['approval_state']}


# ---------------------------------------------------------------------------
# Human-readable Markdown report -- generated from the canonical JSON report,
# never hand-maintained separately (Phase 12).
# ---------------------------------------------------------------------------

def render_markdown(report, calibration=None, gate_result=None):
    def fmt(m):
        if m['status'] == INSUFFICIENT_DATA:
            return '_insufficient data_'
        if m['status'] == UNAVAILABLE:
            return '_unavailable for this engine/view_'
        if 'numerator' in m:
            return f"**{m['value']:.4f}** ({m['numerator']}/{m['denominator']})"
        return f"**{m['value']:.4f}**"

    lines = ['# Fit assessment evaluation report', '',
             '_Generated from `backend.evaluation`\'s canonical machine-readable output -- not hand-maintained._',
             '',
             f"- Corpus: `{report['corpus_content_version']}` ({report['coverage']['total_cases']} cases, "
             f"{report['coverage']['query_sets']} query sets, {report['coverage']['unclear_count']} UNCLEAR)",
             f"- Code: assessment schema `{report['versions']['assessment_schema']}`, ruleset "
             f"`{report['versions']['assessment_ruleset']}`, taxonomy `{report['versions']['taxonomy']}`, "
             f"experience parser `{report['versions']['experience_parser']}`",
             f"- Evaluated commit: `{report['provenance']['evaluated_commit']}`",
             f"- Evaluated tree: `{report['provenance']['evaluated_tree_hash']}`",
             f"- Report snapshot: {report['provenance']['report_snapshot_note']}",
             f"- Engine/view: `{report['engine']}` / `{report['evaluation_view']}`",
             '',
             f"> **{report['caveats'][0]}** Score means ranking priority, never a probability or hiring "
             'likelihood. These results measure this corpus only -- not global web recall -- and provider '
             'coverage in the corpus is metadata, never a quality signal. Bucket thresholds and component '
             'weights remain provisional (issue #41); running this harness changes no production default.',
             '',
             '## Coverage', '',
             f"| Reference label | Count |\n|---|---|\n" +
             '\n'.join(f"| {k} | {v} |" for k, v in report['coverage']['reference_label_distribution'].items()),
             '',
             '## Primary metrics', '',
             '| Metric | Value |', '|---|---|']
    for name, m in report['primary_metrics'].items():
        lines.append(f"| {name} | {fmt(m)} |")
    lines += ['', '## Hard-reason precision', '', '| Reason | Precision | Predicted |', '|---|---|---|']
    for code, m in report['hard_reason_precision'].items():
        lines.append(f"| {code} | {fmt(m)} | {m['predicted_count']} |")
    lines.append(f"| USER_BLOCKED | {fmt(report['user_blocked_check'])} | "
                 f"{report['user_blocked_check']['predicted_count']} |")
    lines += ['', '## Ranking quality', '',
             f"- Precision@10: {report['ranking_metrics']['precision_at_k']['value']}",
             f"- Recall@K: {report['ranking_metrics']['recall_at_k']['value']}",
             f"- nDCG@10: {report['ranking_metrics']['ndcg_at_k']['value']}",
             f"- Pairwise ordering agreement: {fmt(report['pairwise_ordering_agreement'])}",
             '', '## Legacy vs new engine', '',
             f"- Category counts: `{report['legacy_new_transitions']['category_counts']}`",
             f"- New regressions (reference-useful, highest review priority): "
             f"`{report['legacy_new_transitions']['new_regression_case_ids_reference_useful']}`",
             f"- Recovered useful cases: "
             f"{len(report['legacy_new_transitions']['recovered_case_ids_reference_useful'])}",
             '']
    if 'duplicate_rate' in report:
        dr = report['duplicate_rate']
        lines += ['## Duplicate / stale-link', '',
                 f"- Dedupe recall (issue #40 corpus, isolated in-memory DB): {fmt(dr['dedupe_recall_rate'])}",
                 f"- False-merge rate: {fmt(dr['false_merge_rate'])}",
                 f"- Stale-link rate (labelled snapshot proxy, no live check): {fmt(report['stale_link_rate'])}",
                 '']
    if calibration:
        lines += ['## Calibration candidates (PROPOSED, not adopted)', '',
                 '| Policy | Split | MUST_SHOW FR | Useful FR | HP leakage | nDCG@10 |',
                 '|---|---|---|---|---|---|']
        for entry in calibration['entries']:
            for split in ('development', 'holdout'):
                s = entry[split]
                lines.append(f"| {entry['id']} | {split} | "
                             f"{fmt(s['must_show_false_rejection_rate'])} | {fmt(s['useful_false_rejection_rate'])} | "
                             f"{fmt(s['high_priority_irrelevant_leakage'])} | {fmt(s['ndcg_at_k'])} |")
        improving = calibration['smallest_improvement_candidate_id']
        improving_text = improving if improving is not None else 'none (no candidate improves the real baseline)'
        lines += ['', f"Smallest-deviation improving candidate (development split): "
                     f"**{improving_text}**", '', calibration['note'], '']
    if gate_result:
        lines += ['## PROPOSED quality gate (NOT Owner-approved)', '',
                 f"Overall: **{gate_result['gate_status']}**", '',
                 '| Check | Status | Threshold | Observed |', '|---|---|---|---|']
        for c in gate_result['checks']:
            observed = c.get('observed', '')
            if c.get('reason'):
                observed = f"{observed} ({c['reason']}; denominator={c.get('denominator')}, minimum={c.get('min_denominator')})"
            lines.append(f"| {c['name']} | {c['status']} | {c.get('operator', '')} {c.get('threshold', '')} | {observed} |")
        lines.append('')
    lines += ['## Top failures', '']
    for name, m in report['primary_metrics'].items():
        if m['status'] == OK and m['failing_case_ids']:
            lines.append(f"- **{name}**: {', '.join(m['failing_case_ids'])}")
    lines += ['', '---', '', f"Report schema `{report['report_schema_version']}`, "
             f"metric definitions `{report['metric_definition_version']}`, "
             f"corpus SHA-256 `{report['corpus_sha256'][:16]}...`"]
    return '\n'.join(lines) + '\n'


def report_to_json(report):
    """Deterministic serialization: sorted keys, fixed float formatting, no
    trailing wall-clock/path noise.
    """
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + '\n'

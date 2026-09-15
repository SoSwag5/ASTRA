"""Issue #42: offline evaluation + bounded calibration harness for issue #41's
FitAssessment engine.

Pure, deterministic, network-free. Consumes the REAL production engine
(`backend.assessment.assess`, `backend.recall.evaluate_legacy`,
`backend.recall.evaluate`) -- this module never recomputes a score or
reimplements domain/seniority/geography classification.

Reference labels (MUST_SHOW / REASONABLE_STRETCH / LOW_BUT_USEFUL /
GENUINE_REJECTION / UNCLEAR) are an evaluation-only concept, independent of
system buckets (STRONG/GOOD/STRETCH/LOW/REJECTED) -- see
docs/evaluation/FIT_EVALUATION.md. Every reference label in the shipped
corpus carries `reference_status: "PROPOSED"`; nothing in this module (or
anything that calls it) may treat a proposed label as Owner-approved ground
truth.
"""
import hashlib
import json
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

REPORT_SCHEMA_VERSION = 'fit-eval-report-1'
METRIC_DEFINITION_VERSION = 'metrics-v1'

LABELS = ('MUST_SHOW', 'REASONABLE_STRETCH', 'LOW_BUT_USEFUL', 'GENUINE_REJECTION', 'UNCLEAR')
USEFUL_LABELS = ('MUST_SHOW', 'REASONABLE_STRETCH', 'LOW_BUT_USEFUL')
DEFAULT_GAINS = {'MUST_SHOW': 3, 'REASONABLE_STRETCH': 2, 'LOW_BUT_USEFUL': 1, 'GENUINE_REJECTION': 0}
HARD_REASONS_EVALUATED = ('DOMAIN_INCOMPATIBLE', 'GEO_INCOMPATIBLE', 'EXTREME_LEADERSHIP_MISMATCH',
                          'CONFIRMED_ELIGIBILITY_CONFLICT')
BUCKET_ORDER = {'STRONG': 4, 'GOOD': 3, 'STRETCH': 2, 'LOW': 1, 'REJECTED': 0}
INSUFFICIENT_DATA = 'INSUFFICIENT_DATA'
OK = 'OK'


class CorpusError(ValueError):
    """A structural problem with an evaluation corpus file."""


# ---------------------------------------------------------------------------
# Corpus loading and validation
# ---------------------------------------------------------------------------

def load_corpus(path):
    """Load and validate a versioned evaluation corpus. Raises CorpusError
    with a specific, actionable message on any structural problem -- this
    harness never silently tolerates a malformed corpus.
    """
    raw = Path(path).read_text(encoding='utf-8')
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise CorpusError(f'Corpus is not valid JSON: {e}') from e

    for key in ('corpus_schema_version', 'corpus_content_version', 'human_label_version',
                'metric_definition_version', 'fixed_assessment_clock', 'cases'):
        if key not in data:
            raise CorpusError(f'Corpus is missing required top-level key: {key}')
    if data['corpus_schema_version'] != 'fit-eval-corpus-1':
        raise CorpusError(f"Unsupported corpus_schema_version {data['corpus_schema_version']!r}; "
                           "this harness only understands 'fit-eval-corpus-1'. Refusing to guess.")
    try:
        datetime.fromisoformat(data['fixed_assessment_clock'].replace('Z', '+00:00'))
    except (ValueError, AttributeError) as e:
        raise CorpusError(f'fixed_assessment_clock is not a valid ISO-8601 timestamp: {e}') from e

    cases = data['cases']
    if not isinstance(cases, list) or not cases:
        raise CorpusError('Corpus cases must be a non-empty list')

    seen_ids = set()
    query_ids = {}
    for i, case in enumerate(cases):
        where = f'case[{i}]'
        for key in ('id', 'query_id', 'source_kind', 'job', 'reference_label', 'reference_status',
                    'human_reason', 'allowed_hard_reasons', 'reference_link_state'):
            if key not in case:
                raise CorpusError(f'{where}: missing required field {key!r}')
        cid = case['id']
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,80}', cid):
            raise CorpusError(f'{where}: id {cid!r} is not a stable lowercase-kebab identifier')
        if cid in seen_ids:
            raise CorpusError(f'Duplicate case id: {cid!r}')
        seen_ids.add(cid)
        if case['reference_label'] not in LABELS:
            raise CorpusError(f'{where} ({cid}): invalid reference_label {case["reference_label"]!r}; '
                               f'must be one of {LABELS}')
        if not isinstance(case['allowed_hard_reasons'], list):
            raise CorpusError(f'{where} ({cid}): allowed_hard_reasons must be a list')
        if case['reference_label'] != 'GENUINE_REJECTION' and case['allowed_hard_reasons']:
            raise CorpusError(f'{where} ({cid}): allowed_hard_reasons is only meaningful for '
                               'GENUINE_REJECTION cases')
        if case['reference_link_state'] not in ('LIKELY_LIVE', 'LIKELY_STALE', 'UNKNOWN'):
            raise CorpusError(f'{where} ({cid}): invalid reference_link_state {case["reference_link_state"]!r}')
        job = case['job']
        if not isinstance(job, dict) or not job.get('title'):
            raise CorpusError(f'{where} ({cid}): job.title is required')
        query_ids.setdefault(case['query_id'], []).append(cid)

    if len(query_ids) < 1:
        raise CorpusError('Corpus has no query sets')
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
    id: str
    description: str
    weights: dict  # component -> weight (must sum to 100)
    bucket_floors: list = field(default_factory=lambda: list(assessment.BUCKET_FLOORS))

    def content_hash(self):
        payload = json.dumps({'weights': self.weights, 'bucket_floors': self.bucket_floors}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_candidate_policy(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    for key in ('id', 'description', 'weights'):
        if key not in data:
            raise CorpusError(f'Candidate policy missing required field: {key}')
    if set(data['weights']) != set(assessment.WEIGHTS):
        raise CorpusError(f'Candidate policy weights must cover exactly {sorted(assessment.WEIGHTS)}')
    if abs(sum(data['weights'].values()) - 100) > 0.01:
        raise CorpusError('Candidate policy weights must sum to 100')
    floors = data.get('bucket_floors')
    if floors is not None:
        floors = [tuple(f) for f in floors]
    return CandidatePolicy(id=data['id'], description=data['description'], weights=data['weights'],
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
        ndcg = (dcg / idcg) if idcg > 0 else (1.0 if dcg == 0 else None)
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
        return subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=5,
                              check=True).stdout.strip()
    except Exception:
        return 'UNKNOWN'


def build_report(corpus, corpus_path, results, *, split_filter=None, slice_filters=None,
                  candidate_policy=None, engine='compare'):
    """Assemble the single canonical machine-readable report. Deterministic:
    same commit + corpus + ruleset + candidate policy + fixed clock always
    produces the same report (modulo the informational git_commit/corpus_sha
    fields, which are themselves deterministic functions of repository state).
    """
    filtered = results
    if split_filter:
        filtered = [r for r in filtered if r.split == split_filter]

    by_query = {}
    for r in filtered:
        by_query.setdefault(r.query_id, []).append(r)

    versions = {'assessment_schema': assessment.SCHEMA_VERSION, 'assessment_ruleset': assessment.RULESET_VERSION,
                'taxonomy': career_tracks.VERSION, 'experience_parser': experience_module.VERSION,
                'metric_definition_version': METRIC_DEFINITION_VERSION}

    coverage_total = len(filtered)
    unclear_count = sum(1 for r in filtered if r.reference_label == 'UNCLEAR')
    from collections import Counter
    label_distribution = dict(Counter(r.reference_label for r in filtered))

    report = {
        'report_schema_version': REPORT_SCHEMA_VERSION,
        'corpus_schema_version': corpus['corpus_schema_version'],
        'corpus_content_version': corpus['corpus_content_version'],
        'human_label_version': corpus['human_label_version'],
        'metric_definition_version': METRIC_DEFINITION_VERSION,
        'corpus_sha256': hashlib.sha256(Path(corpus_path).read_bytes()).hexdigest(),
        'git_commit': _git_commit(),
        'versions': versions,
        'engine': engine,
        'split_filter': split_filter,
        'slice_filters': slice_filters or {},
        'candidate_policy': {'id': candidate_policy.id, 'hash': candidate_policy.content_hash()} if candidate_policy else None,
        'coverage': {'total_cases': coverage_total, 'query_sets': len(by_query),
                    'unclear_count': unclear_count, 'reference_label_distribution': label_distribution},
        'primary_metrics': {
            'must_show_false_rejection_rate': must_show_false_rejection(filtered),
            'useful_false_rejection_rate': useful_false_rejection(filtered),
            'new_useful_regression_rate': new_useful_regression(filtered),
            'high_priority_irrelevant_leakage': high_priority_leakage(filtered),
            'broad_irrelevant_leakage': broad_leakage(filtered),
        },
        'hard_reason_precision': hard_reason_precision(filtered),
        'user_blocked_check': user_blocked_check(filtered),
        'legacy_new_transitions': legacy_new_transitions(filtered),
        'ranking_metrics': precision_recall_ndcg_at_k(by_query, k=10),
        'pairwise_ordering_agreement': pairwise_ordering_agreement(by_query),
        'bucket_distribution_by_reference_label': bucket_distribution_by_label(filtered),
        'per_case': [r.to_public_dict() for r in sorted(filtered, key=lambda r: r.id)],
        'determinism': {'wall_clock_excluded': True, 'assessment_clock': corpus['fixed_assessment_clock']},
        'caveats': [
            'Reference labels carry reference_status PROPOSED and are not yet Owner-approved ground truth.',
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
    return [replace(r, new_bucket=r.candidate_bucket, new_score=r.candidate_score) for r in results]


def summarize_candidate(results, split=None):
    """Bounded summary for one candidate policy over one split: exactly the
    lexicographic criteria Phase 15 asks for, nothing else.
    """
    pool = [r for r in results if split is None or r.split == split]
    view = _as_candidate_view(pool)
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
        'development': summarize_candidate(baseline_results, 'development'),
        'holdout': summarize_candidate(baseline_results, 'holdout'),
    }]
    for policy in policies:
        results = run_corpus(corpus, engine=engine, candidate_policy=policy)
        entries.append({
            'id': policy.id, 'description': policy.description, 'weights': policy.weights,
            'hash': policy.content_hash(),
            'development': summarize_candidate(results, 'development'),
            'holdout': summarize_candidate(results, 'holdout'),
        })
    ranked = sorted(entries[1:], key=lambda e: _lexicographic_key(e['development']))
    return {'entries': entries, 'smallest_improvement_candidate_id': ranked[0]['id'] if ranked else None,
            'note': 'PROPOSED comparison only. No candidate is adopted into production defaults by this report; '
                    'Owner review and a code change to backend/assessment.py plus a new ruleset version are '
                    'required before any candidate can become authoritative.'}


# ---------------------------------------------------------------------------
# PROPOSED quality-gate evaluation (Phase 17) -- never an approved gate.
# ---------------------------------------------------------------------------

def evaluate_quality_gate(report, gate):
    """Evaluate a PROPOSED gate policy against an already-built report.
    `gate` is a dict of bounded thresholds; every check is skipped (not
    failed) when its metric is INSUFFICIENT_DATA -- an untested hard reason
    must never silently pass or fail a gate.
    """
    checks = []

    def check(name, metric, threshold, comparison='<='):
        if metric['status'] == INSUFFICIENT_DATA:
            checks.append({'name': name, 'status': 'SKIPPED_INSUFFICIENT_DATA', 'threshold': threshold})
            return
        passed = metric['value'] <= threshold if comparison == '<=' else metric['value'] >= threshold
        checks.append({'name': name, 'status': 'PASS' if passed else 'FAIL', 'threshold': threshold,
                       'observed': metric['value']})

    pm = report['primary_metrics']
    if 'max_must_show_false_rejection_rate' in gate:
        check('max_must_show_false_rejection_rate', pm['must_show_false_rejection_rate'],
              gate['max_must_show_false_rejection_rate'])
    if 'max_useful_false_rejection_rate' in gate:
        check('max_useful_false_rejection_rate', pm['useful_false_rejection_rate'],
              gate['max_useful_false_rejection_rate'])
    if 'max_high_priority_leakage' in gate:
        check('max_high_priority_leakage', pm['high_priority_irrelevant_leakage'],
              gate['max_high_priority_leakage'])
    if gate.get('forbid_useful_legacy_accepted_new_rejected'):
        m = pm['new_useful_regression_rate']
        checks.append({'name': 'forbid_useful_legacy_accepted_new_rejected',
                       'status': 'SKIPPED_INSUFFICIENT_DATA' if m['status'] == INSUFFICIENT_DATA else
                                 ('PASS' if m['numerator'] == 0 else 'FAIL'),
                       'observed': m['numerator']})
    if 'min_hard_reason_sample_size' in gate:
        for code, m in report['hard_reason_precision'].items():
            checks.append({'name': f'min_hard_reason_sample_size[{code}]',
                           'status': 'PASS' if m['predicted_count'] >= gate['min_hard_reason_sample_size'] else 'FAIL',
                           'threshold': gate['min_hard_reason_sample_size'], 'observed': m['predicted_count']})
    overall = 'PASS' if all(c['status'] in ('PASS', 'SKIPPED_INSUFFICIENT_DATA') for c in checks) else 'FAIL'
    return {'gate_status': overall, 'checks': checks,
            'approval_state': 'PROPOSED / NOT OWNER-APPROVED'}


# ---------------------------------------------------------------------------
# Human-readable Markdown report -- generated from the canonical JSON report,
# never hand-maintained separately (Phase 12).
# ---------------------------------------------------------------------------

def render_markdown(report, calibration=None, gate_result=None):
    def fmt(m):
        if m['status'] == INSUFFICIENT_DATA:
            return '_insufficient data_'
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
             f"- Git commit: `{report['git_commit']}`",
             f"- Engine: `{report['engine']}`",
             '',
             '> **Reference labels in this corpus carry `reference_status: PROPOSED` and are NOT yet '
             'Owner-approved ground truth.** Score means ranking priority, never a probability or hiring '
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
        lines += ['', f"Smallest-deviation improving candidate (development split): "
                     f"**{calibration['smallest_improvement_candidate_id']}**", '', calibration['note'], '']
    if gate_result:
        lines += ['## PROPOSED quality gate (NOT Owner-approved)', '',
                 f"Overall: **{gate_result['gate_status']}**", '',
                 '| Check | Status | Threshold | Observed |', '|---|---|---|---|']
        for c in gate_result['checks']:
            lines.append(f"| {c['name']} | {c['status']} | {c.get('threshold', '')} | {c.get('observed', '')} |")
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

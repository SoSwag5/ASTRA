#!/usr/bin/env python
"""Issue #42: offline CLI for backend.evaluation.

Network-free, deterministic. Examples:

  python scripts/evaluate_fit.py
  python scripts/evaluate_fit.py --case cyber_soc_security_engineering-01
  python scripts/evaluate_fit.py --query cyber_soc_security_engineering
  python scripts/evaluate_fit.py --slice domain=cloud_security
  python scripts/evaluate_fit.py --engine new
  python scripts/evaluate_fit.py --engine compare --format json > report.json
  python scripts/evaluate_fit.py --split holdout
  python scripts/evaluate_fit.py --candidate-policy path/to/policy.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import evaluation as ev

DEFAULT_CORPUS = 'tests/fixtures/fit_evaluation_v1.json'


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--corpus', default=DEFAULT_CORPUS, help=f'Evaluation corpus path (default: {DEFAULT_CORPUS})')
    p.add_argument('--case', help='Run exactly one case by id')
    p.add_argument('--query', help='Run exactly one query set by id')
    p.add_argument('--slice', action='append', default=[], metavar='TAG=VALUE',
                   help='Filter to cases whose tags[TAG] == VALUE; may be given multiple times')
    p.add_argument('--split', choices=('development', 'holdout'), help='Restrict to one split')
    p.add_argument('--engine', choices=('new', 'legacy', 'compare'), default='compare',
                   help='Which engine(s) to run (default: compare)')
    p.add_argument('--candidate-policy', help='Path to a candidate weight-policy JSON file (recomposes this run only)')
    p.add_argument('--calibration', action='append', default=[], metavar='POLICY.json',
                   help='Compare a predeclared candidate policy against the baseline on dev/holdout splits; '
                        'may be given multiple times. Never modifies production defaults.')
    p.add_argument('--gate', help='Path to a PROPOSED quality-gate policy JSON file to evaluate (not an approved gate)')
    p.add_argument('--format', choices=('json', 'text', 'markdown'), default='text', help='Output format (default: text)')
    p.add_argument('--dedupe', action='store_true', help='Also compute the #40 duplicate-rate and stale-link metrics')
    return p.parse_args(argv)


def build_case_filter(args):
    filters = []
    if args.case:
        filters.append(lambda c: c['id'] == args.case)
    if args.query:
        filters.append(lambda c: c['query_id'] == args.query)
    slice_filters = {}
    for item in args.slice:
        if '=' not in item:
            raise SystemExit(f'--slice must be TAG=VALUE, got: {item!r}')
        tag, value = item.split('=', 1)
        slice_filters[tag] = value
        filters.append(lambda c, tag=tag, value=value: c.get('tags', {}).get(tag) == value)
    if args.split:
        filters.append(lambda c: c.get('split', 'development') == args.split)

    def combined(case):
        return all(f(case) for f in filters)
    return (combined if filters else None), slice_filters


def render_text(report):
    lines = []
    lines.append(f"Corpus: {report['corpus_content_version']} ({report['coverage']['total_cases']} cases, "
                 f"{report['coverage']['query_sets']} query sets, {report['coverage']['unclear_count']} UNCLEAR)")
    lines.append(f"Engine: {report['engine']}   Git commit: {report['git_commit']}")
    lines.append('')
    lines.append('Primary metrics:')
    for name, m in report['primary_metrics'].items():
        lines.append(f"  {name}: {_fmt_rate(m)}")
    lines.append('')
    lines.append('Hard-reason precision:')
    for code, m in report['hard_reason_precision'].items():
        lines.append(f"  {code}: {_fmt_rate(m)} (predicted={m['predicted_count']})")
    lines.append(f"  USER_BLOCKED: {_fmt_rate(report['user_blocked_check'])}")
    lines.append('')
    lines.append('Ranking:')
    rm = report['ranking_metrics']
    lines.append(f"  Precision@10: {_fmt_value(rm['precision_at_k'])}")
    lines.append(f"  Recall@K: {_fmt_value(rm['recall_at_k'])}")
    lines.append(f"  nDCG@10: {_fmt_value(rm['ndcg_at_k'])}")
    lines.append(f"  Pairwise ordering agreement: {_fmt_rate(report['pairwise_ordering_agreement'])}")
    lines.append('')
    lines.append('Legacy vs new:')
    lt = report['legacy_new_transitions']
    lines.append(f"  category counts: {lt['category_counts']}")
    lines.append(f"  new regressions (reference-useful): {lt['new_regression_case_ids_reference_useful']}")
    return '\n'.join(lines)


def _fmt_rate(m):
    if m['status'] == ev.INSUFFICIENT_DATA:
        return 'INSUFFICIENT_DATA (denominator=0)'
    return f"{m['value']:.4f} ({m['numerator']}/{m['denominator']})"


def _fmt_value(m):
    if m['status'] == ev.INSUFFICIENT_DATA:
        return 'INSUFFICIENT_DATA'
    return f"{m['value']:.4f} (over {m['query_sets_scored']} query sets)"


def main(argv=None):
    args = parse_args(argv)
    try:
        corpus = ev.load_corpus(args.corpus)
    except ev.CorpusError as e:
        print(f'Corpus error: {e}', file=sys.stderr)
        return 2

    candidate_policy = None
    if args.candidate_policy:
        try:
            candidate_policy = ev.load_candidate_policy(args.candidate_policy)
        except ev.CorpusError as e:
            print(f'Candidate policy error: {e}', file=sys.stderr)
            return 2

    case_filter, slice_filters = build_case_filter(args)
    try:
        results = ev.run_corpus(corpus, engine=args.engine, case_filter=case_filter, candidate_policy=candidate_policy)
    except Exception as e:
        print(f'Evaluation error: {e}', file=sys.stderr)
        return 2
    if not results:
        print('No cases matched the given filters.', file=sys.stderr)
        return 2

    report = ev.build_report(corpus, args.corpus, results, split_filter=args.split, slice_filters=slice_filters,
                             candidate_policy=candidate_policy, engine=args.engine)
    if args.dedupe:
        report['duplicate_rate'] = ev.duplicate_rate()
        report['stale_link_rate'] = ev.stale_link_rate(results)

    calibration = None
    if args.calibration:
        try:
            policies = [ev.load_candidate_policy(p) for p in args.calibration]
        except ev.CorpusError as e:
            print(f'Calibration policy error: {e}', file=sys.stderr)
            return 2
        calibration = ev.evaluate_candidate_policies(corpus, policies, engine=args.engine)

    gate_result = None
    if args.gate:
        gate = json.loads(Path(args.gate).read_text(encoding='utf-8'))
        gate_result = ev.evaluate_quality_gate(report, gate)

    if args.format == 'json':
        out = dict(report)
        if calibration is not None:
            out['calibration'] = calibration
        if gate_result is not None:
            out['quality_gate'] = gate_result
        print(ev.report_to_json(out), end='')
    elif args.format == 'markdown':
        print(ev.render_markdown(report, calibration=calibration, gate_result=gate_result), end='')
    else:
        print(render_text(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

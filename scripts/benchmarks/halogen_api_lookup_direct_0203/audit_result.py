"""Recalculate the saved CPU comparison; no tokenizer/engine dependency."""
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics


def pin(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def audit(path):
    value = json.loads(Path(path).read_bytes())
    assert value['schema'] == 'halogen0203.cpu-lookup-direct-backend.v1'
    assert value['terminal'] and value['completed'] and value['parity_passed']
    assert value['engine_HTTP_GPU_NPU_calls'] is False
    assert value['model_weights_accessed'] is False
    assert value['tok_s_or_acceptance_gain_qualified'] is False
    assert value['environment_before'] == value['environment_after']
    assert value['tokenizer_files_before'] == value['tokenizer_files_after']
    assert value['iterations'] == 21 and len(value['fixtures']) == 8
    assert len(value['warmups']) == 16 and len(value['raw_pairs']) == 168
    assert value['untimed_parity']['passed'] and value['contracts']['passed']
    proof = value['direct_backend_usage']
    assert proof['proven'] and proof['candidate_namespace_enabled'] and proof['actual_type_binding']
    assert proof['untimed_only'] and proof['timing_profiler_used'] is False
    assert proof['actual_HF_wrapper_calls'] == {'stock': 85, 'direct_backend_scalar': 0}
    assert proof['bound_classes'] == ['transformers.models.qwen2.tokenization_qwen2.Qwen2Tokenizer', 'tokenizers.Tokenizer', 'tokenizers.models.BPE']
    assert value['untimed_parity']['actual_HF_object_used'] and value['untimed_parity']['profiler_restored']
    assert value['untimed_parity']['native_encoding_call_reduction_claimed'] is False
    rows = []
    for index, fixture in enumerate(value['fixtures']):
        name = fixture['name']
        warmups = [row for row in value['warmups'] if row['case'] == name]
        assert collections.Counter(row['arm'] for row in warmups) == {'stock': 1, 'direct_backend_scalar': 1}
        assert all(row['excluded_warmup'] for row in warmups)
        pairs = [row for row in value['raw_pairs'] if row['case'] == name]
        assert [row['iteration'] for row in pairs] == list(range(21))
        timings = dict(stock=[], direct_backend_scalar=[])
        for pair in pairs:
            assert pair['parity'] and set(pair['arms']) == {'stock', 'direct_backend_scalar'}
            assert pair['order'] == (['stock', 'direct_backend_scalar'] if (index + pair['iteration']) % 2 == 0 else ['direct_backend_scalar', 'stock'])
            assert pair['arms']['stock']['output_counts'] == pair['arms']['direct_backend_scalar']['output_counts']
            assert pair['arms']['stock']['output_sha256'] == pair['arms']['direct_backend_scalar']['output_sha256']
            for arm, sample in pair['arms'].items():
                assert not sample['counter_wrapper_used']
                assert sample['cache_mode'] == fixture['cache_mode']
                assert sample['primed_outside_timing'] == (fixture['cache_mode'] == 'warm')
                assert len(sample['call_ns']) == fixture['repetitions']
                assert all(type(ns) is int and ns > 0 for ns in sample['call_ns'])
                assert sum(sample['call_ns']) == sample['total_lookup_ns']
                timings[arm].append(sample['total_lookup_ns'])
        recalculated = {}
        for arm in ('stock', 'direct_backend_scalar'):
            ns = timings[arm]
            stats = dict(mean_ns=statistics.fmean(ns), median_ns=statistics.median(ns),
                         min_ns=min(ns), max_ns=max(ns), stdev_ns=statistics.stdev(ns))
            assert stats == value['aggregates'][name][arm]
            recalculated[arm] = stats
        differences = [candidate - stock for stock, candidate in zip(timings['stock'], timings['direct_backend_scalar'])]
        assert differences == value['aggregates'][name]['paired_difference_ns']
        percent = (recalculated['direct_backend_scalar']['mean_ns'] / recalculated['stock']['mean_ns'] - 1) * 100
        assert percent == value['aggregates'][name]['direct_backend_scalar_vs_stock_mean_percent']
        rows.append(dict(name=name, cache_mode=fixture['cache_mode'], pairs=21,
            measured_calls_per_observation=fixture['repetitions'], **recalculated,
            direct_backend_scalar_mean_change_percent=percent,
            direct_backend_scalar_slower_pairs=sum(delta > 0 for delta in differences),
            stock_first_pairs=sum(pair['order'][0] == 'stock' for pair in pairs)))
    for row in rows:
        selected = [pair for pair in value['raw_pairs'] if pair['case'] == row['name']]
        saved = [pair['arms']['stock']['total_lookup_ns'] - pair['arms']['direct_backend_scalar']['total_lookup_ns'] for pair in selected]
        row['mean_saved_ns'] = row['stock']['mean_ns'] - row['direct_backend_scalar']['mean_ns']
        row['median_paired_saved_ns'] = statistics.median(saved)
        row['direct_faster_pairs'] = sum(ns > 0 for ns in saved)
    return dict(schema='halogen0203.cpu-lookup-direct-backend-recalculation.v1',
        utc=datetime.now(timezone.utc).isoformat(), source_result=pin(path),
        independent_raw_arithmetic_passed=True, cases=rows,
        warmups_excluded=16, measured_pairs=168,
        stock_first_pairs=sum(row['stock_first_pairs'] for row in rows),
        direct_first_pairs=168 - sum(row['stock_first_pairs'] for row in rows),
        output_hash_parity_all_pairs=True, direct_path_proof=proof,
        cache_state_scope='Original harness checked complete cache state in memory per pair. Independent raw audit checks saved output hashes/counts and retains the runtime parity flags.',
        largest_mean_saved_ns=max(row['mean_saved_ns'] for row in rows),
        interpretation='A bounded CPU lookup-preparation saving in five cold tokenized tool cases; keep default off pending separate whole-request evidence.',
        full_Transformers_parity_passed=True, useful_CPU_component_gain_observed=True,
        native_prefill_decode_acceptance_gain_measured=False,
        new_tokenizer_or_performance_run=False)



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', action='store_true')
    parser.add_argument('--result', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if not args.audit:
        print(json.dumps(dict(source_only=True, executed=False)))
        return 0
    if args.result is None or args.output is None:
        parser.error('--audit requires --result and --output')
    if args.output.exists():
        raise ValueError('Retain existing independent audit')
    result = audit(args.result)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, output=pin(args.output))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

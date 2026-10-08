"""Publish this completed, rejected native-attention comparison from raw receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ROOT = PREP.parents[3]
sys.path.insert(0, str(ROOT / 'server'))
from controller import atomic, read

def ref(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def metrics(summary):
    rows = summary['rows'][1:]
    assert summary['passed'] and len(rows) == 3
    assert all(r['usage']['prompt_tokens'] == 8192 and r['usage']['completion_tokens'] == 128
        and r['accepted'] == 70 and r['drafted'] == 113 for r in rows)
    return dict(raw_prefill=statistics.fmean(r['timings']['prompt_per_second'] for r in rows),
        raw_decode=statistics.fmean(r['timings']['predicted_per_second'] for r in rows),
        normalized_prefill=statistics.fmean(r['pp_tps'] for r in rows),
        normalized_decode=statistics.fmean(r['decode_tps'] for r in rows),
        wall_mean=statistics.fmean(r['wall_seconds'] for r in rows),
        wall_stdev=statistics.stdev(r['wall_seconds'] for r in rows),
        raw_prefill_stdev=statistics.stdev(r['timings']['prompt_per_second'] for r in rows),
        raw_decode_stdev=statistics.stdev(r['timings']['predicted_per_second'] for r in rows),
        clock_factors=[r['clock_calibration']['monotonic_per_raw'] for r in rows],
        normalized_phase_estimates=any(abs(r['clock_calibration']['monotonic_per_raw']-1)>.0001 for r in rows),
        accepted=sum(r['accepted'] for r in rows), drafted=sum(r['drafted'] for r in rows),
        output_hashes=[r['output_sha256'] for r in rows],
        minimum_memory_bytes={k:min(r['observed_minimum_memory_bytes'][k] for r in rows)
            for k in ('available_bytes','commit_headroom_bytes')})

if __name__ == '__main__':
    summaries = {n:read(WORK/n/'summary.json') for n in ('before','candidate','after')}
    windows = {n:metrics(s) for n,s in summaries.items()}
    assert len({s['request_sha256'] for s in summaries.values()}) == 1
    assert len({h for w in windows.values() for h in w['output_hashes']}) == 1
    manifests = {n:read(WORK/n/'identity.json')['manifest']['environment'] for n in summaries}
    assert manifests['before'] == manifests['after']
    expected = dict(manifests['before'], HALOGEN_ATTN_QS_BT4_OPT='0')
    assert manifests['candidate'] == expected
    ready = read(WORK/'final-ready-open.json')
    assert ready['ready_open'] and ready['candidate_removed']
    assessment = read(WORK/'independent-assessment.json')
    assert assessment['material_mismatches'] == []
    assert len(assessment['retained_inputs']) == 21
    for sealed in assessment['retained_inputs']:
        assert ref(Path(sealed['path'])) == sealed
    fields = ('raw_prefill','raw_decode','wall_mean')
    stock = {k:statistics.fmean(windows[n][k] for n in ('before','after')) for k in fields}
    delta = {k:100*(windows['candidate'][k]/stock[k]-1) for k in fields}
    after_delta = {k:100*(windows['candidate'][k]/windows['after'][k]-1) for k in fields}
    drift = {k:100*(windows['after'][k]/windows['before'][k]-1) for k in fields}
    evidence = dict(utc=datetime.now(timezone.utc).isoformat(),version='0.17.2',
        classification='no-qualified-gain',candidate_adopted=False,repeat_unchanged_candidate=False,
        changed_control={'HALOGEN_ATTN_QS_BT4_OPT':'0'},actual_input_tokens=8192,output_tokens=128,
        input_kind='synthetic finite-vocabulary pseudoprose;116 repeated a-prefix calibration units',
        output_kind='normally generated non-copying story',measured_repetitions_per_window=3,
        excluded_warmups_per_window=1,acceptance_scope='combined API MTP+PLD',
        request_sha256=next(iter(summaries.values()))['request_sha256'],summaries=summaries,
        windows=windows,pooled_stock_raw_means=stock,candidate_vs_pooled_raw_percent=delta,
        candidate_vs_after_raw_percent=after_delta,stock_bookend_raw_drift_percent=drift,
        output_and_accounting_parity_for_this_workload=True,
        exact_internal_attention_numerical_equivalence_proved=False,
        runtime_kernel_dispatch_captured=False,npu_execution=False,startup_floors_changed=False,
        final_ready=ref(WORK/'final-ready-open.json'),preparation=ref(WORK/'preparation.json'),
        source_decision=ref(PREP/'prefill-next-mechanism-20261008/decision.md'),
        source_delivery=ref(PREP/'prefill-next-mechanism-20261008/delivery.json'),
        dispatch_pair=ref(PREP/'prefill-next-mechanism-20261008/bt4x-pair.json'),
        load_receipts=[ref(WORK/(n+'-premeasurement-load.json')) for n in summaries],
        raw_receipts=[ref(WORK/n/file) for n in summaries for file in
            ['identity.json','samples.json','summary.json']+[f'response-{rep}.json' for rep in range(4)]])
    for suffix in ('json','md'):
        path = WORK/('independent-assessment.'+suffix)
        if path.exists():
            evidence['independent_assessment_'+suffix] = ref(path)
    target = ROOT/'docs/benchmarks/halogen0172-native-attn-bt4-opt-20261008'
    atomic(target.with_suffix('.json'),evidence)
    lines = ['# Halogen 0.17.2: native Attention BT4 OPT0 comparison','',
        'The sole native `HALOGEN_ATTN_QS_BT4_OPT=0` candidate establishes no qualified serving gain. It remains disabled; the normal server is ready and open with its visible request-log console.','',
        'Stock → candidate → stock. Each window has one separately excluded warmup and three measurements: 8,192 actual synthetic input tokens, 128 normally generated output tokens, temperature 0, seed 1, Thinking Off and Cache Off. The input is finite-vocabulary pseudoprose with 116 repeated ` a` calibration prefix units. The output is a non-copying story. Capacity 262144, MTP2/PLD3,3 and chunk/arena 8192 remain fixed.','',
        '| Window | Raw API Prefill tok/s | Raw API Decode tok/s | QPC request wall s | Combined acceptance |',
        '| --- | ---: | ---: | ---: | ---: |']
    for n,w in windows.items():
        lines.append(f"| {n} | {w['raw_prefill']:.2f} | {w['raw_decode']:.2f} | {w['wall_mean']:.4f} | {w['accepted']}/{w['drafted']} = {100*w['accepted']/w['drafted']:.2f}% |")
    lines += ['',
        'Independent read-only review rehashed all 21 retained raw input files and reproduced environment, output, accounting and timing calculations with no material mismatch. Its sealed assessment is attached to the JSON.','',
        f"Candidate versus pooled stock, descriptively: raw Prefill {delta['raw_prefill']:+.2f}%, raw Decode {delta['raw_decode']:+.2f}%, independent whole-request QPC wall {delta['wall_mean']:+.2f}%. Against stock-after only, raw Prefill is {after_delta['raw_prefill']:+.2f}% and raw Decode {after_delta['raw_decode']:+.2f}%; QPC wall is {after_delta['wall_mean']:+.2f}%.",'',
        f"These are not established gains. Stock Prefill drifts {drift['raw_prefill']:+.2f}% between bookends; stock-before Prefill standard deviation is {windows['before']['raw_prefill_stdev']:.2f} tok/s. Its first measurement is retained, not discarded. The after-only difference is small relative to observed variation. No additional cohort was run to erase the unstable baseline.",'',
        'Candidate repetition 2 has MONOTONIC/RAW factor 1.00829194765. Applying whole-request calibration gives candidate means 1240.79 Prefill / 43.25 Decode tok/s, assuming uniform phase scaling. These normalized candidate phase rates and related deltas are estimates, not qualified post values. Raw rates, every clock endpoint and independent QPC times remain in the JSON. Both stock windows have factors approximately 1. A timestamp offset is not a restart reason.','',
        'All twelve requests, including warmups, have identical full emitted-text hashes and 70 accepted / 113 drafted tokens per request. Acceptance is combined API MTP+PLD, not isolated native MTP. This proves output/accounting parity for this frozen workload; internal logits, state and general numerical equivalence are unproved.','',
        'Bounded source inspection identifies a complete native attention alternative with 140 versus 168 VGPRs, unchanged 27 SGPRs / 14928-byte LDS / zero spills, identical argument layout, buffers, grid, block and one launch. Lower register pressure was the concrete hypothesis. No new runtime dispatch capture or individual GPU timing was taken. No custom kernel, binary patch, extra preload, weight edit, NPU helper or startup-floor study occurred.','',
        'The unchanged normal lifecycle restored the original profile after measurement. This candidate will not be repeated unchanged. The full acceleration goal remains unachieved.','']
    target.with_suffix('.md').write_text('\n'.join(lines),encoding='utf-8')
    state_path = PREP.parent/'continuation-current.json'
    state = read(state_path)
    entry = state['active0172_native_attn_bt4_opt_comparison']
    entry.update(phase='complete-stock-ready-open',completed=True,candidate_adopted=False,
        serving_gain_qualified=False,repeat_unchanged_candidate=False,
        own_measurement_helpers_closed=True,full_goal_completed=False,windows=windows,
        candidate_vs_pooled_raw_percent=delta,candidate_vs_after_raw_percent=after_delta,
        stock_bookend_raw_drift_percent=drift,report=ref(target.with_suffix('.md')),
        evidence=ref(target.with_suffix('.json')))
    state['latest0172_stock_reference'] = dict(window='native-attn-bt4-opt-comparison/after',
        version='0.17.2',actual_input_tokens=8192,output_tokens=128,
        input_kind=evidence['input_kind'],prefill_tps=windows['after']['raw_prefill'],
        decode_tps=windows['after']['raw_decode'],accepted=210,drafted=339,
        acceptance_percent=100*210/339,acceptance_scope=evidence['acceptance_scope'],
        thinking=False,cache=False,excluded_warmups=1,measured_repetitions=3,
        evidence=ref(target.with_suffix('.json')),normalized_candidate_rates_not_promoted=True)
    state['active_goal']='Active, unachieved: Halogen0.17.2 native attention OPT0 comparison completed; no qualified gain; stock ready/open. Distinct CPU external-corpus third-draft screen in progress. No startup-floor study.'
    atomic(state_path,state)
    print(json.dumps(dict(report=str(target.with_suffix('.md')),classification='no-qualified-gain',
        candidate_vs_pooled_raw_percent=delta,candidate_vs_after_raw_percent=after_delta,
        stock_bookend_raw_drift_percent=drift,ready_open=True)))

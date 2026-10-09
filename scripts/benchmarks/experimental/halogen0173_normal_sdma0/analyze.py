"""Separate collection completion from native-clock speed qualification."""
import hashlib
import json
from pathlib import Path
import statistics

WORK=Path(__file__).resolve().parent
FIELDS=('output_sha256','accepted','drafted','finish_reason')

def clock_gate(values):
    measured=[row for value in values for row in value['rows'][1:]]
    ratios=[row['clock_calibration']['monotonic_per_raw'] for row in measured]
    rawqpc=[row['clock_calibration']['raw_per_qpc'] for row in measured]
    spread=max(ratios)/min(ratios)-1
    return dict(measured_rows=len(measured),monotonic_per_raw_min=min(ratios),
                monotonic_per_raw_max=max(ratios),relative_spread=spread,
                raw_per_qpc_min=min(rawqpc),raw_per_qpc_max=max(rawqpc),
                raw_qpc_within_0_1_percent=all(abs(v-1)<=.001 for v in rawqpc),
                comparable=spread<=.001 and all(abs(v-1)<=.001 for v in rawqpc),
                limit=.001,native_rates_normalized=False)

def main():
    arms={name:json.loads((WORK/name/'summary.json').read_bytes()) for name in ('before','candidate','after')}
    refs=[]
    baseline=arms['before']
    for name,value in arms.items():
        assert value['passed'] and len(value['rows'])==4
        for key in ('version','profile_sha256','prompt_sha256','request_sha256','client_sha256','equality_baseline'):
            assert value[key]==baseline[key],key
        assert all({k:row[k] for k in FIELDS}==baseline['equality_baseline'] for row in value['rows'])
        path=WORK/name/'summary.json'
        refs.append(dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    pooled=clock_gate(list(arms.values()))
    pairs={name:clock_gate([arms['candidate'],arms[name]]) for name in ('before','after')}
    compact={}
    for name,value in arms.items():
        measured=value['rows'][1:]
        compact[name]=dict(prefill_mean=value['prefill_mean'],prefill_stdev=value['prefill_stdev'],
            decode_mean=value['decode_mean'],decode_stdev=value['decode_stdev'],
            acceptance=value['acceptance'],accepted=sum(row['accepted'] for row in measured),
            drafted=sum(row['drafted'] for row in measured),
            wall_seconds_mean=statistics.fmean(row['wall_seconds'] for row in measured),
            clocks=clock_gate([value]),min_physical_gib=min(row['observed_minimum_memory_bytes']['available_bytes'] for row in value['rows'])/2**30,
            min_commit_gib=min(row['observed_minimum_memory_bytes']['commit_headroom_bytes'] for row in value['rows'])/2**30)
    deltas={name:dict(prefill_percent=(arms['candidate']['prefill_mean']/arms[name]['prefill_mean']-1)*100,
                     decode_percent=(arms['candidate']['decode_mean']/arms[name]['decode_mean']-1)*100,
                     native_clock_comparison_qualified=pairs[name]['comparable']) for name in ('before','after')}
    gain=pooled['comparable'] and all(d['prefill_percent']>0 and d['decode_percent']>0 for d in deltas.values())
    result=dict(version='0.17.3',experiment='normal SDMA1/0/1',actual_input_tokens=8192,output_tokens=128,
        input_scope='synthetic pseudoprose with116repeated input calibration units',
        excluded_warmups_per_arm=1,measured_repetitions_per_arm=3,acceptance_scope='combined API MTP/PLD draft-token counters',
        NPU_executed=False,all_output_and_counter_parity=True,raw_native_arms=compact,
        clocks_three_arms=pooled,clocks_pairs=pairs,raw_deltas=deltas,
        positive_mean_prefill_and_decode_screen=gain,summary_refs=refs,
        serving_gain_adopted=False,small_cohort_not_a_statistical_gain_proof=True,
        full_goal_completed=False,default_candidate_remains_off=True,
        decision='retain standard; candidate needs separate adoption decision' if gain else 'retain standard; no qualified net Prefill/Decode gain')
    (WORK/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__': main()

"""Account only complete matched direct-registration cohorts; retain raw evidence."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics

WORK=Path(__file__).resolve().parent

def read(path): return json.loads(path.read_bytes())
def ref(path):
    return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())

if __name__=='__main__':
    arms={key:read(WORK/key/'summary.json') for key in ('before','candidate','after')}
    reference=read(WORK/'before/response-0.json')
    all_raw=[]
    for name,arm in arms.items():
        assert arm['passed'] and arm['excluded_warmups']==1 and arm['measured_repetitions']==3
        assert len(arm['rows'])==4 and arm['rows'][0]['phase']=='warmup'
        assert arm['actual_input_tokens']==8192 and arm['output_tokens']==128
        assert arm['request_sha256']==arms['before']['request_sha256']
        assert arm['final_health']['completed']-arm['first_health']['completed']==4
        assert arm['final_health']['cancelled']==arm['first_health']['cancelled']
        for row in arm['rows']:
            path=WORK/name/('response-'+str(row['rep'])+'.json')
            response=read(path)
            assert response['choices']==reference['choices']
            assert response['model']==reference['model'] and response['usage']==reference['usage']
            assert row['accepted']==70 and row['drafted']==113
            assert min(row['observed_minimum_memory_bytes'].values())>=18*2**30
            all_raw.append(ref(path))
    clocks=[row['clock_calibration'] for arm in arms.values() for row in arm['rows'][1:]]
    clock_ratios=[row['monotonic_per_raw'] for row in clocks]
    assert all(abs(row['raw_per_qpc']-1)<0.001 for row in clocks)
    comparable_clocks=max(clock_ratios)/min(clock_ratios)-1<0.001
    pair_clocks={}
    for stock_name in ('before','after'):
        ratios=[row['clock_calibration']['monotonic_per_raw']
                for name in ('candidate',stock_name) for row in arms[name]['rows'][1:]]
        pair_clocks[stock_name]=max(ratios)/min(ratios)-1<0.001
    candidate=arms['candidate'];stock=[row for name in ('before','after') for row in arms[name]['rows'][1:]]
    stock_pp=statistics.fmean(row['pp_tps'] for row in stock)
    stock_tg=statistics.fmean(row['decode_tps'] for row in stock)
    result=dict(schema='halogen0172.hc6-direct-registration.cohort.v1',utc=datetime.now(timezone.utc).isoformat(),
                version='0.17.2',workload=dict(actual_input_tokens=8192,context_capacity=262144,
                  output_tokens=128,type='synthetic pseudoprose',repeated_calibration_units=116,
                  non_repetitive_natural=False,prompt_sha256='0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1',
                  temperature=0,seed=1,thinking=False,cache=False,MTP_depth=2,PLD='3,3',
                  warmups_per_arm=1,measured_runs_per_arm=3),arms=arms,raw_responses=all_raw,
                acceptance_scope='combined native API MTP+PLD, not isolated MTP',
                rate_basis='native API response.timings rates, no clock normalization',
                clock_scaling=dict(monotonic_per_raw_min=min(clock_ratios),monotonic_per_raw_max=max(clock_ratios),
                                   raw_per_qpc_within_0_1_percent=True,comparable_within_0_1_percent=comparable_clocks,
                                   per_arm={name:[row['clock_calibration']['monotonic_per_raw'] for row in arm['rows'][1:]] for name,arm in arms.items()}),
                three_arm_raw_rate_comparison_qualified=comparable_clocks,
                candidate_stock_pair_clock_comparable=pair_clocks,
                serving_gain_qualified=False,candidate_kept_off=True,repeat_unchanged=False,
                disposition='No serving gain qualified: three-arm clocks differ; candidate/after rates overlap',
                acceptance_per_measured_arm=dict(accepted=210,drafted=339,ratio=210/339),
                all_12_exact_choices_model_usage=True,
                stock_combined_mean=dict(prefill=stock_pp,decode=stock_tg),
                candidate_delta_percent=dict(prefill=100*(candidate['prefill_mean']/stock_pp-1),
                                             decode=100*(candidate['decode_mean']/stock_tg-1)),
                candidate_delta_scope='Descriptive raw arithmetic only; combined stock clocks are not comparable',
                candidate_vs_each_stock_delta_percent={name:dict(
                    prefill=100*(candidate['prefill_mean']/arms[name]['prefill_mean']-1),
                    decode=100*(candidate['decode_mean']/arms[name]['decode_mean']-1))
                    for name in ('before','after')},
                observed_stock_range=dict(prefill=[min(r['pp_tps'] for r in stock),max(r['pp_tps'] for r in stock)],
                                          decode=[min(r['decode_tps'] for r in stock),max(r['decode_tps'] for r in stock)]),
                exact_registration=read(WORK/'candidate-registration-before.json'),
                exact_registration_after=read(WORK/'candidate-registration-after.json'),
                CPU_build=ref(WORK/'build.json'),
                final_ready_open_receipt=ref(WORK/'final-ready-open.json'),
                own_candidate_source=[ref(WORK/x) for x in ('registration.c','test_registration.c','launch.py','register-launch.sh')],
                full_goal_completed=False,NPU_executed=False)
    path=WORK/'cohort-analysis.json'
    assert not path.exists()
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(arms={key:{field:value[field] for field in ('prefill_mean','decode_mean','acceptance')} for key,value in arms.items()},
                         three_arm_clock_comparable=comparable_clocks,pair_clock_comparable=pair_clocks,
                         candidate_vs_stock_raw_deltas=result['candidate_vs_each_stock_delta_percent'],
                         serving_gain_qualified=False,stock_range=result['observed_stock_range'],parity=True)))

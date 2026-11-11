"""Offline exact reference/scenario comparison; no runtime or model access."""
import argparse
import array
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=ROOT/'scripts/benchmarks/halogen_flm_growing_replay/replay_tools.py'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!='0e2bd704e9a2b6d6cc496b02dc94a8bf41ab84108b771f9cb89b0fb1a5f63b8b':
    raise ValueError('Original exact row comparator changed')
spec=importlib.util.spec_from_file_location('stateful_original_row_criterion',BASE)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
compare_words=base.compare_words


def need(ok,message):
    if not ok:raise ValueError(message)


def span(value):
    need(type(value)is dict and all(type(value.get(k))is int for k in('started_ticks','finished_ticks'))
         and 0<=value['started_ticks']<=value['finished_ticks'],'Invalid QPC endpoints')


def validate_report(report,mode):
    need(mode in('reference','scenario')and report.get('schema')=='halogen0201.flm1012-state-parity.v1'
         and report.get('mode')==mode and report.get('complete')is True,'Complete matching native mode required')
    need(type(report.get('QPC_frequency'))is int and report['QPC_frequency']>0,'Actual QPC frequency required')
    need(report.get('runtime_requested')=='1.0.12'
         and type(report.get('state_api_version'))is int and report['state_api_version']==1
         and type(report.get('state_api_struct_size'))is int and report['state_api_struct_size']>=72,
         'Matching 1.0.12 runtime and AMD64 v1 state table required')
    packet=base.validate_input(report.get('input',{}))
    c=report['case'];seed=c['seed_tail_ids'];teachers=c['teacher_ids']
    need(len(packet['cases'])==1 and packet['cases'][0]==c,'Report case differs from frozen input authority')
    need(c.get('name')=='natural8192'and c.get('actual_input_tokens')==8192,'One frozen 8K family required')
    need(type(seed)is list and len(seed)==512 and type(teachers)is list and len(teachers)==128
         and all(type(i)is int and 0<=i<248070 for i in seed+teachers),'Bounded shared authority required')
    for key in('native_acceptance','target_readiness','prefill_tok_s','decode_tok_s'):
        need(key in report and report[key]is None,'Unmeasured engine metric must remain null')
    need(report.get('full_retain_optimization_qualified')is False,'Always-restore scope required')
    need(report.get('forced_branches_are_prediction_quality')is False,'Forced branches are not prediction quality')
    states=report.get('states',[]);cycles=report.get('cycles',[])
    need(len(states)==129 and len(cycles)==(128 if mode=='scenario'else 0),'Complete129-state trajectory required')
    span(report.get('startup_timing'))
    previous=report['startup_timing']['finished_ticks']
    for i,s in enumerate(states):
        need(s.get('state_index')==i and s.get('local_count')==512+i and s.get('row_count')==248070
             and s.get('row_file')=='state-'+str(i)+'.bf16','Exact full-row endpoint required')
        need(type(s.get('greedy_id'))is int and 0<=s['greedy_id']<248070,'Shared greedy ID required')
        span(s.get('timing'));span(s.get('row_write_timing'))
        need(previous<=s['timing']['started_ticks']<=s['timing']['finished_ticks']
             <=s['row_write_timing']['started_ticks'],'Startup/state/row-write QPC order differs')
        previous=s['row_write_timing']['finished_ticks']
    matches=sum(s['greedy_id']==teacher for s,teacher in zip(states,teachers))
    need(type(report.get('natural_committed_predictions'))is int and report['natural_committed_predictions']==128
         and type(report.get('natural_committed_next_ID_matches'))is int
         and report['natural_committed_next_ID_matches']==matches,
         'Natural committed next-ID accounting differs from owned states')
    for i,v in enumerate(cycles):
        L=512+i;n=min(3,128-i);proposal=v.get('proposals')
        need(v.get('step')==i and v.get('committed_length')==L and v.get('proposal_count')==n
             and v.get('consumed_inputs')==n-1,'Bounded speculative context differs')
        need(type(proposal)is list and len(proposal)==n
             and all(type(x)is int and 0<=x<248070 for x in proposal),'Invalid speculative IDs')
        label={0:'forced_zero',15:'forced_partial',16:'forced_full'}.get(i,'natural')
        need(v.get('label')==label and v.get('forced')is(label!='natural'),'Forced schedule label or boolean differs')
        if label!='natural':
            expected=teachers[i:i+n].copy()
            if label=='forced_zero':expected[0]=(expected[0]+1)%248070
            elif label=='forced_partial':expected[1]=(expected[1]+1)%248070
            need(proposal==expected,'Exact forced zero/partial/full fixture differs')
        else:
            need(proposal[0]==states[i]['greedy_id'],'Natural proposal must begin with owned committed greedy ID')
        equal=0
        while equal<n and proposal[equal]==teachers[i+equal]:equal+=1
        need(v.get('proposal_prefix_matches')==equal,'Prefix-match accounting differs')
        need(all(v.get(k)==L for k in('state_read_length','saved_length','state_write_length','restored_length'))
             and v.get('saved_kv_from')==0,'Restore must recover exact committed context')
        need(v.get('committed_authority')==teachers[i],'Only true next teacher may be committed')
        need(type(v.get('estimated_state_bytes'))is int and v['estimated_state_bytes']>=0,'State estimate required')
        span(v.get('read_timing'));span(v.get('write_timing'))
        need(states[i]['row_write_timing']['finished_ticks']<=v['read_timing']['started_ticks']
             <=v['read_timing']['finished_ticks']<=v['write_timing']['started_ticks']
             <=v['write_timing']['finished_ticks']<=states[i+1]['timing']['started_ticks'],
             'State read/write/append QPC order differs')
        forwards=v.get('speculative_forward_timings')
        need(type(forwards)is list and len(forwards)==n-1,'Exact speculative-forward span count required')
        previous=v['read_timing']['finished_ticks']
        for timing in forwards:
            span(timing)
            need(previous<=timing['started_ticks']<=timing['finished_ticks']<=v['write_timing']['started_ticks'],
                 'Speculative forward must follow read and precede restore in order')
            previous=timing['finished_ticks']


def row_greedy(raw):
    """Lowest-index finite BF16 argmax, including the equality of -0 and +0."""
    need(len(raw)==248070*2,'Complete shared BF16 row required for greedy reconstruction')
    words=array.array('H');words.frombytes(raw)
    if sys.byteorder!='little':words.byteswap()
    best=None;greedy=-1
    for index,word in enumerate(words):
        magnitude=word&0x7fff
        need(magnitude<0x7f80,'Nonfinite BF16 greedy row')
        # Finite BF16 magnitude encodings increase monotonically with value.
        value=-magnitude if word&0x8000 else magnitude
        if best is None or value>best:best=value;greedy=index
    return greedy


def row_file(report_path,report,state):
    directory=Path(str(Path(report_path))+'.rows').resolve()
    need(Path(report['bf16_rows_directory']).resolve()==directory,'Owned row directory differs')
    path=directory/state['row_file']
    need(path.resolve().parent==directory and not any(p.is_symlink()or p.is_junction()for p in(path,*path.parents)),
         'Linked or foreign row snapshot')
    return path


def compare(reference_path,scenario_path):
    ref=json.loads(Path(reference_path).read_bytes());scn=json.loads(Path(scenario_path).read_bytes())
    validate_report(ref,'reference');validate_report(scn,'scenario')
    need(ref['case']==scn['case']and ref['input']==scn['input'],'Reference/scenario authority differs')
    comparisons=[]
    for a,b in zip(ref['states'],scn['states']):
        paths=[row_file(reference_path,ref,a),row_file(scenario_path,scn,b)]
        raws=[p.read_bytes()for p in paths]
        for state,raw in zip((a,b),raws):
            need(state['greedy_id']==row_greedy(raw),'Reported greedy ID differs from actual full BF16 row')
        result=compare_words(*raws)
        need(not result['passed']or a['greedy_id']==b['greedy_id'],'Equal rows have different greedy IDs')
        result.update(state_index=a['state_index'],local_count=a['local_count'],files=[base.pin(p)for p in paths])
        comparisons.append(result)
    return dict(schema='halogen0201.flm1012-state-parity-comparison.v1',
        exact_sequential_row_parity=all(c['passed']for c in comparisons),compared_states=129,
        compared_BF16_values=129*248070,comparisons=comparisons,tolerance_relaxed=False,
        criterion='original exact BF16 word equality',native_acceptance=None,prefill_tok_s=None,
        decode_tok_s=None,target_readiness=None,full_retain_optimization_qualified=False,
        reports=[base.pin(Path(reference_path)),base.pin(Path(scenario_path))])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare',nargs=2,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=compare(*args.compare)
    with args.output.open('x',encoding='utf-8')as stream:json.dump(result,stream,indent=2);stream.write('\n')
    raise SystemExit(0 if result['exact_sequential_row_parity']else 1)

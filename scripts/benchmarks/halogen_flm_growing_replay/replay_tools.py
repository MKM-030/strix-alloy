"""CPU-only bounded replay inputs, exact BF16 comparison and build recipe.

This module has no compiler, DLL, process, device, network or lifecycle entry
point. Root separately owns compilation and native execution.
"""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import re
import struct

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PRIVATE_OUTPUT=ROOT / 'server/.local/halogen-flm-growing-replay'
INPUT_SCHEMA='halogen0201.growing-native-replay-input.v1'
ROWS=248070
TARGET_ENGINE='7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577'
TARGET_TOKENIZER='0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'
FLM=Path('C:/AI/src/FastFlowLM-zip/FastFlowLM-1.0.7/src')
SDK=Path('C:/AI/dev/halogen-pld-xrt-2.21.75/sdk/xrt_sdk/xrt')
VC=Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat')


def require(ok,why):
    if not ok:raise ValueError(why)


def pin(path):
    path=Path(path);raw=path.read_bytes()
    return dict(path=str(path.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def validate_input(packet):
    require(packet.get('schema')==INPUT_SCHEMA and packet.get('authority')=='recorded_native_T','Native T input required')
    require(packet.get('target_engine_sha256')==TARGET_ENGINE and packet.get('target_tokenizer_sha256')==TARGET_TOKENIZER,'Target identity differs')
    cases=packet.get('cases');require(type(cases)is list and 1<=len(cases)<=2,'One or two cases required')
    epochs=set()
    for c in cases:
        require(type(c.get('request_id'))is int and 0<=c['request_id']<1<<63,'Native request ID required')
        epoch=c.get('request_epoch');require(type(epoch)is str and re.fullmatch('[0-9a-f]{32}',epoch)and epoch not in epochs,'Fresh epoch required');epochs.add(epoch)
        require(c.get('name')in('natural8192','natural16384')and c.get('actual_input_tokens')in(8192,16384),'Frozen natural family required')
        require(c['actual_input_tokens']==(8192 if c['name']=='natural8192' else 16384),'Input family/count mismatch')
        require(type(c.get('request_sha256'))is str and re.fullmatch('[0-9a-f]{64}',c['request_sha256']),'Request SHA required')
        for key,count in [('seed_tail_ids',512),('teacher_ids',128)]:
            ids=c.get(key);require(type(ids)is list and len(ids)==count and all(type(t)is int and 0<=t<ROWS for t in ids),'Bounded shared IDs required: '+key)
    return packet


def cpu_schedule(case,reference=False):
    trace=[('seed',512)]
    for i,token in enumerate(case['teacher_ids']):
        if not reference:trace.append(('predict',512+i))
        trace.append(('append',token))
    return trace


def bf16_float(word):
    return struct.unpack('<f',struct.pack('<I',word<<16))[0]


def compare_words(candidate,reference):
    require(len(candidate)==len(reference)==ROWS*2,'Exact complete shared-row bytes required')
    a=array.array('H');a.frombytes(candidate);b=array.array('H');b.frombytes(reference)
    import sys
    if sys.byteorder!='little':a.byteswap();b.byteswap()
    differences=0;first=[];maximum=0.0
    for i,(left,right)in enumerate(zip(a,b)):
        x,y=bf16_float(left),bf16_float(right)
        require(math.isfinite(x)and math.isfinite(y),'nonfinite supported BF16 row')
        if left!=right:
            differences+=1
            if len(first)<16:first.append(i)
            maximum=max(maximum,abs(x-y))
    return dict(compared_rows=ROWS,exact_word_differences=differences,
        first_mismatch_rows=first,max_absolute_difference=maximum,
        passed=differences==0,tolerance_relaxed=False,criterion='original exact BF16 word equality')


def validate_timing(value):
    keys=('host_call_started_ticks','operation_started_ticks','logits_owned_ticks','host_call_returned_ticks')
    require(type(value.get('frequency'))is int and value['frequency']>0
        and all(type(value.get(k))is int and value[k]>=0 for k in keys)
        and list(value[k]for k in keys)==sorted(value[k]for k in keys),'Invalid actual native/host QPC timing')


def validate_case_report(report,case,mode='candidate',frequency=None):
    states=report.get('states',[]);require(len(states)==129,'Complete129 native states required')
    require(report.get('speculative_inputs')==0,'Zero speculative inputs required')
    for k in('name','request_id','request_epoch','actual_input_tokens','seed_tail_ids','teacher_ids'):
        require(report.get(k)==case[k],'Replay authoritative identity differs: '+k)
    for k in('consumer_arrival_timestamp','target_need_timestamp','consumer_arrived_before_target_need'):
        require(k in report and report[k]is None,'Unmeasured target readiness must remain null')
    frequency=states[0].get('timing',{}).get('frequency') if frequency is None else frequency
    require(type(frequency)is int and frequency>0,'Positive single QPC frequency required')
    previous_end=0
    for i,s in enumerate(states):
        require(s.get('state_index')==i and s.get('local_count')==512+i and s.get('row_count')==ROWS,'Native state index/length/rows differ')
        require(type(s.get('greedy_id'))is int and 0<=s['greedy_id']<ROWS,'Shared greedy ID required')
        validate_timing(s.get('timing',{}))
        t=s['timing']
        require(t.get('clock')=='Windows QPC' and t['frequency']==frequency,'Native QPC clock/frequency differs')
        begin,end=s.get('rows_write_started_ticks'),s.get('rows_write_finished_ticks')
        require(type(begin)is int and type(end)is int
            and previous_end<=t['host_call_started_ticks']<=t['host_call_returned_ticks']<=begin<=end,
            'Cross-state or row-write QPC order differs')
        previous_end=end
    predictions=report.get('predictions')
    require(type(predictions)is list and len(predictions)==(128 if mode=='candidate' else 0),'Complete count-one predictions required')
    for i,r in enumerate(predictions):
        require(r.get('ordinal')==i and r.get('local_count')==512+i
            and r.get('predicted_id')==states[i]['greedy_id']
            and r.get('authoritative_id_after_prediction')==case['teacher_ids'][i]
            and r.get('owned_words_unchanged')is True and r.get('context_unchanged')is True
            and r.get('speculative_inputs')==0,'Prediction must precede authoritative append without mutation')
        begin,end=r.get('ready_started_ticks'),r.get('ready_finished_ticks')
        require(type(begin)is int and type(end)is int and states[i]['rows_write_finished_ticks']<=begin<=end
            <=states[i+1]['timing']['host_call_started_ticks'],'Prediction QPC order differs')
        for k in('consumer_arrival_timestamp','target_need_timestamp','consumer_arrived_before_target_need'):
            require(k in r and r[k]is None,'Unmeasured prediction readiness must remain null')


def compare_reports(candidate_path,reference_path):
    reports=[json.loads(Path(p).read_bytes())for p in(candidate_path,reference_path)]
    candidate,reference=reports
    require(candidate.get('mode')=='candidate'and reference.get('mode')=='reference','Separate candidate/reference reports required')
    require(candidate.get('input')==reference.get('input'),'Input pack differs across native passes')
    packet=validate_input(candidate['input'])
    for report in reports:
        require(report.get('schema')=='halogen0201.growing-native-replay.v1'and report.get('complete')is True
            and report.get('shared_rows')==ROWS and report.get('engine_capacity_requested')==4096
            and report.get('native_acceptance')is None and report.get('readiness_to_target')is None,'Incomplete or unqualified native report')
        require(len(report.get('cases',[]))==len(packet['cases']),'Missing native replay family')
        require(report.get('clock')=='Windows QPC' and type(report.get('QPC_frequency'))is int
            and report['QPC_frequency']>0,'Actual report QPC clock/frequency required')
    results=[]
    for index,case in enumerate(packet['cases']):
        a,b=candidate['cases'][index],reference['cases'][index]
        validate_case_report(a,case,'candidate',candidate['QPC_frequency'])
        validate_case_report(b,case,'reference',reference['QPC_frequency'])
        states=[]
        for i,(left,right)in enumerate(zip(a['states'],b['states'])):
            files=[]
            for output,report,s in zip((candidate_path,reference_path),reports,(left,right)):
                directory=Path(str(Path(output))+'.rows').resolve()
                require(Path(report['bf16_rows_directory']).resolve()==directory,'Native row directory differs')
                f=directory/s['row_file'];require(f.resolve().parent==directory and not f.is_symlink(),'Nonfinite native row path')
                files.append(f)
            comparison=compare_words(files[0].read_bytes(),files[1].read_bytes())
            require(left['greedy_id']==right['greedy_id']or not comparison['passed'],'Equal rows with different greedy ID')
            comparison.update(state_index=i,local_count=512+i,greedy_ids=[left['greedy_id'],right['greedy_id']],files=[pin(f)for f in files])
            states.append(comparison)
        exact_ids=sum(r['predicted_id']==r['authoritative_id_after_prediction']for r in a['predictions'])
        results.append(dict(name=case['name'],states=states,all_owned_rows_equal=all(s['passed']for s in states),
            compared_states=129,compared_values=129*ROWS,offline_exact_next_IDs=exact_ids,offline_proposed_IDs=128,
            native_acceptance=None,target_readiness=None))
    return dict(schema='halogen0201.growing-native-replay-comparison.v1',cases=results,
        exact_sequential_row_parity=all(r['all_owned_rows_equal']for r in results),
        tolerance_relaxed=False,criterion='original exact BF16 word equality',
        native_acceptance=None,prefill_tok_s=None,decode_tok_s=None,engine_benefit=None,
        reports=[pin(Path(p))for p in(candidate_path,reference_path)])


def build_recipe(output):
    output=Path(output).resolve()
    require(output.is_absolute()and output.is_relative_to((ROOT/'server/.local').resolve())and output!=HERE,'Finite private build directory required')
    source=HERE/'replay_host.cpp';exe=output/'growing-replay.exe'
    args=['cl','/nologo','/std:c++20','/Zc:__cplusplus','/EHsc','/MD','/O2','/fp:precise',
        '/D__WINDOWS__','/DDISABLE_ABI_CHECK=1','/DWIN32_LEAN_AND_MEAN','/DNOMINMAX',
        '/D_CRT_SECURE_NO_WARNINGS','/D_CRT_NONSTDC_NO_DEPRECATE',
        '/I'+str(FLM/'include'),'/I'+str(SDK/'include'),str(source),
        '/Fe:'+str(exe),'/Fo:'+str(output/'replay_host.obj'),'/link','/MACHINE:X64',
        '/LIBPATH:'+str(FLM/'lib/xrt'),'/LIBPATH:'+str(SDK/'lib'),
        'qwen3_5vl_npu.lib','q4_npu_eXpress.lib','xrt_coreutil.lib','aiebu_static.lib']
    # A recipe only: this module never starts cmd, cl or the linked executable.
    import subprocess
    text='@echo off\ncall "'+str(VC)+'" >nul\nif errorlevel 1 exit /b %errorlevel%\n'+subprocess.list2cmdline(args)+'\nexit /b %errorlevel%\n'
    return dict(compiler_arguments=args,vcvars=str(VC),build_cmd=text,executable=str(exe),
        compiled=False,DLL_loaded=False,device_created=False,
        definitions_exclude_FLM_USE_HRX=True,precise_FP=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare',nargs=2,type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--build-recipe',type=Path)
    args=parser.parse_args()
    require(not(args.compare and args.build_recipe),'Choose offline comparison or build recipe')
    result=compare_reports(*args.compare)if args.compare else build_recipe(args.build_recipe or PRIVATE_OUTPUT/'build-v1')
    if args.output:
        with args.output.open('x',encoding='utf-8')as f:json.dump(result,f,indent=2);f.write('\n')
    else:print(json.dumps(result,indent=2))


if __name__=='__main__':main()

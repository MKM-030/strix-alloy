"""Passive synthetic journal and environment checks; never launches an ELF."""
from pathlib import Path, PurePosixPath
from unittest.mock import patch
import copy, json, struct, tempfile
import launch_phase_clock as launch
import verify_phase_journal as verify
OUT=Path(__file__).resolve().parent
def bits(v):return struct.unpack('<Q',struct.pack('<d',v))[0]
def fixture():
    header=dict(kind='activation',engine_sha256=launch.ENGINE_SHA,provider_sha256=verify.PROVIDER_SHA,
        raw_clock_id=4,real_clock_address=0x8000+0xd5490,provider_base=0x8000,engine_base=0x7000,default_off=1,
        deferred_arm=1,arm_file_device=77,arm_file_inode=173,decode_pairing_version=2)
    rows=[header]
    def pair(phase,obj,stack,tid,native,raw,delta,stored=0.0):
        seq=len(rows);base=dict(kind='phase',sequence=seq,begin=1,pair_id=seq,caller_stack=stack,
            phase=phase,status=0,request_id=-17,object=obj,begin_object=obj,tid=tid,
            caller_rva=0x1746b3f if phase==1 else 0x17490bb,
            native_start_ns=native,raw_start_ns=raw,raw_end_ns=raw,returned_end_ns=native,raw_delta_ns=0,
            observed_native_start_ns=native,object_native_start_ns=0)
        if phase==2:base.update(native_prefill_ms_bits=0,prompt_count=0,predicted_count=0)
        rows.append(base)
        end=dict(base,sequence=seq+1,begin=0,caller_rva=0x1746f16 if phase==1 else 0x174ca12,
            raw_end_ns=raw+delta,returned_end_ns=native+delta,raw_delta_ns=delta)
        if phase==2:end.update(native_prefill_ms_bits=bits(stored),prompt_count=37,predicted_count=9,
            caller_stack=stack+0x1000,tid=tid+1,object=obj+0x2000,object_native_start_ns=native)
        rows.append(end)
    pair(1,0x1000,0x2000,17,8_000_000_000_000_000_000,1_000_000,123456)
    pair(1,0x1000,0x2000,17,8_000_000_000_000_000_000,2_000_000,876544)
    pair(2,0x3000,0x4000,17,8_000_000_000_000_000_000,3_000_000,2345000,1.0)
    d=[dict(request_id=-17,prefill_ms=1.0,decode_ms=2.3,prompt_count=37,predicted_count=9)]
    return rows,d
def main():
    checks=[]
    with tempfile.TemporaryDirectory(prefix='phase-clock-passive-') as td:
        target=Path(td);journal=target/'journal.jsonl';dfile=target/'d.json'
        def evaluate(rows,records):
            journal.write_text(''.join(json.dumps(x)+'\n' for x in rows))
            if records is not None:dfile.write_text(json.dumps({'records':records}))
            return verify.validate(journal,dfile if records is not None else None)
        rows,d=fixture();result=evaluate(rows,d)
        assert result['paired_raw_phase_verified'] and result['consumed_pairs']==3
        assert result['requests'][0]['prefill_chunks']==2 and result['requests'][0]['prefill_ms']==1.0
        checks.append('valid_chunk_sum_signed_id_decode_cross_thread_and_D_rounding')
        assert not evaluate(rows,None)['paired_raw_phase_verified'];checks.append('no_D_is_instrumentation_only')
        assert verify.validate(journal,None,True)['arm_file_inode']==173;checks.append('deferred_arm_identity_bound')
        immediate=copy.deepcopy(rows);immediate[0].update(deferred_arm=0,arm_file_inode=0)
        evaluate(immediate,None)
        try:verify.validate(journal,None,True)
        except ValueError:checks.append('immediate_activation_rejected_when_deferred_required')
        else:raise AssertionError('Accepted immediate activation for deferred cohort')
        def reject(name,mutate):
            altered,records=copy.deepcopy(rows),copy.deepcopy(d);mutate(altered,records)
            try:evaluate(altered,records)
            except ValueError:checks.append(name)
            else:raise AssertionError('Accepted invalid fixture: '+name)
        reject('pending_begin',lambda r,d:r.pop())
        def duplicate_begin(r,d):
            begin=dict(r[1],sequence=2,pair_id=2);r.insert(2,begin)
            for i in range(3,len(r)):r[i]['sequence']=i
        reject('duplicate_begin',duplicate_begin)
        reject('duplicate_end',lambda r,d:r.append(dict(r[-1],sequence=len(r))))
        reject('mismatched_native_start',lambda r,d:r[2].update(native_start_ns=1))
        reject('fallback',lambda r,d:r[2].update(status=3))
        reject('RAW_reversal',lambda r,d:r[2].update(raw_end_ns=0))
        reject('incorrect_returned_delta',lambda r,d:r[2].update(returned_end_ns=1))
        reject('incorrect_D_duration',lambda r,d:d[0].update(decode_ms=2.4))
        reject('incorrect_D_count',lambda r,d:d[0].update(prompt_count=38))
        reject('noninteger_D_count',lambda r,d:d[0].update(prompt_count=37.0))
        reject('prefill_end_thread_mismatch',lambda r,d:r[2].update(tid=18))
        reject('prefill_end_stack_mismatch',lambda r,d:r[2].update(caller_stack=1))
        reject('end_request_id_mismatch',lambda r,d:r[2].update(request_id=-18))
        assert result['moved_decode_pairs']==1;checks.append('moved_decode_endpoint_preserves_begin_object')
        reject('decode_begin_object_mismatch',lambda r,d:r[-1].update(begin_object=1))
        reject('prefill_end_object_mismatch',lambda r,d:r[2].update(object=1))
        reject('decode_observed_native_start_mismatch',lambda r,d:r[-1].update(observed_native_start_ns=1))
        reject('decode_object_native_start_mismatch',lambda r,d:r[-1].update(object_native_start_ns=1))
        reject('missing_pairing_version',lambda r,d:r[0].pop('decode_pairing_version'))
        def duplicate_decode_id(r,d):
            begin=dict(r[5],sequence=6,pair_id=6,object=0x9999,begin_object=0x9999,tid=99,caller_stack=0x9990)
            r.insert(6,begin);r[7]['sequence']=7
        reject('duplicate_active_signed_decode_ID_after_move',duplicate_decode_id)
        concurrent=copy.deepcopy(rows)
        next_begin=dict(concurrent[5],sequence=6,pair_id=6,request_id=-18)
        next_end=dict(concurrent[6],sequence=8,pair_id=6,request_id=-18,native_prefill_ms_bits=bits(0.0))
        concurrent.insert(6,next_begin);concurrent[7]['sequence']=7;concurrent.append(next_end)
        concurrent_d=copy.deepcopy(d)+[dict(d[0],request_id=-18,prefill_ms=0.0)]
        assert evaluate(concurrent,concurrent_d)['consumed_pairs']==4
        checks.append('reused_stack_object_with_distinct_active_decode_IDs')
        reject('changed_native_start_return',lambda r,d:r[1].update(returned_end_ns=1))
        reject('sequence_gap',lambda r,d:r[2].update(sequence=9))
        reject('provider_binding_mismatch',lambda r,d:r[0].update(real_clock_address=1))
        reject('orphan_prefill_chunks',lambda r,d:r.__delitem__(slice(5,None)))
        def incomplete_D(r,d):
            begin=dict(r[5],sequence=7,pair_id=7,request_id=-18)
            end=dict(r[6],sequence=8,pair_id=7,request_id=-18,native_prefill_ms_bits=bits(0.0))
            r.extend([begin,end])
        reject('incomplete_D_coverage',incomplete_D)
        runtime_adapter='/phase/libhalogen0173_phase_clock.so'
        base_env={'LD_PRELOAD':runtime_adapter+':/independent/capture.so','HGN0173_PHASE_RAW':'1',
            'HGN0173_PHASE_JOURNAL':'old','HGN0173_PHASE_ARM_FILE':'old-arm','ALLOY0173_FL_CAPTURE_ENABLE':'1'}
        with patch.object(Path,'resolve',return_value=PurePosixPath(runtime_adapter)):
            env=launch.compose_phase_environment(runtime_adapter,True,None,['--resident-gib','16'],base_env)
            assert env=={'LD_PRELOAD':'/independent/capture.so','ALLOY0173_FL_CAPTURE_ENABLE':'1'}
            checks.append('residency_bypass_precedes_journal_validation')
            env=launch.compose_phase_environment(runtime_adapter,True,None,['--resident-gib=16'],base_env)
            assert 'HGN0173_PHASE_RAW' not in env;checks.append('residency_equals_form_bypass')
            env=launch.compose_phase_environment(runtime_adapter,False,None,[],base_env)
            assert 'HGN0173_PHASE_RAW' not in env and env['LD_PRELOAD']=='/independent/capture.so'
            checks.append('default_off_strips_inherited_phase')
            fresh=target/'fresh.jsonl'
            env=launch.compose_phase_environment(runtime_adapter,True,fresh,[],base_env)
            assert env['LD_PRELOAD']==runtime_adapter+' /independent/capture.so'
            assert env['HGN0173_PHASE_RAW']=='1' and env['HGN0173_PHASE_JOURNAL']==str(fresh)
            assert env['ALLOY0173_FL_CAPTURE_ENABLE']=='1' and not fresh.exists()
            checks.append('serving_preload_composition_is_passive')
            arm=target/'fresh.arm'
            env=launch.compose_phase_environment(runtime_adapter,True,fresh,[],base_env,arm_file=arm)
            assert env['HGN0173_PHASE_ARM_FILE']==str(arm) and not arm.exists() and not fresh.exists()
            checks.append('deferred_launcher_never_creates_marker_or_journal')
            for name,value in [('arming_path_equals_journal',fresh),('relative_arming_path',Path('relative.arm'))]:
                try:launch.compose_phase_environment(runtime_adapter,True,fresh,[],base_env,arm_file=value)
                except ValueError:checks.append(name)
                else:raise AssertionError('Accepted invalid arming path: '+name)
            arm.write_bytes(b'')
            try:launch.compose_phase_environment(runtime_adapter,True,fresh,[],base_env,arm_file=arm)
            except ValueError:checks.append('preexisting_arm_marker_rejected')
            else:raise AssertionError('Accepted preexisting marker')
            env=launch.compose_phase_environment(runtime_adapter,True,None,['--resident-gib'],base_env,arm_file=arm)
            assert 'HGN0173_PHASE_ARM_FILE' not in env;checks.append('residency_bypass_strips_arm_and_skips_marker_validation')
    receipt=dict(schema='halogen0173.phase-clock-passive-tool-tests.v2',checks=checks,total=len(checks),
        all_passed=True,wsl_invoked=False,upstream_executed=False,linux_adapter_loaded=False,gpu_npu_used=False)
    (OUT/'tool-test-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
if __name__=='__main__':main()

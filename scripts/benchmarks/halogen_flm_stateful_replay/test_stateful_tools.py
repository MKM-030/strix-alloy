"""CPU fixtures for rejecting incomplete or causally invalid native evidence."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import json

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('stateful_tools_under_test', HERE / 'stateful_tools.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def report(mode='reference'):
    case = dict(name='natural8192', actual_input_tokens=8192, request_id=4,
                request_epoch='a'*32, request_sha256='b'*64,
                seed_tail_ids=list(range(512)), teacher_ids=list(range(1000,1128)))
    states = [dict(state_index=i, local_count=512+i, row_count=248070,
                   row_file='state-'+str(i)+'.bf16', greedy_id=1000+i,
                   timing=dict(started_ticks=100*i+10, finished_ticks=100*i+11),
                   row_write_timing=dict(started_ticks=100*i+12, finished_ticks=100*i+13)) for i in range(129)]
    cycles = [dict(step=i, committed_length=512+i, proposal_count=min(3,128-i),
                   consumed_inputs=min(3,128-i)-1, proposals=case['teacher_ids'][i:i+min(3,128-i)],
                   proposal_prefix_matches=min(3,128-i), label='natural', forced=False,
                   state_read_length=512+i, saved_length=512+i, saved_kv_from=0,
                   state_write_length=512+i, restored_length=512+i,
                   committed_authority=case['teacher_ids'][i], estimated_state_bytes=1024,
                   read_timing=dict(started_ticks=100*i+14, finished_ticks=100*i+15),
                   speculative_forward_timings=[dict(started_ticks=100*i+16+2*j,
                       finished_ticks=100*i+17+2*j) for j in range(min(3,128-i)-1)],
                   write_timing=dict(started_ticks=100*i+22, finished_ticks=100*i+23)) for i in range(128)]
    for index,label,expected in ((0,'forced_zero',0),(15,'forced_partial',1),(16,'forced_full',3)):
        cycles[index].update(label=label, forced=True, proposal_prefix_matches=expected)
        if expected<3:cycles[index]['proposals'][expected]+=1
    packet=dict(schema=m.base.INPUT_SCHEMA, authority='recorded_native_T',
                target_engine_sha256=m.base.TARGET_ENGINE,
                target_tokenizer_sha256=m.base.TARGET_TOKENIZER,cases=[copy.deepcopy(case)])
    return dict(schema='halogen0201.flm1012-state-parity.v1', mode=mode, complete=True,
                case=case, QPC_frequency=10000000, states=states,
                cycles=cycles if mode=='scenario' else [], native_acceptance=None,
                target_readiness=None, prefill_tok_s=None, decode_tok_s=None,
                full_retain_optimization_qualified=False, forced_branches_are_prediction_quality=False,
                natural_committed_predictions=128, natural_committed_next_ID_matches=128,
                startup_timing=dict(started_ticks=1,finished_ticks=9), runtime_requested='1.0.12',
                state_api_version=1,state_api_struct_size=72,input=packet)


class StatefulTests(unittest.TestCase):
    def test_complete_sequential_and_scenario_reports_are_accepted(self):
        for mode in ('reference','scenario'):
            self.assertIs(m.validate_report(report(mode),mode),None)

    def test_incomplete_last_state_is_rejected(self):
        value=report();value['states'].pop()
        with self.assertRaises(ValueError):m.validate_report(value,'reference')

    def test_partial_restore_or_wrong_authority_is_rejected(self):
        for field,value in (('restored_length',513),('state_write_length',-1),('committed_authority',42)):
            data=report('scenario');data['cycles'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.validate_report(data,'scenario')

    def test_speculative_tail_is_bounded_and_native_acceptance_stays_unmeasured(self):
        data=report('scenario');data['cycles'][-1]['consumed_inputs']=2
        with self.assertRaises(ValueError):m.validate_report(data,'scenario')
        data=report('scenario');data['native_acceptance']=1.0
        with self.assertRaises(ValueError):m.validate_report(data,'scenario')

    def test_exact_row_comparison_detects_the_last_word_without_relaxing_tolerance(self):
        row=bytes(248070*2);other=bytearray(row);other[-2:]=b'\x80\x3f'
        result=m.compare_words(row,bytes(other))
        self.assertFalse(result['passed'])
        self.assertEqual(result['exact_word_differences'],1)
        self.assertFalse(result['tolerance_relaxed'])

    def test_forced_schedule_labels_and_boolean_flags_are_required(self):
        for step,field,bad in ((0,'label','natural'),(15,'forced',False),(16,'label','forced_partial'),
                               (17,'label','forced_full'),(17,'forced',1),(0,'forced',1)):
            data=report('scenario');data['cycles'][step][field]=bad
            with self.subTest(step=step,field=field),self.assertRaises(ValueError):
                m.validate_report(data,'scenario')
        for bad in (True,0,None):
            data=report('scenario');data['forced_branches_are_prediction_quality']=bad
            with self.subTest(prediction_quality=bad),self.assertRaises(ValueError):
                m.validate_report(data,'scenario')

    def test_forced_fixture_tokens_cannot_be_replaced_by_other_matching_prefixes(self):
        for step in (0,15,16):
            data=report('scenario');v=data['cycles'][step]
            v['proposals'][-1]=(v['proposals'][-1]+1)%248070
            v['proposal_prefix_matches']=next((j for j,x in enumerate(v['proposals'])
                if x!=data['case']['teacher_ids'][step+j]),len(v['proposals']))
            with self.subTest(step=step),self.assertRaises(ValueError):m.validate_report(data,'scenario')

    def test_speculative_timing_count_order_and_restore_boundaries_are_required(self):
        mutations=(lambda v:v['speculative_forward_timings'].pop(),
                   lambda v:v['speculative_forward_timings'].reverse(),
                   lambda v:v['speculative_forward_timings'][0].update(started_ticks=14),
                   lambda v:v['speculative_forward_timings'][-1].update(finished_ticks=23),
                   lambda v:v.update(speculative_forward_timings=None))
        for index,mutate in enumerate(mutations):
            data=report('scenario');mutate(data['cycles'][0])
            with self.subTest(index=index),self.assertRaises(ValueError):m.validate_report(data,'scenario')
        data=report('scenario');data['cycles'][-1]['speculative_forward_timings']=[dict(started_ticks=12716,finished_ticks=12717)]
        with self.assertRaises(ValueError):m.validate_report(data,'scenario')

    def test_natural_counter_is_reconstructed_before_forced_branches(self):
        for field,bad in (('natural_committed_predictions',127),('natural_committed_next_ID_matches',127)):
            data=report('scenario');data[field]=bad
            with self.subTest(field=field),self.assertRaises(ValueError):m.validate_report(data,'scenario')
        data=report('scenario');data['states'][15]['greedy_id']=44
        with self.assertRaises(ValueError):m.validate_report(data,'scenario')
        data['natural_committed_next_ID_matches']=127
        m.validate_report(data,'scenario')
        data=report('scenario');data['cycles'][17]['proposals'][0]=44
        data['cycles'][17]['proposal_prefix_matches']=0
        with self.assertRaises(ValueError):m.validate_report(data,'scenario')

    def test_startup_and_row_write_qpc_chronology_are_required(self):
        for mode in ('reference','scenario'):
            for index,mutate in enumerate((lambda d:d['startup_timing'].update(finished_ticks=11),
                    lambda d:d['states'][0]['row_write_timing'].update(started_ticks=10),
                    lambda d:d['states'][0]['row_write_timing'].update(finished_ticks=111),
                    lambda d:d['states'][0].pop('row_write_timing'))):
                data=report(mode);mutate(data)
                with self.subTest(mode=mode,index=index),self.assertRaises(ValueError):m.validate_report(data,mode)
        data=report('scenario');data['states'][0]['row_write_timing']['finished_ticks']=15
        with self.assertRaises(ValueError):m.validate_report(data,'scenario')

    def test_new_runtime_api_and_exact_reported_input_authority_are_required(self):
        for field,bad in (('runtime_requested','1.0.7'),('state_api_version',2),('state_api_struct_size',64)):
            data=report();data[field]=bad
            with self.subTest(field=field),self.assertRaises(ValueError):m.validate_report(data,'reference')
        for mutate in (lambda d:d['input'].update(target_engine_sha256='0'*64),
                       lambda d:d['input']['cases'][0]['teacher_ids'].__setitem__(0,42)):
            data=report();mutate(data)
            with self.assertRaises(ValueError):m.validate_report(data,'reference')

    def test_greedy_is_reconstructed_from_full_bf16_rows_including_ties(self):
        row=bytearray(248070*2)
        row[0:2]=b'\x00\x80'  # -0 and +0 tie; C++ preserves the first index.
        self.assertEqual(m.row_greedy(bytes(row)),0)
        row[-2:]=b'\x80\x3f'
        self.assertEqual(m.row_greedy(bytes(row)),248069)
        row[-2:]=b'\x80\x7f'
        with self.assertRaises(ValueError):m.row_greedy(bytes(row))

    def test_matching_rows_with_fabricated_greedy_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=[]
            for mode in ('reference','scenario'):
                path=Path(tmp)/(mode+'.json');directory=Path(str(path)+'.rows');directory.mkdir()
                data=report(mode);data['bf16_rows_directory']=str(directory)
                path.write_text(json.dumps(data),encoding='utf-8')
                (directory/'state-0.bf16').write_bytes(bytes(248070*2))
                paths.append(path)
            with self.assertRaisesRegex(ValueError,'greedy'):m.compare(*paths)


if __name__=='__main__':unittest.main()

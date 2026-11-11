"""CPU-only authority scheduling, bounded inputs and full-row equality tests."""
import copy
import importlib.util
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('growing_replay_tools_under_test', HERE / 'replay_tools.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ReplayTests(unittest.TestCase):
    def packet(self):
        return dict(schema=m.INPUT_SCHEMA, authority='recorded_native_T',
            target_engine_sha256=m.TARGET_ENGINE, target_tokenizer_sha256=m.TARGET_TOKENIZER,
            cases=[dict(name='natural8192', request_id=4, request_epoch='a'*32,
                actual_input_tokens=8192, request_sha256='b'*64,
                seed_tail_ids=list(range(512)), teacher_ids=list(range(1000,1128)))])

    def test_bounded_input(self):
        m.validate_input(self.packet())
        for key, replacement in [('seed_tail_ids',[1]*511),('teacher_ids',[1]*127),('teacher_ids',[m.ROWS]*128)]:
            packet=self.packet();packet['cases'][0][key]=replacement
            with self.assertRaises(ValueError):m.validate_input(packet)

    def test_prediction_precedes_authoritative_append(self):
        trace=m.cpu_schedule(self.packet()['cases'][0])
        self.assertEqual(trace[0],('seed',512))
        self.assertEqual(trace[1:5],[('predict',512),('append',1000),('predict',513),('append',1001)])
        self.assertEqual(trace[-2:],[('predict',639),('append',1127)])
        self.assertEqual(sum(op=='predict' for op,_ in trace),128)

    def test_every_shared_row_compared(self):
        before=bytearray(m.ROWS*2);after=bytearray(before);after[-2:]=struct.pack('<H',0x3f80)
        result=m.compare_words(before,after)
        self.assertEqual(result['compared_rows'],m.ROWS)
        self.assertEqual(result['exact_word_differences'],1)
        self.assertEqual(result['first_mismatch_rows'],[m.ROWS-1])
        self.assertFalse(result['passed'])

    def test_no_tolerance_relaxation_or_nonfinite(self):
        rows=bytes(m.ROWS*2)
        self.assertTrue(m.compare_words(rows,rows)['passed'])
        changed=bytearray(rows);changed[:2]=struct.pack('<H',0x7fc0)
        with self.assertRaisesRegex(ValueError,'nonfinite'):m.compare_words(changed,changed)
        with self.assertRaisesRegex(ValueError,'row bytes'):m.compare_words(rows[:-1],rows)

    def test_incomplete_states_rejected(self):
        packet=self.packet()
        with self.assertRaisesRegex(ValueError,'129'):m.validate_case_report(dict(states=[]),packet['cases'][0])

    def test_host_and_native_qpc_order(self):
        timing=dict(frequency=10000000,host_call_started_ticks=10,operation_started_ticks=11,
                    logits_owned_ticks=12,host_call_returned_ticks=13)
        m.validate_timing(timing)
        timing['logits_owned_ticks']=14
        with self.assertRaisesRegex(ValueError,'QPC'):m.validate_timing(timing)

    def test_reference_never_calls_proposer(self):
        trace=m.cpu_schedule(self.packet()['cases'][0],reference=True)
        self.assertEqual(sum(op=='predict' for op,_ in trace),0)
        self.assertEqual(len(trace),129)

    def test_no_speculative_inputs_and_no_target_readiness_claim(self):
        case=self.packet()['cases'][0]
        report=dict(name=case['name'],request_id=case['request_id'],request_epoch=case['request_epoch'],
            seed_tail_ids=case['seed_tail_ids'],teacher_ids=case['teacher_ids'],states=[{}]*129,
            predictions=[],speculative_inputs=1,consumer_arrival_timestamp=None,target_need_timestamp=None)
        with self.assertRaisesRegex(ValueError,'speculative'):m.validate_case_report(report,case)

    def report(self):
        case=self.packet()['cases'][0];report=copy.deepcopy(case)
        report.update(speculative_inputs=0,consumer_arrival_timestamp=None,target_need_timestamp=None,
            consumer_arrived_before_target_need=None,states=[],predictions=[])
        for i in range(129):
            start=i*100+10
            report['states'].append(dict(state_index=i,local_count=512+i,row_count=m.ROWS,greedy_id=3,
                timing=dict(clock='Windows QPC',frequency=10000000,host_call_started_ticks=start,
                    operation_started_ticks=start+1,logits_owned_ticks=start+2,host_call_returned_ticks=start+3),
                rows_write_started_ticks=start+4,rows_write_finished_ticks=start+5))
            if i<128:
                report['predictions'].append(dict(ordinal=i,local_count=512+i,predicted_id=3,
                    authoritative_id_after_prediction=case['teacher_ids'][i],owned_words_unchanged=True,
                    context_unchanged=True,speculative_inputs=0,ready_started_ticks=start+10,
                    ready_finished_ticks=start+11,consumer_arrival_timestamp=None,target_need_timestamp=None,
                    consumer_arrived_before_target_need=None))
        return report,case

    def test_prediction_before_owned_rows_rejected(self):
        report,case=self.report();m.validate_case_report(report,case)
        report['predictions'][0]['ready_started_ticks']=0
        with self.assertRaisesRegex(ValueError,'QPC'):m.validate_case_report(report,case)

    def test_mixed_state_frequencies_rejected(self):
        report,case=self.report();report['states'][2]['timing']['frequency']=20000000
        with self.assertRaisesRegex(ValueError,'frequency'):m.validate_case_report(report,case)

    def test_cross_state_order_rejected(self):
        report,case=self.report();report['states'][1]['timing'].update(host_call_started_ticks=1,
            operation_started_ticks=2,logits_owned_ticks=3,host_call_returned_ticks=4)
        with self.assertRaisesRegex(ValueError,'QPC'):m.validate_case_report(report,case)


if __name__=='__main__':unittest.main()

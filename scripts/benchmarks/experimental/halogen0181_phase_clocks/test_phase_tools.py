import copy
import struct
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from verify_phase_journal import verify_records as read_records,verify_capture_receipt
from observe_api_done import DObserver
from compose_environment import compose_environment


def verify_records(rows,d_rows=None):
    return read_records(rows,d_rows,api_sha256='a'*64 if d_rows else None)


def fixture():
    header=dict(kind='activation',schema='halogen0181.passive-phase.v1',
        engine_sha256='d946e7b32a46400884ee7309b909da73f4a6586140cd9f9b94fa9ff583b3c3ab',
        provider_sha256='972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00',
        nonce='0'*32,engine_base=0x100000,provider_base=0x800000,real_clock_address=0x8d5490,
        raw_clock_id=4,default_off=1,native_returns_unchanged=1,deferred_arm=1,arm_file_device=7,arm_file_inode=9)
    rows=[header]
    def endpoint(phase,begin,sequence,pair_id,obj,begin_obj,native_start,native,before,start_before):
        rvas={(1,1):0x181870f,(1,0):0x1818d60,(2,1):0x181a8dc,(2,0):0x181e7c2}
        row=dict(kind='phase',sequence=sequence,phase=phase,begin=begin,pair_id=pair_id,request_epoch=1,
          status=0,request_id=-17,caller_rva=rvas[phase,begin],caller_stack=0x1000,tid=91,
          object=obj,begin_object=begin_obj,native_return_ns=native,returned_ns=native,native_start_ns=native_start,
          raw_before_ns=before,raw_after_ns=before+20,start_raw_before_ns=start_before,start_raw_after_ns=start_before+20,
          observed_native_start_ns=native_start,object_native_start_ns=native_start if phase==2 and not begin else 0,
          bookkeeping_done_raw_ns=before+50,dropped=0)
        if phase==2 and not begin:
          row.update(native_prefill_ms_bits=struct.unpack('<Q',struct.pack('<d',1.0))[0],prompt_count=37,predicted_count=9)
        elif phase==2:row.update(prompt_count=37,predicted_count=1)
        rows.append(row)
        rows.append(dict(kind='overhead',sequence=sequence+1,phase_sequence=sequence,request_epoch=1,
          raw_before_ns=before,raw_after_ns=before+20,bookkeeping_done_raw_ns=before+50,
          phase_emit_done_raw_ns=before+80,status=0,dropped=0))
    endpoint(1,1,1,1,0x100,0x100,1000000,1000000,10000000,10000000)
    endpoint(1,0,3,1,0x100,0x100,1000000,2000000,11000000,10000000)
    endpoint(2,1,5,5,0x200,0x200,3000000,3000000,12000000,12000000)
    endpoint(2,0,7,5,0x300,0x200,3000000,5000000,14000000,12000000)
    d=[dict(kind='activation',schema='halogen0181.native-d-after-parser.v1',nonce='0'*32,api_sha256='a'*64,
            deferred_arm=1,arm_file_device=7,arm_file_inode=9),
       dict(kind='native_d',sequence=1,request_id=-17,prompt_count=37,predicted_count=9,
            prefill_ms=1.0,decode_ms=2.0,reason='length',parts=['D','-17','length','37','9','1.0','2.0'],stock_parser_fields_unchanged=True),
       dict(kind='completion',request_count=1,failed=False)]
    return rows,d


class PhaseTests(unittest.TestCase):
    def test_changed_native_return_is_rejected(self):
        rows,d=fixture();rows[7]['returned_ns']+=1
        with self.assertRaisesRegex(ValueError,'native return'):
            verify_records(rows,d)

    def test_moved_decode_and_native_D_rounding_are_bound_without_rates(self):
        rows,d=fixture();value=verify_records(rows,d)
        self.assertTrue(value['native_d_matched']);self.assertTrue(value['requests'][0]['moved_decode'])
        self.assertEqual(value['requests'][0]['native_prefill_ms'],1.0)
        self.assertEqual(value['requests'][0]['raw_decode_lower_ms'],1.99998)
        self.assertIsNone(value['qualified_tok_per_second'])
        self.assertFalse(value['clean_serving_phase_rates_qualified'])
        self.assertFalse(value['phase_count_scope_qualified'])
        self.assertFalse(value['observed_instrumented_durations_verified'])
        self.assertEqual(value['requests'][0]['observed_decode_count_delta'],8)

    def test_missing_overhead_record_is_rejected(self):
        rows,d=fixture();rows.pop()
        with self.assertRaisesRegex(ValueError,'Incomplete'):verify_records(rows,d)

    def test_same_ID_different_epoch_is_rejected(self):
        rows,d=fixture();rows[5]['request_epoch']=2
        with self.assertRaisesRegex(ValueError,'collision'):verify_records(rows,d)

    def test_moved_native_start_tamper_is_rejected(self):
        rows,d=fixture();rows[7]['object_native_start_ns']+=1
        with self.assertRaisesRegex(ValueError,'Moved Decode'):verify_records(rows,d)

    def test_raw_clock_reversal_is_rejected(self):
        rows,d=fixture();rows[3]['raw_before_ns']=rows[1]['raw_after_ns']-1
        with self.assertRaisesRegex(ValueError,'RAW phase'):verify_records(rows,d)

    def test_native_prefill_scalar_tamper_is_rejected(self):
        rows,d=fixture();rows[7]['native_prefill_ms_bits']=struct.unpack('<Q',struct.pack('<d',1.1))[0]
        with self.assertRaisesRegex(ValueError,'Prefill'):verify_records(rows,d)

    def test_D_nonce_and_count_tamper_are_rejected(self):
        for key,value in [('nonce','f'*32),('prompt_count',38)]:
            rows,d=fixture();d[0 if key=='nonce' else 1][key]=value
            with self.assertRaises(ValueError):verify_records(rows,d)

    def test_expected_API_pin_is_required_and_checked(self):
        rows,d=fixture()
        with self.assertRaisesRegex(ValueError,'expected API'):read_records(rows,d)
        with self.assertRaisesRegex(ValueError,'source header'):read_records(rows,d,api_sha256='b'*64)

    def test_copied_D_frame_and_completion_are_required(self):
        rows,d=fixture();d[1]['parts'][4]='10'
        with self.assertRaisesRegex(ValueError,'Copied native D'):verify_records(rows,d)
        rows,d=fixture();d.pop()
        with self.assertRaisesRegex(ValueError,'completed native D'):verify_records(rows,d)

    def test_same_epoch_sequential_Prefill_object_collision_is_rejected(self):
        rows,d=fixture();other=copy.deepcopy(rows[1]);other.update(sequence=5,pair_id=5,object=0x101,begin_object=0x101)
        rows.insert(5,other)
        with self.assertRaisesRegex(ValueError,'Prefill object collision'):verify_records(rows,d)

    def test_actual_request_receipt_binds_QPC_and_saved_bytes_without_qualifying_rates(self):
        rows,d=fixture()
        with tempfile.TemporaryDirectory(prefix='hgn0181-coupling-fixture-') as folder:
            root=Path(folder);request=b'offline synthetic request';reply=b'offline synthetic reply'
            (root/'request.bin').write_bytes(request);(root/'reply.bin').write_bytes(reply)
            receipt=dict(schema='halogen0181.actual-capture-coupling.v1',capture_kind='fresh_actual',nonce='0'*32,
                engine_sha256=rows[0]['engine_sha256'],provider_sha256=rows[0]['provider_sha256'],api_sha256='a'*64,
                clock_journal_sha256='c'*64,native_d_journal_sha256='d'*64,companion_closed=True,companion_failed=False,
                api_callable_source_verified=True,adapter_sha256='e'*64,source_pins_sha256='f'*64,
                profile_manifest_sha256='1'*64,client_source_sha256='2'*64,
                requests=[dict(request_epoch=1,request_id=-17,prompt_count=37,predicted_count=9,
                    request_path='request.bin',request_sha256=hashlib.sha256(request).hexdigest(),
                    reply_path='reply.bin',reply_sha256=hashlib.sha256(reply).hexdigest(),
                    qpc_start_ticks=100,qpc_complete_ticks=2100,qpc_frequency_hz=1000000)])
            value=verify_capture_receipt(verify_records(rows,d),receipt,'c'*64,'d'*64,artifact_root=root)
            self.assertTrue(value['actual_request_evidence_coupled']);self.assertEqual(value['requests'][0]['actual_request_qpc_wall_ms'],2)
            self.assertIsNone(value['qualified_tok_per_second']);self.assertFalse(value['independent_RAW_QPC_calibration_completed'])
            self.assertFalse(value['phase_count_scope_qualified']);self.assertFalse(value['measured_overhead_protocol_completed'])
            receipt['requests'][0]['reply_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'saved request/reply hash'):verify_capture_receipt(verify_records(rows,d),receipt,'c'*64,'d'*64,artifact_root=root)

    def test_nonzero_status_or_drop_is_rejected(self):
        for key in ('status','dropped'):
            rows,d=fixture();rows[3][key]=1
            with self.assertRaisesRegex(ValueError,'failure/drop'):verify_records(rows,d)

    def test_defaultoff_and_residency_remove_only_owned_observer(self):
        base={'LD_PRELOAD':'/normal.so /obs.so','HGN0181_OBSERVER_ENABLE':'1'}
        for args in ((),('--resident-gib=16',)):
            env=compose_environment('/obs.so',enabled=bool(args),engine_args=args,environment=base)
            self.assertEqual(env['LD_PRELOAD'],'/normal.so');self.assertNotIn('HGN0181_OBSERVER_ENABLE',env)

    def test_API_observer_disabled_preserves_identity_and_one_stock_call(self):
        returned={'value':'same'};calls=[]
        def stock(parts):calls.append(parts);return returned
        wrapped=DObserver().wrap(stock);parts=['D']
        self.assertIs(wrapped(parts),returned);self.assertEqual(calls,[parts])

    def test_API_observer_after_stock_preserves_same_object_and_original_fields(self):
        with tempfile.TemporaryDirectory(prefix='hgn0181-offline-test-') as folder:
            api=Path(folder)/'api.py';api.write_text('# offline fixture only\n')
            log=Path(folder)/'D.jsonl';obs=DObserver(True,journal=log,nonce='0'*32,api_file=api,api_sha256=hashlib.sha256(api.read_bytes()).hexdigest())
            returned=dict(reason='length',n_prompt=37,n_gen=9,prefill_ms=1.0,decode_ms=2.0);calls=[]
            def stock(parts):
                self.assertFalse(log.exists());calls.append(parts);return returned
            parts=['D','-17','length','37','9','1.0','2.0'];wrapped=obs.wrap(stock)
            self.assertIs(wrapped(parts),returned);self.assertEqual(calls,[parts]);self.assertFalse(obs.failed)
            obs.close();rows=[json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(rows[1]['request_id'],-17);self.assertEqual(rows[1]['parts'],parts)
            self.assertEqual(returned,dict(reason='length',n_prompt=37,n_gen=9,prefill_ms=1.0,decode_ms=2.0))

    def test_API_observer_failure_preserves_stock_result(self):
        obs=DObserver();obs.enabled=True;obs.arm=None;obs.api_sha256='a'*64;obs.nonce='0'*32
        returned={};wrapped=obs.wrap(lambda parts:returned)
        self.assertIs(wrapped(['bad']),returned);self.assertTrue(obs.failed)

    def test_API_arm_read_failure_preserves_stock_result(self):
        obs=DObserver();obs.enabled=True;returned={}
        with mock.patch.object(obs,'_arm_ready',side_effect=PermissionError('fixture denied')):
            self.assertIs(obs.wrap(lambda parts:returned)(['D']),returned)
        self.assertTrue(obs.failed)

    def test_API_companion_cannot_reopen_after_close(self):
        obs=DObserver();obs.enabled=True;obs.arm=None;obs.close()
        returned={};self.assertIs(obs.wrap(lambda parts:returned)(['bad']),returned)
        self.assertFalse(obs.failed)

    def test_API_companion_same_arm_and_journal_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='hgn0181-offline-test-') as folder:
            api=Path(folder)/'api.py';api.write_text('# offline fixture\n')
            log=Path(folder)/'D.jsonl'
            with self.assertRaisesRegex(ValueError,'Distinct'):
                DObserver(True,journal=log,arm_file=log,nonce='0'*32,api_file=api,
                    api_sha256=hashlib.sha256(api.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()

"""Fake-only closed-evidence checks. No campaign result is opened."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import struct
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dnz_offline_audit', HERE / 'audit_terminal.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def response(request_id=1):
    scopes = dict(head=dict(rounds=10, drafted=20, accepted=12),
                  lookup=dict(rounds=0, drafted=0, accepted=0),
                  grammar=dict(rounds=0, drafted=0, accepted=0))
    return dict(id='fake-' + str(request_id), choices=[dict(text='Grüße', finish_reason='length')],
                usage=dict(prompt_tokens=2048, completion_tokens=128, total_tokens=2176),
                timings=dict(raw_native_request_id=request_id, prompt_n=2048, predicted_n=128,
                    cache_n=0, draft_n=20, draft_n_accepted=12,
                    speculation=dict(drafter='mtp', rounds=10, **scopes)))


def counter(value):
    return dict(identity=dict(pid=123, starttime_ticks=99, sha256=m.ENGINE_SHA,bytes=35410384), container_id='container',
                load_base='0x1000', counter_address='0x21cb518', counter_rva='0x21ca518',
                counter_value=value, read_only=True, counter_bytes=8)


def bracket(delta=0):
    return dict(before_host_started_ns=1, before_host_finished_ns=2,
                before=counter(10), after=counter(10 + delta),
                after_host_started_ns=4_000_000_005, after_host_finished_ns=4_000_000_006,
                outside_HTTP_QPC_proved=True, delta=delta)


def transport():
    return dict(http_status=200, qpc_start_ns=3, qpc_end_ns=4_000_000_003,
                http_qpc_seconds=4.0, minimum_reserve_gib=18.01)


def raw_row(pf=2_000_000_000, dec=1_000_000_000):
    return dict(valid=True, prefill_raw_lower_ns=pf-10, prefill_raw_upper_ns=pf+10,
                decode_raw_lower_ns=dec-10, decode_raw_upper_ns=dec+10,
                prompt=2048, processed_prompt=2048, generated_end=128, generated_begin=1,
                generated_delta=127, decode_numerator=128, output_cap=128,
                prefill_raw_tps_mid=2048e9/pf, decode_raw_tps_mid=128e9/dec,
                prefill_raw_tps_lower=2048e9/(pf+10), prefill_raw_tps_upper=2048e9/(pf-10),
                decode_raw_tps_lower=128e9/(dec+10), decode_raw_tps_upper=128e9/(dec-10))


class Tests(unittest.TestCase):
    def test_confirmation_precedes_any_file_access(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('file accessed')):
            with self.assertRaisesRegex(ValueError, 'terminal confirmation'):
                m.audit_terminal(Path('not-a-real-handle.json'), confirmed=False)

    def test_partial_or_unrestored_cannot_be_headline(self):
        for key in ('terminal', 'completed', 'restored'):
            value = dict(terminal=True, completed=True, restored=True,
                         phase='complete_normal_online', ended_utc='fake')
            value[key] = False
            with self.assertRaises(ValueError): m.require_complete(value)

    def test_response_scopes_and_UTF8_are_exact_but_not_native_ID_proof(self):
        metrics = m.response_metrics(response())
        self.assertEqual(metrics['actual_input_tokens'], 2048)
        self.assertEqual(metrics['actual_output_tokens'], 128)
        self.assertEqual(metrics['output_utf8_bytes'], len('Grüße'.encode()))
        for update in ('text', 'accepted', 'length', 'reasoning', 'cache'):
            other = response()
            if update == 'text': other['choices'][0]['text'] += 'x'
            if update == 'accepted':
                other['timings']['speculation']['head']['accepted'] = 11
                other['timings']['draft_n_accepted'] = 11
            if update == 'length': other['usage']['completion_tokens'] = 127
            if update == 'reasoning': other['choices'][0]['text'] = '<think>x</think>'
            if update == 'cache': other['timings']['cache_n'] = 1
            with self.assertRaises(ValueError):
                m.require_response_parity(metrics, m.response_metrics(other))

    def test_counter_width_mode_identity_and_monotonicity(self):
        self.assertEqual(m.counter_delta(counter(10), counter(10), 0), 0)
        self.assertEqual(m.counter_delta(counter(10), counter(12), 1), 2)
        for before, after, mode in ((counter(10),counter(11),0),
                                    (counter(10),counter(10),1),
                                    (counter(10),counter(9),1),
                                    (counter(10),counter(11),True)):
            with self.assertRaises(ValueError): m.counter_delta(before, after, mode)
        bad=counter(12);bad['identity']['starttime_ticks']=100
        with self.assertRaises(ValueError):m.counter_delta(counter(10),bad,1)
        bad=counter(12);bad['identity']['sha256']='a'*64
        with self.assertRaises(ValueError):m.counter_delta(bad,bad,1)

    def test_counter_reads_must_be_outside_HTTP_and_reserve_at_least18(self):
        self.assertEqual(m.validate_transport(transport(), bracket(), 0)['HTTP_seconds'], 4)
        for kind in ('inside', 'resource', 'HTTP'):
            t,b=transport(),bracket()
            if kind=='inside':b['before_host_finished_ns']=4
            if kind=='resource':t['minimum_reserve_gib']=17.99
            if kind=='HTTP':t['http_qpc_seconds']=3.99
            with self.assertRaises(ValueError):m.validate_transport(t,b,0)

    def test_RAW_brackets_not_API_or_uniform_clock_adjustments(self):
        rates=m.raw_rates(raw_row(),transport())
        self.assertEqual(rates['RAW_prefill_tok_s'],1024)
        self.assertEqual(rates['RAW_decode_tok_s'],128)
        bad=raw_row();bad['prefill_raw_upper_ns']=5_000_000_000
        with self.assertRaises(ValueError):m.raw_rates(bad,transport())
        bad=raw_row();bad['decode_numerator']=127
        with self.assertRaises(ValueError):m.raw_rates(bad,transport())

    def test_arithmetic_means_exclude_warmup_and_keep_all3(self):
        rows=[dict(ordinal=i,phase='warmup_excluded' if i==0 else 'measured',
                   RAW_prefill_tok_s=v,RAW_decode_tok_s=v/2,HTTP_seconds=v/10,
                   RAW_prefill_tok_s_lower=v-.1,RAW_prefill_tok_s_upper=v+.1,
                   RAW_decode_tok_s_lower=v/2-.1,RAW_decode_tok_s_upper=v/2+.1,
                   scoped=response()['timings']['speculation'])
              for i,v in enumerate((99999,10,20,30))]
        report=m.summarize_arm(rows)
        self.assertEqual(report['RAW_prefill_tok_s']['mean'],20)
        self.assertEqual(report['HTTP_seconds']['mean'],2)
        self.assertEqual(report['acceptance_scopes']['head'],
                         dict(accepted=36,drafted=60,rate=.6))
        self.assertIsNone(report['acceptance_scopes']['lookup']['rate'])
        with self.assertRaises(ValueError):m.summarize_arm(rows[:3])

    def test_same262pins_no_duplicate_or_stale_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            pins=[]
            for i in range(262):
                path=Path(temporary)/str(i);data=str(i).encode();path.write_bytes(data)
                pins.append(dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            self.assertEqual(m.verify_pins(pins),262)
            duplicate=copy.deepcopy(pins);duplicate[-1]=duplicate[0]
            with self.assertRaises(ValueError):m.verify_pins(duplicate)
            Path(pins[100]['path']).write_bytes(b'changed')
            with self.assertRaises(ValueError):m.verify_pins(pins)

    def test_artifact_absence_and_exact_original_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'artifact';backup=Path(temporary)/'backup'
            m.restored_artifacts([dict(path=str(target),before=None)])
            target.write_bytes(b'old');backup.write_bytes(b'old');original=m.file_pin(target)
            m.restored_artifacts([dict(path=str(target),before=original,backup=str(backup))])
            target.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                m.restored_artifacts([dict(path=str(target),before=original,backup=str(backup))])

    def test_real_frozen_RAW_validator_with_entirely_fake_journal(self):
        validator=m._validator(m.SOURCE)
        epoch=0x020300D800000001;pcs={1:0x1f810af,2:0x1f818d5,3:0x1f83c1a,4:0x1fa1150}
        fbits=lambda f:struct.unpack('<Q',struct.pack('<d',f))[0]
        events=[]
        for site in range(1,5):
            native=(site+9)*1_000_000_000;obj=100 if site<3 else 200
            event={key:0 for key in validator.FIELDS}
            event.update(caller_rva=pcs[site],caller_stack=obj+1000,saved_r15=obj,saved_r14=obj,
                saved_rbx=12_000_000_000 if site==4 else 0,object=obj,request_id=1,native=native,
                native_start=10_000_000_000 if site<=2 else 12_000_000_000,tid=44,
                raw_before=native,raw_after=native+10,site=site,status=0,prompt=2048,
                generated=128 if site==4 else 1,native_slot=0,
                prefill_accum_bits=fbits(0),published_prefill_bits=fbits(1000 if site>=3 else 0))
            events.append(event)
        data=validator.HEADER.pack(validator.MAGIC,3,4,0,1,0,4,epoch)
        data+=b''.join(validator.RECORD.pack(*(event[key] for key in validator.FIELDS)) for event in events)
        data+=bytes(validator.CAPTURE_BYTES-len(data))
        parsed=validator.read_capture(data,0,epoch);reply=response()
        reply['timings'].update(prompt_ms=1000,predicted_ms=1000)
        result=validator.validate(parsed,reply,pcs=pcs,request=dict(max_tokens=128,stream=False),require_cold=True)
        self.assertEqual(result['generated_delta'],127)
        self.assertEqual(result['decode_numerator'],128)
        parsed[2]['request_id']=2
        with self.assertRaises(ValueError):
            validator.validate(parsed,reply,pcs=pcs,request=dict(max_tokens=128,stream=False),require_cold=True)

    def test_partial_recovery_preserves_original_failure_and_never_qualifies_rates(self):
        profile=dict(path='fake-profile',bytes=1,sha256='p')
        original=dict(terminal=False,completed=False,restored=False,phase='restoration_incomplete',
                      error=dict(message='22-GiB memory reserve unavailable'),
                      restoration_error=dict(message='Unexpected owned startup phase'))
        original_pin=dict(path='fake-handle',bytes=2,sha256='h')
        normal=dict(profile=profile,outer=dict(phase='ready',context=32768,port=8840,run_id='outer'),
            inner=dict(phase='ready',context=32768,run_id='inner'),gateway=dict(status='ok',context=32768),
            native=dict(status='ok',context=32768,slot_ctx=32768,kv_pool_positions=32768,slots=1,
                        version=dict(api='0.20.3',engine='0.20.3',match=True)))
        receipt=dict(schema='halogen0203.DNZ8K-supplemental-normal-recovery.v1',
            original_campaign_handle=original_pin,original_campaign_flags={k:original[k] for k in ('terminal','completed','restored','phase')},
            coordinator_identity_exited=True,original_evidence_unchanged=True,
            campaign_session_id=35211,campaign_exit_code=1,supplemental_session_id=13542,supplemental_exit_code=0,
            supplemental_ready=True,restored_after_supplemental_recovery=True,normal_profile=profile,normal=normal,
            benchmark_requests_total=1,excluded_warmups=1,measured_requests=0,candidate_started=False,
            DNZ_gain_qualified=False,full_goal_achieved=False,
            original_failure=original['error'],original_restoration_error=original['restoration_error'])
        supplement=dict(terminal=True,ready=True,stage='normal_ready_open',benchmark_requests=0,
                        effective_service_startup_floor_GiB=[30,131],normal=normal)
        smoke=dict(status=200,not_benchmark=True,response=dict(choices=[dict(message=dict(content='READY'))]))
        result=m.reconcile_partial_recovery(original,original_pin,receipt,supplement,normal,smoke,profile)
        self.assertFalse(result['original_campaign_flags']['terminal'])
        self.assertFalse(result['original_campaign_flags']['restored'])
        self.assertTrue(result['later_normal_recovery_verified'])
        self.assertFalse(result['headline_qualified'])
        self.assertIsNone(result['DNZ_tok_s_difference'])
        for field in ('coordinator_identity_exited','restored_after_supplemental_recovery','candidate_started'):
            bad=copy.deepcopy(receipt);bad[field]=not bad[field]
            with self.assertRaises(ValueError):
                m.reconcile_partial_recovery(original,original_pin,bad,supplement,normal,smoke,profile)


if __name__=='__main__':unittest.main()

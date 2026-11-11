"""Focused synthetic v3 contract tests; no campaign, process or device calls."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SCHEMA = 'halogen0203.DNZ-arena2048-capacity8192-actual2048-bindings.v3'
RECORD = 'halogen0203.DNZ-GPU-arena2048-cohort.v3'


def binding():
    return dict(schema=SCHEMA, root_sealed=True, dependency_closure_reviewed=True,
        reviewed_dependency_count=262, pins=[dict(path='fake-'+str(i)) for i in range(262)],
        guards=dict(startup_physical=30, startup_commit=131, entry=22, runtime=18),
        NPU_helper=False, external_stream=False, capacity_context=8192,
        paired_prefill_arena=2048)


def profile(mode=0):
    return dict(engine=dict(context=8192, prefill_chunk=2048, max_prefill_tokens=2048,
        kernel_controls=dict(HALOGEN_DN_Z_STREAM=mode)), backend=dict(context=8192), concurrency=1)


def manifest(mode=0):
    return dict(environment=dict(HALOGEN_DN_Z_STREAM=str(mode), HALOGEN_CTX='8192',
        HALOGEN_KV_POOL_POSITIONS='8192', HALOGEN_MAX_TOK='2048', HALOGEN_PREFILL_CHUNK='2048',
        HALOGEN_PROMPT_CACHE='0', HGN0203_RAW_ENABLE='1', HGN0203_API_NATIVE_ID='1'))


class Tests(unittest.TestCase):
    def setUp(self):
        path=HERE/'audit_terminal.py'
        self.assertTrue(path.exists(), 'Separate v3 offline auditor is not implemented')
        spec=importlib.util.spec_from_file_location('dnz_v3_contract_audit',path)
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)

    def test_default_cli_is_inert_without_root_freeze(self):
        with patch.object(sys,'argv',['audit_terminal.py']), patch.object(Path,'read_bytes',side_effect=AssertionError('evidence access')):
            self.assertEqual(self.m.main(),0)

    def test_root_hash_and_exact_declared_count_are_required_not_user_weakenable(self):
        value=binding();data=json.dumps(value).encode();digest=self.m.sha(data)
        self.assertEqual(self.m.validate_root_binding(data,data,digest,262),value)
        for expected in (None,True,261,263):
            with self.subTest(expected=expected),self.assertRaises(ValueError):
                self.m.validate_root_binding(data,data,digest,expected)
        for change in ('schema','root_sealed','reviewed_dependency_count','pins','paired_prefill_arena','guards'):
            bad=copy.deepcopy(value)
            if change=='schema':bad[change]='halogen0203.DNZ-capacity8192-actual2048-bindings.v2'
            if change=='root_sealed':bad[change]=False
            if change=='reviewed_dependency_count':bad[change]=261
            if change=='pins':bad[change]=bad[change][:-1]
            if change=='paired_prefill_arena':bad[change]=8192
            if change=='guards':bad[change]['entry']=21
            encoded=json.dumps(bad).encode()
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.m.validate_root_binding(encoded,encoded,self.m.sha(encoded),262)
        with self.assertRaises(ValueError):self.m.validate_root_binding(data,data,'0'*64,262)
        other=json.dumps(dict(value,external_stream=True)).encode()
        with self.assertRaises(ValueError):self.m.validate_root_binding(other,data,digest,262)

    def test_native_capacity8192_is_independent_of_prefill2048(self):
        self.m.validate_profile_native(profile(),manifest(),0)
        self.m.validate_profile_native(profile(1),manifest(1),1)
        for kind in ('old_arena','native_context2048','profile_context2048','explicit_slots','external','wrong_mode'):
            p,m=profile(),manifest()
            if kind=='old_arena':p['engine']['max_prefill_tokens']=8192
            if kind=='native_context2048':m['environment']['HALOGEN_CTX']='2048'
            if kind=='profile_context2048':p['engine']['context']=2048
            if kind=='explicit_slots':p['engine']['slots']=1
            if kind=='external':m['environment']['HALOGEN_EXTERNAL_STREAM']='0'
            if kind=='wrong_mode':m['environment']['HALOGEN_DN_Z_STREAM']='1'
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                self.m.validate_profile_native(p,m,0)

    def test_complete_record_requires_v3_and_paired2048(self):
        value=dict(schema=RECORD, terminal=True, completed=True, restored=True,
            phase='complete_normal_online',ended_utc='fake',NPU_helper=False,
            capacity_context=8192,paired_prefill_arena=2048,actual_input_tokens=2048,
            output_tokens=128,warmups_excluded=1,measured_per_arm=3)
        self.m.require_complete(value)
        for field,wrong in (('schema','old'),('paired_prefill_arena',8192),('actual_input_tokens',8192)):
            bad=dict(value);bad[field]=wrong
            with self.assertRaises(ValueError):self.m.require_complete(bad)

    def test_partial_even_restored_never_emits_rates(self):
        with tempfile.TemporaryDirectory() as temporary:
            handle=Path(temporary)/'handle.json'
            handle.write_text(json.dumps(dict(terminal=True,completed=False,restored=True,
                phase='complete_normal_online',error=dict(message='22-GiB reserve unavailable'))))
            result=self.m.audit_terminal(handle,confirmed=True)
            self.assertFalse(result['rates_verified']);self.assertFalse(result['headline_qualified'])
            self.assertEqual(result['arms'],{})
            self.assertNotIn('comparison',result);self.assertNotIn('samples',result)

    def test_twelve_requests_and_reported_stock_bookend_drift(self):
        def rows(speed):
            scoped=dict(head=dict(accepted=12,drafted=20),lookup=dict(accepted=0,drafted=0),grammar=dict(accepted=0,drafted=0))
            return [dict(ordinal=i,phase='warmup_excluded' if i==0 else 'measured',
                RAW_prefill_tok_s=(99999 if i==0 else speed),RAW_decode_tok_s=speed/2,
                RAW_prefill_tok_s_lower=speed-.1,RAW_prefill_tok_s_upper=speed+.1,
                RAW_decode_tok_s_lower=speed/2-.1,RAW_decode_tok_s_upper=speed/2+.1,
                HTTP_seconds=10/speed,scoped=scoped) for i in range(4)]
        cohorts=dict(before=rows(10),candidate=rows(15),after=rows(20))
        result=self.m.summarize_complete_arms(cohorts)
        self.assertEqual(result['arms']['before']['RAW_prefill_tok_s']['mean'],10)
        self.assertEqual(result['comparison']['RAW_prefill_tok_s']['stock_after_vs_before_percent'],100)
        self.assertEqual(result['comparison']['RAW_prefill_tok_s']['candidate_vs_stock_percent'],0)
        for bad in (dict(before=rows(10),after=rows(20)),dict(cohorts,candidate=rows(15)[:3])):
            with self.assertRaises(ValueError):self.m.summarize_complete_arms(bad)

    def test_saved_normal_restore_margin_retains_real_frames_and_unchanged_floor(self):
        frame=dict(available_bytes=31*2**30,commit_headroom_bytes=132*2**30)
        value=dict(schema='halogen0203.DNZ-arena2048-normal-restore-margin.v3',
            required_physical_gib=30.25,required_commit_gib=131,
            runtime_physical_commit_gib=18,service_startup_physical_commit_gib=[30,131],
            stable_seconds_required=10,maximum_seconds=300,started_monotonic=0,
            finished_monotonic=15,stable_started_monotonic=5,stable_seconds_observed=10,
            observed_samples=2,stable_frames=[dict(observed_monotonic=t,frame=copy.deepcopy(frame)) for t in (5,15)],
            minimum_physical_gib=31,minimum_commit_gib=132,passing_check_file_writes=0,new_launch_attempts_performed=0)
        self.m.validate_restore_margin(value)
        for kind in ('short','old_floor','bad_frame','runtime','relaunch'):
            bad=copy.deepcopy(value)
            if kind=='short':bad['stable_seconds_observed']=9
            if kind=='old_floor':bad['service_startup_physical_commit_gib']=[29,131]
            if kind=='bad_frame':bad['stable_frames'][0]['frame']['available_bytes']=30*2**30
            if kind=='runtime':bad['minimum_physical_gib']=17.9
            if kind=='relaunch':bad['new_launch_attempts_performed']=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.m.validate_restore_margin(bad)

    def test_restore_margin_rejects_after300_but_accepts_exact_deadline(self):
        frame=dict(available_bytes=31*2**30,commit_headroom_bytes=132*2**30)
        def value(finish):
            return dict(schema='halogen0203.DNZ-arena2048-normal-restore-margin.v3',
                required_physical_gib=30.25,required_commit_gib=131,
                runtime_physical_commit_gib=18,service_startup_physical_commit_gib=[30,131],
                stable_seconds_required=10,maximum_seconds=300,started_monotonic=0,
                finished_monotonic=finish,stable_started_monotonic=finish-10,stable_seconds_observed=10,
                observed_samples=2,stable_frames=[dict(observed_monotonic=t,frame=copy.deepcopy(frame)) for t in (finish-10,finish)],
                minimum_physical_gib=31,minimum_commit_gib=132,passing_check_file_writes=0,new_launch_attempts_performed=0)
        self.m.validate_restore_margin(value(300))
        with self.assertRaises(ValueError):self.m.validate_restore_margin(value(301))


if __name__=='__main__':unittest.main()

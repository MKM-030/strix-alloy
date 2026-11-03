"""Portable CPU capacity regressions using tracked sources and static expected fixtures."""
import asyncio
import contextlib
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'backends/halogen-wsl2-0.18.22/scripts'
sys.path.insert(0, str(REPO / 'server'))
import controller
import manage
from gateway import Backend, Gateway

FIXTURES=Path(__file__).resolve().parent/'fixtures'


@contextlib.contextmanager
def isolated_backend():
    """Keep backend imports and lazy imports from contaminating legacy tests."""
    names={path.stem for path in SCRIPTS.glob('*.py')}
    saved={name:sys.modules.pop(name) for name in names if name in sys.modules}
    previous_path=sys.path[:]
    sys.path.insert(0,str(SCRIPTS))
    try:
        yield (importlib.import_module('service'),importlib.import_module('capacity_policy'),
               importlib.import_module('memory_budget'))
    finally:
        sys.path[:]=previous_path
        for name in names:sys.modules.pop(name,None)
        sys.modules.update(saved)


def normalize_paths(value, repo):
    if isinstance(value,dict):return {key:normalize_paths(item,repo) for key,item in value.items()}
    if isinstance(value,list):return [normalize_paths(item,repo) for item in value]
    if isinstance(value,str) and value.startswith(str(repo)):
        return '<REPO>/'+Path(value).relative_to(repo).as_posix()
    return value




class CapacityTests(unittest.TestCase):
    def setUp(self):
        context=isolated_backend()
        self.service,self.capacity,self.memory_budget=context.__enter__()
        self.addCleanup(context.__exit__,None,None,None)

    def engine(self, slots=2, pool=32768):
        return dict(kind='halogen', directory='backends/halogen-wsl2-0.18.22',
            checkpoint='v2', context=32768, prompt_cache='Off', launcher='python',
            python_executable=sys.executable, powershell='powershell.exe',
            prefill_chunk=8192, max_prefill_tokens=8192, disable_vision=True,
            slots=slots, kv_pool_positions=pool)

    def profile(self, slots=2, pool=32768, concurrency=2):
        return dict(minimum_reserve_gib=18, concurrency=concurrency,
            engine=self.engine(slots, pool), backend=dict(checkpoint='v2', context=32768,
            expected={'context':32768, 'slot_ctx':32768,
                      'kv_pool_positions':pool, 'slots':slots, 'vision.enabled':False, 'capability_probe':'ok'}))

    def options(self, slots=2, pool=32768):
        return self.service.options(['--context-size','32768','--disable-vision',
            '--slots',str(slots),'--kv-pool-positions',str(pool),
            '--prefill-chunk','8192','--max-prefill-tokens','8192'])

    def launch_admission(self, profile):
        controller.validate_halogen_capacity_profile(profile,REPO)
        engine=profile['engine']
        command=controller.halogen_launch_command(engine,controller.validate_engine(engine,REPO))
        options=self.service.options(command[4:])
        floors=self.service.floors(options.context_size,options.checkpoint,options.disable_vision,
                                  **self.service.capacity_options(options))
        return options,floors

    def test_concurrency2_requires_complete_engine_capacity_before_launch_admission(self):
        for fields in ({},{'slots':1},{'kv_pool_positions':32768}):
            profile=json.loads((FIXTURES/'halogen01822-capacity-text32k-profile.json').read_text())
            profile['concurrency']=2
            profile['backend']['expected']['capability_probe']='ok'
            profile['engine']['python_executable']=sys.executable
            profile['engine'].update(fields)
            with self.subTest(fields=fields),self.assertRaisesRegex(
                    ValueError,'concurrency 2 requires explicit slots and kv_pool_positions'):
                self.launch_admission(profile)

    def test_launch_admission_keeps_singleton_and_explicit_queued_control_floors(self):
        profile=json.loads((FIXTURES/'halogen01822-capacity-text32k-profile.json').read_text())
        profile['engine']['python_executable']=sys.executable
        options,floors=self.launch_admission(profile)
        self.assertFalse(self.service.explicit_capacity(options))
        self.assertEqual(floors,(30,124))
        profile['concurrency']=2
        profile['engine'].update(slots=1,kv_pool_positions=32768)
        profile['backend']['expected']['capability_probe']='ok'
        options,floors=self.launch_admission(profile)
        self.assertTrue(self.service.explicit_capacity(options))
        self.assertEqual((options.slots,options.kv_pool_positions),(1,32768))
        self.assertEqual(floors,(30,131))

    def test_default_capacity_is_unchanged_at_all_existing_contexts(self):
        for context in (4096,4097,32768,262144):
            for checkpoint in ('v2','w4b'):
                self.assertEqual(self.capacity.resolve(context,checkpoint),
                                 dict(context=context, slots=1, kv_pool_positions=context))

    def test_bounded_opt_in_and_position_accounting(self):
        for slots in (1,2):
            for pool in (32768,65536):
                actual=self.capacity.resolve(32768,'v2',slots=slots,kv_pool_positions=pool,disable_vision=True)
                self.assertEqual(actual,dict(context=32768,slots=slots,kv_pool_positions=pool))
        self.assertLessEqual(2*(8192+128),32768)
        self.assertGreater(2*(16384+128),32768)
        self.assertLessEqual(2*(16384+128),65536)

    def test_rejects_unbounded_types_pools_and_wrong_scope(self):
        for kwargs in ({'slots':True},{'slots':0},{'slots':3},{'slots':'2'},
                       {'kv_pool_positions':True},{'kv_pool_positions':'65536'},
                       {'kv_pool_positions':33024},{'kv_pool_positions':65535},
                       {'kv_pool_positions':131072}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.capacity.resolve(32768,'v2',disable_vision=True,**kwargs)
        for context,checkpoint,vision in ((262144,'v2',True),(32768,'w4b',True),(32768,'v2',False)):
            with self.subTest(context=context,checkpoint=checkpoint,vision=vision), self.assertRaises(ValueError):
                self.capacity.resolve(context,checkpoint,slots=2,disable_vision=vision)

    def test_normal_controller_forwards_exact_slots_and_pool(self):
        for slots in (1,2):
            for pool in (32768,65536):
                engine=self.engine(slots,pool)
                directory=controller.validate_engine(engine,REPO)
                argv=controller.halogen_launch_command(engine,directory)
                self.assertEqual(argv[argv.index('--slots')+1],str(slots))
                self.assertEqual(argv[argv.index('--kv-pool-positions')+1],str(pool))
                self.assertIn('--disable-vision',argv)
        engine=self.engine(); del engine['slots']; del engine['kv_pool_positions']
        argv=controller.halogen_launch_command(engine,controller.validate_engine(engine,REPO))
        self.assertNotIn('--slots',argv); self.assertNotIn('--kv-pool-positions',argv)
        engine=self.engine(1);del engine['kv_pool_positions'];engine['disable_vision']=False
        with self.assertRaisesRegex(ValueError,'text-only'):
            controller.validate_engine(engine,REPO)

    def test_gateway2_engine1_is_fair_control_but_unsafe_profiles_fail(self):
        for slots in (1,2):
            controller.validate_halogen_capacity_profile(self.profile(slots),REPO)
        for changes in ({'concurrency':1},{'concurrency':True},{'concurrency':3},
                        {'minimum_reserve_gib':12}):
            value=self.profile(); value.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                controller.validate_halogen_capacity_profile(value,REPO)
        for key,value in (('slots',1),('kv_pool_positions',65536),('vision.enabled',True)):
            profile=self.profile(); profile['backend']['expected'][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                controller.validate_halogen_capacity_profile(profile,REPO)
        for key,value in (('checkpoint','w4b'),('directory','backends/halogen-wsl2-0.18.16'),
                          ('disable_vision',False),('slots',3)):
            engine=self.engine(); engine[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                controller.validate_engine(engine,REPO)

    def test_explicit_capacity_rejects_nulls_cache_changes_and_powershell_launcher(self):
        for changes in ({'slots':None}, {'kv_pool_positions':None},
                        {'prompt_cache':'Flexible'}, {'prompt_cache':'Exact'},
                        {'launcher':'powershell'}):
            engine=self.engine();engine.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                controller.validate_engine(engine,REPO)

    def test_default_commands_preserve_both_launcher_types_without_capacity_flags(self):
        engine=self.engine();del engine['slots'];del engine['kv_pool_positions']
        for launcher in ('python','powershell'):
            engine['launcher']=launcher
            # Existing vision-disable control is supported only by Python.
            if launcher=='powershell':del engine['disable_vision']
            command=controller.halogen_launch_command(engine,controller.validate_engine(engine,REPO))
            self.assertNotIn('--slots',command);self.assertNotIn('--kv-pool-positions',command)
            self.assertNotIn('-Slots',command);self.assertNotIn('-KvPoolPositions',command)
            if launcher=='python':self.assertIn('--disable-vision',command)
            else:self.assertEqual(command[:3],['powershell.exe','-NoProfile','-File'])

    def test_other_backend_and_legacy_default_capacity_validation_stays_unchanged(self):
        controller.validate_halogen_capacity_profile({'engine':{'kind':'native'},'concurrency':4},REPO)
        controller.validate_halogen_capacity_profile({'engine':{'kind':'halogen',
            'directory':'backends/halogen-wsl2-0.16.2'},'concurrency':1},REPO)
        controller.validate_halogen_capacity_profile({'engine':{'kind':'halogen',
            'directory':'backends/halogen-wsl2-0.16.2'},'concurrency':2},REPO)
        with self.assertRaises(ValueError):
            controller.validate_halogen_capacity_profile({'engine':{'kind':'native','slots':2},
                'concurrency':2},REPO)

    def test_generator_rejects_wrong_scope_types_and_cache_before_installation(self):
        cases=[('GUFO','v2',32768,'Off','0.16.2',{'concurrency':2}),
               ('Halogen','v2',32768,'Off','0.18.16',{'concurrency':2}),
               ('Halogen','w4b',32768,'Off','0.18.22',{'concurrency':2}),
               ('Halogen','v2',262144,'Off','0.18.22',{'concurrency':2}),
               ('Halogen','v2',32768,'Flexible','0.18.22',{'concurrency':2}),
               ('Halogen','v2',32768,'Off','0.18.22',{'slots':True}),
               ('Halogen','v2',32768,'Off','0.18.22',{'concurrency':True})]
        for backend,checkpoint,context,cache,version,kwargs in cases:
            with self.subTest(case=(backend,checkpoint,context,cache,version,kwargs)), \
                    patch.object(manage,'REPO',Path('/synthetic-missing-repo')), \
                    self.assertRaisesRegex(ValueError,'[Cc]apacity|[Ss]lots|[Cc]ache'):
                manage.make_profile(backend,checkpoint,context,cache,version,**kwargs)

    def test_real_service_environment_manifest_and_health_agree(self):
        for slots in (1,2):
            for pool in (32768,65536):
                options=self.options(slots,pool)
                with tempfile.TemporaryDirectory() as folder, \
                        patch.object(self.service.r,'manifest_for',return_value={'stage':'serve','artifacts':{'bridge':{'path':'C:/fixture/bridge.so','container_path':'/candidate/bridge.so'},'private':{'path':'C:/fixture/private.so','container_path':'/candidate/private.so'}}}), \
                        patch.object(self.service.r,'MACHINE',{'ngram_source':'fixture.hgn'}), \
                        patch.object(self.service.r,'FIXED_MOUNTS',{}):
                    attempt=Path(folder); (attempt/'entrypoint-service.sh').write_bytes(b'fixture')
                    manifest=self.service.build_manifest(options,attempt,'a'*32)
                self.assertEqual(manifest['slots'],slots)
                self.assertEqual(manifest['kv_pool_positions'],pool)
                self.assertEqual(manifest['environment']['HALOGEN_CTX'],'32768')
                self.assertEqual(manifest['environment']['HALOGEN_KV_SLOTS'],str(slots))
                self.assertEqual(manifest['environment']['HALOGEN_KV_POOL_POSITIONS'],str(pool))
                self.assertEqual(manifest['environment']['HALOGEN_HOST_RESERVE_GIB'],'18')
                self.assertNotIn('HALOGEN_PHASE_RAW',manifest['environment'])
                self.service.reject_unqualified_manifest_overrides(manifest)
                for field in ('HALOGEN_KV_SLOTS','HALOGEN_KV_POOL_POSITIONS','HALOGEN_CTX'):
                    altered=deepcopy(manifest); altered['environment'][field]='unbounded'
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        self.service.reject_unqualified_manifest_overrides(altered)
                for field,bad in (('slots',True),('slots',3),('kv_pool_positions',33024)):
                    altered=deepcopy(manifest);altered[field]=bad
                    with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):
                        self.service.reject_unqualified_manifest_overrides(altered)
                h=dict(status='ok',version=dict(api='0.18.22',engine='0.18.22',match=True),
                    context=32768,slot_ctx=32768,kv_pool_positions=pool,slots=slots,
                    vision=dict(enabled=False),capability_probe='ok')
                self.service.validate_health(h,32768,disable_vision=True,slots=slots,kv_pool_positions=pool)
                for key,bad in (('slots',3),('slots',True),('kv_pool_positions',12345),
                                ('kv_pool_positions',65536 if pool==32768 else 32768),
                                ('capability_probe','failed')):
                    wrong=deepcopy(h); wrong[key]=bad
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        self.service.validate_health(wrong,32768,disable_vision=True,slots=slots,kv_pool_positions=pool)

    def test_default_service_env_and_manifest_preserve_normal_semantics(self):
        expected=json.loads((FIXTURES/'halogen01822-capacity-default-environment.json').read_text())
        with patch.object(self.service.r,'MACHINE',{'ngram_source':'synthetic-fixture.hgn'}):
            actual=self.service.environment(32768,'v2','Off',prefill_chunk=8192,max_prefill_tokens=8192,
                kernel_controls={'HALOGEN_DECODE_PREFETCH':0},
                speculation_policy={'HALOGEN_PLD':'3,3','HALOGEN_MTP_GATE_P':'0.90'},
                api_defaults={'enable_thinking':False,'reasoning_effort':'low','max_thinking_tokens':2048},disable_vision=True)
        self.assertEqual(actual,expected)
        options=self.service.options(['--context-size','32768','--disable-vision'])
        with tempfile.TemporaryDirectory() as folder, patch.object(self.service.r,'FIXED_MOUNTS',{}), \
                patch.object(self.service.r,'MACHINE',{'ngram_source':'synthetic-fixture.hgn'}):
            attempt=Path(folder);(attempt/'entrypoint-service.sh').write_bytes(b'fixture')
            manifest=self.service.build_manifest(options,attempt,'a'*32)
        self.assertEqual(manifest['context'],32768);self.assertEqual(manifest['slots'],1)
        self.assertNotIn('kv_pool_positions',manifest)
        self.assertEqual(manifest['environment']['HALOGEN_KV_POOL_POSITIONS'],'32768')
        self.assertEqual(manifest['environment']['HALOGEN_KV_SLOTS'],'1')
        self.assertNotIn('HALOGEN_PHASE_RAW',manifest['environment'])
        self.service.reject_unqualified_manifest_overrides(manifest)

    def test_default_admission_unchanged_opt_in_never_below_30_131(self):
        expected_commits={4096:123,4097:123,32768:124,262144:131}
        for context,commit in expected_commits.items():
            self.assertEqual(self.memory_budget.admission_floors(context,'v2'),(30,commit))
            self.assertEqual(self.memory_budget.admission_floors(context,'w4b'),(52,commit))
        for slots in (1,2):
            for pool in (32768,65536):
                physical,commit=self.service.floors(32768,disable_vision=True,slots=slots,kv_pool_positions=pool)
                self.assertGreaterEqual(physical,30);self.assertGreaterEqual(commit,131)
                frame=dict(available_bytes=physical*2**30,commit_headroom_bytes=commit*2**30)
                self.service.check_admission(frame,32768,disable_vision=True,slots=slots,kv_pool_positions=pool)
                for field in ('available_bytes','commit_headroom_bytes'):
                    bad=dict(frame);bad[field]-=1
                    with self.subTest(slots=slots,pool=pool,field=field),self.assertRaises(ValueError):
                        self.service.check_admission(bad,32768,disable_vision=True,slots=slots,kv_pool_positions=pool)

    def test_manage_generation_default_parity_and_explicit_capacity(self):
        expected=json.loads((FIXTURES/'halogen01822-capacity-default-profile.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            repo=Path(folder);package=repo/'backends/halogen-wsl2-0.18.22'
            (package/'.local').mkdir(parents=True);(package/'profiles').mkdir();(package/'scripts').mkdir()
            (package/'scripts/capacity_policy.py').write_bytes((SCRIPTS/'capacity_policy.py').read_bytes())
            (package/'profiles/release.json').write_text(json.dumps(dict(version='0.18.22',image='synthetic-image')))
            (package/'.local/machine.json').write_text(json.dumps(dict(version='0.18.22',image='synthetic-image',pwsh='<POWERSHELL>')))
            (package/'.local/api-token.txt').write_text('synthetic-fixture-token')
            with patch.object(manage,'REPO',repo),patch.object(controller,'ROOT',repo/'server'):
                default=manage.make_profile('Halogen','v2',32768,'Off','0.18.22')
                self.assertEqual(normalize_paths(default,repo),expected)
                for slots in (1,2):
                    value=manage.make_profile('Halogen','v2',32768,'Off','0.18.22',slots=slots,kv_pool_positions=65536,concurrency=2)
                    self.assertEqual(value['concurrency'],2)
                    self.assertEqual(value['engine']['slots'],slots)
                    self.assertEqual(value['engine']['kv_pool_positions'],65536)
                    self.assertEqual(value['backend']['expected']['slots'],slots)
                    self.assertEqual(value['backend']['expected']['kv_pool_positions'],65536)
                    self.assertEqual(value['backend']['expected']['capability_probe'],'ok')
                    self.assertIs(value['engine']['disable_vision'],True)
                    controller.validate_halogen_capacity_profile(value,repo)
                with self.assertRaises(ValueError):
                    manage.make_profile('Halogen','v2',32768,'Off','0.18.22',slots=2,concurrency=1)

    def test_cli_opt_in_uses_distinct_profiles_and_cannot_overwrite_singleton(self):
        paths=[]
        with tempfile.TemporaryDirectory() as folder,patch.object(manage,'ROOT',Path(folder)/'server'), \
                patch.object(manage,'atomic',side_effect=lambda path,value:paths.append(path)), \
                patch.object(manage.subprocess,'call',return_value=0) as process:
            for slots in (1,2):
                value=self.profile(slots,65536)
                with patch.object(sys,'argv',['manage.py','start','--context','32768',
                    '--halogen-version','0.18.22','--slots',str(slots),'--kv-pool-positions','65536','--concurrency','2']), \
                        patch.object(manage,'make_profile',return_value=value) as make:
                    self.assertEqual(manage.main(),0)
                    make.assert_called_once_with('Halogen','v2',32768,'Off','0.18.22',
                        slots=slots,kv_pool_positions=65536,concurrency=2)
            self.assertEqual(process.call_count,2)
        self.assertEqual(len(set(paths)),2)
        self.assertTrue(all(path.name!='halogen-0.18.22-v2-32768-Off.json' for path in paths))


class GatewayCapacityTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_admitted_callers_and_third_refusal_are_not_unfair_control(self):
        backend=Backend('halogen-v2','http://127.0.0.1:8731','halogen-model')
        one=Gateway(backend,'fixture-secret-at-least-32-characters',concurrency=1)
        self.assertTrue(await one.acquire_slot());self.assertFalse(await one.acquire_slot());one.release_slot()
        two=Gateway(backend,'fixture-secret-at-least-32-characters',concurrency=2)
        self.assertTrue(await two.acquire_slot());self.assertTrue(await two.acquire_slot())
        self.assertEqual(two.active,2);self.assertFalse(await two.acquire_slot())
        two.release_slot();self.assertTrue(await two.acquire_slot())
        two.release_slot();two.release_slot();self.assertEqual(two.active,0)


if __name__=='__main__':unittest.main()

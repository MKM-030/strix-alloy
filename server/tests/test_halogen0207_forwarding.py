"""Managed 0.20.7 preserves version binding and capacity admission."""
import os

try:
    from . import test_halogen0202_forwarding as baseline
except ImportError:
    import test_halogen0202_forwarding as baseline


class Halogen0207Forwarding(baseline.Halogen0202Forwarding):
    version = '0.20.7'


class Halogen0207CommandForwarding(baseline.unittest.TestCase):
    def test_persistent_prompt_cache_is_a_direct_python_opt_in(self):
        with baseline.tempfile.TemporaryDirectory() as td:
            repo = baseline.Path(td)
            package = repo / 'backends/halogen-wsl2-0.20.7'
            (package / 'scripts').mkdir(parents=True)
            source = baseline.REPO / 'backends/halogen-wsl2-0.20.7'
            baseline.shutil.copyfile(source / 'Start.ps1', package / 'Start.ps1')
            service = package / 'scripts/service.py'
            service.write_text('# --disable-vision --persist-prompt-cache\n', encoding='utf-8')
            engine = dict(kind='halogen', directory='backends/halogen-wsl2-0.20.7',
                          checkpoint='v2', context=32768, prompt_cache='Flexible',
                          launcher='python', python_executable=baseline.sys.executable,
                          prefill_chunk=8192, max_prefill_tokens=8192, disable_vision=True)
            with baseline.patch.object(baseline.controller, 'ROOT', repo / 'server'):
                baseline.controller.validate_engine(engine, repo)
                command = baseline.controller.halogen_launch_command(engine, package)
                opted_in = dict(engine, persist_prompt_cache=True)
                baseline.controller.validate_engine(opted_in, repo)
                self.assertEqual(baseline.controller.halogen_launch_command(opted_in, package),
                                 command + ['--persist-prompt-cache'])
                opted_out = dict(engine, persist_prompt_cache=False)
                baseline.controller.validate_engine(opted_out, repo)
                self.assertEqual(baseline.controller.halogen_launch_command(opted_out, package), command)
                for changes in (dict(persist_prompt_cache=1), dict(persist_prompt_cache='false'),
                                dict(checkpoint='w4b'), dict(context=65536), dict(prompt_cache='Off'),
                                dict(prompt_cache='Exact'), dict(disable_vision=False),
                                dict(prefill_chunk=2048), dict(max_prefill_tokens=16384),
                                dict(slots=1), dict(kv_pool_positions=32768), dict(launcher='powershell')):
                    with self.subTest(changes=changes), self.assertRaises(ValueError):
                        baseline.controller.validate_engine(dict(opted_in, **changes), repo)
                with self.assertRaisesRegex(ValueError, '0.20.7'):
                    baseline.controller.halogen_launch_command(
                        opted_in, repo / 'backends/halogen-wsl2-0.20.6')
                service.write_text('# --disable-vision\n', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'persistent prompt cache'):
                    baseline.controller.validate_engine(opted_in, repo)

    @baseline.unittest.skipUnless(os.name == 'nt', 'Managed lookup receipt needs a Windows drive path')
    def test_native_lookup_reaches_the_current_python_service(self):
        repo = baseline.REPO
        receipt = repo / ('server/.local/optimization9h-20261004/'
                          'lookup-native-copy-9447b9641f964497980fcb281b18a5c3/'
                          'extraction.receipt.json')
        digest = 'df0dc1e5d2de921b58c4f18f988624687191ec6f80e2336c90c7de454144c7fb'
        engine = dict(kind='halogen', directory='backends/halogen-wsl2-0.20.7',
                      checkpoint='v2', context=32768, prompt_cache='Off',
                      launcher='python', python_executable=baseline.sys.executable)
        for opts in (engine, dict(engine, lookup_tuning=dict(receipt=str(receipt),
                                                          receipt_sha256=digest))):
            directory = baseline.controller.validate_engine(opts, repo)
            argv = baseline.controller.halogen_launch_command(opts, directory)
            if 'lookup_tuning' in opts:
                self.assertEqual(argv[argv.index('--lookup-receipt') + 1], str(receipt.resolve()))
                self.assertEqual(argv[argv.index('--lookup-receipt-sha256') + 1], digest)
            else:
                self.assertNotIn('--lookup-receipt', argv)
                self.assertNotIn('--lookup-receipt-sha256', argv)

    def test_current_controls_reach_service_and_reject_invalid_capacity(self):
        with baseline.tempfile.TemporaryDirectory() as td:
            repo = baseline.Path(td)
            package = repo / 'backends/halogen-wsl2-0.20.7'
            (package / 'scripts').mkdir(parents=True)
            source = baseline.REPO / 'backends/halogen-wsl2-0.20.7'
            for name in ('Start.ps1', 'scripts/service.py', 'scripts/kernel_controls.py',
                         'scripts/speculation_policy.py', 'scripts/api_defaults.py',
                         'scripts/capacity_policy.py'):
                baseline.shutil.copyfile(source / name, package / name)
            engine = dict(kind='halogen', directory='backends/halogen-wsl2-0.20.7',
                checkpoint='v2', context=32768, prompt_cache='Off', launcher='python',
                python_executable=baseline.sys.executable, powershell='powershell.exe',
                prefill_chunk=8192, max_prefill_tokens=8192, disable_vision=True,
                kernel_controls={'HALOGEN_DECODE_PREFETCH': 0},
                speculation_policy={'HALOGEN_PLD': '3,3', 'HALOGEN_MTP_GATE_P': '0.90'},
                api_defaults={'enable_thinking': False, 'reasoning_effort': 'low',
                              'max_thinking_tokens': 2048})
            with baseline.patch.object(baseline.controller, '__file__', str(repo / 'server/controller.py')), \
                    baseline.patch.object(baseline.controller, 'ROOT', repo / 'server'):
                for capacity in ({}, dict(slots=1, kv_pool_positions=32768),
                                 dict(slots=2, kv_pool_positions=65536)):
                    with self.subTest(capacity=capacity):
                        configured = dict(engine, **capacity)
                        directory = baseline.controller.validate_engine(configured, repo)
                        argv = baseline.controller.halogen_launch_command(configured, directory)
                        self.assertEqual(baseline.Path(argv[3]), package / 'scripts/service.py')
                        self.assertIn('--disable-vision', argv)
                        for flag, value in (('--prefill-chunk', '8192'),
                                            ('--max-prefill-tokens', '8192'),
                                            ('--prompt-cache', 'Off')):
                            self.assertEqual(argv[argv.index(flag) + 1], value)
                        for key, flag in (('kernel_controls', '--kernel-controls-json'),
                                          ('speculation_policy', '--speculation-policy-json'),
                                          ('api_defaults', '--api-defaults-json')):
                            self.assertEqual(baseline.json.loads(argv[argv.index(flag) + 1]), engine[key])
                        self.assertNotIn('--draft-tokens', argv)
                        if capacity:
                            self.assertEqual(argv[argv.index('--slots') + 1], str(capacity['slots']))
                            self.assertEqual(argv[argv.index('--kv-pool-positions') + 1], str(capacity['kv_pool_positions']))
                        else:
                            self.assertNotIn('--slots', argv)
                for changes in (dict(prefill_chunk=8192, max_prefill_tokens=2048),
                                dict(slots=2, kv_pool_positions=65536, disable_vision=False)):
                    with self.subTest(changes=changes), self.assertRaises(ValueError):
                        baseline.controller.validate_engine(dict(engine, **changes), repo)

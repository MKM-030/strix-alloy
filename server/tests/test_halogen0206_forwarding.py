"""Managed 0.20.6 preserves version binding and capacity admission."""
try:
    from . import test_halogen0202_forwarding as baseline
except ImportError:
    import test_halogen0202_forwarding as baseline


class Halogen0206Forwarding(baseline.Halogen0202Forwarding):
    version = '0.20.6'


class Halogen0206CommandForwarding(baseline.unittest.TestCase):
    def test_current_controls_reach_service_and_reject_invalid_capacity(self):
        with baseline.tempfile.TemporaryDirectory() as td:
            repo = baseline.Path(td)
            package = repo / 'backends/halogen-wsl2-0.20.6'
            (package / 'scripts').mkdir(parents=True)
            source = baseline.REPO / 'backends/halogen-wsl2-0.20.6'
            for name in ('Start.ps1', 'scripts/service.py', 'scripts/kernel_controls.py',
                         'scripts/speculation_policy.py', 'scripts/api_defaults.py',
                         'scripts/capacity_policy.py'):
                baseline.shutil.copyfile(source / name, package / name)
            engine = dict(kind='halogen', directory='backends/halogen-wsl2-0.20.6',
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

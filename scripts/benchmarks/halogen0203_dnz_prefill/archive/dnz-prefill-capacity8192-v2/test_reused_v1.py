"""Finite CPU fakes only. No provider, process, network or live API is loaded."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent


def load(test, name):
    path = HERE / (name + '.py')
    test.assertTrue(path.exists(), name + ' is not implemented')
    spec = importlib.util.spec_from_file_location('dnz_test_' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CounterTests(unittest.TestCase):
    def setUp(self):
        self.m = load(self, 'counter_reader')
        self.maps = ('10000000-10001000 r--p 00000000 00:25 100 /halogen/flash_serve\n'
                     '10003000-10004000 r-xp 00002000 00:25 100 /halogen/flash_serve\n'
                     '121ca000-121cb000 rw-p 00000000 00:00 0\n')

    def test_offsetzero_identity_base_finds_anonymous_BSS_not_RX_bias(self):
        result = self.m.locate_counter(self.maps, 0, 0x25, 100)
        self.assertEqual(result['load_base'], 0x10000000)
        self.assertEqual(result['counter_address'], 0x121ca518)
        self.assertEqual(result['counter_region']['inode'], 0)

    def test_mapping_ambiguity_unreadable_or_wrong_identity_is_rejected(self):
        for maps, inode in [(self.maps + self.maps.splitlines()[0] + '\n', 100),
                            (self.maps.replace('rw-p', '-w-p'), 100), (self.maps, 99)]:
            with self.subTest(inode=inode), self.assertRaises(ValueError):
                self.m.locate_counter(maps, 0, 0x25, inode)

    def test_counter_delta_rejects_reset_changed_owner_and_zero_candidate(self):
        before = dict(identity={'pid': 7, 'starttime_ticks': 55},
                      container_id='owned', counter_address='0x1234', counter_value=4)
        after = dict(before, counter_value=7)
        self.assertEqual(self.m.qualify_delta(before, after, 1), 3)
        self.assertEqual(self.m.qualify_delta(before, before, 0), 0)
        for bad, mode in [(dict(after, counter_value=3), 1),
                          (dict(after, identity={'pid': 7, 'starttime_ticks': 56}), 1),
                          (dict(after, container_id='foreign'), 1),
                          (before, 1), (after, 0)]:
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.m.qualify_delta(before, bad, mode)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.m = load(self, 'campaign')

    def test_unsealed_or_changed_dependency_cannot_enter_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / 'input.py'
            data.write_text('original')
            pin = self.m.pin(data)
            binding = dict(schema=self.m.SCHEMA, root_sealed=False,
                           dependency_closure_reviewed=True, pins=[pin])
            with self.assertRaises(ValueError):
                self.m.require_execution_seal(binding)
            binding['root_sealed'] = True
            self.m.require_execution_seal(binding)
            data.write_text('foreign')
            with self.assertRaises(ValueError):
                self.m.require_execution_seal(binding)

    def test_counter_reads_bracket_original_timed_post_and_restore_wrapper(self):
        calls = []
        async def post(*args, **kwargs):
            calls.append('timed HTTP')
            return b'answer', 200, {'qpc_start_ns': 3, 'qpc_end_ns': 5}
        collector = types.SimpleNamespace(post_once=post, m=types.SimpleNamespace(
            check_reserve=lambda *args: calls.append('entry22')))
        reader = iter([dict(value=0), dict(value=2)])
        records = []
        def capture():
            calls.append('counter')
            return next(reader)
        host_clock = iter([1, 2, 6, 7])
        with self.m.counter_bracket(collector, object(), capture,
                lambda b, a: 2, records.append, clock_ns=lambda: next(host_clock)):
            value = asyncio.run(collector.post_once())
        self.assertIs(collector.post_once, post)
        self.assertEqual(calls, ['counter', 'entry22', 'timed HTTP', 'counter'])
        self.assertEqual(value[2], {'qpc_start_ns': 3, 'qpc_end_ns': 5})
        self.assertEqual(records[0]['delta'], 2)

    def test_exact_response_parity_rejects_even_same_counts_changed_output(self):
        reference = dict(text='original', finish_reason='length',
                         actual_input_tokens=2048, actual_output_tokens=128)
        self.m.require_parity(reference, dict(reference))
        with self.assertRaises(ValueError):
            self.m.require_parity(reference, dict(reference, text='different'))

    def test_finally_restores_source_then_normal_even_when_measurement_fails(self):
        calls = []
        with self.assertRaisesRegex(RuntimeError, 'measurement failed'):
            with self.m.restoration_guard(lambda: calls.append('restore')):
                calls.append('measure')
                raise RuntimeError('measurement failed')
        self.assertEqual(calls, ['measure', 'restore'])

    def test_restore_does_not_stop_original_online_server_after_preflight_failure(self):
        calls = []
        baseline = {'identities': {'native': 'same'}, 'outer': {'run_id': 'normal'}}
        result = self.m.restore_online(
            active=baseline, baseline=baseline, overlay_attempted=False,
            current={'phase': 'ready', 'run_id': 'normal'},
            stop=lambda *args: calls.append('stop'),
            rollback=lambda: calls.append('rollback'),
            launch=lambda: calls.append('launch'),
            verify=lambda: baseline)
        self.assertIs(result, baseline)
        self.assertEqual(calls, [])

    def test_restore_stops_private_then_rolls_back_before_normal_launch(self):
        calls = []
        result = self.m.restore_online(
            active={'private': True}, baseline={}, overlay_attempted=True,
            current={'phase': 'ready', 'run_id': 'private'},
            stop=lambda *args: calls.append('stop private'),
            rollback=lambda: calls.append('rollback'),
            launch=lambda: calls.append('launch normal') or {'ready': True},
            verify=lambda: None)
        self.assertEqual(calls, ['stop private', 'rollback', 'launch normal'])
        self.assertEqual(result, {'ready': True})


if __name__ == '__main__':
    unittest.main()

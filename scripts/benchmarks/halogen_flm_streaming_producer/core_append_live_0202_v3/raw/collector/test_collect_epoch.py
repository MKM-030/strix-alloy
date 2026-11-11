"""Finite mocked runtime and HTTP tests. No real service or hardware calls."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import collect_epoch as collector
from test_validator import fixture, packed
from validate_capture import bound_pcs

REAL_SINGLE_SLOT_ADMISSION = dict(version=1, policy='not_required', ready=None, reason='not_required',
    required_available_bytes=None, required_commit_headroom_bytes=None,
    available_bytes=None, commit_headroom_bytes=None, sample_age_ms=None)


class FakeRuntime:
    def __init__(self, expected):
        self.expected = expected
        self.completed = self.cancelled = 0
        self.reserve = 24
        self.ops = types.SimpleNamespace(
            atomic=self.atomic, host=types.SimpleNamespace(frame=self.frame),
            ident=types.SimpleNamespace(process_identity=self.identity))

    def atomic(self, path, value):
        Path(path).write_text(json.dumps(value), encoding='utf-8')

    def frame(self):
        return dict(available_bytes=self.reserve * 2**30, commit_headroom_bytes=64 * 2**30)

    def identity(self, pid):
        return next(value for value in self.expected['identities'].values() if value['pid'] == pid)

    def verify(self, profile, port, require_idle=True):
        value = copy.deepcopy(self.expected)
        value['gateway'].update(completed=self.completed, cancelled=self.cancelled)
        return value

    def gpu_receipt(self, label):
        return dict(label=label, games=[], gpu=[])


class FakeSession:
    def __init__(self, runtime, raw_dir):
        self.runtime, self.raw_dir = runtime, raw_dir
        self.bodies = []
        self.main_ordinal = 0
        self.generated = 37
        self.status = 200
        self.transport_error = False
        self.wrong_serial = False
        self.foreign_gateway = False
        self.foreign_raw = False
        self.finish_reason = 'stop'
        self.slots = 2
        self.changed_main_after = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, data):
        self.bodies.append(data)
        session = self
        request = json.loads(data)

        class Response:
            status = session.status

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def read(self):
                await asyncio.sleep(0.012)
                if session.transport_error:
                    raise RuntimeError('synthetic transport failure')
                native_id = 70 + len(session.bodies)
                events, response = fixture(session.generated, request_id=native_id,
                    native_slot=session.main_ordinal % session.slots, offset=session.main_ordinal * 10000000,
                    prompt=39)
                text = 'wrong' if session.wrong_serial and request['drafter'] == 'serial' else 'fixture result'
                if (request['drafter'] == 'mtp' and session.changed_main_after is not None
                        and session.main_ordinal >= session.changed_main_after):
                    text = 'changed deterministic output'
                response['choices'] = [dict(text=text, finish_reason=session.finish_reason)]
                response['timings'].update(prompt_per_second=19500.0,
                    predicted_per_second=session.generated / 0.003, draft_n=3, draft_n_accepted=2,
                    speculation=dict(drafter='mtp' if request['drafter'] == 'mtp' else 'none', rounds=2,
                        head=dict(rounds=1, drafted=2, accepted=1),
                        lookup=dict(rounds=1, drafted=1, accepted=1),
                        grammar=dict(rounds=0, drafted=0, accepted=0)))
                if request['drafter'] == 'serial':
                    assert not (session.raw_dir / 'arm').exists()
                else:
                    nonce = int((session.raw_dir / 'arm').read_text(), 16)
                    for event in events:
                        event['caller_rva'] = bound_pcs()[event['site']]
                    data = packed(events, ordinal=session.main_ordinal,
                                  flags=2 if session.foreign_raw else 0, epoch=nonce)
                    if session.generated < 2:
                        data = b''
                    (session.raw_dir / f'capture-{nonce:016x}-{session.main_ordinal}.bin').write_bytes(data)
                    session.main_ordinal += 1
                session.runtime.completed += 2 if session.foreign_gateway else 1
                return json.dumps(response).encode()

        return Response()


class CollectorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw_dir = self.root / 'attempt/raw-phase'
        self.raw_dir.mkdir(parents=True)
        token = self.root / 'token'
        token.write_text('fixture-secret')
        self.profile = self.root / 'profile.json'
        self.profile.write_text(json.dumps(dict(token_file=str(token), concurrency=2,
            engine=dict(slots=2, prompt_cache='Off'))))
        self.expected = dict(identities=dict(controller=dict(pid=101, creation_time_100ns=1),
            backend=dict(pid=102, creation_time_100ns=2)),
            outer=dict(run_id='controller', profile_sha256=collector.m.digest(self.profile.read_bytes())),
            inner=dict(run_id='backend', attempt=str(self.raw_dir.parent)),
            gateway=dict(active_requests=0, queued_requests=0, draining=False,
                request_admission_ready=True, completed=0, cancelled=0),
            native=dict(slots=2, busy=False, in_flight=0, queued=0,
                version=dict(api='0.20.2', engine='0.20.2', match=True)))
        self.runtime = FakeRuntime(self.expected)
        self.session = FakeSession(self.runtime, self.raw_dir)
        self.request = json.dumps(dict(stream=False, temperature=0, drafter='mtp', max_tokens=512)).encode()
        self.serial = json.dumps({**json.loads(self.request), 'drafter': 'serial'}).encode()
        self.patch = patch.object(collector, 'session_for_token', return_value=self.session)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.qpc_tick = 0
        self.qpc_patch = patch.object(collector.time, 'perf_counter_ns', side_effect=self.next_qpc)
        self.qpc_patch.start()
        self.addCleanup(self.qpc_patch.stop)

    def next_qpc(self):
        # Synthetic RAW fixtures require synthetic, monotonic HTTP intervals.
        self.qpc_tick += 20000000
        return self.qpc_tick

    async def run_epoch(self, name='result', epoch=1, serial=False, oracle=None,
                        expected_output_tokens=None):
        return await collector.collect_epoch(runtime=self.runtime, profile=self.profile, port=18840,
            expected=self.expected, request_bytes=self.request,
            request_sha256=collector.m.digest(self.request), route='/v1/completions',
            raw_dir=self.raw_dir, epoch=epoch, output=self.root / name,
            oracle_bytes=oracle, expected_prompt_tokens=39,
            expected_output_tokens=expected_output_tokens,
            oracle_request_bytes=self.serial if serial else None,
            oracle_request_sha256=collector.m.digest(self.serial) if serial else None)

    def handle(self, name='result'):
        return json.loads((self.root / name / 'handle.json').read_bytes())

    def assert_disarmed(self):
        self.assertFalse((self.raw_dir / 'arm').exists())
        self.assertFalse((self.raw_dir / 'collector.lock').exists())

    async def test_four_serial_responses_and_raw_qpc_pairing(self):
        result = await self.run_epoch()
        self.assertTrue(result['collector']['completed'])
        self.assertTrue(result['collector']['terminal'])
        self.assertTrue(result['qpc_audit']['valid'])
        self.assertEqual(len(self.session.bodies), 4)
        self.assertEqual(set(self.session.bodies), {self.request})
        self.assertEqual([row['actual_output_tokens'] for row in result['samples']], [37] * 4)
        self.assertEqual([row['output_cap'] for row in result['samples']], [512] * 4)
        self.assertEqual(len(list((self.root / 'result/journals').glob('*.bin'))), 4)
        self.assert_disarmed()

    async def test_expected_output_count_matches_actual_and_preserves_cap(self):
        result = await self.run_epoch(expected_output_tokens=37)
        self.assertEqual(result['collector']['expected_output_tokens'], 37)
        self.assertEqual([row['actual_output_tokens'] for row in result['samples']], [37] * 4)
        self.assertEqual([row['output_cap'] for row in result['samples']], [512] * 4)
        self.assertEqual(len(self.session.bodies), 4)
        self.assert_disarmed()

    async def test_changed_output_hash_preserves_partial_response_and_stops_without_retry(self):
        self.session.changed_main_after = 1
        with self.assertRaisesRegex(ValueError, 'output hash'):
            await self.run_epoch(expected_output_tokens=37)
        self.assertEqual(len(self.session.bodies), 2)
        for ordinal in (0, 1):
            self.assertTrue((self.root / ('result/response-'+str(ordinal)+'.json')).is_file())
            self.assertTrue((self.root / ('result/sample-'+str(ordinal)+'.json')).is_file())
        self.assertFalse(self.handle()['completed'])
        self.assertTrue(self.handle()['terminal'])
        self.assertTrue(self.handle()['restart_required'])
        self.assertEqual(len(list((self.root / 'result/journals').glob('*.bin'))), 2)
        self.assert_disarmed()

    async def test_expected_count_does_not_replace_disagreeing_actual_timing_count(self):
        await self.run_epoch(expected_output_tokens=37)
        response = json.loads((self.root / 'result/response-0.json').read_bytes())
        response['timings']['predicted_n'] = 38
        raw = json.dumps(response).encode()
        with self.assertRaisesRegex(ValueError, 'predicted/actual output counts differ'):
            collector.account_response(raw, json.loads(self.request), expected_output_tokens=37)
        self.assertEqual(response['usage']['completion_tokens'], 37)
        self.assertEqual(response['timings']['predicted_n'], 38)

    async def test_wrong_first_main_output_count_preserves_body_and_stops(self):
        with self.assertRaisesRegex(ValueError, 'expected output count'):
            await self.run_epoch(expected_output_tokens=38)
        self.assertEqual(len(self.session.bodies), 1)
        self.assertTrue((self.root / 'result/response-0.json').is_file())
        response = json.loads((self.root / 'result/response-0.json').read_bytes())
        self.assertEqual(response['usage']['completion_tokens'], 37)
        self.assertTrue(self.handle()['restart_required'])
        self.assert_disarmed()

    async def test_wrong_serial_output_count_preserves_body_and_stops_before_arm(self):
        with self.assertRaisesRegex(ValueError, 'expected output count'):
            await self.run_epoch(serial=True, oracle=b'fixture result', expected_output_tokens=38)
        self.assertEqual(self.session.bodies, [self.serial])
        self.assertTrue((self.root / 'result/serial.response.json').is_file())
        self.assertFalse((self.root / 'result/arm-created.json').exists())
        self.assertFalse(list(self.raw_dir.glob('capture-*.bin')))
        self.assertFalse(self.handle()['restart_required'])
        self.assert_disarmed()

    async def test_invalid_expected_output_count_rejected_before_http(self):
        for index, value in enumerate((True, False, 0, -1, 37.0, '37', 0x100000000)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.run_epoch(name='invalid' + str(index), expected_output_tokens=value)
            with self.assertRaises(ValueError):
                collector.account_response(b'{}', json.loads(self.request), expected_output_tokens=value)
        self.assertFalse(self.session.bodies)
        self.assert_disarmed()

    async def test_one_slot_profile_and_native_slot_zero(self):
        config = json.loads(self.profile.read_bytes())
        config['engine']['slots'] = config['concurrency'] = 1
        self.profile.write_text(json.dumps(config))
        self.expected['outer']['profile_sha256'] = collector.m.digest(self.profile.read_bytes())
        self.expected['native']['slots'] = self.session.slots = 1
        result = await self.run_epoch()
        self.assertTrue(result['collector']['completed'])
        self.assertEqual({row['native_slot'] for row in result['raw_report']['samples']}, {0})
        self.assert_disarmed()

    def single_slot_not_required(self):
        config = json.loads(self.profile.read_bytes())
        config['engine']['slots'] = config['concurrency'] = 1
        self.profile.write_text(json.dumps(config))
        self.expected['outer']['profile_sha256'] = collector.m.digest(self.profile.read_bytes())
        self.expected['native']['slots'] = self.session.slots = 1
        self.expected['gateway'].update(request_admission_ready=None,
            request_admission=copy.deepcopy(REAL_SINGLE_SLOT_ADMISSION))

    async def test_real_single_slot_not_required_admission_runs_four_requests(self):
        self.single_slot_not_required()
        result = await self.run_epoch()
        self.assertTrue(result['collector']['completed'])
        self.assertEqual(len(self.session.bodies), 4)
        self.assertEqual(json.loads((self.root / 'result/ready-before.json').read_bytes())
            ['gateway']['request_admission'], REAL_SINGLE_SLOT_ADMISSION)
        self.assert_disarmed()

    async def test_not_required_is_rejected_for_two_slots_and_readiness_is_saved(self):
        self.expected['gateway'].update(request_admission_ready=None,
            request_admission=copy.deepcopy(REAL_SINGLE_SLOT_ADMISSION))
        with self.assertRaisesRegex(ValueError, 'Gateway is busy'):
            await self.run_epoch()
        saved = json.loads((self.root / 'result/ready-before.json').read_bytes())
        self.assertIsNone(saved['gateway']['request_admission_ready'])
        self.assertEqual(saved['gateway']['request_admission'], REAL_SINGLE_SLOT_ADMISSION)
        self.assertFalse(self.session.bodies)
        self.assert_disarmed()

    async def test_single_slot_not_required_metadata_must_be_exact(self):
        self.single_slot_not_required()
        variants = [dict(REAL_SINGLE_SLOT_ADMISSION, version=True),
                    dict(REAL_SINGLE_SLOT_ADMISSION, ready=False),
                    dict(REAL_SINGLE_SLOT_ADMISSION, extra=None),
                    dict(REAL_SINGLE_SLOT_ADMISSION, policy='halogen_two_slot_memory'),
                    {key: value for key, value in REAL_SINGLE_SLOT_ADMISSION.items() if key != 'reason'},
                    None]
        for index, metadata in enumerate(variants):
            self.expected['gateway']['request_admission'] = metadata
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'Gateway is busy'):
                await self.run_epoch(name='malformed' + str(index))
        self.assertFalse(self.session.bodies)
        self.assert_disarmed()

    async def test_single_slot_false_or_missing_ready_is_rejected(self):
        self.single_slot_not_required()
        self.expected['gateway']['request_admission_ready'] = False
        with self.assertRaises(ValueError):
            await self.run_epoch(name='false')
        del self.expected['gateway']['request_admission_ready']
        with self.assertRaisesRegex(ValueError, 'readiness field missing'):
            await self.run_epoch(name='missing')
        self.assertFalse(self.session.bodies)
        self.assert_disarmed()

    async def test_one_slot_not_required_does_not_bypass_manual_memory_entry_gate(self):
        self.single_slot_not_required()
        self.runtime.reserve = 21
        with self.assertRaisesRegex(ValueError, '22-GiB'):
            await self.run_epoch()
        self.assertFalse(self.session.bodies)
        self.assert_disarmed()

    async def test_serial_oracle_runs_once_before_arm(self):
        result = await self.run_epoch(serial=True, oracle=b'fixture result')
        self.assertTrue(result['collector']['serial_smoke_completed'])
        self.assertEqual(self.session.bodies, [self.serial] + [self.request] * 4)
        self.assertTrue((self.root / 'result/serial.response.json').is_file())
        self.assert_disarmed()

    async def test_unarmed_oracle_mismatch_preserves_response_and_skips_raw(self):
        self.session.wrong_serial = True
        with self.assertRaises(collector.OracleMismatch):
            await self.run_epoch(serial=True, oracle=b'fixture result')
        self.assertEqual(self.session.bodies, [self.serial])
        self.assertTrue((self.root / 'result/serial.response.json').is_file())
        self.assertFalse(list(self.raw_dir.glob('capture-*.bin')))
        self.assertFalse(self.handle()['restart_required'])
        self.assert_disarmed()

    async def test_skipped_unarmed_oracle_retains_owned_gateway_count(self):
        self.session.wrong_serial = True
        with self.assertRaises(collector.OracleMismatch):
            await self.run_epoch(serial=True, oracle=b'fixture result')
        self.session.wrong_serial = False
        result = await self.run_epoch(name='next-case', epoch=2)
        self.assertTrue(result['collector']['completed'])
        self.assertEqual(len(self.session.bodies), 5)
        self.assert_disarmed()

    async def test_armed_oracle_mismatch_requires_restart(self):
        with self.assertRaises(collector.OracleMismatch):
            await self.run_epoch(oracle=b'other')
        self.assertEqual(len(self.session.bodies), 1)
        self.assertTrue(self.handle()['restart_required'])
        self.assertTrue((self.root / 'result/response-0.json').is_file())
        self.assertEqual(len(list((self.root / 'result/journals').glob('*.bin'))), 1)
        self.assert_disarmed()

    async def test_unsupported_short_actual_output_stops_without_retry(self):
        for generated in (0, 1):
            self.session.generated = generated
            name = 'short' + str(generated)
            with self.assertRaises(collector.UnsupportedCapture):
                await self.run_epoch(name=name, epoch=generated + 1)
            self.assertTrue(self.handle(name)['unsupported'])
            self.assertTrue(self.handle(name)['restart_required'])
            self.assert_disarmed()
            if generated == 0:
                (self.raw_dir / 'collector-epoch.json').unlink()
                for path in self.raw_dir.glob('capture-*.bin'):
                    path.unlink()
                self.session.main_ordinal = 0
                self.runtime.completed = 0
        self.assertEqual(len(self.session.bodies), 2)

    async def test_http_error_body_preserved_and_no_retry(self):
        self.session.status = 500
        with self.assertRaisesRegex(ValueError, 'HTTP 500'):
            await self.run_epoch()
        self.assertEqual(len(self.session.bodies), 1)
        self.assertTrue((self.root / 'result/response-0.json').is_file())
        self.assertTrue(self.handle()['restart_required'])
        self.assert_disarmed()

    async def test_transport_error_disarms_and_preserves_error(self):
        self.session.transport_error = True
        with self.assertRaisesRegex(RuntimeError, 'transport'):
            await self.run_epoch()
        self.assertEqual(len(self.session.bodies), 1)
        self.assertEqual(self.handle()['error']['type'], 'RuntimeError')
        self.assert_disarmed()

    async def test_foreign_gateway_or_raw_interference_rejects(self):
        self.session.foreign_gateway = True
        with self.assertRaisesRegex(ValueError, 'Foreign gateway'):
            await self.run_epoch()
        self.assertEqual(len(self.session.bodies), 1)
        self.assert_disarmed()

    async def test_raw_interference_rejects_completed_epoch(self):
        self.session.foreign_raw = True
        with self.assertRaisesRegex(ValueError, 'interference'):
            await self.run_epoch()
        self.assertEqual(len(self.session.bodies), 1)
        self.assertTrue(self.handle()['restart_required'])
        self.assert_disarmed()

    async def test_nonce_reuse_and_incomplete_epoch_block_without_http(self):
        await self.run_epoch()
        with self.assertRaisesRegex(ValueError, 'Previous epoch'):
            await self.run_epoch(name='reused')
        self.assertEqual(len(self.session.bodies), 4)
        self.assert_disarmed()

    async def test_two_increasing_epochs_share_engine(self):
        await self.run_epoch()
        self.session.main_ordinal = 0
        result = await self.run_epoch(name='second', epoch=2)
        self.assertTrue(result['collector']['completed'])
        self.assertEqual(len(self.session.bodies), 8)
        self.assert_disarmed()

    async def test_low_entry_memory_prevents_http_and_disarms(self):
        self.runtime.reserve = 21
        with self.assertRaisesRegex(ValueError, '22-GiB'):
            await self.run_epoch()
        self.assertFalse(self.session.bodies)
        self.assert_disarmed()

    async def test_foreign_gateway_activity_between_epochs_blocks_http(self):
        await self.run_epoch()
        self.runtime.completed += 1
        self.session.main_ordinal = 0
        with self.assertRaisesRegex(ValueError, 'between epochs'):
            await self.run_epoch(name='second', epoch=2)
        self.assertEqual(len(self.session.bodies), 4)
        self.assert_disarmed()

    async def test_bad_qpc_preserves_received_body_before_rejection(self):
        original = collector.m.fetch_http_response

        async def backward(session, url, body):
            raw, status, ended = await original(session, url, body)
            return raw, status, 0

        with patch.object(collector.m, 'fetch_http_response', side_effect=backward):
            with self.assertRaisesRegex(ValueError, 'QPC'):
                await self.run_epoch()
        self.assertTrue((self.root / 'result/response-0.json').is_file())
        self.assertTrue((self.root / 'result/transport-0.json').is_file())
        self.assertEqual(len(self.session.bodies), 1)
        self.assert_disarmed()

    async def test_cap_length_allowed_without_oracle_stop_required_with_oracle(self):
        self.session.finish_reason = 'length'
        await self.run_epoch()
        with self.assertRaisesRegex(ValueError, 'natural stop'):
            await self.run_epoch(name='oracle', epoch=2, oracle=b'fixture result')
        self.assert_disarmed()


if __name__ == '__main__':
    unittest.main()

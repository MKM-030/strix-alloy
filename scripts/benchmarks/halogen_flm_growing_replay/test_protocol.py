import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def load():
    path = HERE / 'protocol.py'
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location('growing_protocol_tested', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Clock:
    def __init__(self):
        self.value = 1000

    def __call__(self):
        self.value += 10
        return self.value


class Backend:
    """CPU fake for the externally owned typed native engine, never a prediction oracle."""
    def __init__(self):
        self.calls, self.ids = [], []
        self.callback = None
        self.fail = False
        self.bad_binding = False

    def reply(self, request, epoch):
        if self.fail:
            raise RuntimeError('finite backend failure')
        if self.callback:
            self.callback()
        return dict(request_id=request, request_epoch='f' * 32 if self.bad_binding else epoch,
                    local_count=len(self.ids), greedy_id=(sum(self.ids[-4:]) + len(self.ids)) % 1000,
                    owned_rows=True, row_count=248070, speculative_inputs=0,
                    native_timing=dict(clock='Windows QPC', frequency=10000000,
                        operation_started_ticks=100, logits_owned_ticks=200))

    def begin(self, request, epoch, tail):
        self.calls.append(('begin', list(tail)))
        self.ids = list(tail)
        return self.reply(request, epoch)

    def append_authoritative(self, request, epoch, token):
        self.calls.append(('append', token))
        self.ids.append(token)
        return self.reply(request, epoch)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.assertIsNotNone(self.m, 'The growing authority protocol is missing')
        self.backend, self.clock = Backend(), Clock()
        self.p = self.m.GrowingProducer(self.backend, enabled=True, clock_ns=self.clock)
        self.epoch = 'a' * 32
        self.prompt = list(range(1024))

    def begin(self):
        return self.p.begin(41, self.epoch, self.prompt)

    def test_disabled_path_does_not_touch_backend_or_validate_input(self):
        p = self.m.GrowingProducer(self.backend)
        self.assertIsNone(p.begin(None, None, None))
        self.assertEqual(self.backend.calls, [])

    def test_exact_tail_and_global_prefix_are_distinct_and_ready_has_no_forward(self):
        self.begin()
        self.assertEqual(self.backend.ids, self.prompt[-512:])
        packet = self.p.ready()
        self.assertEqual(packet['prefix_count'], 1024)
        self.assertEqual(packet['local_count'], 512)
        self.assertEqual(packet['prefix_sha256'], self.m.prefix_hash(self.prompt))
        self.assertEqual(len(packet['token_ids']), 1)
        self.assertFalse(packet['oracle_future_IDs'])
        self.assertEqual(packet, self.p.ready())
        self.assertEqual(len(self.backend.calls), 1)

    def test_128_authoritative_corrections_grow_to640_without_reseed_or_predicted_inputs(self):
        self.begin()
        actual = []
        for _ in range(128):
            prediction = self.p.ready()['token_ids'][0]
            token = (prediction + 7) % 1000
            actual.append(token)
            self.p.feed_line(('T 41 ' + str(token) + '\n').encode(), self.epoch)
        self.assertEqual(self.backend.ids, self.prompt[-512:] + actual)
        self.assertEqual(len(self.backend.ids), 640)
        self.assertEqual(sum(call[0] == 'begin' for call in self.backend.calls), 1)
        self.assertEqual(len(self.p.observations), 128)
        self.assertTrue(all(row['prediction_equal_to_observed_native_ID'] is False for row in self.p.observations))
        self.assertTrue(all(row['native_acceptance'] is None for row in self.p.observations))
        self.assertIsNone(self.p.ready())

    def test_native_foreign_request_is_ignored(self):
        self.begin()
        packet = self.p.ready()
        self.assertIsNone(self.p.feed_line(b'T 99 100\n', self.epoch))
        self.assertEqual(self.p.ready(), packet)
        self.assertEqual(len(self.backend.calls), 1)

    def test_unsupported_authoritative_ID_retires_before_native_append(self):
        self.begin()
        with self.assertRaises(ValueError):
            self.p.feed_line(b'T 41 248070\n', self.epoch)
        self.assertIsNone(self.p.ready())
        self.assertEqual(len(self.backend.calls), 1)

    def test_malformed_stream_retires_old_ready(self):
        self.begin()
        with self.assertRaises(ValueError):
            self.p.feed_line(b'T 41 bad\n', self.epoch)
        self.assertIsNone(self.p.ready())

    def test_cancel_during_backend_completion_cannot_publish_late_epoch(self):
        self.begin()
        self.backend.callback = lambda: self.p.cancel(self.epoch)
        self.p.feed_line(b'T 41 101\n', self.epoch)
        self.assertIsNone(self.p.ready())

    def test_backend_failure_retires_before_rethrow(self):
        self.begin()
        self.backend.fail = True
        with self.assertRaises(RuntimeError):
            self.p.feed_line(b'T 41 101\n', self.epoch)
        self.assertIsNone(self.p.ready())

    def test_bad_native_epoch_binding_cannot_publish(self):
        self.backend.bad_binding = True
        with self.assertRaises(ValueError):
            self.begin()
        self.assertIsNone(self.p.ready())

    def test_epoch_reuse_and_invalid_reset_do_not_keep_previous_ready(self):
        self.begin()
        with self.assertRaises(ValueError):
            self.begin()
        self.assertIsNone(self.p.ready())
        with self.assertRaises(ValueError):
            self.p.begin(42, 'b' * 32, [100] * 511)
        self.assertIsNone(self.p.ready())

    def test_new_epoch_resets_seed_without_carrying_previous_output(self):
        self.begin()
        self.p.feed_line(b'T 41 101\n', self.epoch)
        prompt = [100] * 8192
        self.p.begin(42, 'b' * 32, prompt)
        self.assertEqual(self.backend.ids, [100] * 512)
        self.assertEqual(self.p.ready()['prefix_count'], 8192)

    def test_done_and_error_clear_readiness_without_another_NPU_operation(self):
        for suffix in (b'D 41 stop 1024 1 1.0 3.0\n', b'D 41 error refused\n'):
            with self.subTest(suffix=suffix):
                p = self.m.GrowingProducer(self.backend, enabled=True, clock_ns=self.clock)
                p.begin(41, 'c' * 32, self.prompt)
                p.feed_line(b'T 41 101\n', 'c' * 32)
                count = len(self.backend.calls)
                p.feed_line(suffix, 'c' * 32)
                self.assertIsNone(p.ready())
                self.assertEqual(len(self.backend.calls), count)

    def test_actual_publication_clock_does_not_invent_receiver_or_target_need(self):
        self.begin()
        delivered = []
        receipt = self.p.publish_ready(lambda packet: delivered.append(packet) or True)
        self.assertTrue(receipt['submitted'])
        self.assertGreaterEqual(receipt['send_returned_qpc_ns'], receipt['send_started_qpc_ns'])
        self.assertEqual(len(delivered), 1)
        self.assertIsNone(receipt['consumer_arrived_before_target_need'])
        self.assertIsNone(receipt['consumer_arrival_timestamp'])
        self.assertEqual(len(self.backend.calls), 1)

    def test_failed_publication_does_not_claim_arrival(self):
        self.begin()
        receipt = self.p.publish_ready(lambda packet: False)
        self.assertFalse(receipt['submitted'])
        self.assertIsNone(receipt['consumer_arrived_before_target_need'])

    def test_cancelled_inflight_call_cannot_be_reentered_by_new_seed(self):
        self.begin()
        def reset_during_call():
            self.p.cancel(self.epoch)
            self.backend.callback = None
            with self.assertRaisesRegex(ValueError, 'in flight'):
                self.p.begin(42, 'b' * 32, self.prompt)
        self.backend.callback = reset_during_call
        self.p.feed_line(b'T 41 101\n', self.epoch)
        self.assertEqual([call[0] for call in self.backend.calls], ['begin', 'append'])
        self.assertIsNone(self.p.ready())

    def test_129th_target_ID_retires_without_native_overflow(self):
        self.begin()
        for _ in range(128):
            self.p.feed_line(b'T 41 101\n', self.epoch)
        with self.assertRaisesRegex(ValueError, '128'):
            self.p.feed_line(b'T 41 101\n', self.epoch)
        self.assertEqual(len(self.backend.ids), 640)
        self.assertEqual(len(self.backend.calls), 129)
        self.assertIsNone(self.p.ready())

    def test_invalid_native_done_count_retires_previous_prediction(self):
        self.begin()
        self.p.feed_line(b'T 41 101\n', self.epoch)
        with self.assertRaises(ValueError):
            self.p.feed_line(b'D 41 stop 1024 2 1.0 3.0\n', self.epoch)
        self.assertIsNone(self.p.ready())


if __name__ == '__main__':
    unittest.main()

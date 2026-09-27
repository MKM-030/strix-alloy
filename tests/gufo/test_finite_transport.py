import threading
import unittest
from gufo_control import smoke_http

class ScriptedSocket:
    def __init__(self, receives=(), *, on_send=None):
        self.receives = list(receives)
        self.on_send = on_send
        self.sent, self.closed = [], False
    def settimeout(self, timeout):
        self.timeout = timeout
    def sendall(self, data):
        self.sent.append(data)
        if self.on_send:
            self.on_send(data)
    def recv(self, maximum):
        if not self.receives:
            return b''
        data = self.receives[0]
        head, tail = data[:maximum], data[maximum:]
        if tail:
            self.receives[0] = tail
        else:
            self.receives.pop(0)
        return head
    def close(self):
        self.closed = True

class ReaderTests(unittest.TestCase):
    def test_reader_observes_split_bytes_without_raw_copy(self):
        now = [1.0]
        seen = []
        sock = ScriptedSocket([b'ab', b'cd', b''])
        reader = smoke_http._Reader(sock, 60.0, threading.Event(), wire_limit=3,
                                    on_wire=lambda data, at: seen.append((data, at)),
                                    retain_raw=False, clock=lambda: now[0],
                                    check=lambda deadline, cancel: None)
        self.assertEqual(reader.exact(2), b'ab')
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_wire_limit'):
            reader.exact(2)
        self.assertEqual(seen, [(b'ab', 1.0), (b'cd', 1.0)])
        self.assertEqual(reader.raw, bytearray())

    def test_body_limit_is_optional_and_finite_override_works(self):
        reader = smoke_http._Reader(ScriptedSocket([b'4\r\nABCD\r\n0\r\n\r\n']),
                                    60.0, threading.Event(), check=lambda *_: None)
        self.assertEqual(b''.join(p for p, _ in smoke_http._body_chunks(
            reader, {'transfer-encoding': 'chunked'}, body_limit=4)), b'ABCD')

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from gufo_control import finite_transport
from gufo_control.finite_ledger import Ledger
from gufo_control.finite_workload import load_workload

class FiniteTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'ledger'
        self.workload = load_workload()
        self.now = [100.0]
        self.ledger = Ledger(self.root, self.workload, 1, 'transport-test', 100.0,
                             create=True, clock=lambda: self.now[0])
        self.events = []

    def client(self, factory):
        return finite_transport.FiniteTransport(
            self.ledger, self.workload, 'A' * 43, socket_factory=factory,
            clock=lambda: self.now[0], milestone=self.events.append)

    def test_reservation_precedes_factory_even_on_ambiguous_send(self):
        def factory(host, port, timeout):
            self.assertTrue((self.root / 'post-001.reserved.json').exists())
            return ScriptedSocket(on_send=lambda data: (_ for _ in ()).throw(OSError('ambiguous')))
        result = self.client(factory).post(1)
        self.assertFalse(result.success)
        self.assertEqual(self.ledger.snapshot()['counts']['post'], 1)
        self.assertTrue((self.root / 'post-001.outcome.json').exists())

    def test_split_secret_capture_hash_and_no_raw_copy(self):
        sink = finite_transport.Capture(Path(self.temp.name) / 'raw.wire.bin', b'split-secret', 100)
        sink.feed(b'prefix split-', 100.0)
        sink.feed(b'secret suffix', 100.1)
        sink.close()
        data = (Path(self.temp.name) / 'raw.wire.bin').read_bytes()
        self.assertEqual(len(data), len(b'prefix split-secret suffix'))
        self.assertNotIn(b'split-secret', data)
        self.assertEqual(sink.raw_hash.hexdigest(),
                         __import__('hashlib').sha256(b'prefix split-secret suffix').hexdigest())

    def test_three_socket_ceiling(self):
        from concurrent.futures import ThreadPoolExecutor
        import time
        gate = threading.Event()
        active, peak, made = [0], [0], [0]
        lock = threading.Lock()
        opened = threading.Condition(lock)
        payload = b'{"error":{"code":"not_ready"}}'
        wire = (b'HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(payload)}\r\n\r\n'.encode() + payload)
        class HoldingSocket:
            def __init__(self):
                self.received = False
                self.closed = False
            def settimeout(self, timeout):
                self.timeout = timeout
            def sendall(self, data):
                pass
            def recv(self, maximum):
                gate.wait(2)
                if not self.received:
                    self.received = True
                    return wire
                return b''
            def close(self):
                if not self.closed:
                    self.closed = True
                    with lock:
                        active[0] -= 1
        def factory(host, port, timeout):
            with lock:
                active[0] += 1
                made[0] += 1
                peak[0] = max(peak[0], active[0])
                opened.notify_all()
            return HoldingSocket()
        client = self.client(factory)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = []
            for ordinal in (1, 2, 3):
                futures.append(pool.submit(client.get, 'ready', ordinal))
                with opened:
                    self.assertTrue(opened.wait_for(lambda: made[0] == ordinal, timeout=2))
            fourth = pool.submit(client.get, 'ready', 4)
            time.sleep(0.05)
            with lock:
                self.assertEqual(made[0], 3)
            gate.set()
            results = [future.result(timeout=3) for future in futures + [fourth]]
        self.assertEqual(peak[0], 3)
        self.assertEqual(self.ledger.snapshot()['counts']['ready'], 4)
        self.assertTrue(all(result.success for result in results))

    def test_sibling_evidence_not_ledger_metadata(self):
        sibling = self.root.with_name(self.root.name + '-finite-evidence')
        self.assertEqual(self.ledger.snapshot()['reserved_evidence_bytes'], 1048576)
        sibling.mkdir()
        (sibling / 'unexpected.bin').write_bytes(b'x')
        called = []
        result = self.client(lambda *args: called.append(args)).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(called, [])
        self.assertEqual(self.ledger.snapshot()['counts']['ready'], 1)

    def test_ledger_root_rejects_capture(self):
        (self.root / 'post-001.wire.bin').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'finite_ledger_entry'):
            self.ledger.snapshot()

    def test_ready_shape_and_bounded_return(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        sock = ScriptedSocket([wire])
        result = self.client(lambda *args: sock).get('ready', 1)
        self.assertTrue(result.success)
        self.assertEqual(result.response['model'], 'gufo-flash-next')
        self.assertEqual(result.wire_bytes, len(wire))
        self.assertEqual(result.wire_sha256,
                         __import__('hashlib').sha256(wire).hexdigest().upper())
        self.assertNotIn('response', json.loads((self.root / 'ready-001.outcome.json').read_text())['result'])

    def test_header_disconnect_counts_buffered_body_and_consumes_slot(self):
        for attempt in range(1, 31):
            post = self.workload.post(1, attempt)
            row = self.ledger.reserve('post', attempt, body=post.body)
            self.ledger.complete(row['slot'], {'success': True})
        body = b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        sock = ScriptedSocket([wire])
        result = self.client(lambda *args: sock).post(31, disconnect='headers')
        self.assertTrue(result.success)
        self.assertEqual(result.buffered_at_close, len(body))
        self.assertEqual(result.first_content_at, None)
        self.assertEqual(result.wire_bytes, len(wire))
        self.assertTrue(sock.closed)

    def test_incremental_chat_trigger_ignores_role_and_rejects_terminal(self):
        seen = []
        observer = finite_transport.SseObserver('/v1/chat/completions', 1,
                                                  lambda event, at: seen.append((event, at)))
        self.assertFalse(observer.feed(b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n', 2.0))
        self.assertTrue(observer.feed(b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n', 3.0))
        self.assertEqual(seen, [('first_content', 3.0)])
        early = finite_transport.SseObserver('/v1/chat/completions', 8, lambda *_: None)
        with self.assertRaisesRegex(smoke_http.SmokeError, 'cancel_trigger_missed'):
            early.feed(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n', 4.0)

    def test_responses_sequence_and_type_checked_before_cancel(self):
        observer = finite_transport.SseObserver('/v1/responses', 1, lambda *_: None)
        bad = (b'event: response.output_text.delta\n'
               b'data: {"type":"response.output_text.delta","sequence_number":1,"delta":"x"}\n\n')
        with self.assertRaisesRegex(smoke_http.SmokeError, 'sse_sequence_or_type'):
            observer.feed(bad, 1.0)

    def test_complete_chat_tail_survives_observer_and_transport(self):
        timing = dict(prompt_n=26, cache_n=0, predicted_n=1,
                      draft_n=0, draft_n_accepted=0)
        frames = [
            dict(model='gufo-flash-next',
                 choices=[dict(index=0, delta=dict(content='4'), finish_reason=None)]),
            dict(choices=[dict(index=0, delta={}, finish_reason='stop')], timings=timing),
            dict(choices=[], usage=dict(prompt_tokens=26, completion_tokens=1,
                                        total_tokens=27), timings=timing)]
        events = b''.join(b'data: ' + json.dumps(value).encode() + b'\n\n'
                          for value in frames) + b'data: [DONE]\n\n'
        head = (b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                + f'Content-Length: {len(events)}\r\n\r\n'.encode())
        result = self.client(lambda *args: ScriptedSocket([head, events])).post(1)
        self.assertTrue(result.success, result)
        self.assertTrue(result.assessment['fully_validated'], result.assessment)
        self.assertEqual(result.classification, 'complete_positive')
        self.assertIsNotNone(result.first_content_at)
        self.assertIsNotNone(result.terminal_at)
        self.assertTrue((self.root.with_name(self.root.name + '-finite-evidence') /
                         'post-001.answer.json').exists())

    def test_pinned_tool_stream_completes_without_usage_chunk(self):
        for attempt in range(1, 12):
            post = self.workload.post(1, attempt)
            row = self.ledger.reserve('post', attempt, body=post.body)
            self.ledger.complete(row['slot'], {'success': True})
        tool = dict(index=0, id='call_1', type='function',
                    function=dict(name='report_sum', arguments='{"sum":4}'))
        frames = [
            dict(model='gufo-flash-next',
                 choices=[dict(index=0, delta=dict(tool_calls=[tool]), finish_reason=None)]),
            dict(choices=[dict(index=0, delta={}, finish_reason='tool_calls')],
                 timings=dict(prompt_n=2304, cache_n=0, predicted_n=1,
                              draft_n=0, draft_n_accepted=0))]
        events = b''.join(b'data: ' + json.dumps(value).encode() + b'\n\n'
                          for value in frames) + b'data: [DONE]\n\n'
        head = (b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                + f'Content-Length: {len(events)}\r\n\r\n'.encode())
        result = self.client(lambda *args: ScriptedSocket([head, events])).post(12)
        self.assertTrue(result.success, result)
        self.assertTrue(result.assessment['fully_validated'], result.assessment)
        self.assertEqual(result.classification, 'complete_positive')
        self.assertIsNotNone(result.terminal_at)

    def test_received_overcap_keeps_prefix_and_hashes_all(self):
        path = Path(self.temp.name) / 'bounded.wire.bin'
        sink = finite_transport.Capture(path, b'split-secret', 16)
        first, second = b'prefix split-', b'secret suffix'
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_wire_limit'):
            sink.feed(first + second, 1.0)
        sink.close()
        self.assertEqual(sink.count, len(first + second))
        self.assertLessEqual(path.stat().st_size, 16)
        self.assertNotIn(b'split-secret', path.read_bytes())
        self.assertEqual(sink.raw_hash.hexdigest(),
                         __import__('hashlib').sha256(first + second).hexdigest())

    def test_part_limit_fails_before_append(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        with patch.object(finite_transport.finite_responses, 'PART_LIMIT', 0):
            result = self.client(lambda *args: ScriptedSocket([wire])).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'body_parts_limit')

    def test_responses_first_and_eighth_content_events(self):
        for target in (1, 8):
            with self.subTest(target=target):
                seen = []
                observer = finite_transport.SseObserver('/v1/responses', target,
                    lambda event, at: seen.append((event, at)))
                for number in range(target):
                    frame = (f'event: response.output_text.delta\n'
                             f'data: {{"type":"response.output_text.delta",'
                             f'"sequence_number":{number},"delta":"x"}}\n\n').encode()
                    self.assertEqual(observer.feed(frame[:7], float(number)), False)
                    hit = observer.feed(frame[7:], float(number) + 0.1)
                    self.assertEqual(hit, number + 1 == target)
                self.assertEqual(observer.count, target)
                self.assertEqual(seen, [('first_content', 0.1)])

    def test_encoded_output_and_utf8_frame_bounds(self):
        observer = finite_transport.SseObserver('/v1/responses', None, lambda *_: None)
        frame = (b'event: response.output_text.delta\n'
                 b'data: {"type":"response.output_text.delta","sequence_number":0,"delta":"')
        with self.assertRaises(UnicodeError):
            observer.feed(frame + b'\xff"}\n\n', 1.0)
        large = finite_transport.SseObserver('/v1/chat/completions', None, lambda *_: None)
        payload = b'data: {"choices":[{"delta":{"content":"' + b'x' * 1048577 + b'"}}]}\n\n'
        with self.assertRaisesRegex(smoke_http.SmokeError, 'decoded_output_limit'):
            large.feed(payload, 1.0)

    def test_chunk_framing_in_received_hash(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                b'Transfer-Encoding: chunked\r\n\r\n'
                + f'{len(body):X}\r\n'.encode() + body + b'\r\n0\r\n\r\n')
        result = self.client(lambda *args: ScriptedSocket([wire])).get('ready', 1)
        self.assertTrue(result.success)
        self.assertEqual(result.wire_bytes, len(wire))
        self.assertEqual(result.wire_sha256,
                         __import__('hashlib').sha256(wire).hexdigest().upper())

    def test_get_body_and_wire_caps(self):
        body = b'x' * 49153
        framed = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                  + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        result = self.client(lambda *args: ScriptedSocket([framed])).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'response_body_limit')
        self.assertLessEqual((self.root.with_name(self.root.name + '-finite-evidence') /
                              'ready-001.wire.bin').stat().st_size, 65536)

    def test_post_wire_and_body_limits_use_pinned_numbers(self):
        capture_path = Path(self.temp.name) / 'post-cap.wire.bin'
        sink = finite_transport.Capture(capture_path, b'A' * 43, 8388608)
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_wire_limit'):
            sink.feed(b'x' * 8388609, 1.0)
        sink.close()
        self.assertEqual(sink.count, 8388609)
        self.assertEqual(capture_path.stat().st_size, 8388608)
        reader = smoke_http._Reader(ScriptedSocket(), 60.0, threading.Event(),
                                    check=lambda *_: None)
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_body_limit'):
            list(smoke_http._body_chunks(reader, {'content-length': '7340033'},
                                         body_limit=7340032))

    def test_get_wire_limit_counts_all_received_bytes(self):
        path = Path(self.temp.name) / 'get-cap.wire.bin'
        sink = finite_transport.Capture(path, b'A' * 43, 65536)
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_wire_limit'):
            sink.feed(b'x' * 65537, 1.0)
        sink.close()
        self.assertEqual(sink.count, 65537)
        self.assertEqual(path.stat().st_size, 65536)

    def test_get_outcome_limit_is_4096(self):
        row = self.ledger.reserve('ready', 1)
        with self.assertRaisesRegex(ValueError, 'finite_record_size'):
            self.ledger.complete(row['slot'], {'success': True, 'oversize': 'x' * 4096})
        self.assertEqual(self.ledger.snapshot()['pending'], ['ready-001'])

    def test_answer_file_limit_rejects_without_saving_answer(self):
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                b'Content-Length: 2\r\n\r\n{}')
        parsed = dict(visible_answer='x' * 1048576, reasoning_content='', tool_calls=[])
        with patch.object(finite_transport.finite_responses, 'parse_positive_response', return_value=parsed), \
             patch.object(finite_transport.finite_assessment, 'assess_positive',
                          return_value={'structural_success': True}):
            result = self.client(lambda *args: ScriptedSocket([wire])).post(1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'answer_limit')
        self.assertFalse((self.root.with_name(self.root.name + '-finite-evidence') /
                          'post-001.answer.json').exists())

    def test_exact_pinned_exception_request_bytes(self):
        post = self.workload.post(1, 60)
        self.assertEqual((post.request_id, len(post.body)), ('reject_body_16385', 16385))
        request = self.client(lambda *args: self.fail('socket'))._request('POST', post.route, post.body)
        head, sent_body = request.split(b'\r\n\r\n', 1)
        self.assertIn(b'Content-Length: 16385', head)
        self.assertEqual(sent_body, post.body)
        self.assertEqual(__import__('hashlib').sha256(sent_body).hexdigest().upper(),
                         post.body_sha256)

    def test_deadline_during_send_latches_and_refuses_next(self):
        def late_send(data):
            self.now[0] = 161.0
        client = self.client(lambda *args: ScriptedSocket(on_send=late_send))
        with self.assertRaisesRegex(ValueError, 'finite_outcome_deadline'):
            client.post(1)
        self.assertTrue((self.root / 'transport-failed.json').exists())
        with self.assertRaisesRegex(ValueError, 'finite_transport_failed'):
            client.post(2)

    def test_bad_sibling_symlink_blocks_socket(self):
        sibling = self.root.with_name(self.root.name + '-finite-evidence')
        try:
            sibling.symlink_to(Path(self.temp.name), target_is_directory=True)
        except OSError:
            self.skipTest('Windows symlink privilege unavailable')
        calls = []
        with self.assertRaisesRegex(ValueError, 'reparse_path'):
            self.client(lambda *args: calls.append(args))
        self.assertEqual(calls, [])

    def test_late_outcome_flush_refuses_snapshot_reserve_and_reopen(self):
        from gufo_control import finite_ledger
        original_exclusive = finite_ledger._exclusive
        def advance_after_outcome(path, value, maximum):
            original_exclusive(path, value, maximum)
            if path.name.endswith('.outcome.json'):
                self.now[0] = 161.0
        row = self.ledger.reserve('ready', 1)
        with patch.object(finite_ledger, '_exclusive', side_effect=advance_after_outcome):
            with self.assertRaisesRegex(ValueError, 'finite_outcome_deadline'):
                self.ledger.complete(row['slot'], {'success': True})
        self.assertTrue((self.root / 'transport-failed.json').exists())
        for action in (self.ledger.snapshot, lambda: self.ledger.reserve('ready', 2),
                       lambda: Ledger(self.root, self.workload, 1, 'transport-test',
                                      100.0, clock=lambda: self.now[0])):
            with self.assertRaisesRegex(ValueError, 'finite_transport_failed'):
                action()

    def test_unexpected_terminal_callback_persists_failure(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        sock = ScriptedSocket([wire])
        client = self.client(lambda *args: sock)
        def unexpected(event):
            if event.event == 'terminal':
                raise RuntimeError('callback failed')
        client.milestone = unexpected
        with self.assertRaises(RuntimeError):
            client.get('ready', 1)
        outcome = json.loads((self.root / 'ready-001.outcome.json').read_text())
        self.assertFalse(outcome['result']['success'])
        self.assertTrue(sock.closed)
        self.assertEqual(self.ledger.snapshot()['pending'], [])

    def test_socket_close_failure_consumes_and_releases_permit(self):
        class CloseFailSocket(ScriptedSocket):
            def close(self):
                self.closed = True
                raise OSError('close failed')
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        sock = CloseFailSocket([wire])
        client = self.client(lambda *args: sock)
        result = client.get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(self.ledger.snapshot()['pending'], [])
        acquired = [client.sockets.acquire(blocking=False) for _ in range(4)]
        self.assertEqual(acquired, [True, True, True, False])
        for held in acquired:
            if held:
                client.sockets.release()

    def test_content_length_trailing_wire_is_ambiguous(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body + b'EXTRA')
        result = self.client(lambda *args: ScriptedSocket([wire])).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'ambiguous_response_framing')
        self.assertEqual(result.wire_bytes, len(wire))

    def test_chunked_trailing_wire_is_ambiguous(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                b'Transfer-Encoding: chunked\r\n\r\n'
                + f'{len(body):X}\r\n'.encode() + body + b'\r\n0\r\n\r\nEXTRA')
        result = self.client(lambda *args: ScriptedSocket([wire])).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'ambiguous_response_framing')
        self.assertEqual(result.wire_bytes, len(wire))

    def test_normal_close_times_are_recorded(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        result = self.client(lambda *args: ScriptedSocket([wire])).get('ready', 1)
        self.assertTrue(result.success)
        self.assertEqual(result.close_started_at, 100.0)
        self.assertEqual(result.close_completed_at, 100.0)

    def test_failed_stream_preserves_emitted_first_content_time(self):
        events = (b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n'
                  b'data: broken-json\n\n')
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                + f'Content-Length: {len(events)}\r\n\r\n'.encode() + events)
        result = self.client(lambda *args: ScriptedSocket([wire])).post(1)
        self.assertFalse(result.success)
        self.assertEqual(result.first_content_at, 100.0)
        self.assertEqual([event.event for event in self.events], ['sent', 'first_content'])

    def test_numeric_disconnect_trigger_requires_integer(self):
        calls = []
        with self.assertRaisesRegex(ValueError, 'finite_disconnect'):
            self.client(lambda *args: calls.append(args)).post(35, disconnect=1.0)
        self.assertEqual(calls, [])
        self.assertEqual(self.ledger.snapshot()['counts']['post'], 0)

    def test_latch_can_be_last_allowed_directory_entry(self):
        from types import SimpleNamespace
        from gufo_control import finite_ledger
        row = self.ledger.reserve('ready', 1)
        self.now[0] = 161.0
        self.ledger.fail_transport(row['slot'], 'outcome_deadline', self.now[0])
        maximum = 2 + 2 * (self.ledger.life['maximum_post_attempts']
                            + self.ledger.life['maximum_ready_polls'] + 1)
        reservation = self.root / 'ready-001.reserved.json'
        lock = self.root / 'runner.lock'
        latch = self.root / 'transport-failed.json'

        class Entries(list):
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False

        entries = Entries([SimpleNamespace(name=reservation.name, path=str(reservation))]
                          + [SimpleNamespace(name=lock.name, path=str(lock))] * (maximum - 1)
                          + [SimpleNamespace(name=latch.name, path=str(latch))])
        with patch.object(finite_ledger.os, 'scandir', return_value=entries):
            with self.assertRaisesRegex(ValueError, 'finite_transport_failed'):
                self.ledger.snapshot()

    def test_malformed_http_version_cannot_pass_ready(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.bogus 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        result = self.client(lambda *args: ScriptedSocket([wire])).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'malformed_status')

    def test_malformed_header_name_cannot_pass_ready(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                b'Bad Header: value\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        result = self.client(lambda *args: ScriptedSocket([wire])).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'malformed_header')

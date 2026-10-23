"""Public synthetic Task16 admission tests; never contact a model service."""
import asyncio
import json
import socket
import threading
import time
import unittest
from contextlib import asynccontextmanager

from conversation_router import ConversationRouter, LoopbackConversationModel, RoutingContext

PATH = '/v1/chat/completions'
TEXT = 'Bitte prüfe diese Äußerung.'


def count_body(value=3584):
    return json.dumps({'object': 'response.input_tokens', 'input_tokens': value}).encode()


def choice_body(value=3584, **changes):
    result = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"choice":"clarify"}'}}],
              'usage': {'prompt_tokens': value, 'completion_tokens': 6}}
    result.update(changes)
    return json.dumps(result).encode()


def framed(body, extra=b''):
    return b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n' + extra + b'\r\n' + body


class Peer:
    """One controlled persistent connection; captures exact received wire bytes."""
    def __init__(self, replies):
        self.replies = replies
        self.requests = []
        self.accepted = 0
        self.closed = threading.Event()
        self.stop = threading.Event()
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen()
        self.listener.settimeout(.05)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            while not self.stop.is_set():
                try: connection, _ = self.listener.accept()
                except socket.timeout: continue
                self.accepted += 1
                with connection:
                    connection.settimeout(1)
                    for reply in self.replies:
                        raw = b''
                        while b'\r\n\r\n' not in raw:
                            part = connection.recv(4096)
                            if not part: return
                            raw += part
                        headers, body = raw.split(b'\r\n\r\n', 1)
                        length = next(int(line.split(b':', 1)[1]) for line in headers.split(b'\r\n')[1:]
                                      if line.lower().startswith(b'content-length:'))
                        while len(body) < length:
                            part = connection.recv(length - len(body))
                            if not part: return
                            body += part
                        self.requests.append((headers.split(b' ')[1].decode(), body, headers + b'\r\n\r\n' + body))
                        if callable(reply): reply(connection)
                        else: connection.sendall(reply)
                    # Observe client retirement instead of masking leaks with server closure.
                    while connection.recv(4096): pass
                return
        except (OSError, StopIteration):
            pass
        finally:
            self.closed.set()

    async def finish(self):
        self.stop.set()
        await asyncio.to_thread(self.thread.join, 1.2)
        self.listener.close()


class ObservedModel(LoopbackConversationModel):
    def __init__(self, port, timeout=1, token=''):
        super().__init__(None, f'http://127.0.0.1:{port}{PATH}', 'synthetic', token, timeout)
        self.observations = []

    def _observe_admission(self, snapshot):
        self.observations.append(snapshot)


@asynccontextmanager
async def transaction(replies, timeout=1):
    peer = Peer(replies)
    model = ObservedModel(peer.port, timeout)
    try: yield peer, model
    finally: await peer.finish()


class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def decide(self, model, text=TEXT):
        return await ConversationRouter(model).decide(text, RoutingContext('scope', []))

    async def test_exact_boundaries_gate_before_inference(self):
        for n, reason, attempts in ((3583, 'unclear', 2), (3584, 'unclear', 2), (3585, 'context_budget', 1)):
            async with transaction([framed(count_body(n)), framed(choice_body(n))]) as (peer, model):
                d = await self.decide(model)
                self.assertEqual(d.reason, reason)
                self.assertEqual(len(peer.requests), attempts)
                self.assertEqual(peer.requests[0][0], PATH + '/input_tokens')
                if attempts == 2:
                    self.assertEqual(peer.requests[1][0], PATH)
                    self.assertEqual(peer.requests[0][1], peer.requests[1][1])
                    self.assertFalse(json.loads(peer.requests[0][1])['cache_prompt'])

    async def test_malformed_count_never_reaches_inference(self):
        bodies = [b'{}', b'{', b'{"object":"other","input_tokens":1}',
                  b'{"object":"response.input_tokens","input_tokens":1,"input_tokens":2}']
        bodies += [count_body(n) for n in (True, 1.0, '1', 0, -1, None)]
        bodies += [b'x' * 8193]
        for body in bodies:
            async with transaction([framed(body), framed(choice_body())]) as (peer, model):
                d = await self.decide(model)
                self.assertEqual(d.reason, 'unavailable')
                self.assertEqual(len(peer.requests), 1)
                self.assertIsNone(d.proposal.json_syntax_valid)

    async def test_usage_disagreement_and_incomplete_output_fail_closed(self):
        cases = [(choice_body(3583), 'unavailable'), (choice_body(usage={}), 'unavailable'),
                 (choice_body(usage={'prompt_tokens': True, 'completion_tokens': 1}), 'unavailable'),
                 (choice_body(usage={'prompt_tokens': 3584, 'completion_tokens': 25}), 'unavailable'),
                 (choice_body(choices=[{'finish_reason': 'length', 'message': {'content': '{"choice":"clarify"}'}}]), 'schema')]
        for body, reason in cases:
            async with transaction([framed(count_body()), framed(body)]) as (_, model):
                self.assertEqual((await self.decide(model)).reason, reason)

    async def test_complete_count_frame_required_before_admission(self):
        def partial(connection):
            connection.sendall(framed(count_body())[:-1])
            time.sleep(.16)
        async with transaction([partial, framed(choice_body())], .08) as (peer, model):
            self.assertEqual((await self.decide(model)).reason, 'timeout')
            await asyncio.sleep(.18)
            self.assertEqual(len(peer.requests), 1)

    async def test_count_and_inference_share_absolute_deadline(self):
        def delayed(body):
            def send(connection):
                time.sleep(.09)
                connection.sendall(framed(body))
            return send
        async with transaction([delayed(count_body()), delayed(choice_body())], .14) as (peer, model):
            started = time.monotonic()
            self.assertEqual((await self.decide(model)).reason, 'timeout')
            self.assertLess(time.monotonic() - started, .24)
            self.assertEqual(len(peer.requests), 2)

    async def test_cancelled_count_cannot_dispatch_inference(self):
        entered = threading.Event()
        release = threading.Event()
        def late(connection):
            entered.set()
            release.wait(.5)
            connection.sendall(framed(count_body()))
        async with transaction([late, framed(choice_body())]) as (peer, model):
            pending = asyncio.create_task(model.classify(TEXT, RoutingContext('scope', [])))
            self.assertTrue(await asyncio.to_thread(entered.wait, .5))
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError): await pending
            release.set()
            await asyncio.sleep(.05)
            self.assertEqual(len(peer.requests), 1)
            self.assertTrue(peer.closed.is_set())

    async def test_snapshot_counters_are_private_and_resources_retired(self):
        async with transaction([framed(count_body()), framed(choice_body())]) as (peer, model):
            await self.decide(model)
            self.assertTrue(model.observations, 'request-owned admission observation missing')
            receipt = model.observations[-1]
            self.assertEqual((receipt.count_attempts, receipt.inference_attempts, receipt.total_attempts), (1, 1, 2))
            self.assertEqual(receipt.protocol, 'pinned_chat_count_v1')
            self.assertEqual(receipt.transaction_bytes, sum(len(r[2]) for r in peer.requests))
            self.assertFalse(receipt.worker_outstanding)
            self.assertTrue(receipt.connection_closed)
            self.assertTrue(receipt.usage_count_match)
            self.assertFalse(hasattr(model, 'last_receipt'))

class FramingAndOwnershipTests(unittest.IsolatedAsyncioTestCase):
    decide = AdmissionTests.decide

    async def test_trickle_and_fragmented_headers_share_deadline(self):
        def trickle(connection):
            for byte in framed(count_body()):
                connection.sendall(bytes([byte]))
                time.sleep(.005)
        async with transaction([trickle, framed(choice_body())], .08) as (peer, model):
            started = time.monotonic()
            self.assertEqual((await self.decide(model)).reason, 'timeout')
            self.assertLess(time.monotonic() - started, .2)
            self.assertEqual(len(peer.requests), 1)

    async def test_complete_chunked_and_fragmented_responses(self):
        def chunked(body):
            chunks = [body[:3], body[3:10], body[10:]]
            return (b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n' +
                    b''.join(f'{len(c):x}\r\n'.encode() + c + b'\r\n' for c in chunks) + b'0\r\n\r\n')
        def fragmented(connection):
            wire = chunked(count_body())
            for index in range(0, len(wire), 7):
                connection.sendall(wire[index:index+7])
        async with transaction([fragmented, chunked(choice_body())]) as (peer, model):
            self.assertEqual((await self.decide(model)).reason, 'unclear')
            self.assertEqual(len(peer.requests), 2)
            self.assertEqual(peer.accepted, 1)

    async def test_chunk_prefix_cannot_admit_without_terminal_chunk(self):
        body = count_body()
        def truncated(connection):
            connection.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n' +
                               f'{len(body):x}\r\n'.encode() + body + b'\r\n')
            time.sleep(.15)
        async with transaction([truncated, framed(choice_body())], .06) as (peer, model):
            self.assertEqual((await self.decide(model)).reason, 'timeout')
            self.assertEqual(len(peer.requests), 1)

    async def test_status_framing_failure_and_connection_loss_never_retry(self):
        body = count_body()
        bad = [b'HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\n\r\n',
               b'HTTP/1.1 302 Redirect\r\nLocation: http://example.com/\r\nContent-Length: 0\r\n\r\n',
               framed(body, b'Content-Length: 1\r\n'),
               framed(body, b'Transfer-Encoding: chunked\r\n'),
               framed(body, b'Connection: close\r\n'),
               framed(body, b'X-Padding: ' + b'x' * 16400 + b'\r\n')]
        def lost(connection): connection.shutdown(socket.SHUT_RDWR)
        for reply in bad + [lost]:
            async with transaction([reply, framed(choice_body())]) as (peer, model):
                self.assertEqual((await self.decide(model)).reason, 'unavailable')
                self.assertEqual(len(peer.requests), 1)
                self.assertEqual(peer.accepted, 1)

    async def test_envelope_body8192_independent_of_header_framing(self):
        body = choice_body()
        body += b' ' * (8192 - len(body))
        async with transaction([framed(count_body()), framed(body, b'X-Synthetic: valid\r\n')]) as (_, model):
            self.assertEqual((await self.decide(model)).reason, 'unclear')
        async with transaction([framed(count_body()), framed(body + b' ')]) as (_, model):
            self.assertEqual((await self.decide(model)).reason, 'unavailable')

    async def test_actual_complete_wire16384_boundary_includes_long_auth_and_count_path(self):
        import tempfile
        from pathlib import Path
        from conversation_admission import AdmissionRequest, prepare_frames, exchange
        with tempfile.TemporaryDirectory() as folder:
            token_file = Path(folder) / 'token'
            token_file.write_text('t' * 4096, encoding='utf-8')
            async with transaction([framed(count_body()), framed(choice_body())]) as (peer, _):
                # Independent expected explicit wire format, including the longer count path.
                prefix = f'POST {PATH}/input_tokens HTTP/1.1\r\nHost: 127.0.0.1:{peer.port}\r\nContent-Type: application/json\r\nAccept: application/json\r\n'
                suffix = '\r\nConnection: keep-alive\r\nAuthorization: Bearer ' + 't' * 4096 + '\r\n\r\n'
                size = 12000
                for _ in range(3):
                    size = 16384 - len((prefix + f'Content-Length: {size}' + suffix).encode())
                payload = b'x' * size
                expected = (prefix + f'Content-Length: {size}' + suffix).encode() + payload
                self.assertEqual(len(expected), 16384)
                frames = prepare_frames('127.0.0.1', peer.port, payload, token_file)
                self.assertEqual(frames[0], expected)
                self.assertEqual(len(frames[1]), 16371)
                state = AdmissionRequest(1)
                def send():
                    try:
                        state.dispatch('count', len(frames[0]))
                        owned = state.connect('127.0.0.1', peer.port)
                        return exchange(state, owned, frames[0])[0]
                    finally: state.close()
                self.assertEqual(await asyncio.to_thread(send), count_body())
                self.assertEqual(peer.requests[0][2], expected)
                from routing_policy import ContextBudgetExceeded
                with self.assertRaises(ContextBudgetExceeded):
                    prepare_frames('127.0.0.1', peer.port, payload + b'x', token_file)

    async def test_cancellation_before_and_after_dispatch_linearization(self):
        from unittest.mock import patch
        from conversation_admission import AdmissionRequest
        original = AdmissionRequest.dispatch
        for after in (False, True):
            entered, release = threading.Event(), threading.Event()
            def dispatch(state, phase, size):
                if phase != 'inference': return original(state, phase, size)
                if after: original(state, phase, size)
                entered.set()
                release.wait(.5)
                if not after: return original(state, phase, size)
            async with transaction([framed(count_body()), framed(choice_body())]) as (peer, model):
                with patch.object(AdmissionRequest, 'dispatch', dispatch):
                    pending = asyncio.create_task(model.classify(TEXT, RoutingContext('scope', [])))
                    self.assertTrue(await asyncio.to_thread(entered.wait, .5))
                    pending.cancel()
                    with self.assertRaises(asyncio.CancelledError): await pending
                    release.set()
                    await asyncio.sleep(.04)
                self.assertEqual(len(peer.requests), 1)
                receipt = model.observations[-1]
                self.assertEqual(receipt.inference_attempts, int(after))
                self.assertEqual(receipt.reason, 'cancelled')
                self.assertTrue(receipt.connection_closed)

    async def test_preparation_and_observer_consume_deadline_without_late_acceptance(self):
        from unittest.mock import patch
        from pathlib import Path
        original = Path.open
        def delayed(path, *args, **kwargs):
            time.sleep(.12)
            return original(path, *args, **kwargs)
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / 'token'
            token.write_text('test', encoding='utf-8')
            async with transaction([framed(count_body()), framed(choice_body())], .05) as (peer, model):
                model.token_file = token
                with patch.object(Path, 'open', delayed):
                    self.assertEqual((await self.decide(model)).reason, 'timeout')
                    await asyncio.sleep(.13)
                self.assertEqual(peer.requests, [])
                self.assertEqual(model.observations[-1].total_attempts, 0)
        async with transaction([framed(count_body()), framed(choice_body())], .05) as (_, model):
            def observer(_): time.sleep(.12)
            model._observe_admission = observer
            self.assertEqual((await self.decide(model)).reason, 'timeout')

    async def test_all70_options_original_text_and_competitors_preserved(self):
        from dataclasses import replace
        from test_unified_routing_policy import AGENT, context
        ctx = context('Wie lautet Ihr Name?', 'An welchem Datum?')
        for i in range(2, 9):
            ctx.tasks.append(dict(ctx.tasks[0], task_id=f'work-{i}2', open_question=None))
        ctx.agents = [replace(AGENT, alias=f'office-{i}', agent_id=f'agent-{i}', description='  Grüß dich 東京  ') for i in range(16)]
        original = '  Bitte prüfe meine Äußerung. 東京 \n '
        async with transaction([framed(count_body()), framed(choice_body())]) as (peer, model):
            self.assertEqual((await ConversationRouter(model).decide(original, ctx)).reason, 'unclear')
            data = json.loads(json.loads(peer.requests[0][1])['messages'][1]['content'])
            self.assertEqual(data['utterance'], original)
            self.assertEqual(len(data['context']['options']), 70)
            self.assertEqual(len(data['context']['tasks']), 8)
            self.assertEqual(len(data['context']['agents']), 16)
            self.assertEqual([a['description'] for a in data['context']['agents']], ['  Grüß dich 東京  '] * 16)
            for expected, actual in zip(ctx.tasks, data['context']['tasks']):
                for key in ('objective', 'open_question', 'previous_question'):
                    if key in expected: self.assertEqual(actual[key], expected[key])
            self.assertEqual(peer.requests[0][1], peer.requests[1][1])

    async def test_byte_fitting_high_token_input_is_not_estimated_or_truncated(self):
        async with transaction([framed(count_body(3585)), framed(choice_body())]) as (peer, model):
            text = '東京' * 1800
            self.assertEqual((await self.decide(model, text)).reason, 'context_budget')
            self.assertEqual(len(peer.requests), 1)
            self.assertLessEqual(len(peer.requests[0][2]), 16384)
            self.assertEqual(json.loads(json.loads(peer.requests[0][1])['messages'][1]['content'])['utterance'], text)

    async def test_overlapping_requests_have_distinct_immutable_observations(self):
        from dataclasses import FrozenInstanceError
        async with transaction([framed(count_body(3583)), framed(choice_body(3583))]) as (_, first):
            async with transaction([framed(count_body(3585))]) as (_, second):
                result = await asyncio.gather(self.decide(first), self.decide(second))
                self.assertEqual([d.reason for d in result], ['unclear', 'context_budget'])
                a, b = first.observations[-1], second.observations[-1]
                self.assertNotEqual(a.request_id, b.request_id)
                self.assertEqual((a.input_tokens, b.input_tokens), (3583, 3585))
                self.assertEqual((a.total_attempts, b.total_attempts), (2, 1))
                with self.assertRaises(FrozenInstanceError): a.input_tokens = 1

    async def test_byte_rejection_and_local_bypass_make_zero_attempts(self):
        async with transaction([framed(count_body())]) as (peer, model):
            d = await self.decide(model, 'ü' * 4001)
            self.assertEqual(d.reason, 'schema')
            self.assertEqual(peer.requests, [])
            d = await self.decide(model, 'Hör bitte auf zu sprechen')
            self.assertEqual(d.route.intent, 'stop_speaking')
            self.assertEqual(peer.requests, [])

    async def test_local_and_byte_rejection_receipts_have_zero_attempts(self):
        async with transaction([framed(count_body())]) as (peer, model):
            await self.decide(model, 'Hör bitte auf zu sprechen')
            self.assertTrue(model.observations)
            receipt = model.observations[-1]
            self.assertEqual((receipt.count_attempts, receipt.inference_attempts, receipt.total_attempts), (0, 0, 0))
            self.assertEqual(receipt.stage, 'bypass')
            self.assertIsNone(receipt.count_valid)
            await self.decide(model, 'x' * 4001)
            self.assertEqual(model.observations[-1].reason, 'bounds')
            self.assertEqual(peer.requests, [])

    async def test_cancel_reports_honest_outstanding_worker_then_cleanup(self):
        from unittest.mock import patch
        import conversation_router
        entered, release = threading.Event(), threading.Event()
        original = conversation_router.prepare_frames
        def held(*args):
            entered.set()
            release.wait(.5)
            return original(*args)
        async with transaction([framed(count_body())]) as (peer, model):
            with patch.object(conversation_router, 'prepare_frames', held):
                pending = asyncio.create_task(model.classify(TEXT, RoutingContext('scope', [])))
                self.assertTrue(await asyncio.to_thread(entered.wait, .5))
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError): await pending
                await asyncio.sleep(.02)
                self.assertTrue(any(s.worker_outstanding and s.reason == 'cancelled' for s in model.observations))
                release.set()
                await asyncio.sleep(.04)
            self.assertFalse(model.observations[-1].worker_outstanding)
            self.assertEqual(model.observations[-1].reason, 'cancelled')
            self.assertEqual(peer.requests, [])

    async def test_premature_eof_in_chunk_terminator_cannot_admit(self):
        body = count_body()
        def incomplete(connection):
            connection.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n' +
                               f'{len(body):x}\r\n'.encode() + body + b'\r\n0\r\n')
            connection.shutdown(socket.SHUT_WR)
        async with transaction([incomplete, framed(choice_body())]) as (peer, model):
            d = await self.decide(model)
            self.assertEqual(d.reason, 'unavailable')
            self.assertEqual(len(peer.requests), 1)

    async def test_deadline_during_final_count_validation_prevents_inference(self):
        from unittest.mock import patch
        import conversation_router
        original = conversation_router._strict_json
        def slow(raw, cap):
            value = original(raw, cap)
            if value.get('object') == 'response.input_tokens': time.sleep(.1)
            return value
        async with transaction([framed(count_body()), framed(choice_body())], .05) as (peer, model):
            with patch.object(conversation_router, '_strict_json', slow):
                self.assertEqual((await self.decide(model)).reason, 'timeout')
                await asyncio.sleep(.1)
            self.assertEqual(len(peer.requests), 1)

    async def test_same_model_overlapping_requests_keep_private_receipts(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        barrier = threading.Barrier(2)
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_): pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                text = json.loads(payload['messages'][1]['content'])['utterance']
                count = 3583 if text == 'first' else 3585
                if self.path.endswith('/input_tokens'):
                    barrier.wait(1)
                    body = count_body(count)
                else:
                    body = choice_body(count)
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            model = ObservedModel(server.server_port)
            result = await asyncio.gather(self.decide(model, 'first'), self.decide(model, 'second'))
            self.assertEqual([d.reason for d in result], ['unclear', 'context_budget'])
            receipts = model.observations
            self.assertEqual(len(receipts), 2)
            self.assertEqual(len({s.request_id for s in receipts}), 2)
            self.assertEqual(sorted((s.input_tokens, s.total_attempts) for s in receipts), [(3583, 2), (3585, 1)])
            self.assertTrue(all(s.connection_closed and not s.worker_outstanding for s in receipts))
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close()

    async def test_invalid_chunk_separator_never_admits(self):
        body = count_body()
        wire = (b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n' +
                f'{len(body):x}\r\n'.encode() + body + b'XX0\r\n\r\n')
        async with transaction([wire, framed(choice_body())]) as (peer, model):
            self.assertEqual((await self.decide(model)).reason, 'unavailable')
            self.assertEqual(len(peer.requests), 1)

    async def test_connection_failure_is_one_attempt_with_phase_timing(self):
        from unittest.mock import patch
        from conversation_admission import AdmissionRequest
        async with transaction([]) as (peer, model):
            with patch.object(AdmissionRequest, 'connect', side_effect=OSError('synthetic connect failure')):
                self.assertEqual((await self.decide(model)).reason, 'unavailable')
            receipt = model.observations[-1]
            self.assertEqual((receipt.count_attempts, receipt.inference_attempts, receipt.total_attempts), (1, 0, 1))
            self.assertIsNotNone(receipt.count_ms)
            self.assertTrue(receipt.connection_closed)
            self.assertEqual(peer.requests, [])

    async def test_router_preparation_is_inside_shared_deadline(self):
        from unittest.mock import patch
        from route_proposal import ProposalContract
        original = ProposalContract.model_data
        def slow(contract):
            time.sleep(.12)
            return original(contract)
        async with transaction([framed(count_body()), framed(choice_body())], .05) as (peer, model):
            started = time.monotonic()
            with patch.object(ProposalContract, 'model_data', slow):
                self.assertEqual((await self.decide(model)).reason, 'timeout')
                self.assertLess(time.monotonic() - started, .1)
                await asyncio.sleep(.14)
            self.assertEqual(peer.requests, [])

    async def test_missing_usage_and_context_error_envelope_are_unavailable(self):
        for body in (b'{}', b'{"error":{"message":"context exceeded"}}',
                     choice_body(usage=None), choice_body(choices=[{'message': {'content': '{"choice":"clarify"}'}}])):
            async with transaction([framed(count_body()), framed(body)]) as (_, model):
                d = await self.decide(model)
                self.assertEqual(d.reason, 'unavailable')
                self.assertIsNone(d.proposal.schema_shape_valid)

    async def test_completion_usage_strict_integer_and_output_stop_required(self):
        for value in (True, 1.0, '1', -1, 25, None):
            body = choice_body(usage={'prompt_tokens': 3584, 'completion_tokens': value})
            async with transaction([framed(count_body()), framed(body)]) as (_, model):
                self.assertEqual((await self.decide(model)).reason, 'unavailable')
        for value in (0, 24):
            body = choice_body(usage={'prompt_tokens': 3584, 'completion_tokens': value})
            async with transaction([framed(count_body()), framed(body)]) as (_, model):
                self.assertEqual((await self.decide(model)).reason, 'unclear')

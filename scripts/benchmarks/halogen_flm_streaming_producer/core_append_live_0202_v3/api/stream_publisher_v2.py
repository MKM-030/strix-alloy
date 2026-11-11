"""Default-off queued producer endpoint and immediate HDO2 authority publication.

Only cold construction creates sockets/threads. API callbacks never await NPU
work or TCP I/O. Unix sendto is DONTWAIT; this is not a wall-clock guarantee for
kernel scheduling. No regular-file polling or per-token open/pread occurs.
"""
import json
import queue
import secrets
import socket
import struct
import threading

import wire

MAX_FRAME = 4 * 1024 * 1024
MAX_EVENTS = 64


class StreamingPublisher:
    def __init__(self, endpoint, consumer_socket, *, enabled=False):
        self.enabled = enabled is True
        self.active = None
        self.sequence = 0
        self.error = None
        self.dropped_ready = 0
        self.events = queue.Queue(MAX_EVENTS)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.retirement_requested = threading.Event()
        self.retirement_reason = None
        self.socket = None
        self.connection = None
        self.consumer_socket = consumer_socket
        if not self.enabled:
            return
        if (type(endpoint) is not tuple or len(endpoint) != 2 or type(endpoint[0]) is not str
                or not wire.integer(endpoint[1], 1, 65535)
                or type(consumer_socket) is not str or not consumer_socket.startswith('/tmp/')
                or len(consumer_socket.encode()) >= 108):
            raise ValueError('Explicit cold-owned producer endpoint and Unix socket required')
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.endpoint = endpoint
        self.writer = threading.Thread(target=self._writer, daemon=True, name='hdo2-event-writer')
        self.writer.start()

    def _send_consumer(self, packet):
        try:
            return self.socket.sendto(packet, self.consumer_socket) == len(packet)
        except OSError:
            return False

    def _retire(self, reason):
        # Caller holds lock. Retirement never depends on successful transport.
        previous, self.active = self.active, None
        self.error = self.error or reason
        if previous is not None:
            self.sequence += 1
            self._send_consumer(wire.encode(wire.CANCEL, previous, self.sequence))

    def _request_retirement(self, reason):
        # Nonwaiting API failure signal only. No model/speculative state is
        # touched here; the transport worker closes TCP and the client cleans
        # up its own serial actor/context on EOF.
        self.retirement_reason = self.retirement_reason or reason
        self.enabled = False
        self.retirement_requested.set()
        self.stop.set()

    def _finish_retirement(self):
        # Worker only, after TCP close. READY never owns this lock now. A
        # remaining API owner can finish without waiting for any native work.
        if self.retirement_requested.is_set():
            with self.lock:
                self._retire(self.retirement_reason)

    def _fail_transport(self, reason):
        # Caller holds lock. Only signal here; the writer owns TCP shutdown.
        self.enabled = False
        self._retire(self.retirement_reason or reason)
        self.stop.set()

    def _enqueue(self, event):
        try:
            self.events.put_nowait(event)
            return True
        except queue.Full:
            self._fail_transport('producer_event_queue_full')
            return False

    def begin(self, packet, prompt_ids):
        if not self.enabled:
            return False
        if not self.lock.acquire(blocking=False):
            self._request_retirement('authority_lock_busy')
            return False
        try:
            if self.active is not None:
                self._fail_transport('concurrent_request_unsupported')
                return False
            ids = tuple(prompt_ids)
            binding = wire.key(dict(packet, n_prompt=packet['prefix_count'], nonce=secrets.randbits(64) or 1,
                                    current_token=-1))
            if (packet['kind'] != 'begin' or binding['generated_count'] != 0
                    or len(ids) != binding['n_prompt']
                    or any(not wire.integer(i, 0, wire.HEAD_ROWS - 1) for i in ids)):
                raise ValueError('Exact prompt and begin packet required')
            self.active, self.sequence, self.error = binding, 1, None
            if not self._send_consumer(wire.encode(wire.BEGIN, binding, self.sequence)):
                self._fail_transport('consumer_begin_unavailable')
                return False
            return self._enqueue(dict(packet, n_prompt=binding['n_prompt'], nonce=binding['nonce'],
                                      current_token=-1, prompt_ids=ids, sequence=self.sequence))
        finally:
            self.lock.release()

    def feedback(self, packet):
        if not self.enabled:
            return False
        if not self.lock.acquire(blocking=False):
            self._request_retirement('authority_lock_busy')
            return False
        try:
            old = self.active
            if old is None:
                return False
            if (packet['request_id'] != old['request_id'] or packet['request_epoch'] != old['request_epoch']):
                self._fail_transport('feedback_epoch_mismatch')
                return False
            kind = packet['kind']
            if kind == 'commit':
                ids = tuple(packet['token_ids'])
                if len(ids) != 1 or packet['generated_count'] != old['generated_count'] + 1:
                    self._fail_transport('authority_sequence_gap')
                    return False
                binding = wire.key(dict(packet, n_prompt=old['n_prompt'], nonce=old['nonce'], current_token=ids[0]))
                self.active = binding
                self.sequence += 1
                if not self._send_consumer(wire.encode(wire.AUTHORITY, binding, self.sequence, ids)):
                    self._fail_transport('consumer_authority_unavailable')
                    return False
                return self._enqueue(dict(packet, n_prompt=binding['n_prompt'], nonce=binding['nonce'],
                                          current_token=ids[0], sequence=self.sequence))
            if kind in ('done', 'error', 'cancelled', 'invalid'):
                self.sequence += 1
                self._send_consumer(wire.encode(wire.END if kind == 'done' else wire.CANCEL, old, self.sequence))
                event = dict(packet, n_prompt=old['n_prompt'], nonce=old['nonce'],
                             current_token=old['current_token'], sequence=self.sequence)
                self.active = None
                return self._enqueue(event)
            return False
        finally:
            self.lock.release()

    def _writer(self):
        try:
            connection = socket.create_connection(self.endpoint, timeout=5)
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            connection.settimeout(1)
            self.connection = connection
            threading.Thread(target=self._reader, args=(connection,), daemon=True,
                             name='hdo2-ready-reader').start()
            while not self.stop.is_set():
                try:
                    event = self.events.get(timeout=0.2)
                except queue.Empty:
                    continue
                frame = json.dumps(event, separators=(',', ':'), allow_nan=False).encode('utf-8')
                if not 0 < len(frame) <= MAX_FRAME:
                    raise ValueError('Producer event exceeds framed endpoint bound')
                connection.sendall(struct.pack('<I', len(frame)) + frame)
        except Exception as error:
            with self.lock:
                self._fail_transport('producer_transport_' + type(error).__name__)
        finally:
            self.stop.set()
            connection = self.connection
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
            self._finish_retirement()

    def _read_exact(self, connection, size):
        result = bytearray()
        while len(result) < size:
            try:
                part = connection.recv(size - len(result))
            except socket.timeout:
                if self.stop.is_set():
                    raise EOFError('Producer owner stopped')
                continue
            if not part:
                raise EOFError('Producer endpoint disconnected')
            result.extend(part)
        return bytes(result)

    def _reader(self, connection):
        try:
            while not self.stop.is_set():
                length, = struct.unpack('<I', self._read_exact(connection, 4))
                if not 0 < length <= MAX_FRAME:
                    raise ValueError('Invalid producer frame length')
                response = json.loads(self._read_exact(connection, length))
                self._relay_ready(response)
        except Exception as error:
            with self.lock:
                self._fail_transport('producer_response_' + type(error).__name__)

    def _relay_ready(self, response):
        binding = wire.key(response)
        # Active bindings are immutable dictionaries, replaced atomically by
        # the API authority owner. Copy the reference without owning its lock.
        # Native AUTH/G/hash/current checks independently reject any stale race.
        active = self.active
        if (not self.enabled or self.stop.is_set() or active is None
                or any(binding[k] != active[k] for k in
                       ('request_id', 'n_prompt', 'request_epoch', 'nonce'))):
            return False
        if (binding['generated_count'] < 1 or not active['generated_count'] <=
                binding['generated_count'] <= active['generated_count'] + 3):
            return False
        packet = wire.encode(wire.READY, binding, response['ready_sequence'], response['token_ids'])
        if not self._send_consumer(packet):
            self.dropped_ready += 1
            return False
        return True

    def close(self):
        with self.lock:
            self.enabled = False
            self._retire('owner_closed')
        self.stop.set()
        if self.connection is not None:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
        if self.socket is not None:
            self.socket.close()

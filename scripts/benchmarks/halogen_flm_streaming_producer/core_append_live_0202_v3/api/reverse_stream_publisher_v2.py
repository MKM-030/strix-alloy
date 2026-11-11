"""Reverse TCP listener for the frozen HDO2 publisher; no protocol changes.

API construction starts a worker and returns. A Windows producer makes exactly
one connection via the explicit Docker localhost publication. No reconnect,
outbound Windows connection, driver or firewall changes are performed here.
"""
import json
import queue
import socket
import struct
import threading
import time

from stream_publisher_v2 import StreamingPublisher, MAX_FRAME


class ReverseStreamingPublisher(StreamingPublisher):
    def __init__(self, endpoint, consumer_socket, *, enabled=False):
        super().__init__(None, consumer_socket, enabled=False)
        self.listener = None
        self.listening = threading.Event()
        if enabled is not True:
            return
        if (endpoint != ('0.0.0.0', 8734) or type(consumer_socket) is not str
                or not consumer_socket.startswith('/tmp/') or len(consumer_socket.encode()) >= 108):
            raise ValueError('Exact private reverse listener and Unix socket required')
        self.enabled = True
        self.endpoint = endpoint
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.writer = threading.Thread(target=self._writer, daemon=True, name='hdo2-reverse-event-writer')
        self.writer.start()

    def _writer(self):
        listener = None
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener = listener
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(self.endpoint)
            listener.listen(1)
            listener.settimeout(0.2)
            deadline = time.monotonic() + 900
            self.listening.set()
            print('[hdo2-transport] reverse listener ready; one client, 900-second admission', flush=True)
            connection = None
            while not self.stop.is_set() and time.monotonic() < deadline:
                try:
                    connection, _ = listener.accept()
                    break
                except socket.timeout:
                    continue
            if connection is None:
                raise TimeoutError('Reverse producer connection did not arrive in its finite window')
            self.connection = connection
            # No second client can be accepted, including after transport loss.
            listener.close()
            listener = None
            self.listener = None
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            connection.settimeout(1)
            threading.Thread(target=self._reader, args=(connection,), daemon=True,
                             name='hdo2-reverse-ready-reader').start()
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
                self._fail_transport('reverse_producer_transport_' + type(error).__name__)
        finally:
            self.stop.set()
            if listener is not None:
                listener.close()
            self.listener = None
            connection = self.connection
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
            self._finish_retirement()

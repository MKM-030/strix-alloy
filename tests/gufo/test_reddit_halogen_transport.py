"""Loopback-only regression; run only when the Halogen endpoint is stopped."""
import http.server
import threading
import time
import unittest

from scripts.gufo_control.reddit_halogen_client import exchange


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.flush()
        time.sleep(5.25 if self.path == '/slow' else .4)
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *_):
        pass


class TransportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Bind failure must remain a failure; never stop an existing endpoint.
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 8731), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    def test_prefill_silence_longer_than_five_seconds(self):
        status, _, raw, start, end = exchange('GET', '/slow', timeout=8)
        self.assertEqual((status, raw), (200, b'{"ok":true}'))
        self.assertGreaterEqual(end-start, 5)
        self.assertLess(end-start, 8)

    def test_absolute_deadline_is_retained(self):
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            exchange('GET', '/deadline', timeout=.1)
        self.assertLess(time.monotonic()-start, 1)


if __name__ == '__main__':
    unittest.main()

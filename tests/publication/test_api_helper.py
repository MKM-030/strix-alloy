"""Exercise PowerShell against a tiny loopback HTTP fixture, never an LLM."""
import http.server
import json
import pathlib
import shutil
import subprocess
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PWSH = shutil.which('pwsh')

@unittest.skipUnless(PWSH, 'PowerShell 7 is required')
class ApiHelperTests(unittest.TestCase):
    def setUp(self):
        self.model = 'Qwen3.8-Flash-Next'
        self.content = 'OK'
        self.requests = []
        self.redirect = False
        owner = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def send_json(self, value):
                payload = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def do_GET(self):
                owner.requests.append(('GET', self.path))
                if owner.redirect:
                    self.send_response(302)
                    self.send_header('Location', 'http://127.0.0.1:9/unreachable')
                    self.end_headers()
                    return
                self.send_json({'data': [{'id': owner.model}]})
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append(('POST', body))
                self.send_json({'choices': [{'message': {'content': owner.content}}]})
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.base = f'http://127.0.0.1:{self.server.server_port}/v1'

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def invoke(self, backend='Projfix', base=None):
        return subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File',
            str(ROOT / 'app/test-backend.ps1'), '-Backend', backend,
            '-ApiBase', base or self.base, '-TimeoutSeconds', '5'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)

    def test_native_and_halogen_request_shapes(self):
        for backend, model in [('Projfix', 'Qwen3.8-Flash-Next'),
                               ('Halogen', 'halogen-qwen3.8-flash-next')]:
            with self.subTest(backend=backend):
                self.model = model
                result = self.invoke(backend)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(json.loads(result.stdout)['exact_ok'])
                body = self.requests[-1][1]
                self.assertEqual(body['model'], model)
                self.assertFalse(body['stream'])
                if backend == 'Halogen':
                    self.assertFalse(body['enable_thinking'])
                    self.assertEqual(body['drafter'], 'serial')
                    self.assertEqual(body['reasoning_effort'], 'none')
                else:
                    self.assertFalse(body['chat_template_kwargs']['enable_thinking'])

    def test_wrong_model_stops_before_chat(self):
        self.model = 'different-model'
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.requests, [('GET', '/v1/models')])

    def test_empty_or_nonstring_content_is_not_a_pass(self):
        for content in ('', None, 42, ['not plain answer text']):
            with self.subTest(content=content):
                self.content = content
                self.assertNotEqual(self.invoke().returncode, 0)

    def test_redirect_is_not_followed(self):
        self.redirect = True
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertEqual(self.requests, [('GET', '/v1/models')])

    def test_gufo_and_remote_or_credentialed_urls_refuse_before_http(self):
        self.assertEqual(self.invoke('GUFO').returncode, 2)
        for base in ('http://example.invalid/v1', 'http://user:secret@127.0.0.1/v1',
                     self.base + '?key=example', self.base + '#fragment'):
            with self.subTest(base=base):
                self.assertNotEqual(self.invoke(base=base).returncode, 0)
        self.assertEqual(self.requests, [])

if __name__ == '__main__':
    unittest.main()

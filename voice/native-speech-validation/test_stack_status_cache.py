import importlib.util
import json
import pathlib
import unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('review_stack_status', HERE / 'stack_status.py')
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class Response:
    status = 200
    def __init__(self, body): self.body = json.dumps(body).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return self.body[:limit]


class Opener:
    def __init__(self, body): self.body = body
    def open(self, request, timeout): return Response(self.body)


class CacheHealthTests(unittest.TestCase):
    def health(self, cache):
        with patch.object(status.urllib.request, 'build_opener', return_value=Opener({'prompt_cache': cache})):
            return status.health(8731)

    def test_reports_only_typed_cache_fields_from_live_health(self):
        cache = dict(mode=1, enabled=True, cap_mb=4096, bitwise_identical_to_cold=True,
                     token='do-not-report', hits=4, unused=['do-not-report'])
        result = self.health(cache)
        self.assertIn('prompt_cache', result)
        self.assertEqual(result['prompt_cache'], dict(mode=1, enabled=True, cap_mb=4096,
            bitwise_identical_to_cold=True))
        self.assertNotIn('do-not-report', json.dumps(result))

    def test_off_cache_is_reported_truthfully(self):
        result = self.health(dict(mode=0, enabled=False, cap_mb=0, bitwise_identical_to_cold=True))
        self.assertIn('prompt_cache', result)
        self.assertEqual(result['prompt_cache']['mode'], 0)
        self.assertFalse(result['prompt_cache']['enabled'])

    def test_malformed_fields_do_not_become_an_exact_cache(self):
        result = self.health(dict(mode=True, enabled='true', cap_mb='4096', bitwise_identical_to_cold=1))
        self.assertIn('prompt_cache', result)
        self.assertEqual(result['prompt_cache'], {})

    def test_absent_cache_remains_absent(self):
        self.assertNotIn('prompt_cache', self.health(None))


if __name__ == '__main__': unittest.main()

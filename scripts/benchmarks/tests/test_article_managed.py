"""Offline streamed article accounting and managed-runtime safety checks."""
import asyncio
import contextlib
import hashlib
import io
import json
import pathlib
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

BENCHMARKS = pathlib.Path(__file__).resolve().parents[1]
REPO = BENCHMARKS.parents[1]
sys.path.insert(0, str(BENCHMARKS))
sys.path.insert(0, str(REPO / 'server'))
import aiohttp
import host_frames


class ArticleManagedTests(unittest.TestCase):
    def run_fixture(self, *, altered_profile=False, reserve_gib=30, cross_reserve=False):
        posted = []
        with tempfile.TemporaryDirectory(dir=REPO / 'server/.local') as directory:
            work = pathlib.Path(directory)
            token = work / 'token.txt'
            token.write_text('fixture-token', encoding='ascii')
            (work / 'corpus.json').write_text(json.dumps([{'path': 'a.py', 'text': 'source'}]))
            profile = work / 'profile.json'
            profile.write_text(json.dumps({'engine': {'kind': 'native'}, 'minimum_reserve_gib': 18,
                'backend': {'identifier': 'gufo-flash-next', 'model': 'fixture-model', 'context': 65536}}))
            state = {'phase': 'ready', 'run_id': 'fixture-run', 'backend': 'gufo-flash-next',
                'context': 65536, 'port': 8840, 'minimum_reserve_gib': 18,
                'profile_sha256': 'wrong' if altered_profile else hashlib.sha256(profile.read_bytes()).hexdigest()}
            original_read = pathlib.Path.read_text

            def read_fixture(path, *args, **kwargs):
                if path == REPO / 'server/.local/current.json':
                    return json.dumps(state)
                return original_read(path, *args, **kwargs)

            class Tokenizer:
                @classmethod
                def from_file(cls, path):
                    return cls()
                def encode(self, text, **kwargs):
                    return types.SimpleNamespace(ids=[1] * max(1, len(text) // 4))
                def decode(self, values, **kwargs):
                    return 'code' * len(values)

            class Response:
                status = 200
                async def __aenter__(self):
                    return self
                async def __aexit__(self, *args):
                    pass
                async def json(self):
                    return {'backend': state['backend'], 'context': 65536, 'active_requests': 0}
                async def text(self):
                    return 'fixture'
                def close(self):
                    pass

            class Stream:
                async def iter_any(self):
                    if cross_reserve:
                        await asyncio.sleep(.01)
                    event = {'choices': [{'delta': {'content': '{"SERVICE_LABEL":"fixture"}'}}]}
                    yield ('data: ' + json.dumps(event) + '\n\n').encode()
                    event = {'choices': [{'delta': {}, 'finish_reason': 'stop'}],
                        'usage': {'prompt_tokens': 32768, 'completion_tokens': 100,
                            'prompt_tokens_per_second': 1000, 'completion_tokens_per_second': 40,
                            'draft_tokens': 60, 'draft_tokens_accepted': 30,
                            'gufo': {'prefill_ms': 32768, 'decode_ms': 2500, 'cache_hit': False}}}
                    yield ('data: ' + json.dumps(event) + '\n\ndata: [DONE]\n\n').encode()

            class Session:
                def __init__(self, **kwargs):
                    pass
                async def __aenter__(self):
                    return self
                async def __aexit__(self, *args):
                    pass
                def get(self, *args, **kwargs):
                    return Response()
                def post(self, url, *, json, **kwargs):
                    posted.append(json)
                    response = Response()
                    response.content = Stream()
                    return response

            argv = ['article_bench.py', '--work', str(work), '--backend', 'gufo',
                    '--context', '65536', '--fill', '32768', '--profile', str(profile),
                    '--token-file', str(token)]
            memory = {'available_bytes': reserve_gib * 1024**3,
                      'commit_headroom_bytes': 30 * 1024**3}
            frames = [memory, {**memory, 'available_bytes': 17 * 1024**3}, memory] if cross_reserve else None
            with patch.object(sys, 'argv', argv), patch.object(pathlib.Path, 'read_text', read_fixture), \
                 patch.dict(sys.modules, {'tokenizers': types.SimpleNamespace(Tokenizer=Tokenizer)}), \
                 patch.object(aiohttp, 'ClientSession', Session), \
                 patch.object(host_frames, 'frame', return_value=memory, side_effect=frames), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as ended:
                    runpy.run_path(str(BENCHMARKS / 'article_bench.py'), run_name='__main__')
            summary_path = work / 'gufo-c65536-p32768/summary.json'
            summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
            identity_path = work / 'gufo-c65536-p32768/identity.json'
            identity = json.loads(identity_path.read_text()) if identity_path.exists() else None
            samples_path = work / 'gufo-c65536-p32768/samples.jsonl'
            rows = [json.loads(line) for line in samples_path.read_text().splitlines()] if samples_path.exists() else []
            return ended.exception.code, posted, summary, identity, rows

    def test_streamed_accounting_and_profile_model(self):
        code, posted, summary, identity, rows = self.run_fixture()
        self.assertEqual(code, 0)
        self.assertEqual(len(posted), 6)
        self.assertTrue(all(body['model'] == 'fixture-model' for body in posted))
        self.assertEqual(identity['managed_run_id'], 'fixture-run')
        self.assertEqual(summary['decode_tps'], 40)
        self.assertEqual(summary['mtp_acceptance'], .5)
        self.assertEqual(summary['capped_outputs'], 0)
        self.assertEqual(rows[0]['observed_cache_state'], 'cold')
        self.assertEqual(rows[0]['output_tokens'], 100)
        self.assertEqual(rows[0]['host_memory']['observed_minimum']['available_bytes'], 30 * 1024**3)

    def test_profile_or_memory_refusal_happens_before_inference(self):
        for kwargs in ({'altered_profile': True}, {'reserve_gib': 17}):
            with self.subTest(**kwargs):
                code, posted, summary, _, _ = self.run_fixture(**kwargs)
                self.assertEqual(code, 2)
                self.assertEqual(posted, [])
                self.assertFalse(summary['passed_execution'])

    def test_sampled_memory_breach_rejects_completed_response(self):
        code, posted, summary, _, rows = self.run_fixture(cross_reserve=True)
        self.assertEqual(code, 2)
        self.assertEqual(len(posted), 1)
        self.assertEqual(rows, [])
        self.assertIn('Memory reserve crossed during request', summary['error'])


if __name__ == '__main__':
    unittest.main()

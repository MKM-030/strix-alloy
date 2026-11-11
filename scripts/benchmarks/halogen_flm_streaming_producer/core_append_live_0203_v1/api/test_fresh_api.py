"""Real 0.20.3 API functions with fake native streams; no runtime/device calls."""
import asyncio
import copy
import hashlib
from pathlib import Path
import struct
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import api_stream_feedback as stream
import api_observation as identity
import native_api_fixture as fixture
import token_feedback


class Publisher:
    def __init__(self): self.events = []
    def begin(self, packet, ids):
        self.events.append(('begin', packet, ids)); return True
    def feedback(self, packet):
        self.events.append(('feedback', packet)); return True


class FreshApiTests(unittest.TestCase):
    def allowed(self):
        h = hashlib.sha256(token_feedback.HASH_DOMAIN)
        h.update(struct.pack('<2i', 100, 200))
        return {(2, h.hexdigest())}

    def test_actual_generate_yields_and_GEN_bytes_unchanged_with_authority_observer(self):
        async def run(enabled):
            namespace, records, publisher = fixture.original_namespace(), [], Publisher()
            stream.install(namespace, fixture.SOURCE, enabled=enabled, publish=records.append,
                           publisher=publisher, allowed_prompts=self.allowed())
            engine = await fixture.engine_for(namespace, [b'T 41 6574\n', b'T 41 248060\n',
                b'T 41 248046\n', b'D 41 stop 2 3 1.0 3.0\n'])
            rows = [row async for row in engine.generate([100, 200], 128, [248046], drafter=1)]
            return rows, engine.w.lines, records, publisher.events
        stock, observed = asyncio.run(run(False)), asyncio.run(run(True))
        self.assertEqual(stock[:2], observed[:2])
        record = observed[2][0]
        self.assertEqual(record['schema'], 'halogen0203.streaming-native-ID-observer.v1')
        self.assertEqual(record['api_sha256'], stream.UPSTREAM_SHA256)
        self.assertEqual(record['begin']['engine_sha256'], token_feedback.ENGINE_SHA256)
        self.assertEqual(record['token_ids'], [6574, 248060, 248046])
        self.assertTrue(record['terminal']['complete_native_stream'])
        self.assertFalse(record['sidecar_retired'])
        self.assertEqual([row[0] for row in observed[3]], ['begin', 'feedback', 'feedback', 'feedback', 'feedback'])

    def test_unqualified_prompt_stays_native_without_begin_or_capture(self):
        async def run():
            namespace, records, publisher = fixture.original_namespace(), [], Publisher()
            stream.install(namespace, fixture.SOURCE, enabled=True, publish=records.append,
                           publisher=publisher, allowed_prompts={(8192, 'a' * 64)})
            engine = await fixture.engine_for(namespace, [b'T 41 7\n', b'D 41 stop 2 1 1.0 3.0\n'])
            rows = [row async for row in engine.generate([100, 200], 128, [], drafter=1)]
            return rows, records, publisher.events
        rows, records, events = asyncio.run(run())
        self.assertTrue(rows)
        self.assertEqual(records, [])
        self.assertEqual(events, [])

    def test_early_close_retires_authority_without_inventing_done(self):
        async def run():
            namespace, records, publisher = fixture.original_namespace(), [], Publisher()
            observer = stream.install(namespace, fixture.SOURCE, enabled=True, publish=records.append,
                publisher=publisher, allowed_prompts=self.allowed())
            engine = await fixture.engine_for(namespace, [b'T 41 6574\n', b'T 41 7\n'])
            generator = engine.generate([100, 200], 128, [], drafter=1)
            await anext(generator); await generator.aclose()
            return observer, records
        observer, records = asyncio.run(run())
        self.assertEqual(observer.active_count, 0)
        self.assertEqual(records[0]['token_ids'], [6574])
        self.assertEqual(records[0]['terminal']['kind'], 'cancelled')
        self.assertFalse(records[0]['terminal']['complete_native_stream'])

    def test_source_or_live_method_drift_rejected_before_mutation(self):
        namespace = fixture.original_namespace(); original = namespace['Engine'].generate
        with self.assertRaises(ValueError):
            stream.install(namespace, fixture.SOURCE + b'\n', enabled=True,
                publisher=Publisher(), allowed_prompts=self.allowed())
        self.assertIs(namespace['Engine'].generate, original)
        async def other(self): yield None
        namespace['Engine'].generate = other
        with self.assertRaises(ValueError):
            stream.install(namespace, fixture.SOURCE, enabled=True,
                publisher=Publisher(), allowed_prompts=self.allowed())
        self.assertIs(namespace['Engine'].generate, other)

    def test_private_D_identity_wraps_exact_new_parser_without_changing_other_fields(self):
        namespace = fixture.original_namespace()
        compiled = compile(fixture.SOURCE, identity.UPSTREAM, 'exec', dont_inherit=True)
        code = next(c for c in compiled.co_consts if isinstance(c, types.CodeType) and c.co_name == 'timings_of')
        namespace['timings_of'] = types.FunctionType(code, namespace)
        namespace['timings_of'].__defaults__ = (None,)
        parts = ['D', '41', 'stop', '2', '3', '1.0', '3.0']
        before = namespace['Engine']._done_dict(parts)
        self.assertTrue(identity.install(namespace, fixture.SOURCE, enabled=True))
        after = namespace['Engine']._done_dict(parts)
        self.assertEqual(after.pop(identity.PRIVATE_KEY), 41)
        self.assertEqual(before, after)


if __name__ == '__main__': unittest.main()

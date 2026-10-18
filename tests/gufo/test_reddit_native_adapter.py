"""Focused offline contracts for the private Reddit adapter."""
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.gufo_control import reddit_native_run as adapter


class RedditAdapterContract(unittest.TestCase):
    def test_generator_parity_and_serialization(self):
        upstream = adapter.upstream()
        text = adapter.turn_text(2048, 1.42, 'prose', 131072, 2)
        self.assertEqual(text, upstream.turn_prompt(2048, 1.42, task='prose', depth=131072,
                                                    repetition=0, attempt=2))
        messages = [dict(role='user', content=text)]
        request, body = adapter.request_body(messages, 128, stream=True)
        self.assertEqual(request['messages'], messages)
        self.assertNotIn('cache_prompt', request)
        self.assertNotIn('seed', request)
        self.assertEqual(adapter.decode_body(body), request)

    def test_counts_fail_closed(self):
        self.assertEqual(adapter.count_errors(dict(cached_prompt_tokens=131072,
            new_prefill_tokens=2048, completion_tokens=128,
            logical_prompt_tokens=133120,
            engine_decode_ms=1000, engine_prefill_ms=100,
            engine_tg_tokens_per_second=128), 131072, 2048, 128), [])
        self.assertIn('cache_outside_tolerance', adapter.count_errors(dict(
            cached_prompt_tokens=0, new_prefill_tokens=133120, completion_tokens=128,
            logical_prompt_tokens=133120,
            engine_decode_ms=1000, engine_prefill_ms=100,
            engine_tg_tokens_per_second=128), 131072, 2048, 128))

    def test_fixed_argv_and_guard_constants(self):
        argv = adapter.fixed_argv('secret')
        self.assertEqual(argv[argv.index('--context')+1], '133760')
        self.assertEqual(argv[argv.index('--draft-tokens')+1], '7')
        self.assertEqual(argv[argv.index('--mtp-policy')+1], 'survival')
        self.assertEqual(argv[argv.index('--mtp-draft-vocab')+1], 'latin')
        self.assertIn('--prompt-lookup', argv)
        self.assertEqual(adapter.REQUEST_LIMIT, 4 << 20)
        self.assertEqual(adapter.MAX_CALLS, 15)

    def test_fresh_admission_and_runtime_floors(self):
        policy = adapter.Policy('mixed')
        profile = policy.profile_from_manifest(dict(profile=adapter.PROFILE,
            binding=dict(table='mixed')))
        self.assertEqual(profile.envelope['gpu_peak_bytes'], 78*adapter.GIB)
        self.assertEqual(profile.envelope['host_peak_bytes'], 12*adapter.GIB)
        base = SimpleNamespace(identity=('bound',), available_min=52*adapter.GIB,
            committed_max=16*adapter.GIB, gpu_max=(0, 0, 0), last_end=0)
        snapshot = dict(available_physical_bytes=44*adapter.GIB,
                        commit_headroom_bytes=103*adapter.GIB,
                        host_committed_bytes=16*adapter.GIB,
                        adapter_dedicated_bytes=0, adapter_shared_bytes=0,
                        adapter_total_committed_bytes=0)
        frame = SimpleNamespace(snapshot=snapshot, query_start=1)
        with (patch.object(adapter, '_base_valid', return_value=True),
              patch.object(adapter, '_frame_reasons', return_value=[]),
              patch.object(adapter, '_identity', return_value=('bound',))):
            self.assertEqual(policy.admission_reasons(profile, base, frame,
                now=2, now_utc=None), [])
            snapshot['available_physical_bytes'] = 43*adapter.GIB
            self.assertIn('scenario_fresh_physical_below_43_564664300_gib',
                policy.admission_reasons(profile, base, frame, now=2, now_utc=None))
            snapshot['available_physical_bytes'] = 44*adapter.GIB
            snapshot['commit_headroom_bytes'] = 100*adapter.GIB
            self.assertIn('scenario_fresh_commit_below_102_gib',
                policy.admission_reasons(profile, base, frame, now=2, now_utc=None))
            snapshot['available_physical_bytes'] = 23*adapter.GIB
            self.assertIn('runtime_physical_floor', policy.frame_numeric_reasons(
                profile, base, frame, now=2, now_utc=None))

    def test_recheck_uses_pinned_stamps_without_full_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root/'binary.bin'
            review = root/'review.json'
            baseline = root/'baseline.jsonl'
            for path in (artifact, review, baseline):
                path.write_bytes(b'bound')
            store = adapter.Store('mixed')
            store.EVIDENCE = root
            manifest = dict(binding=dict(table='mixed'),
                artifact_stamps=[adapter.operator_store.stamp(artifact)],
                review_sha256=adapter.prior.file_digest(review),
                operator=dict(fresh_baseline_log=str(baseline),
                    fresh_baseline_log_sha256=adapter.prior.file_digest(baseline)))
            store.cached_manifest = manifest
            with (patch.object(adapter, 'REVIEW', review),
                  patch.object(adapter, 'static_binding', side_effect=AssertionError('full validation repeated')),
                  patch.object(adapter, 'source_identity', return_value=None, create=True)):
                store.recheck_static(manifest)
                artifact.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'bound_artifact_stamp_changed'):
                    store.recheck_static(manifest)


if __name__ == '__main__':
    unittest.main()

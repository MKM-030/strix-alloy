"""Stage-specific counter and output checks use native response field shapes."""
from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from gufo_control import mtp_stage_http, smoke_http
from gufo_control.mtp_stage_http import validate_response


def response():
    return dict(success=True, post_attempted=True, status=200,
        finish_reason='stop', visible_answer=(
            'A backup lets you restore a saved copy after accidental deletion.\n'
            'Mit einem Backup kannst du eine gespeicherte Kopie nach versehentlichem Loeschen wiederherstellen.'),
        reasoning_content='', tool_calls=[], observed_models=['gufo-flash-next'],
        usage=dict(prompt_tokens=100, completion_tokens=35, total_tokens=135,
            cached_tokens=0, prompt_tokens_details={'cached_tokens': 0},
            draft_tokens=12, draft_tokens_accepted=8,
            gufo=dict(prefill_tokens=100, cache_hit=False, cache_disk_hit=False,
            cache_restore_bytes=0, cache_disk_queued_bytes=0,
            cache_common_prefix_tokens=0, cache_shared_bytes=0,
            cache_shared_prefix_snapshots=0, cache_shared_prefix_bytes=0,
                physical_execution_width=1, requested_logical_concurrency=1,
                resident_requests_at_admission=1)),
        timings=dict(prompt_n=100, cache_n=0, predicted_n=35,
                     draft_n=12, draft_n_accepted=8),
        metrics={'mtp_acceptance': 8/12})


class ResponseTests(unittest.TestCase):
    def test_positive_native_counts_and_omission_provenance(self):
        value = validate_response(response())
        self.assertEqual(value['state'], 'semantic_review_pending')
        self.assertEqual(value['lookup_source'], 'omitted_when_zero_in_pinned_emitter')
        self.assertEqual(value['draft_tokens'], 12)
        self.assertEqual(value['draft_tokens_accepted'], 8)

    def test_rejects_visible_control_tags(self):
        for first_line in ('<think>A backup lets you restore a saved copy.</think>',
                           '<analysis>A backup lets you restore a saved copy.</analysis>'):
            with self.subTest(first_line=first_line):
                value = response()
                value['visible_answer'] = first_line + '\n' + value['visible_answer'].split('\n')[1]
                self.assertEqual(validate_response(value)['state'], 'failed')

    def test_rejects_single_underscore_emphasis(self):
        for first_line in ('_A backup lets you restore a saved copy._',
                           'A backup restores a _saved_copy_.'):
            with self.subTest(first_line=first_line):
                value = response()
                value['visible_answer'] = first_line + '\n' + value['visible_answer'].split('\n')[1]
                self.assertEqual(validate_response(value)['state'], 'failed')

    def test_rejects_counter_cache_model_and_output_failures(self):
        changes = {
            'missing_draft': lambda r: r['usage'].pop('draft_tokens'),
            'zero_draft': lambda r: r['usage'].update(draft_tokens=0),
            'bool_draft': lambda r: r['timings'].update(draft_n=True),
            'inconsistent': lambda r: r['timings'].update(draft_n_accepted=7),
            'one_lookup': lambda r: r['timings'].update(lookup_n=0),
            'nonzero_lookup': lambda r: r['timings'].update(lookup_n=1, lookup_n_accepted=0),
            'cache_hit': lambda r: r['usage']['gufo'].update(cache_hit=True),
            'cached': lambda r: r['usage']['prompt_tokens_details'].update(cached_tokens=1),
            'wrong_model': lambda r: r.update(observed_models=['other']),
            'missing_model': lambda r: r.update(observed_models=[]),
            'truncated': lambda r: r.update(finish_reason='length'),
            'reasoning': lambda r: r.update(reasoning_content='hidden'),
            'tools': lambda r: r.update(tool_calls=[{'x': 1}]),
            'third_line': lambda r: r.update(visible_answer=r['visible_answer']+'\nextra'),
            'markdown': lambda r: r.update(visible_answer='- '+r['visible_answer']),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                value = response(); change(value)
                self.assertEqual(validate_response(value)['state'], 'failed')

    def test_one_post_and_raw_artifact_with_semantics_pending(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
                mtp_stage_http.benchmark_suite, '_ready', return_value=None), patch.object(
                mtp_stage_http.benchmark_http, 'request_once', return_value=response()) as send:
            now = time.monotonic()
            task = mtp_stage_http.start_stage(evidence_dir=Path(temp), api_key='private',
                startup_deadline=now+480, lifetime_deadline=now+600)
            self.assertTrue(task.done.wait(5))
            self.assertTrue(task.result['success'], task.result)
            self.assertEqual(task.result['semantic_status'], 'semantic_review_pending')
            self.assertEqual(send.call_count, 1)
            self.assertTrue((Path(temp)/'request-000.json').exists())

    def test_readiness_failure_never_posts(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
                mtp_stage_http.benchmark_suite, '_ready', side_effect=smoke_http.SmokeError('cancelled')), patch.object(
                mtp_stage_http.benchmark_http, 'request_once') as send:
            now = time.monotonic()
            task = mtp_stage_http.start_stage(evidence_dir=Path(temp), api_key='private',
                startup_deadline=now+480, lifetime_deadline=now+600, cancel=threading.Event())
            self.assertTrue(task.done.wait(5))
            self.assertFalse(task.result['success'])
            send.assert_not_called()
            self.assertFalse((Path(temp)/'request-000.json').exists())

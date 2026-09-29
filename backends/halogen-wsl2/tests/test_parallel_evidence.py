import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class EvidenceTests(unittest.TestCase):
    def test_real_completed_pair_is_recounted(self):
        data = json.loads((ROOT/'docs/benchmarks/steady-dual-20260925.json').read_bytes())
        summary = self.validator()(data)
        self.assertTrue(summary['passed'])
        self.assertEqual(summary['input_tokens'], 780124)
        self.assertEqual(summary['output_tokens'], 6144)
        self.assertEqual(summary['measured_phases']['baseline']['aggregate_tokens_per_second'], 66.55)
        self.assertEqual(summary['measured_phases']['pair']['aggregate_tokens_per_second'], 50.9)

    def test_host_freeze_is_not_a_throughput_or_safe_cleanup_result(self):
        data = json.loads((ROOT/'docs/benchmarks/triple260k-freeze-20260925.json').read_bytes())
        self.assertFalse(data['qualified'])
        self.assertFalse(data['ready_observed'])
        self.assertFalse(data['clean_container_stop_verified'])
        self.assertEqual(data['requests_started'], 0)
        self.assertIsNone(data['prefill_tokens_per_second'])
        self.assertIsNone(data['decode_tokens_per_second'])
        values = [sample['available_bytes'] for sample in data['samples']]
        values += [failure['minimum_available_bytes'] for failure in data['failures']]
        self.assertEqual(min(values), data['minimum_reported_windows_available_bytes'])
        self.assertEqual(min(values), 651264)
        self.assertEqual(data['failures'][-1]['reason'], 'docker_stop_timeout_30s')

    def validator(self):
        path = ROOT / 'scripts/verify-parallel-evidence.py'
        self.assertTrue(path.exists(), 'independent evidence verifier missing')
        spec = importlib.util.spec_from_file_location('verify_parallel',path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.verify

    def test_real_aborted_run_counts_but_no_qualified_rate(self):
        data = json.loads((ROOT/'docs/benchmarks/steady-first-aborted-20260925.json').read_bytes())
        check = self.validator()
        summary = check(data)
        self.assertFalse(summary['passed'])
        self.assertEqual(summary['output_tokens'],2048)
        self.assertEqual(summary['measured_phases'],{})
        broken = copy.deepcopy(data)
        next(iter(broken['responses'].values()))['usage']['completion_tokens'] += 1
        with self.assertRaisesRegex(ValueError,'count'):
            check(broken)

    def test_memory_summary_is_recounted_from_samples(self):
        data = json.loads((ROOT/'docs/benchmarks/steady-first-aborted-20260925.json').read_bytes())
        check = self.validator()
        for key in ('minimum_windows_available_bytes','sampled_gpu_adapter_peak'):
            broken = copy.deepcopy(data)
            if key == 'minimum_windows_available_bytes': broken[key] += 1
            else: broken[key]['combinedBytes'] += 1
            with self.assertRaisesRegex(ValueError,'memory'):
                check(broken)

    def test_common_window_native_counts_and_boundary(self):
        check = self.validator()
        label = 'STEADY-BASELINE-SESSION-01'
        def event(t,parts,**extra):
            return dict(pid=1,monotonic_ns=int(t*1e9),parts=parts,**extra)
        raw = ('C 0 0 0 0 0 0 0 0 0 0.0 0.0 0.0 0.0 0 0 0.0 '
               '0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.0 0 0 0 '
               '0 0.0 0 0 262144 524288 1 0 0 0 0').split()
        events = [event(9,['G','3','260000','2048','1'],label=label),
                  event(10,['T','3','101']),event(11,raw),event(20,['T','3','102']),
                  event(25,['T','3','103']),event(35,['T','3','104']),
                  event(40,['D','3','length','260000','4','1000','30000','1','0','0','0'])]
        phase = dict(classification='measured',labels=[label],start_ns=15_000_000_000,end_ns=35_000_000_000,
                     duration_seconds=20,counts={label:3},per_session_tokens_per_second={label:.15},
                     aggregate_tokens_per_second=.15,pool=dict(cache_event_ns=11_000_000_000))
        data = dict(passed=True,common_window_seconds=20,native_events=events,
                    terminal=dict(running=False,pid=0,stopSucceeded=True,oomKilled=False),
                    responses={label:dict(completed=True,marker_present=True,content=label,
                                          usage=dict(prompt_tokens=260000,completion_tokens=4),
                                          timings=dict(prompt_ms=1000,predicted_ms=30000,cache_n=0))},
                    phases=dict(baseline=phase))
        self.assertEqual(check(data)['measured_phases']['baseline']['aggregate_tokens_per_second'],.15)
        for mutation in ('count','early_done','pool'):
            broken = copy.deepcopy(data)
            if mutation == 'count': broken['phases']['baseline']['counts'][label]=4
            elif mutation == 'early_done': broken['native_events'][-1]['monotonic_ns']=35_000_000_000
            else: broken['native_events'][2]['parts'][46]='0'
            with self.assertRaises(ValueError): check(broken)


if __name__ == '__main__':
    unittest.main()

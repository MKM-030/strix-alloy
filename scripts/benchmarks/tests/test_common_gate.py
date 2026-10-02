import asyncio
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from article_metrics import benchmark_input_sizes, calibrated_prompt, cold_sample, memory_snapshot, verified_prompt, checked_profile_hash
import hashlib
import tempfile


class CommonGateTests(unittest.TestCase):
    def test_cold_benchmark_requires_exact_managed_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = pathlib.Path(directory) / 'profile.json'
            profile.write_bytes(b'{"minimum_reserve_gib":18}')
            expected = hashlib.sha256(profile.read_bytes()).hexdigest()
            self.assertEqual(checked_profile_hash({'profile_sha256': expected}, profile), expected)
            with self.assertRaises(ValueError):
                checked_profile_hash({'profile_sha256': 'other'}, profile)
            with self.assertRaises(ValueError):
                checked_profile_hash({}, profile)
    def test_exact_sizes_and_capacity(self):
        self.assertEqual(benchmark_input_sizes([512, 2048, 8192, 16384], 32768),
                         (512, 2048, 8192, 16384))
        with self.assertRaises(ValueError):
            benchmark_input_sizes([16384], 16400)

    def test_observed_calibration_and_failure(self):
        async def measure(text):
            return len(text.split()) + 3
        prompt = asyncio.run(calibrated_prompt('base text', 512, measure))
        self.assertEqual(asyncio.run(measure(prompt)), 512)
        async def impossible(text):
            return 511 if text == 'base text' else 513
        with self.assertRaises(ValueError):
            asyncio.run(calibrated_prompt('base text', 512, impossible))

    def test_cold_accounting_rejects_cache_clamp_and_missing_rates(self):
        value={'usage':{'prompt_tokens':512,'completion_tokens':128},
               'timings':{'prompt_n':512,'predicted_n':128,'cache_n':0,
                          'prompt_per_second':120,'predicted_per_second':22},
               'choices':[{'message':{'content':'example'},'finish_reason':'length'}]}
        row=cold_sample(value,512,128)
        self.assertEqual(row['output_sha256'], __import__('hashlib').sha256(b'example').hexdigest())
        self.assertIsNone(row['acceptance'])
        value['timings']['cache_n']=1
        with self.assertRaises(ValueError): cold_sample(value,512,128)
        value['timings']['cache_n']=0
        value['usage']['gufo']={'cache_hit':True,'cache_disk_hit':True}
        with self.assertRaises(ValueError): cold_sample(value,512,128)
        value['usage'].pop('gufo')
        value['timings']['max_tokens_clamped_from']=256
        with self.assertRaises(ValueError): cold_sample(value,512,128)
        value['timings'].pop('max_tokens_clamped_from')
        value['usage']['cached_tokens']=1
        with self.assertRaises(ValueError): cold_sample(value,512,128)

    def test_memory_is_controller_telemetry_not_gpu_allocation(self):
        state={'memory':{'available_bytes':12,'commit_headroom_bytes':34}}
        self.assertEqual(memory_snapshot(state),{'available_bytes':12,'commit_headroom_bytes':34})
        with self.assertRaises(ValueError): memory_snapshot({'memory':{'available_bytes':-1}})

    def test_one_token_prefill_does_not_require_decode_rate(self):
        value={'usage':{'prompt_tokens':512,'completion_tokens':1},
               'timings':{'prompt_per_second':50,'predicted_per_second':0},
               'choices':[{'message':{'content':'x'},'finish_reason':'length'}]}
        self.assertEqual(cold_sample(value,512,1)['usage']['completion_tokens'],1)

    def test_optional_input_manifest_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'prompt-512-prose.txt'
            path.write_text('river prose',encoding='utf-8')
            manifest={'prompts':{'512':{'file':path.name,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}}
            self.assertEqual(verified_prompt(path,512,manifest),'river prose')
            path.write_text('river changed',encoding='utf-8')
            with self.assertRaises(ValueError):verified_prompt(path,512,manifest)

if __name__=='__main__': unittest.main()

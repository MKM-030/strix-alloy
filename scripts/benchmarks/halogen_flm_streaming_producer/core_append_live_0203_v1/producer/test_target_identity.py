"""Fresh target admission without a producer thread, DLL or accelerator."""
import copy
import unittest

from service import ProducerWorker, ENGINE, TOKENIZER
from actor import prefix_hash


class TargetIdentityTests(unittest.TestCase):
    def test_only_fresh_actual_target_events_are_admitted(self):
        prompt = list(range(512))
        event = dict(schema='halogen0203.authoritative-token-feedback.v1', kind='begin',
            source='native_T', engine_sha256=ENGINE, tokenizer_sha256=TOKENIZER,
            request_id=4, n_prompt=512, request_epoch='a' * 32, nonce=7,
            generated_count=0, prefix_count=512, prefix_sha256=prefix_hash(prompt),
            current_token=-1, sequence=1, token_ids=[], prompt_ids=prompt)
        worker = ProducerWorker(lambda: self.fail('No backend construction'), lambda packet: None)
        key, kind, sequence = worker._validated_event(event)
        self.assertEqual((key.prompt_count, kind, sequence), (512, 'begin', 1))
        for field, bad in [('engine_sha256', '7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577'),
                           ('schema', 'halogen0201.authoritative-token-feedback.v1'),
                           ('source', 'recorded_oracle'), ('tokenizer_sha256', '0' * 64)]:
            altered = copy.deepcopy(event); altered[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError): worker._validated_event(altered)
        self.assertIsNone(worker.thread)
        self.assertIsNone(worker.backend)


if __name__ == '__main__': unittest.main()

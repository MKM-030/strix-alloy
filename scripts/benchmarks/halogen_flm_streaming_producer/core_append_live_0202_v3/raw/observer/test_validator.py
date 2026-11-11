"""Pure offline fixtures. These tests make no runtime/performance claim."""
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from validate_capture import (BINDING, CAPTURE_BYTES, FIELDS, HEADER, MAGIC, RECORD,
                              UnsupportedCapture, bound_pcs, parse_epoch, read_capture,
                              response_counts, validate)
from validate_cohort import validate_cohort

PCS = {1: 0x101, 2: 0x201, 3: 0x301, 4: 0x401}
EPOCH = 0x0202000000000001


def bits(value):
    return struct.unpack('<Q', struct.pack('<d', value))[0]


def fixture(generated=128, request_id=17, native_slot=1, offset=0, prompt=8192):
    def event(site, native, before, start, obj, count=0):
        return dict(site=site, caller_rva=PCS[site], caller_stack=4096,
                    saved_r14=obj if site > 2 else 1, saved_r15=obj if site < 3 else 1,
                    saved_rbx=start if site == 4 else 0, object=obj,
                    request_id=request_id, native=native + offset,
                    native_start=start + offset, tid=91, raw_before=before + offset,
                    raw_after=before + offset + 10, status=0, prompt=prompt,
                    generated=count, prefill_accum_bits=0, published_prefill_bits=0,
                    native_slot=native_slot)

    events = [event(1, 1000000, 1000000, 1000000, 11),
              event(2, 3000000, 3000000, 1000000, 11),
              event(3, 4000000, 4000000, 4000000, 22, 1),
              event(4, 7000000, 7000000, 4000000, 33, generated)]
    events[-1]['saved_rbx'] += offset
    events[-1]['published_prefill_bits'] = bits(2.0)
    events[-2]['published_prefill_bits'] = bits(2.0)
    response = dict(id='cmpl-fixture-' + str(request_id),
                    usage=dict(prompt_tokens=prompt, completion_tokens=generated,
                               total_tokens=prompt + generated),
                    timings=dict(prompt_n=prompt, predicted_n=generated, cache_n=0,
                                 prompt_ms=2.0, predicted_ms=3.0,
                                 raw_native_request_id=request_id))
    return events, response


def packed(events, ordinal=0, flags=0, version=3, epoch=EPOCH):
    rows = b''.join(RECORD.pack(*(event[key] for key in FIELDS)) for event in events)
    return (HEADER.pack(MAGIC, version, len(events), flags, 1, ordinal, 4, epoch)
            + rows + bytes((64 - len(events)) * RECORD.size))


class CaptureTests(unittest.TestCase):
    def test_actual_generated_counts_and_cap_are_distinct(self):
        for actual in (2, 37, 128, 260):
            with self.subTest(actual=actual):
                events, response = fixture(actual)
                report = validate(events, response, PCS, dict(max_tokens=512))
                self.assertEqual(report['generated_end'], actual)
                self.assertEqual(report['generated_delta'], actual - 1)
                self.assertEqual(report['decode_numerator'], actual)
                self.assertEqual(report['output_cap'], 512)
                self.assertEqual(report['decode_native_tps'], actual * 1e9 / 3000000)
                self.assertEqual(report['native_slot'], 1)
                self.assertEqual(report['request_id'], 17)

    def test_general_prompt_lengths_and_zero_slot(self):
        for prompt in (39, 8192, 16384):
            events, response = fixture(37, native_slot=0, prompt=prompt)
            self.assertEqual(validate(events, response, PCS)['prompt'], prompt)

    def test_causal_identity_is_mandatory(self):
        for value in (None, True, '17', 0, -17, 0x8000000000000000, 18):
            events, response = fixture()
            response['timings']['raw_native_request_id'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(events, response, PCS)

    def test_mixed_identity_and_slot_fail(self):
        for key, value in (('request_id', 18), ('native_slot', 0), ('native_slot', 2),
                           ('native_slot', -1)):
            events, response = fixture()
            events[-1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate(events, response, PCS)

    def test_phase_and_register_rejections(self):
        mutations = [('status', 1), ('caller_rva', 123), ('saved_rbx', 123),
                     ('native_start', 123), ('published_prefill_bits', 0),
                     ('generated', 1), ('raw_after', 0), ('prompt', 1)]
        for key, value in mutations:
            events, response = fixture()
            events[-1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(events, response, PCS)

    def test_missing_duplicate_nested_or_reordered_phases_fail(self):
        events, response = fixture()
        for bad in (events[:-1], events + [events[-1]], events[:1] + events, events[1:]):
            with self.assertRaises(ValueError):
                validate(bad, response, PCS)
        events[2]['raw_before'] = 1
        with self.assertRaises(ValueError):
            validate(events, response, PCS)

    def test_multiple_outer_prefill_pairs(self):
        events, response = fixture()
        begin = events[0].copy()
        end = events[1].copy()
        begin.update(native=3100000, native_start=3100000,
                     raw_before=3100000, raw_after=3100010)
        end.update(native=3500000, native_start=3100000,
                   raw_before=3500000, raw_after=3500010)
        begin['prefill_accum_bits'] = end['prefill_accum_bits'] = bits(2.0)
        events = events[:2] + [begin, end] + events[2:]
        events[-1]['published_prefill_bits'] = bits(2.4)
        events[-2]['published_prefill_bits'] = bits(2.4)
        response['timings']['prompt_ms'] = 2.4
        self.assertEqual(validate(events, response, PCS)['prefill_pairs'], 2)

    def test_response_actual_counts_and_native_phases_must_agree(self):
        for where, key, value in (('usage', 'completion_tokens', 37),
                                  ('usage', 'prompt_tokens', 9),
                                  ('usage', 'total_tokens', 1),
                                  ('timings', 'predicted_n', 37),
                                  ('timings', 'prompt_n', 9),
                                  ('timings', 'predicted_ms', 4.0),
                                  ('timings', 'prompt_ms', float('nan'))):
            events, response = fixture()
            response[where][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(events, response, PCS)

    def test_cache_aware_processed_numerator_and_optional_cold_gate(self):
        events, response = fixture()
        response['timings'].update(cache_n=4096, prompt_n=4096)
        report = validate(events, response, PCS)
        self.assertEqual(report['prefill_native_tps'], 4096 * 1e9 / 2000000)
        self.assertEqual(report['cached_prompt'], 4096)
        with self.assertRaises(ValueError):
            validate(events, response, PCS, require_cold=True)

    def test_unsupported_native_endpoint_scopes(self):
        for actual in (0, 1):
            events, response = fixture(actual)
            with self.subTest(actual=actual), self.assertRaisesRegex(UnsupportedCapture, 'below 2'):
                validate(events, response, PCS)
        events, response = fixture()
        response['timings'].update(cache_n=8192, prompt_n=0)
        with self.assertRaisesRegex(UnsupportedCapture, 'zero processed'):
            validate(events, response, PCS)

    def test_output_cap_and_nonstreaming_scope(self):
        _, response = fixture()
        for request in (dict(max_tokens=1), dict(max_tokens=True), dict(),
                        dict(max_tokens=512, max_output_tokens=512),
                        dict(max_tokens=512, stream=True)):
            with self.subTest(request=request), self.assertRaises(ValueError):
                response_counts(response, request)

    def test_binary_format_and_fail_closed_flags(self):
        events, _ = fixture()
        data = packed(events)
        self.assertEqual(RECORD.size, 136)
        self.assertEqual(len(data), CAPTURE_BYTES)
        self.assertEqual(CAPTURE_BYTES, 8768)
        self.assertEqual(read_capture(data, 0, EPOCH), events)
        for invalid in (b'', data[:-1], data + b'x', packed(events, flags=1),
                        packed(events, flags=2), packed(events, flags=4),
                        packed(events, version=2), packed(events, ordinal=4), packed(events, epoch=0)):
            with self.assertRaises(ValueError):
                read_capture(invalid)
        with self.assertRaises(ValueError):
            read_capture(data, 1)
        with self.assertRaises(ValueError):
            read_capture(data, 0, EPOCH + 1)

    def test_epoch_parser(self):
        self.assertEqual(parse_epoch(f'{EPOCH:016x}'), EPOCH)
        for invalid in ('0', '0000000000000000', '020200000000000A', '0x0202000000000001', 1):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_epoch(invalid)

    def test_fresh_binding_is_available(self):
        self.assertEqual(set(bound_pcs()), set(PCS))


class CohortTests(unittest.TestCase):
    def make_cohort(self, folder):
        request_file = folder / 'request.json'
        request_data = b'{"prompt":"fixture","max_tokens":512,"stream":false}'
        request_file.write_bytes(request_data)
        prefix = folder / 'capture'
        responses = []
        bound = bound_pcs()
        for ordinal, actual in enumerate((2, 37, 128, 260)):
            events, response = fixture(actual, 17 + ordinal,
                                       native_slot=ordinal % 2, offset=ordinal * 10000000)
            for event in events:
                event['caller_rva'] = bound[event['site']]
            Path(str(prefix) + f'-{EPOCH:016x}-{ordinal}.bin').write_bytes(packed(events, ordinal))
            response_file = folder / f'response-{ordinal}.json'
            response_file.write_text(json.dumps(response), encoding='utf-8')
            responses.append(response_file)
        return prefix, responses, request_file

    def test_cohort_hashes_actual_counts_and_warmup(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix, responses, request_file = self.make_cohort(Path(temporary))
            report = validate_cohort(prefix, responses, request_file, EPOCH, prefix.parent / 'arm')
            self.assertTrue(report['valid'])
            self.assertEqual(report['measured_repetitions'], 3)
            self.assertEqual([row['decode_numerator'] for row in report['samples']], [2, 37, 128, 260])
            self.assertEqual(report['samples'][0]['phase'], 'warmup_excluded')
            self.assertEqual(report['request_sha256'], hashlib.sha256(request_file.read_bytes()).hexdigest())
            self.assertEqual(report['binding_sha256'], hashlib.sha256(BINDING.read_bytes()).hexdigest())
            self.assertEqual(report['samples'][2]['response_sha256'],
                             hashlib.sha256(responses[2].read_bytes()).hexdigest())
            expected = (37 + 128 + 260) * 1e9 / 3000000 / 3
            self.assertEqual(report['arithmetic_means']['decode_native_tps'], expected)

    def test_response_reordering_rejected_by_native_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix, responses, request_file = self.make_cohort(Path(temporary))
            responses[1], responses[2] = responses[2], responses[1]
            with self.assertRaisesRegex(ValueError, 'native request ID'):
                validate_cohort(prefix, responses, request_file, EPOCH, prefix.parent / 'arm')

    def test_cohort_rejects_reused_id_and_cross_request_overlap(self):
        for mode in ('reused', 'overlap'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                prefix, responses, request_file = self.make_cohort(Path(temporary))
                path = Path(str(prefix) + f'-{EPOCH:016x}-1.bin')
                events = read_capture(path.read_bytes(), 1)
                response = json.loads(responses[1].read_bytes())
                if mode == 'reused':
                    for event in events:
                        event['request_id'] = 17
                    response['timings']['raw_native_request_id'] = 17
                else:
                    for event in events:
                        event['raw_before'] -= 10000000
                        event['raw_after'] -= 10000000
                path.write_bytes(packed(events, 1))
                responses[1].write_text(json.dumps(response), encoding='utf-8')
                with self.assertRaises(ValueError):
                    validate_cohort(prefix, responses, request_file, EPOCH, prefix.parent / 'arm')

    def test_epoch_fault_marker_and_disarm_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix, responses, request_file = self.make_cohort(Path(temporary))
            fault = Path(str(prefix) + f'-{EPOCH:016x}-fault.bin')
            fault.write_bytes(b'foreign endpoint')
            with self.assertRaisesRegex(ValueError, 'fault marker'):
                validate_cohort(prefix, responses, request_file, EPOCH, prefix.parent / 'arm')
            fault.unlink()
            arm = Path(temporary) / 'arm'
            arm.write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'disarm'):
                validate_cohort(prefix, responses, request_file, EPOCH, arm_file=arm)
            arm.unlink()
            report = validate_cohort(prefix, responses, request_file, EPOCH, arm_file=arm)
            self.assertTrue(report['epoch_disarm_verified'])


if __name__ == '__main__':
    unittest.main()

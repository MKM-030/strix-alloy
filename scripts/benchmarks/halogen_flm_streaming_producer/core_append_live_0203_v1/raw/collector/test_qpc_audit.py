"""Pure RAW/QPC arithmetic and causal-linkage fixtures."""
import copy
import unittest

from qpc_audit import audit_qpc

REQUEST_SHA = 'a' * 64


def fixture(boundaries=True):
    rows = []
    samples = []
    for ordinal, actual in enumerate((2, 37, 128, 260)):
        phase = 'warmup_excluded' if ordinal == 0 else 'measured'
        response_sha = str(ordinal + 1) * 64
        request_id = 71 + ordinal
        rows.append(dict(valid=True, ordinal=ordinal, phase=phase,
            api_phase_agreement=True, api_native_identity_agreement=True,
            request_id=request_id, prompt=8192, generated_begin=1, generated_end=actual,
            generated_delta=actual - 1, decode_numerator=actual, output_cap=512,
            response_sha256=response_sha, API_response_id='cmpl-' + str(request_id),
            prefill_raw_lower_ns=200000000, prefill_raw_upper_ns=200000100,
            decode_raw_lower_ns=300000000, decode_raw_upper_ns=300000100,
            prefill_native_ns=200000000, decode_native_ns=300000000))
        sample = dict(ordinal=ordinal, phase=phase, case='code-log-fixture',
            timings=dict(raw_native_request_id=request_id), actual_input_tokens=8192,
            actual_output_tokens=actual, output_cap=512, request_sha256=REQUEST_SHA,
            response_sha256=response_sha, API_response_id='cmpl-' + str(request_id),
            http_qpc_seconds=1.0)
        if boundaries:
            sample.update(qpc_start_ns=ordinal * 2000000000,
                          qpc_end_ns=ordinal * 2000000000 + 1000000000)
        samples.append(sample)
    report = dict(schema='halogen0203.raw-side.cohort.v3', valid=True,
                  request_sha256=REQUEST_SHA, warmup_excluded=True,
                  measured_repetitions=3, samples=rows)
    return report, samples


class QpcAuditTests(unittest.TestCase):
    def test_variable_actual_outputs_cap_and_unadjusted_arithmetic(self):
        report, samples = fixture()
        audit = audit_qpc(report, samples, REQUEST_SHA)
        self.assertTrue(audit['valid'])
        self.assertEqual(audit['schema'], 'halogen0203.raw-phase.qpc-audit.v1')
        self.assertTrue(audit['serial_qpc_boundaries_verified'])
        self.assertFalse(audit['api_phase_clock_qualified'])
        self.assertEqual([row['actual_output_tokens'] for row in audit['samples']], [2, 37, 128, 260])
        row = audit['samples'][1]
        self.assertEqual(row['actual_output_tokens'], 37)
        self.assertEqual(row['output_cap'], 512)
        self.assertEqual(row['decode_numerator'], 37)
        self.assertEqual(row['generated_delta'], 36)
        self.assertEqual(row['raw_phase_sum_lower_ns'], 500000000)
        self.assertEqual(row['raw_phase_sum_upper_ns'], 500000200)
        self.assertEqual(row['raw_phase_sum_mid_ns'], 500000100)
        self.assertEqual(row['http_residual_after_raw_lower_seconds'], 0.5)
        self.assertEqual(row['http_residual_after_raw_upper_seconds'], 1.0 - 0.5000002)
        self.assertEqual(row['http_residual_after_native_seconds'], 0.5)

    def test_optional_qpc_boundaries(self):
        report, samples = fixture(False)
        audit = audit_qpc(report, samples, REQUEST_SHA)
        self.assertTrue(audit['valid'])
        self.assertFalse(audit['serial_qpc_boundaries_verified'])
        self.assertNotIn('whole_http_qpc_ns', audit['samples'][0])

    def test_causal_native_id_is_mandatory_and_exact(self):
        for value in (None, '72', True, 0, -72, 73):
            report, samples = fixture()
            samples[1]['timings']['raw_native_request_id'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                audit_qpc(report, samples, REQUEST_SHA)

    def test_request_and_response_hashes_must_match(self):
        for mode in ('request', 'sample-request', 'response', 'missing-response', 'invalid-response'):
            report, samples = fixture()
            if mode == 'request':
                report['request_sha256'] = 'b' * 64
            if mode == 'sample-request':
                samples[1]['request_sha256'] = 'b' * 64
            if mode == 'response':
                samples[1]['response_sha256'] = 'b' * 64
            if mode == 'missing-response':
                samples[1].pop('response_sha256')
            if mode == 'invalid-response':
                report['samples'][1]['response_sha256'] = 'bad'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                audit_qpc(report, samples, REQUEST_SHA)

    def test_native_id_reuse_or_response_reordering_fails(self):
        report, samples = fixture()
        report['samples'][1]['request_id'] = 71
        samples[1]['timings']['raw_native_request_id'] = 71
        with self.assertRaises(ValueError):
            audit_qpc(report, samples, REQUEST_SHA)
        report, samples = fixture()
        samples[1], samples[2] = samples[2], samples[1]
        with self.assertRaises(ValueError):
            audit_qpc(report, samples, REQUEST_SHA)

    def test_counts_numerator_and_cap_cannot_be_substituted(self):
        for target, key, value in (('raw', 'generated_end', 512),
                                    ('raw', 'decode_numerator', 512),
                                    ('raw', 'generated_delta', 37),
                                    ('raw', 'generated_begin', 0),
                                    ('sample', 'actual_input_tokens', 4096),
                                    ('sample', 'actual_output_tokens', 512),
                                    ('sample', 'output_cap', 1024)):
            report, samples = fixture()
            row = report['samples'][1] if target == 'raw' else samples[1]
            row[key] = value
            with self.subTest(target=target, key=key), self.assertRaises(ValueError):
                audit_qpc(report, samples, REQUEST_SHA)

    def test_both_raw_bounds_must_fit_each_whole_http_interval(self):
        report, samples = fixture(False)
        samples[1]['http_qpc_seconds'] = 0.4
        audit = audit_qpc(report, samples, REQUEST_SHA)
        self.assertFalse(audit['valid'])
        self.assertTrue(audit['impossible_phase_duration'])
        self.assertFalse(audit['all_lower_bounds_fit'])
        self.assertFalse(audit['all_full_upper_brackets_fit'])
        self.assertLess(audit['samples'][1]['http_residual_after_raw_lower_seconds'], 0)
        report, samples = fixture(False)
        samples[1]['http_qpc_seconds'] = 0.5000001
        audit = audit_qpc(report, samples, REQUEST_SHA)
        self.assertFalse(audit['valid'])
        self.assertFalse(audit['impossible_phase_duration'])
        self.assertTrue(audit['all_lower_bounds_fit'])
        self.assertFalse(audit['all_full_upper_brackets_fit'])

    def test_integer_qpc_boundary_fits_without_added_tolerance(self):
        report, samples = fixture()
        for ordinal, sample in enumerate(samples):
            sample['http_qpc_seconds'] = 0.5000002
            sample['qpc_end_ns'] = sample['qpc_start_ns'] + 500000200
        self.assertTrue(audit_qpc(report, samples, REQUEST_SHA)['valid'])
        samples[1]['http_qpc_seconds'] = 0.500000199
        samples[1]['qpc_end_ns'] -= 1
        audit = audit_qpc(report, samples, REQUEST_SHA)
        self.assertFalse(audit['valid'])
        self.assertEqual(audit['samples'][1]['raw_phase_sum_upper_ns']
                         - audit['samples'][1]['whole_http_qpc_ns'], 1)

    def test_qpc_boundary_presence_duration_and_serial_order(self):
        for mode in ('missing-end', 'backward', 'seconds-differ', 'overlap', 'bool'):
            report, samples = fixture()
            if mode == 'missing-end':
                samples[1].pop('qpc_end_ns')
            if mode == 'backward':
                samples[1]['qpc_end_ns'] = samples[1]['qpc_start_ns']
            if mode == 'seconds-differ':
                samples[1]['http_qpc_seconds'] = 2.0
            if mode == 'overlap':
                samples[1]['qpc_start_ns'] = 500000000
                samples[1]['qpc_end_ns'] = 1500000000
            if mode == 'bool':
                samples[1]['qpc_start_ns'] = True
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                audit_qpc(report, samples, REQUEST_SHA)

    def test_invalid_raw_duration_or_qpc_duration_fails(self):
        for key, value in (('prefill_raw_lower_ns', 0), ('decode_raw_upper_ns', 1),
                           ('prefill_native_ns', -1), ('decode_native_ns', True)):
            report, samples = fixture()
            report['samples'][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit_qpc(report, samples, REQUEST_SHA)
        for value in (0, -1, True, float('nan'), float('inf')):
            report, samples = fixture(False)
            samples[1]['http_qpc_seconds'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                audit_qpc(report, samples, REQUEST_SHA)

    def test_native_duration_is_an_observation_and_not_a_calibration(self):
        report, samples = fixture()
        report['samples'][1]['prefill_native_ns'] = 2000000000
        audit = audit_qpc(report, samples, REQUEST_SHA)
        self.assertTrue(audit['valid'])
        self.assertFalse(audit['samples'][1]['native_phase_sum_fits_whole_http'])
        self.assertLess(audit['samples'][1]['http_residual_after_native_seconds'], 0)
        self.assertEqual(audit['samples'][1]['raw_phase_sum_lower_ns'], 500000000)

    def test_four_rows_and_warmup_convention_required(self):
        for mode in ('three', 'five', 'warmup', 'phase', 'case', 'identity-agreement'):
            report, samples = fixture()
            if mode == 'three':
                samples.pop()
            if mode == 'five':
                samples.append(copy.deepcopy(samples[-1]))
            if mode == 'warmup':
                report['warmup_excluded'] = False
            if mode == 'phase':
                samples[0]['phase'] = 'measured'
            if mode == 'case':
                samples[1]['case'] = 'different'
            if mode == 'identity-agreement':
                report['samples'][1]['api_native_identity_agreement'] = False
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                audit_qpc(report, samples, REQUEST_SHA)


if __name__ == '__main__':
    unittest.main()

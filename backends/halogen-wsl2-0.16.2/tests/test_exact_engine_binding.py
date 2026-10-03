"""Offline regressions for copied bridge bindings; no engine or container launch."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import bridge_adapter as bridge
import runner


class ExactTraceBindingTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / 'profiles/preflight-sequences.json'
        self.vector = json.loads(self.path.read_text())[0][:-1]
        aggregate = sum(self.vector)
        rows = []
        begin = 0
        for index, size in enumerate(self.vector):
            rows.append(f'[preflight-bridge] range[{index}]={begin}:{begin + size}')
            begin += size
        self.log = '\n'.join([
            f'[preflight-bridge] active sha256={bridge.ENGINE_SHA} '
            f'rva={hex(bridge.SITE_RVA)} trace=1',
            f'[preflight] plan phase=1 ranges=252 aggregate={aggregate} '
            'copy=50433337536 host=20001656832',
            f'[preflight-bridge] demand aggregate={aggregate} host=20001656832 '
            'mapping=124068083904 count=252 floor=17179869184',
            *rows,
        ])

    def test_audited_engine_trace_is_accepted(self):
        runner.validate_trace(self.log, 1, self.vector)

    def test_stale_rvas_and_file_offset_cannot_qualify_trace(self):
        for stale_rva in ('0x1171030', '0x1876e70', '0x1876a40'):
            with self.subTest(rva=stale_rva):
                log = self.log.replace(f'rva={hex(bridge.SITE_RVA)}', f'rva={stale_rva}')
                with self.assertRaisesRegex(ValueError, 'exact vector'):
                    runner.validate_trace(log, 1, self.vector)

    def test_changed_engine_or_duplicate_activation_cannot_qualify_trace(self):
        for log in (self.log.replace(bridge.ENGINE_SHA, '0' * 64),
                    self.log + '\n' + self.log.splitlines()[0]):
            with self.assertRaisesRegex(ValueError, 'exact vector'):
                runner.validate_trace(log, 1, self.vector)

    def test_reviewed_registration_vectors_are_accepted(self):
        self.assertEqual(runner.trace_vector(self.path), self.vector)

    def test_manifest_seals_the_same_reviewed_registration_vectors(self):
        sequences = runner.manifest_for('trace')['artifacts']['sequences']
        seal = runner.make_seal({'artifacts': {'sequences': sequences}})
        self.assertEqual(len(seal['seal_sha256']), 64)

    def test_stale_registration_sequence_digest_is_rejected(self):
        with patch.object(runner, 'file_sha', return_value=
                          '9df3f1c86196c5e6187bebec754d56e67c4b57e660f13ca647a006dd1d42079c'):
            with self.assertRaisesRegex(ValueError, 'sequences changed'):
                runner.trace_vector(self.path)


class ExactSourceBindingTests(unittest.TestCase):
    def generate(self, root):
        engine = root / 'flash_serve'
        engine.write_bytes(b'CPU source-binding fixture')
        # ELF identity is independently covered by the exact-engine tests.
        # This fixture isolates the source gate and never executes the file.
        with patch.object(bridge, 'verify_engine') as verify:
            result = bridge.generate(ROOT / 'patches', engine, root / 'generated')
        verify.assert_called_once_with(engine.read_bytes())
        return result

    def test_pinned_current_sources_generate_a_reviewable_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.generate(Path(directory))
            self.assertEqual(result['original_sources'], result['candidate_sources'])
            self.assertEqual(result['site_rva'], '0x1877a40')
            self.assertEqual(result['site_file_offset'], '0x1876a40')

    def test_copied_hybrid_source_pin_fails_before_output_creation(self):
        stale = {**bridge.SOURCES, 'hip-register-hybrid.c':
                 '02c8480d1dd085935a42237e0f157116911bd0e4872455e136fe8e04305adc6f'}
        with tempfile.TemporaryDirectory() as directory, patch.object(bridge, 'SOURCES', stale):
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'source identity mismatch: hip-register-hybrid.c'):
                self.generate(root)
            self.assertFalse((root / 'generated').exists())


if __name__ == '__main__':
    unittest.main()
